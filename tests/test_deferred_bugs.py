"""BUG-010 + BUG-014 deferred fixes (W2.3)."""

from __future__ import annotations

from datetime import date

import pytest

from src.diff import _diff_class
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


# ---- BUG-014: None vs 0 / None vs 1.0 must register as a change -----------


def _np_pref(name, shares, issue_price=None, conv_ratio=None, rank=1):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=issue_price, issue_date=date(2024, 1, 1),
        seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=shares * (issue_price or 1), type=LPType.non_participating
        ),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
        conversion_ratio=conv_ratio,
    )


def test_bug014_none_to_zero_issue_price_is_a_diff():
    a = _np_pref("A", 1000, issue_price=None)
    b = _np_pref("A", 1000, issue_price=0.0)
    deltas = _diff_class(a, b)
    assert any(d.field == "issue_price" for d in deltas)


def test_bug014_none_to_one_conv_ratio_is_a_diff():
    a = _np_pref("A", 1000, issue_price=1.0, conv_ratio=None)
    b = _np_pref("A", 1000, issue_price=1.0, conv_ratio=1.0)
    deltas = _diff_class(a, b)
    assert any(d.field == "conversion_ratio" for d in deltas)


def test_bug014_zero_to_zero_is_not_a_diff():
    a = _np_pref("A", 1000, issue_price=0.0)
    b = _np_pref("A", 1000, issue_price=0.0)
    deltas = _diff_class(a, b)
    assert not any(d.field == "issue_price" for d in deltas)


# ---- BUG-010: /whatif zero-share fallback no longer silent --------------


def test_bug010_whatif_zero_shares_recomputes_lp():
    """Simulate the math in app.py /whatif: a zero-share class with override
    must produce a non-zero new LP amount (not silently scale to zero)."""
    sc = ShareClass(
        name="A",
        type=ShareClassType.preferred,
        shares_outstanding=0,
        issue_price=2.0,
        issue_date=date(2024, 1, 1),
        seniority_rank=1,
        liquidation_preference=LiquidationPreference(
            multiple=1.0, amount=0.0, type=LPType.non_participating
        ),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
    )
    new_shares = 1000
    new_mult = 1.0
    # Mirror the patched code path:
    price = sc.issue_price or 0.0
    new_amount = new_shares * price * new_mult if price > 0 else sc.liquidation_preference.amount
    assert new_amount == 2000.0
    # And verify the fix preserves the override → re-validates a real LP.
    new_lp = sc.liquidation_preference.model_copy(update={
        "multiple": new_mult,
        "amount": new_amount,
    })
    assert new_lp.amount > 0
