"""Règles sur le flux NEON-dx lui-même : fichiers reçus, format, remplissage, troncature, maturation.

Le Daily Dashboard est exporté chaque jour du back-office NEON-dx de Flytxt et ne couvre que le mois en cours.
Ces règles ne jugent pas les campagnes mais la donnée : une donnée manquante, un format qui change ou une
métrique qui cesse d'arriver doivent être signalés (et remontés à Flytxt) avant de fausser les autres règles.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from ..analytics.maturity import maturity_curves
from ..ingest.schema import IM_SHEET, PUSH_SHEET
from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule

SHEET_LABEL = {"push": "Data_Push", "im": "Data_IM"}
# Métrique → indicateur de volume : la métrique doit être renseignée les jours où le volume existe.
PUSH_FED = {"acknowledged": "Acknowledged", "delivered": "Delivered", "cg_size": "Overall Ctrl Grp"}
PUSH_FED_MATURE = {"conversions": "Conversions"}   # jugée seulement sur les jours d'au moins 1 jour
# Indicateurs (0 = « non ») et taux recopiés de la source : leur part non nulle n'est pas un remplissage.
NOT_FILL_METRICS = {"is_seeding", "ack_rate", "conv_rate", "fulfillment_rate", "cg_conv_rate", "net_conv_rate"}


def _period_start(ctx: RuleContext) -> str:
    return min(ctx.push["date"].min(), ctx.im["date"].min() if not ctx.im.empty else "9999")


def _runs(days: list[str]) -> list[list[str]]:
    """Jours ISO triés → épisodes de jours consécutifs."""
    out: list[list[str]] = []
    for d in sorted(days):
        if out and (date.fromisoformat(d) - date.fromisoformat(out[-1][-1])).days == 1:
            out[-1].append(d)
        else:
            out.append([d])
    return out


def _span(days: list[str]) -> str:
    return f"le {days[0]}" if len(days) == 1 else f"du {days[0]} au {days[-1]} ({len(days)} jours)"


# --------------------------------------------------------------------------- fichiers reçus

@rule("FEED-01", "Fichier NEON-dx manquant", "feed", "minor", month_end_days=3)
def missing_files(ctx: RuleContext, p: dict):
    """Jours sans fichier depuis le début du mois (et fin du mois précédent).

    Un fichier manquant en fin de mois est plus grave : le mois suivant ne reporte plus ces envois, dont les
    conversions ne seront jamais complétées (voir FEED-04).
    """
    if ctx.snapshots is None or len(ctx.snapshots) < 2:
        return
    received = set(ctx.snapshots["snapshot_date"])
    first = date.fromisoformat(ctx.snapshots["snapshot_date"].min())
    month_start = ctx.snapshot_date.replace(day=1)
    start = max(first, month_start - timedelta(days=p["month_end_days"]))
    calendar = [first + timedelta(days=k) for k in range((ctx.snapshot_date - first).days)]
    missing = [d.isoformat() for d in calendar if d.isoformat() not in received]
    for days in _runs(missing):
        if days[-1] < start.isoformat():
            continue  # épisode ancien : déjà signalé par un fichier précédent
        month_end = any((date.fromisoformat(d) + timedelta(days=1)).day == 1 for d in days)
        sev = "major" if month_end or len(days) >= 3 else p["severity"]
        yield Anomaly(
            entity_type="dataset", entity_key="fichiers NEON-dx", date=days[0], severity=sev,
            metric="missing_files", value=len(days), expected="un fichier par jour", volume=len(days),
            message=(f"Aucun Daily Dashboard reçu {_span(days)}."
                     + (" Fin de mois : les derniers envois du mois ne seront plus jamais mis à jour." if month_end else "")),
            details={"days": days, "month_end": month_end},
        )


# --------------------------------------------------------------------------- format

@rule("FEED-02", "Changement de format NEON-dx", "feed", "major")
def format_change(ctx: RuleContext, p: dict):
    """Colonnes ajoutées ou retirées, nouvelles valeurs de dimension, colonne qui se remplit ou se vide."""
    snaps = ctx.snapshots
    # a) Colonnes brutes du fichier vs fichier précédent
    if snaps is not None and len(snaps) >= 2 and "columns" in snaps:
        cur, prev = snaps.iloc[-1].get("columns"), snaps.iloc[-2].get("columns")
        if cur and prev:
            cur, prev = json.loads(cur), json.loads(prev)
            for sheet in (PUSH_SHEET, IM_SHEET):
                added = [c for c in cur.get(sheet, []) if c not in prev.get(sheet, [])]
                removed = [c for c in prev.get(sheet, []) if c not in cur.get(sheet, [])]
                if added or removed:
                    txt = "; ".join(x for x in (f"ajoutée(s) : {', '.join(added)}" if added else "",
                                                 f"retirée(s) : {', '.join(removed)}" if removed else "") if x)
                    yield Anomaly(
                        entity_type="column", entity_key=f"{sheet} · colonnes", date=ctx.snapshot_date.isoformat(),
                        metric="columns_changed", value=len(added) + len(removed), expected="colonnes inchangées",
                        message=f"{sheet} : colonnes {txt} depuis le fichier du {ctx.prev_snapshot_date}.",
                        details={"added": added, "removed": removed},
                    )
    # b) Valeurs de dimension jamais vues (nouveau statut, catégorie, touchpoint, programme)
    for col, df, label in (("status", ctx.push, "Status"), ("category", ctx.push, "Campaign Category"),
                           ("touchpoint", ctx.im, "Touchpoint"), ("program", ctx.im, "Program")):
        known = ctx.known_values.get(col)
        if not known or col not in df:
            continue
        for value in sorted(set(df[col].dropna()) - known):
            rows = df[df[col] == value]
            vol = int(rows["sent"].sum() if "sent" in rows else rows["impressions"].sum())
            yield Anomaly(
                entity_type="column", entity_key=f"{label} = {value}", date=rows["date"].min(), severity="minor",
                metric="new_value", value=len(rows), expected="valeur connue", volume=vol,
                message=(f"Nouvelle valeur de {label} : « {value} » ({len(rows)} ligne(s), volume {fmt_int(vol)}). "
                         "À documenter : les règles et l'interface la classent pour l'instant « autre »."),
                details={"column": col, "value": value},
            )
    # c) Colonne qui commence à être alimentée, ou qui ne l'est plus
    for sheet, col, cur, prev in _fill_pairs(ctx):
        label = f"{SHEET_LABEL[sheet]}.{col}"
        if prev == 0 and cur > 0:
            yield Anomaly(
                entity_type="column", entity_key=label, date=ctx.snapshot_date.isoformat(), severity="info",
                metric="fill_rate", value=round(cur, 4), expected="vide auparavant",
                message=f"{label} est désormais alimentée ({fmt_pct(cur)} des lignes), vide dans le fichier précédent.",
                details={"previous": prev},
            )
        elif prev >= 0.05 and cur == 0:
            yield Anomaly(
                entity_type="column", entity_key=label, date=ctx.snapshot_date.isoformat(),
                metric="fill_rate", value=0, expected=f"≈ {fmt_pct(prev)} (fichier précédent)",
                message=f"{label} n'est plus alimentée : vide dans ce fichier, renseignée à {fmt_pct(prev)} dans le précédent.",
                details={"previous": prev},
            )


def _fill_pairs(ctx: RuleContext):
    """(feuille, colonne, remplissage courant, remplissage du fichier précédent)."""
    f = ctx.fill
    if f is None or f.empty or ctx.snapshots is None or len(ctx.snapshots) < 2:
        return
    cur_id, prev_id = ctx.snapshots.iloc[-1]["id"], ctx.snapshots.iloc[-2]["id"]
    cur = f[f["snapshot_id"] == cur_id].set_index(["sheet", "column"])["fill"]
    prev = f[f["snapshot_id"] == prev_id].set_index(["sheet", "column"])["fill"]
    for key in cur.index.intersection(prev.index):
        if pd.notna(cur[key]) and pd.notna(prev[key]):
            yield key[0], key[1], float(cur[key]), float(prev[key])


# --------------------------------------------------------------------------- remplissage

@rule("FEED-03", "Métrique non alimentée", "feed", "major", min_volume=1000, drop_ratio=0.5, min_fill=0.05)
def metric_not_fed(ctx: RuleContext, p: dict):
    """Jours où une métrique est vide alors que son volume existe et qu'elle est renseignée les autres jours.

    Exemple réel : Data_IM, Fulfillment Success / Failures à 0 du 01 au 18/08 malgré ~800 000 impressions par
    jour. Détecté dès le premier fichier, sans attendre d'historique. S'y ajoute la baisse de remplissage d'une
    colonne par rapport aux fichiers précédents.
    """
    # a) Data_IM : fulfillment par touchpoint
    if not ctx.im.empty:
        d = ctx.im.groupby(["touchpoint", "date"])[["impressions", "fulfillment_success", "fulfillment_failures"]].sum()
        d["attempts"] = d["fulfillment_success"] + d["fulfillment_failures"]
        for tp, g in d.groupby(level=0):
            g = g.droplevel(0)
            if not (g["attempts"] > 0).any():
                continue  # jamais alimenté sur ce touchpoint : IM-DQ-02
            # Quasi nul (quelques unités pour des centaines de milliers d'impressions) = non alimenté aussi.
            typical = g.loc[g["attempts"] > 0, "attempts"].median()
            floor = max(p.get("residual_floor", 10), p.get("residual_ratio", 0.01) * typical)
            dead = g[(g["impressions"] >= p["min_volume"]) & (g["attempts"] < floor)].index.tolist()
            for days in _runs(dead):
                imp = int(g.loc[days, "impressions"].sum())
                yield Anomaly(
                    entity_type="touchpoint", entity_key=f"{tp} · fulfillment", date=days[0],
                    severity=ctx.scaled(p["severity"], imp), metric="fulfillment_attempts", value=0, expected="> 0",
                    volume=imp, category=str(tp),
                    message=(f"Data_IM {tp} : Fulfillment Success et Failures à 0 (ou quasi) {_span(days)} malgré "
                             f"{fmt_int(imp)} impressions, alors qu'ils sont renseignés les autres jours du fichier. "
                             "Donnée non alimentée par NEON-dx (pas zéro achat)."),
                    details={"days": days, "touchpoint": tp, "attempts": int(g.loc[days, "attempts"].sum())},
                )
    # b) Data_Push : métriques journalières vides malgré du volume
    daily = ctx.push.groupby("date")[["sent", *PUSH_FED, *PUSH_FED_MATURE]].sum()
    young = {d for d, age in ctx.push.groupby("date")["age_days"].max().items() if age < 1}
    for col, label in {**PUSH_FED, **PUSH_FED_MATURE}.items():
        if not (daily[col] > 0).any():
            continue  # colonne jamais remplie : FEED-02 / PM-DQ-05
        mask = (daily["sent"] >= p["min_volume"]) & (daily[col] == 0)
        if col in PUSH_FED_MATURE:
            mask &= ~daily.index.isin(young)
        for days in _runs(daily[mask].index.tolist()):
            sent = int(daily.loc[days, "sent"].sum())
            yield Anomaly(
                entity_type="column", entity_key=f"Data_Push.{col}", date=days[0],
                severity=ctx.scaled(p["severity"], sent), metric="daily_total", value=0, expected="> 0",
                volume=sent,
                message=(f"Data_Push : {label} à 0 {_span(days)} pour {fmt_int(sent)} Sent, alors que la colonne est "
                         "renseignée les autres jours. Donnée non alimentée par NEON-dx."),
                details={"days": days, "column": col},
            )
    # c) Remplissage d'une colonne en forte baisse vs les fichiers précédents (le passage à 0 est FEED-02)
    f = ctx.fill
    covered = (date.fromisoformat(ctx.push["date"].max()) - date.fromisoformat(ctx.push["date"].min())).days + 1
    # Un fichier de début de mois couvre trop peu de jours (et des envois trop jeunes) pour être comparable.
    if f is not None and not f.empty and ctx.snapshots is not None and len(ctx.snapshots) >= 4 and covered >= p.get("min_days_covered", 7):
        f = f[~f["column"].isin(NOT_FILL_METRICS)]
        ids = list(ctx.snapshots["id"])
        cur, past = f[f["snapshot_id"] == ids[-1]], f[f["snapshot_id"].isin(ids[-8:-1])]
        ref = past.groupby(["sheet", "column"])["fill"].median()
        for r in cur.itertuples():
            m = ref.get((r.sheet, r.column))
            if m is None or pd.isna(m) or pd.isna(r.fill) or m < p["min_fill"] or r.fill == 0:
                continue
            if r.fill < m * p["drop_ratio"]:
                label = f"{SHEET_LABEL[r.sheet]}.{r.column}"
                yield Anomaly(
                    entity_type="column", entity_key=label, date=ctx.snapshot_date.isoformat(), severity="minor",
                    metric="fill_rate", value=round(float(r.fill), 4), expected=f"≈ {fmt_pct(m)} (médiane des fichiers précédents)",
                    message=f"{label} : renseignée sur {fmt_pct(r.fill)} des lignes contre {fmt_pct(m)} habituellement.",
                    details={"median_previous": round(float(m), 4)},
                )


# --------------------------------------------------------------------------- troncature et maturation

def _curves(ctx: RuleContext) -> dict[str, list[float]]:
    if ctx.versions is None or ctx.versions.empty:
        return {}
    return maturity_curves(ctx.versions, ["conversions"], int(ctx.det.get("maturity_reference_age", 10)))


def _completion(curve: list[float], age: int) -> float:
    if not curve or age >= len(curve) - 1:
        return 1.0
    return max(curve[max(0, age)], 0.01)


@rule("FEED-04", "Envois de fin de mois tronqués", "feed", "major")
def month_end_truncation(ctx: RuleContext, p: dict):
    """Au premier fichier d'un mois : envois du mois précédent jamais observés matures.

    Le fichier ne couvre que le mois en cours ; les envois des derniers jours du mois précédent ne seront plus
    jamais mis à jour. Prévention : demander à Flytxt d'inclure les 7 derniers jours du mois précédent.
    """
    if ctx.prev_snapshot_date is None or ctx.prev_snapshot_date.month == ctx.snapshot_date.month:
        return
    maturity = int(ctx.det.get("maturity_days", 3))
    prev_month = ctx.prev_snapshot_date.strftime("%Y-%m")
    h = ctx.hist_push
    # Vus pour la dernière fois dans le dernier fichier du mois : les disparitions antérieures relèvent de SNP-02.
    h = h[h["date"].str.startswith(prev_month) & (h["age_days"] < maturity) & (h["sent"] > 0)
          & (h["snapshot_date"] == ctx.prev_snapshot_date.isoformat())]
    if h.empty:
        return
    curve = _curves(ctx).get("conversions", [])
    est = (h["conversions"] / h["age_days"].map(lambda a: _completion(curve, int(a)))).sum()
    missing = int(round(est - h["conversions"].sum()))
    days = sorted(h["date"].unique().tolist())
    yield Anomaly(
        entity_type="dataset", entity_key=f"fin de mois {prev_month}", date=days[0],
        severity=ctx.scaled(p["severity"], missing), metric="truncated_broadcasts", value=len(h),
        expected=f"envois observés jusqu'à J+{maturity}", volume=missing,
        message=(f"{len(h)} envois de fin {prev_month} ({days[0]} → {days[-1]}) sortis des fichiers avant J+{maturity} : "
                 f"{fmt_int(h['conversions'].sum())} conversions observées, ≈ {fmt_int(est)} attendues à maturité "
                 f"(≈ {fmt_int(missing)} jamais remontées). Prévention : demander à Flytxt d'inclure les 7 derniers "
                 "jours du mois précédent dans le Daily Dashboard."),
        details={"broadcast_ids": h["broadcast_id"].astype(int).tolist(), "days": days, "estimated_missing": missing},
    )


@rule("FEED-06", "Maturation des conversions anormalement lente", "feed", "minor",
      min_conversions=1000, min_expected_growth=0.15, max_ratio=0.4)
def slow_maturation(ctx: RuleContext, p: dict):
    """Les conversions des envois récents progressent beaucoup moins que la courbe de maturité ne le prévoit
    entre le fichier précédent et celui-ci : retard probable de l'attribution côté NEON-dx."""
    if ctx.prev_push is None or ctx.prev_push.empty:
        return
    curve = _curves(ctx).get("conversions", [])
    if len(curve) < 3:
        return
    m = ctx.prev_push[["broadcast_id", "age_days", "conversions"]].merge(
        ctx.push[["broadcast_id", "age_days", "conversions"]], on="broadcast_id", suffixes=("_prev", ""))
    m = m[(m["age_days_prev"] < len(curve) - 1) & (m["conversions_prev"] > 0)]
    base = m["conversions_prev"].sum()
    if base < p["min_conversions"]:
        return
    expected = (m["conversions_prev"] * m["age_days"].map(lambda a: _completion(curve, int(a)))
                / m["age_days_prev"].map(lambda a: _completion(curve, int(a)))).sum()
    exp_growth, obs_growth = expected / base - 1, m["conversions"].sum() / base - 1
    if exp_growth >= p["min_expected_growth"] and obs_growth < p["max_ratio"] * exp_growth:
        missing = int(expected - m["conversions"].sum())
        yield Anomaly(
            entity_type="global", entity_key="attribution des conversions", date=ctx.snapshot_date.isoformat(),
            severity=ctx.scaled(p["severity"], missing), metric="conversion_growth", value=round(obs_growth, 4),
            expected=f"≈ +{fmt_pct(exp_growth)} (courbe de maturité)", volume=missing,
            message=(f"Les conversions des {len(m)} envois récents ont progressé de {fmt_pct(obs_growth)} depuis le "
                     f"fichier du {ctx.prev_snapshot_date}, contre ≈ +{fmt_pct(exp_growth)} attendus "
                     f"(≈ {fmt_int(missing)} conversions de retard). Attribution probablement en retard côté NEON-dx."),
            details={"broadcasts": int(len(m)), "expected_growth": round(exp_growth, 4), "observed_growth": round(obs_growth, 4)},
        )
