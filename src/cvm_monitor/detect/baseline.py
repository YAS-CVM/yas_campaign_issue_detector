"""Comparaison à l'historique : médiane glissante + MAD (écart robuste)."""

from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SIGMA = 1.4826


def robust_zscores(series: pd.Series, window: int = 14, min_points: int = 5) -> pd.DataFrame:
    """Pour chaque point, compare la valeur aux `window` points PRÉCÉDENTS de la série.

    `series` doit être indexée par date (triée). Renvoie un DataFrame avec
    value, median, mad, z (NaN si l'historique est insuffisant).
    """
    s = series.sort_index().astype(float)
    rows = []
    values = s.to_numpy()
    for i, (idx, v) in enumerate(s.items()):
        past = values[max(0, i - window):i]
        past = past[~np.isnan(past)]
        if len(past) < min_points or np.isnan(v):
            rows.append((idx, v, np.nan, np.nan, np.nan))
            continue
        med = float(np.median(past))
        mad = float(np.median(np.abs(past - med))) * MAD_TO_SIGMA
        # plancher : évite les z démesurés sur une série quasi constante
        scale = max(mad, abs(med) * 0.05, 1e-9)
        rows.append((idx, v, med, mad, (v - med) / scale))
    return pd.DataFrame(rows, columns=["key", "value", "median", "mad", "z"]).set_index("key")
