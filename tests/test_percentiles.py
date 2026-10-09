"""Seuils par percentiles : helpers et règles converties."""

from __future__ import annotations

import pandas as pd

from cvm_monitor.detect import percentiles as pct
from conftest import make_ctx, make_im, make_push, run_one

PC = pct.settings({})


def _peers(n=30, rate=0.95):
    return pd.DataFrame({"category": ["CVM"] * n, "rate": [rate + 0.001 * i for i in range(n)]})


def test_peer_outliers_flags_low_tail_only():
    t = _peers()
    t.loc[0, "rate"] = 0.40
    res = pct.peer_outliers(t, "rate", "category", pct.LOW, PC, 0.05)
    assert res["flag"].tolist().count(True) == 1 and bool(res.loc[0, "flag"])
    assert res.loc[0, "mode"] == "percentile" and res.loc[0, "n"] == 30


def test_peer_outliers_tight_distribution_is_not_flagged():
    # tout le monde entre 94.9 % et 95.0 % : le P5 existe mais l'écart à la médiane est négligeable
    t = pd.DataFrame({"category": "CVM", "rate": [0.949 + 0.00001 * i for i in range(30)]})
    assert not pct.peer_outliers(t, "rate", "category", pct.LOW, PC, 0.05)["flag"].any()


def test_peer_outliers_high_direction():
    t = _peers(rate=0.05)
    t.loc[0, "rate"] = 0.9
    res = pct.peer_outliers(t, "rate", "category", pct.HIGH, PC, 0.05)
    assert res["flag"].tolist() == [True] + [False] * 29


def test_peer_outliers_small_group_uses_global_then_static():
    t = pd.concat([_peers(25), pd.DataFrame({"category": ["Rare"], "rate": [0.2]})], ignore_index=True)
    res = pct.peer_outliers(t, "rate", "category", pct.LOW, PC, 0.05)
    assert res.iloc[-1]["mode"] == "percentile_global" and bool(res.iloc[-1]["flag"])

    tiny = _peers(5)
    static = pd.Series([True] + [False] * 4, index=tiny.index)
    res = pct.peer_outliers(tiny, "rate", "category", pct.LOW, PC, 0.05, static)
    assert set(res["mode"]) == {"static"} and res["flag"].tolist() == [True, False, False, False, False]
    off = pct.peer_outliers(tiny, "rate", "category", pct.LOW, {**PC, "fallback_to_static": False}, 0.05, static)
    assert not off["flag"].any()


def test_history_outliers_and_runs():
    days = pd.date_range("2026-09-01", periods=20).strftime("%Y-%m-%d")
    values = [0.50 + 0.01 * (i % 3) for i in range(20)]
    values[15] = values[16] = 0.20                       # deux jours de suite
    values[19] = 0.20                                     # un jour isolé
    res = pct.history_outliers(pd.Series(values, index=days), pct.LOW, PC, min_abs_gap=0.1)
    assert res["n"].iloc[5] == 5 and not res["flag"].iloc[:10].any()   # trop peu d'historique au début
    runs = pct.runs(res, set(days))
    assert [len(r) for r in runs] == [2, 1]
    assert runs[0].index[0] == days[15]


# --------------------------------------------------------------------------- règles


def _category_rows(n, ack, **extra):
    return [{"bc_name": f"BC_{i}", "sent": 10_000, "acknowledged": int(10_000 * (ack + 0.0005 * i)),
             "delivered": 5_000 + 20 * i, **extra} for i in range(n)]


def test_low_ack_percentile_flags_outlier_among_peers(cfg):
    rows = _category_rows(30, 0.95)
    rows.append({"bc_name": "BC_BAD", "sent": 10_000, "acknowledged": 4_000})
    ctx = make_ctx(cfg, push=make_push(rows))
    found = run_one(ctx, "PM-DLV-03")
    assert [a.entity_key for a in found] == ["BC_BAD"]
    assert found[0].details["mode"] == "percentile" and "P5" in found[0].message


def test_low_ack_static_mode_keeps_fixed_threshold(cfg):
    cfg.raw["rules"]["PM-DLV-03"]["mode"] = "static"
    rows = _category_rows(30, 0.95) + [{"bc_name": "BC_89", "sent": 10_000, "acknowledged": 8_900}]
    found = run_one(make_ctx(cfg, push=make_push(rows)), "PM-DLV-03")
    assert [a.entity_key for a in found] == ["BC_89"]           # < 90 % : seuil fixe
    assert found[0].details["mode"] == "static"


def test_low_ack_falls_back_to_static_with_few_peers(cfg):
    rows = [{"bc_name": "A", "acknowledged": 5_000}, {"bc_name": "B"}]
    found = run_one(make_ctx(cfg, push=make_push(rows)), "PM-DLV-03")
    assert [a.entity_key for a in found] == ["A"] and found[0].details["mode"] == "static"


def test_zero_delivery_groups_structural_zeros_by_category(cfg):
    rows = _category_rows(30, 0.95)
    rows += [{"bc_name": f"NBO_{i}", "sent": 5_000, "delivered": 0, "acknowledged": 5_000} for i in range(3)]
    found = run_one(make_ctx(cfg, push=make_push(rows)), "PM-DLV-01")
    grouped = [a for a in found if a.entity_type == "category"]
    assert len(grouped) == 1 and "3 BC avec Delivered 0" in grouped[0].message
    assert not [a for a in found if a.entity_type == "bc_name" and a.entity_key.startswith("NBO_")]


def test_push_fulfillment_failure_high_tail(cfg):
    rows = [{"bc_name": f"BC_{i}", "fulfillment_success": 980 - i, "fulfillment_failure": 20 + i} for i in range(30)]
    rows.append({"bc_name": "BC_BAD", "fulfillment_success": 300, "fulfillment_failure": 700})
    found = run_one(make_ctx(cfg, push=make_push(rows)), "PM-PRF-03")
    assert [a.entity_key for a in found] == ["BC_BAD"]


def test_im_failure_rate_vs_touchpoint_peers(cfg):
    rows = [{"rule_id": i, "rule_name": f"R{i}", "fulfillment_success": 700 - i, "fulfillment_failures": 300 + i}
            for i in range(30)]
    rows.append({"rule_id": 99, "rule_name": "R99", "fulfillment_success": 100, "fulfillment_failures": 900})
    found = run_one(make_ctx(cfg, im=make_im(rows), snapshot_date=pd.Timestamp("2026-09-20").date()), "IM-FUL-01")
    assert [a.entity_key for a in found] == ["99"] and found[0].severity == "critical"   # ≥ 90 % d'échec


def test_delivery_drop_collapses_consecutive_days_into_one_episode(cfg):
    days = pd.date_range("2026-09-01", periods=20).strftime("%Y-%m-%d")
    rows = []
    for i, d in enumerate(days):
        delivered = 2_000 if 14 <= i <= 16 else 6_000 + 50 * (i % 3)
        rows.append({"date": d, "bc_name": f"BC_{i}", "sent": 10_000, "delivered": delivered})
    push = make_push(rows)
    found = run_one(make_ctx(cfg, push=push), "PM-DLV-02")
    cats = [a for a in found if a.entity_key == "CVM"]
    assert len(cats) == 1 and cats[0].date == days[14] and len(cats[0].details["days"]) == 3
    assert cats[0].severity in ("major", "critical")
