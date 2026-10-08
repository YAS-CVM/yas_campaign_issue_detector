import math

import numpy as np
import pandas as pd
import pytest

from cvm_monitor.analytics.maturity import maturity_curve, nowcast
from cvm_monitor.analytics.uplift import two_proportion_test
from cvm_monitor.detect.baseline import robust_zscores


def test_robust_z_flags_outlier_only_with_enough_history():
    s = pd.Series([0.50, 0.52, 0.49, 0.51, 0.50, 0.48, 0.20], index=[f"d{i}" for i in range(7)])
    z = robust_zscores(s, window=14, min_points=5)
    assert z["z"].iloc[:5].isna().all()
    assert z.loc["d6", "z"] < -3.5
    assert abs(z.loc["d5", "z"]) < 3.5


def test_robust_z_constant_series_has_floor():
    s = pd.Series([100.0] * 6 + [104.0])
    z = robust_zscores(s, min_points=5)
    assert np.isfinite(z["z"].iloc[-1]) and z["z"].iloc[-1] < 3.5  # +4 % n'est pas une anomalie


def test_two_proportion_test():
    res = two_proportion_test(1_000, 100_000, 300, 20_000)
    assert res.uplift == pytest.approx(0.01 - 0.015)
    assert res.significant and res.p_value < 0.001
    assert res.ci_low < res.uplift < res.ci_high
    assert two_proportion_test(10, 0, 1, 10) is None


def test_two_proportion_test_not_significant():
    res = two_proportion_test(50, 5_000, 9, 1_000)
    assert not res.significant


def test_maturity_curve_and_nowcast():
    versions = pd.DataFrame([
        {"broadcast_id": 1, "age_days": 0, "conversions": 30},
        {"broadcast_id": 1, "age_days": 20, "conversions": 100},
        {"broadcast_id": 2, "age_days": 0, "conversions": 20},
        {"broadcast_id": 2, "age_days": 20, "conversions": 100},
    ])
    curve = maturity_curve(versions, reference_age=14)
    assert curve.loc[curve["age_days"] == 0, "completion"].item() == pytest.approx(0.25)
    assert curve["completion"].iloc[-1] == 1.0
    push = pd.DataFrame([{"date": "2026-09-22", "conversions": 50, "age_days": 0},
                         {"date": "2026-09-01", "conversions": 200, "age_days": 21}])
    nc = nowcast(push, curve).set_index("date")
    assert nc.loc["2026-09-22", "expected_final"] == pytest.approx(200)
    assert nc.loc["2026-09-01", "expected_final"] == pytest.approx(200)
    assert math.isclose(nc.loc["2026-09-01", "completion"], 1.0)
