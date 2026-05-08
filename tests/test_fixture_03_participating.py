"""
Day-1 verification for fixture 03: participating-with-cap waterfall.

Re-derives the eight breakpoints and tranche allocations from the input JSON
and compares against ground_truth.json. The math here is materially harder
than fixtures 01-02 because Series A is participating-with-cap, which introduces
three additional regimes:

  - regime where A is uncapped (LP + participation share)
  - regime where A is capped at 3x and frozen (no marginal)
  - regime where A pure-converts (forgoes LP+cap, becomes ordinary common)

This test scaffolds the math used at the fixture-design stage. The production
waterfall code (Day 3, src/waterfall.py) reimplements with a cleaner data model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent.parent / "fixtures" / "fixture_03_edge_case"


# Fixture-specific constants (sourced from cap_table_input.json)
SHARES = {
    "founders": 4_000_000,
    "seed": 1_000_000,
    "a": 2_500_000,
    "b": 3_500_000,
    "options_granted": 1_200_000,
}
LP = {
    "b": 875_000_000,
    "a": 250_000_000,
    "seed": 50_000_000,
}
A_CAP = 750_000_000  # 3x of A's 250M LP


@dataclass
class State:
    """Encodes which regime we're in via flags."""
    seed_converted: bool
    a_capped: bool
    b_converted: bool
    a_pure_converted: bool


def truth():
    return json.loads((FIXTURE / "ground_truth.json").read_text())


def lps_paid_in_state(s: State) -> float:
    """Sum of LPs still being paid (i.e., classes not converted, not capped)."""
    total = 0.0
    if not s.b_converted:
        total += LP["b"]
    # A's LP is part of A's payout up to cap; only "paid as separate LP" if A is in LP+participation mode
    # When A is capped: A's LP is consumed within the cap.
    # When A is pure-converted: A forgoes LP entirely.
    if not s.a_capped and not s.a_pure_converted:
        total += LP["a"]
    if not s.seed_converted:
        total += LP["seed"]
    return total


def common_pool_for_marginal(s: State) -> int:
    """Shares sharing the marginal $1 above LPs."""
    pool = SHARES["founders"] + SHARES["options_granted"]
    if s.seed_converted:
        pool += SHARES["seed"]
    # A: in pool if participating (uncapped) or pure-converted; not in pool if capped
    if (not s.a_capped) or s.a_pure_converted:
        pool += SHARES["a"]
    if s.b_converted:
        pool += SHARES["b"]
    return pool


def alloc_marginal(s: State) -> dict[str, float]:
    """Fraction of marginal $1 to each class in this regime."""
    pool = common_pool_for_marginal(s)
    out = {
        "founders_common": SHARES["founders"] / pool,
        "option_pool_granted": SHARES["options_granted"] / pool,
        "series_seed_ccps": SHARES["seed"] / pool if s.seed_converted else 0.0,
        "series_a_ccps": (
            SHARES["a"] / pool if (not s.a_capped or s.a_pure_converted) else 0.0
        ),
        "series_b_ccps": SHARES["b"] / pool if s.b_converted else 0.0,
    }
    return out


# ---- Tests ----


def test_lp_breakpoints():
    """T1, T2, T3: B then A then Seed LP being paid."""
    bp1 = LP["b"]
    bp2 = bp1 + LP["a"]
    bp3 = bp2 + LP["seed"]
    t = truth()
    assert t["breakpoints"][1]["value_inr"] == bp1
    assert t["breakpoints"][2]["value_inr"] == bp2
    assert t["breakpoints"][3]["value_inr"] == bp3
    assert t["liquidation_preferences_total_inr"] == bp3


def test_seed_conversion_threshold():
    """Seed converts when its converted-as-common payout = LP, in the regime where A is participating."""
    # State: A participating (uncapped), B preferred, Seed converted.
    s = State(seed_converted=True, a_capped=False, b_converted=False, a_pure_converted=False)
    pool = common_pool_for_marginal(s)
    # Seed's payout if converted = (seed_shares/pool) * (V - LPs_other_paid)
    # LPs other paid = B (875M) + A (250M) = 1125M
    senior_lps = LP["b"] + LP["a"]
    threshold = LP["seed"] / (SHARES["seed"] / pool) + senior_lps
    assert threshold == pytest.approx(1_560_000_000)
    assert truth()["breakpoints"][4]["value_inr"] == pytest.approx(threshold)


def test_a_participation_cap_breakpoint():
    """A's cap reached at: A's LP + participation_residual_share = 3x LP = 750M.
    Regime: Seed converted, A still participating, B preferred."""
    s = State(seed_converted=True, a_capped=False, b_converted=False, a_pure_converted=False)
    pool = common_pool_for_marginal(s)
    # A's residual share = 2.5M / pool
    a_share = SHARES["a"] / pool
    # Senior LPs: B (875M). A's LP (250M) is paid first, A's participation comes from residual.
    # Residual base above all LPs (₹1,175M including Seed's LP, but Seed has converted by this point so Seed's LP is gone).
    # Residual = V - (B's LP + A's LP) = V - 1,125M
    # A's total = 250M + a_share * (V - 1,125M)
    # Cap at 750M → a_share * (V - 1,125M) = 500M → V = 1,125M + 500M / a_share
    target_residual_share = A_CAP - LP["a"]
    threshold = (LP["b"] + LP["a"]) + target_residual_share / a_share
    assert threshold == pytest.approx(2_865_000_000)
    assert truth()["breakpoints"][5]["value_inr"] == pytest.approx(threshold)


def test_b_conversion_threshold_after_a_capped():
    """B converts after A is capped. Transitioning from regime T6 (A capped, B preferred) to T7 (A capped, B converted).

    In regime T6: B receives flat 875M (LP).
    In regime T7: B receives (B_shares/pool_T7) * (V - 750M).
    Equality: (3.5/9.7) * (V - 750M) = 875M → V = 750M + 875M * 9.7/3.5 = 750M + 2,425M = 3,175M.
    """
    s_t7 = State(seed_converted=True, a_capped=True, b_converted=True, a_pure_converted=False)
    pool_t7 = common_pool_for_marginal(s_t7)
    # Total payout up to V in T7: A capped at 750M, plus marginal pool getting V - 750M total
    # B's payout = (b_shares/pool) * (V - 750M)
    # Set equal to B's LP (875M):
    threshold = A_CAP + LP["b"] * pool_t7 / SHARES["b"]
    assert threshold == pytest.approx(3_175_000_000)
    assert truth()["breakpoints"][6]["value_inr"] == pytest.approx(threshold)


def test_a_pure_conversion_threshold():
    """A pure-converts when (a_shares/full_pool) * V exceeds the cap.

    Regime T8: all classes pure common. Pool = 12.2M.
    A's pure-converted payout = (2.5/12.2) * V.
    Indifferent with cap (750M): V = 750M * 12.2 / 2.5 = 3,660M.
    """
    s_t8 = State(seed_converted=True, a_capped=False, b_converted=True, a_pure_converted=True)
    pool_t8 = common_pool_for_marginal(s_t8)
    threshold = A_CAP * pool_t8 / SHARES["a"]
    assert threshold == pytest.approx(3_660_000_000)
    assert truth()["breakpoints"][7]["value_inr"] == pytest.approx(threshold)


def test_t4_marginal_allocation():
    """T4: All LPs paid; Seed in LP state; A participating; B preferred."""
    s = State(seed_converted=False, a_capped=False, b_converted=False, a_pure_converted=False)
    alloc = alloc_marginal(s)
    t = truth()["tranche_allocations"][3]
    expected = t["marginal_allocation_pct"]
    for key, exp in expected.items():
        got = alloc[key] * 100
        assert got == pytest.approx(exp, abs=1e-3), f"T4 {key}: got {got} expected {exp}"


def test_t5_marginal_allocation():
    """T5: Seed converted; A participating uncapped; B preferred."""
    s = State(seed_converted=True, a_capped=False, b_converted=False, a_pure_converted=False)
    alloc = alloc_marginal(s)
    t = truth()["tranche_allocations"][4]
    expected = t["marginal_allocation_pct"]
    for key, exp in expected.items():
        got = alloc[key] * 100
        assert got == pytest.approx(exp, abs=1e-3), f"T5 {key}: got {got} expected {exp}"


def test_t6_marginal_allocation():
    """T6: A capped; B preferred. Marginal goes to founders + options + Seed only."""
    s = State(seed_converted=True, a_capped=True, b_converted=False, a_pure_converted=False)
    alloc = alloc_marginal(s)
    t = truth()["tranche_allocations"][5]
    expected = t["marginal_allocation_pct"]
    for key, exp in expected.items():
        got = alloc[key] * 100
        assert got == pytest.approx(exp, abs=1e-3), f"T6 {key}: got {got} expected {exp}"


def test_t7_marginal_allocation():
    """T7: A capped; B converted; Seed converted. Marginal pool excludes A only."""
    s = State(seed_converted=True, a_capped=True, b_converted=True, a_pure_converted=False)
    alloc = alloc_marginal(s)
    t = truth()["tranche_allocations"][6]
    expected = t["marginal_allocation_pct"]
    for key, exp in expected.items():
        got = alloc[key] * 100
        assert got == pytest.approx(exp, abs=1e-3), f"T7 {key}: got {got} expected {exp}"


def test_t8_marginal_allocation():
    """T8: A pure-converted; everyone is common."""
    s = State(seed_converted=True, a_capped=False, b_converted=True, a_pure_converted=True)
    alloc = alloc_marginal(s)
    t = truth()["tranche_allocations"][7]
    expected = t["marginal_allocation_pct"]
    for key, exp in expected.items():
        got = alloc[key] * 100
        assert got == pytest.approx(exp, abs=1e-3), f"T8 {key}: got {got} expected {exp}"


def test_payout_continuity_at_bp6_a_cap_reached():
    """At BP6, A's LP+participation in T5 must equal A's flat cap (750M)."""
    s_t5 = State(seed_converted=True, a_capped=False, b_converted=False, a_pure_converted=False)
    pool_t5 = common_pool_for_marginal(s_t5)
    a_share_t5 = SHARES["a"] / pool_t5
    bp6 = 2_865_000_000
    a_payout_at_bp6 = LP["a"] + a_share_t5 * (bp6 - (LP["b"] + LP["a"]))
    assert a_payout_at_bp6 == pytest.approx(A_CAP)


def test_payout_continuity_at_bp7_b_converts():
    """At BP7, B's payout must be continuous between T6 (LP=875M) and T7 (converted)."""
    s_t7 = State(seed_converted=True, a_capped=True, b_converted=True, a_pure_converted=False)
    pool_t7 = common_pool_for_marginal(s_t7)
    bp7 = 3_175_000_000
    b_t7 = (SHARES["b"] / pool_t7) * (bp7 - A_CAP)
    assert b_t7 == pytest.approx(LP["b"])


def test_payout_continuity_at_bp8_a_pure_converts():
    """At BP8, A's payout must be continuous between T7 (capped at 750M) and T8 (pure-converted)."""
    s_t8 = State(seed_converted=True, a_capped=False, b_converted=True, a_pure_converted=True)
    pool_t8 = common_pool_for_marginal(s_t8)
    bp8 = 3_660_000_000
    a_t8 = (SHARES["a"] / pool_t8) * bp8
    assert a_t8 == pytest.approx(A_CAP)


def test_total_share_count():
    total = sum(SHARES.values())
    assert total == 12_200_000
    assert truth()["shares_summary"]["total_fully_diluted_for_waterfall"] == total
