"""Application FastAPI : lecture filtrable des données, valeur business, anomalies, import."""

from __future__ import annotations

import math
import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from cvm_monitor import pipeline
from cvm_monitor.analytics import kpi
from cvm_monitor.analytics.maturity import maturity_curve, nowcast
from cvm_monitor.detect import percentiles as pcs
from cvm_monitor.detect import engine as _engine  # noqa: F401  (enregistre les règles)
from cvm_monitor.detect.base import REGISTRY
from cvm_monitor.ingest.schema import SchemaError
from cvm_monitor.services import alerts
from cvm_monitor.services import filters as flt
from cvm_monitor.services import value
from cvm_monitor.storage import repository as repo

from .deps import Cfg, Conn, F, history, records, write_lock

def _clean(obj):
    """NaN / ±inf → null : JSON n'accepte pas ces valeurs (ex. un taux dont le dénominateur est nul après filtrage)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return super().render(_clean(content))


app = FastAPI(title="CVM Monitor API", version="0.1.0", default_response_class=SafeJSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
v1 = "/api/v1"


@app.get("/health")
def health(cfg: Cfg):
    return {"status": "ok", "db": str(cfg.path("db"))}


@app.get(f"{v1}/snapshots")
def snapshots(conn: Conn):
    return records(repo.list_snapshots(conn))


@app.get(f"{v1}/filters/options")
def filter_options(cfg: Cfg, conn: Conn, f: F):
    push, im = history(cfg, conn)
    return flt.options(push, im, f)


def _data(cfg, conn, f):
    push, im = history(cfg, conn)
    return flt.apply_push(push, f), flt.apply_im(im, f)


PUSH_TOTALS = ["generated", "sent", "delivered", "conversions", "cg_size", "cg_conversions"]
IM_TOTALS = ["impressions", "fulfillment_success", "fulfillment_failures"]


def _totals(push: pd.DataFrame, im: pd.DataFrame) -> dict:
    out = {c: float(push[c].sum()) if c in push else 0.0 for c in PUSH_TOTALS}
    out.update({c: float(im[c].sum()) if c in im else 0.0 for c in IM_TOTALS})
    return out


def _previous_window(f: flt.Filters) -> flt.Filters | None:
    """Période de même durée juste avant la période filtrée (nécessite deux bornes)."""
    if not (f.date_from and f.date_to):
        return None
    lo, hi = pd.Timestamp(f.date_from), pd.Timestamp(f.date_to)
    days = (hi - lo).days + 1
    prev_hi = lo - pd.Timedelta(days=1)
    prev_lo = prev_hi - pd.Timedelta(days=days - 1)
    return flt.Filters(**{**f.__dict__, "date_from": prev_lo.date().isoformat(),
                          "date_to": prev_hi.date().isoformat()})


@app.get(f"{v1}/overview")
def overview(cfg: Cfg, conn: Conn, f: F):
    push, im = _data(cfg, conn, f)
    prev_f = _previous_window(f)
    previous = None
    if prev_f:
        pp, pi = _data(cfg, conn, prev_f)
        previous = {"from": prev_f.date_from, "to": prev_f.date_to, **_totals(pp, pi)}
    return {
        "headline": kpi.headline(push, im) if not push.empty else {},
        "totals": _totals(push, im),
        "previous": previous,
        "push_daily": records(kpi.push_daily(push)) if not push.empty else [],
        "im_daily": records(kpi.im_daily(im)),
        "by_category": records(kpi.push_by(push, ["category"])) if not push.empty else [],
    }


# ------------------------------------------------------------------ valeur

def _value_frames(cfg, conn, f, camp_level, offer_level):
    push, im = _data(cfg, conn, f)
    pc = pcs.settings(cfg.detection)
    camp = value.campaigns(push, pc, level=camp_level, maturity_days=f.maturity_days,
                           exclude_categories=tuple(cfg.detection.get("non_conversion_categories", [])))
    off = value.offers(im, pc, level=offer_level)
    return camp, off


@app.get(f"{v1}/value/summary")
def value_summary(cfg: Cfg, conn: Conn, f: F,
                  campaign_level: Literal["category", "campaign", "bc"] = "bc",
                  offer_level: Literal["touchpoint", "program", "rule", "offer"] = "offer"):
    """Totaux au niveau de lecture choisi : les tuiles doivent compter la même chose que les graphiques."""
    return value.summary(*_value_frames(cfg, conn, f, campaign_level, offer_level))


@app.get(f"{v1}/value/campaigns")
def value_campaigns(cfg: Cfg, conn: Conn, f: F, level: Literal["category", "campaign", "bc"] = "bc",
                    only_underperforming: bool = False):
    camp, _ = _value_frames(cfg, conn, f, level, "offer")
    if only_underperforming and not camp.empty:
        camp = camp[camp["underperforming"]]
    return records(camp)


@app.get(f"{v1}/value/offers")
def value_offers(cfg: Cfg, conn: Conn, f: F,
                 level: Literal["touchpoint", "program", "rule", "offer"] = "offer",
                 only_underperforming: bool = False):
    _, off = _value_frames(cfg, conn, f, "bc", level)
    if only_underperforming and not off.empty:
        off = off[off["underperforming"]]
    return records(off)


# ------------------------------------------------------------------ push / inbound / campagnes

@app.get(f"{v1}/push/breakdown")
def push_breakdown(cfg: Cfg, conn: Conn, f: F,
                   group_by: Annotated[list[Literal["date", "category", "campaign_name", "bc_name",
                                                    "broadcast_id", "status"]], Query()] = ["category"]):
    push, _ = _data(cfg, conn, f)
    return records(kpi.push_by(push, list(group_by))) if not push.empty else []


@app.get(f"{v1}/inbound/daily")
def inbound_daily(cfg: Cfg, conn: Conn, f: F,
                  group_by: Annotated[list[Literal["touchpoint", "program", "rule_name", "offer_name"]],
                                      Query()] = []):
    _, im = _data(cfg, conn, f)
    return records(kpi.im_daily(im, list(group_by)))


@app.get(f"{v1}/inbound/rules")
def inbound_rules(cfg: Cfg, conn: Conn, f: F):
    _, im = _data(cfg, conn, f)
    return records(kpi.im_by_rule(im)) if not im.empty else []


@app.get(f"{v1}/campaigns/scorecard")
def scorecard(cfg: Cfg, conn: Conn, f: F, key: Literal["campaign_name", "bc_name"] = "campaign_name"):
    push, _ = _data(cfg, conn, f)
    return records(kpi.campaign_scorecard(push, key, f.maturity_days)) if not push.empty else []


@app.get(f"{v1}/maturity")
def maturity(cfg: Cfg, conn: Conn, f: F, reference_age: Annotated[int, Query(ge=7, le=30)] = 14):
    push, _ = _data(cfg, conn, f)
    curve = maturity_curve(repo.push_versions(conn), reference_age)
    return {"curve": records(curve),
            "nowcast": records(nowcast(push, curve)) if not push.empty and len(curve) >= 2 else []}


@app.get(f"{v1}/snapshots/compare")
def compare_snapshots(conn: Conn, a: int, b: int, kind: Literal["push", "im"] = "push"):
    """Écarts de volumes entre deux snapshots (b - a), par ligne de fait."""
    load, key = (repo.load_push, ["broadcast_id"]) if kind == "push" else (repo.load_im, repo.IM_KEY)
    da, db_ = load(conn, a), load(conn, b)
    if da.empty or db_.empty:
        return []
    nums = [c for c in da.select_dtypes("number").columns if c in db_ and c not in key and c != "snapshot_id"]
    m = da[key + nums].merge(db_[key + nums], on=key, how="outer", suffixes=("_a", "_b"))
    for c in nums:
        m[f"{c}_delta"] = m[f"{c}_b"].fillna(0) - m[f"{c}_a"].fillna(0)
    changed = m[[f"{c}_delta" for c in nums]].abs().sum(axis=1) > 0
    return records(m[changed])


@app.get(f"{v1}/data-quality")
def data_quality(conn: Conn, status: Annotated[list[str] | None, Query()] = None):
    df = repo.anomalies_df(conn, status=status or ["open", "ack"])
    if df.empty:
        return []
    return records(df[df["rule_id"].str.contains("-DQ-|^SNP-", regex=True)])


# ------------------------------------------------------------------ anomalies

@app.get(f"{v1}/anomalies")
def anomalies(conn: Conn, status: Annotated[list[str] | None, Query()] = None,
              severity: Annotated[list[str] | None, Query()] = None,
              rule_id: Annotated[list[str] | None, Query()] = None,
              category: Annotated[list[str] | None, Query()] = None,
              scope: str | None = None, q: str | None = None,
              date_from: str | None = None, date_to: str | None = None):
    df = repo.anomalies_df(conn, status=status)
    if df.empty:
        return []
    for col, vals in (("severity", severity), ("rule_id", rule_id), ("category", category)):
        if vals:
            df = df[df[col].isin(vals)]
    if scope:
        df = df[df["scope"] == scope]
    if date_from:
        df = df[df["date"] >= date_from]
    if date_to:
        df = df[df["date"] <= date_to]
    if q:
        hay = df[["entity_key", "message", "rule_name"]].fillna("").agg(" ".join, axis=1)
        df = df[hay.str.contains(q, case=False, regex=False)]
    return records(df)


@app.get(f"{v1}/anomalies/summary")
def anomalies_summary(conn: Conn, status: Annotated[list[str] | None, Query()] = None,
                      date_from: str | None = None, date_to: str | None = None):
    """Comptes par sévérité (total et par jour) et par règle, pour la page Risques."""
    df = repo.anomalies_df(conn, status=status or ["open", "ack"])
    if not df.empty:
        if date_from:
            df = df[df["date"] >= date_from]
        if date_to:
            df = df[df["date"] <= date_to]
    if df.empty:
        return {"by_severity": [], "by_day": [], "by_rule": []}
    sev = df.groupby("severity").size().rename("n").reset_index()
    day = df.groupby(["date", "severity"]).size().rename("n").reset_index().sort_values("date")
    rule = (df.groupby(["rule_id", "rule_name"]).agg(n=("id", "size"), volume=("volume", "sum"))
            .reset_index().sort_values("n", ascending=False).head(10))
    return {"by_severity": records(sev), "by_day": records(day), "by_rule": records(rule)}


class StatusUpdate(BaseModel):
    ids: list[int]
    status: Literal["open", "ack", "muted", "resolved"]
    by: str | None = None
    note: str | None = None


@app.patch(f"{v1}/anomalies")
def update_anomalies(body: StatusUpdate, conn: Conn):
    with write_lock:
        repo.set_status(conn, body.ids, body.status, body.by, body.note)
    return {"updated": len(body.ids)}


@app.get(f"{v1}/rules")
def rules(cfg: Cfg):
    return [{"id": r.id, "name": r.name, "scope": r.scope, "severity": r.severity,
             "enabled": cfg.rule(r.id).get("enabled", True), "defaults": r.defaults,
             "params": {k: v for k, v in cfg.rule(r.id).items() if k not in ("enabled", "severity")}}
            for r in REGISTRY.values()]


# ------------------------------------------------------------------ paramètres : canaux d'alerte

_last_test: dict[str, float] = {}
TEST_COOLDOWN_S = 5.0


@app.get(f"{v1}/settings/alerts")
def alerts_status(cfg: Cfg):
    """Configuration des canaux, sans aucun secret (l'URL du webhook et le mot de passe SMTP ne sortent jamais)."""
    return alerts.channel_status(cfg)


@app.post(f"{v1}/settings/alerts/test/{{channel}}")
def alerts_test(channel: Literal["teams", "email"], cfg: Cfg):
    """Envoie un message de test réel ; un délai minimal évite de spammer le canal par double-clic."""
    now = time.monotonic()
    if now - _last_test.get(channel, -TEST_COOLDOWN_S) < TEST_COOLDOWN_S:
        raise HTTPException(429, "Un test vient d'être envoyé : patientez quelques secondes.")
    _last_test[channel] = now
    return alerts.send_test(cfg, channel)


# ------------------------------------------------------------------ import

_jobs: dict[str, dict] = {}


def _run_import(job_id: str, cfg, filename: str, data: bytes, notify: bool) -> None:
    try:
        with write_lock:
            res = pipeline.import_upload(cfg, filename, data, notify=notify)
        _jobs[job_id] = {"state": "done", "summary": res.summary(), "skipped": res.skipped,
                         "snapshot_id": res.snapshot_id}
    except (ValueError, SchemaError) as e:
        _jobs[job_id] = {"state": "error", "error": str(e)}
    except Exception as e:  # pragma: no cover
        _jobs[job_id] = {"state": "error", "error": f"{type(e).__name__}: {e}"}


@app.post(f"{v1}/import", status_code=202)
async def import_file(cfg: Cfg, tasks: BackgroundTasks, file: UploadFile = File(...), notify: bool = False):
    if not (file.filename or "").lower().endswith((".xlsb", ".xlsx", ".xlsm")):
        raise HTTPException(400, "Extension non supportée (attendu : .xlsb)")
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"state": "running"}
    tasks.add_task(_run_import, job_id, cfg, file.filename, await file.read(), notify)
    return {"job_id": job_id}


@app.get(f"{v1}/import/{{job_id}}")
def import_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "job inconnu")
    return _jobs[job_id]


class SPAFiles(StaticFiles):
    """Fichiers statiques avec repli sur index.html (routes React côté client)."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404 and not path.replace("\\", "/").startswith("api/"):
                return await super().get_response("index.html", scope)
            raise


def mount_frontend(dist: Path) -> None:
    """Sert le build React (web/dist) si présent."""
    if dist.is_dir():
        app.mount("/", SPAFiles(directory=dist, html=True), name="web")


# Doit rester en dernier : le montage "/" ne doit pas masquer les routes de l'API.
mount_frontend(Path(__file__).resolve().parents[3] / "web" / "dist")
