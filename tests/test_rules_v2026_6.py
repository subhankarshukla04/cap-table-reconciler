"""Tests for v2026.6.0 — depth pack to 60 rules (W5.6)."""

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
    ConvertibleNote,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.rule_pack import load_pack_from_file


def _pack():
    return load_pack_from_file(Path("rule_packs/v2026.6.0.json"))


def _common(shares=10_000_000):
    return ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=shares)


def _pref(name, rank=1, shares=1_000_000, price=1.0, date_=date(2024, 1, 1), subtype=None):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=price, issue_date=date_, seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=1, amount=price * shares, type=LPType.non_participating),
        anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
        instrument_subtype=subtype,
    )


def test_pack_v6_has_60_rules():
    pack = _pack()
    assert len(pack.rule_ids) == 60


# India FEMA -----------------------------------------------------------------


def test_g_in_002_fcy_price_floor():
    ct = CapTable(
        company=Company(name="X", jurisdiction="India", currency="USD"),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="IN")]
    assert any("IN-FEMA-FCY-PRICE-FLOOR" in c for c in codes)


def test_g_in_002_does_not_fire_for_inr():
    ct = CapTable(
        company=Company(name="X", jurisdiction="India", currency="INR"),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="IN")]
    assert not any("IN-FEMA-FCY-PRICE-FLOOR" in c for c in codes)


def test_g_in_003_down_round_consideration():
    ct = CapTable(
        company=Company(name="X", jurisdiction="India"),
        share_classes=[
            _common(),
            _pref("A", rank=2, price=2.0, date_=date(2023, 1, 1)),
            _pref("B", rank=1, price=1.0, date_=date(2024, 6, 1)),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="IN")]
    assert any("IN-FEMA-DOWNROUND-B" in c for c in codes)


def test_g_in_004_ccps_conversion_window():
    ct = CapTable(
        company=Company(name="X", jurisdiction="India"),
        share_classes=[
            _common(),
            _pref("A", subtype="CCPS"),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="IN")]
    assert any("IN-CCPS-CONV-WINDOW-A" in c for c in codes)


# Singapore IRAS -------------------------------------------------------------


def test_g_sg_001_iras_deemed_consideration():
    ct = CapTable(
        company=Company(name="X", jurisdiction="Singapore"),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="SG")]
    assert any("SG-IRAS-DEEMED" in c for c in codes)


def test_g_sg_002_fy_boundary_within_30_days():
    ct = CapTable(
        company=Company(name="X", jurisdiction="Singapore",
                        valuation_date=date(2026, 3, 25)),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="SG")]
    assert any("SG-IRAS-FY-BOUNDARY" in c for c in codes)


def test_g_sg_002_does_not_fire_mid_year():
    ct = CapTable(
        company=Company(name="X", jurisdiction="Singapore",
                        valuation_date=date(2026, 7, 1)),
        share_classes=[_common(), _pref("A")],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="SG")]
    assert not any("SG-IRAS-FY-BOUNDARY" in c for c in codes)


# US §409A -------------------------------------------------------------------


def test_g_us_001_presumption_lapsed():
    ct = CapTable(
        company=Company(name="X", jurisdiction="US-DE",
                        valuation_date=date(2026, 6, 1)),
        share_classes=[
            _common(),
            _pref("A", date_=date(2024, 1, 1)),  # ~29 months prior
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="US-DE")]
    assert any("US-409A-PRESUMPTION-LAPSED" in c for c in codes)


def test_g_us_002_material_event_on_down_round():
    ct = CapTable(
        company=Company(name="X", jurisdiction="US-DE"),
        share_classes=[
            _common(),
            _pref("A", rank=2, price=2.0, date_=date(2023, 1, 1)),
            _pref("B", rank=1, price=1.0, date_=date(2024, 1, 1)),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack(),
                                           engagement_jurisdiction="US-DE")]
    assert any("US-409A-MATERIAL-EVENT" in c for c in codes)


# AICPA OPM allocation triggers ---------------------------------------------


def test_g_aicpa_003_common_near_zero():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=100_000),
            _pref("A", price=10.0, shares=900_000),  # LP $9M
            _pref("B", rank=2, price=10.0, shares=900_000),  # LP $9M
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("AICPA-OPM-COMMON-NEAR-ZERO" in c for c in codes)


def test_g_aicpa_004_junior_otm():
    """Senior preferred LP > EV proxy → junior is deep-OTM → OPM."""
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=100),
            # Senior A with 5x LP: $50k LP vs EV proxy ($10 * 1110 = $11.1k)
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=10.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=5, amount=50_000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
            _pref("B", rank=2, price=10.0, shares=10),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("AICPA-OPM-JUNIOR-OTM-A" in c for c in codes)


# Convertible mechanics ----------------------------------------------------


def test_g_conv_002_maturity_past():
    ct = CapTable(
        company=Company(name="X", valuation_date=date(2026, 6, 1)),
        share_classes=[_common()],
        convertible_notes_outstanding=[
            ConvertibleNote(
                id="N1", principal=100_000,
                issue_date=date(2023, 1, 1),  # ~41 months earlier
            ),
        ],
    )
    codes = [f.code for f in run_checklist(ct, pack=_pack())]
    assert any("CONV-MATURITY-PAST-N1" in c for c in codes)
