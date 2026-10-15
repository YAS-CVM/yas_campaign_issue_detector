"""Règles business : ce qui ne convertit plus (BC en Push, offre en Inbound), chiffré en conversions / valeur."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from . import percentiles as pct
from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule


def _severity(p: dict, days: int, lost: float) -> str:
    """minor pour un seul jour, major à partir de 2 jours ou d'une perte importante, critical si très élevée."""
    if lost >= p["critical_lost"]:
        return "critical"
    if days > 1 or lost >= p["major_lost"]:
        return p["severity"]
    return "minor"


def _when(first: str, last: str, days: int) -> str:
    return f"le {first}" if days == 1 else f"du {first} au {last} ({days} jours)"


@rule("BIZ-CONV-01", "BC qui ne convertit plus", "push", "major",
      min_sent=1000, min_rel_gap=0.4, min_lost=50, major_lost=500, critical_lost=5000)
def bc_stopped_converting(ctx: RuleContext, p: dict):
    """Conversions/envoi d'un BC sous sa propre normale (P5 des 28 jours précédents), chiffré en conversions et valeur.

    Seuls les envois arrivés à maturité sont jugés (les conversions arrivent après l'envoi).
    """
    maturity = ctx.det.get("maturity_days", 3)
    pc = pct.settings(ctx.det)
    snap = pd.Timestamp(ctx.snapshot_date)

    hist = ctx.conversion_scope(ctx.hist_push)
    hist = hist[hist["sent"] > 0].copy()
    hist["age"] = (snap - pd.to_datetime(hist["date"])).dt.days
    hist = hist[hist["age"] >= maturity]
    evaluated = set(ctx.conversion_scope(ctx.push).query("age_days >= @maturity")["date"])
    if hist.empty or not evaluated:
        return

    daily = hist.groupby(["bc_name", "date"]).agg(
        sent=("sent", "sum"), conv=("conversions", "sum"), value=("conversion_value", "sum"),
        category=("category", "first"), campaign=("campaign_name", "first")).reset_index()

    for bc, g in daily.groupby("bc_name", sort=False):
        g = g.set_index("date").sort_index()
        rate = (g["conv"] / g["sent"]).where(g["sent"] >= p["min_sent"])
        res = pct.history_outliers(rate, pct.LOW, pc, min_rel_gap=p["min_rel_gap"])
        for run in pct.runs(res, evaluated):
            first, last, days = run.index[0], run.index[-1], len(run)
            lost = float(((run["p50"] - run["value"]) * g.loc[run.index, "sent"]).sum())
            if lost < p["min_lost"]:
                continue
            total_conv = g["conv"].sum()
            lost_value = lost * (g["value"].sum() / total_conv) if total_conv > 0 and g["value"].sum() > 0 else None
            worst = run.loc[run["value"].idxmin()]
            impact = f"~{fmt_int(lost)} conversions perdues" + (f" (≈ {fmt_int(lost_value)} de valeur)" if lost_value else "")
            yield Anomaly(
                entity_type="bc_name", entity_key=str(bc), date=first, category=g["category"].iloc[0],
                severity=_severity(p, days, lost), metric="conversion_rate", value=round(float(worst["value"]), 5),
                expected=f"≥ {fmt_pct(worst['p_low'])} (P5 des 28 derniers jours)",
                volume=int(g.loc[run.index, "sent"].sum()),
                message=(f"« {bc} » convertit moins {_when(first, last, days)} : Conv% {fmt_pct(worst['value'])} "
                         f"contre {fmt_pct(worst['p50'])} habituellement. {impact}."),
                details={"days": run.index.tolist(), "last_date": last, "campaign": g["campaign"].iloc[0],
                         "lost_conversions": int(lost), "lost_value": None if lost_value is None else int(lost_value),
                         "impact": impact,
                         "action": "Vérifier le message, la cible et l'offre ; comparer au créneau d'envoi habituel.",
                         **pct.info(worst)},
            )


@rule("BIZ-OFR-01", "Offre qui ne convertit plus", "im", "major",
      min_impressions=1000, min_rel_gap=0.4, min_lost=50, major_lost=500, critical_lost=5000)
def offer_stopped_converting(ctx: RuleContext, p: dict):
    """Taux d'achat (Fulfillment Success / Impression) d'une offre sous sa propre normale (P5 des 28 jours précédents)."""
    pc = pct.settings(ctx.det)
    lookback = ctx.det.get("im_lookback_days", 7)
    start = (ctx.snapshot_date - timedelta(days=lookback - 1)).isoformat()
    evaluated = set(ctx.im.loc[ctx.im["date"] >= start, "date"])

    daily = ctx.hist_im.groupby(["offer_id", "date"]).agg(
        impressions=("impressions", "sum"), success=("fulfillment_success", "sum"),
        offer=("offer_name", "last"), touchpoint=("touchpoint", "last")).reset_index()

    for offer_id, g in daily.groupby("offer_id", sort=False):
        g = g.set_index("date").sort_index()
        rate = (g["success"] / g["impressions"]).where(g["impressions"] >= p["min_impressions"])
        res = pct.history_outliers(rate, pct.LOW, pc, min_rel_gap=p["min_rel_gap"])
        for run in pct.runs(res, evaluated):
            first, last, days = run.index[0], run.index[-1], len(run)
            lost = float(((run["p50"] - run["value"]) * g.loc[run.index, "impressions"]).sum())
            if lost < p["min_lost"]:
                continue
            worst = run.loc[run["value"].idxmin()]
            name = g["offer"].iloc[-1]
            impact = f"~{fmt_int(lost)} achats perdus"
            yield Anomaly(
                entity_type="offer", entity_key=str(offer_id), date=first, category=g["touchpoint"].iloc[-1],
                severity=_severity(p, days, lost), metric="take_rate", value=round(float(worst["value"]), 5),
                expected=f"≥ {fmt_pct(worst['p_low'])} (P5 des 28 derniers jours)",
                volume=int(g.loc[run.index, "impressions"].sum()),
                message=(f"Offre « {name} » ({g['touchpoint'].iloc[-1]}) convertit moins {_when(first, last, days)} : "
                         f"taux d'achat {fmt_pct(worst['value'])} contre {fmt_pct(worst['p50'])} habituellement. {impact}."),
                details={"days": run.index.tolist(), "last_date": last, "offer": name, "lost_purchases": int(lost),
                         "impact": impact,
                         "action": "Vérifier l'éligibilité, le prix/contenu de l'offre et sa règle de ciblage.",
                         **pct.info(worst)},
            )
