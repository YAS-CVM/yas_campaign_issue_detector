from conftest import make_ctx, make_im, run_one


def test_failing_rule_critical_above_90pct(cfg):
    im = make_im([
        {"rule_id": 1, "rule_name": "Broken", "fulfillment_success": 5, "fulfillment_failures": 995},
        {"rule_id": 2, "rule_name": "Degraded", "fulfillment_success": 4000, "fulfillment_failures": 6000},
        {"rule_id": 5, "rule_name": "Small", "fulfillment_success": 400, "fulfillment_failures": 600},
        {"rule_id": 3, "rule_name": "Healthy", "fulfillment_success": 900, "fulfillment_failures": 100},
        {"rule_id": 4, "rule_name": "Tiny", "fulfillment_success": 0, "fulfillment_failures": 50},
    ])
    found = {a.entity_key: a for a in run_one(make_ctx(cfg, im=im), "IM-FUL-01")}
    assert set(found) == {"1", "2", "5"}
    assert found["1"].severity == "critical"
    assert found["2"].severity == "major"
    assert found["5"].severity == "minor"  # < low_volume échecs


def test_failing_rule_only_looks_at_recent_window(cfg):
    im = make_im([{"date": "2026-09-01", "fulfillment_success": 0, "fulfillment_failures": 5000}])
    assert run_one(make_ctx(cfg, im=im), "IM-FUL-01") == []


def test_impressions_without_any_attempt(cfg):
    im = make_im([
        {"rule_id": 7, "impressions": 50_000, "fulfillment_success": 0, "fulfillment_failures": 0},
        {"rule_id": 8, "impressions": 50_000},
    ])
    assert [a.entity_key for a in run_one(make_ctx(cfg, im=im), "IM-IMP-01")] == ["7"]


def test_touchpoint_without_result(cfg):
    im = make_im([
        {"touchpoint": "YAS APP", "impressions": 40_000, "fulfillment_success": 0, "fulfillment_failures": 0},
        {"touchpoint": "USSD"},
    ])
    assert [a.entity_key for a in run_one(make_ctx(cfg, im=im), "IM-DQ-02")] == ["YAS APP"]


def test_stale_refresh(cfg):
    im = make_im([
        {"rule_id": 1, "last_refresh": "2026-09-23 06:00:00"},
        {"rule_id": 2, "last_refresh": "2026-09-19 12:00:00"},
        {"rule_id": 3, "last_refresh": "2026-09-01 00:00:00", "rule_status": "Completed"},  # inactive : ignorée
    ])
    found = run_one(make_ctx(cfg, im=im), "IM-DQ-03")
    assert len(found) == 1 and found[0].value == 1
