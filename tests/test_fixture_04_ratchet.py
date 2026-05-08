"""Regression tests for Fixture 04 — Surya Foods, down-round + triggered full-ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.checklist import run_checklist
from src.parser import load_from_canonical_json
from src.waterfall import compute_waterfall


F04_DIR = Path(__file__).parent.parent / "fixtures" / "fixture_04_down_round_ratchet"


@pytest.fixture(scope="module")
def cap_table():
    return load_from_canonical_json(F04_DIR / "cap_table_input.json")


@pytest.fixture(scope="module")
def ground_truth():
    return json.loads((F04_DIR / "ground_truth.json").read_text())


def test_company_metadata(cap_table):
    assert cap_table.company.name == "Surya Foods Pvt. Ltd."
    assert cap_table.company.currency == "INR"
    assert cap_table.company.currency_symbol == "₹"


def test_total_fully_diluted_post_trigger(cap_table, ground_truth):
    expected = ground_truth["structural_facts"]["total_fully_diluted_shares"]
    assert cap_table.total_fully_diluted_for_waterfall == expected


def test_seed_post_trigger_shares(cap_table):
    seed = next(sc for sc in cap_table.share_classes if sc.name == "Series Seed CCPS")
    assert seed.shares_outstanding == 800000
    assert seed.conversion_ratio == 1.667
    assert seed.anti_dilution.variant.value == "full_ratchet"
    assert "TRIGGERED" in (seed.anti_dilution.notes or "")


def test_a2_is_most_senior(cap_table):
    most_senior = cap_table.preferred_classes_by_seniority[0]
    assert most_senior.name == "Series A2 CCPS"
    assert most_senior.seniority_rank == 1
    assert most_senior.issue_price == 30.0


def test_lp_total(cap_table, ground_truth):
    w = compute_waterfall(cap_table)
    assert w.lp_total == ground_truth["structural_facts"]["lp_total_inr"]


def test_breakpoint_count_and_values(cap_table, ground_truth):
    w = compute_waterfall(cap_table)
    expected = ground_truth["expected_breakpoints"]
    assert len(w.breakpoints) == len(expected)
    for bp, exp in zip(w.breakpoints, expected):
        assert bp.id == exp["id"]
        assert abs(bp.value - exp["value_inr"]) < 100.0, (
            f"{bp.id}: expected ₹{exp['value_inr']:,.0f}, got ₹{bp.value:,.0f}"
        )
        assert exp["event_contains"].lower() in bp.event.lower()


def test_findings_include_ratchet_flag_and_side_letter_scope(cap_table, ground_truth):
    findings = run_checklist(cap_table)
    codes = {f.code for f in findings}
    for required in ground_truth["expected_findings"]["must_include_codes"]:
        assert required in codes, f"missing required finding code: {required}"


def test_no_blockers_at_post_trigger_state(cap_table):
    """Once the ratchet has triggered and the cap table reflects the adjusted
    state, no fields should block waterfall computation."""
    findings = run_checklist(cap_table)
    blockers = [f for f in findings if f.severity == "blocker"]
    assert blockers == [], f"unexpected blockers: {[f.code for f in blockers]}"


def test_demo_route_loads_f04(monkeypatch):
    """End-to-end: /demo/fixture_04 redirects to a review page that renders."""
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/demo/fixture_04_down_round_ratchet", follow_redirects=True)
        assert r.status_code == 200
        body = r.data.decode()
        assert "Surya Foods" in body
        assert "full ratchet" in body.lower() or "full_ratchet" in body.lower()
    SESSIONS.clear()
