"""Insights « valeur » : campagnes qui convertissent peu, offres peu achetées, manque à gagner estimé."""

from __future__ import annotations

from typing import Any

import pandas as pd

from cvm_monitor.analytics import kpi
from cvm_monitor.detect import percentiles as pcs

CAMPAIGN_LEVELS = {"category": ["category"], "campaign": ["campaign_name", "category"],
                   "bc": ["bc_name", "campaign_name", "category"]}
OFFER_LEVELS = {"touchpoint": ["touchpoint"], "program": ["program", "touchpoint"],
                "rule": ["rule_name", "program", "touchpoint"],
                "offer": ["offer_name", "touchpoint"]}


def _finish(df: pd.DataFrame, rate_col: str, volume_col: str, unit_value: pd.Series | float) -> pd.DataFrame:
    """Écart à la médiane des pairs et manque à gagner (conversions/achats manquants × valeur unitaire)."""
    # Sans assez de pairs (mode « static »), pas de médiane de groupe : on prend celle de toute la population.
    ref = df["p50"].fillna(df[rate_col].median())
    # Le manque à gagner ne se compte que pour les entités hors norme : une valeur sous la médiane mais dans la norme n'est pas un manque.
    df["gap_rate"] = (ref - df[rate_col]).clip(lower=0).where(df["flag"], 0.0)
    df["missing"] = df["gap_rate"] * df[volume_col]
    df["missing_value"] = df["missing"] * unit_value
    return df.rename(columns={"flag": "underperforming"})


def campaigns(push: pd.DataFrame, pc: dict[str, Any], *, level: str = "bc", maturity_days: int = 3,
              min_sent: int = 1000, min_abs_gap: float = 0.002,
              exclude_categories: tuple[str, ...] = ("Informative", "Engagements")) -> pd.DataFrame:
    """Conversion par entité vs pairs de la même catégorie (P5/P50). Matures, hors seeding/informatif."""
    if push.empty:
        return pd.DataFrame()
    df = push[~push["category"].isin(exclude_categories)]
    if "is_seeding" in df:
        df = df[~df["is_seeding"].astype(bool)]
    if "age_days" in df:
        df = df[df["age_days"] >= maturity_days]
    keys = CAMPAIGN_LEVELS[level]
    agg = kpi.push_by(df, keys)
    agg = agg[agg["sent"] >= min_sent].reset_index(drop=True)
    if agg.empty:
        return agg
    static = agg["conv_rate"] < min_abs_gap
    res = pcs.peer_outliers(agg, "conv_rate", "category", pcs.LOW, pc, min_abs_gap, static_mask=static)
    unit = (res["conversion_value"] / res["conversions"].where(res["conversions"] > 0)).fillna(0)
    res = _finish(res, "conv_rate", "sent", unit)
    return res.sort_values(["underperforming", "missing_value", "missing"], ascending=False).reset_index(drop=True)


def offers(im: pd.DataFrame, pc: dict[str, Any], *, level: str = "offer", min_impressions: int = 1000,
           min_abs_gap: float = 0.0005) -> pd.DataFrame:
    """Taux d'achat (fulfillment success / impressions) vs pairs du même touchpoint."""
    if im.empty:
        return pd.DataFrame()
    keys = OFFER_LEVELS[level]
    g = im.groupby(keys, dropna=False)
    agg = g[["impressions", "accepted", "declined", "fulfillment_success", "fulfillment_failures"]].sum().reset_index()
    agg["rules"] = g["rule_id"].nunique().to_numpy()
    agg = agg[agg["impressions"] >= min_impressions].reset_index(drop=True)
    if agg.empty:
        return agg
    agg["take_rate"] = agg["fulfillment_success"] / agg["impressions"]
    agg["accept_rate"] = agg["accepted"] / agg["impressions"]
    static = agg["take_rate"] == 0
    res = pcs.peer_outliers(agg, "take_rate", "touchpoint", pcs.LOW, pc, min_abs_gap, static_mask=static)
    res = _finish(res, "take_rate", "impressions", 1.0)  # pas de valeur monétaire IM : achats manquants
    res = res.rename(columns={"missing_value": "missing_purchases"}).drop(columns=["missing"])
    return res.sort_values(["underperforming", "missing_purchases"], ascending=False).reset_index(drop=True)


def summary(camp: pd.DataFrame, off: pd.DataFrame) -> dict[str, Any]:
    c = camp[camp["underperforming"]] if not camp.empty else camp
    o = off[off["underperforming"]] if not off.empty else off
    return {
        "campaigns_total": int(len(camp)), "campaigns_underperforming": int(len(c)),
        "missing_conversions": float(c["missing"].sum()) if len(c) else 0.0,
        "missing_value": float(c["missing_value"].sum()) if len(c) else 0.0,
        "offers_total": int(len(off)), "offers_underperforming": int(len(o)),
        "missing_purchases": float(o["missing_purchases"].sum()) if len(o) else 0.0,
    }
