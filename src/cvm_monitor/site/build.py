"""Génération du site statique : une page, quatre onglets, toutes les données embarquées.

Exigence : aucun chargement à l'affichage. Le site est donc régénéré après chaque import et contient tout ce que
l'interface affiche : faits consolidés Push et IM (en colonnes, chaînes encodées par dictionnaire), versions
successives des métriques qui arrivent en retard, courbes de maturité, taux de remplissage par fichier, anomalies,
catalogue des règles et analyses pré-calculées (uplift, potentiel).

Le navigateur filtre et agrège localement (static/kpi.js reprend les formules de analytics/kpi.py) ; tout ce qui
demande une statistique (percentiles des pairs, z-test, maturité) est calculé ici, une seule fois.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from cvm_monitor.analytics import kpi
from cvm_monitor.analytics.maturity import LATE_METRICS, maturity_curves
from cvm_monitor.config import Config
from cvm_monitor.detect import engine as _engine  # noqa: F401  (enregistre les règles)
from cvm_monitor.detect import percentiles as pcs
from cvm_monitor.detect.base import REGISTRY
from cvm_monitor.services import timing, value
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect, table_exists

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
# Ordre de chargement : les onglets s'appuient sur charts, kpi et core.
ASSETS = ["app.css", "charts.js", "kpi.js", "xlsx.js", "core.js", "tab_push.js", "tab_inbound.js", "tab_analytics.js",
          "tab_alerts.js"]
SETTINGS_ASSETS = ["app.css", "settings.js"]

PUSH_DIMS = {"d": "date", "cat": "category", "camp": "campaign_name", "bc": "bc_name", "st": "status"}
PUSH_NUMS = {"gen": "generated", "sent": "sent", "ack": "acknowledged", "dlv": "delivered", "conv": "conversions",
             "uconv": "unique_conversions", "val": "conversion_value", "fs": "fulfillment_success",
             "ff": "fulfillment_failure", "cg": "cg_size", "cgc": "cg_conversions"}
IM_DIMS = {"d": "date", "tp": "touchpoint", "prog": "program", "rule": "rule_key", "offer": "offer_name",
           "prod": "product_name", "rst": "rule_status"}
IM_NUMS = {"imp": "impressions", "fs": "fulfillment_success", "ff": "fulfillment_failures", "acc": "accepted",
           "dec": "declined", "later": "maybe_later", "conv": "conversions"}
# Métriques suivies d'un fichier à l'autre (elles évoluent après l'envoi) : historique des versions.
VERSION_COLS = {"conv": "conversions", "cgc": "cg_conversions", "fs": "fulfillment_success",
                "ff": "fulfillment_failure", "val": "conversion_value"}
ANOMALY_COLS = ["id", "rule_id", "rule_name", "scope", "severity", "entity_type", "entity_key", "category", "date",
                "metric", "value", "expected", "volume", "message", "status", "first_seen_snapshot",
                "last_seen_snapshot", "first_seen_at", "last_seen_at", "occurrences", "resolved_at", "ack_by",
                "ack_note", "ack_at", "last_notified_at"]

# Description des règles (docs/PLATEFORME.md §7.1), affichée dans le tiroir d'une alerte.
RULE_DOCS = {
    'IM-DQ-01': 'Conversions IM non alimentées (conv ÷ succès < 1 %).',
    'IM-DQ-02': 'Touchpoint avec impressions mais aucun fulfillment.',
    'IM-DQ-03': 'Règle IM active dont le Last Refresh est en retard.',
    'IM-FUL-01': 'Failure% par règle IM (7 derniers jours) trop haut par rapport aux pairs du touchpoint (alerte au-dessus du P95, avec écart minimal et volume minimal).',
    'IM-FUL-02': 'Failure% journalier IM global trop haut par rapport aux historique propre (alerte au-dessus du P95, avec écart minimal et volume minimal).',
    'IM-IMP-01': 'fulfillment ÷ impressions par règle IM trop bas par rapport aux pairs du touchpoint (alerte sous le P5, avec écart minimal et volume minimal).',
    'IM-IMP-02': 'Impressions journalières (par touchpoint et programme) trop bas par rapport aux historique propre (alerte sous le P5, avec écart minimal et volume minimal).',
    'PM-DLV-01': 'Delivery% par BC trop bas par rapport aux pairs de la catégorie (alerte sous le P5, avec écart minimal et volume minimal).',
    'PM-DLV-02': 'Delivery% journalier (par catégorie et total) trop bas par rapport aux historique propre (alerte sous le P5, avec écart minimal et volume minimal).',
    'PM-DLV-03': 'Acknowledged % par BC trop bas par rapport aux pairs de la catégorie (alerte sous le P5, avec écart minimal et volume minimal).',
    'PM-DQ-01': 'Sent > Generated.',
    'PM-DQ-02': 'Conversions > Sent pour une campagne.',
    'PM-DQ-03': 'Fulfillment Success > Conversions.',
    'PM-DQ-04': 'Pas de groupe de contrôle (CG = 0) alors que Sent ≥ 1 000.',
    'PM-DQ-05': 'Colonne entièrement vide.',
    'PM-DQ-06': 'Jour manquant dans les données.',
    'PM-EXE-01': 'Broadcast bloqué en « Delivering » depuis au moins 1 jour.',
    'PM-EXE-02': 'Broadcast Aborted ou Delivery Stalled.',
    'PM-EXE-03': 'Broadcast Paused.',
    'PM-EXE-04': 'Broadcast en Blackout (rétrogradé en info : attendu, consultation seule).',
    'PM-EXE-05': 'Generated ≥ 1 000 mais Sent = 0 (ciblé, jamais envoyé).',
    'PM-PRF-01': 'Conv% par BC (envois matures) trop bas par rapport aux pairs de la catégorie (alerte sous le P5, avec écart minimal et volume minimal).',
    'PM-PRF-02': 'Uplift négatif significatif (le test z de la section 6).',
    'PM-PRF-03': 'Fulfillment Failure% par BC trop haut par rapport aux pairs de la catégorie (alerte au-dessus du P95, avec écart minimal et volume minimal).',
    'SNP-01': 'Broadcast révisé : des chiffres censés être figés ont changé depuis le fichier précédent.',
    'SNP-02': 'Broadcast disparu du fichier courant.',
    'SNP-03': 'Données IM de jours clos modifiées.',
}


@dataclass
class BuildResult:
    path: Path
    size: int
    gzip_size: int
    seconds: float

    def summary(self) -> str:
        return (f"Site généré : {self.path} ({self.size / 1024:.0f} Ko, {self.gzip_size / 1024:.0f} Ko compressé, "
                f"{self.seconds:.1f} s)")


# --------------------------------------------------------------------------------------------- encodage

def _clean(obj: Any) -> Any:
    """NaN / inf → null, types numpy → natifs : le JSON embarqué doit rester valide."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if hasattr(obj, "item"):  # scalaires numpy
        return _clean(obj.item())
    return obj


def _records(df: pd.DataFrame, cols: list[str] | None = None, digits: int = 6) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df[[c for c in cols if c in df]] if cols else df
    return json.loads(df.round(digits).to_json(orient="records"))


def _columnar(df: pd.DataFrame, dims: dict[str, str], nums: dict[str, str]) -> dict[str, Any]:
    """Table en colonnes : dimensions → codes + dictionnaire trié, mesures → entiers (vide = 0)."""
    out: dict[str, Any] = {"n": int(len(df)), "dict": {}, "cols": {}}
    for key, col in dims.items():
        s = df[col].astype("string").fillna("") if col in df else pd.Series([""] * len(df), dtype="string")
        codes, uniques = pd.factorize(s, sort=True)
        out["dict"][key] = [str(u) for u in uniques]
        out["cols"][key] = codes.tolist()
    for key, col in nums.items():
        s = pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(0, index=df.index)
        out["cols"][key] = s.fillna(0).round().astype("int64").tolist()
    return out


# --------------------------------------------------------------------------------------------- données

def _push(push: pd.DataFrame, snaps: pd.DataFrame, latest_id: int) -> dict[str, Any]:
    if push.empty:
        return {"n": 0, "dict": {}, "cols": {}}
    push = push.sort_values(["date", "broadcast_id"]).reset_index(drop=True)
    out = _columnar(push, PUSH_DIMS, PUSH_NUMS)
    sched = pd.to_datetime(push.get("scheduled_at"), errors="coerce")
    snap_idx = {sid: i for i, sid in enumerate(snaps["id"])}
    out["cols"].update({
        "id": push["broadcast_id"].astype("int64").tolist(),
        "name": push["broadcast_name"].astype("string").fillna("").tolist(),
        "seed": push["is_seeding"].astype(bool).astype(int).tolist(),
        "hour": sched.dt.hour.fillna(-1).astype(int).tolist(),
        "age": push["age_days"].astype("int64").tolist(),       # âge au dernier fichier où le broadcast figure
        "snap": push["snapshot_id"].map(snap_idx).astype(int).tolist(),
        # Absent du dernier fichier : ses valeurs ne bougeront plus (fin de mois, broadcast retiré…).
        "frozen": (push["snapshot_id"] != latest_id).astype(int).tolist(),
    })
    return out


def _im(im: pd.DataFrame) -> tuple[dict[str, Any], list[dict]]:
    if im.empty:
        return {"n": 0, "dict": {}, "cols": {}}, []
    im = im.sort_values(["date", "rule_id", "offer_id"]).reset_index(drop=True)
    im["rule_key"] = im["rule_id"].astype("int64").astype(str)
    facts = _columnar(im, IM_DIMS, IM_NUMS)
    # Fiche de chaque règle : dernière version connue de ses métadonnées.
    last = im.sort_values(["snapshot_date", "date"]).groupby("rule_id").tail(1).set_index("rule_id")
    span = im.groupby("rule_id")["date"].agg(["min", "max"])
    rules = []
    for rid in facts["dict"]["rule"]:
        r = last.loc[int(rid)]
        rules.append({
            "id": int(rid), "name": r.get("rule_name"), "program": r.get("program"), "touchpoint": r.get("touchpoint"),
            "status": r.get("rule_status"), "program_status": r.get("program_status"),
            "created_by": r.get("created_by"), "created_at": r.get("created_at"),
            "modified_by": r.get("modified_by"), "modified_at": r.get("modified_at"),
            "last_refresh": r.get("last_refresh"), "next_refresh": r.get("next_refresh"),
            "approved_by": r.get("approved_by"), "approved_at": r.get("approved_at"),
            "first_date": span.loc[int(rid), "min"], "last_date": span.loc[int(rid), "max"],
            "snapshot_date": r.get("snapshot_date"),
        })
    return facts, _clean(rules)


def _read_versions(conn) -> pd.DataFrame:
    """Toutes les versions des broadcasts, réduites aux colonnes utiles (maturité et historique)."""
    if not table_exists(conn, "push_facts"):
        return pd.DataFrame()
    cols = ", ".join(["broadcast_id", "snapshot_id", "age_days", "status", *dict.fromkeys([*VERSION_COLS.values(), *LATE_METRICS])])
    return pd.read_sql(f"SELECT {cols} FROM push_facts", conn)


def _versions(v: pd.DataFrame, snaps: pd.DataFrame) -> dict[str, Any]:
    """Versions successives des métriques tardives et du statut, une ligne par changement observé.

    Permet de répondre à « que savait-on au fichier du JJ ? » et de tracer la maturation d'un broadcast.
    """
    if v.empty:
        return {"n": 0, "dict": {}, "cols": {}}
    order = {sid: i for i, sid in enumerate(snaps["id"])}
    v = v.assign(snap=v["snapshot_id"].map(order)).sort_values(["broadcast_id", "snap"]).reset_index(drop=True)
    tracked = ["status", *VERSION_COLS.values()]
    prev = v.groupby("broadcast_id")[tracked].shift()
    changed = prev.isna().all(axis=1) | (v[tracked].ne(prev) & prev.notna()).any(axis=1)
    v = v[changed]
    out = _columnar(v, {"st": "status"}, VERSION_COLS)
    out["cols"].update({"id": v["broadcast_id"].astype("int64").tolist(), "snap": v["snap"].astype(int).tolist(),
                        "age": v["age_days"].astype(int).tolist()})
    return out


def _fill(conn, snaps: pd.DataFrame) -> dict[str, Any]:
    """Taux de remplissage (valeur non vide et non nulle) de chaque colonne, fichier par fichier.

    Une colonne vide aujourd'hui peut se remplir demain : on la suit au lieu de l'ignorer.
    """
    out: dict[str, Any] = {}
    for table in ("push_facts", "im_facts"):
        if not table_exists(conn, table):
            continue
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        skip = {"snapshot_id", "date", "age_days"}
        exprs = []
        for _, name, typ, *_ in info:
            if name in skip:
                continue
            cond = (f"\"{name}\" IS NOT NULL AND \"{name}\" <> 0" if typ in ("INTEGER", "REAL")
                    else f"\"{name}\" IS NOT NULL AND TRIM(\"{name}\") <> ''")
            exprs.append((name, f"AVG(CASE WHEN {cond} THEN 1.0 ELSE 0 END)"))
        sql = f"SELECT snapshot_id, {', '.join(e for _, e in exprs)} FROM {table} GROUP BY snapshot_id"
        df = pd.DataFrame(conn.execute(sql).fetchall(), columns=["snapshot_id", *[n for n, _ in exprs]])
        df = df.set_index("snapshot_id").reindex(snaps["id"])
        out[table.split("_")[0]] = {c: [None if pd.isna(x) else round(float(x), 4) for x in df[c]] for c in df.columns}
    return out


def _anomalies(conn) -> list[dict]:
    """Anomalies actives et résolues depuis 45 jours (le cycle de vie reste consultable)."""
    df = repo.anomalies_df(conn)
    if df.empty:
        return []
    horizon = (pd.Timestamp.now() - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    keep = (df["status"] != "resolved") | (df["resolved_at"].fillna("") >= horizon)
    df = df[keep]
    rows = _records(df, ANOMALY_COLS)
    details = df["details"].tolist()
    for r, d in zip(rows, details):
        try:
            r["details"] = json.loads(d) if d else {}
        except (TypeError, ValueError):
            r["details"] = {}
    return _clean(rows)


def _catalog(cfg: Config, anomalies: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for a in anomalies:
        counts[a["rule_id"]] = counts.get(a["rule_id"], 0) + 1
    out = []
    for r in sorted(REGISTRY.values(), key=lambda r: r.id):
        rc = cfg.rule(r.id)
        out.append({
            "id": r.id, "name": r.name, "scope": r.scope, "severity": rc.get("severity", r.severity),
            "enabled": bool(rc.get("enabled", True)), "doc": RULE_DOCS.get(r.id) or (r.func.__doc__ or "").strip(),
            "params": {**r.defaults, **{k: v for k, v in rc.items() if k not in ("enabled", "severity")}},
            "count": counts.get(r.id, 0),
        })
    return _clean(out)


def _presets(latest: str, first: str) -> dict[str, tuple[str, str]]:
    end = date.fromisoformat(latest)
    return {
        "7j": ((end - timedelta(days=6)).isoformat(), latest),
        "30j": ((end - timedelta(days=29)).isoformat(), latest),
        "mois": (end.replace(day=1).isoformat(), latest),
        "tout": (first, latest),
    }


def _analytics(cfg: Config, push: pd.DataFrame, im: pd.DataFrame) -> dict[str, Any]:
    """Statistiques pré-calculées par période type : uplift (z-test), potentiel d'amélioration (percentiles)."""
    if push.empty:
        return {"presets": {}, "periods": {}}
    det = cfg.detection
    maturity = int(det.get("maturity_days", 3))
    pc = pcs.settings(det)
    excluded = tuple(det.get("non_conversion_categories", []))
    technical = tuple(det.get("technical_bc_patterns", []))
    dates = pd.concat([push["date"], im["date"]]) if not im.empty else push["date"]
    presets = _presets(dates.max(), dates.min())
    periods: dict[str, Any] = {}
    # Seeding exclu de l'uplift : le bonus est crédité sans parcours de conversion, la comparaison TG/CG n'a pas de sens.
    organic = push[~push["is_seeding"].astype(bool)]
    sc_cols = ["campaign_name", "bc_name", "category", "broadcasts", "sent", "conversions", "unique_conversions",
               "conversion_value", "cg_size", "cg_conversions", "conv_rate", "cg_conv_rate", "uplift", "ci_low",
               "ci_high", "p_value", "significant", "incremental_conversions", "verdict"]
    val_cols = ["campaign_name", "bc_name", "category", "sent", "conversions", "conversion_value", "conv_rate", "p_low",
                "p50", "p_high", "n", "mode", "underperforming", "gap_rate", "missing", "missing_value"]
    off_cols = ["offer_name", "rule_name", "program", "touchpoint", "impressions", "fulfillment_success",
                "fulfillment_failures", "rules", "take_rate", "p_low", "p50", "n", "mode", "underperforming",
                "gap_rate", "missing_purchases"]
    for key, (lo, hi) in presets.items():
        p = organic[(organic["date"] >= lo) & (organic["date"] <= hi)]
        i = im[(im["date"] >= lo) & (im["date"] <= hi)] if not im.empty else im
        camp = value.campaigns(push[(push["date"] >= lo) & (push["date"] <= hi)], pc, level="campaign",
                               maturity_days=maturity, exclude_categories=excluded)
        bc = value.campaigns(push[(push["date"] >= lo) & (push["date"] <= hi)], pc, level="bc",
                             maturity_days=maturity, exclude_categories=excluded)
        off = value.offers(i, pc, level="offer") if not i.empty else pd.DataFrame()
        rules = value.offers(i, pc, level="rule") if not i.empty else pd.DataFrame()
        # Sans assez de pairs (repli statique), la référence est la médiane de toute la population (value._finish) :
        # on l'affiche à la place d'un vide.
        for df, rate in ((camp, "conv_rate"), (bc, "conv_rate"), (off, "take_rate"), (rules, "take_rate")):
            if not df.empty:
                df["p50"] = df["p50"].fillna(df[rate].median())
        periods[key] = {
            "scorecard_campaign": _records(kpi.campaign_scorecard(p, "campaign_name", maturity), sc_cols) if not p.empty else [],
            "scorecard_bc": _records(kpi.campaign_scorecard(p, "bc_name", maturity), sc_cols) if not p.empty else [],
            "value_campaign": _records(camp, val_cols), "value_bc": _records(bc, val_cols),
            "value_offer": _records(off, off_cols), "value_rule": _records(rules, off_cols),
            "summary": value.summary(bc, off) if not bc.empty or not off.empty else {},
            "timing": timing.best_times(
                timing.scope(push[(push["date"] >= lo) & (push["date"] <= hi)], maturity_days=maturity,
                             exclude_categories=excluded, technical_patterns=technical),
                blackout=det.get("sms_blackout")),
        }
    trends = timing.bc_trends(timing.scope(push, maturity_days=maturity, exclude_categories=excluded,
                                           technical_patterns=technical))
    return _clean({"presets": presets, "periods": periods, "bc_trends": trends})


def _notifications(conn) -> list[dict]:
    df = repo.notifications_df(conn)
    return _clean(_records(df.head(200)))


def build_payload(cfg: Config, conn) -> dict[str, Any]:
    snaps = repo.list_snapshots(conn)
    det = cfg.detection
    meta: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "maturity_days": int(det.get("maturity_days", 3)),
        "non_conversion_categories": det.get("non_conversion_categories", []),
        "technical_bc_patterns": det.get("technical_bc_patterns", []),
        "test_categories": det.get("test_categories", ["UAT"]),
        "percentiles": pcs.settings(det),
        "dashboard_url": cfg.notify.get("dashboard_url"),
    }
    if snaps.empty:
        return {"meta": meta, "snapshots": [], "empty": True}
    snaps = snaps.sort_values(["snapshot_date", "id"]).reset_index(drop=True)
    latest = snaps.iloc[-1]
    push = repo.history_push(conn, latest["snapshot_date"])
    im = repo.history_im(conn, latest["snapshot_date"])
    versions_df = _read_versions(conn)
    ref_age = int(det.get("maturity_reference_age", 10))
    anomalies = _anomalies(conn)
    im_facts, im_rules = _im(im)
    meta["latest"] = _clean(latest.drop(labels=["file_hash", "columns"], errors="ignore").to_dict())
    meta["maturity_reference_age"] = ref_age
    return {
        "meta": meta,
        "snapshots": _records(snaps.drop(columns=["file_hash", "columns"], errors="ignore")),
        "push": _push(push, snaps, int(latest["id"])),
        "im": im_facts,
        "im_rules": im_rules,
        "versions": _versions(versions_df, snaps),
        "curves": maturity_curves(versions_df, LATE_METRICS, ref_age),
        "fill": _fill(conn, snaps),
        "anomalies": anomalies,
        "catalog": _catalog(cfg, anomalies),
        "notifications": _notifications(conn),
        "analytics": _analytics(cfg, push, im),
    }


# --------------------------------------------------------------------------------------------- écriture

def _hashed(name: str, content: bytes) -> str:
    stem, ext = name.rsplit(".", 1)
    return f"{stem}.{hashlib.sha1(content).hexdigest()[:10]}.{ext}"


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _publish_assets(site: Path) -> dict[str, str]:
    """Copie les assets sous un nom contenant leur empreinte (cache navigateur permanent, invalidé au changement)."""
    assets = site / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    urls: dict[str, str] = {}
    for f in sorted(STATIC.iterdir()):
        if f.is_file():
            content = f.read_bytes()
            name = _hashed(f.name, content)
            if not (assets / name).exists():
                _write_atomic(assets / name, content)
            urls[f.name] = f"assets/{name}"
    keep = set(Path(u).name for u in urls.values())
    for old in assets.iterdir():  # anciennes versions des assets
        if old.name not in keep:
            old.unlink(missing_ok=True)
    return urls


def _json_for_html(payload: dict[str, Any]) -> str:
    # « </ » fermerait la balise <script> : on l'échappe ; le JSON reste équivalent.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")


def build_site(cfg: Config, conn=None) -> BuildResult:
    started = time.perf_counter()
    own = conn is None
    conn = conn or connect(cfg.path("db"))
    try:
        payload = build_payload(cfg, conn)
    finally:
        if own:
            conn.close()
    site = cfg.path("site") if "site" in cfg.raw.get("paths", {}) else cfg.root / "site"
    site.mkdir(parents=True, exist_ok=True)
    urls = _publish_assets(site)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
    ctx = {"assets": urls, "meta": payload["meta"], "css": urls["app.css"],
           "logo": (HERE / "templates" / "logo.svg").read_text(encoding="utf-8"),
           "scripts": [urls[a] for a in ASSETS if a.endswith(".js")]}
    html = env.get_template("index.html.j2").render(payload_json=_json_for_html(payload), **ctx).encode("utf-8")
    _write_atomic(site / "index.html", html)
    settings = env.get_template("settings.html.j2").render(
        snapshots=payload.get("snapshots", []), scripts=[urls[a] for a in SETTINGS_ASSETS if a.endswith(".js")],
        **{k: v for k, v in ctx.items() if k != "scripts"}).encode("utf-8")
    _write_atomic(site / "settings.html", settings)
    return BuildResult(site / "index.html", len(html), len(gzip.compress(html, 6)), time.perf_counter() - started)
