"""Tests for v2026.3.0 expansion rules (W2.5)."""

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
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
    SideLetter,
)
from src.rule_pack import load_pack_from_file


def _pack():
    return load_pack_from_file(Path("rule_packs/v2026.3.0.json"))


def _common():
    return ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=10_000_000)


def _pref(name, rank=1, price=1.0, shares=1_000_000):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=price, issue_date=date(2024, 1, 1), seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=price * shares, type=LPType.non_participating),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
    )


def test_pack_has_30_rules():
    pack = _pack()
    assert len(pack.rule_ids) == 30


def test_g_de_001_delaware_overlay():
    ct = CapTable(
        company=Company(name="X", jurisdiction="US-DE"),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("DE-DGCL-OVERLAY" in c for c in codes)


def test_g_de_001_does_not_fire_outside_delaware():
    ct = CapTable(
        company=Company(name="X", jurisdiction="Singapore"),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert not any("DE-DGCL-OVERLAY" in c for c in codes)


def test_g_nvca_002_protective_provisions_missing():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        side_letters=[],  # no PP letter
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("NVCA-PP-MISSING" in c for c in codes)


def test_g_drag_001_drag_along_keyword():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        side_letters=[
            SideLetter(id="SL-1", title="Voting agreement",
                       summary="Drag-along at 67% trigger.", body=None),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("DRAG-SL-1" in c for c in codes)


def test_g_rofr_001_rofr_no_notice_period():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        side_letters=[
            SideLetter(id="SL-2", title="ROFR/Co-Sale",
                       summary="ROFR applies on all transfers.", body=None),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("ROFR-NOTICE-SL-2" in c for c in codes)


def test_g_aicpa_002_dlom_reminder_fires_when_common_present():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("AICPA-DLOM-REMINDER" in c for c in codes)


def test_g_aicpa_001_lp_overhang_fires_when_lp_dominates():
    """LP > 50% of PPS-implied enterprise value triggers Cheap-Stock §4.18."""
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=1_000_000),
            _pref("A", price=10.0, shares=1_000_000),
            _pref("B", rank=2, price=10.0, shares=1_000_000),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    # Total LP = $10M + $10M = $20M. Enterprise proxy = 10 * 3M = $30M.
    # Ratio = 67% > 50%. Should fire.
    assert any("AICPA-LP-OVERHANG" in c for c in codes)


def test_g_nvca_001_optional_clause_keyword():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A")],
        side_letters=[
            SideLetter(id="SL-3", title="Subscription side letter",
                       summary="Co-sale rights granted on founder transfers.",
                       body=None),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("NVCA-CLAUSE-SL-3" in c for c in codes)
