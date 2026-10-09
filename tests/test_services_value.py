from __future__ import annotations

from cvm_monitor.detect import percentiles as pcs
from cvm_monitor.services import filters as flt
from cvm_monitor.services import value

from conftest import make_im, make_push

PC = {**pcs.DEFAULTS, "min_peers": 5}


def _push_rows():
    rows = [{"bc_name": f"BC_{i}", "campaign_name": f"C{i}", "conversions": 100, "unique_conversions": 100,
             "conversion_value": 1000.0, "date": "2026-09-10"} for i in range(9)]
    rows.append({"bc_name": "BC_LOW", "campaign_name": "CLOW", "conversions": 1, "unique_conversions": 1,
                 "conversion_value": 10.0, "date": "2026-09-10"})
    return rows


def test_campaigns_flags_low_converter_and_estimates_gap():
    out = value.campaigns(make_push(_push_rows()), PC, level="bc")
    flagged = out[out["underperforming"]]
    assert list(flagged["bc_name"]) == ["BC_LOW"]
    assert flagged.iloc[0]["missing"] > 0
    assert flagged.iloc[0]["missing_value"] > 0


def test_campaigns_excludes_informative_and_seeding():
    rows = _push_rows() + [{"bc_name": "INFO", "category": "Informative", "conversions": 0, "unique_conversions": 0},
                           {"bc_name": "SEED", "is_seeding": True, "conversions": 0, "unique_conversions": 0}]
    out = value.campaigns(make_push(rows), PC, level="bc")
    assert not {"INFO", "SEED"} & set(out["bc_name"])


def test_offers_flags_low_take_rate():
    rows = [{"offer_name": f"O{i}", "offer_id": i, "rule_id": i, "fulfillment_success": 500} for i in range(9)]
    rows.append({"offer_name": "O_LOW", "offer_id": 99, "rule_id": 99, "fulfillment_success": 0})
    out = value.offers(make_im(rows), PC, level="offer")
    assert list(out[out["underperforming"]]["offer_name"]) == ["O_LOW"]


def test_summary_counts():
    camp = value.campaigns(make_push(_push_rows()), PC, level="bc")
    s = value.summary(camp, value.offers(make_im([{}]), PC))
    assert s["campaigns_underperforming"] == 1


def test_filters_cascade_options():
    push = make_push([{"category": "CVM", "bc_name": "A"}, {"category": "Upsell Campaign", "bc_name": "B"}])
    opts = flt.options(push, make_im([{}]), flt.Filters(categories=["CVM"]))
    assert opts["bcs"] == ["A"]                             # filtré par la catégorie choisie
    assert set(opts["categories"]) == {"CVM", "Upsell Campaign"}  # sa propre dimension reste complète
    assert len(flt.apply_push(push, flt.Filters(categories=["CVM"]))) == 1


def test_small_population_still_estimates_missing():
    """Moins de pairs que min_peers : repli statique, mais le manque à gagner reste chiffré (médiane globale)."""
    few = {**pcs.DEFAULTS, "min_peers": 50}
    out = value.campaigns(make_push(_push_rows()), few, level="bc")
    low = out[out["bc_name"] == "BC_LOW"].iloc[0]
    assert low["mode"] == "static" and low["underperforming"]
    assert low["missing"] > 0


def test_missing_only_counted_for_flagged_entities():
    out = value.campaigns(make_push(_push_rows()), PC, level="bc")
    assert (out.loc[~out["underperforming"], "missing"] == 0).all()
    assert out.loc[out["underperforming"], "missing"].gt(0).all()
