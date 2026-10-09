from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from conftest import make_im, make_push
from cvm_monitor.api import deps
from cvm_monitor.api.main import app
from cvm_monitor.ingest.loader import Snapshot
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect


@pytest.fixture
def client(cfg, monkeypatch):
    rows = [{"bc_name": f"BC_{i}", "campaign_name": f"C{i}", "conversions": 100, "unique_conversions": 100,
             "conversion_value": 1000.0} for i in range(9)]
    rows.append({"bc_name": "BC_LOW", "campaign_name": "CLOW", "conversions": 1, "unique_conversions": 1})
    im = make_im([{"offer_name": f"O{i}", "offer_id": i, "rule_id": i} for i in range(3)])
    conn = connect(cfg.path("db"))
    repo.insert_snapshot(conn, Snapshot(Path("x.xlsb"), "h1", date(2026, 9, 22), make_push(rows), im))
    conn.close()
    monkeypatch.setattr(deps, "_cfg", cfg)
    deps._cache.clear()
    return TestClient(app)


def test_health_and_snapshots(client):
    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get("/api/v1/snapshots").json()) == 1


def test_filter_options_and_overview(client):
    opts = client.get("/api/v1/filters/options", params={"category": "CVM"}).json()
    assert "BC_LOW" in opts["bcs"]
    ov = client.get("/api/v1/overview", params={"bc": "BC_LOW"}).json()
    assert ov["headline"]["sent"]["value"] == 10_000  # un seul broadcast après filtre


def test_value_campaigns_granular(client):
    r = client.get("/api/v1/value/campaigns", params={"level": "bc", "only_underperforming": True})
    # 10 pairs < min_peers (20) : repli statique, donc la liste peut être vide mais l'appel doit réussir
    assert r.status_code == 200
    assert client.get("/api/v1/value/summary").json()["campaigns_total"] == 10


def test_anomaly_status_update_and_rules(client):
    assert client.get("/api/v1/anomalies").json() == []
    assert client.patch("/api/v1/anomalies", json={"ids": [], "status": "ack"}).status_code == 200
    assert client.patch("/api/v1/anomalies", json={"ids": [1], "status": "bogus"}).status_code == 422
    assert any(r["id"] == "PM-PRF-01" for r in client.get("/api/v1/rules").json())


def test_import_rejects_bad_extension(client):
    r = client.post("/api/v1/import", files={"file": ("a.txt", b"x")})
    assert r.status_code == 400


def test_unknown_api_path_is_404_not_spa(client):
    assert client.get("/api/v1/nope").status_code == 404


def test_overview_totals_and_previous_period(client):
    ov = client.get("/api/v1/overview").json()
    assert ov["totals"]["sent"] == 100_000 and ov["previous"] is None
    ov = client.get("/api/v1/overview", params={"date_from": "2026-09-11", "date_to": "2026-09-20"}).json()
    assert ov["previous"]["from"] == "2026-09-01" and ov["previous"]["to"] == "2026-09-10"
    assert ov["previous"]["sent"] == 100_000          # les broadcasts du 10/09 tombent dans la période précédente
    assert ov["totals"]["sent"] == 0


def test_anomalies_summary_empty(client):
    s = client.get("/api/v1/anomalies/summary").json()
    assert s == {"by_severity": [], "by_day": [], "by_rule": []}


def test_concurrent_requests_do_not_trip_sqlite_thread_check(client):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda _: client.get("/api/v1/snapshots").status_code, range(40)))
    assert set(codes) == {200}


def test_overview_with_zero_im_attempts_returns_json_not_500(client):
    """Filtre IM sans aucune tentative : le Failure % est 0/0 (NaN) ; l'API doit répondre null, pas 500."""
    r = client.get("/api/v1/overview", params={"rule": "inexistante"})
    assert r.status_code == 200


def test_nan_values_are_serialised_as_null():
    from cvm_monitor.api.main import _clean
    assert _clean({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.5}}) == {"a": None, "b": [1.0, None], "c": {"d": 2.5}}
