"""Règles business : BC / offre qui ne convertit plus, blackout SMS."""

import pandas as pd

from conftest import make_ctx, make_im, make_push, run_one
from cvm_monitor.detect.base import RuleContext


def _bc_history(drop_days=(24, 25, 26), last=26, rate_ok=0.05, rate_low=0.005):
    """BC_A envoie 20 000 SMS par jour du 01/09 au 27/09 ; le Conv% chute les `drop_days`."""
    rows = []
    for i in range(1, 28):
        d = f"2026-09-{i:02d}"
        conv = int(20_000 * (rate_low if i in drop_days else rate_ok))
        rows.append({"date": d, "bc_name": "BC_A", "sent": 20_000, "generated": 20_000, "conversions": conv,
                     "conversion_value": conv * 100.0})
    return rows


def test_bc_stopped_converting_is_quantified(cfg):
    from datetime import date
    snap = date(2026, 9, 30)
    push = make_push(_bc_history(), snap)
    found = run_one(make_ctx(cfg, push=push, snapshot_date=snap), "BIZ-CONV-01")
    assert len(found) == 1
    a = found[0]
    assert a.entity_key == "BC_A" and a.severity == "major"          # 3 jours de suite
    assert a.details["lost_conversions"] > 2_000
    assert a.details["lost_value"] > 0 and "conversions perdues" in a.details["impact"]
    assert a.details["action"]


def test_bc_stable_does_not_alert(cfg):
    from datetime import date
    snap = date(2026, 9, 30)
    push = make_push(_bc_history(drop_days=()), snap)
    assert run_one(make_ctx(cfg, push=push, snapshot_date=snap), "BIZ-CONV-01") == []


def test_immature_days_are_not_judged(cfg):
    from datetime import date
    snap = date(2026, 9, 28)  # J+1 : la chute du 27/09 n'est pas encore jugeable
    push = make_push(_bc_history(drop_days=(27,)), snap)
    assert run_one(make_ctx(cfg, push=push, snapshot_date=snap), "BIZ-CONV-01") == []


def test_offer_stopped_converting(cfg):
    from datetime import date
    snap = date(2026, 9, 28)
    rows = [{"date": f"2026-09-{i:02d}", "offer_id": 7, "offer_name": "Pass Data", "impressions": 20_000,
             "fulfillment_success": 100 if i >= 26 else 2_000} for i in range(1, 29)]
    im = make_im(rows)
    found = run_one(make_ctx(cfg, im=im, snapshot_date=snap), "BIZ-OFR-01")
    assert len(found) == 1 and found[0].entity_key == "7" and found[0].severity in ("major", "critical")
    assert "achats perdus" in found[0].details["impact"]


def test_in_blackout_window(cfg):
    ctx = make_ctx(cfg)
    s = pd.Series(["2026-09-10 18:59:00", "2026-09-10 19:00:00", "2026-09-10 23:30:00",
                   "2026-09-10 06:59:00", "2026-09-10 07:00:00", "2026-09-10 00:00:00", None])
    assert ctx.in_blackout(s).tolist() == [False, True, True, True, False, False, False]
    assert isinstance(ctx, RuleContext)


def test_demoted_rules_are_info_only(cfg):
    push = make_push([{"status": "Paused"}])
    found = run_one(make_ctx(cfg, push), "PM-EXE-03")
    assert found and all(a.severity == "info" for a in found)
