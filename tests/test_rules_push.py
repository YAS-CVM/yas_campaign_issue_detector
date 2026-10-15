import pandas as pd

from conftest import make_ctx, make_push, run_one


def test_stuck_delivering_grouped_by_bc(cfg):
    push = make_push([
        {"bc_name": "Flow_X", "status": "Delivering", "date": "2026-09-19", "generated": 600_000, "sent": 0},
        {"bc_name": "Flow_X", "status": "Delivering", "date": "2026-09-20", "generated": 600_000, "sent": 0},
        {"bc_name": "Today", "status": "Delivering", "date": "2026-09-22"},  # âge 0 : normal
    ])
    found = run_one(make_ctx(cfg, push), "PM-EXE-01")
    assert len(found) == 1
    a = found[0]
    assert a.entity_key == "Flow_X" and a.value == 2 and a.date == "2026-09-19"
    assert a.severity == "critical"


def test_aborted_severity_scales_with_volume(cfg):
    push = make_push([
        {"status": "Aborted", "generated": 0, "sent": 1},
        {"status": "Aborted", "generated": 2_000_000, "sent": 100_000},
        {"status": "Completed"},
    ])
    found = sorted(run_one(make_ctx(cfg, push), "PM-EXE-02"), key=lambda a: a.volume)
    assert [a.severity for a in found] == ["critical"]  # sous min_volume : pas une alerte business


def test_aborted_in_sms_blackout_is_expected(cfg):
    push = make_push([
        {"status": "Aborted", "generated": 200_000, "sent": 100_000, "scheduled_at": "2026-09-10 20:30:00"},
        {"status": "Aborted", "generated": 200_000, "sent": 100_000, "scheduled_at": "2026-09-10 10:30:00"},
        {"status": "Aborted", "generated": 200_000, "sent": 100_000, "scheduled_at": "2026-09-10 00:00:00"},  # flow
    ])
    found = run_one(make_ctx(cfg, push), "PM-EXE-02")
    assert len(found) == 2
    assert {a.entity_key for a in found} == {"1001", "1002"}


def test_generated_not_sent_skips_statuses_covered_elsewhere(cfg):
    push = make_push([
        {"sent": 0, "status": "Completed", "generated": 5000},
        {"sent": 0, "status": "Aborted", "generated": 5000},
        {"sent": 0, "status": "Blackout Expired", "generated": 5000},
    ])
    found = run_one(make_ctx(cfg, push), "PM-EXE-05")
    assert len(found) == 1


def test_zero_delivery_grouped_and_excludes_dummy(cfg):
    push = make_push([
        {"bc_name": "Info_A", "delivered": 0, "date": "2026-09-10"},
        {"bc_name": "Info_A", "delivered": 0, "date": "2026-09-12"},
        {"bc_name": "Flow_Dummy BC to Start", "delivered": 0},
        {"bc_name": "OK", "delivered": 5000},
    ])
    found = run_one(make_ctx(cfg, push), "PM-DLV-01")
    assert [a.entity_key for a in found] == ["Info_A"]
    assert found[0].volume == 20_000


def test_delivery_drop_uses_history_baseline(cfg):
    days = pd.date_range("2026-09-01", "2026-09-15").strftime("%Y-%m-%d")
    rows = [{"date": d, "category": "Informative", "sent": 100_000, "delivered": 60_000 + (i % 3) * 1000}
            for i, d in enumerate(days)]
    rows.append({"date": "2026-09-16", "category": "Informative", "sent": 100_000, "delivered": 15_000})
    push = make_push(rows)
    found = run_one(make_ctx(cfg, push), "PM-DLV-02")
    assert {a.date for a in found} == {"2026-09-16"}
    assert {a.entity_key for a in found} == {"Informative", "Toutes catégories"}


def test_no_conversion_respects_maturity_category_and_seeding(cfg):
    push = make_push([
        {"bc_name": "Mature_zero", "conversions": 0, "date": "2026-09-10"},
        {"bc_name": "Recent_zero", "conversions": 0, "date": "2026-09-21"},          # trop récent
        {"bc_name": "Info_zero", "conversions": 0, "category": "Informative"},        # pas d'objectif
        {"bc_name": "Seed_zero", "conversions": 0, "is_seeding": True},              # offre gratuite
        {"bc_name": "Converts", "conversions": 10},
    ])
    found = run_one(make_ctx(cfg, push), "PM-PRF-01")
    assert [a.entity_key for a in found] == ["Mature_zero"]


def test_negative_uplift_needs_significance(cfg):
    push = make_push([
        {"bc_name": "Bad", "sent": 200_000, "unique_conversions": 1_000, "cg_size": 20_000, "cg_conversions": 300},
        {"bc_name": "Noise", "sent": 10_000, "unique_conversions": 100, "cg_size": 3_000, "cg_conversions": 33},
        {"bc_name": "Good", "sent": 200_000, "unique_conversions": 4_000, "cg_size": 20_000, "cg_conversions": 200},
    ])
    found = run_one(make_ctx(cfg, push), "PM-PRF-02")
    assert [a.entity_key for a in found] == ["Bad"]


def test_sent_greater_than_generated_ignores_zero_generated(cfg):
    push = make_push([{"generated": 0, "sent": 500}, {"bc_name": "X", "generated": 100, "sent": 500}])
    found = run_one(make_ctx(cfg, push), "PM-DQ-01")
    assert [a.entity_key for a in found] == ["X"]


def test_missing_day(cfg):
    push = make_push([{"date": "2026-09-20"}, {"date": "2026-09-22"}])
    from conftest import make_im
    im = make_im([{"date": d} for d in ("2026-09-20", "2026-09-21", "2026-09-22")])
    found = run_one(make_ctx(cfg, push, im), "PM-DQ-06")
    assert [(a.entity_key, a.date) for a in found] == [("Data_Push", "2026-09-21")]


def test_snapshot_revision_detected(cfg):
    prev = make_push([{"sent": 1000, "conversions": 10}, {"sent": 500}])
    cur = prev.copy()
    cur.loc[0, "sent"] = 1200          # volumétrie figée modifiée -> anomalie
    cur.loc[1, "conversions"] = 150    # conversions en hausse -> normal
    found = run_one(make_ctx(cfg, cur, prev_push=prev), "SNP-01")
    assert len(found) == 1 and "sent" in found[0].details
