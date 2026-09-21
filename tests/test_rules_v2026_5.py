"""Tests for v2026.5.0 expansion rules (W4.4 — reaches 50 rules)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from src.checklist import run_checklist
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    ConvertibleNote,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
    SideLetter,
    Warrant,
)
from src.rule_pack import load_pack_from_file


def _pack():
    return load_pack_from_file(Path("rule_packs/v2026.5.0.json"))


def _common(shares=10_000_000):
    return ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=shares)


def _pref(name, rank=1, shares=1_000_000, note=None, conv_ratio=None):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=shares * 1.0, type=LPType.non_participating),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
        note=note,
        conversion_ratio=conv_ratio,
    )


def test_pack_v5_has_50_rules():
    pack = _pack()
    assert len(pack.rule_ids) == 50


# ESOP ----------------------------------------------------------------------


def test_g_esop_001_reserved_without_granted():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            ShareClass(name="ESOP-Reserved", type=ShareClassType.option_pool_reserved,
                       shares_outstanding=500_000),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("ESOP-NO-GRANTS" in c for c in codes)


def test_g_esop_002_oversized_pool():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A", shares=100_000),
            ShareClass(name="ESOP", type=ShareClassType.option_pool_granted,
                       shares_outstanding=500_000),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("ESOP-OVER-PREFERRED" in c for c in codes)


def test_g_esop_003_early_exercise_silence_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A"),
            ShareClass(name="ESOP", type=ShareClassType.option_pool_granted,
                       shares_outstanding=100),
        ],
        side_letters=[],  # no early-exercise mention
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("ESOP-EARLY-EXERCISE-UNADDRESSED" in c for c in codes)


# Singapore VIMA ------------------------------------------------------------


def test_g_vima_001_only_fires_for_singapore():
    ct_sg = CapTable(company=Company(name="X", jurisdiction="Singapore"),
                     share_classes=[_common(), _pref("A")])
    ct_us = CapTable(company=Company(name="X", jurisdiction="US-DE"),
                     share_classes=[_common(), _pref("A")])
    sg_codes = [f.code for f in run_checklist(ct_sg, pack=_pack(),
                                              engagement_jurisdiction="SG")]
    us_codes = [f.code for f in run_checklist(ct_us, pack=_pack(),
                                              engagement_jurisdiction="US-DE")]
    assert any("VIMA-FOUNDER-VESTING" in c for c in sg_codes)
    assert not any("VIMA-FOUNDER-VESTING" in c for c in us_codes)


def test_g_vima_002_convertible_double_dip():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common()],
        convertible_notes_outstanding=[
            ConvertibleNote(
                id="N1", principal=100_000,
                valuation_cap=5_000_000,
                discount_rate=0.20,
                issue_date=date(2023, 1, 1),
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("VIMA-DOUBLE-DIP-N1" in c for c in codes)


# Indonesia OJK -------------------------------------------------------------


def test_g_ojk_001_only_for_indonesia():
    ct = CapTable(company=Company(name="X", jurisdiction="Indonesia"),
                  share_classes=[_common(), _pref("A")])
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="ID")]
    assert any("OJK-FOREIGN-OWNERSHIP" in c for c in codes)


# Audit-trail / reporting ---------------------------------------------------


def test_g_audit_001_long_lookback():
    ct = CapTable(
        company=Company(name="X", valuation_date=date(2026, 6, 1)),
        share_classes=[
            _common(),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=1.0, issue_date=date(2024, 1, 1),
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("AUDIT-OLD-LOOKBACK" in c for c in codes)


def test_g_audit_002_valuation_date_significantly_after_last_round():
    """W4-AUDIT M-2 fix: rule now compares against the cap-table's
    most-recent priced round, not date.today() (which violated
    determinism §6.6). Fires when valuation_date is > 18 months after
    the most recent round."""
    ct = CapTable(
        company=Company(name="X", valuation_date=date(2026, 6, 1)),
        share_classes=[
            _common(),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=1.0, issue_date=date(2024, 1, 1),  # 29mo before vd
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("AUDIT-VDATE-LATE" in c for c in codes)


# Preferred ----------------------------------------------------------------


def test_g_prf_001_dividend_keyword_in_note():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(),
                       _pref("A", note="Cumulative 6% dividend, declared annually.")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("PRF-DIVIDEND-A" in c for c in codes)


def test_g_prf_002_redemption_keyword_in_note():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(),
                       _pref("A", note="Redemption right after 7 years at issue price.")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("PRF-REDEMPTION-A" in c for c in codes)


# Capital ------------------------------------------------------------------


def test_g_cap_001_subpar_conversion_ratio():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[_common(), _pref("A", conv_ratio=0.5)],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("CAP-SUBPAR-CONVERT-A" in c for c in codes)


def test_g_cap_002_zero_share_class():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            ShareClass(name="Treasury", type=ShareClassType.common,
                       shares_outstanding=0),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("CAP-ZERO-SHARES-Treasury" in c for c in codes)


# Warrant ------------------------------------------------------------------


def test_g_war_002_expired_warrant_flagged():
    """W4-AUDIT M-2 fix: rule anchors against valuation_date (deterministic),
    not date.today(). Test sets valuation_date AFTER warrant expiry."""
    ct = CapTable(
        company=Company(name="X", valuation_date=date(2025, 1, 1)),
        share_classes=[_common()],
        warrants_outstanding=[
            Warrant(
                id="W1", holder="Lender Co", shares=10000,
                share_class="Common", strike_price=1.0,
                issue_date=date(2020, 1, 1), expiry_date=date(2024, 1, 1),
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("WAR-EXPIRED-W1" in c for c in codes)
