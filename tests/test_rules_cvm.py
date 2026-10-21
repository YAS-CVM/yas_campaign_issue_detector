"""Règles CVM-* : un cas qui déclenche et un cas qui ne déclenche pas, par règle."""

from __future__ import annotations

from datetime import date, timedelta

from conftest import make_ctx, make_im, make_push, run_one

SNAP = date(2026, 9, 22)


def d(n: int) -> str:
    """Date située n jours avant le snapshot."""
    return (SNAP - timedelta(days=n)).isoformat()


def push_rows(spec):
    """spec : liste de (jours_avant, overrides)."""
    return [{"date": d(n), "scheduled_at": f"{d(n)} 09:00:00", **o} for n, o in spec]


def run(cfg, rule, rows):
    return run_one(make_ctx(cfg, push=make_push(rows, SNAP), snapshot_date=SNAP), rule)


def test_push_01_no_longer_converts(cfg):
    rows = push_rows([(12, {}), (11, {}), (10, {}), (9, {}), (8, {"conversions": 0}), (7, {"conversions": 0}), (6, {"conversions": 0})])
    out = run(cfg, "CVM-PUSH-01", rows)
    assert len(out) == 1 and out[0].severity == "critical" and out[0].entity_key == "BC_A"
    assert not run(cfg, "CVM-PUSH-01", rows[:-1])  # seulement 2 envois à zéro


def test_push_01_ignores_dummy_bc(cfg):
    rows = push_rows([(12, {"bc_name": "Dummy BC"}), (8, {"bc_name": "Dummy BC", "conversions": 0}),
                      (7, {"bc_name": "Dummy BC", "conversions": 0}), (6, {"bc_name": "Dummy BC", "conversions": 0})])
    assert not run(cfg, "CVM-PUSH-01", rows)


def test_push_02_zero_targeting(cfg):
    rows = push_rows([(9, {}), (8, {"sent": 0}), (7, {"sent": 0}), (6, {"sent": 0})])
    assert len(run(cfg, "CVM-PUSH-02", rows)) == 1
    assert not run(cfg, "CVM-PUSH-02", rows[:3])


def test_push_03_failed_send(cfg):
    assert len(run(cfg, "CVM-PUSH-03", push_rows([(6, {}), (2, {"status": "Aborted"})]))) == 1
    assert not run(cfg, "CVM-PUSH-03", push_rows([(6, {"status": "Aborted"}), (2, {})]))  # le dernier envoi est sain
    assert not run(cfg, "CVM-PUSH-03", push_rows([(10, {"status": "Aborted"})]))  # trop ancien


def test_push_04_conversion_drop(cfg):
    rows = push_rows([(n, {}) for n in range(14, 8, -1)] + [(n, {"conversions": 40}) for n in (8, 7, 6)])
    out = run(cfg, "CVM-PUSH-04", rows)
    assert len(out) == 1 and out[0].details["drop_pct"] == 60.0
    assert not run(cfg, "CVM-PUSH-04", push_rows([(n, {}) for n in range(14, 5, -1)]))


def test_push_05_delivery_drop_vs_platform(cfg):
    bc_a = [(n, {}) for n in range(14, 8, -1)] + [(n, {"delivered": 4_000}) for n in (8, 7, 6)]
    others = [(n, {"bc_name": "BC_B", "broadcast_name": "B"}) for n in range(14, 5, -1)]
    assert len(run(cfg, "CVM-PUSH-05", push_rows(bc_a + others))) == 1
    # toute la plateforme baisse : pas d'alerte pour le BC
    platform = [(n, {"delivered": 4_000}) for n in (8, 7, 6)]
    same = push_rows(bc_a + [(n, {"bc_name": "BC_B", **({"delivered": 4_000} if n in (8, 7, 6) else {})}) for n in range(14, 5, -1)])
    assert not run(cfg, "CVM-PUSH-05", same + push_rows(platform))


def test_push_06_no_delivery(cfg):
    rows = push_rows([(n, {}) for n in (12, 11, 10, 9)] + [(n, {"delivered": 0}) for n in (8, 7, 6)])
    assert len(run(cfg, "CVM-PUSH-06", rows)) == 1
    assert not run(cfg, "CVM-PUSH-06", rows[:-1])


def test_push_07_never_converted(cfg):
    rows = push_rows([(n, {"conversions": 0}) for n in range(14, 7, -1)])
    assert len(run(cfg, "CVM-PUSH-07", rows)) == 1
    rows[0]["conversions"] = 1
    assert not run(cfg, "CVM-PUSH-07", rows)


def test_push_08_not_better_than_control(cfg):
    rows = push_rows([(n, {"conversions": 5, "cg_conversions": 10}) for n in range(14, 8, -1)])  # 0,05 % vs 1 %
    assert len(run(cfg, "CVM-PUSH-08", rows)) == 1
    assert not run(cfg, "CVM-PUSH-08", push_rows([(n, {}) for n in range(14, 8, -1)]))  # 1 % vs 0,8 %


def test_push_09_stopped_sending(cfg):
    rows = push_rows([(n, {}) for n in range(18, 11, -1)])  # dernier envoi il y a 12 jours
    out = run(cfg, "CVM-PUSH-09", rows)
    assert len(out) == 1 and out[0].severity == "info" and out[0].value == 12
    assert not run(cfg, "CVM-PUSH-09", push_rows([(n, {}) for n in range(18, 0, -1)]))  # envoie toujours


def im_rows(spec):
    return [{"date": d(n), **o} for n, o in spec]


def run_im(cfg, rule, rows):
    return run_one(make_ctx(cfg, im=make_im(rows), snapshot_date=SNAP), rule)


def test_inb_01_no_purchase(cfg):
    rows = im_rows([(n, {"fulfillment_success": 100}) for n in range(14, 9, -1)]
                   + [(n, {"fulfillment_success": 0}) for n in range(9, 0, -1)])
    out = run_im(cfg, "CVM-INB-01", rows)
    assert len(out) == 1 and out[0].severity == "critical"
    rows[-1]["fulfillment_success"] = 1
    assert not run_im(cfg, "CVM-INB-01", rows)


def test_inb_01_watch_when_few_expected(cfg):
    rows = im_rows([(14, {"fulfillment_success": 2, "impressions": 100_000})]
                   + [(n, {"fulfillment_success": 0, "impressions": 1_000}) for n in range(9, 0, -1)])
    assert run_im(cfg, "CVM-INB-01", rows)[0].severity == "minor"


def test_inb_02_high_failures(cfg):
    rows = im_rows([(n, {"fulfillment_success": 100, "fulfillment_failures": 300}) for n in range(6, 0, -1)])
    assert run_im(cfg, "CVM-INB-02", rows)[0].severity == "critical"
    assert not run_im(cfg, "CVM-INB-02", im_rows([(n, {"fulfillment_failures": 5}) for n in range(6, 0, -1)]))


def test_inb_03_purchases_drop(cfg):
    rows = im_rows([(n, {"fulfillment_success": 100}) for n in range(10, 3, -1)]
                   + [(n, {"fulfillment_success": 20}) for n in (3, 2, 1)])
    assert len(run_im(cfg, "CVM-INB-03", rows)) == 1
    assert not run_im(cfg, "CVM-INB-03", im_rows([(n, {"fulfillment_success": 100}) for n in range(10, 0, -1)]))


def test_inb_04_never_purchased(cfg):
    rows = im_rows([(n, {"fulfillment_success": 0, "impressions": 1_000}) for n in range(7, 0, -1)])
    assert len(run_im(cfg, "CVM-INB-04", rows)) == 1
    assert not run_im(cfg, "CVM-INB-04", im_rows([(n, {"fulfillment_success": 1, "impressions": 1_000}) for n in range(7, 0, -1)]))


def test_inb_05_no_longer_displayed_per_rule(cfg):
    rows = im_rows([(n, {}) for n in range(14, 10, -1)]  # règle 1 : s'arrête
                   + [(n, {"rule_id": 2, "rule_name": "Rule B"}) for n in range(14, 0, -1)])  # règle 2 : toujours affichée
    out = run_im(cfg, "CVM-INB-05", rows)
    assert [a.entity_key for a in out] == ["1:1"]
    for r in rows:
        r["rule_status"] = "Completed"
    assert not run_im(cfg, "CVM-INB-05", rows)


def test_campaign_scorecard_without_mature_sends():
    """Aucun envoi mature : tableau vide avec les colonnes habituelles (régression sur la colonne verdict)."""
    from cvm_monitor.analytics.kpi import campaign_scorecard
    out = campaign_scorecard(make_push([{"date": d(1)}], SNAP), "campaign_name", 3)
    assert out.empty and {"verdict", "uplift", "significant"} <= set(out.columns)


def test_state_alert_resolves_then_reopens(cfg):
    """BC récurrent : une seule alerte par (règle, BC) ; résolue quand le phénomène disparaît, rouverte s'il revient."""
    from cvm_monitor.detect.base import Anomaly
    from cvm_monitor.storage import repository as repo
    from cvm_monitor.storage.db import connect
    from test_lifecycle_and_notify import _snapshot

    def mk(day, rule="CVM-PUSH-05"):
        return Anomaly(entity_type="bc_name", entity_key="BC_A", date=day, message="m", severity="major", rule_id=rule)

    assert mk("2026-09-29").fingerprint == mk("2026-10-16").fingerprint
    assert mk("2026-09-29", "PM-EXE-02").fingerprint != mk("2026-10-16", "PM-EXE-02").fingerprint  # règles datées inchangées

    conn = connect(cfg.path("db"))
    rules = {"CVM-PUSH-05"}
    r1 = repo.sync_anomalies(conn, _snapshot(conn, 1, "2026-09-30", "2026-09-30"), [mk("2026-09-29")], rules)
    r2 = repo.sync_anomalies(conn, _snapshot(conn, 2, "2026-10-05", "2026-10-01"), [], rules)  # disparu, hors période de la 1re date
    r3 = repo.sync_anomalies(conn, _snapshot(conn, 3, "2026-10-16", "2026-10-10"), [mk("2026-10-16")], rules)
    assert len(r1.new) == 1 and len(r2.resolved) == 1 and len(r3.reopened) == 1
    assert [tuple(r) for r in conn.execute("SELECT status, first_seen_at, occurrences FROM anomalies")] == [("open", "2026-10-16", 1)]
