"""Quand envoyer et quoi pousser : meilleurs jours / heures d'envoi, BC qui progressent ou déclinent.

Le Conv% brut d'un créneau dépend surtout des campagnes qui y sont programmées. Chaque créneau est donc comparé
à ce que ses BC font en moyenne par ailleurs : `index` = conversions observées ÷ conversions attendues au
Conv% moyen de ces mêmes BC (1,00 = dans la norme du BC, 1,20 = 20 % au-dessus).
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from cvm_monitor.analytics import kpi

WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def blackout_hours(blackout: dict[str, str] | None) -> set[int]:
    """Heures entières couvertes par le blackout SMS (19h-07h par défaut)."""
    cfg = blackout or {}
    start, end = (int(str(cfg.get(k, d)).split(":")[0]) for k, d in (("start", "19:00"), ("end", "07:00")))
    return set(range(start, 24)) | set(range(0, end)) if start > end else set(range(start, end))


def scope(push: pd.DataFrame, *, maturity_days: int = 3, exclude_categories: tuple[str, ...] = (),
          technical_patterns: tuple[str, ...] = ()) -> pd.DataFrame:
    """Envois matures, hors seeding, catégories sans objectif de conversion et BC techniques, avec jour et heure."""
    if push.empty:
        return push
    df = push[(push["sent"] > 0) & ~push["category"].isin(exclude_categories)]
    if "is_seeding" in df:
        df = df[~df["is_seeding"].astype(bool)]
    if "age_days" in df:
        df = df[df["age_days"] >= maturity_days]
    if technical_patterns:
        pat = "|".join(map(re.escape, technical_patterns))
        df = df[~df["bc_name"].fillna("").str.contains(pat, case=False, regex=True)]
    df = df.copy()
    ts = pd.to_datetime(df["scheduled_at"], errors="coerce") if "scheduled_at" in df else pd.Series(pd.NaT, index=df.index)
    df["weekday"] = pd.to_datetime(df["date"]).dt.dayofweek
    df["hour"] = ts.dt.hour.fillna(-1).astype(int)
    # minuit pile = flow déclenché par un événement client, pas un créneau choisi
    df.loc[(ts.dt.hour == 0) & (ts.dt.minute == 0) & (ts.dt.second == 0), "hour"] = -1
    return df


def _with_index(df: pd.DataFrame, keys: list[str], min_sent: int, min_bc_conversions: int = 100) -> pd.DataFrame:
    """Agrégat par créneau + indice vs norme des BC concernés.

    L'indice ne porte que sur les BC qui convertissent assez (≥ `min_bc_conversions`, sinon la norme proche de zéro
    donne des indices démesurés) et qui sont envoyés sur au moins deux créneaux (un BC à créneau unique est
    toujours dans sa propre norme : il n'apprend rien). Il n'est fiable que si le créneau attend assez de conversions.
    """
    bc = df.groupby("bc_name")[["sent", "conversions"]].sum()
    slots = df.groupby("bc_name")[keys].apply(lambda g: len(g.drop_duplicates()))
    rate = (bc["conversions"] / bc["sent"]).where((bc["conversions"] >= min_bc_conversions) & (slots >= 2))
    df = df.assign(expected=df["sent"] * df["bc_name"].map(rate))
    agg = kpi.push_by(df, keys)
    g = df.dropna(subset=["expected"]).groupby(keys, dropna=False)
    obs, exp = g["conversions"].sum(), g["expected"].sum()
    agg = agg.merge((obs / exp.where(exp > 0)).rename("index").reset_index(), on=keys, how="left")
    agg = agg.merge(exp.rename("expected").reset_index(), on=keys, how="left")
    agg["value_per_sent"] = agg["conversion_value"] / agg["sent"].where(agg["sent"] > 0)
    agg["reliable"] = (agg["sent"] >= min_sent) & (agg["expected"].fillna(0) >= 100)
    return agg


def best_times(df: pd.DataFrame, *, blackout: dict[str, str] | None = None, min_sent: int = 20_000) -> dict[str, Any]:
    """Jours et heures d'envoi classés (hors blackout), + meilleurs créneaux jour × heure."""
    empty = {"weekday": [], "hour": [], "slots": [], "best_weekday": None, "best_hour": None, "blackout": []}
    if df is None or df.empty:
        return empty
    hours_off = blackout_hours(blackout)
    choice = df[df["hour"] >= 0]          # créneaux réellement choisis (hors flows déclenchés)
    allowed = choice[~choice["hour"].isin(hours_off)]
    out = dict(empty, blackout=sorted(hours_off))

    wd = _with_index(df[df["hour"].isin(range(24)) | (df["hour"] == -1)], ["weekday"], min_sent)
    out["weekday"] = _rows(wd, "weekday", lambda k: WEEKDAYS[int(k)])
    if not allowed.empty:
        hr = _with_index(allowed, ["hour"], min_sent)
        out["hour"] = _rows(hr, "hour", lambda k: f"{int(k)} h")
        sl = _with_index(allowed, ["weekday", "hour"], min_sent)
        sl = sl[sl["reliable"]].sort_values("index", ascending=False).head(10)
        out["slots"] = [{"label": f"{WEEKDAYS[int(r.weekday)]} {int(r.hour)} h", "index": r.index_, "conv_rate": r.conv_rate,
                         "sent": r.sent, "broadcasts": r.broadcasts}
                        for r in sl.rename(columns={"index": "index_"}).itertuples()]
        out["best_hour"] = _best(out["hour"])
    out["best_weekday"] = _best(out["weekday"])
    return out


def _rows(agg: pd.DataFrame, key: str, label) -> list[dict]:
    return [{"key": int(r[key]), "label": label(r[key]), "sent": float(r["sent"]), "broadcasts": int(r["broadcasts"]),
             "conversions": float(r["conversions"]), "conv_rate": r["conv_rate"], "value_per_sent": r["value_per_sent"],
             "index": r["index"], "reliable": bool(r["reliable"])}
            for _, r in agg.sort_values(key).iterrows()]


def _best(rows: list[dict]) -> dict | None:
    ok = [r for r in rows if r["reliable"] and pd.notna(r["index"])]
    return max(ok, key=lambda r: r["index"]) if ok else None


def bc_trends(df: pd.DataFrame, *, recent_days: int = 7, base_days: int = 28, min_sent: int = 5_000,
              min_lost: int = 50, rel_drop: float = 0.2, top: int = 10) -> dict[str, list[dict]]:
    """Meilleurs BC (conversions sur la période de référence) et BC en déclin (Conv% récent vs référence)."""
    if df is None or df.empty:
        return {"top": [], "declining": []}
    end = pd.Timestamp(df["date"].max())
    d = pd.to_datetime(df["date"])
    recent = df[d > end - pd.Timedelta(days=recent_days)]
    base = df[(d <= end - pd.Timedelta(days=recent_days)) & (d > end - pd.Timedelta(days=recent_days + base_days))]
    cols = ["bc_name", "category", "sent", "conversions", "conversion_value", "conv_rate"]
    best = kpi.push_by(pd.concat([recent, base]), ["bc_name", "category"]).sort_values("conversions", ascending=False).head(top)
    window = {"end": end.date().isoformat(), "recent_days": recent_days, "base_days": base_days}
    top_rows = best[[c for c in cols if c in best]].to_dict("records")
    if recent.empty or base.empty:
        return {"top": top_rows, "declining": [], "window": window}
    r, b = kpi.push_by(recent, ["bc_name", "category"]), kpi.push_by(base, ["bc_name", "category"])
    both = r.merge(b, on=["bc_name", "category"], suffixes=("", "_base"))
    both = both[(both["sent"] >= min_sent) & (both["sent_base"] >= min_sent)].copy()
    both["rel_change"] = both["conv_rate"] / both["conv_rate_base"].where(both["conv_rate_base"] > 0) - 1
    both["lost_conversions"] = ((both["conv_rate_base"] - both["conv_rate"]) * both["sent"]).clip(lower=0)
    unit = both["conversion_value_base"] / both["conversions_base"].where(both["conversions_base"] > 0)
    both["lost_value"] = both["lost_conversions"] * unit.fillna(0)
    dec = both[(both["rel_change"] <= -rel_drop) & (both["lost_conversions"] >= min_lost)]
    dec = dec.sort_values("lost_conversions", ascending=False).head(top)
    keep = ["bc_name", "category", "sent", "conversions", "conv_rate", "conv_rate_base", "rel_change", "lost_conversions", "lost_value"]
    return {"top": top_rows, "declining": dec[keep].to_dict("records"), "window": window}
