"""Structured snapshot diff tests (SYSTEM_SPEC §4.4)."""

from __future__ import annotations

from datetime import date

import pytest

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
from src.rule_pack import load_pack_from_file
from src.structured_diff import diff_snapshots
from pathlib import Path


def _np_pref(name, shares, rank, amt):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=amt / max(shares, 1), issue_date=date(2024, 1, 1),
        seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=amt, type=LPType.non_participating
        ),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
    )


def _ct(*classes, company_name="Demo Co"):
    return CapTable(
        company=Company(name=company_name, currency="USD"),
        share_classes=list(classes),
    )


def test_no_diff_for_identical_cap_tables():
    left = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
               _np_pref("A", 1000, 1, 1000))
    right = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
                _np_pref("A", 1000, 1, 1000))
    result = diff_snapshots(left, right)
    assert result.change_count == 0


def test_share_count_increase_detected():
    left = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
               _np_pref("A", 1000, 1, 1000))
    right = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1200),
                _np_pref("A", 1000, 1, 1000))
    result = diff_snapshots(left, right, right_snapshot_id="snap-002")
    target = next(d for d in result.diffs if d.path.endswith(".shares_outstanding"))
    assert target.change_type == "modified"
    assert target.old_value == 1000
    assert target.new_value == 1200
    assert target.source_snapshot == "snap-002"


def test_added_class_surfaces():
    left = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000))
    right = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
                _np_pref("A", 1000, 1, 1000))
    result = diff_snapshots(left, right)
    added_paths = [d.path for d in result.diffs if d.change_type == "added"]
    assert any("share_classes[A]" in p for p in added_paths)


def test_removed_class_surfaces():
    left = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
               _np_pref("A", 1000, 1, 1000))
    right = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000))
    result = diff_snapshots(left, right)
    removed_paths = [d.path for d in result.diffs if d.change_type == "removed"]
    assert any("share_classes[A]" in p for p in removed_paths)


def test_rename_detected_when_class_attributes_unchanged():
    left = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
               _np_pref("Series A", 1000, 1, 1000))
    right = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
                _np_pref("Series A Preferred", 1000, 1, 1000))
    result = diff_snapshots(left, right)
    renames = [d for d in result.diffs if d.change_type == "renamed"]
    assert len(renames) == 1
    assert renames[0].old_value == "Series A"
    assert renames[0].new_value == "Series A Preferred"
    # And no spurious "removed/added" diffs for the unchanged attributes.
    non_rename = [d for d in result.diffs if d.change_type != "renamed"]
    assert non_rename == []


def test_rule_implications_filled_when_pack_supplied():
    """A change that flips a rule's firing surfaces in rule_implications."""
    pack = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    # Left: anti_dilution present → G-AD-001 does NOT fire
    left = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
               _np_pref("A", 1000, 1, 1000))
    # Right: same class but with anti_dilution removed → G-AD-001 fires
    a_no_ad = ShareClass(
        name="A", type=ShareClassType.preferred, shares_outstanding=1000,
        issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=1000, type=LPType.non_participating
        ),
        anti_dilution=None,
    )
    right = _ct(ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
                a_no_ad)
    result = diff_snapshots(left, right, pack=pack)
    impl = next(d for d in result.diffs if d.path == "$rule_pack.findings_delta")
    assert any("AD-MISSING" in c for c in impl.rule_implications)


def test_determinism_repeated_call_returns_identical_diffs():
    left = _ct(_np_pref("A", 1000, 1, 1000),
               ShareClass(name="C", type=ShareClassType.common, shares_outstanding=2000))
    right = _ct(_np_pref("A", 1500, 1, 1500),
                ShareClass(name="C", type=ShareClassType.common, shares_outstanding=2000))
    a = diff_snapshots(left, right)
    b = diff_snapshots(left, right)
    assert a.diffs == b.diffs
