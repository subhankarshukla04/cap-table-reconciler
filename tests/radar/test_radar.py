"""Unit tests for radar engines. Focus on the engines, not the scrapers."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from radar import mechanics, compliance
from radar.models import (
    EligibilityFilter, Holder, Issuer, ComplianceParams,
    SellerMix, TenderParams,
)
from radar.matching import match_issuer


ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = ROOT / "data" / "fixtures"
TODAY = date(2026, 5, 11)


@pytest.fixture
def razorpay_issuer():
    issuers = json.loads((FIXTURES / "issuers.json").read_text())["issuers"]
    raw = next(i for i in issuers if i["id"] == "razorpay")
    raw.pop("_design_target", None)
    return Issuer.model_validate(raw)


@pytest.fixture
def razorpay_holders():
    rows = json.loads((FIXTURES / "holders" / "razorpay.json").read_text())["holders"]
    return [Holder.model_validate(h) for h in rows]


# ---------- matching ----------

def test_match_handles_legal_suffix():
    assert match_issuer("Razorpay Software Private Limited") == "razorpay"


def test_match_handles_alternate_name():
    assert match_issuer("PT GoTo Gojek Tokopedia Tbk") == "gotogroup"


def test_match_rejects_unrelated():
    assert match_issuer("Some Random Co News") is None


# ---------- mechanics ----------

def test_preview_tender_returns_consistent_pool(razorpay_issuer, razorpay_holders):
    params = TenderParams(
        tender_size_usd=20_000_000,
        price_per_share_usd=0.84,
        eligibility_filter=EligibilityFilter(),
    )
    result = mechanics.preview_tender(razorpay_issuer, razorpay_holders, params)
    assert result.eligible_holder_count > 0
    assert result.eligible_unit_pool > 0
    assert 0 <= result.scaleback_factor <= 1
    assert 0 <= result.scaleback_factor_if_2x <= 1
    assert result.scaleback_factor_if_2x <= result.scaleback_factor


def test_preview_tender_speed_under_50ms(razorpay_issuer, razorpay_holders):
    params = TenderParams(
        tender_size_usd=20_000_000,
        price_per_share_usd=0.84,
        eligibility_filter=EligibilityFilter(),
    )
    start = time.perf_counter()
    for _ in range(20):
        mechanics.preview_tender(razorpay_issuer, razorpay_holders, params)
    elapsed_ms = (time.perf_counter() - start) / 20 * 1000
    assert elapsed_ms < 50, f"preview_tender averaged {elapsed_ms:.1f}ms per call"


def test_eligibility_excludes_unvested(razorpay_holders):
    # An ESOP holder hired 6 months ago is below the 12mo cliff
    holder = Holder.model_validate({
        "holder_id": "test", "name": "Test", "class": "ESOP",
        "units_held": 1000, "vested_units": 0,
        "is_employee": True, "is_ex_employee": False, "residency": "resident",
        "hire_date": (TODAY - timedelta(days=180)).isoformat(),
        "termination_date": None,
    })
    assert not mechanics.is_eligible(holder, EligibilityFilter())


# ---------- compliance ----------

def test_compliance_india_pass_when_price_above_floor():
    params = ComplianceParams(
        issuer_state="Karnataka",
        seller_mix=SellerMix(resident_pct=78, nri_pct=14, foreign_pct=8),
        share_class="Common",
        transfer_price_per_share_local=80.0,
        fair_value_proxy_local=70.0,
    )
    out = compliance.preview_compliance(params, eligible_holders=400)
    assert out.rbi_floor_verdict == "PASS"
    assert out.rbi_floor_delta_pct > 0


def test_compliance_india_fail_when_price_below_floor():
    params = ComplianceParams(
        issuer_state="Karnataka",
        seller_mix=SellerMix(resident_pct=78, nri_pct=14, foreign_pct=8),
        share_class="Common",
        transfer_price_per_share_local=60.0,
        fair_value_proxy_local=70.0,
    )
    out = compliance.preview_compliance(params, eligible_holders=400)
    assert out.rbi_floor_verdict == "FAIL"


def test_compliance_singapore_returns_na():
    params = ComplianceParams(
        issuer_state="Singapore",
        seller_mix=SellerMix(singapore_resident_pct=80, foreign_pct=20),
        share_class="Common",
        transfer_price_per_share_local=5.10,
        fair_value_proxy_local=5.10,
    )
    out = compliance.preview_compliance(params, eligible_holders=400)
    assert out.rbi_floor_verdict == "N/A"
    assert "Singapore Stamp Duties Act" in out.state_duty_citation


def test_compliance_stamp_duty_scales_with_holders():
    params = ComplianceParams(
        issuer_state="Karnataka",
        seller_mix=SellerMix(resident_pct=100),
        share_class="Common",
        transfer_price_per_share_local=70.0,
        fair_value_proxy_local=70.0,
    )
    a = compliance.preview_compliance(params, eligible_holders=100)
    b = compliance.preview_compliance(params, eligible_holders=400)
    assert b.stamp_duty_local > a.stamp_duty_local
