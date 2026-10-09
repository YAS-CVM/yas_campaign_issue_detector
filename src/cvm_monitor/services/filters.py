"""Filtres uniques, du général au fin, appliqués aux faits Push et IM."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Filters:
    date_from: str | None = None
    date_to: str | None = None
    categories: list[str] = field(default_factory=list)
    campaigns: list[str] = field(default_factory=list)
    bcs: list[str] = field(default_factory=list)
    broadcasts: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    touchpoints: list[str] = field(default_factory=list)
    programs: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    offers: list[str] = field(default_factory=list)
    include_seeding: bool = False
    mature_only: bool = False
    maturity_days: int = 3


# filtre -> colonne
_PUSH_COLS = {"categories": "category", "campaigns": "campaign_name", "bcs": "bc_name",
              "broadcasts": "broadcast_id", "statuses": "status"}
_IM_COLS = {"touchpoints": "touchpoint", "programs": "program", "rules": "rule_name", "offers": "offer_name"}


def _between(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    if "date" not in df or df.empty:
        return df
    if f.date_from:
        df = df[df["date"] >= f.date_from]
    if f.date_to:
        df = df[df["date"] <= f.date_to]
    return df


def _isin(df: pd.DataFrame, f: Filters, cols: dict[str, str]) -> pd.DataFrame:
    for attr, col in cols.items():
        values = getattr(f, attr)
        if values and col in df:
            df = df[df[col].astype(str).isin([str(v) for v in values])]
    return df


def apply_push(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    df = _isin(_between(df, f), f, _PUSH_COLS)
    if not f.include_seeding and "is_seeding" in df:
        df = df[~df["is_seeding"].astype(bool)]
    if f.mature_only and "age_days" in df:
        df = df[df["age_days"] >= f.maturity_days]
    return df


def apply_im(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    return _isin(_between(df, f), f, _IM_COLS)


def options(push: pd.DataFrame, im: pd.DataFrame, f: Filters) -> dict[str, list[str]]:
    """Valeurs disponibles par dimension, en cascade (chaque liste tient compte des autres filtres)."""
    def values(df: pd.DataFrame, col: str, cols: dict[str, str], apply) -> list[str]:
        if df.empty or col not in df:
            return []
        attr = next(a for a, c in cols.items() if c == col)
        relaxed = Filters(**{**f.__dict__, attr: []})
        sub = apply(df, relaxed)
        return sorted(sub[col].dropna().astype(str).unique().tolist())

    out = {a: values(push, c, _PUSH_COLS, apply_push) for a, c in _PUSH_COLS.items()}
    out.update({a: values(im, c, _IM_COLS, apply_im) for a, c in _IM_COLS.items()})
    dates = pd.concat([push.get("date", pd.Series(dtype=str)), im.get("date", pd.Series(dtype=str))])
    out["date_range"] = [str(dates.min()), str(dates.max())] if not dates.empty else []
    return out
