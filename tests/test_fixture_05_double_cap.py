"""Fixture 05 — AeroFreight Inc., Delaware double participating-cap.

Two participating-capped preferred classes at different cap multiples (A 2x, B 3x).
Exercises the regime-state algorithm through five distinct regimes:
  1. LP payment (T1, T2)
  2. Both participating uncapped (T3)
  3. A capped + B participating (T4)
  4. A pure-converted + B capped (T5)
  5. Both pure-converted (T6)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.parser import load_from_canonical_json
from src.waterfall import compute_waterfall


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "fixture_05_delaware_double_cap"


@pytest.fixture(scope="module")
def cap_table():
    return load_from_canonical_json(FIXTURE_DIR / "cap_table_input.json")


@pytest.fixture(scope="module")
def waterfall(cap_table):
    return compute_waterfall(cap_table)


@pytest.fixture(scope="module")
def ground_truth():
    return json.loads((FIXTURE_DIR / "ground_truth.json").read_text())


def test_lp_total_matches_ground_truth(waterfall, ground_truth):
    assert waterfall.lp_total == pytest.approx(
        ground_truth["liquidation_preferences_total_usd"]
    )


def test_total_fully_diluted_excludes_reserved_pool(waterfall, ground_truth):
    assert waterfall.total_fully_diluted_shares == ground_truth[
        "shares_summary"
    ]["total_fully_diluted_for_waterfall"]


def test_breakpoint_count(waterfall, ground_truth):
    assert len(waterfall.breakpoints) == len(ground_truth["breakpoints"])


def test_breakpoint_values(waterfall, ground_truth):
    for bp, expected in zip(waterfall.breakpoints, ground_truth["breakpoints"]):
        assert bp.id == expected["id"]
        assert bp.value == pytest.approx(expected["value_usd"])


def test_breakpoint_events_descriptive(waterfall, ground_truth):
    for bp, expected in zip(waterfall.breakpoints, ground_truth["breakpoints"]):
        # Event strings need not match exactly, but the key noun phrases must.
        evt_lc = bp.event.lower()
        if "lp" in expected["event"].lower():
            assert "lp" in evt_lc or "preference" in evt_lc
        if "cap reached" in expected["event"].lower():
            assert "cap" in evt_lc
        if "pure-converts" in expected["event"].lower():
            assert "convert" in evt_lc


def test_series_a_cap_reach(waterfall, ground_truth):
    expected = ground_truth["cap_reach_thresholds_usd"]["Series A Preferred"]
    assert waterfall.cap_reach_thresholds["Series A Preferred"] == pytest.approx(expected)


def test_series_b_cap_reach(waterfall, ground_truth):
    expected = ground_truth["cap_reach_thresholds_usd"]["Series B Preferred"]
    assert waterfall.cap_reach_thresholds["Series B Preferred"] == pytest.approx(expected)


def test_t3_pool_allocation_pct(waterfall):
    """T3 = both participating uncapped, 9.8M-share pool."""
    t3 = next(t for t in waterfall.tranches if t.id == "T3")
    pct = t3.marginal_allocation_pct
    assert pct["Founders Common"] == pytest.approx(40.8163, abs=0.01)
    assert pct["Series A Preferred"] == pytest.approx(20.4082, abs=0.01)
    assert pct["Series B Preferred"] == pytest.approx(30.6122, abs=0.01)
    assert pct["Option Pool (Granted)"] == pytest.approx(8.1633, abs=0.01)


def test_t5_b_capped_excludes_b_from_pool(waterfall):
    """When B is capped, B receives 0% of marginal $1; the pool shrinks to 6.8M."""
    t5 = next(t for t in waterfall.tranches if t.id == "T5")
    pct = t5.marginal_allocation_pct
    assert pct["Series B Preferred"] == pytest.approx(0.0, abs=0.001)
    assert pct["Founders Common"] == pytest.approx(58.8235, abs=0.01)
    assert pct["Series A Preferred"] == pytest.approx(29.4118, abs=0.01)
    assert pct["Option Pool (Granted)"] == pytest.approx(11.7647, abs=0.01)


def test_tranches_partition_value_axis(waterfall):
    """Tranches must form a contiguous partition of the value axis from 0."""
    sorted_tr = sorted(waterfall.tranches, key=lambda t: t.range_low)
    assert sorted_tr[0].range_low == 0
    for i in range(len(sorted_tr) - 1):
        assert sorted_tr[i].range_high == sorted_tr[i + 1].range_low
    assert sorted_tr[-1].range_high is None


def test_each_tranche_allocations_sum_to_100(waterfall):
    for t in waterfall.tranches:
        total = sum(t.marginal_allocation_pct.values())
        assert total == pytest.approx(100.0, abs=0.01), \
            f"Tranche {t.id} allocations sum to {total}, not 100"
