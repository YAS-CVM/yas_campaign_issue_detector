"""Règles CVM : les 14 alertes lisibles (9 BC Push, 5 offres Inbound), orientées « ce qu'il faut regarder ».

Sévérités : Critique = critical, Élevée = major, À surveiller = minor, Info = info.
Unité d'analyse Push = le BC (BC Name) ; les BC techniques (« Dummy BC ») sont exclus.
"""

from __future__ import annotations

import pandas as pd

from .base import Anomaly, RuleContext, fmt_int, fmt_pct, rule

FAILED_STATUSES = ["Aborted", "Delivery Stalled", "Blackout Expired"]


# --------------------------------------------------------------------------- helpers Push

def _sends(ctx: RuleContext, scoped: bool = True) -> pd.DataFrame:
    """Envois (un par ligne) triés chronologiquement ; `age` = jours depuis l'envoi."""
    df = ctx.conversion_scope(ctx.hist_push) if scoped else ctx.business(ctx.hist_push)
    df = df.copy()
    ts = pd.to_datetime(df["scheduled_at"], errors="coerce") if "scheduled_at" in df else pd.Series(pd.NaT, index=df.index)
    df["_ts"] = ts.fillna(pd.to_datetime(df["date"]))
    df["age"] = (pd.Timestamp(ctx.snapshot_date) - pd.to_datetime(df["date"])).dt.days
    return df.sort_values(["_ts", "broadcast_id"])


def _mature(ctx: RuleContext, df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["sent"] > 0) & (df["age"] >= ctx.det.get("maturity_days", 3))]


def _recent(g: pd.DataFrame, p: dict) -> bool:
    """Le BC a envoyé récemment (sinon l'arrêt relève de « N'envoie plus », pas d'une dégradation)."""
    return int(g["age"].iloc[-1]) <= p["recent_days"]


def _trailing(mask: pd.Series) -> int:
    n = 0
    for v in reversed(mask.tolist()):
        if not v:
            break
        n += 1
    return n


def _bc_anomaly(bc: str, g: pd.DataFrame, date: str, severity: str, metric: str, value, expected: str,
                message: str, impact: str, action: str, **details) -> Anomaly:
    return Anomaly(
        entity_type="bc_name", entity_key=str(bc), date=date, category=g["category"].iloc[-1], severity=severity,
        metric=metric, value=value, expected=expected, volume=int(g["sent"].sum()), message=message,
        details={"last_date": g["date"].iloc[-1], "campaign": g["campaign_name"].iloc[-1], "impact": impact,
                 "action": action, **details})


# --------------------------------------------------------------------------- Push

@rule("CVM-PUSH-01", "Ne convertit plus", "push", "critical",
      last_n=3, min_conversions=10, min_sent=1000, recent_days=14)
def push_no_longer_converts(ctx: RuleContext, p: dict):
    """La BC a déjà converti (au moins `min_conversions`), mais ses `last_n` derniers envois n'ont enregistré aucune conversion."""
    for bc, g in _mature(ctx, _sends(ctx)).groupby("bc_name", sort=False):
        run = _trailing(g["conversions"].fillna(0) == 0)
        if run < p["last_n"] or not _recent(g, p):
            continue
        tail, before = g.tail(run), g.iloc[:-run]
        if before["conversions"].sum() < p["min_conversions"] or tail["sent"].sum() < p["min_sent"]:
            continue
        yield _bc_anomaly(
            bc, g, tail["date"].iloc[0], p["severity"], "conversions", 0, f"≥ 1 conversion sur {run} envois",
            f"« {bc} » ne convertit plus : 0 conversion sur ses {run} derniers envois ({fmt_int(tail['sent'].sum())} messages), "
            f"alors qu'elle en avait {fmt_int(before['conversions'].sum())} avant.",
            f"{fmt_int(tail['sent'].sum())} messages sans conversion",
            "Vérifier le message, la cible, l'offre et le suivi de conversion (attribution) du BC.")


@rule("CVM-PUSH-02", "Ciblage à zéro", "push", "major", last_n=3, recent_days=14)
def push_zero_targeting(ctx: RuleContext, p: dict):
    """Les `last_n` derniers envois de la BC n'ont ciblé aucun client (Sent = 0)."""
    df = _sends(ctx, scoped=False)
    df = df[(df["age"] >= 1) & ~df["status"].isin(FAILED_STATUSES)]
    if "scheduled_at" in df:
        df = df[~ctx.in_blackout(df["scheduled_at"])]
    for bc, g in df.groupby("bc_name", sort=False):
        run = _trailing(g["sent"].fillna(0) == 0)
        if run < p["last_n"] or not _recent(g, p):
            continue
        tail = g.tail(run)
        yield _bc_anomaly(
            bc, g, tail["date"].iloc[0], p["severity"], "sent", 0, "Sent > 0",
            f"« {bc} » ne cible plus personne : Sent = 0 sur ses {run} derniers envois (depuis le {tail['date'].iloc[0]}).",
            f"{fmt_int(tail['generated'].sum())} clients générés, aucun envoyé",
            "Vérifier la requête de ciblage / le segment du BC et l'éligibilité des clients.")


@rule("CVM-PUSH-03", "Envoi en échec", "push", "major", days=3, min_generated=0)
def push_failed_send(ctx: RuleContext, p: dict):
    """Le dernier envoi de la BC, sur les `days` derniers jours, a un statut d'échec (Aborted, Delivery Stalled, Blackout Expired)."""
    df = _sends(ctx, scoped=False)
    for bc, g in df.groupby("bc_name", sort=False):
        last = g.iloc[-1]
        if last["age"] > p["days"] or last["status"] not in FAILED_STATUSES or (last["generated"] or 0) < p["min_generated"]:
            continue
        yield _bc_anomaly(
            bc, g, last["date"], p["severity"], "status", None, "Completed",
            f"Le dernier envoi de « {bc} » ({last['date']}) est en échec : Status {last['status']}, "
            f"Generated {fmt_int(last['generated'])}, Sent {fmt_int(last['sent'])}.",
            f"{fmt_int(last['generated'] - last['sent'])} clients non servis",
            "Vérifier l'exécution dans NEON-dx (statut, fenêtre de blackout, file d'envoi) et relancer si besoin.",
            status=last["status"], broadcast_id=int(last["broadcast_id"]))


@rule("CVM-PUSH-04", "Taux de conversion en baisse", "push", "major",
      last_n=3, prev_n=6, min_drop_pct=40, min_conversions=30, min_sent=1000, recent_days=14)
def push_conversion_drop(ctx: RuleContext, p: dict):
    """Taux de conversion des `last_n` derniers envois inférieur d'au moins `min_drop_pct` % à celui des `prev_n` précédents."""
    for bc, g in _mature(ctx, _sends(ctx)).groupby("bc_name", sort=False):
        if len(g) < p["last_n"] + p["prev_n"] or not _recent(g, p):
            continue
        last, prev = g.tail(p["last_n"]), g.iloc[-(p["last_n"] + p["prev_n"]):-p["last_n"]]
        if last["conversions"].sum() == 0 or last["sent"].sum() < p["min_sent"] or prev["conversions"].sum() < p["min_conversions"]:
            continue  # zéro conversion : couvert par « Ne convertit plus »
        r_last, r_prev = last["conversions"].sum() / last["sent"].sum(), prev["conversions"].sum() / prev["sent"].sum()
        drop = 1 - r_last / r_prev
        if drop < p["min_drop_pct"] / 100:
            continue
        lost = (r_prev - r_last) * last["sent"].sum()
        yield _bc_anomaly(
            bc, g, last["date"].iloc[-1], p["severity"], "conversion_rate", round(float(r_last), 5),
            f"≈ {fmt_pct(r_prev)} (les {p['prev_n']} envois précédents)",
            f"« {bc} » : taux de conversion {fmt_pct(r_last)} sur les {p['last_n']} derniers envois contre {fmt_pct(r_prev)} "
            f"avant (−{drop * 100:.0f} %).",
            f"~{fmt_int(lost)} conversions perdues",
            "Vérifier le message, la cible et le créneau d'envoi ; comparer à la période précédente.",
            drop_pct=round(drop * 100, 1), lost_conversions=int(lost))


@rule("CVM-PUSH-05", "Livraison en baisse", "push", "major",
      last_n=3, prev_n=6, min_drop_pct=15, min_sent=5000, recent_days=14)
def push_delivery_drop(ctx: RuleContext, p: dict):
    """Delivery% des `last_n` derniers envois en baisse d'au moins `min_drop_pct` % vs les `prev_n` précédents, variation plateforme retirée."""
    df = _sends(ctx, scoped=False)
    df = df[(df["sent"] > 0) & (df["age"] >= 1) & df["delivered"].notna()].copy()
    if df.empty:
        return
    day = df.groupby("date").agg(d=("delivered", "sum"), s=("sent", "sum"))
    df["expected"] = df["sent"] * df["date"].map(day["d"] / day["s"])  # livraison attendue au niveau plateforme du jour

    for bc, g in df.groupby("bc_name", sort=False):
        if len(g) < p["last_n"] + p["prev_n"] or not _recent(g, p):
            continue
        last, prev = g.tail(p["last_n"]), g.iloc[-(p["last_n"] + p["prev_n"]):-p["last_n"]]
        if last["sent"].sum() < p["min_sent"] or last["delivered"].sum() == 0 or prev["delivered"].sum() == 0:
            continue  # zéro livraison : couvert par « Plus aucune livraison remontée »
        rel_last = last["delivered"].sum() / last["expected"].sum()
        rel_prev = prev["delivered"].sum() / prev["expected"].sum()
        drop = 1 - rel_last / rel_prev
        if drop < p["min_drop_pct"] / 100:
            continue
        r_last, r_prev = last["delivered"].sum() / last["sent"].sum(), prev["delivered"].sum() / prev["sent"].sum()
        yield _bc_anomaly(
            bc, g, last["date"].iloc[-1], p["severity"], "delivery_rate", round(float(r_last), 5),
            f"≈ {fmt_pct(r_prev)} avant, corrigé de la plateforme",
            f"« {bc} » : Delivery% {fmt_pct(r_last)} sur les {p['last_n']} derniers envois contre {fmt_pct(r_prev)} avant ; "
            f"−{drop * 100:.0f} % par rapport à la plateforme sur les mêmes jours.",
            f"~{fmt_int((rel_prev - rel_last) * last['expected'].sum())} messages non délivrés en plus",
            "Vérifier la route SMS (opérateur, SMSC) et la remontée des accusés de réception pour ce BC.",
            drop_pct=round(drop * 100, 1))


@rule("CVM-PUSH-06", "Plus aucune livraison remontée", "push", "major",
      last_n=3, min_sends=3, min_sent=1000, recent_days=14)
def push_no_delivery(ctx: RuleContext, p: dict):
    """Livraison mesurée sur au moins `min_sends` envois, et les `last_n` derniers ne remontent plus aucun message délivré."""
    df = _sends(ctx, scoped=False)
    df = df[(df["sent"] > 0) & (df["age"] >= 1)]
    for bc, g in df.groupby("bc_name", sort=False):
        run = _trailing(g["delivered"].fillna(0) == 0)
        if run < p["last_n"] or not _recent(g, p):
            continue
        tail, before = g.tail(run), g.iloc[:-run]
        if (before["delivered"].fillna(0) > 0).sum() < p["min_sends"] or tail["sent"].sum() < p["min_sent"]:
            continue
        yield _bc_anomaly(
            bc, g, tail["date"].iloc[0], p["severity"], "delivered", 0, "Delivered > 0",
            f"« {bc} » : plus aucune livraison remontée sur ses {run} derniers envois ({fmt_int(tail['sent'].sum())} envoyés).",
            f"{fmt_int(tail['sent'].sum())} messages sans accusé de livraison",
            "Vérifier la remontée des accusés (DLR) : perte de remontée ou vrai problème de livraison.")


@rule("CVM-PUSH-07", "Aucune conversion enregistrée", "push", "minor", min_sends=5, min_sent=10000, recent_days=14)
def push_never_converted(ctx: RuleContext, p: dict):
    """BC active qui n'a enregistré aucune conversion depuis le début des rapports, sur `min_sends` envois et `min_sent` clients ciblés."""
    for bc, g in _mature(ctx, _sends(ctx)).groupby("bc_name", sort=False):
        if g["conversions"].fillna(0).sum() > 0 or len(g) < p["min_sends"] or g["sent"].sum() < p["min_sent"] or not _recent(g, p):
            continue
        yield _bc_anomaly(
            bc, g, g["date"].iloc[0], p["severity"], "conversions", 0, "≥ 1 conversion",
            f"« {bc} » n'a enregistré aucune conversion depuis le {g['date'].iloc[0]} : {len(g)} envois, "
            f"{fmt_int(g['sent'].sum())} clients ciblés.",
            f"{fmt_int(g['sent'].sum())} messages sans conversion",
            "Vérifier que le BC a un objectif de conversion et que le suivi (offre, attribution) est configuré.")


@rule("CVM-PUSH-08", "Pas mieux que le groupe de contrôle", "push", "minor",
      last_n=5, min_cg=1000, min_conversions=10, recent_days=14)
def push_not_better_than_control(ctx: RuleContext, p: dict):
    """Sur les `last_n` derniers envois avec groupe de contrôle, le taux des ciblés est inférieur ou égal à celui du GC."""
    df = _mature(ctx, _sends(ctx))
    df = df[df["cg_size"].fillna(0) > 0]
    for bc, g in df.groupby("bc_name", sort=False):
        if not _recent(g, p):
            continue
        w = g.tail(p["last_n"])
        if w["cg_size"].sum() < p["min_cg"] or w["conversions"].sum() + w["cg_conversions"].sum() < p["min_conversions"]:
            continue
        r_t, r_cg = w["conversions"].sum() / w["sent"].sum(), w["cg_conversions"].sum() / w["cg_size"].sum()
        if r_t > r_cg:
            continue
        yield _bc_anomaly(
            bc, g, w["date"].iloc[-1], p["severity"], "conversion_rate", round(float(r_t), 5),
            f"> {fmt_pct(r_cg)} (groupe de contrôle)",
            f"« {bc} » n'apporte pas mieux que le groupe de contrôle sur ses {len(w)} derniers envois : "
            f"ciblés {fmt_pct(r_t)}, GC {fmt_pct(r_cg)} ({fmt_int(w['cg_size'].sum())} clients en GC).",
            "Aucun effet incrémental mesuré",
            "Revoir le ciblage, l'offre ou le message ; consulter l'onglet Analytics › Incrémentalité.",
            cg_rate=round(float(r_cg), 5))


@rule("CVM-PUSH-09", "N'envoie plus", "push", "info",
      min_active_days=5, window_days=14, silent_days=3, stopped_within_days=30)
def push_stopped_sending(ctx: RuleContext, p: dict):
    """La BC, qui convertissait et envoyait au moins `min_active_days` jours sur `window_days`, n'a plus rien envoyé depuis `silent_days` jours ou plus."""
    snap = pd.Timestamp(ctx.snapshot_date)
    df = _sends(ctx)
    df = df[df["sent"] > 0]
    for bc, g in df.groupby("bc_name", sort=False):
        last = pd.Timestamp(g["date"].max())
        silent = (snap - last).days
        if silent < p["silent_days"] or silent > p["stopped_within_days"]:
            continue
        w = g[pd.to_datetime(g["date"]) > last - pd.Timedelta(days=p["window_days"])]
        if w["date"].nunique() < p["min_active_days"] or w["conversions"].fillna(0).sum() <= 0:
            continue
        yield _bc_anomaly(
            bc, g, last.date().isoformat(), p["severity"], "jours_sans_envoi", silent, "envoi régulier",
            f"« {bc} » n'envoie plus depuis {silent} jours (dernier envoi le {last.date()}) ; elle envoyait "
            f"{w['date'].nunique()} jours sur {p['window_days']} et convertissait ({fmt_int(w['conversions'].sum())} conversions).",
            f"~{fmt_int(w['conversions'].sum() / p['window_days'] * silent)} conversions non réalisées",
            "Vérifier si l'arrêt est voulu (campagne terminée) ; sinon relancer le BC.")


# --------------------------------------------------------------------------- Inbound

def _offer_daily(ctx: RuleContext):
    """Agrégat journalier par offre + date de référence (dernier jour du fichier IM)."""
    im = ctx.hist_im.copy()
    daily = im.groupby(["offer_id", "date"]).agg(
        imp=("impressions", "sum"), ok=("fulfillment_success", "sum"), ko=("fulfillment_failures", "sum"),
        offer=("offer_name", "last"), touchpoint=("touchpoint", "last")).reset_index()
    return daily, pd.Timestamp(daily["date"].max())


def _window(g: pd.DataFrame, end: pd.Timestamp, days: int, back: int = 0) -> pd.DataFrame:
    """Jours (end - back - days, end - back]."""
    d = pd.to_datetime(g["date"])
    hi = end - pd.Timedelta(days=back)
    return g[(d <= hi) & (d > hi - pd.Timedelta(days=days))]


def _offer_anomaly(entity_key: str, g: pd.DataFrame, date: str, severity: str, metric: str, value, expected: str,
                   message: str, impact: str, action: str, volume: int, entity_type: str = "offer", **details) -> Anomaly:
    return Anomaly(
        entity_type=entity_type, entity_key=entity_key, date=date, category=g["touchpoint"].iloc[-1], severity=severity,
        metric=metric, value=value, expected=expected, volume=int(volume), message=message,
        details={"offer": g["offer"].iloc[-1], "impact": impact, "action": action, **details})


@rule("CVM-INB-01", "Plus aucun achat", "im", "critical", days=7, min_impressions=1000, critical_expected=20)
def offer_no_purchase(ctx: RuleContext, p: dict):
    """Offre déjà achetée, sans achat réussi sur les `days` derniers jours alors qu'elle a été affichée au moins `min_impressions` fois.

    Critique si, à son taux d'achat d'avant, au moins `critical_expected` achats étaient attendus depuis le dernier achat ; à surveiller sinon.
    """
    daily, end = _offer_daily(ctx)
    for oid, g in daily.groupby("offer_id", sort=False):
        g = g.sort_values("date")
        bought = g[g["ok"] > 0]
        win = _window(g, end, p["days"])
        if bought.empty or win["ok"].sum() > 0 or win["imp"].sum() < p["min_impressions"]:
            continue
        last_buy = bought["date"].iloc[-1]
        before = g[g["date"] <= last_buy]
        rate = before["ok"].sum() / before["imp"].sum() if before["imp"].sum() else 0
        since = g[g["date"] > last_buy]
        expected = rate * since["imp"].sum()
        sev = "critical" if expected >= p["critical_expected"] else "minor"
        name = g["offer"].iloc[-1]
        yield _offer_anomaly(
            str(oid), g, last_buy, sev, "purchases", 0, f"~{fmt_int(expected)} achats attendus",
            f"Offre « {name} » : aucun achat réussi depuis le {last_buy} ({fmt_int(since['imp'].sum())} impressions depuis) ; "
            f"≈ {fmt_int(expected)} achats attendus à son taux d'avant ({fmt_pct(rate)}).",
            f"~{fmt_int(expected)} achats perdus", "Vérifier l'éligibilité, le prix/contenu de l'offre et le provisioning.",
            since["imp"].sum(), expected_purchases=round(float(expected), 1), last_purchase=last_buy)


@rule("CVM-INB-02", "Échecs d'achat élevés", "im", "major", days=7, min_fail_pct=20, critical_pct=50, min_attempts=100)
def offer_high_failures(ctx: RuleContext, p: dict):
    """Sur les `days` derniers jours, au moins `min_fail_pct` % des tentatives d'achat échouent (Fulfillment Failures). Critique dès `critical_pct` %."""
    daily, end = _offer_daily(ctx)
    for oid, g in daily.groupby("offer_id", sort=False):
        win = _window(g, end, p["days"])
        attempts = win["ok"].sum() + win["ko"].sum()
        if attempts < p["min_attempts"]:
            continue
        rate = win["ko"].sum() / attempts
        if rate < p["min_fail_pct"] / 100:
            continue
        sev = "critical" if rate >= p["critical_pct"] / 100 else p["severity"]
        name = g["offer"].iloc[-1]
        yield _offer_anomaly(
            str(oid), g, end.date().isoformat(), sev, "failure_rate", round(float(rate), 4), f"< {p['min_fail_pct']} %",
            f"Offre « {name} » : {fmt_pct(rate)} des tentatives d'achat échouent sur {p['days']} jours "
            f"({fmt_int(win['ko'].sum())} échecs sur {fmt_int(attempts)}).",
            f"{fmt_int(win['ko'].sum())} achats échoués", "Vérifier le provisioning de l'offre avec l'équipe IT / Flytxt.",
            attempts)


@rule("CVM-INB-03", "Achats en baisse", "im", "major", days=3, prev_days=7, min_drop_pct=50, min_prev=30)
def offer_purchases_drop(ctx: RuleContext, p: dict):
    """Achats par jour des `days` derniers jours inférieurs d'au moins `min_drop_pct` % à ceux des `prev_days` jours précédents (au moins `min_prev` achats)."""
    daily, end = _offer_daily(ctx)
    for oid, g in daily.groupby("offer_id", sort=False):
        recent = _window(g, end, p["days"])
        prev = _window(g, end, p["prev_days"], back=p["days"])
        if recent["ok"].sum() == 0 or prev["ok"].sum() < p["min_prev"]:
            continue  # zéro achat : couvert par « Plus aucun achat »
        per_recent, per_prev = recent["ok"].sum() / p["days"], prev["ok"].sum() / p["prev_days"]
        drop = 1 - per_recent / per_prev
        if drop < p["min_drop_pct"] / 100:
            continue
        name = g["offer"].iloc[-1]
        lost = (per_prev - per_recent) * p["days"]
        yield _offer_anomaly(
            str(oid), g, end.date().isoformat(), p["severity"], "purchases_per_day", round(float(per_recent), 1),
            f"≈ {fmt_int(per_prev)} /jour avant",
            f"Offre « {name} » : {fmt_int(per_recent)} achats/jour sur les {p['days']} derniers jours contre "
            f"{fmt_int(per_prev)} sur les {p['prev_days']} précédents (−{drop * 100:.0f} %).",
            f"~{fmt_int(lost)} achats perdus", "Vérifier l'affichage, l'éligibilité et le prix de l'offre.",
            recent["imp"].sum(), drop_pct=round(drop * 100, 1))


@rule("CVM-INB-04", "Jamais achetée", "im", "minor", min_impressions=5000, recent_days=7)
def offer_never_purchased(ctx: RuleContext, p: dict):
    """Offre toujours affichée qui n'a enregistré aucun achat réussi, pour au moins `min_impressions` impressions depuis le début du suivi."""
    daily, end = _offer_daily(ctx)
    for oid, g in daily.groupby("offer_id", sort=False):
        if g["ok"].sum() > 0 or g["imp"].sum() < p["min_impressions"] or _window(g, end, p["recent_days"])["imp"].sum() <= 0:
            continue
        name = g["offer"].iloc[-1]
        yield _offer_anomaly(
            str(oid), g, g["date"].min(), p["severity"], "purchases", 0, "≥ 1 achat",
            f"Offre « {name} » affichée {fmt_int(g['imp'].sum())} fois depuis le {g['date'].min()} sans aucun achat réussi.",
            f"{fmt_int(g['imp'].sum())} impressions sans achat",
            "Vérifier le prix, le contenu et le provisioning de l'offre ; envisager de la retirer.", g["imp"].sum())


@rule("CVM-INB-05", "N'est plus affichée", "im", "major", silent_days=7, max_silent_days=30)
def offer_no_longer_displayed(ctx: RuleContext, p: dict):
    """Offre qui marchait (au moins un achat réussi) et n'a plus aucune impression depuis `silent_days` jours.

    Vérifié règle par règle : une offre peut disparaître d'une règle ou d'un programme et rester affichée ailleurs.
    Les règles au statut « Completed » (promos programmées arrivées à leur fin) sont ignorées.
    """
    im = ctx.hist_im
    end = pd.Timestamp(im["date"].max())
    for (oid, rid), g in im.groupby(["offer_id", "rule_id"], sort=False):
        if g["fulfillment_success"].sum() < 1 or str(g.sort_values("date")["rule_status"].iloc[-1]) == "Completed":
            continue
        shown = g[g["impressions"] > 0]
        if shown.empty:
            continue
        last = shown["date"].max()
        silent = (end - pd.Timestamp(last)).days
        if silent < p["silent_days"] or silent > p["max_silent_days"]:
            continue
        name, rname = g["offer_name"].iloc[-1], g["rule_name"].iloc[-1]
        g2 = g.assign(offer=g["offer_name"], touchpoint=g["touchpoint"])
        yield _offer_anomaly(
            f"{rid}:{oid}", g2, last, p["severity"], "jours_sans_impression", silent, f"< {p['silent_days']} jours",
            f"Offre « {name} » n'est plus affichée dans la règle « {rname} » depuis {silent} jours (dernière impression le {last}) ; "
            f"elle avait {fmt_int(g['fulfillment_success'].sum())} achats réussis.",
            f"{fmt_int(g['fulfillment_success'].sum())} achats historiques à risque",
            "Vérifier le statut de la règle / du programme et l'éligibilité de l'offre ; sinon l'archiver.",
            g["impressions"].sum(), entity_type="im_rule", rule=rname, offer_id=str(oid), rule_id_im=str(rid))
