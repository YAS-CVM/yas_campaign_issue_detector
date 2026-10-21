"""Règles du flux NEON-dx (FEED-*), PM-EXE-06/07 et correctifs (SNP-02, IM-DQ-03, références d'historique)."""

from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

from conftest import make_ctx, make_im, make_push, run_one
from cvm_monitor.detect import percentiles as pct


def _snaps(dates: list[str], columns: list[dict] | None = None) -> pd.DataFrame:
    df = pd.DataFrame({"id": range(1, len(dates) + 1), "snapshot_date": dates})
    if columns:
        df["columns"] = [json.dumps(c) for c in columns]
    return df


# --------------------------------------------------------------------------- FEED-01

def test_missing_files_episodes_and_month_end(cfg):
    ctx = make_ctx(cfg, snapshot_date=date(2026, 10, 4))
    ctx.snapshots = _snaps(["2026-09-27", "2026-09-28", "2026-10-04"])
    found = run_one(ctx, "FEED-01")
    assert len(found) == 1
    a = found[0]
    assert a.details["days"] == ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03"]
    assert a.details["month_end"] and a.severity == "major"
    # Le fichier suivant revoit le même épisode : même date, donc même empreinte (pas de doublon).
    ctx2 = make_ctx(cfg, snapshot_date=date(2026, 10, 5))
    ctx2.snapshots = _snaps(["2026-09-27", "2026-09-28", "2026-10-04", "2026-10-05"])
    assert [x.date for x in run_one(ctx2, "FEED-01")] == [a.date]


# --------------------------------------------------------------------------- FEED-02

def test_format_change_columns_new_values_and_fill(cfg):
    ctx = make_ctx(cfg, push=make_push([{"status": "Targeting"}, {}]))
    ctx.prev_snapshot_date = date(2026, 9, 21)
    ctx.snapshots = _snaps(["2026-09-21", "2026-09-22"], [{"Data_Push": ["A", "B"], "Data_IM": ["X"]},
                                                         {"Data_Push": ["A", "C"], "Data_IM": ["X"]}])
    ctx.known_values = {"status": {"Completed"}, "category": {"CVM"}, "touchpoint": {"USSD"}, "program": {"NBO_Inbound_Program"}}
    ctx.fill = pd.DataFrame([
        {"snapshot_id": 1, "sheet": "push", "column": "delivered", "fill": 0.9},
        {"snapshot_id": 2, "sheet": "push", "column": "delivered", "fill": 0.0},
        {"snapshot_id": 1, "sheet": "im", "column": "declined", "fill": 0.0},
        {"snapshot_id": 2, "sheet": "im", "column": "declined", "fill": 0.2},
    ])
    cfg.raw["rules"]["FEED-02"]["severity"] = "major"
    found = {a.entity_key: a for a in run_one(ctx, "FEED-02")}
    assert found["Data_Push · colonnes"].details == {"added": ["C"], "removed": ["B"]}
    assert "Status = Targeting" in found
    assert found["Data_Push.delivered"].severity == "major"       # n'est plus alimentée
    assert found["Data_IM.declined"].severity == "info"           # commence à être alimentée


# --------------------------------------------------------------------------- FEED-03

def test_im_fulfillment_not_fed_detected_from_first_file(cfg):
    """Cas réel d'août : fulfillment nul (ou résiduel) pendant des jours malgré les impressions → un seul épisode."""
    rows = []
    for d in range(1, 20):
        day = f"2026-08-{d:02d}"
        fed = d == 19
        residual = 2 if d == 11 else 0
        rows.append({"date": day, "touchpoint": "USSD", "impressions": 800_000,
                     "fulfillment_success": 19_000 if fed else residual, "fulfillment_failures": 9_000 if fed else 0})
        rows.append({"date": day, "touchpoint": "YAS APP", "rule_id": 2, "impressions": 5_000,
                     "fulfillment_success": 0, "fulfillment_failures": 0})  # jamais alimenté : IM-DQ-02, pas FEED-03
    ctx = make_ctx(cfg, im=make_im(rows), snapshot_date=date(2026, 8, 19))
    found = [a for a in run_one(ctx, "FEED-03") if a.entity_type == "touchpoint"]
    assert len(found) == 1
    assert found[0].entity_key == "USSD · fulfillment"
    assert found[0].details["days"][0] == "2026-08-01" and found[0].details["days"][-1] == "2026-08-18"


def test_push_metric_not_fed_on_a_day(cfg):
    push = make_push([{"date": "2026-09-18"}, {"date": "2026-09-19", "delivered": 0}, {"date": "2026-09-20"}])
    found = run_one(make_ctx(cfg, push=push), "FEED-03")
    assert [(a.entity_key, a.details["days"]) for a in found] == [("Data_Push.delivered", ["2026-09-19"])]


# --------------------------------------------------------------------------- FEED-04

def test_month_end_truncation_excludes_mid_month_losses(cfg):
    hist = make_push([
        {"date": "2026-09-30", "conversions": 500, "snapshot_date": "2026-09-30"},   # J+0 au dernier fichier : tronqué
        {"date": "2026-09-29", "conversions": 800, "snapshot_date": "2026-09-30"},   # J+1 : tronqué
        {"date": "2026-09-14", "conversions": 300, "snapshot_date": "2026-09-14"},   # disparu en cours de mois : SNP-02
        {"date": "2026-09-20", "conversions": 900, "snapshot_date": "2026-09-30"},   # mature
    ], snapshot_date=date(2026, 9, 30))
    hist.loc[2, "age_days"] = 0  # âge vu dans le fichier du 14/09
    ctx = make_ctx(cfg, push=make_push([{"date": "2026-10-04"}], date(2026, 10, 4)), snapshot_date=date(2026, 10, 4),
                   prev_push=hist, hist_push=hist)
    ctx.prev_snapshot_date = date(2026, 9, 30)
    ctx.versions = pd.DataFrame({"broadcast_id": [1, 1, 2, 2], "age_days": [0, 10, 1, 10], "conversions": [50, 100, 80, 100]})
    found = run_one(ctx, "FEED-04")
    assert len(found) == 1
    a = found[0]
    assert a.value == 2 and sorted(a.details["days"]) == ["2026-09-29", "2026-09-30"]
    assert a.details["estimated_missing"] > 0


def test_no_truncation_alert_within_a_month(cfg):
    ctx = make_ctx(cfg, prev_push=make_push([{}]))
    ctx.prev_snapshot_date = date(2026, 9, 21)
    assert run_one(ctx, "FEED-04") == []


# --------------------------------------------------------------------------- FEED-06

def test_slow_maturation(cfg):
    versions = pd.DataFrame({"broadcast_id": [1, 1, 1], "age_days": [0, 1, 10], "conversions": [50, 75, 100]})
    prev = make_push([{"date": "2026-09-21", "conversions": 2_000}], date(2026, 9, 21))
    cur_slow = make_push([{"date": "2026-09-21", "conversions": 2_050}], date(2026, 9, 22))
    prev["broadcast_id"] = cur_slow["broadcast_id"] = 7
    ctx = make_ctx(cfg, push=cur_slow, prev_push=prev)
    ctx.versions = versions
    found = run_one(ctx, "FEED-06")
    assert len(found) == 1 and found[0].details["expected_growth"] > 0.4
    cur_ok = cur_slow.assign(conversions=2_900)
    ctx.push = cur_ok
    assert run_one(ctx, "FEED-06") == []


# --------------------------------------------------------------------------- exécution

def test_blackout_expired_never_sent(cfg):
    push = make_push([{"status": "Blackout Expired", "generated": 500_000, "sent": 0},
                      {"status": "Blackout Expired", "generated": 500_000, "sent": 400_000},
                      {"status": "Completed", "generated": 500_000, "sent": 0}])
    found = run_one(make_ctx(cfg, push=push), "PM-EXE-06")
    assert len(found) == 1 and found[0].volume == 500_000


def test_transient_status_lasting(cfg):
    push = make_push([{"status": "Targeting", "date": "2026-09-20"}, {"status": "Render Scheduled", "date": "2026-09-22"},
                      {"status": "Delivering", "date": "2026-09-20"}])
    found = run_one(make_ctx(cfg, push=push), "PM-EXE-07")
    assert [a.details["status"] for a in found] == ["Targeting"]  # Render Scheduled est à J+0


# --------------------------------------------------------------------------- correctifs

def test_snp02_stays_open_while_missing_and_ignores_month_change(cfg):
    hist = make_push([{"date": "2026-09-10", "snapshot_date": "2026-09-14"},
                      {"date": "2026-09-11", "snapshot_date": "2026-09-22"},
                      {"date": "2026-08-30", "snapshot_date": "2026-08-31"},
                      {"date": "2026-09-01", "snapshot_date": "2026-09-22"}])
    cur = hist.iloc[[1, 3]].copy()  # le fichier du 22/09 couvre le mois depuis le 1er
    found = run_one(make_ctx(cfg, push=cur, hist_push=hist), "SNP-02")
    assert len(found) == 1
    assert found[0].details["broadcast_ids"] == [int(hist.iloc[0]["broadcast_id"])]
    assert found[0].details["last_seen"] == "2026-09-14"  # août n'est pas couvert : pas une disparition


def test_stale_refresh_uses_hours(cfg):
    im = make_im([{"rule_id": 1, "last_refresh": "2026-09-22 03:10:00"},          # nuit suivante : à jour
                  {"rule_id": 2, "last_refresh": "2026-09-20 03:10:00"},          # 74 h : en retard
                  {"rule_id": 3, "last_refresh": "2025-01-01 00:00:00", "rule_status": "Inactive"}])
    found = run_one(make_ctx(cfg, im=im), "IM-DQ-03")
    assert len(found) == 1 and found[0].details["rule_ids"] == [2]


def test_history_reference_excludes_unfed_days_but_still_judges_them():
    idx = [f"2026-09-{d:02d}" for d in range(1, 21)]
    s = pd.Series([0.5] * 20, index=idx)
    s.iloc[5:10] = 0.0          # jours non alimentés
    exclude = pd.Series(s == 0, index=idx)
    pc = {**pct.DEFAULTS, "min_history_points": 5}
    res = pct.history_outliers(s, pct.LOW, pc, min_abs_gap=0.1, exclude=exclude)
    assert res.loc["2026-09-20", "p_low"] == 0.5          # la référence ignore les zéros
    assert res.loc["2026-09-08", "flag"]                  # un jour non alimenté reste jugé


def test_impressions_drop_accounts_for_weekday(cfg):
    days = pd.date_range("2026-07-01", "2026-09-27")
    rows = [{"date": d.strftime("%Y-%m-%d"), "impressions": 300_000 if d.dayofweek == 6 else 800_000} for d in days]
    hist = make_im(rows)
    current = hist[hist["date"] >= "2026-09-01"]
    ctx = make_ctx(cfg, im=current, hist_im=hist, snapshot_date=date(2026, 9, 27))
    assert run_one(ctx, "IM-IMP-02") == []  # les dimanches calmes ne sont pas des chutes


def test_feed_check_deadline(cfg):
    from cvm_monitor.ingest.loader import Snapshot
    from cvm_monitor.notify import feed_check
    from cvm_monitor.storage import repository as repo
    from cvm_monitor.storage.db import connect
    from pathlib import Path
    conn = connect(cfg.path("db"))
    repo.insert_snapshot(conn, Snapshot(Path("f.xlsb"), "h", date(2026, 10, 6), make_push([{"date": "2026-10-06"}]), make_im([{"date": "2026-10-06"}]),
                                        columns={"Data_Push": ["A"]}))
    conn.commit()
    assert feed_check.check(cfg, conn, datetime(2026, 10, 7, 9, 0)) is None          # avant l'heure limite
    assert feed_check.check(cfg, conn, datetime(2026, 10, 7, 11, 0)) is None         # « till 06 » reçu
    missing = feed_check.check(cfg, conn, datetime(2026, 10, 8, 11, 0))
    assert missing and missing.expected == date(2026, 10, 7) and missing.lag_days == 1
    stored = conn.execute("SELECT columns FROM snapshots").fetchone()[0]
    assert json.loads(stored) == {"Data_Push": ["A"]}
    conn.close()
