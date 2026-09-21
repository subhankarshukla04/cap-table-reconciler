"""Verify the checklist surfaces the planted gaps in each fixture."""

from __future__ import annotations

from pathlib import Path

from src.checklist import run_checklist
from src.parser import load_from_canonical_json


FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_fixture_01_clean_has_no_blockers_or_warnings():
    """The fixture was curated against the wave-1 baseline pack (8 rules).
    Later packs add heuristic warnings (NVCA-PP-MISSING, ESOP-EARLY-EXERCISE-
    UNADDRESSED, etc.) that this fixture intentionally doesn't satisfy.
    Pin to the v1 pack to honour the original curation intent. The wave-5
    test_rules_v2026_5 + wave-4 tests cover the newer-pack behaviour
    against fixtures tailored for those rules."""
    from src.rule_pack import load_pack_from_file
    cap_table = load_from_canonical_json(FIXTURES / "fixture_01_clean" / "cap_table_input.json")
    v1_pack = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    findings = run_checklist(cap_table, pack=v1_pack)
    blockers = [f for f in findings if f.severity == "blocker"]
    warnings = [f for f in findings if f.severity == "warning"]
    assert blockers == [], f"clean fixture should not produce blockers: {[f.code for f in blockers]}"
    assert warnings == [], f"clean fixture should not produce warnings: {[f.code for f in warnings]}"


def test_fixture_02_messy_flags_anti_dilution_blank():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_02_typical_messy" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    codes = {f.code for f in findings}
    assert "AD-MISSING-Series A Preferred" in codes


def test_fixture_02_messy_flags_stale_option_pool():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_02_typical_messy" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    pool_findings = [f for f in findings if f.category == "stale_option_pool"]
    assert len(pool_findings) == 1
    assert pool_findings[0].severity == "warning"


def test_fixture_02_messy_flags_unrecorded_safes():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_02_typical_messy" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    safe_findings = [f for f in findings if f.category == "unrecorded_safe_conversion"]
    assert len(safe_findings) == 2  # both SAFEs should be flagged
    for f in safe_findings:
        assert f.severity == "blocker"


def test_fixture_02_messy_flags_warrant():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_02_typical_messy" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    warrant_findings = [f for f in findings if f.category == "unrecorded_warrant"]
    assert len(warrant_findings) == 1


def test_fixture_02_messy_flags_side_letter_scope_unresolved():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_02_typical_messy" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    # Body is now populated, but the side letter has unresolved scope questions
    scope_findings = [f for f in findings if f.category == "side_letter_scope_unresolved"]
    assert len(scope_findings) == 1
    assert scope_findings[0].severity == "warning"
    assert "MFN" in scope_findings[0].detail or "anti-dilution" in scope_findings[0].detail.lower()


def test_fixture_03_flags_full_ratchet_info():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    ratchet_findings = [f for f in findings if f.category == "anti_dilution_full_ratchet_documented"]
    assert len(ratchet_findings) == 1
    assert ratchet_findings[0].severity == "info"


def test_fixture_03_flags_participating_with_cap_info():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    cap_findings = [f for f in findings if f.category == "participating_with_cap_documented"]
    assert len(cap_findings) == 1
    assert cap_findings[0].severity == "info"


def test_fixture_03_flags_dual_class_voting():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    voting_findings = [f for f in findings if f.category == "dual_class_voting_documented"]
    assert len(voting_findings) == 1


def test_findings_sorted_by_severity():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_02_typical_messy" / "cap_table_input.json")
    findings = run_checklist(cap_table)
    sev_order = {"blocker": 0, "warning": 1, "info": 2}
    seen = -1
    for f in findings:
        assert sev_order[f.severity] >= seen
        seen = sev_order[f.severity]
