"""Maturation des conversions Push : combien de conversions arrivent après l'envoi ?

Chaque snapshot fige les conversions d'un broadcast à un âge donné (snapshot_date - date d'envoi).
En comparant les versions d'un même broadcast entre snapshots, on estime la part des conversions
finales déjà connue à J+n, et on extrapole les conversions attendues pour les jours récents.
"""

from __future__ import annotations

import pandas as pd


def maturity_curve(versions: pd.DataFrame, reference_age: int = 14) -> pd.DataFrame:
    """Part des conversions (mesurées à ≥ reference_age jours) déjà présentes à chaque âge.

    `versions` : toutes les versions de broadcasts (repository.push_versions).
    Renvoie age_days, completion (médiane pondérée par le volume), broadcasts observés.
    """
    if versions.empty:
        return pd.DataFrame(columns=["age_days", "completion", "broadcasts"])
    v = versions[["broadcast_id", "age_days", "conversions"]]
    final = (v[v["age_days"] >= reference_age]
             .sort_values("age_days").groupby("broadcast_id")["conversions"].last())
    final = final[final > 0]
    early = v[v["broadcast_id"].isin(final.index) & (v["age_days"] < reference_age)].copy()
    if early.empty:
        return pd.DataFrame(columns=["age_days", "completion", "broadcasts"])
    early["final"] = early["broadcast_id"].map(final)
    curve = early.groupby("age_days").agg(conversions=("conversions", "sum"), final=("final", "sum"),
                                          broadcasts=("broadcast_id", "nunique")).reset_index()
    curve["completion"] = (curve["conversions"] / curve["final"]).clip(upper=1.0)
    curve = pd.concat([curve, pd.DataFrame([{"age_days": reference_age, "completion": 1.0, "broadcasts": len(final)}])])
    return curve[["age_days", "completion", "broadcasts"]].sort_values("age_days").reset_index(drop=True)


LATE_METRICS = ["conversions", "unique_conversions", "conversion_value", "fulfillment_success",
                "fulfillment_failure", "cg_conversions"]


def maturity_curves(versions: pd.DataFrame, metrics: list[str] | None = None,
                    reference_age: int = 10) -> dict[str, list[float]]:
    """Complétude par âge (0..reference_age) pour chaque métrique qui arrive en retard.

    Même méthode que `maturity_curve`, métrique par métrique : on rapporte la valeur connue à chaque âge à la
    valeur finale (mesurée à ≥ reference_age jours). Les âges jamais observés sont interpolés ; la complétude
    ne dépasse pas 1. Renvoie {métrique: [complétude à J0, J1, …, J reference_age]}.
    """
    out: dict[str, list[float]] = {}
    if versions.empty:
        return out
    for m in metrics or LATE_METRICS:
        if m not in versions:
            continue
        v = versions[["broadcast_id", "age_days", m]].dropna()
        final = v[v["age_days"] >= reference_age].sort_values("age_days").groupby("broadcast_id")[m].last()
        final = final[final > 0]
        early = v[v["broadcast_id"].isin(final.index) & (v["age_days"] < reference_age) & (v["age_days"] >= 0)].copy()
        if early.empty:
            continue
        early["final"] = early["broadcast_id"].map(final)
        g = early.groupby("age_days")[[m, "final"]].sum()
        c = (g[m] / g["final"]).clip(upper=1.0)
        c.loc[reference_age] = 1.0
        full = c.reindex(range(0, reference_age + 1)).interpolate(limit_direction="both").clip(lower=0.01)
        out[m] = [round(float(x), 4) for x in full]
    return out


def nowcast(push: pd.DataFrame, curve: pd.DataFrame) -> pd.DataFrame:
    """Conversions attendues à maturité pour chaque jour, via la courbe (interpolée par âge)."""
    daily = push.groupby("date").agg(conversions=("conversions", "sum"), age_days=("age_days", "max")).reset_index()
    if curve.empty or len(curve) < 2:
        daily["completion"] = None
        daily["expected_final"] = None
        return daily
    c = curve.set_index("age_days")["completion"]
    full = c.reindex(range(0, int(c.index.max()) + 1)).interpolate(limit_direction="both")
    daily["completion"] = daily["age_days"].map(lambda a: float(full.get(min(a, full.index.max()), 1.0)))
    daily["expected_final"] = daily["conversions"] / daily["completion"].where(daily["completion"] > 0)
    return daily
