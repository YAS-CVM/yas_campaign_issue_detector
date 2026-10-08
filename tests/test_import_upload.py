"""Import d'un fichier depuis l'interface web."""

import pytest

from conftest import REAL_FILES
from cvm_monitor.ingest.schema import SchemaError
from cvm_monitor.pipeline import import_upload
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect


def test_rejects_non_xlsb(cfg):
    with pytest.raises(ValueError):
        import_upload(cfg, "rapport.xlsx", b"x", notify=False)


def test_invalid_file_leaves_nothing_behind(cfg):
    with pytest.raises(Exception):
        import_upload(cfg, "Yas_Senegal_Daily_Dashboard_till_22_Sep_2026.xlsb", b"pas un classeur", notify=False)
    assert not list((cfg.path("db").parent / "uploads").glob("*"))
    assert not list(cfg.path("archive").glob("*.xlsb"))
    assert not list(cfg.path("inbox").glob("*.xlsb"))


@pytest.mark.skipif(not REAL_FILES, reason="fichier réel absent")
def test_upload_processes_archives_and_dedups(cfg):
    data = REAL_FILES[-1].read_bytes()
    r = import_upload(cfg, "../../" + REAL_FILES[-1].name, data, notify=False)  # chemin ignoré
    assert not r.skipped and r.detected > 0
    assert [p.name for p in cfg.path("archive").glob("*.xlsb")] == [REAL_FILES[-1].name]
    assert len(repo.list_snapshots(connect(cfg.path("db")))) == 1

    again = import_upload(cfg, REAL_FILES[-1].name, data, notify=False)
    assert again.skipped and "déjà importé" in again.reason
    assert len(list(cfg.path("archive").glob("*.xlsb"))) == 1  # pas de copie en double
