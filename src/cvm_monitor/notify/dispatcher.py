"""Choix de ce qui est envoyé, à qui et quand (anti-doublon, rappels)."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..analytics.kpi import headline
from ..config import Config, severity_rank
from ..storage import repository as repo
from . import email as mail
from . import teams

log = logging.getLogger(__name__)

TEMPLATES = Path(__file__).parent / "templates"
LABELS = {"critical": "Critique", "major": "Majeure", "minor": "Mineure", "info": "Info"}
COLORS = {
    "critical": {"bg": "#fde8e8", "fg": "#b42318"},
    "major": {"bg": "#fff1e0", "fg": "#b54708"},
    "minor": {"bg": "#fef9c3", "fg": "#854d0e"},
    "info": {"bg": "#eef2f6", "fg": "#475467"},
}


def _at_least(df: pd.DataFrame, severity: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["severity"].map(severity_rank) >= severity_rank(severity)]


def _counts(df: pd.DataFrame) -> dict[str, int]:
    return df["severity"].value_counts().to_dict() if not df.empty else {}


def _fmt_int(v) -> str:
    return "–" if v is None else f"{int(round(v)):,}".replace(",", " ")


def _fmt_pct(v) -> str:
    return "–" if v is None else f"{100 * v:.1f} %"


def _kpi_tiles(kpis: dict) -> list[dict]:
    spec = [("Sent", "sent", _fmt_int, True), ("Delivery%", "delivery_rate", _fmt_pct, True),
            ("Conv", "conversions", _fmt_int, True), ("Impression", "impressions", _fmt_int, True),
            ("Fulfillment Failures%", "im_failure_rate", _fmt_pct, False)]
    tiles = []
    for label, key, fmt, up_is_good in spec:
        k = kpis.get(key) or {}
        value, ref = k.get("value"), k.get("ref7")
        delta = text = None
        if value is not None and ref:
            if "rate" in key:  # taux : écart en points
                delta, text = (value - ref) / ref, f"{100 * (value - ref):+.1f} pt"
            else:
                delta = (value - ref) / ref
                text = f"{delta:+.0%}"
        color = "#6b7280"
        if delta is not None and abs(delta) >= 0.05:
            color = "#067647" if (delta > 0) == up_is_good else "#b42318"
        tiles.append({"label": label, "value": fmt(value), "delta": text, "color": color})
    return tiles


def render_digest(cfg: Config, snapshot, sync: repo.SyncResult, new: pd.DataFrame, open_: pd.DataFrame,
                  resolved: pd.DataFrame, kpis: dict) -> tuple[str, str, str]:
    min_sev = cfg.notify.get("email", {}).get("min_severity", "minor")
    counts = _counts(open_)
    title = f"Surveillance des campagnes du {snapshot['snapshot_date']}"
    subject = (f"{cfg.notify.get('email', {}).get('subject_prefix', '[Yas CVM Monitor]')} {snapshot['snapshot_date']} : "
               f"{counts.get('critical', 0)} critique(s), {counts.get('major', 0)} majeure(s), {len(new)} nouvelle(s)")
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template("digest.html.j2").render(
        title=title, file_name=snapshot["file_name"], date_min=snapshot["date_min"], date_max=snapshot["date_max"],
        kpis=_kpi_tiles(kpis) if kpis else [], kpi_date=kpis.get("date") if kpis else None,
        severities=[{"label": LABELS[s], "count": counts.get(s, 0), **COLORS[s]} for s in ("critical", "major", "minor")],
        sync_summary=f"Depuis le fichier précédent : {sync.summary()}.",
        sections=[
            {"title": "Nouvelles anomalies", "rows": list(_at_least(new, min_sev).itertuples()), "limit": 25},
            {"title": "Toujours ouvertes (critiques et majeures)",
             "rows": list(_at_least(open_[~open_["id"].isin(new["id"])], "major").itertuples()), "limit": 15},
            {"title": "Résolues", "rows": list(resolved.itertuples()), "limit": 10},
        ],
        labels=LABELS, colors=COLORS, dashboard_url=cfg.notify.get("dashboard_url"),
    )
    text = f"{title}\n{sync.summary()}\n\n" + "\n".join(
        f"[{LABELS[r.severity]}] {r.rule_id} - {r.message}" for r in _at_least(new, min_sev).itertuples())
    return subject, html, text


def dispatch(cfg: Config, conn, snapshot, sync: repo.SyncResult) -> dict[str, str]:
    ncfg = cfg.notify
    today = date.fromisoformat(snapshot["snapshot_date"])
    new = repo.anomalies_df(conn, ids=sync.to_notify)
    new = new[new["status"] == "open"] if not new.empty else new
    open_ = repo.anomalies_df(conn, status=["open"])
    resolved = repo.anomalies_df(conn, ids=sync.resolved)
    results: dict[str, str] = {}

    # ---- Teams : nouvelles anomalies graves + rappels
    tcfg = ncfg.get("teams", {})
    webhook = cfg.env("TEAMS_WEBHOOK_URL")
    if not tcfg.get("enabled", True):
        results["teams"] = "désactivé"
    elif not webhook:
        results["teams"] = "non configuré (TEAMS_WEBHOOK_URL)"
    else:
        min_sev = tcfg.get("min_severity", "major")
        reminder_ids = set(repo.reminder_candidates(conn, ncfg.get("realert_after_days", 3), min_sev, today))
        reminder_ids -= set(new["id"]) if not new.empty else set()
        items = pd.concat([_at_least(new, min_sev), repo.anomalies_df(conn, ids=sorted(reminder_ids))])
        if items.empty:
            results["teams"] = "rien à signaler"
        else:
            card = teams.build_card(
                title=f"Yas CVM Monitor : {len(items)} anomalie(s) à traiter",
                subtitle=f"Fichier du {snapshot['snapshot_date']} · {sync.summary()}",
                items=items, counts=_counts(items), dashboard_url=ncfg.get("dashboard_url"),
                max_items=tcfg.get("max_items", 5),
            )
            try:
                teams.post_card(webhook, card)
                repo.mark_notified(conn, items["id"].astype(int).tolist())
                repo.log_notification(conn, snapshot["id"], "teams", len(items), True)
                results["teams"] = f"envoyé ({len(items)} anomalies)"
            except Exception as e:
                log.error("Teams : %s", e)
                repo.log_notification(conn, snapshot["id"], "teams", len(items), False, str(e))
                results["teams"] = f"ERREUR : {e}"

    # ---- E-mail : récapitulatif
    ecfg = ncfg.get("email", {})
    if not ecfg.get("enabled", True):
        results["email"] = "désactivé"
    elif not mail.is_configured(cfg):
        results["email"] = "non configuré (MAIL_TO / SMTP_HOST)"
    elif new.empty and not ecfg.get("send_when_nothing_new", True):
        results["email"] = "rien de nouveau"
    else:
        kpis = headline(repo.load_push(conn, snapshot["id"]), repo.load_im(conn, snapshot["id"]))
        subject, html, text = render_digest(cfg, snapshot, sync, new, open_, resolved, kpis)
        csv = cfg.path("reports") / f"anomalies_{snapshot['snapshot_date']}.csv"
        attachments = [csv] if ecfg.get("attach_csv", True) and csv.exists() else []
        try:
            mail.send_email(cfg, subject, html, text, attachments)
            if not new.empty:
                repo.mark_notified(conn, _at_least(new, ecfg.get("min_severity", "minor"))["id"].astype(int).tolist())
            repo.log_notification(conn, snapshot["id"], "email", len(new), True)
            results["email"] = f"envoyé à {', '.join(mail.recipients(cfg))}"
        except Exception as e:
            log.error("E-mail : %s", e)
            repo.log_notification(conn, snapshot["id"], "email", len(new), False, str(e))
            results["email"] = f"ERREUR : {e}"

    conn.commit()
    return results


def preview_digest(cfg: Config, conn, snapshot, out: Path) -> Path:
    """Écrit le récapitulatif HTML sur disque sans l'envoyer (aperçu)."""
    ids = repo.anomalies_df(conn, status=["open"])
    sync = repo.SyncResult(new=ids["id"].astype(int).tolist() if not ids.empty else [])
    kpis = headline(repo.load_push(conn, snapshot["id"]), repo.load_im(conn, snapshot["id"]))
    _, html, _ = render_digest(cfg, snapshot, sync, ids, ids, ids.iloc[0:0], kpis)
    out.write_text(html, encoding="utf-8")
    return out
