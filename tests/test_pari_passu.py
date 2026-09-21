"""Pari-passu seniority tests (SYSTEM_SPEC §4.2, §8 round 1).

Covers:
- Two-way pari-passu group (B-1 + B-2 same-day close, common in SEA)
- Three-way pari-passu group (cardinality, GAP-20)
- Mixed-LP refusal (GAP-21)
- Backward compatibility: default seniority_sub_rank=0 preserves legacy behavior
"""

from __future__ import annotations

import pytest

from src.models import (
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.waterfall import compute_waterfall


def _common(name: str = "Common", shares: int = 10_000_000) -> ShareClass:
    return ShareClass(name=name, type=ShareClassType.common, shares_outstanding=shares)


def _np_preferred(name: str, shares: int, rank: int, sub_rank: int, lp_amt: float) -> ShareClass:
    return ShareClass(
        name=name,
        type=ShareClassType.preferred,
        shares_outstanding=shares,
        issue_price=lp_amt / max(shares, 1),
        seniority_rank=rank,
        seniority_sub_rank=sub_rank,
        liquidation_preference=LiquidationPreference(
            multiple=1.0, amount=lp_amt, type=LPType.non_participating
        ),
    )


def test_two_way_pari_passu_combined_lp_breakpoint():
    """B-1 ($5M) + B-2 ($3M) at rank 1, pari-passu → one combined $8M LP BP."""
    ct = CapTable(
        company=Company(name="ParitySG"),
        share_classes=[
            _common(),
            _np_preferred("Series B-1", 5_000_000, rank=1, sub_rank=1, lp_amt=5_000_000),
            _np_preferred("Series B-2", 3_000_000, rank=1, sub_rank=2, lp_amt=3_000_000),
            _np_preferred("Series A", 2_000_000, rank=2, sub_rank=0, lp_amt=2_000_000),
        ],
    )
    wf = compute_waterfall(ct)
    # Two LP breakpoints: combined-B group ($8M), then A ($10M cumulative).
    lp_events = [bp for bp in wf.breakpoints if "LP satisfied" in bp.event]
    assert len(lp_events) == 2
    assert lp_events[0].value == pytest.approx(8_000_000)
    assert "pari-passu" in lp_events[0].event
    assert lp_events[1].value == pytest.approx(10_000_000)


def test_two_way_pari_passu_marginal_split_proportional_to_lp():
    """In the LP-paying tranche of a pari-passu group, marginal $1 splits
    by LP amount. B-1 LP $6M, B-2 LP $2M → 75% / 25%."""
    ct = CapTable(
        company=Company(name="ParitySplit"),
        share_classes=[
            _common(),
            _np_preferred("Series B-1", 6_000_000, rank=1, sub_rank=1, lp_amt=6_000_000),
            _np_preferred("Series B-2", 2_000_000, rank=1, sub_rank=2, lp_amt=2_000_000),
        ],
    )
    wf = compute_waterfall(ct)
    lp_tranche = next(t for t in wf.tranches if "pari-passu LP" in t.description)
    assert lp_tranche.marginal_allocation_pct["Series B-1"] == pytest.approx(75.0)
    assert lp_tranche.marginal_allocation_pct["Series B-2"] == pytest.approx(25.0)
    assert lp_tranche.marginal_allocation_pct["Common"] == 0.0


def test_three_way_pari_passu_cardinality(): # GAP-20
    ct = CapTable(
        company=Company(name="TripleTie"),
        share_classes=[
            _common(),
            _np_preferred("B-1", 1_000_000, rank=1, sub_rank=1, lp_amt=1_000_000),
            _np_preferred("B-2", 1_000_000, rank=1, sub_rank=2, lp_amt=1_000_000),
            _np_preferred("B-3", 1_000_000, rank=1, sub_rank=3, lp_amt=1_000_000),
        ],
    )
    wf = compute_waterfall(ct)
    lp_tranche = next(t for t in wf.tranches if "pari-passu LP" in t.description)
    assert lp_tranche.marginal_allocation_pct["B-1"] == pytest.approx(33.333, rel=1e-3)
    assert lp_tranche.marginal_allocation_pct["B-2"] == pytest.approx(33.333, rel=1e-3)
    assert lp_tranche.marginal_allocation_pct["B-3"] == pytest.approx(33.333, rel=1e-3)


def test_duplicate_rank_and_sub_rank_rejected():
    """Two classes at exactly the same (rank, sub_rank) must still be refused."""
    with pytest.raises(ValueError, match=r"duplicate \(seniority_rank, seniority_sub_rank\)"):
        CapTable(
            company=Company(name="X"),
            share_classes=[
                _common(),
                _np_preferred("A", 1_000, rank=1, sub_rank=0, lp_amt=1_000),
                _np_preferred("B", 1_000, rank=1, sub_rank=0, lp_amt=1_000),
            ],
        )


def test_pari_passu_with_mixed_lp_types_refused(): # GAP-21
    with pytest.raises(ValueError, match="mixes LP types"):
        CapTable(
            company=Company(name="MixedBag"),
            share_classes=[
                _common(),
                ShareClass(
                    name="B-1-NP", type=ShareClassType.preferred, shares_outstanding=1000,
                    issue_price=1, seniority_rank=1, seniority_sub_rank=1,
                    liquidation_preference=LiquidationPreference(
                        multiple=1, amount=1000, type=LPType.non_participating),
                ),
                ShareClass(
                    name="B-2-PU", type=ShareClassType.preferred, shares_outstanding=1000,
                    issue_price=1, seniority_rank=1, seniority_sub_rank=2,
                    liquidation_preference=LiquidationPreference(
                        multiple=1, amount=1000, type=LPType.participating_uncapped),
                ),
            ],
        )


def test_backward_compat_default_sub_rank_zero():
    """A legacy CapTable without seniority_sub_rank still validates and
    behaves identically to pre-pari-passu code."""
    ct = CapTable(
        company=Company(name="Legacy"),
        share_classes=[
            _common(),
            _np_preferred("A", 1_000_000, rank=1, sub_rank=0, lp_amt=1_000_000),
            _np_preferred("B", 1_000_000, rank=2, sub_rank=0, lp_amt=2_000_000),
        ],
    )
    wf = compute_waterfall(ct)
    lp_events = [bp for bp in wf.breakpoints if "LP satisfied" in bp.event]
    assert len(lp_events) == 2
    assert lp_events[0].value == pytest.approx(1_000_000)
    assert lp_events[1].value == pytest.approx(3_000_000)
