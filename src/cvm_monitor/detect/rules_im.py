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
    return pct.peer_outliers(table, col, "touchpoint", direction, pct.settings(ctx.det),
                             p.get("min_abs_gap", default_gap), static_mask)


def _position(r, direction: str) -> str:
    return "seuil fixe" if r["mode"] == "static" else pct.describe(r, direction, fmt_pct)


@rule("IM-FUL-01", "Program Rule : Fulfillment Failures", "im", "major",
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
                      else f"< {fmt_pct(r['p_high'])} (P95 des pairs {r['touchpoint']})"),
            volume=int(r["failures"]),
            message=(f"« {r['rule_name']} » ({r['touchpoint']}, {r['offer']}) : Fulfillment Failures% "
                     f"{fmt_pct(r['fail_rate'])} sur {window} j (Fulfillment Failures {fmt_int(r['failures'])}, "
                     f"Fulfillment Success {fmt_int(r['success'])}). {_position(r, pct.HIGH)}."),
            details={"program": r["program"], "offer": r["offer"], "success": int(r["success"]),
                     "failures": int(r["failures"]), "impressions": int(r["impressions"]), **pct.info(r)},
        )


@rule("IM-FUL-02", "Hausse du Fulfillment Failures%", "im", "major", min_attempts=5000, min_abs_gap=0.02)
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


@rule("IM-IMP-01", "Impression sans Fulfillment", "im", "major", min_impressions=1000, min_abs_gap=0.05)
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
            expected="> 0" if r["mode"] == "static" else f"> {fmt_pct(r['p_low'])}", volume=int(r["impressions"]),
            message=(f"« {r['rule_name']} » ({r['touchpoint']}) : Impression {fmt_int(r['impressions'])}, "
                     f"Fulfillment {fmt_int(r['attempts'])} ({fmt_pct(r['attempt_rate'])}) sur {window} j. "
                     f"{_position(r, pct.LOW)}."),
            details={"program": r["program"], "offer": r["offer"], **pct.info(r)},
        )


@rule("IM-IMP-02", "Chute des Impression", "im", "major", min_impressions=10000, min_rel_gap=0.30)
def impressions_drop(ctx: RuleContext, p: dict):
    pc = pct.settings(ctx.det)
    current = set(ctx.im["date"])
    for dim in ("touchpoint", "program"):
        daily = ctx.hist_im.groupby([dim, "date"])["impressions"].sum()
        for key, s in daily.groupby(level=0):
            s = s.droplevel(0).sort_index()
            res = pct.history_outliers(s, pct.LOW, pc, min_rel_gap=p["min_rel_gap"])
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


@rule("IM-DQ-01", "Conversions Data_IM non alimentées", "im", "info", max_ratio=0.01)
def conversions_not_tracked(ctx: RuleContext, p: dict):
    success, conv = ctx.im["fulfillment_success"].sum(), ctx.im["conversions"].sum()
    if success > 0 and conv / success < p["max_ratio"]:
        yield Anomaly(
            entity_type="column", entity_key="Data_IM.conversions", date=_period_start(ctx),
            metric="conversions_per_success", value=round(conv / success, 5), expected=f"≥ {p['max_ratio']}",
            message=(f"Data_IM : Conversions {fmt_int(conv)} pour Fulfillment Success {fmt_int(success)} "
                     "(Conversions / Accepted non alimentées)."),
        )


@rule("IM-DQ-02", "Touchpoint sans Fulfillment", "im", "minor", min_impressions=1000)
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


@rule("IM-DQ-03", "Last Refresh Date Time en retard", "im", "major")
def stale_refresh(ctx: RuleContext, p: dict):
    if "last_refresh" not in ctx.im:
        return
    df = ctx.im[ctx.im.get("rule_status", "Active") == "Active"]
    last = df.groupby("rule_id").agg(rule_name=("rule_name", "last"), refresh=("last_refresh", "max"))
    last["refresh_date"] = pd.to_datetime(last["refresh"], errors="coerce").dt.date
    stale = last[last["refresh_date"].notna() & (last["refresh_date"] < ctx.snapshot_date)]
    if len(stale):
        oldest = stale["refresh"].min()
        yield Anomaly(
            entity_type="dataset", entity_key="IM_refresh", date=ctx.snapshot_date.isoformat(),
            metric="stale_rules", value=len(stale), expected="0", volume=len(stale),
            message=(f"{len(stale)} Program Rule Active avec Last Refresh Date Time avant le {ctx.snapshot_date} "
                     f"(min : {oldest})."),
            details={"rules": stale["rule_name"].astype(str).head(20).tolist()},
        )
