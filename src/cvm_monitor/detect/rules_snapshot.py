"""Règles de comparaison entre le snapshot courant et le précédent."""

from __future__ import annotations

from ..ingest.schema import PUSH_COLUMNS
from .base import Anomaly, RuleContext, fmt_int, rule

SOURCE_NAME = {v: k for k, v in PUSH_COLUMNS.items()}

FROZEN = ["generated", "sent", "delivered", "cg_size"]
IN_PROGRESS = {"Delivering", "Paused", "Blackout Pause"}
IM_KEY = ["date", "touchpoint", "rule_id", "offer_id"]
IM_VALUES = ["impressions", "fulfillment_success", "fulfillment_failures"]


@rule("SNP-01", "Broadcast révisé", "snapshot", "major", needs_previous=True)
def frozen_metrics_changed(ctx: RuleContext, p: dict):
    prev = ctx.prev_push[~ctx.prev_push["status"].isin(IN_PROGRESS)]
    m = prev.merge(ctx.push, on="broadcast_id", suffixes=("_prev", ""))
    for r in m.to_dict("records"):
        changes = {c: (r[f"{c}_prev"], r[c]) for c in FROZEN if r[f"{c}_prev"] != r[c]}
        if r["conversions"] < r["conversions_prev"]:
            changes["conversions"] = (r["conversions_prev"], r["conversions"])
        if not changes:
            continue
        txt = ", ".join(f"{SOURCE_NAME.get(c, c)} {fmt_int(a)} → {fmt_int(b)}" for c, (a, b) in changes.items())
        yield Anomaly(
            entity_type="broadcast", entity_key=str(r["broadcast_id"]), date=r["date"], category=r["category"],
            metric="revised_fields", value=len(changes), expected="valeurs figées",
            volume=int(max(abs(b - a) for a, b in changes.values())),
            message=f"« {r['bc_name']} » ({r['date']}) révisé depuis le fichier du {ctx.prev_snapshot_date} : {txt}.",
            details={c: [int(a), int(b)] for c, (a, b) in changes.items()},
        )


@rule("SNP-02", "Broadcast disparu", "snapshot", "major")
def broadcast_disappeared(ctx: RuleContext, p: dict):
    """Broadcasts du mois couvert par le fichier, vus dans un fichier antérieur, absents du fichier courant.

    Comparé à tout l'historique (et non au seul fichier précédent) : l'alerte reste ouverte tant que les
    broadcasts manquent et se résout s'ils reviennent. Le changement de mois n'est pas une disparition
    (le fichier ne couvre que le mois en cours). Un épisode par fichier de dernière apparition.
    """
    start, end = ctx.push["date"].min(), ctx.push["date"].max()
    h = ctx.hist_push
    gone = h[(h["date"] >= start) & (h["date"] <= end) & ~h["broadcast_id"].isin(ctx.push["broadcast_id"])]
    for last_seen, g in gone.groupby("snapshot_date"):
        sent = int(g["sent"].sum())
        first, last = g["date"].min(), g["date"].max()
        yield Anomaly(
            entity_type="dataset", entity_key=f"broadcasts absents après le fichier du {last_seen}", date=first,
            category=g["category"].mode().iloc[0] if g["category"].notna().any() else None,
            severity=ctx.scaled(p["severity"], sent), metric="missing_broadcasts", value=len(g), expected="présents",
            volume=sent,
            message=(f"{len(g)} broadcast(s) envoyés du {first} au {last} (Sent {fmt_int(sent)}), présents dans le "
                     f"fichier du {last_seen}, absents du fichier du {ctx.snapshot_date}. Leurs dernières valeurs "
                     "connues sont conservées. À signaler à Flytxt."),
            details={"broadcast_ids": g["broadcast_id"].astype(int).tolist(), "last_seen": last_seen,
                     "bc_names": sorted(g["bc_name"].dropna().unique().tolist())[:30]},
        )


@rule("SNP-03", "Data_IM révisée", "snapshot", "minor", needs_previous=True)
def im_revised(ctx: RuleContext, p: dict):
    if ctx.prev_im is None or ctx.prev_im.empty:
        return
    prev = ctx.prev_im[ctx.prev_im["date"] < ctx.prev_snapshot_date.isoformat()]  # jours clos au snapshot précédent
    m = prev.merge(ctx.im, on=IM_KEY, suffixes=("_prev", ""))
    diff = m[[f"{c}_prev" for c in IM_VALUES]].to_numpy() != m[IM_VALUES].to_numpy()
    changed = m[diff.any(axis=1)]
    for day, g in changed.groupby("date"):
        delta = int(sum((g[c] - g[f"{c}_prev"]).abs().sum() for c in IM_VALUES))
        yield Anomaly(
            entity_type="dataset", entity_key="IM", date=day, metric="revised_rows", value=len(g),
            expected="0", volume=delta,
            message=f"Data_IM du {day} : {len(g)} ligne(s) modifiée(s) depuis le fichier du {ctx.prev_snapshot_date} (écart {fmt_int(delta)}).",
        )
