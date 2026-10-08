"""Cycle de vie des anomalies (anti-doublon, résolution) et envoi des alertes."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cvm_monitor.detect.base import Anomaly
from cvm_monitor.notify import dispatcher
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect


def _snapshot(conn, sid, day, dmin="2026-09-01", dmax=None):
    conn.execute("INSERT INTO snapshots(id, file_name, file_hash, snapshot_date, ingested_at, date_min, date_max)"
                 " VALUES (?,?,?,?,?,?,?)", (sid, f"f{sid}.xlsb", f"h{sid}", day, day, dmin, dmax or day))
    return repo.get_snapshot(conn, sid)


def _a(key, severity="major", day="2026-09-10", rule="PM-EXE-02"):
    return Anomaly(entity_type="broadcast", entity_key=key, date=day, message=f"msg {key}",
                   severity=severity, rule_id=rule, rule_name="Test", scope="push", volume=10)


@pytest.fixture
def conn(cfg):
    return connect(cfg.path("db"))


def test_new_ongoing_resolved_reopened_escalated(conn):
    s1 = _snapshot(conn, 1, "2026-09-20")
    r1 = repo.sync_anomalies(conn, s1, [_a("A"), _a("B")], {"PM-EXE-02"})
    assert len(r1.new) == 2

    s2 = _snapshot(conn, 2, "2026-09-21")
    r2 = repo.sync_anomalies(conn, s2, [_a("A")], {"PM-EXE-02"})
    assert r2.new == [] and len(r2.ongoing) == 1 and len(r2.resolved) == 1

    s3 = _snapshot(conn, 3, "2026-09-22")
    r3 = repo.sync_anomalies(conn, s3, [_a("A", "critical"), _a("B")], {"PM-EXE-02"})
    assert len(r3.escalated) == 1 and len(r3.reopened) == 1
    assert len(r3.to_notify) == 2


def test_ack_survives_until_escalation_and_mute_is_permanent(conn):
    s1 = _snapshot(conn, 1, "2026-09-20")
    r = repo.sync_anomalies(conn, s1, [_a("A"), _a("M")], {"PM-EXE-02"})
    repo.set_status(conn, [r.new[0]], "ack", "moi", "ticket 42")
    repo.set_status(conn, [r.new[1]], "muted")
    s2 = _snapshot(conn, 2, "2026-09-21")
    r2 = repo.sync_anomalies(conn, s2, [_a("A"), _a("M", "critical")], {"PM-EXE-02"})
    assert r2.to_notify == []
    df = repo.anomalies_df(conn).set_index("entity_key")
    assert df.loc["A", "status"] == "ack" and df.loc["A", "ack_note"] == "ticket 42"
    assert df.loc["M", "status"] == "muted"


def test_rules_not_executed_do_not_resolve(conn):
    s1 = _snapshot(conn, 1, "2026-09-20")
    repo.sync_anomalies(conn, s1, [_a("A", rule="SNP-01")], {"SNP-01"})
    s2 = _snapshot(conn, 2, "2026-09-21")
    r = repo.sync_anomalies(conn, s2, [], {"PM-EXE-02"})  # SNP-01 non exécutée
    assert r.resolved == []


def test_anomaly_outside_period_not_resolved(conn):
    s1 = _snapshot(conn, 1, "2026-09-30", dmin="2026-09-01")
    repo.sync_anomalies(conn, s1, [_a("A", day="2026-09-15")], {"PM-EXE-02"})
    s2 = _snapshot(conn, 2, "2026-10-01", dmin="2026-10-01")  # nouveau mois : septembre absent du fichier
    r = repo.sync_anomalies(conn, s2, [], {"PM-EXE-02"})
    assert r.resolved == []


class _Hook(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Hook.received.append(json.loads(body))
        self.send_response(202)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_dispatch_posts_teams_card_once(cfg, conn, monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", f"http://127.0.0.1:{server.server_port}/hook")
    _Hook.received.clear()

    s1 = _snapshot(conn, 1, "2026-09-20")
    r1 = repo.sync_anomalies(conn, s1, [_a("A", "critical"), _a("B", "minor")], {"PM-EXE-02"})
    out = dispatcher.dispatch(cfg, conn, s1, r1)
    assert out["teams"].startswith("envoyé (1")  # la mineure n'est pas postée sur Teams
    card = _Hook.received[0]["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard" and "msg A" in json.dumps(card)

    s2 = _snapshot(conn, 2, "2026-09-21")
    r2 = repo.sync_anomalies(conn, s2, [_a("A", "critical"), _a("B", "minor")], {"PM-EXE-02"})
    out2 = dispatcher.dispatch(cfg, conn, s2, r2)
    assert out2["teams"] == "rien à signaler"  # déjà notifiée, pas de doublon
    server.shutdown()


def test_dispatch_email_digest(cfg, conn, monkeypatch):
    monkeypatch.setenv("MAIL_TO", "a@example.com, b@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MAIL_FROM", "bot@example.com")
    sent = {}
    monkeypatch.setattr(dispatcher.mail, "send_email",
                        lambda cfg, subject, html, text, attachments=None: sent.update(subject=subject, html=html))
    s1 = _snapshot(conn, 1, "2026-09-20")
    r1 = repo.sync_anomalies(conn, s1, [_a("A", "critical")], {"PM-EXE-02"})
    out = dispatcher.dispatch(cfg, conn, s1, r1)
    assert out["email"].startswith("envoyé à a@example.com")
    assert "1 critique(s)" in sent["subject"]
    assert "msg A" in sent["html"]
    assert out["teams"].startswith("non configuré")
