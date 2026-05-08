"""
Day-1 verification: re-derive each fixture's waterfall from its input JSON and
compare against ground_truth.json. Parametrized across fixtures with
non-participating preferred (fixture 01 and 02). Fixture 03 (participating-
with-cap, RCPS) is verified separately once we add the extended logic.

This is throwaway scaffolding. The production waterfall code lives in
src/waterfall.py (Day 3); this exists only to catch hand-math errors in
ground truths before they propagate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

NON_PARTICIPATING_FIXTURES = [
    "fixture_01_clean",
    "fixture_02_typical_messy",
]

NAME_TO_KEY = {
    "Series B Preferred": "series_b_preferred",
    "Series A Preferred": "series_a_preferred",
    "Series Seed Preferred": "series_seed_preferred",
    "Founders Common": "founders_common",
    "Option Pool (Granted)": "option_pool_granted",
}


@dataclass
class Klass:
    name: str
    type: str
    shares: int
    seniority: int
    lp_amount: float
    lp_type: str | None
    is_common_pool: bool


def load_classes(fixture: str) -> list[Klass]:
    data = json.loads((FIXTURES_DIR / fixture / "cap_table_input.json").read_text())
    out: list[Klass] = []
    for sc in data["share_classes"]:
        if sc["type"] == "option_pool_reserved":
            continue
        lp = sc.get("liquidation_preference")
        out.append(
            Klass(
                name=sc["name"],
                type=sc["type"],
                shares=sc["shares_outstanding"],
                seniority=sc["seniority_rank"],
                lp_amount=(lp["amount_usd"] if lp else 0.0),
                lp_type=(lp["type"] if lp else None),
                is_common_pool=sc["type"] in ("common", "option_pool_granted"),
            )
        )
    return out


def conversion_threshold(target: Klass, classes: list[Klass]) -> float:
    """Non-participating: target converts when converted-share of residual = LP."""
    assert target.lp_type == "non_participating", target.name
    senior_lp = sum(
        c.lp_amount
        for c in classes
        if c.type == "preferred" and c.seniority < target.seniority
    )
    pool = sum(c.shares for c in classes if c.is_common_pool) + sum(
        c.shares
        for c in classes
        if c.type == "preferred" and c.seniority >= target.seniority
    )
    return target.lp_amount / (target.shares / pool) + senior_lp


def lp_breakpoints(classes: list[Klass]) -> list[float]:
    preferred = sorted(
        [c for c in classes if c.type == "preferred"], key=lambda c: c.seniority
    )
    bps = [0.0]
    cum = 0.0
    for c in preferred:
        cum += c.lp_amount
        bps.append(cum)
    return bps


def all_breakpoints(classes: list[Klass], thresholds: dict[str, float]) -> list[float]:
    bps = set(lp_breakpoints(classes))
    bps.update(thresholds.values())
    return sorted(bps)


def alloc_above_lps(value: float, classes: list[Klass], thresholds: dict[str, float]):
    converted = {
        c.name: (c.type != "preferred" or value > thresholds.get(c.name, float("inf")))
        for c in classes
    }
    pool = sum(c.shares for c in classes if converted[c.name])
    return pool, {
        c.name: (c.shares / pool if converted[c.name] else 0.0) for c in classes
    }


def get_thresholds(classes: list[Klass]) -> dict[str, float]:
    return {
        c.name: conversion_threshold(c, classes)
        for c in classes
        if c.type == "preferred"
    }


@pytest.fixture(scope="module", params=NON_PARTICIPATING_FIXTURES)
def fixture_data(request):
    fixture = request.param
    truth = json.loads((FIXTURES_DIR / fixture / "ground_truth.json").read_text())
    classes = load_classes(fixture)
    thresholds = get_thresholds(classes)
    return {
        "name": fixture,
        "classes": classes,
        "thresholds": thresholds,
        "truth": truth,
    }


def test_lp_total(fixture_data):
    classes = fixture_data["classes"]
    truth = fixture_data["truth"]
    bps = lp_breakpoints(classes)
    expected_lp_total = truth["liquidation_preferences_total_usd"]
    assert bps[-1] == pytest.approx(expected_lp_total)


def test_conversion_thresholds(fixture_data):
    truth = fixture_data["truth"]
    expected = truth["conversion_thresholds_usd"]
    thresholds = fixture_data["thresholds"]
    assert thresholds["Series Seed Preferred"] == pytest.approx(expected["series_seed_preferred"])
    assert thresholds["Series A Preferred"] == pytest.approx(expected["series_a_preferred"])
    assert thresholds["Series B Preferred"] == pytest.approx(expected["series_b_preferred"])


def test_full_breakpoint_set(fixture_data):
    classes = fixture_data["classes"]
    thresholds = fixture_data["thresholds"]
    truth = fixture_data["truth"]
    bps = all_breakpoints(classes, thresholds)
    expected = [bp["value_usd"] for bp in truth["breakpoints"]]
    assert len(bps) == len(expected)
    for got, exp in zip(bps, expected):
        assert got == pytest.approx(exp, abs=0.01), f"breakpoint diff: {got} vs {exp}"


def test_tranche_allocations(fixture_data):
    classes = fixture_data["classes"]
    thresholds = fixture_data["thresholds"]
    truth = fixture_data["truth"]
    bps = all_breakpoints(classes, thresholds)
    truth_tranches = truth["tranche_allocations"]

    for i, low in enumerate(bps):
        high = bps[i + 1] if i + 1 < len(bps) else None
        mid = (low + high) / 2 if high is not None else low + 1.0

        cum = 0.0
        lp_class = None
        for c in sorted(
            [k for k in classes if k.type == "preferred"], key=lambda k: k.seniority
        ):
            prev = cum
            cum += c.lp_amount
            if prev <= mid < cum:
                lp_class = c
                break

        if lp_class is not None:
            for c in classes:
                exp = truth_tranches[i]["marginal_allocation_pct"][NAME_TO_KEY[c.name]]
                got = 100.0 if c.name == lp_class.name else 0.0
                assert got == pytest.approx(exp), (
                    f"{fixture_data['name']} T{i+1} {c.name}: got {got} expected {exp}"
                )
        else:
            _, frac = alloc_above_lps(mid, classes, thresholds)
            for c in classes:
                exp = truth_tranches[i]["marginal_allocation_pct"][NAME_TO_KEY[c.name]]
                got = frac[c.name] * 100
                assert got == pytest.approx(exp, abs=1e-3), (
                    f"{fixture_data['name']} T{i+1} {c.name}: got {got} expected {exp}"
                )


def test_payout_continuity_at_conversion_thresholds(fixture_data):
    """At each class's conversion threshold, LP value must equal converted value."""
    classes = fixture_data["classes"]
    thresholds = fixture_data["thresholds"]
    for target in [c for c in classes if c.type == "preferred"]:
        v = thresholds[target.name]
        # Junior classes have already converted at this point
        senior_lp = sum(
            c.lp_amount
            for c in classes
            if c.type == "preferred" and c.seniority < target.seniority
        )
        pool = sum(c.shares for c in classes if c.is_common_pool) + sum(
            c.shares
            for c in classes
            if c.type == "preferred" and c.seniority >= target.seniority
        )
        converted_value = (target.shares / pool) * (v - senior_lp)
        assert target.lp_amount == pytest.approx(converted_value), (
            f"{fixture_data['name']} {target.name}: LP {target.lp_amount} != converted {converted_value} at threshold {v}"
        )


def test_consistency_checks_flag_is_true(fixture_data):
    truth = fixture_data["truth"]
    checks = truth["consistency_checks"]
    assert checks["tranche_pcts_sum_to_100_each"] is True
    assert checks["lp_total_equals_bp4"] is True
    assert checks["conversion_thresholds_strictly_increasing"] is True
    assert checks["conversion_thresholds_above_lp_total"] is True
