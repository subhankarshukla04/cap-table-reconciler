"""Rule-pack versioning tests (SYSTEM_SPEC §4.1, §8.15)."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.checklist import run_checklist
from src.models import (
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.rule_pack import (
    EngagementPackBinding,
    RulePack,
    current_engine_commit,
    head_pack,
    load_pack_from_file,
    registered_rule_ids,
    rule_metadata,
    run_pack,
    save_pack_to_file,
)


def _simple_ct() -> CapTable:
    return CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
            ShareClass(
                name="A",
                type=ShareClassType.preferred,
                shares_outstanding=1000,
                issue_price=1.0,
                issue_date=date(2024, 1, 1),
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating
                ),
                anti_dilution=None,  # triggers G-AD-001 blocker
            ),
        ],
    )


def test_baseline_pack_exists_and_loads():
    p = Path("rule_packs/v2026.1.0.json")
    assert p.exists(), "expected baseline pack at rule_packs/v2026.1.0.json"
    pack = load_pack_from_file(p)
    assert pack.version == "v2026.1.0"
    assert len(pack.rule_ids) == 8


def test_all_baseline_rules_registered():
    pack = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    for rid in pack.rule_ids:
        assert rule_metadata(rid) is not None, f"rule {rid} declared in pack but not registered"


def test_run_pack_matches_run_checklist_default():
    ct = _simple_ct()
    pack = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    a = run_pack(ct, pack=pack)
    b = run_checklist(ct, pack=pack)
    assert [f.code for f in a] == [f.code for f in b]


def test_engine_pack_skew_surfaces_as_meta_finding():
    """A pack referencing an unknown rule emits META-RULE-MISSING blocker."""
    pack = RulePack(
        version="v2099.0.0-test",
        effective_from=date.today(),
        rule_ids=["G-AD-001", "G-DOES-NOT-EXIST"],
    )
    findings = run_pack(_simple_ct(), pack=pack)
    codes = [f.code for f in findings]
    assert any("META-RULE-MISSING-G-DOES-NOT-EXIST" in c for c in codes)


def test_engagement_pack_binding_captures_engine_version():
    pack = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    binding = EngagementPackBinding.create("eng-test-001", pack)
    assert binding.engagement_id == "eng-test-001"
    assert binding.pack_version == "v2026.1.0"
    assert binding.engine_version != ""
    # Round-trips through JSON.
    blob = binding.model_dump_json()
    revived = EngagementPackBinding.model_validate_json(blob)
    assert revived == binding


def test_head_pack_returns_effective_pack_today():
    pack = head_pack()
    # Either the baseline pack or the dev fallback.
    assert pack.version in ("v2026.1.0", "v0.0.0-dev") or pack.version.startswith("v")


def test_jurisdiction_filter_excludes_untagged_when_target_set():
    """A jurisdiction-tagged rule fires only for matching engagements."""
    from src.rule_pack import _REGISTRY, rule

    # Synthesize an India-only rule for the test.
    @rule(
        id="G-TEST-IN-001",
        severity="info",
        category="india_only_test_rule",
        summary="Test rule tagged India only.",
        citation="test-only",
        jurisdictions=("IN",),
    )
    def _india_only(_ct):
        from src.checklist import Finding

        return [Finding(code="G-TEST-IN-001-FIRED", severity="info", category="t", summary="fired")]

    try:
        pack = RulePack(
            version="v0.0.0-test", effective_from=date.today(),
            rule_ids=["G-TEST-IN-001"],
        )
        in_findings = run_pack(_simple_ct(), pack=pack, engagement_jurisdiction="IN")
        sg_findings = run_pack(_simple_ct(), pack=pack, engagement_jurisdiction="SG")
        assert any(f.code == "G-TEST-IN-001-FIRED" for f in in_findings)
        assert not any(f.code == "G-TEST-IN-001-FIRED" for f in sg_findings)
    finally:
        _REGISTRY.pop("G-TEST-IN-001", None)


def test_pack_serializes_and_round_trips():
    p = Path("rule_packs/v2026.1.0.json")
    pack = load_pack_from_file(p)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as fh:
        out = Path(fh.name)
    try:
        save_pack_to_file(pack, out)
        revived = load_pack_from_file(out)
        assert revived == pack
    finally:
        out.unlink(missing_ok=True)


def test_current_engine_commit_returns_a_value():
    v = current_engine_commit()
    assert v  # either a short SHA or "unversioned"
