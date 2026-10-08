"""Règles Push (Data_Push). Voir ROADMAP.md §8 pour le catalogue."""

from __future__ import annotations

import pandas as pd

from ..analytics.uplift import two_proportion_test
from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule
from ..ingest.schema import PUSH_COLUMNS
from .baseline import robust_zscores

SOURCE_NAME = {v: k for k, v in PUSH_COLUMNS.items()}

# Statuts déjà couverts par PM-EXE-01 à 04 : PM-EXE-05 ne les re-signale pas
HANDLED_ELSEWHERE = ["Delivering", "Paused", "Aborted", "Delivery Stalled", "Blackout Pause", "Blackout Expired"]


def _period_start(ctx: RuleContext) -> str:
    return min(ctx.push["date"].min(), ctx.im["date"].min() if not ctx.im.empty else "9999")


def _episodes_by_bc(df: pd.DataFrame):
    """Regroupe par BC Name : (bc_name, sous-DataFrame trié, 1re date, dernière date, nb jours)."""
    for bc, g in df.groupby("bc_name", sort=False):
        g = g.sort_values("date")
        yield bc, g, g["date"].iloc[0], g["date"].iloc[-1], g["date"].nunique()


def _first(g: pd.DataFrame, col: str):
    return g[col].iloc[0] if col in g and len(g) else None


# --------------------------------------------------------------------------- exécution

@rule("PM-EXE-01", "Status Delivering bloqué", "push", "critical", min_generated=1000)
def stuck_delivering(ctx: RuleContext, p: dict):
    df = ctx.push
    df = df[(df["status"] == "Delivering") & (df["age_days"] >= 1) & (df["generated"] >= p["min_generated"])]
    for bc, g, first, last, days in _episodes_by_bc(df):
        vol = int(g["generated"].max())
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            severity=ctx.scaled(p["severity"], vol), metric="jours_bloques", value=days,
            expected="Completed en moins de 24 h", volume=vol,
            message=(f"« {bc} » en Status Delivering sur {days} jour(s) ({first} → {last}) : "
                     f"Generated {fmt_int(vol)}/jour, Sent {fmt_int(g['sent'].sum())}, "
                     f"Delivered {fmt_int(g['delivered'].sum())}."),
            details={"broadcast_ids": g["broadcast_id"].tolist(), "last_date": last,
                     "campaign": _first(g, "campaign_name")},
        )


@rule("PM-EXE-02", "Status Aborted / Delivery Stalled", "push", "major")
def aborted(ctx: RuleContext, p: dict):
    df = ctx.push[ctx.push["status"].isin(["Aborted", "Delivery Stalled"])]
    for r in df.itertuples():
        vol = max(r.generated, r.sent)
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=ctx.scaled(p["severity"], vol), metric="status", expected="Completed", volume=vol,
            message=(f"« {r.bc_name} » ({r.date}) : Status {r.status}, Generated {fmt_int(r.generated)}, "
                     f"Sent {fmt_int(r.sent)}, Delivered {fmt_int(r.delivered)}."),
            details={"bc_name": r.bc_name, "status": r.status, "campaign": r.campaign_name},
        )


@rule("PM-EXE-03", "Status Paused", "push", "major", min_days=1)
def paused(ctx: RuleContext, p: dict):
    df = ctx.push[ctx.push["status"] == "Paused"]
    for bc, g, first, last, days in _episodes_by_bc(df):
        if days < p["min_days"]:
            continue
        vol = int(g[["generated", "sent"]].max(axis=1).max())
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            severity=ctx.scaled(p["severity"], vol), metric="jours_en_pause", value=days, volume=vol,
            expected="Completed",
            message=(f"« {bc} » en Status Paused sur {days} jour(s) ({first} → {last}), "
                     f"Generated jusqu'à {fmt_int(vol)}/jour."),
            details={"broadcast_ids": g["broadcast_id"].tolist(), "dates": sorted(g["date"].unique().tolist())},
        )


@rule("PM-EXE-04", "Status Blackout", "push", "minor", max_severity="major")
def blackout(ctx: RuleContext, p: dict):
    df = ctx.push[ctx.push["status"].isin(["Blackout Pause", "Blackout Expired"])]
    for r in df.itertuples():
        unsent = max(r.generated - r.sent, 0) if r.generated > 0 else None
        undelivered = max(r.sent - r.delivered, 0)
        vol = unsent if unsent is not None else undelivered
        sev = ctx.scaled(p["severity"], vol)
        if sev == "critical" and p.get("max_severity"):
            sev = p["max_severity"]
        detail = (f"Generated − Sent = {fmt_int(unsent)}" if unsent is not None
                  else f"Sent − Delivered = {fmt_int(undelivered)}")
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=sev, metric="status", expected="Completed", volume=vol,
            message=(f"« {r.bc_name} » ({r.date}) : Status {r.status}, {detail}, "
                     f"Delivery% {fmt_pct(r.delivered / r.sent if r.sent else None)}."),
            details={"bc_name": r.bc_name, "status": r.status, "generated": r.generated, "sent": r.sent},
        )


@rule("PM-EXE-05", "Generated sans Sent", "push", "major", min_generated=1000)
def generated_not_sent(ctx: RuleContext, p: dict):
    df = ctx.push
    df = df[(df["generated"] >= p["min_generated"]) & (df["sent"] == 0) & ~df["status"].isin(HANDLED_ELSEWHERE)]
    for r in df.itertuples():
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=ctx.scaled(p["severity"], r.generated), metric="sent", value=0, expected="> 0",
            volume=r.generated,
            message=f"« {r.bc_name} » ({r.date}) : Generated {fmt_int(r.generated)}, Sent 0 (Status {r.status}).",
            details={"bc_name": r.bc_name, "status": r.status},
        )


# --------------------------------------------------------------------------- livraison

@rule("PM-DLV-01", "Delivered = 0", "push", "major", min_sent=100)
def zero_delivery(ctx: RuleContext, p: dict):
    df = ctx.business(ctx.push)
    df = df[(df["sent"] >= p["min_sent"]) & (df["delivered"] == 0) & (df["status"] != "Delivering")]
    for bc, g, first, last, days in _episodes_by_bc(df):
        sent = int(g["sent"].sum())
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            severity=ctx.scaled(p["severity"], sent), metric="delivered", value=0, expected="> 0", volume=sent,
            message=(f"« {bc} » : Delivered 0 pour Sent {fmt_int(sent)} sur {len(g)} broadcast(s) "
                     f"({first} → {last}, Status {g['status'].iloc[-1]})."),
            details={"broadcast_ids": g["broadcast_id"].tolist(), "dates": sorted(g["date"].unique().tolist()),
                     "acknowledged": int(g["acknowledged"].sum())},
        )


@rule("PM-DLV-02", "Chute du Delivery%", "push", "major", min_sent=10000)
def delivery_drop(ctx: RuleContext, p: dict):
    b = ctx.det.get("baseline", {})
    hist = ctx.business(ctx.hist_push)
    hist = hist[hist["sent"] > 0]
    if hist.empty:
        return
    current_dates = set(ctx.push["date"])
    daily = hist.groupby(["category", "date"])[["sent", "delivered"]].sum()
    total = hist.groupby("date")[["sent", "delivered"]].sum()
    total["category"] = "Toutes catégories"
    daily = pd.concat([daily.reset_index(), total.reset_index()])

    for cat, g in daily.groupby("category"):
        g = g.set_index("date").sort_index()
        rate = g["delivered"] / g["sent"]
        rate[g["sent"] < p["min_sent"]] = float("nan")
        z = robust_zscores(rate, b.get("window_days", 14), b.get("min_points", 5))
        flagged = z[(z["z"] <= -b.get("z_threshold", 3.5)) & z.index.isin(current_dates)]
        for day, row in flagged.iterrows():
            sent = int(g.loc[day, "sent"])
            missing = int(sent * (row["median"] - row["value"]))
            yield Anomaly(
                entity_type="category", entity_key=cat, date=day, category=None if cat.startswith("Toutes") else cat,
                severity=ctx.scaled(p["severity"], missing), metric="delivery_rate", value=round(row["value"], 4),
                expected=f"≈ {fmt_pct(row['median'])}", volume=missing,
                message=(f"{cat} le {day} : Delivery% {fmt_pct(row['value'])} contre {fmt_pct(row['median'])} "
                         f"habituellement (z = {row['z']:.1f}), soit ~{fmt_int(missing)} Delivered en moins."),
                details={"sent": sent, "delivered": int(g.loc[day, "delivered"]), "z": round(row["z"], 2)},
            )


@rule("PM-DLV-03", "Acknowledged % faible", "push", "minor", min_sent=1000, max_ack_rate=0.90)
def low_ack(ctx: RuleContext, p: dict):
    df = ctx.business(ctx.push)
    df = df[df["sent"] >= p["min_sent"]]
    df = df[df["acknowledged"] / df["sent"] < p["max_ack_rate"]]
    for bc, g, first, last, days in _episodes_by_bc(df):
        sent, ack = int(g["sent"].sum()), int(g["acknowledged"].sum())
        rate = ack / sent
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            severity=ctx.scaled(p["severity"], sent - ack), metric="ack_rate", value=round(rate, 4),
            expected=f"≥ {fmt_pct(p['max_ack_rate'])}", volume=sent - ack,
            message=(f"« {bc} » : Acknowledged % {fmt_pct(rate)} (Acknowledged {fmt_int(ack)} / Sent {fmt_int(sent)}) "
                     f"sur {len(g)} broadcast(s), {first} → {last}."),
            details={"broadcast_ids": g["broadcast_id"].tolist(), "dates": sorted(g["date"].unique().tolist())},
        )


# --------------------------------------------------------------------------- performance

def _mature(ctx: RuleContext) -> pd.DataFrame:
    df = ctx.conversion_scope(ctx.push)
    return df[(df["age_days"] >= ctx.det.get("maturity_days", 3)) & (df["sent"] > 0)]


@rule("PM-PRF-01", "Conv = 0", "push", "minor", min_sent=1000)
def no_conversion(ctx: RuleContext, p: dict):
    df = _mature(ctx)
    for bc, g, first, last, days in _episodes_by_bc(df):
        sent = int(g["sent"].sum())
        if g["conversions"].sum() > 0 or sent < p["min_sent"]:
            continue
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            metric="conversions", value=0, expected="> 0", volume=sent,
            message=f"« {bc} » : Conv 0 pour Sent {fmt_int(sent)} sur {days} jour(s) ({first} → {last}).",
            details={"campaign": _first(g, "campaign_name"), "broadcasts": len(g)},
        )


@rule("PM-PRF-02", "% Net Conversion négatif", "push", "minor", min_cg=1000, min_cg_conversions=30, p_value=0.05)
def negative_uplift(ctx: RuleContext, p: dict):
    df = _mature(ctx)
    for bc, g, first, last, days in _episodes_by_bc(df):
        cg, cg_conv = g["cg_size"].sum(), g["cg_conversions"].sum()
        if cg < p["min_cg"] or cg_conv < p["min_cg_conversions"]:
            continue
        tg, tg_conv = g["sent"].sum(), g["unique_conversions"].sum()
        res = two_proportion_test(tg_conv, tg, cg_conv, cg, alpha=p["p_value"])
        if res is None or res.uplift >= 0 or not res.significant:
            continue
        lost = int(-res.uplift * tg)
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            metric="uplift", value=round(res.uplift, 5), expected="≥ 0", volume=int(tg),
            message=(f"« {bc} » : TG Conv% {fmt_pct(res.tg_rate)} < % CG Conversion {fmt_pct(res.cg_rate)} "
                     f"(p = {res.p_value:.3f}), ~{fmt_int(lost)} Conv en moins ({first} → {last})."),
            details={"tg": int(tg), "tg_conv": int(tg_conv), "cg": int(cg), "cg_conv": int(cg_conv),
                     "ci95": [round(res.ci_low, 5), round(res.ci_high, 5)]},
        )


@rule("PM-PRF-03", "Fulfillment Failure (Push)", "push", "major", min_failures=10, max_failure_rate=0.20)
def push_fulfillment_failure(ctx: RuleContext, p: dict):
    df = ctx.push.copy()
    attempts = df["fulfillment_success"] + df["fulfillment_failure"]
    df["fail_rate"] = df["fulfillment_failure"] / attempts.where(attempts > 0)
    df = df[(df["fulfillment_failure"] >= p["min_failures"]) & (df["fail_rate"] >= p["max_failure_rate"])]
    for r in df.itertuples():
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=ctx.scaled(p["severity"], r.fulfillment_failure), metric="fulfillment_failure_rate",
            value=round(r.fail_rate, 4), expected=f"< {fmt_pct(p['max_failure_rate'])}", volume=r.fulfillment_failure,
            message=(f"« {r.bc_name} » ({r.date}) : Fulfillment Failure {fmt_int(r.fulfillment_failure)} "
                     f"({fmt_pct(r.fail_rate)})."),
            details={"bc_name": r.bc_name, "success": r.fulfillment_success},
        )


# --------------------------------------------------------------------------- qualité de données

@rule("PM-DQ-01", "Sent > Generated", "push", "minor")
def sent_gt_generated(ctx: RuleContext, p: dict):
    df = ctx.business(ctx.push)
    df = df[(df["generated"] > 0) & (df["sent"] > df["generated"])]
    for bc, g, first, last, days in _episodes_by_bc(df):
        excess = int((g["sent"] - g["generated"]).sum())
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            metric="sent_minus_generated", value=excess, expected="Sent ≤ Generated", volume=excess,
            message=f"« {bc} » : Sent > Generated sur {len(g)} broadcast(s) (+{fmt_int(excess)}), {first} → {last}.",
            details={"broadcast_ids": g["broadcast_id"].tolist()},
        )


@rule("PM-DQ-02", "Conv > Sent (Campaign Name)", "push", "minor")
def conversions_gt_sent(ctx: RuleContext, p: dict):
    df = ctx.push
    if ctx.det.get("exclude_seeding_from_conversion", True):
        df = df[~df["is_seeding"]]
    agg = df.groupby("campaign_name").agg(sent=("sent", "sum"), conversions=("conversions", "sum"),
                                           category=("category", "first"))
    for camp, r in agg[(agg["conversions"] > agg["sent"]) & (agg["sent"] > 0)].iterrows():
        yield Anomaly(
            entity_type="campaign", entity_key=camp, date=_period_start(ctx), category=r["category"],
            metric="conversions_per_sent", value=round(r["conversions"] / r["sent"], 3), expected="≤ 1",
            volume=int(r["conversions"]),
            message=(f"« {camp} » : Conv {fmt_int(r['conversions'])} pour Sent {fmt_int(r['sent'])} "
                     "(hors Is Seeding)."),
        )


@rule("PM-DQ-03", "Fulfillment Success > Conv", "push", "minor")
def fulfillment_gt_conversions(ctx: RuleContext, p: dict):
    df = ctx.push[(ctx.push["conversions"] > 0) & (ctx.push["fulfillment_success"] > ctx.push["conversions"])]
    for bc, g, first, last, days in _episodes_by_bc(df):
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            metric="fulfillment_minus_conversions", value=int((g["fulfillment_success"] - g["conversions"]).sum()),
            expected="Fulfillment ≤ Conversions", volume=int(g["fulfillment_success"].sum()),
            message=f"« {bc} » : Fulfillment Success > Conv sur {len(g)} broadcast(s) ({first} → {last}).",
        )


@rule("PM-DQ-04", "Overall Ctrl Grp = 0", "push", "minor", min_sent=1000)
def no_control_group(ctx: RuleContext, p: dict):
    df = ctx.conversion_scope(ctx.push)
    df = df[(df["cg_size"] == 0) & (df["sent"] > 0)]
    for bc, g, first, last, days in _episodes_by_bc(df):
        sent = int(g["sent"].sum())
        if sent < p["min_sent"]:
            continue
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            metric="cg_size", value=0, expected="> 0", volume=sent,
            message=f"« {bc} » : Overall Ctrl Grp = 0 (Sent {fmt_int(sent)}, {first} → {last}).",
        )


@rule("PM-DQ-05", "Colonne entièrement vide", "push", "info")
def empty_columns(ctx: RuleContext, p: dict):
    candidates = ["total_con_val", "conversion_value", "unique_conversion_value", "acknowledged", "delivered"]
    for col in candidates:
        if col in ctx.push and (ctx.push[col].isna() | (ctx.push[col] == 0)).all():
            yield Anomaly(
                entity_type="column", entity_key=f"Data_Push.{col}", date=_period_start(ctx),
                metric="non_empty_rows", value=0, expected="> 0",
                message=f"Data_Push : colonne {SOURCE_NAME.get(col, col)} vide sur toutes les lignes.",
            )


@rule("PM-DQ-06", "Jour manquant", "push", "major")
def missing_days(ctx: RuleContext, p: dict):
    start = pd.Timestamp(_period_start(ctx))
    expected = {d.strftime("%Y-%m-%d") for d in pd.date_range(start, pd.Timestamp(ctx.snapshot_date))}
    for label, df in (("Data_Push", ctx.push), ("Data_IM", ctx.im)):
        for day in sorted(expected - set(df["date"])):
            yield Anomaly(
                entity_type="dataset", entity_key=label, date=day, metric="rows", value=0, expected="> 0",
                message=f"Aucune ligne {label} pour le {day} (fichier du {ctx.snapshot_date}).",
            )

