"""Parser tests against all three fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models import (
    AntiDilutionVariant,
    LPType,
    ShareClassType,
)
from src.parser import (
    _coerce_anti_dilution,
    _coerce_class_type,
    _coerce_lp_type,
    _detect_field_for_header,
    _parse_date,
    load_from_canonical_json,
    parse_excel,
)


FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---- Header detection ----


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Stakeholder / Class", "class_name"),
        ("Class Name", "class_name"),
        ("# Shares Outstanding", "shares"),
        ("Quantity", "shares"),
        ("Issue Price (USD)", "price"),
        ("PPS (USD)", "price"),
        ("Issue Date", "date"),
        ("Date Issued", "date"),
        ("LP Multiple", "lp_multiple"),
        ("Liq Pref", "lp_multiple"),
        ("LP Type", "lp_type"),
        ("Liq Type", "lp_type"),
        ("Anti-Dilution", "anti_dilution"),
        ("Conversion Ratio", "conversion_ratio"),
        ("Conv Ratio", "conversion_ratio"),
        ("Participation Cap (x of LP)", "participation_cap"),
        ("Voting Differential", "voting"),
        ("Notes", "notes"),
    ],
)
def test_header_detection(header, expected):
    assert _detect_field_for_header(header) == expected


# ---- Type coercion ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("common", ShareClassType.common),
        ("Common", ShareClassType.common),
        ("preferred", ShareClassType.preferred),
        ("ccps", ShareClassType.preferred),
        ("CCPS", ShareClassType.preferred),
        ("rcps", ShareClassType.preferred),
        ("option_pool_granted", ShareClassType.option_pool_granted),
        ("Option Pool (Granted)", ShareClassType.option_pool_granted),
        ("Option Pool (Reserved)", ShareClassType.option_pool_reserved),
        ("Preferred (CCPS)", ShareClassType.preferred),
        ("dual_class_voting_common", ShareClassType.common),
    ],
)
def test_class_type_coercion(raw, expected):
    assert _coerce_class_type(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("non_participating", LPType.non_participating),
        ("non-participating", LPType.non_participating),
        ("participating_capped", LPType.participating_capped),
        ("participating with cap", LPType.participating_capped),
        ("participating_uncapped", LPType.participating_uncapped),
    ],
)
def test_lp_type_coercion(raw, expected):
    assert _coerce_lp_type(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("broad_based_weighted_average", AntiDilutionVariant.broad_based_weighted_average),
        ("Broad-Based Weighted Average", AntiDilutionVariant.broad_based_weighted_average),
        ("BBWA", AntiDilutionVariant.broad_based_weighted_average),
        ("full_ratchet", AntiDilutionVariant.full_ratchet),
        ("Full Ratchet", AntiDilutionVariant.full_ratchet),
        ("ratchet", AntiDilutionVariant.full_ratchet),
    ],
)
def test_anti_dilution_coercion(raw, expected):
    assert _coerce_anti_dilution(raw) == expected


# ---- Date parsing ----


@pytest.mark.parametrize(
    "raw,year,month,day",
    [
        ("2024-02-08", 2024, 2, 8),
        ("Sep 12, 2021", 2021, 9, 12),
        ("September 12, 2021", 2021, 9, 12),
        ("11/4/2022", 2022, 11, 4),
        ("15-Mar-2026", 2026, 3, 15),
    ],
)
def test_date_parsing(raw, year, month, day):
    d = _parse_date(raw)
    assert d is not None
    assert (d.year, d.month, d.day) == (year, month, day)


# ---- Canonical JSON round-trip ----


@pytest.mark.parametrize(
    "fixture_dir",
    ["fixture_01_clean", "fixture_02_typical_messy", "fixture_03_edge_case"],
)
def test_canonical_json_loads(fixture_dir):
    inp = FIXTURES / fixture_dir / "cap_table_input.json"
    cap_table = load_from_canonical_json(inp)
    assert cap_table.company.name
    assert len(cap_table.share_classes) >= 4


def test_fixture_01_canonical_structure():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_01_clean" / "cap_table_input.json")
    assert cap_table.company.name == "Solstice Labs Pte. Ltd."
    assert cap_table.company.currency == "USD"
    classes_by_name = {sc.name: sc for sc in cap_table.share_classes}
    assert "Series B Preferred" in classes_by_name
    b = classes_by_name["Series B Preferred"]
    assert b.type == ShareClassType.preferred
    assert b.shares_outstanding == 3_000_000
    assert b.liquidation_preference is not None
    assert b.liquidation_preference.amount == 15_000_000
    assert b.liquidation_preference.type == LPType.non_participating


def test_fixture_03_participating_with_cap_loaded():
    cap_table = load_from_canonical_json(FIXTURES / "fixture_03_edge_case" / "cap_table_input.json")
    a = next(sc for sc in cap_table.share_classes if sc.name == "Series A CCPS")
    assert a.liquidation_preference.type == LPType.participating_capped
    assert a.liquidation_preference.cap_multiple == 3.0
    assert a.participation is not None
    assert a.participation.cap_multiple_of_lp == 3.0


# ---- Excel parser end-to-end ----


def test_parse_fixture_01_xlsx():
    cap_table, report = parse_excel(FIXTURES / "fixture_01_clean" / "cap_table.xlsx")
    assert report.cap_table_sheet == "Cap Table"
    assert "class_name" in report.column_mapping
    assert "shares" in report.column_mapping
    assert cap_table.company.name == "Solstice Labs Pte. Ltd."

    classes_by_name = {sc.name: sc for sc in cap_table.share_classes}
    assert len(classes_by_name) == 6  # 4 preferred + common + reserved + granted... actually 6: founders, seed, A, B, granted, reserved
    b = classes_by_name["Series B Preferred"]
    assert b.shares_outstanding == 3_000_000
    assert b.liquidation_preference is not None
    assert b.liquidation_preference.multiple == 1.0
    assert b.liquidation_preference.type == LPType.non_participating
    assert b.anti_dilution.variant == AntiDilutionVariant.broad_based_weighted_average


def test_parse_fixture_02_xlsx_handles_messy_headers_and_dates():
    cap_table, report = parse_excel(FIXTURES / "fixture_02_typical_messy" / "cap_table.xlsx")
    assert report.cap_table_sheet == "Cap Table"
    classes_by_name = {sc.name: sc for sc in cap_table.share_classes}
    a = classes_by_name["Series A Preferred"]
    # Anti-dilution was intentionally blank for Series A — variant should be None
    assert a.anti_dilution is None or a.anti_dilution.variant is None

    seed = classes_by_name["Series Seed Preferred"]
    assert seed.issue_date.year == 2022
    assert seed.issue_date.month == 11
    b = classes_by_name["Series B Preferred"]
    assert b.issue_date.year == 2026
    assert b.issue_date.month == 3
    founders = classes_by_name["Founders Common"]
    assert founders.issue_date.year == 2021
    assert founders.issue_date.month == 9

    # Convertibles tab should populate SAFEs and warrants
    assert len(cap_table.safes_outstanding) == 2
    assert len(cap_table.warrants_outstanding) == 1
    assert cap_table.warrants_outstanding[0].holder == "Northstar Marketing Pte. Ltd."


def test_parse_fixture_03_xlsx_inr_and_ccps():
    cap_table, report = parse_excel(FIXTURES / "fixture_03_edge_case" / "cap_table.xlsx")
    assert cap_table.company.currency == "INR"
    classes_by_name = {sc.name: sc for sc in cap_table.share_classes}
    a = classes_by_name["Series A CCPS"]
    # CCPS instrument type should map to preferred
    assert a.type == ShareClassType.preferred
    assert a.liquidation_preference.type == LPType.participating_capped
    assert a.liquidation_preference.cap_multiple == 3.0
    assert a.participation is not None
    assert a.participation.cap_multiple_of_lp == 3.0
    assert len(cap_table.side_letters) == 3
