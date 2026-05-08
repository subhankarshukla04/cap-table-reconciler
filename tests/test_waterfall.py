"""
Verifies src/waterfall.py against the hand-computed ground_truth.json files
for all three fixtures. Replaces the standalone fixture-design verifiers
with a test against the production code path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.parser import load_from_canonical_json
from src.waterfall import compute_waterfall


FIXTURES = Path(__file__).parent.parent / "fixtures"

NAME_TO_KEY = {
    # Fixture 01 / 02
    "Series B Preferred": "series_b_preferred",
    "Series A Preferred": "series_a_preferred",
    "Series Seed Preferred": "series_seed_preferred",
    "Founders Common": "founders_common",
    "Option Pool (Granted)": "option_pool_granted",
    # Fixture 03
    "Series B CCPS": "series_b_ccps",
    "Series A CCPS": "series_a_ccps",
    "Series Seed CCPS": "series_seed_ccps",
    "Founders Common (Class A)": "founders_common",
}


def _load_ground_truth(fixture_dir: str) -> dict:
    return json.loads((FIXTURES / fixture_dir / "ground_truth.json").read_text())


def _value_key(fixture_dir: str) -> str:
    """Ground truth uses 'value_usd' or 'value_inr' depending on fixture currency."""
    truth = _load_ground_truth(fixture_dir)
    sample_bp = truth["breakpoints"][0]
    return next(k for k in sample_bp.keys() if k.startswith("value_"))


@pytest.mark.parametrize(
    "fixture_dir",
    ["fixture_01_clean", "fixture_02_typical_messy", "fixture_03_edge_case"],
)
def test_breakpoint_count_matches(fixture_dir):
    cap_table = load_from_canonical_json(FIXTURES / fixture_dir / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    truth = _load_ground_truth(fixture_dir)
    assert len(result.breakpoints) == len(truth["breakpoints"]), (
        f"{fixture_dir}: got {len(result.breakpoints)} breakpoints, expected {len(truth['breakpoints'])}"
    )


@pytest.mark.parametrize(
    "fixture_dir",
    ["fixture_01_clean", "fixture_02_typical_messy", "fixture_03_edge_case"],
)
def test_breakpoint_values_match_ground_truth(fixture_dir):
    cap_table = load_from_canonical_json(FIXTURES / fixture_dir / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    truth = _load_ground_truth(fixture_dir)
    vk = _value_key(fixture_dir)
    expected = [bp[vk] for bp in truth["breakpoints"]]
    actual = [bp.value for bp in result.breakpoints]
    for got, exp in zip(actual, expected):
        assert got == pytest.approx(exp, abs=0.5), f"{fixture_dir}: {got} vs {exp}"


@pytest.mark.parametrize(
    "fixture_dir",
    ["fixture_01_clean", "fixture_02_typical_messy", "fixture_03_edge_case"],
)
def test_tranche_allocations_match_ground_truth(fixture_dir):
    cap_table = load_from_canonical_json(FIXTURES / fixture_dir / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    truth = _load_ground_truth(fixture_dir)
    expected_tranches = truth["tranche_allocations"]
    assert len(result.tranches) == len(expected_tranches)

    for i, (got, exp) in enumerate(zip(result.tranches, expected_tranches)):
        for klass_name, pct_got in got.marginal_allocation_pct.items():
            key = NAME_TO_KEY.get(klass_name)
            if key is None:
                continue
            expected_pct = exp["marginal_allocation_pct"].get(key)
            if expected_pct is None:
                continue
            assert pct_got == pytest.approx(expected_pct, abs=1e-3), (
                f"{fixture_dir} T{i+1} {klass_name}: got {pct_got} expected {expected_pct}"
            )


@pytest.mark.parametrize(
    "fixture_dir",
    ["fixture_01_clean", "fixture_02_typical_messy"],
)
def test_lp_total_matches(fixture_dir):
    cap_table = load_from_canonical_json(FIXTURES / fixture_dir / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    truth = _load_ground_truth(fixture_dir)
    assert result.lp_total == pytest.approx(truth["liquidation_preferences_total_usd"])


def test_fixture_03_lp_total_inr():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    truth = _load_ground_truth("fixture_03_edge_case")
    assert result.lp_total == pytest.approx(truth["liquidation_preferences_total_inr"])


def test_fixture_03_cap_reach_threshold():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    assert "Series A CCPS" in result.cap_reach_thresholds
    assert result.cap_reach_thresholds["Series A CCPS"] == pytest.approx(2_865_000_000)


def test_fixture_03_pure_conversion_threshold():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    assert "Series A CCPS" in result.pure_conversion_thresholds
    assert result.pure_conversion_thresholds["Series A CCPS"] == pytest.approx(3_660_000_000)


def test_fixture_03_b_conversion_threshold_in_capped_regime():
    """B's conversion threshold in fixture 03 should reflect that A is capped (not participating)."""
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    result = compute_waterfall(cap_table)
    assert "Series B CCPS" in result.conversion_thresholds
    assert result.conversion_thresholds["Series B CCPS"] == pytest.approx(3_175_000_000)
