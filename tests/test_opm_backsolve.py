"""OPM Backsolve tests (SYSTEM_SPEC §5.1, §8.7)."""

from __future__ import annotations

import math
from datetime import date

import pytest

from src.checklist import Finding, run_checklist
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.opm.backsolve import (
    AnchorInputs,
    BacksolveAnchorMissing,
    BacksolveBlockersOutstanding,
    MarketInputs,
    backsolve,
)
from src.opm.bsm import bsm_call_value


# ---- BSM standalone --------------------------------------------------------


def test_bsm_call_atm_known_value():
    """Sanity: known atm call value, K=S=100, T=1, sigma=0.20, r=0.05.
    Closed-form via standard BSM ≈ 10.45."""
    v = bsm_call_value(S=100, K=100, T=1.0, sigma=0.20, r=0.05, q=0.0)
    assert v == pytest.approx(10.4506, abs=1e-3)


def test_bsm_call_deep_itm_approaches_intrinsic_pv():
    v = bsm_call_value(S=1000, K=100, T=1.0, sigma=0.20, r=0.05, q=0.0)
    forward_minus_strike_pv = 1000 - 100 * math.exp(-0.05)
    assert v == pytest.approx(forward_minus_strike_pv, rel=1e-4)


def test_bsm_call_deep_otm_near_zero():
    v = bsm_call_value(S=10, K=1000, T=1.0, sigma=0.20, r=0.05)
    assert v < 1e-6


def test_bsm_zero_vol_returns_intrinsic_discounted():
    """sigma=0: deterministic forward minus strike, discounted."""
    v = bsm_call_value(S=100, K=80, T=1.0, sigma=0.0, r=0.05)
    forward = 100 * math.exp(0.05)
    intrinsic = forward - 80
    assert v == pytest.approx(intrinsic * math.exp(-0.05), rel=1e-6)


def test_bsm_zero_time_returns_intrinsic():
    assert bsm_call_value(S=100, K=80, T=0.0, sigma=0.2, r=0.05) == pytest.approx(20)
    assert bsm_call_value(S=80, K=100, T=0.0, sigma=0.2, r=0.05) == 0.0


# ---- Backsolve refusals + happy path --------------------------------------


def _clean_ct():
    return CapTable(
        company=Company(name="Series B Co", currency="USD"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=5_000_000),
            ShareClass(
                name="Series A",
                type=ShareClassType.preferred,
                shares_outstanding=2_000_000,
                issue_price=1.00,
                issue_date=date(2023, 6, 1),
                seniority_rank=2,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=2_000_000, type=LPType.non_participating
                ),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
            ShareClass(
                name="Series B",
                type=ShareClassType.preferred,
                shares_outstanding=1_000_000,
                issue_price=10.00,
                issue_date=date(2025, 6, 1),
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=10_000_000, type=LPType.non_participating
                ),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )


def test_refuses_when_blocker_findings_outstanding():
    ct = _clean_ct()
    # Force a blocker finding by removing anti_dilution on Series A.
    ct.share_classes[1].anti_dilution = None
    fs = run_checklist(ct)
    assert any(f.severity == "blocker" for f in fs)
    with pytest.raises(BacksolveBlockersOutstanding):
        backsolve(
            ct,
            findings=fs,
            market=MarketInputs(volatility=0.55, time_to_liquidity_years=4.0,
                                risk_free_rate=0.045, dlom=0.0),
            anchor=AnchorInputs(class_name="Series B", price_per_share=10.0),
        )


def test_anchor_missing_raises():
    ct = _clean_ct()
    fs = run_checklist(ct)
    with pytest.raises(BacksolveAnchorMissing):
        backsolve(
            ct,
            findings=fs,
            market=MarketInputs(volatility=0.55, time_to_liquidity_years=4.0,
                                risk_free_rate=0.045),
            anchor=AnchorInputs(class_name="Series Z (does not exist)", price_per_share=1.0),
        )


def test_backsolve_residual_zero_at_solution():
    """The solved S must make modeled Series-B PPS == anchor PPS."""
    ct = _clean_ct()
    market = MarketInputs(volatility=0.55, time_to_liquidity_years=4.0, risk_free_rate=0.045)
    anchor = AnchorInputs(class_name="Series B", price_per_share=10.0)
    result = backsolve(ct, findings=run_checklist(ct), market=market, anchor=anchor)
    series_b = next(c for c in result.per_class if c.name == "Series B")
    assert series_b.fair_value_per_share == pytest.approx(10.0, rel=1e-4)


def test_common_pps_is_lower_than_anchor_pps():
    """Common is junior; absent unusual ratchets, common < anchor PPS."""
    ct = _clean_ct()
    market = MarketInputs(volatility=0.55, time_to_liquidity_years=4.0, risk_free_rate=0.045)
    anchor = AnchorInputs(class_name="Series B", price_per_share=10.0)
    result = backsolve(ct, findings=run_checklist(ct), market=market, anchor=anchor)
    common = next(c for c in result.per_class if c.name == "Common")
    assert 0 < common.fair_value_per_share < anchor.price_per_share


def test_dlom_applied_to_common():
    ct = _clean_ct()
    base_market = MarketInputs(volatility=0.55, time_to_liquidity_years=4.0, risk_free_rate=0.045, dlom=0.0)
    base = backsolve(ct, findings=run_checklist(ct), market=base_market,
                     anchor=AnchorInputs(class_name="Series B", price_per_share=10.0))
    dlom_market = MarketInputs(volatility=0.55, time_to_liquidity_years=4.0, risk_free_rate=0.045, dlom=0.25)
    dlom_result = backsolve(ct, findings=run_checklist(ct), market=dlom_market,
                            anchor=AnchorInputs(class_name="Series B", price_per_share=10.0))
    common_base = next(c for c in base.per_class if c.name == "Common")
    common_dlom = next(c for c in dlom_result.per_class if c.name == "Common")
    assert common_dlom.fair_value_per_share_after_dlom == pytest.approx(
        common_base.fair_value_per_share * 0.75, rel=1e-3
    )


def test_sensitivity_tables_populated():
    ct = _clean_ct()
    market = MarketInputs(volatility=0.55, time_to_liquidity_years=4.0, risk_free_rate=0.045)
    anchor = AnchorInputs(class_name="Series B", price_per_share=10.0)
    result = backsolve(ct, findings=run_checklist(ct), market=market, anchor=anchor)
    assert len(result.sensitivity["volatility"]) >= 3
    assert len(result.sensitivity["time"]) >= 3
    assert len(result.sensitivity["rfr"]) >= 3
    # Every row carries a valid common-FMV (positive, finite).
    for table_name in ("volatility", "time", "rfr"):
        for row in result.sensitivity[table_name]:
            assert row["common_fmv_per_share"] > 0
            assert row["implied_equity_value"] > 0


def test_determinism():
    """Same inputs → same outputs."""
    ct = _clean_ct()
    market = MarketInputs(volatility=0.55, time_to_liquidity_years=4.0, risk_free_rate=0.045)
    anchor = AnchorInputs(class_name="Series B", price_per_share=10.0)
    a = backsolve(ct, findings=run_checklist(ct), market=market, anchor=anchor)
    b = backsolve(ct, findings=run_checklist(ct), market=market, anchor=anchor)
    assert a.implied_total_equity_value == pytest.approx(b.implied_total_equity_value, rel=1e-9)
