"""Seuils relatifs par percentiles : comparaison aux pairs (coupe transversale) ou à l'historique propre."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DEFAULTS: dict[str, Any] = {
    "low": 5,                   # bas = mauvais : alerte sous ce percentile
    "median": 50,               # repère central affiché dans les messages
    "normal_high": 75,          # borne haute de la plage « normale » (contexte)
    "high": 95,                 # haut = mauvais : alerte au-dessus de ce percentile
    "min_peers": 20,            # taille minimale d'un groupe de pairs
    "min_history_points": 10,   # jours d'historique minimaux pour une série
    "history_window_days": 28,  # fenêtre d'historique glissante
    "fallback_to_static": True,  # sans assez de pairs, on garde le seuil fixe historique
}

LOW, HIGH = "low", "high"       # sens du « mauvais » : valeur trop basse / trop haute


def settings(det: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULTS, **(det.get("percentiles") or {})}


def _quantiles(values: np.ndarray, pc: dict[str, Any]) -> dict[str, float]:
    qs = [pc["low"], pc["median"], pc["normal_high"], pc["high"]]
    p_low, p50, p_nh, p_high = np.percentile(values, qs)
    return {"p_low": float(p_low), "p50": float(p50), "p_normal_high": float(p_nh), "p_high": float(p_high)}


def _is_outlier(value: float, q: dict[str, float], direction: str, min_abs_gap: float) -> bool:
    """Valeur dans la queue « mauvaise » ET assez loin de la médiane (évite d'alerter sur une distribution serrée)."""
    if direction == LOW:
        return value <= q["p_low"] and (q["p50"] - value) >= min_abs_gap
    return value >= q["p_high"] and (value - q["p50"]) >= min_abs_gap


def peer_outliers(table: pd.DataFrame, col: str, group_col: str | None, direction: str,
                  pc: dict[str, Any], min_abs_gap: float, static_mask: pd.Series | None = None) -> pd.DataFrame:
    """Compare chaque ligne de `table[col]` à la distribution de ses pairs (même `group_col`).

    Groupe trop petit → distribution de toute la population ; population trop petite → `static_mask`
    (seuil fixe) si `fallback_to_static`, sinon pas d'alerte.
    Ajoute : flag, mode (percentile | percentile_global | static | insufficient), n, p_low, p50, p_normal_high, p_high.
    """
    out = table.copy()
    for c in ("p_low", "p50", "p_normal_high", "p_high"):
        out[c] = np.nan
    out["n"] = 0
    out["flag"] = False
    out["mode"] = "insufficient"

    valid = out[col].notna()
    all_vals = out.loc[valid, col].to_numpy(dtype=float)
    global_q = _quantiles(all_vals, pc) if len(all_vals) >= pc["min_peers"] else None

    groups = out.groupby(group_col, dropna=False).groups if group_col else {None: out.index}
    for _, idx in groups.items():
        idx = out.loc[idx].index[valid.loc[idx]]
        vals = out.loc[idx, col].to_numpy(dtype=float)
        if len(vals) >= pc["min_peers"]:
            q, mode, n = _quantiles(vals, pc), "percentile", len(vals)
        elif global_q is not None:
            q, mode, n = global_q, "percentile_global", len(all_vals)
        else:
            q, mode, n = None, "insufficient", len(all_vals)
        if q is None:
            if pc["fallback_to_static"] and static_mask is not None:
                out.loc[idx, "flag"] = static_mask.loc[idx].to_numpy()
                out.loc[idx, "mode"] = "static"
            continue
        for k, v in q.items():
            out.loc[idx, k] = v
        out.loc[idx, "n"] = n
        out.loc[idx, "mode"] = mode
        out.loc[idx, "flag"] = [_is_outlier(v, q, direction, min_abs_gap) for v in vals]
    return out


def history_outliers(series: pd.Series, direction: str, pc: dict[str, Any], min_abs_gap: float = 0.0,
                     min_rel_gap: float = 0.0) -> pd.DataFrame:
    """Compare chaque point de `series` (indexée par date) à ses `history_window_days` points PRÉCÉDENTS.

    Ajoute : value, p_low, p50, p_normal_high, p_high, n, flag, consecutive (le point précédent était aussi hors norme).
    """
    s = series.sort_index().astype(float)
    values = s.to_numpy()
    window = int(pc["history_window_days"])
    rows = []
    for i, (idx, v) in enumerate(s.items()):
        past = values[max(0, i - window):i]
        past = past[~np.isnan(past)]
        if len(past) < pc["min_history_points"] or np.isnan(v):
            rows.append((idx, v, np.nan, np.nan, np.nan, np.nan, len(past), False))
            continue
        q = _quantiles(past, pc)
        gap = max(min_abs_gap, min_rel_gap * abs(q["p50"]))
        rows.append((idx, v, q["p_low"], q["p50"], q["p_normal_high"], q["p_high"], len(past),
                     _is_outlier(v, q, direction, gap)))
    df = pd.DataFrame(rows, columns=["key", "value", "p_low", "p50", "p_normal_high", "p_high", "n", "flag"])
    df = df.set_index("key")
    df["consecutive"] = df["flag"] & df["flag"].shift(1, fill_value=False)
    return df


def describe(row: Any, direction: str, fmt) -> str:
    """Position dans la distribution, pour les messages d'alerte."""
    edge = ("P5" if direction == LOW else "P95")
    ref = row["p_low"] if direction == LOW else row["p_high"]
    return (f"{edge} = {fmt(ref)}, médiane = {fmt(row['p50'])}, plage normale ≤ {fmt(row['p_normal_high'])}, "
            f"n = {int(row['n'])}")


def info(row: Any) -> dict[str, Any]:
    """Statistiques de distribution à stocker dans `Anomaly.details`."""
    return {"mode": row["mode"] if "mode" in row else "percentile", "n": int(row["n"]),
            "p_low": _r(row["p_low"]), "p50": _r(row["p50"]),
            "p_normal_high": _r(row["p_normal_high"]), "p_high": _r(row["p_high"])}


def _r(x: float) -> float | None:
    return None if pd.isna(x) else round(float(x), 4)


def runs(res: pd.DataFrame, keep: set[str]) -> list[pd.DataFrame]:
    """Regroupe les jours hors norme consécutifs (index = dates ISO) en épisodes : une alerte par épisode."""
    flagged = res[res["flag"] & res.index.isin(keep)]
    groups: list[list[str]] = []
    prev = None
    for day in flagged.index:
        d = pd.Timestamp(day)
        if prev is not None and (d - prev).days == 1:
            groups[-1].append(day)
        else:
            groups.append([day])
        prev = d
    return [flagged.loc[g] for g in groups]
