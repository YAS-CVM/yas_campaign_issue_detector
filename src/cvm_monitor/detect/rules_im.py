"""Règles Inbound (Data_IM)."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule
from .baseline import robust_zscores


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


@rule("IM-FUL-01", "Program Rule : Fulfillment Failures", "im", "major",
      min_attempts=500, max_failure_rate=0.50, critical_failure_rate=0.90)
def rule_fulfillment_failure(ctx: RuleContext, p: dict):
    window = ctx.det.get("im_lookback_days", 7)
    agg = _by_rule(_recent(ctx))
    agg = agg[(agg["attempts"] >= p["min_attempts"]) & (agg["fail_rate"] >= p["max_failure_rate"])]
    for rule_id, r in agg.iterrows():
        sev = "critical" if r["fail_rate"] >= p["critical_failure_rate"] else ctx.scaled(p["severity"], r["failures"])
        yield Anomaly(
            entity_type="im_rule", entity_key=str(rule_id), date=_period_start(ctx), category=r["program"],
            severity=sev, metric="fulfillment_failure_rate", value=round(r["fail_rate"], 4),
            expected=f"< {fmt_pct(p['max_failure_rate'])}", volume=int(r["failures"]),
            message=(f"« {r['rule_name']} » ({r['touchpoint']}, {r['offer']}) : Fulfillment Failures% "
                     f"{fmt_pct(r['fail_rate'])} sur {window} j (Fulfillment Failures {fmt_int(r['failures'])}, "
                     f"Fulfillment Success {fmt_int(r['success'])})."),
            details={"program": r["program"], "offer": r["offer"], "success": int(r["success"]),
                     "failures": int(r["failures"]), "impressions": int(r["impressions"])},
        )


@rule("IM-FUL-02", "Hausse du Fulfillment Failures%", "im", "major", min_attempts=5000)
def global_failure_rise(ctx: RuleContext, p: dict):
    b = ctx.det.get("baseline", {})
    daily = ctx.hist_im.groupby("date")[["fulfillment_success", "fulfillment_failures"]].sum().sort_index()
    attempts = daily.sum(axis=1)
    rate = (daily["fulfillment_failures"] / attempts).where(attempts >= p["min_attempts"])
    z = robust_zscores(rate, b.get("window_days", 14), b.get("min_points", 5))
    current = set(ctx.im["date"])
    for day, row in z[(z["z"] >= b.get("z_threshold", 3.5)) & z.index.isin(current)].iterrows():
        extra = int(attempts[day] * (row["value"] - row["median"]))
        yield Anomaly(
            entity_type="global", entity_key="IM", date=day, severity=ctx.scaled(p["severity"], extra),
            metric="fulfillment_failure_rate", value=round(row["value"], 4), expected=f"≈ {fmt_pct(row['median'])}",
            volume=extra,
            message=(f"Fulfillment Failures% le {day} : {fmt_pct(row['value'])} contre {fmt_pct(row['median'])} "
                     f"habituellement (z = {row['z']:.1f}), ~{fmt_int(extra)} Fulfillment Failures en plus."),
            details={"attempts": int(attempts[day]), "z": round(row["z"], 2)},
        )


@rule("IM-IMP-01", "Impression sans Fulfillment", "im", "major", min_impressions=1000)
def impressions_without_success(ctx: RuleContext, p: dict):
    window = ctx.det.get("im_lookback_days", 7)
    agg = _by_rule(_recent(ctx))
    agg = agg[(agg["impressions"] >= p["min_impressions"]) & (agg["attempts"] == 0)]
    for rule_id, r in agg.iterrows():
        yield Anomaly(
            entity_type="im_rule", entity_key=str(rule_id), date=_period_start(ctx), category=r["program"],
            severity=ctx.scaled(p["severity"], r["impressions"]), metric="fulfillment_attempts", value=0,
            expected="> 0", volume=int(r["impressions"]),
            message=(f"« {r['rule_name']} » ({r['touchpoint']}) : Impression {fmt_int(r['impressions'])}, "
                     f"Fulfillment Success 0, Fulfillment Failures 0 sur {window} j."),
            details={"program": r["program"], "offer": r["offer"]},
        )


@rule("IM-IMP-02", "Chute des Impression", "im", "major", min_impressions=10000)
def impressions_drop(ctx: RuleContext, p: dict):
    b = ctx.det.get("baseline", {})
    current = set(ctx.im["date"])
    for dim in ("touchpoint", "program"):
        daily = ctx.hist_im.groupby([dim, "date"])["impressions"].sum()
        for key, s in daily.groupby(level=0):
            s = s.droplevel(0).sort_index()
            z = robust_zscores(s, b.get("window_days", 14), b.get("min_points", 5))
            flagged = z[(z["z"] <= -b.get("z_threshold", 3.5)) & (z["median"] >= p["min_impressions"])
                        & z.index.isin(current)]
            for day, row in flagged.iterrows():
                lost = int(row["median"] - row["value"])
                yield Anomaly(
                    entity_type=dim, entity_key=str(key), date=day, category=str(key) if dim == "program" else None,
                    severity=ctx.scaled(p["severity"], lost), metric="impressions", value=row["value"],
                    expected=f"≈ {fmt_int(row['median'])}", volume=lost,
                    message=(f"Impression {dim.capitalize()} « {key} » le {day} : {fmt_int(row['value'])} contre "
                             f"{fmt_int(row['median'])} habituellement (z = {row['z']:.1f})."),
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
