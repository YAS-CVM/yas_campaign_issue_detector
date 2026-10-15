from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from conftest import make_im, make_push
from cvm_monitor.api import deps
from cvm_monitor.api import main as api
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
    # Régénération synchrone : les tests vérifient le site juste après l'écriture.
    monkeypatch.setattr(api, "rebuild_site_async", lambda c: api.pipeline.rebuild_site(c))
    return TestClient(api.app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_site_is_generated_on_first_request_and_served_without_api_reads(client, cfg):
    r = client.get("/")
    assert r.status_code == 200 and 'id="payload"' in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert (cfg.root / "site" / "index.html").exists()
    asset = next((cfg.root / "site" / "assets").glob("core.*.js")).name
    a = client.get(f"/assets/{asset}")
    assert a.status_code == 200 and "immutable" in a.headers["cache-control"]
    assert client.get("/settings.html").status_code == 200


def test_read_endpoints_are_gone(client):
    for path in ("/api/v1/overview", "/api/v1/snapshots", "/api/v1/anomalies"):
        assert client.get(path).status_code in (404, 405)


def test_anomaly_status_update_rebuilds_site(client, cfg):
    conn = connect(cfg.path("db"))
    conn.execute("INSERT INTO anomalies(fingerprint, rule_id, severity, status, date) VALUES ('f1','PM-EXE-02','major','open','2026-09-20')")
    conn.commit()
    conn.close()
    assert client.patch("/api/v1/anomalies", json={"ids": [], "status": "ack"}).status_code == 400
    assert client.patch("/api/v1/anomalies", json={"ids": [1], "status": "bogus"}).status_code == 422
    r = client.patch("/api/v1/anomalies", json={"ids": [1], "status": "ack", "by": "qa", "note": "vu"})
    assert r.json()["updated"] == 1 and r.json()["at"]
    html = (cfg.root / "site" / "index.html").read_text(encoding="utf-8")
    assert '"status":"ack"' in html and '"ack_by":"qa"' in html


def test_import_rejects_bad_extension(client):
    r = client.post("/api/v1/import", files={"file": ("a.txt", b"x")})
    assert r.status_code == 400


def test_alert_settings_expose_no_secret(client, monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.webhook.office.com/x?sig=SECRET123")
    body = client.get("/api/v1/settings/alerts").text
    assert "SECRET123" not in body and "example.webhook.office.com" in body


def test_nan_values_are_serialised_as_null():
    assert api._clean({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.5}}) == {"a": None, "b": [1.0, None], "c": {"d": 2.5}}
