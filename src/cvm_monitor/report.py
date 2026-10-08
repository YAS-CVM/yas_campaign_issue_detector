"""Rapport périodique Excel (hebdo / mensuel) à partager."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .analytics import kpi
from .config import Config
from .labels import rename
from .storage import repository as repo


def build_report(cfg: Config, conn, period: str = "week", end: date | None = None) -> Path:
    latest = repo.latest_snapshot(conn)
    if latest is None:
        raise RuntimeError("Aucun snapshot ingéré : lancer d'abord `cvm-monitor run` ou `backfill`.")
    end = end or date.fromisoformat(latest["snapshot_date"])
    start = end - timedelta(days=6) if period == "week" else end.replace(day=1)
    s, e = start.isoformat(), end.isoformat()

    push = repo.history_push(conn, latest["snapshot_date"])
    im = repo.history_im(conn, latest["snapshot_date"])
    push = push[(push["date"] >= s) & (push["date"] <= e)]
    im = im[(im["date"] >= s) & (im["date"] <= e)]
    maturity = cfg.detection.get("maturity_days", 3)

    anomalies = repo.anomalies_df(conn)
    if not anomalies.empty:
        anomalies = anomalies[(anomalies["last_seen_at"] >= s) | (anomalies["status"].isin(["open", "ack"]))]

    sheets = {
        "PM par jour": kpi.push_daily(push),
        "Campaign Category": kpi.push_by(push, ["category"]).sort_values("sent", ascending=False),
        "Campaign Name": kpi.campaign_scorecard(push[~push["is_seeding"]], "campaign_name", maturity),
        "BC Name": kpi.campaign_scorecard(push[~push["is_seeding"]], "bc_name", maturity),
        "IM par jour": kpi.im_daily(im),
        "Program Rule": kpi.im_by_rule(im).sort_values("failures", ascending=False),
        "Anomalies": anomalies.drop(columns=["details", "fingerprint"], errors="ignore"),
    }
    out = cfg.path("reports") / f"rapport_{period}_{s}_{e}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        pd.DataFrame({
            "Rapport": [f"Yas CVM Monitor : rapport {'hebdomadaire' if period == 'week' else 'mensuel'}"],
            "Période": [f"{s} → {e}"],
            "Snapshot": [latest["file_name"]],
        }).T.to_excel(xw, sheet_name="Info", header=False)
        for name, df in sheets.items():
            rename(df).to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)
    return out
