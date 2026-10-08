"""Indicateurs agrégés (jour, catégorie, campagne, règle IM)."""

from __future__ import annotations

import pandas as pd

from .uplift import two_proportion_test


def _rates(df: pd.DataFrame) -> pd.DataFrame:
    sent = df["sent"].where(df["sent"] > 0)
    df["delivery_rate"] = df["delivered"] / sent
    df["conv_rate"] = df["conversions"] / sent
    df["cg_conv_rate"] = df["cg_conversions"] / df["cg_size"].where(df["cg_size"] > 0)
    df["net_conv_rate"] = df["conv_rate"] - df["cg_conv_rate"]
    return df


PUSH_SUMS = ["generated", "sent", "acknowledged", "delivered", "conversions", "unique_conversions",
             "conversion_value", "fulfillment_success", "fulfillment_failure", "cg_size", "cg_conversions"]


def push_by(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=keys + PUSH_SUMS)
    out = df.groupby(keys, dropna=False)[[c for c in PUSH_SUMS if c in df]].sum().reset_index()
    out["broadcasts"] = df.groupby(keys, dropna=False).size().to_numpy()
    return _rates(out)


def push_daily(df: pd.DataFrame) -> pd.DataFrame:
    return push_by(df, ["date"]).sort_values("date")


def im_daily(df: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    keys = ["date"] + (by or [])
    if df.empty:
        return pd.DataFrame(columns=keys)
    out = df.groupby(keys)[["impressions", "fulfillment_success", "fulfillment_failures"]].sum().reset_index()
    attempts = out["fulfillment_success"] + out["fulfillment_failures"]
    out["take_rate"] = out["fulfillment_success"] / out["impressions"].where(out["impressions"] > 0)
    out["failure_rate"] = out["fulfillment_failures"] / attempts.where(attempts > 0)
    return out.sort_values(keys)


def im_by_rule(df: pd.DataFrame) -> pd.DataFrame:
    out = df.groupby(["rule_id", "rule_name", "program", "touchpoint"], dropna=False).agg(
        impressions=("impressions", "sum"), success=("fulfillment_success", "sum"),
        failures=("fulfillment_failures", "sum"), days=("date", "nunique"), last_date=("date", "max"),
    ).reset_index()
    attempts = out["success"] + out["failures"]
    out["failure_rate"] = out["failures"] / attempts.where(attempts > 0)
    out["take_rate"] = out["success"] / out["impressions"].where(out["impressions"] > 0)
    return out


def campaign_scorecard(df: pd.DataFrame, key: str = "campaign_name", maturity_days: int = 3) -> pd.DataFrame:
    """Uplift par campagne / BC sur les envois matures, avec significativité."""
    mature = df[(df["age_days"] >= maturity_days) & (df["sent"] > 0)] if "age_days" in df else df
    agg = push_by(mature, [key, "category"])
    rows = []
    for r in agg.itertuples(index=False):
        res = two_proportion_test(getattr(r, "unique_conversions"), r.sent, r.cg_conversions, r.cg_size)
        rows.append({
            "uplift": res.uplift if res else None,
            "ci_low": res.ci_low if res else None,
            "ci_high": res.ci_high if res else None,
            "p_value": res.p_value if res else None,
            "significant": bool(res.significant) if res else False,
            "incremental_conversions": res.uplift * r.sent if res else None,
        })
    out = pd.concat([agg.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out["verdict"] = out.apply(_verdict, axis=1)
    return out.sort_values("incremental_conversions", ascending=False, na_position="last")


def _verdict(r: pd.Series) -> str:
    if not r["cg_size"]:
        return "CG = 0"
    if r["cg_conversions"] < 30:
        return "CG Conv < 30"
    if not r["significant"]:
        return "Non significatif"
    return "Net Conversion +" if r["uplift"] > 0 else "Net Conversion −"


def headline(push: pd.DataFrame, im: pd.DataFrame, day: str | None = None) -> dict:
    """KPI du dernier jour disponible + variation vs moyenne des 7 jours précédents."""
    pdaily, idaily = push_daily(push), im_daily(im)
    if pdaily.empty:
        return {}
    day = day or pdaily["date"].max()
    out = {"date": day}
    for name, frame, col in (
        ("sent", pdaily, "sent"), ("delivery_rate", pdaily, "delivery_rate"),
        ("conversions", pdaily, "conversions"), ("impressions", idaily, "impressions"),
        ("im_success", idaily, "fulfillment_success"), ("im_failure_rate", idaily, "failure_rate"),
    ):
        cur = frame.loc[frame["date"] == day, col]
        prev = frame.loc[frame["date"] < day, col].tail(7)
        value = float(cur.iloc[0]) if len(cur) else None
        ref = float(prev.mean()) if len(prev) else None
        out[name] = {"value": value, "ref7": ref,
                     "delta": (value - ref) / ref if value is not None and ref else None}
    return out
