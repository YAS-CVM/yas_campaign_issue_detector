import pandas as pd

from conftest import make_push
from cvm_monitor.services import timing


def _rows():
    """BC_A est envoyé le lundi (10h) et le mercredi (10h) : le mercredi convertit 2x mieux ; un envoi à 20h (blackout)."""
    rows = []
    for week in range(4):
        for day, rate in ((7, 0.01), (9, 0.02)):  # lundi 07/09, mercredi 09/09 (+ 7 j par semaine)
            d = pd.Timestamp("2026-09-01") + pd.Timedelta(days=day - 1 + 7 * week - 7)
            rows.append({"date": d.strftime("%Y-%m-%d"), "scheduled_at": f"{d:%Y-%m-%d} 10:00:00", "bc_name": "BC_A",
                         "sent": 50_000, "conversions": int(50_000 * rate)})
    rows.append({"date": "2026-09-02", "scheduled_at": "2026-09-02 20:15:00", "bc_name": "BC_A", "sent": 50_000, "conversions": 500})
    return rows


def test_best_weekday_is_relative_to_bc_norm_and_blackout_hours_are_excluded():
    df = timing.scope(make_push(_rows()), maturity_days=3)
    res = timing.best_times(df, blackout={"start": "19:00", "end": "07:00"}, min_sent=10_000)
    assert res["best_weekday"]["label"] == "mer."
    assert res["best_weekday"]["index"] > 1.2
    assert [r["key"] for r in res["hour"]] == [10]           # 20 h exclu du classement
    assert 20 in res["blackout"] and 10 not in res["blackout"]


def test_midnight_flows_are_not_a_chosen_slot():
    df = timing.scope(make_push([{"scheduled_at": "2026-09-10 00:00:00"}]), maturity_days=3)
    assert df["hour"].tolist() == [-1]
    assert timing.best_times(df)["hour"] == []


def test_declining_bc_is_quantified():
    rows = [{"date": f"2026-09-{i:02d}", "bc_name": "BC_A", "sent": 10_000, "conversions": 100 if i <= 8 else 40}
            for i in range(1, 15 + 1)]
    df = timing.scope(make_push(rows), maturity_days=3)
    res = timing.bc_trends(df, recent_days=7, base_days=7, min_sent=1_000, min_lost=10)
    assert res["declining"] and res["declining"][0]["bc_name"] == "BC_A"
    assert res["declining"][0]["lost_conversions"] > 100
