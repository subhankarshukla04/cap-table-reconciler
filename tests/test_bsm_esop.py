"""BSM / IFRS 2 ESOP tests (SYSTEM_SPEC §5.2)."""

from __future__ import annotations

from datetime import date

import pytest

from src.opm.bsm_esop import ESOPGrant, VestingTranche, amortise_grant, value_grant


def _grant(**overrides):
    defaults = dict(
        id="GRANT-1",
        grantee="Employee 1",
        grant_date=date(2024, 1, 1),
        shares=1000,
        strike_price=10.0,
        spot_price_at_grant=10.0,
        time_to_expiry_years=4.0,
        volatility=0.55,
        risk_free_rate=0.045,
        cliff_date=date(2026, 1, 1),  # 2-year cliff
    )
    defaults.update(overrides)
    return ESOPGrant(**defaults)


def test_atm_grant_fair_value_positive():
    g = _grant()
    fv = value_grant(g)
    assert fv > 0
    # ATM BSM at sigma=0.55 / T=4 / r=0.045 should be in single-digit dollars per share.
    assert 1.0 < fv < 6.0


def test_amortisation_sums_to_aggregate_fair_value():
    g = _grant()
    res = amortise_grant(g, period="annual")
    total = sum(r.expense_for_period for r in res.schedule)
    assert total == pytest.approx(res.fair_value_aggregate, rel=1e-6)
    assert res.schedule[-1].cumulative_expense == pytest.approx(
        res.fair_value_aggregate, rel=1e-6
    )


def test_amortisation_monotone_cumulative():
    g = _grant()
    res = amortise_grant(g, period="monthly")
    cum_values = [r.cumulative_expense for r in res.schedule]
    assert all(b >= a - 1e-9 for a, b in zip(cum_values, cum_values[1:]))


def test_graded_vesting_front_loaded():
    """IFRS 2 graded: each tranche amortised over its own vesting period →
    earlier tranches have shorter denominators → first-year expense
    higher than cliff equivalent."""
    g_graded = _grant(
        cliff_date=None,
        graded_schedule=(
            VestingTranche(vest_date=date(2025, 1, 1), fraction=0.25),
            VestingTranche(vest_date=date(2026, 1, 1), fraction=0.25),
            VestingTranche(vest_date=date(2027, 1, 1), fraction=0.25),
            VestingTranche(vest_date=date(2028, 1, 1), fraction=0.25),
        ),
    )
    g_cliff = _grant(cliff_date=date(2028, 1, 1))
    graded = amortise_grant(g_graded, period="annual")
    cliff = amortise_grant(g_cliff, period="annual")
    # Both must total the same.
    assert sum(r.expense_for_period for r in graded.schedule) == pytest.approx(
        sum(r.expense_for_period for r in cliff.schedule), rel=1e-6
    )
    # Year 1 expense under graded > year 1 under cliff (front-loaded).
    assert graded.schedule[0].expense_for_period > cliff.schedule[0].expense_for_period


def test_grant_without_vesting_info_raises():
    g = _grant(cliff_date=None)
    with pytest.raises(ValueError, match="cliff_date or graded_schedule"):
        amortise_grant(g)


def test_determinism():
    g = _grant()
    a = amortise_grant(g)
    b = amortise_grant(g)
    assert a.fair_value_per_option == pytest.approx(b.fair_value_per_option, rel=1e-12)
    assert [r.expense_for_period for r in a.schedule] == pytest.approx(
        [r.expense_for_period for r in b.schedule], rel=1e-12
    )
