"""Tests for the DRHP parser + adapter."""
from __future__ import annotations

from pathlib import Path

import pytest

from radar import adapter, drhp_parser
from radar.models import ParsedDRHP

ROOT = Path(__file__).resolve().parent.parent.parent
DRHP_DIR = ROOT / "data" / "drhp"


@pytest.fixture(scope="module")
def parsed_pinelabs() -> ParsedDRHP:
    return drhp_parser.parse(DRHP_DIR / "pinelabs_drhp.pdf", fixture_hint="pinelabs")


@pytest.fixture(scope="module")
def parsed_razorpay() -> ParsedDRHP:
    return drhp_parser.parse(DRHP_DIR / "razorpay_drhp.pdf", fixture_hint="razorpay")


def test_parser_extracts_legal_name(parsed_pinelabs):
    assert "Pine Labs" in parsed_pinelabs.legal_name


def test_parser_extracts_state_and_founded(parsed_pinelabs):
    assert parsed_pinelabs.registered_state == "Karnataka"
    assert parsed_pinelabs.founded_year == 1998


def test_parser_extracts_shareholding(parsed_pinelabs):
    assert len(parsed_pinelabs.shareholding) == 10
    classes = {h.class_ for h in parsed_pinelabs.shareholding}
    assert "Common" in classes
    assert "ESOP" in classes


def test_parser_finds_sections(parsed_razorpay):
    found = set(parsed_razorpay.sections_found)
    for required in ("CAPITAL STRUCTURE", "BUILD-UP OF SHARE CAPITAL",
                     "LOCK-IN PERIODS", "ROFR / ROFO CLAUSES"):
        assert required in found, f"missing {required} in {found}"


def test_parser_extracts_employee_count(parsed_razorpay):
    assert parsed_razorpay.employee_count == 3000


def test_parser_extracts_lock_in_periods(parsed_pinelabs):
    assert len(parsed_pinelabs.lock_in_periods) >= 1
    cats = [lp.category for lp in parsed_pinelabs.lock_in_periods]
    assert any("Promoter" in c for c in cats)


def test_parser_extracts_rofr(parsed_pinelabs):
    assert "ROFR" in parsed_pinelabs.rofr_clause_summary.upper()


def test_adapter_produces_issuer_and_holders(parsed_pinelabs):
    issuer, holders = adapter.adapt(parsed_pinelabs)
    assert issuer.legal_name == parsed_pinelabs.legal_name
    assert issuer.state == "Karnataka"
    assert issuer.geography == "IN"
    # ESOP fan-out + institutional rows
    assert len(holders) > 100
    assert any(h.class_ == "ESOP" for h in holders)
    assert any(h.class_ == "Common" for h in holders)


def test_adapter_handles_razorpay_high_foreign_pct(parsed_razorpay):
    issuer, holders = adapter.adapt(parsed_razorpay)
    # Razorpay has ~62% foreign holders per DRHP; adapter biases ESOP residency accordingly
    foreign_count = sum(1 for h in holders if h.residency in ("foreign", "singapore_resident"))
    assert foreign_count > 0


def test_parser_handles_unknown_pdf_gracefully(tmp_path):
    # Generate a minimal valid PDF that doesn't match DRHP grammar
    from reportlab.pdfgen import canvas
    p = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(100, 100, "Not a DRHP")
    c.showPage()
    c.save()

    parsed = drhp_parser.parse(p)
    assert parsed.source_file == "blank.pdf"
    assert parsed.pages_processed >= 1
    # No matching sections, so the list is empty — but no crash
    assert parsed.shareholding == []
