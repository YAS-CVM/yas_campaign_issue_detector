from __future__ import annotations

import pytest

from cvm_monitor.notify import email as mail
from cvm_monitor.notify import teams
from cvm_monitor.services import alerts

WEBHOOK = "https://example.invalid/workflows/abc/invoke?sig=SECRET123"


def test_status_never_exposes_secrets(cfg, monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    monkeypatch.setenv("MAIL_TO", "a@b.sn, c@d.sn")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.invalid")
    st = alerts.channel_status(cfg)
    dumped = str(st)
    assert "SECRET123" not in dumped and "hunter2" not in dumped and "sig=" not in dumped
    assert st["teams"]["configured"] and st["teams"]["webhook_host"] == "example.invalid"
    assert st["email"]["configured"] and st["email"]["recipients"] == ["a@b.sn", "c@d.sn"]


def test_unconfigured_channels_report_what_is_missing(cfg):
    st = alerts.channel_status(cfg)
    assert not st["teams"]["configured"] and st["teams"]["missing"] == ["TEAMS_WEBHOOK_URL"]
    assert not st["email"]["configured"] and "MAIL_TO" in st["email"]["missing"]
    assert alerts.send_test(cfg, "teams")["ok"] is False
    assert alerts.send_test(cfg, "email")["ok"] is False


def test_send_test_success(cfg, monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", WEBHOOK)
    sent = {}
    monkeypatch.setattr(teams, "post_card", lambda url, card: sent.update(url=url))
    res = alerts.send_test(cfg, "teams")
    assert res["ok"] and sent["url"] == WEBHOOK

    monkeypatch.setenv("MAIL_TO", "a@b.sn")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setattr(mail, "send_email", lambda *a, **k: sent.update(mail=True))
    assert alerts.send_test(cfg, "email")["ok"] and sent["mail"]


def test_errors_are_returned_and_scrubbed(cfg, monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", WEBHOOK)

    def boom(url, card):
        raise RuntimeError(f"connexion refusée vers {url}")
    monkeypatch.setattr(teams, "post_card", boom)
    res = alerts.send_test(cfg, "teams")
    assert res["ok"] is False and "SECRET123" not in res["message"] and "<masqué>" in res["message"]


@pytest.fixture
def api(cfg, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from cvm_monitor.api import deps, main
    monkeypatch.setattr(deps, "_cfg", cfg)
    main._last_test.clear()
    return TestClient(main.app)


def test_api_status_and_test_endpoints(api, cfg, monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setattr(teams, "post_card", lambda url, card: None)
    assert api.get("/api/v1/settings/alerts").json()["teams"]["configured"] is True
    assert "SECRET123" not in api.get("/api/v1/settings/alerts").text
    r = api.post("/api/v1/settings/alerts/test/teams")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert api.post("/api/v1/settings/alerts/test/teams").status_code == 429   # anti double-clic
    assert api.post("/api/v1/settings/alerts/test/sms").status_code == 422
