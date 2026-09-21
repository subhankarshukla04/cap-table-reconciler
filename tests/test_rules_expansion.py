"""Tests for the v2026.2.0 rule-pack expansion (SYSTEM_SPEC §4.1)."""

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
    SAFE,
    ShareClass,
    ShareClassType,
    SideLetter,
)
from src.rule_pack import load_pack_from_file


def _expansion_pack():
    return load_pack_from_file(Path("rule_packs/v2026.2.0.json"))


def _common():
    return ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=10_000_000)


def _pref(name, rank, *, ad=None, ratio=None, sub=0, lp_mult=1.0,
          lp_type=LPType.non_participating, price=1.0, shares=1_000_000,
          date_=date(2024, 1, 1)):
    kwargs = dict(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=price, issue_date=date_, seniority_rank=rank, seniority_sub_rank=sub,
        liquidation_preference=LiquidationPreference(
            multiple=lp_mult, amount=lp_mult * price * shares, type=lp_type,
        ),
    )
    if ad is not None:
        kwargs["anti_dilution"] = AntiDilution(variant=ad)
    if ratio is not None:
        kwargs["conversion_ratio"] = ratio
    return ShareClass(**kwargs)


def test_pack_v2_loads_with_23_rules():
    pack = _expansion_pack()
    assert pack.version == "v2026.2.0"
    assert len(pack.rule_ids) == 23
    assert "G-AD-001" in pack.rule_ids
    assert "G-AD-005" in pack.rule_ids
    assert "G-IN-001" in pack.rule_ids


def test_g_ad_004_triggered_ratchet_fires():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A", rank=1, ad=AntiDilutionVariant.full_ratchet, ratio=1.5),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("AD-TRIGGERED-A" in c for c in codes)


def test_g_lp_003_lp_multiple_above_one():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A", rank=1, ad=AntiDilutionVariant.broad_based_weighted_average, lp_mult=2.0),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("LP-MULT-ABOVE-1-A" in c for c in codes)


def test_g_safe_002_mfn_only_safe_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A", rank=1, ad=AntiDilutionVariant.broad_based_weighted_average,
                  date_=date(2024, 6, 1)),
        ],
        safes_outstanding=[
            SAFE(
                id="MFN-1",
                principal=100_000,
                issue_date=date(2023, 1, 1),
                valuation_cap=None,
                discount_rate=None,
                conversion_trigger_threshold=None,
            )
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("SAFE-MFN-ONLY-MFN-1" in c for c in codes)


def test_g_round_001_down_round_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A", rank=2, ad=AntiDilutionVariant.broad_based_weighted_average,
                  price=2.0, date_=date(2023, 1, 1)),
            _pref("B", rank=1, ad=AntiDilutionVariant.broad_based_weighted_average,
                  price=1.0, date_=date(2024, 6, 1)),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("DOWN-ROUND-B" in c for c in codes)


def test_g_ad_005_pari_passu_inconsistent_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("B-1", rank=1, sub=1, ad=AntiDilutionVariant.broad_based_weighted_average),
            _pref("B-2", rank=1, sub=2, ad=AntiDilutionVariant.full_ratchet),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("AD-PARI-PASSU-INCONSISTENT-1" in c for c in codes)


def test_g_in_001_jurisdiction_filtered_when_engagement_jurisdiction_given():
    ct = CapTable(
        company=Company(name="X", jurisdiction="India"),
        share_classes=[
            _common(),
            _pref("A", rank=1, ad=AntiDilutionVariant.broad_based_weighted_average),
        ],
    )
    pack = _expansion_pack()
    in_codes = {f.code for f in run_checklist(ct, pack=pack, engagement_jurisdiction="IN")}
    sg_codes = {f.code for f in run_checklist(ct, pack=pack, engagement_jurisdiction="SG")}
    assert any("IN-FEMA-OVERLAY" in c for c in in_codes)
    assert not any("IN-FEMA-OVERLAY" in c for c in sg_codes)


def test_g_curr_001_currency_jurisdiction_mismatch_flagged():
    ct = CapTable(
        company=Company(name="X", jurisdiction="India", currency="USD"),
        share_classes=[
            _common(),
            _pref("A", rank=1, ad=AntiDilutionVariant.broad_based_weighted_average),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("CURR-JURIS-MISMATCH" in c for c in codes)


def test_g_sl_002_mfn_side_letter_flagged():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            _common(),
            _pref("A", rank=1, ad=AntiDilutionVariant.broad_based_weighted_average),
        ],
        side_letters=[
            SideLetter(id="SL-1", title="Anchor LP", summary="MFN clause applies",
                       body=None),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_expansion_pack())]
    assert any("SL-MFN-SL-1" in c for c in codes)
