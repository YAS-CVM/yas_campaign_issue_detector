from datetime import date

import pandas as pd
import pytest

from cvm_monitor.ingest import loader, schema


@pytest.mark.parametrize("name,expected", [
    ("Yas_Senegal_Daily_Dashboard_till_22_Sep_2026.xlsb", date(2026, 9, 22)),
    ("Yas_Senegal_Daily_Dashboard_till_01_Oct_2026.xlsb", date(2026, 10, 1)),
    ("Yas_Senegal_Daily_Dashboard_till_5_mai_2026 (1).xlsb", date(2026, 5, 5)),
    ("export.xlsb", None),
    ("till_31_Feb_2026.xlsb", None),
])
def test_snapshot_date_from_name(name, expected):
    assert loader.snapshot_date_from_name(name) == expected


def test_excel_serial_to_iso():
    out = loader.excel_serial_to_iso(pd.Series([46266, 46287.0, None]))
    assert out.tolist()[:2] == ["2026-09-01", "2026-09-22"]
    assert pd.isna(out.iloc[2])


def _raw_push(**over):
    row = {c: 0 for c in schema.PUSH_COLUMNS}
    row.update({"Scheduled Date": 46266, "Scheduled Date.1": "2026-09-01 16:20:00 GMT", "Broadcast ID": 1,
                "BC Name": " BC ", "Campaign Name": "C", "Campaign Category": "CVM", "Status": "Completed",
                "Sent": 100, "Acknowledged %": 99.5, "Is Seeding": "Yes", "Value(Total_Con_Val)": None})
    row.update(over)
    return pd.DataFrame([row, {c: None for c in row}])  # + une ligne vide


def test_clean_push_types_and_units():
    df = loader.clean_push(_raw_push())
    assert len(df) == 1  # ligne vide retirée
    r = df.iloc[0]
    assert r["date"] == "2026-09-01"
    assert r["scheduled_at"] == "2026-09-01 16:20:00"
    assert r["bc_name"] == "BC"
    assert r["ack_rate"] == pytest.approx(0.995)
    assert bool(r["is_seeding"]) is True
    assert df["sent"].dtype == "int64"


def test_clean_push_missing_column_raises():
    with pytest.raises(schema.SchemaError, match="Sent"):
        loader.clean_push(_raw_push().drop(columns=["Sent"]))


@pytest.mark.skipif(not list(__import__("conftest").REAL_FILES), reason="fichiers réels absents")
def test_load_real_snapshot():
    from conftest import REAL_FILES
    snap = loader.load_snapshot(REAL_FILES[-1])
    assert snap.snapshot_date == loader.snapshot_date_from_name(REAL_FILES[-1].name)
    assert len(snap.push) > 0 and len(snap.im) > 0
    assert snap.push["broadcast_id"].is_unique
    assert (snap.push["age_days"] >= 0).all()
