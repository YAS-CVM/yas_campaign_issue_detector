"""Site statique : données embarquées complètes, valides, sans secret ; formules JS identiques à analytics/kpi.py."""

from __future__ import annotations

import gzip
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from conftest import make_im, make_push
from cvm_monitor.analytics import kpi
from cvm_monitor.analytics.maturity import maturity_curves
from cvm_monitor.ingest.loader import Snapshot
from cvm_monitor.pipeline import detect_snapshot
from cvm_monitor.site.build import STATIC, build_site
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect

PAYLOAD_RE = re.compile(r'<script type="application/json" id="payload">(.*?)</script>', re.S)


def _push_rows(day: str, n: int = 25, conv: int = 100) -> list[dict]:
    cats = ["CVM", "Upsell Campaign", "Informative", "UAT"]
    return [{"date": day, "broadcast_id": hash((day, i)) % 10_000_000, "bc_name": f"BC_{i % 7}", "campaign_name": f"C{i % 3}",
             "category": cats[i % 4], "sent": 10_000 + 37 * i, "delivered": 4_000 + 11 * i, "acknowledged": 9_500,
             "conversions": conv + i, "unique_conversions": conv + i, "cg_conversions": 5 + i % 4,
             "generated": 0 if i % 5 == 0 else 12_000, "is_seeding": i % 9 == 0, "status": "Completed" if i % 6 else "Paused"}
            for i in range(n)]


@pytest.fixture
def seeded(cfg):
    """Deux fichiers : le second révise les conversions des envois du premier (maturation)."""
    conn = connect(cfg.path("db"))
    snaps = [(date(2026, 9, 20), 50), (date(2026, 9, 22), 120)]
    for k, (d, conv) in enumerate(snaps):
        rows = []
        for day in ("2026-09-18", "2026-09-19", "2026-09-20") + (("2026-09-21", "2026-09-22") if k else ()):
            rows += _push_rows(day, conv=conv)
        for r in rows:
            r["broadcast_id"] = abs(hash((r["date"], r["bc_name"], r["sent"]))) % 10_000_000
        push = make_push(rows, d)
        im = make_im([{"date": day, "rule_id": i, "offer_id": i, "offer_name": f"O{i}", "touchpoint": "USSD" if i % 2 else "YAS APP",
                       "fulfillment_success": 0 if i % 2 == 0 else 300, "fulfillment_failures": 0 if i % 2 == 0 else 90}
                      for day in ("2026-09-19", "2026-09-20") for i in range(6)])
        sid = repo.insert_snapshot(conn, Snapshot(Path(f"Yas_till_{d.day}_Sep_2026.xlsb"), f"h{k}", d, push, im))
        conn.commit()
        detect_snapshot(cfg, conn, repo.get_snapshot(conn, sid))
    yield conn
    conn.close()


def _payload(cfg) -> dict:
    html = (cfg.root / "site" / "index.html").read_text(encoding="utf-8")
    raw = PAYLOAD_RE.search(html).group(1).replace("<\\/", "</")

    def no_nan(x):
        raise AssertionError(f"valeur non JSON dans les données embarquées : {x}")
    return json.loads(raw, parse_constant=no_nan)


def test_build_writes_pages_assets_and_complete_payload(cfg, seeded):
    res = build_site(cfg, seeded)
    site = cfg.root / "site"
    assert (site / "index.html").exists() and (site / "settings.html").exists()
    names = {p.name for p in (site / "assets").iterdir()}
    for f in STATIC.iterdir():  # chaque asset est publié sous un nom à empreinte
        stem, ext = f.name.rsplit(".", 1)
        assert any(re.fullmatch(rf"{re.escape(stem)}\.[0-9a-f]{{10}}\.{ext}", n) for n in names), f.name
    p = _payload(cfg)
    for key in ("meta", "snapshots", "push", "im", "im_rules", "versions", "curves", "fill", "anomalies", "catalog", "analytics"):
        assert key in p, key
    assert p["push"]["n"] == len(repo.history_push(seeded, "2026-09-22"))
    assert p["meta"]["latest"]["snapshot_date"] == "2026-09-22"
    assert set(p["analytics"]["presets"]) == {"7j", "30j", "mois", "tout"}
    assert p["fill"]["push"]["generated"][0] is not None   # remplissage suivi fichier par fichier
    assert res.gzip_size < 500 * 1024
    assert res.gzip_size == len(gzip.compress((site / "index.html").read_bytes(), 6))


def test_versions_trace_late_conversions(cfg, seeded):
    build_site(cfg, seeded)
    p = _payload(cfg)
    v = p["versions"]["cols"]
    first = {}
    for bid, snap, conv in zip(v["id"], v["snap"], v["conv"]):
        first.setdefault(bid, []).append((snap, conv))
    revised = [h for h in first.values() if len(h) > 1]
    assert revised and all(h[0][1] < h[-1][1] for h in revised)  # 50 → 120 + i : la maturation est conservée


def test_no_secret_leaks_into_site(cfg, seeded, monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://x.webhook.office.com/abc?sig=TOPSECRET")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2pass")
    build_site(cfg, seeded)
    for page in ("index.html", "settings.html"):
        text = (cfg.root / "site" / page).read_text(encoding="utf-8")
        assert "TOPSECRET" not in text and "hunter2pass" not in text


def test_maturity_curves_per_metric():
    v = pd.DataFrame({"broadcast_id": [1, 1, 1, 2, 2], "age_days": [0, 2, 10, 1, 12],
                      "conversions": [50, 90, 100, 30, 60], "conversion_value": [0, 0, 0, 0, 0]})
    c = maturity_curves(v, ["conversions", "conversion_value"], reference_age=10)
    assert c["conversions"][0] == 0.5 and c["conversions"][2] == 0.9 and c["conversions"][10] == 1.0
    assert c["conversions"][1] == 0.5  # J+1 : seul le broadcast 2 (30 / 60)
    assert "conversion_value" not in c  # aucune valeur finale > 0 : pas de courbe plutôt qu'une courbe fausse


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_js_aggregations_match_python(cfg, seeded):
    """static/kpi.js doit donner les mêmes totaux et taux que analytics/kpi.push_by / im_daily."""
    build_site(cfg, seeded)
    p = _payload(cfg)
    script = f"""
      const KPI = require({json.dumps(str(STATIC / 'kpi.js'))});
      const D = JSON.parse(require('fs').readFileSync(0, 'utf8'));
      KPI.init(D);
      const t = (x) => ({{ n: x.n, c: x.cols, d: x.dict, v: (k, i) => x.dict[k][x.cols[k][i]], all: [...Array(x.n).keys()] }});
      const P = t(D.push), I = t(D.im);
      const out = {{ push: {{}}, im: {{}} }};
      for (const [k, s] of KPI.push(P, P.all, (i) => P.v('d', i))) out.push[k] = {{ sent: s.sent, dlv: s.dlv, conv: s.conv, delivery_rate: s.delivery_rate, conv_rate: s.conv_rate, cg_conv_rate: s.cg_conv_rate, net: s.net_conv_rate }};
      for (const [k, s] of KPI.im(I, I.all, (i) => I.v('d', i))) out.im[k] = {{ imp: s.imp, fs: s.fs, take: s.take_rate, fail: s.failure_rate }};
      process.stdout.write(JSON.stringify(out));
    """
    res = subprocess.run(["node", "-e", script], input=json.dumps(p), capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)
    py = kpi.push_daily(repo.history_push(seeded, "2026-09-22")).set_index("date")
    for d, r in py.iterrows():
        j = js["push"][d]
        assert j["sent"] == r["sent"] and j["conv"] == r["conversions"] and j["dlv"] == r["delivered"]
        for a, b in (("delivery_rate", "delivery_rate"), ("conv_rate", "conv_rate"), ("cg_conv_rate", "cg_conv_rate"), ("net", "net_conv_rate")):
            assert j[a] == pytest.approx(r[b]), (d, a)
    pi = kpi.im_daily(repo.history_im(seeded, "2026-09-22")).set_index("date")
    for d, r in pi.iterrows():
        j = js["im"][d]
        assert j["imp"] == r["impressions"] and j["fs"] == r["fulfillment_success"]
        assert j["take"] == pytest.approx(r["take_rate"])
        assert (j["fail"] is None and pd.isna(r["failure_rate"])) or j["fail"] == pytest.approx(r["failure_rate"])
