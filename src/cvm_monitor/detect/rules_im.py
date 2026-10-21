"""Règles Inbound (Data_IM)."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule
from . import percentiles as pct


def _period_start(ctx: RuleContext) -> str:
    return ctx.im["date"].min()


def _recent(ctx: RuleContext) -> pd.DataFrame:
    days = ctx.det.get("im_lookback_days", 7)
    start = (ctx.snapshot_date - timedelta(days=days - 1)).isoformat()
    return ctx.im[ctx.im["date"] >= start]


def _by_rule(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby("rule_id").agg(
        rule_name=("rule_name", "last"), program=("program", "last"), touchpoint=("touchpoint", "last"),
        offer=("offer_name", "last"), impressions=("impressions", "sum"),
        success=("fulfillment_success", "sum"), failures=("fulfillment_failures", "sum"),
        first=("date", "min"), last=("date", "max"),
    )
    agg["attempts"] = agg["success"] + agg["failures"]
    agg["fail_rate"] = agg["failures"] / agg["attempts"].where(agg["attempts"] > 0)
    return agg


def _peers(ctx: RuleContext, p: dict, table: pd.DataFrame, col: str, direction: str, static_mask: pd.Series,
           default_gap: float) -> pd.DataFrame:
    """Règles IM hors norme vs pairs du même touchpoint (ou seuil fixe si mode = static)."""
    if p.get("mode", "percentile") == "static":
        out = table.copy()
        out["flag"], out["mode"], out["n"] = static_mask, "static", 0
        for c in ("p_low", "p50", "p_normal_high", "p_high"):
            out[c] = float("nan")
        return out
    pc, gap = pct.settings(ctx.det), p.get("min_abs_gap", default_gap)
    # Les programmes ont des comportements très différents (Mandatory Offer ~9 % d'achat, New Inbound Free < 1 %) :
    # on compare d'abord aux règles du même touchpoint ET programme, puis du touchpoint s'il y a trop peu de pairs.
    t = table.assign(peer_group=table["touchpoint"].astype(str) + " · " + table["program"].astype(str))
    fine = pct.peer_outliers(t, col, "peer_group", direction, pc, gap, static_mask)
    coarse = pct.peer_outliers(t, col, "touchpoint", direction, pc, gap, static_mask)
    use_coarse = fine["mode"] != "percentile"
    fine.loc[use_coarse] = coarse.loc[use_coarse]
    fine.loc[~use_coarse, "peer_label"] = t.loc[~use_coarse, "peer_group"]
    fine.loc[use_coarse, "peer_label"] = t.loc[use_coarse, "touchpoint"]
    return fine


def _position(r, direction: str) -> str:
    return "seuil fixe" if r["mode"] == "static" else pct.describe(r, direction, fmt_pct)


@rule("IM-FUL-01", "Échecs d'achat élevés par règle", "im", "major",
      min_attempts=500, max_failure_rate=0.50, critical_failure_rate=0.90, min_abs_gap=0.10)
def rule_fulfillment_failure(ctx: RuleContext, p: dict):
    window = ctx.det.get("im_lookback_days", 7)
    agg = _by_rule(_recent(ctx))
    agg = agg[agg["attempts"] >= p["min_attempts"]].copy()
    if agg.empty:
        return
    res = _peers(ctx, p, agg, "fail_rate", pct.HIGH, agg["fail_rate"] >= p["max_failure_rate"], p["min_abs_gap"])
    for rule_id, r in res[res["flag"]].iterrows():
        sev = "critical" if r["fail_rate"] >= p["critical_failure_rate"] else ctx.scaled(p["severity"], r["failures"])
        yield Anomaly(
            entity_type="im_rule", entity_key=str(rule_id), date=_period_start(ctx), category=r["program"],
            severity=sev, metric="fulfillment_failure_rate", value=round(r["fail_rate"], 4),
            expected=(f"< {fmt_pct(p['max_failure_rate'])}" if r["mode"] == "static"
                      else f"< {fmt_pct(r['p_high'])} (P95 des pairs {r.get('peer_label', r['touchpoint'])})"),
            volume=int(r["failures"]),
            message=(f"« {r['rule_name']} » ({r['touchpoint']}, {r['offer']}) : Fulfillment Failures% "
                     f"{fmt_pct(r['fail_rate'])} sur {window} j (Fulfillment Failures {fmt_int(r['failures'])}, "
                     f"Fulfillment Success {fmt_int(r['success'])}). {_position(r, pct.HIGH)}."),
            details={"program": r["program"], "offer": r["offer"], "success": int(r["success"]),
                     "failures": int(r["failures"]), "impressions": int(r["impressions"]), **pct.info(r),
                     "impact": f"{fmt_int(r['failures'])} clients sans leur offre",
                     "action": "Vérifier le provisioning de l'offre côté plateforme/produit."},
        )


@rule("IM-FUL-02", "Hausse globale des échecs d'achat", "im", "major", min_attempts=5000, min_abs_gap=0.02)
def global_failure_rise(ctx: RuleContext, p: dict):
    pc = pct.settings(ctx.det)
    daily = ctx.hist_im.groupby("date")[["fulfillment_success", "fulfillment_failures"]].sum().sort_index()
    attempts = daily.sum(axis=1)
    rate = (daily["fulfillment_failures"] / attempts).where(attempts >= p["min_attempts"])
    res = pct.history_outliers(rate, pct.HIGH, pc, min_abs_gap=p["min_abs_gap"])
    current = set(ctx.im["date"])
    for run in pct.runs(res, current):
        first, last, days = run.index[0], run.index[-1], len(run)
        extra = int((attempts[run.index] * (run["value"] - run["p50"])).sum())
        worst = run.loc[run["value"].idxmax()]
        base = p["severity"] if days > 1 else "minor"
        when = f"le {first}" if days == 1 else f"du {first} au {last} ({days} jours)"
        yield Anomaly(
            entity_type="global", entity_key="IM", date=first, severity=ctx.scaled(base, extra),
            metric="fulfillment_failure_rate", value=round(worst["value"], 4),
            expected=f"≤ {fmt_pct(worst['p_high'])} (P95 historique)", volume=extra,
            message=(f"Fulfillment Failures% {when} : {fmt_pct(worst['value'])} au plus haut, au-dessus du P95 "
                     f"historique {fmt_pct(worst['p_high'])} (médiane {fmt_pct(worst['p50'])}), ~{fmt_int(extra)} "
                     f"Fulfillment Failures en plus."),
            details={"days": run.index.tolist(), "last_date": last, **pct.info(worst)},
        )


@rule("IM-IMP-01", "Affichée sans achat", "im", "major", min_impressions=1000, min_abs_gap=0.05)
def impressions_without_success(ctx: RuleContext, p: dict):
    window = ctx.det.get("im_lookback_days", 7)
    agg = _by_rule(_recent(ctx))
    agg = agg[agg["impressions"] >= p["min_impressions"]].copy()
    if agg.empty:
        return
    agg["attempt_rate"] = agg["attempts"] / agg["impressions"]
    res = _peers(ctx, p, agg, "attempt_rate", pct.LOW, agg["attempts"] == 0, p["min_abs_gap"])
    for rule_id, r in res[res["flag"]].iterrows():
        yield Anomaly(
            entity_type="im_rule", entity_key=str(rule_id), date=_period_start(ctx), category=r["program"],
            severity=ctx.scaled(p["severity"], r["impressions"]), metric="fulfillment_attempt_rate",
            value=round(r["attempt_rate"], 4),
            expected="> 0" if r["mode"] == "static" else f"> {fmt_pct(r['p_low'])} (P5 des pairs {r.get('peer_label', r['touchpoint'])})",
            volume=int(r["impressions"]),
            message=(f"« {r['rule_name']} » ({r['touchpoint']}) : Impression {fmt_int(r['impressions'])}, "
                     f"Fulfillment {fmt_int(r['attempts'])} ({fmt_pct(r['attempt_rate'])}) sur {window} j. "
                     f"{_position(r, pct.LOW)}."),
            details={"program": r["program"], "offer": r["offer"], **pct.info(r)},
        )


def _weekday_factor(s: pd.Series, evaluated: set[str], min_points: int = 14) -> pd.Series:
    """Coefficient du jour de semaine (moyenne du jour ÷ moyenne globale), estimé hors jours évalués.

    Le dimanche est structurellement plus calme : sans correction, chaque dimanche paraîtrait une chute.
    Sans assez d'historique, coefficient 1 (pas de correction).
    """
    idx = pd.to_datetime(s.index)
    ref = s[~s.index.isin(evaluated)]
    ones = pd.Series(1.0, index=s.index)
    if len(ref) < min_points or ref.mean() <= 0:
        return ones
    wd = pd.Series(ref.to_numpy(), index=pd.to_datetime(ref.index).dayofweek)
    coef = (wd.groupby(level=0).mean() / ref.mean()).clip(lower=0.2)
    return pd.Series([coef.get(d, 1.0) for d in idx.dayofweek], index=s.index)


@rule("IM-IMP-02", "Chute des impressions", "im", "major", min_impressions=10000, min_rel_gap=0.30)
def impressions_drop(ctx: RuleContext, p: dict):
    pc = pct.settings(ctx.det)
    current = set(ctx.im["date"])
    for dim in ("touchpoint", "program"):
        daily = ctx.hist_im.groupby([dim, "date"])["impressions"].sum()
        for key, s in daily.groupby(level=0):
            s = s.droplevel(0).sort_index()
            factor = _weekday_factor(s, current)
            res = pct.history_outliers(s / factor, pct.LOW, pc, min_rel_gap=p["min_rel_gap"])
            for c in ("value", "p_low", "p50", "p_normal_high", "p_high"):  # retour à l'échelle réelle du jour
                res[c] = res[c] * factor.reindex(res.index)
            res = res[res["p50"] >= p["min_impressions"]]
            for run in pct.runs(res, current):
                first, last, days = run.index[0], run.index[-1], len(run)
                lost = int((run["p50"] - run["value"]).sum())
                worst = run.loc[run["value"].idxmin()]
                base = p["severity"] if days > 1 else "minor"
                when = f"le {first}" if days == 1 else f"du {first} au {last} ({days} jours)"
                yield Anomaly(
                    entity_type=dim, entity_key=str(key), date=first, category=str(key) if dim == "program" else None,
                    severity=ctx.scaled(base, lost), metric="impressions", value=worst["value"],
                    expected=f"≥ {fmt_int(worst['p_low'])} (P5 historique)", volume=lost,
                    message=(f"Impression {dim.capitalize()} « {key} » {when} : {fmt_int(worst['value'])} au plus bas, "
                             f"sous le P5 historique {fmt_int(worst['p_low'])} (médiane {fmt_int(worst['p50'])}), "
                             f"~{fmt_int(lost)} Impression en moins."),
                    details={"days": run.index.tolist(), "last_date": last, **pct.info(worst)},
                )


@rule("IM-DQ-01", "Données : conversions Inbound non alimentées", "im", "info", max_ratio=0.01)
def conversions_not_tracked(ctx: RuleContext, p: dict):
    success, conv = ctx.im["fulfillment_success"].sum(), ctx.im["conversions"].sum()
    if success > 0 and conv / success < p["max_ratio"]:
        yield Anomaly(
            entity_type="column", entity_key="Data_IM.conversions", date=_period_start(ctx),
            metric="conversions_per_success", value=round(conv / success, 5), expected=f"≥ {p['max_ratio']}",
            message=(f"Data_IM : Conversions {fmt_int(conv)} pour Fulfillment Success {fmt_int(success)} "
                     "(Conversions / Accepted non alimentées)."),
        )


@rule("IM-DQ-02", "Touchpoint sans achat", "im", "minor", min_impressions=1000)
def touchpoint_without_result(ctx: RuleContext, p: dict):
    agg = ctx.im.groupby("touchpoint")[["impressions", "fulfillment_success", "fulfillment_failures"]].sum()
    agg = agg[(agg["impressions"] >= p["min_impressions"])
              & (agg["fulfillment_success"] + agg["fulfillment_failures"] == 0)]
    for tp, r in agg.iterrows():
        yield Anomaly(
            entity_type="touchpoint", entity_key=str(tp), date=_period_start(ctx), metric="fulfillment_attempts",
            value=0, expected="> 0", volume=int(r["impressions"]),
            message=f"Touchpoint {tp} : Impression {fmt_int(r['impressions'])} depuis le {_period_start(ctx)}, Fulfillment Success 0.",
        )


@rule("IM-DQ-03", "Données Inbound en retard", "im", "major", max_lag_hours=48)
def stale_refresh(ctx: RuleContext, p: dict):
    """Program Rules Active du fichier dont le dernier rafraîchissement date de plus de `max_lag_hours`.

    Référence : le lendemain du fichier à 06 h GMT (les règles se rafraîchissent chaque nuit vers 03 h GMT).
    """
    if "last_refresh" not in ctx.im:
        return
    df = ctx.im[ctx.im["rule_status"] == "Active"] if "rule_status" in ctx.im else ctx.im
    last = df.groupby("rule_id").agg(rule_name=("rule_name", "last"), refresh=("last_refresh", "max"),
                                     impressions=("impressions", "sum"))
    refreshed = pd.to_datetime(last["refresh"].astype("string").str.replace(" GMT", "", regex=False), errors="coerce")
    ref = pd.Timestamp(ctx.snapshot_date) + pd.Timedelta(days=1, hours=6)
    last["lag_h"] = (ref - refreshed).dt.total_seconds() / 3600
    stale = last[last["lag_h"] > p["max_lag_hours"]].sort_values("lag_h", ascending=False)
    if stale.empty:
        return
    yield Anomaly(
        entity_type="dataset", entity_key="IM_refresh", date=_period_start(ctx),
        severity=ctx.scaled(p["severity"], int(stale["impressions"].sum())),
        metric="stale_rules", value=len(stale), expected=f"rafraîchies depuis moins de {p['max_lag_hours']} h",
        volume=int(stale["impressions"].sum()),
        message=(f"{len(stale)} Program Rule(s) Active non rafraîchie(s) depuis plus de {p['max_lag_hours']} h "
                 f"(la plus ancienne : {stale['refresh'].iloc[0]}, il y a {int(stale['lag_h'].iloc[0] // 24)} j), "
                 f"{fmt_int(stale['impressions'].sum())} impressions sur le mois."),
        details={"rule_ids": stale.index.astype(int).tolist()[:50], "rules": stale["rule_name"].astype(str).head(20).tolist(),
                 "max_lag_hours": round(float(stale["lag_h"].iloc[0]), 1)},
    )
