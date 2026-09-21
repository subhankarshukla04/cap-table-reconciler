"""Tests for v2026.4.0 protective-provisions / ROFR / drag-along rules (W3.6)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.checklist import run_checklist
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    DragAlongTerms,
    LiquidationPreference,
    LPType,
    ProtectiveProvision,
    ROFRTerms,
    ShareClass,
    ShareClassType,
)
from src.rule_pack import load_pack_from_file


def _pack():
    return load_pack_from_file(Path("rule_packs/v2026.4.0.json"))


def _common():
    return ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=10_000_000)


def _pref(name, rank=1):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=1_000_000,
        issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=1_000_000, type=LPType.non_participating),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
    )


def test_pack_v4_has_37_rules():
    pack = _pack()
    assert len(pack.rule_ids) == 37


def test_g_pp_001_empty_protective_provisions_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        protective_provisions=[],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("PP-EMPTY" in c for c in codes)


def test_g_pp_001_not_flagged_with_provisions():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        protective_provisions=[
            ProtectiveProvision(
                name="amend_charter",
                consent_threshold_pct=51,
                consenting_class_names=["A"],
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert not any("PP-EMPTY" in c for c in codes)


def test_g_pp_002_supermajority_threshold_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        protective_provisions=[
            ProtectiveProvision(
                name="issue_senior_security",
                consent_threshold_pct=75,
                consenting_class_names=["A"],
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("PP-SUPERMAJORITY-issue_senior_security" in c for c in codes)


def test_g_pp_003_no_consenting_class_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        protective_provisions=[
            ProtectiveProvision(name="amend_charter", consent_threshold_pct=51),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("PP-NO-CONSENTER-amend_charter" in c for c in codes)


def test_g_rofr_002_short_notice_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        rofr_terms=ROFRTerms(notice_period_days=7),
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("ROFR-SHORT-NOTICE" in c for c in codes)


def test_g_drag_002_threshold_outside_band_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        drag_along_terms=DragAlongTerms(threshold_pct=90.0, drag_classes=["Common"]),
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("DRAG-THRESHOLD-ATYPICAL" in c for c in codes)


def test_g_drag_003_empty_drag_classes_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        drag_along_terms=DragAlongTerms(threshold_pct=60.0, drag_classes=[]),
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("DRAG-CLASSES-EMPTY" in c for c in codes)


def test_g_xref_001_drag_without_rofr_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        drag_along_terms=DragAlongTerms(threshold_pct=60.0, drag_classes=["Common"]),
        rofr_terms=None,
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("XREF-DRAG-NO-ROFR" in c for c in codes)


def test_legacy_cap_table_without_new_fields_still_validates():
    """A CapTable JSON that omits protective_provisions / rofr / drag must
    still validate — backward compat for the new fields."""
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
    )
    # No exception → backward compat works.
    assert ct.protective_provisions == []
    assert ct.rofr_terms is None
    assert ct.drag_along_terms is None
