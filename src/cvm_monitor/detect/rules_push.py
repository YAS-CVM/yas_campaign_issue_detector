"""Règles Push (Data_Push). Voir ROADMAP.md §8 pour le catalogue."""

from __future__ import annotations

import pandas as pd

from ..analytics.uplift import two_proportion_test
from ..config import severity_rank
from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule
from ..ingest.schema import PUSH_COLUMNS
from . import percentiles as pct

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

@rule("PM-EXE-01", "Envoi bloqué en Delivering", "push", "critical", min_generated=1000)
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
                     "campaign": _first(g, "campaign_name"),
                     "impact": f"{fmt_int(vol)} clients/jour non servis",
                     "action": "Vérifier l'exécution dans NEON-dx et relancer le broadcast."},
        )


@rule("PM-EXE-02", "Envoi interrompu (Aborted / Delivery Stalled)", "push", "major", min_volume=0)
def aborted(ctx: RuleContext, p: dict):
    """Arrêt anormal d'un broadcast à fort volume ; un arrêt dans la fenêtre de blackout SMS est attendu."""
    df = ctx.push[ctx.push["status"].isin(["Aborted", "Delivery Stalled"])]
    df = df[~ctx.in_blackout(df["scheduled_at"])] if "scheduled_at" in df else df
    for r in df.itertuples():
        vol = max(r.generated, r.sent)
        if vol < p["min_volume"]:
            continue
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=ctx.scaled(p["severity"], vol), metric="status", expected="Completed", volume=vol,
            message=(f"« {r.bc_name} » ({r.date}) : Status {r.status}, Generated {fmt_int(r.generated)}, "
                     f"Sent {fmt_int(r.sent)}, Delivered {fmt_int(r.delivered)}."),
            details={"bc_name": r.bc_name, "status": r.status, "campaign": r.campaign_name,
                     "impact": f"{fmt_int(vol)} clients non servis",
                     "action": "Relancer le broadcast ou le reprogrammer hors blackout (19h-07h)."},
        )


@rule("PM-EXE-03", "Envoi en pause", "push", "major", min_days=1)
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


@rule("PM-EXE-04", "Envoi en blackout", "push", "minor", max_severity="major")
def blackout(ctx: RuleContext, p: dict):
    df = ctx.push[ctx.push["status"].isin(["Blackout Pause", "Blackout Expired"])]
    for r in df.itertuples():
        unsent = max(r.generated - r.sent, 0) if r.generated > 0 else None
        undelivered = max(r.sent - r.delivered, 0)
        vol = unsent if unsent is not None else undelivered
        sev = ctx.scaled(p["severity"], vol)
        if p.get("max_severity") and severity_rank(sev) > severity_rank(p["max_severity"]):
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


@rule("PM-EXE-05", "Ciblé mais non envoyé", "push", "major", min_generated=1000)
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


# Statuts dont la sémantique est connue ; tout autre statut est transitoire (ou nouveau) et ne doit pas durer.
KNOWN_STATUSES = {"Completed", "Delivering", "Paused", "Aborted", "Delivery Stalled", "Blackout Pause", "Blackout Expired"}


@rule("PM-EXE-06", "Blackout expiré : volume non envoyé", "push", "major", min_generated=1000, max_sent_ratio=0.01)
def blackout_expired_unsent(ctx: RuleContext, p: dict):
    """La fenêtre de blackout a expiré avant l'envoi : le volume ciblé n'est jamais parti."""
    df = ctx.push[(ctx.push["status"] == "Blackout Expired") & (ctx.push["generated"] >= p["min_generated"])]
    df = df[df["sent"] <= df["generated"] * p["max_sent_ratio"]]
    for r in df.itertuples():
        unsent = int(r.generated - r.sent)
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=ctx.scaled(p["severity"], unsent), metric="unsent", value=unsent, expected="envoi avant expiration",
            volume=unsent,
            message=(f"« {r.bc_name} » ({r.date}) : blackout expiré, {fmt_int(r.generated)} clients ciblés, "
                     f"{fmt_int(r.sent)} envoyés. À reprogrammer hors fenêtre de blackout."),
            details={"bc_name": r.bc_name, "campaign": r.campaign_name, "generated": int(r.generated), "sent": int(r.sent)},
        )


@rule("PM-EXE-07", "Statut transitoire prolongé", "push", "major", min_days=1)
def transient_status(ctx: RuleContext, p: dict):
    """Broadcast resté plus d'un jour dans un statut transitoire ou inconnu (Targeting, Render Scheduled…)."""
    df = ctx.push[~ctx.push["status"].isin(KNOWN_STATUSES) & (ctx.push["age_days"] >= p["min_days"])]
    for r in df.itertuples():
        vol = int(max(r.generated, r.sent))
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r.broadcast_id), date=r.date, category=r.category,
            severity=ctx.scaled(p["severity"], vol), metric="status_age_days", value=int(r.age_days),
            expected="Completed", volume=vol,
            message=(f"« {r.bc_name} » ({r.date}) toujours en Status « {r.status} » à J+{r.age_days} "
                     f"(Generated {fmt_int(r.generated)}, Sent {fmt_int(r.sent)})."),
            details={"bc_name": r.bc_name, "status": r.status, "campaign": r.campaign_name},
        )


# --------------------------------------------------------------------------- livraison

def _bc_table(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par BC Name : volumes sommés, broadcasts et dates concernés."""
    return df.groupby("bc_name", sort=False).agg(
        category=("category", "first"), campaign=("campaign_name", "first"), status=("status", "last"),
        sent=("sent", "sum"), delivered=("delivered", "sum"), acknowledged=("acknowledged", "sum"),
        conversions=("conversions", "sum"), failures=("fulfillment_failure", "sum"),
        success=("fulfillment_success", "sum"), first=("date", "min"), last=("date", "max"),
        broadcast_ids=("broadcast_id", list), dates=("date", lambda s: sorted(set(s))),
    )


def _detect(ctx: RuleContext, p: dict, table: pd.DataFrame, col: str, direction: str, static_mask: pd.Series,
            default_gap: float) -> pd.DataFrame:
    """Lignes hors norme : percentiles des pairs (même catégorie), ou seuil fixe si mode = static."""
    if p.get("mode", "percentile") == "static":
        out = table.copy()
        out["flag"], out["mode"], out["n"] = static_mask, "static", 0
        for c in ("p_low", "p50", "p_normal_high", "p_high"):
            out[c] = float("nan")
        return out
    return pct.peer_outliers(table, col, "category", direction, pct.settings(ctx.det),
                             p.get("min_abs_gap", default_gap), static_mask)


def _position(r, direction: str) -> str:
    return "seuil fixe" if r["mode"] == "static" else pct.describe(r, direction, fmt_pct)


@rule("PM-DLV-01", "Livraison anormalement basse", "push", "major", min_sent=100, min_abs_gap=0.05)
def zero_delivery(ctx: RuleContext, p: dict):
    df = ctx.business(ctx.push)
    df = df[(df["sent"] >= p["min_sent"]) & (df["status"] != "Delivering")]
    if df.empty:
        return
    t = _bc_table(df)
    t["rate"] = t["delivered"] / t["sent"]
    res = _detect(ctx, p, t, "rate", pct.LOW, t["delivered"] == 0, p["min_abs_gap"])
    flagged = res[res["flag"]]
    # Plancher structurel : si P5 = 0, ces BC à 0 % ne sont pas des écarts isolés mais un même motif
    # (ex. Delivered non remonté pour un type de BC) -> une alerte par catégorie, pas une par BC.
    floor = flagged[(flagged["mode"] != "static") & (flagged["rate"] <= 0)]
    for cat, g in floor.groupby("category", dropna=False):
        sent, n = int(g["sent"].sum()), len(g)
        top = g.sort_values("sent", ascending=False)
        yield Anomaly(
            entity_type="category", entity_key=f"{cat} · Delivered = 0", date=g["first"].min(),
            category=None if pd.isna(cat) else cat, severity=ctx.scaled(p["severity"], sent), metric="delivery_rate",
            value=0, expected=f"> {fmt_pct(g['p50'].iloc[0])} (médiane des pairs)", volume=sent,
            message=(f"{cat} : {n} BC avec Delivered 0 pour Sent {fmt_int(sent)} (médiane des pairs "
                     f"{fmt_pct(g['p50'].iloc[0])}). Principaux : "
                     + ", ".join(f"« {b} » ({fmt_int(s)})" for b, s in zip(top.index[:3], top["sent"][:3])) + "."),
            details={"bc_names": top.index.tolist(), "broadcast_ids": [i for ids in g["broadcast_ids"] for i in ids],
                     **pct.info(g.iloc[0])},
        )
    for bc, r in flagged.drop(index=floor.index).iterrows():
        sent = int(r["sent"])
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=r["first"], category=r["category"],
            severity=ctx.scaled(p["severity"], sent - r["delivered"]), metric="delivery_rate",
            value=round(r["rate"], 4), expected="> 0" if r["mode"] == "static" else f"> {fmt_pct(r['p_low'])}",
            volume=int(sent - r["delivered"]),
            message=(f"« {bc} » : Delivery% {fmt_pct(r['rate'])} (Delivered {fmt_int(r['delivered'])} / "
                     f"Sent {fmt_int(sent)}, {r['first']} → {r['last']}). {_position(r, pct.LOW)}."),
            details={"broadcast_ids": r["broadcast_ids"], "dates": r["dates"],
                     "acknowledged": int(r["acknowledged"]), **pct.info(r)},
        )


@rule("PM-DLV-02", "Chute de la livraison", "push", "major", min_sent=10000, min_abs_gap=0.10)
def delivery_drop(ctx: RuleContext, p: dict):
    pc = pct.settings(ctx.det)
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
        not_fed = (g["delivered"] == 0) & (g["sent"] > 0)  # Delivered non remonté ce jour-là (FEED-03)
        res = pct.history_outliers(rate, pct.LOW, pc, min_abs_gap=p["min_abs_gap"], exclude=not_fed)
        for run in pct.runs(res, current_dates):
            # un épisode = jours hors norme consécutifs ; un seul jour = minor, 2 jours et + = sévérité de la règle
            first, last, days = run.index[0], run.index[-1], len(run)
            missing = int((g.loc[run.index, "sent"] * (run["p50"] - run["value"])).sum())
            worst = run.loc[run["value"].idxmin()]
            base = p["severity"] if days > 1 else "minor"
            when = f"le {first}" if days == 1 else f"du {first} au {last} ({days} jours)"
            yield Anomaly(
                entity_type="category", entity_key=cat, date=first, category=None if cat.startswith("Toutes") else cat,
                severity=ctx.scaled(base, missing), metric="delivery_rate", value=round(worst["value"], 4),
                expected=f"≥ {fmt_pct(worst['p_low'])} (P5 historique)", volume=missing,
                message=(f"{cat} {when} : Delivery% {fmt_pct(worst['value'])} au plus bas, sous le P5 historique "
                         f"{fmt_pct(worst['p_low'])} (médiane {fmt_pct(worst['p50'])}), soit ~{fmt_int(missing)} "
                         f"Delivered en moins."),
                details={"days": run.index.tolist(), "last_date": last, **pct.info(worst)},
            )


@rule("PM-DLV-03", "Accusés de réception faibles", "push", "minor", min_sent=1000, max_ack_rate=0.90, min_abs_gap=0.05)
def low_ack(ctx: RuleContext, p: dict):
    df = ctx.business(ctx.push)
    df = df[df["sent"] >= p["min_sent"]]
    if df.empty:
        return
    t = _bc_table(df)
    t["rate"] = t["acknowledged"] / t["sent"]
    res = _detect(ctx, p, t, "rate", pct.LOW, t["rate"] < p["max_ack_rate"], p["min_abs_gap"])
    for bc, r in res[res["flag"]].iterrows():
        sent, ack = int(r["sent"]), int(r["acknowledged"])
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=r["first"], category=r["category"],
            severity=ctx.scaled(p["severity"], sent - ack), metric="ack_rate", value=round(r["rate"], 4),
            expected=(f"≥ {fmt_pct(p['max_ack_rate'])}" if r["mode"] == "static"
                      else f"≥ {fmt_pct(r['p_low'])} (P5 des pairs)"),
            volume=sent - ack,
            message=(f"« {bc} » : Acknowledged % {fmt_pct(r['rate'])} (Acknowledged {fmt_int(ack)} / Sent "
                     f"{fmt_int(sent)}) sur {len(r['broadcast_ids'])} broadcast(s), {r['first']} → {r['last']}. "
                     f"{_position(r, pct.LOW)}."),
            details={"broadcast_ids": r["broadcast_ids"], "dates": r["dates"], **pct.info(r)},
        )


# --------------------------------------------------------------------------- performance

def _mature(ctx: RuleContext) -> pd.DataFrame:
    df = ctx.conversion_scope(ctx.push)
    return df[(df["age_days"] >= ctx.det.get("maturity_days", 3)) & (df["sent"] > 0)]


@rule("PM-PRF-01", "Conversion anormalement basse", "push", "minor", min_sent=1000, min_abs_gap=0.002)
def no_conversion(ctx: RuleContext, p: dict):
    df = _mature(ctx)
    if df.empty:
        return
    t = _bc_table(df)
    t = t[t["sent"] >= p["min_sent"]].copy()
    if t.empty:
        return
    t["rate"] = t["conversions"] / t["sent"]
    res = _detect(ctx, p, t, "rate", pct.LOW, t["conversions"] == 0, p["min_abs_gap"])
    for bc, r in res[res["flag"]].iterrows():
        sent = int(r["sent"])
        lost = sent if r["mode"] == "static" else int(max(r["p50"] - r["rate"], 0) * sent)
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=r["first"], category=r["category"],
            metric="conversion_rate", value=round(r["rate"], 5),
            expected="> 0" if r["mode"] == "static" else f"> {fmt_pct(r['p_low'])}", volume=sent,
            message=(f"« {bc} » : Conv {fmt_int(r['conversions'])} pour Sent {fmt_int(sent)} "
                     f"(Conv% {fmt_pct(r['rate'])}, {r['first']} → {r['last']}), ~{fmt_int(lost)} Conv "
                     f"sous la médiane des pairs. {_position(r, pct.LOW)}."),
            details={"campaign": r["campaign"], "broadcasts": len(r["broadcast_ids"]), **pct.info(r)},
        )


@rule("PM-PRF-02", "Pire que le groupe de contrôle (uplift négatif)", "push", "minor", min_cg=1000, min_cg_conversions=30, p_value=0.05,
      major_lost=500)
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
            severity=p["severity"] if lost >= p["major_lost"] else "minor",  # notifié seulement si l'enjeu est réel
            metric="uplift", value=round(res.uplift, 5), expected="≥ 0", volume=int(tg),
            message=(f"« {bc} » n'apporte aucune conversion incrémentale : les clients ciblés convertissent moins "
                     f"({fmt_pct(res.tg_rate)}) que le groupe de contrôle ({fmt_pct(res.cg_rate)}, p = "
                     f"{res.p_value:.3f}), ~{fmt_int(lost)} conversions en moins ({first} → {last})."),
            details={"tg": int(tg), "tg_conv": int(tg_conv), "cg": int(cg), "cg_conv": int(cg_conv),
                     "ci95": [round(res.ci_low, 5), round(res.ci_high, 5)],
                     "impact": f"~{fmt_int(lost)} conversions perdues vs groupe de contrôle",
                     "action": "Revoir le ciblage ou l'offre, ou suspendre ce BC."},
        )


@rule("PM-PRF-03", "Échecs de fulfillment anormalement élevés", "push", "major",
      min_failures=10, max_failure_rate=0.20, min_abs_gap=0.05)
def push_fulfillment_failure(ctx: RuleContext, p: dict):
    if ctx.push.empty:
        return
    t = _bc_table(ctx.push)
    attempts = t["success"] + t["failures"]
    t["rate"] = t["failures"] / attempts.where(attempts > 0)
    t = t[attempts >= p["min_failures"]].copy()
    if t.empty:
        return
    static = (t["failures"] >= p["min_failures"]) & (t["rate"] >= p["max_failure_rate"])
    res = _detect(ctx, p, t, "rate", pct.HIGH, static, p["min_abs_gap"])
    # le plancher de volume reste absolu : pas d'alerte sur quelques échecs isolés
    res = res[res["flag"] & (res["failures"] >= p["min_failures"])]
    for bc, r in res.iterrows():
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=r["first"], category=r["category"],
            severity=ctx.scaled(p["severity"], r["failures"]), metric="fulfillment_failure_rate",
            value=round(r["rate"], 4),
            expected=(f"< {fmt_pct(p['max_failure_rate'])}" if r["mode"] == "static"
                      else f"< {fmt_pct(r['p_high'])} (P95 des pairs)"),
            volume=int(r["failures"]),
            message=(f"« {bc} » ({r['first']} → {r['last']}) : l'offre n'est pas livrée à {fmt_int(r['failures'])} "
                     f"clients ayant converti ({fmt_pct(r['rate'])} d'échecs de fulfillment). {_position(r, pct.HIGH)}."),
            details={"success": int(r["success"]), "broadcast_ids": r["broadcast_ids"], **pct.info(r),
                     "impact": f"{fmt_int(r['failures'])} clients sans leur offre",
                     "action": "Vérifier le provisioning de l'offre côté plateforme/produit."},
        )


# --------------------------------------------------------------------------- qualité de données

@rule("PM-DQ-01", "Données : Sent supérieur à Generated", "push", "minor")
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


@rule("PM-DQ-02", "Données : conversions supérieures à Sent", "push", "minor")
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


@rule("PM-DQ-03", "Données : succès supérieurs aux conversions", "push", "minor")
def fulfillment_gt_conversions(ctx: RuleContext, p: dict):
    df = ctx.push[(ctx.push["conversions"] > 0) & (ctx.push["fulfillment_success"] > ctx.push["conversions"])]
    for bc, g, first, last, days in _episodes_by_bc(df):
        yield Anomaly(
            entity_type="bc_name", entity_key=bc, date=first, category=_first(g, "category"),
            metric="fulfillment_minus_conversions", value=int((g["fulfillment_success"] - g["conversions"]).sum()),
            expected="Fulfillment ≤ Conversions", volume=int(g["fulfillment_success"].sum()),
            message=f"« {bc} » : Fulfillment Success > Conv sur {len(g)} broadcast(s) ({first} → {last}).",
        )


@rule("PM-DQ-04", "Données : groupe de contrôle absent", "push", "minor", min_sent=1000)
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


@rule("PM-DQ-05", "Données : colonne vide", "push", "info")
def empty_columns(ctx: RuleContext, p: dict):
    candidates = ["total_con_val", "conversion_value", "unique_conversion_value", "acknowledged", "delivered"]
    for col in candidates:
        if col in ctx.push and (ctx.push[col].isna() | (ctx.push[col] == 0)).all():
            yield Anomaly(
                entity_type="column", entity_key=f"Data_Push.{col}", date=_period_start(ctx),
                metric="non_empty_rows", value=0, expected="> 0",
                message=f"Data_Push : colonne {SOURCE_NAME.get(col, col)} vide sur toutes les lignes.",
            )


@rule("PM-DQ-06", "Données : jour manquant", "push", "major")
def missing_days(ctx: RuleContext, p: dict):
    start = pd.Timestamp(_period_start(ctx))
    expected = {d.strftime("%Y-%m-%d") for d in pd.date_range(start, pd.Timestamp(ctx.snapshot_date))}
    for label, df in (("Data_Push", ctx.push), ("Data_IM", ctx.im)):
        for day in sorted(expected - set(df["date"])):
            yield Anomaly(
                entity_type="dataset", entity_key=label, date=day, metric="rows", value=0, expected="> 0",
                message=f"Aucune ligne {label} pour le {day} (fichier du {ctx.snapshot_date}).",
            )

