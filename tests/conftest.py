"""Fixtures : configuration isolée et fabriques de DataFrames synthétiques."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from cvm_monitor.config import load_config
from cvm_monitor.detect.base import RuleContext

ROOT = Path(__file__).resolve().parents[1]
# Les deux fichiers de référence (01/09 et 22/09) : à la racine ou dans data/.
REAL_FILES = sorted({p.name: p for d in (ROOT, ROOT / "data")
                     for p in d.glob("Yas_Senegal_Daily_Dashboard_till_*_Sep_2026.xlsb")}.values(), key=lambda p: p.name)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for k in ("TEAMS_WEBHOOK_URL", "MAIL_TO", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "config.yaml", tmp_path / "config" / "config.yaml")
    return load_config(tmp_path / "config" / "config.yaml")


PUSH_DEFAULTS = dict(
    date="2026-09-10", scheduled_at="2026-09-10 09:00:00", broadcast_name="BC", bc_name="BC_A", campaign_name="Camp A",
    campaign_id=1, category="CVM", status="Completed", generated=10_000, sent=10_000, acknowledged=10_000,
    conversions=100, unique_conversions=100, conversion_value=0.0, fulfillment_success=100, fulfillment_failure=0,
    cg_size=1_000, cg_conversions=8, ack_rate=1.0, conv_rate=0.01, fulfillment_rate=1.0, cg_conv_rate=0.008,
    net_conv_rate=0.002, unique_conversion_value=0.0, is_seeding=False, delivered=8_000, total_con_val=None,
)
IM_DEFAULTS = dict(
    date="2026-09-20", touchpoint="USSD", program="NBO_Inbound_Program", rule_name="Rule A", rule_id=1,
    product_name="P", product_id=1, offer_name="Offer A", offer_id=1, rule_status="Active", program_status="Active",
    last_refresh="2026-09-11 06:00:00", impressions=10_000, conversions=0, fulfillment_success=500,
    fulfillment_failures=100, accepted=0, declined=0, maybe_later=0,
)


def make_push(rows: list[dict], snapshot_date: date = date(2026, 9, 22)) -> pd.DataFrame:
    df = pd.DataFrame([{**PUSH_DEFAULTS, "broadcast_id": 1000 + i, **r} for i, r in enumerate(rows)])
    df["age_days"] = (pd.Timestamp(snapshot_date) - pd.to_datetime(df["date"])).dt.days
    return df


def make_im(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{**IM_DEFAULTS, **r} for r in rows])


def make_ctx(cfg, push=None, im=None, snapshot_date=date(2026, 9, 22), prev_push=None, prev_im=None,
             hist_push=None, hist_im=None) -> RuleContext:
    push = push if push is not None else make_push([{}], snapshot_date)
    im = im if im is not None else make_im([{}])
    return RuleContext(
        cfg=cfg, snapshot_date=snapshot_date, push=push, im=im,
        hist_push=hist_push if hist_push is not None else push, hist_im=hist_im if hist_im is not None else im,
        prev_push=prev_push, prev_im=prev_im,
        prev_snapshot_date=date(2026, 9, 21) if prev_push is not None else None,
    )


def run_one(ctx, rule_id):
    from cvm_monitor.detect.engine import run_rules
    anomalies, executed, errors = run_rules(ctx, only={rule_id})
    assert not errors, errors
    return anomalies
