"""Bout en bout sur les vrais fichiers (ignoré s'ils ne sont pas présents)."""

import pytest

from conftest import REAL_FILES
from cvm_monitor.pipeline import process_file
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect

pytestmark = pytest.mark.skipif(len(REAL_FILES) < 2, reason="les deux fichiers .xlsb de septembre sont nécessaires")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    import shutil
    from pathlib import Path

    from cvm_monitor.config import load_config
    root = tmp_path_factory.mktemp("real")
    (root / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "config" / "config.yaml", root / "config" / "config.yaml")
    cfg = load_config(root / "config" / "config.yaml")
    results = [process_file(cfg, f, notify=False, archive=False) for f in REAL_FILES]
    again = process_file(cfg, REAL_FILES[-1], notify=False, archive=False)
    return cfg, connect(cfg.path("db")), results, again


def test_no_rule_errors(db):
    _, _, results, _ = db
    assert all(not r.rule_errors for r in results)


def test_idempotent(db):
    _, _, _, again = db
    assert again.skipped


def test_known_issues_are_found(db):
    _, conn, _, _ = db
    df = repo.anomalies_df(conn, status=["open"])
    msgs = " | ".join(df["message"])
    assert (df["rule_id"] == "CVM-INB-02").any() and "Illimax" in msgs  # échecs d'achat élevés
    assert not df["message"].str.contains("Dummy BC").any()  # BC techniques exclus des règles CVM
    assert not df["rule_id"].isin(["PM-EXE-01", "IM-FUL-01"]).any()  # remplacées par les règles CVM
    assert not df["rule_id"].isin(["PM-DLV-02", "IM-DQ-02"]).any()  # règles désactivées : aucune alerte


def test_frozen_volumes_not_revised(db):
    _, conn, _, _ = db
    df = repo.anomalies_df(conn)
    assert not (df["rule_id"] == "SNP-01").any()  # seules les conversions ont bougé entre les 2 fichiers


def test_critical_count_is_reasonable(db):
    _, conn, _, _ = db
    df = repo.anomalies_df(conn, status=["open"])
    assert (df["severity"] == "critical").sum() <= 20
