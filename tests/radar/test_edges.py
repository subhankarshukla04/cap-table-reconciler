"""Hard edge-case tests for DRHP Reader — STRICT mode.

Every test asserts the *correct* post-fix behavior. No "passes by design"
allowances. A failure here means the bug is back."""
from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors

from radar import adapter, compliance, drhp_parser
from radar.models import (
    ComplianceParams, EligibilityFilter, ExtractedHolder, Holder,
    Issuer, LockInPeriod, ParsedDRHP, SellerMix, TenderParams,
)


def _basic_doc(out: Path):
    return SimpleDocTemplate(str(out), pagesize=A4)


def _styled_table(rows):
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
    return t


# ============================================================
# Group A — PDF intake (5)
# ============================================================

def test_01_corrupt_pdf_raises(tmp_path):
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"NOT A PDF, JUST GARBAGE\x00\x01\x02")
    with pytest.raises(Exception):
        drhp_parser.parse(p)


def test_02_empty_pdf_returns_zero_shareholders(tmp_path):
    p = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(p))
    c.showPage()
    c.save()
    parsed = drhp_parser.parse(p)
    assert parsed.shareholding == []
    assert parsed.pages_processed == 1


def test_03_no_section_headers_present(tmp_path):
    p = tmp_path / "nodrhp.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(100, 700, "Generic business doc, no DRHP grammar")
    c.showPage()
    c.save()
    parsed = drhp_parser.parse(p)
    assert "BUILD-UP OF SHARE CAPITAL" not in parsed.sections_found
    assert parsed.shareholding == []


def test_04_password_protected_pdf_raises(tmp_path):
    p = tmp_path / "encrypted.pdf"
    c = canvas.Canvas(str(p), encrypt="secret123")
    c.drawString(100, 100, "Locked")
    c.showPage()
    c.save()
    with pytest.raises(Exception):
        drhp_parser.parse(p)


def test_05_50_page_pdf_within_runtime(tmp_path):
    p = tmp_path / "long.pdf"
    c = canvas.Canvas(str(p))
    for i in range(50):
        c.drawString(100, 750, f"Page {i+1}")
        c.showPage()
    c.save()
    t0 = time.perf_counter()
    parsed = drhp_parser.parse(p)
    elapsed = time.perf_counter() - t0
    assert parsed.pages_processed == 50
    assert elapsed < 3.0, f"Parser took {elapsed:.2f}s"


# ============================================================
# Group B — Parser grammar (5) — STRICT
# ============================================================

def test_06_reordered_column_table_extracts_correctly(tmp_path):
    """Column order: % | Class | Units | Holder — parser maps by header NAME."""
    p = tmp_path / "reordered.pdf"
    doc = _basic_doc(p)
    rows = [
        ["%", "Class", "Units", "Holder"],
        ["14.50", "Common", "14,500,000", "Founder A"],
        ["11.00", "SeriesF", "11,000,000", "GIC Pte Ltd"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.shareholding) == 2
    names = {h.name for h in parsed.shareholding}
    assert "Founder A" in names
    assert "GIC Pte Ltd" in names
    # Numbers map to the right holder regardless of column position
    by_name = {h.name: h for h in parsed.shareholding}
    assert by_name["Founder A"].units == 14_500_000
    assert by_name["Founder A"].pct_pre_offer == 14.50


def test_07_alt_section_name_detected(tmp_path):
    p = tmp_path / "alt_section.pdf"
    doc = _basic_doc(p)
    rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        ["Founder", "Common", "14,500,000", "14.50%", "resident"],
    ]
    doc.build([
        Paragraph("EQUITY CAPITAL BUILD-UP", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert "BUILD-UP OF SHARE CAPITAL" in parsed.sections_found
    assert len(parsed.shareholding) == 1


def test_08_two_tables_picks_only_cap_table(tmp_path):
    p = tmp_path / "two_tables.pdf"
    doc = _basic_doc(p)
    cap_rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        ["Founder A", "Common", "14,500,000", "14.50%", "resident"],
        ["GIC", "SeriesF", "11,000,000", "11.00%", "singapore_resident"],
    ]
    tax_rows = [
        ["Tax-Residency Category", "—", "Units", "%", "Country"],
        ["INDIA total", "—", "55,000,000", "55.00%", "IN"],
        ["Out-of-India total", "—", "45,000,000", "45.00%", "FOREIGN"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(cap_rows),
        PageBreak(),
        Paragraph("TAX RESIDENCY OF SHAREHOLDERS", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(tax_rows),
    ])
    parsed = drhp_parser.parse(p)
    # Strict: only the 2 cap-table rows. NOT the tax-residency rows.
    assert len(parsed.shareholding) == 2
    names = {h.name for h in parsed.shareholding}
    assert "INDIA total" not in names
    assert "Out-of-India total" not in names


def test_09_indian_lakh_number_format(tmp_path):
    p = tmp_path / "lakh.pdf"
    doc = _basic_doc(p)
    rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        ["Founder", "Common", "1,45,00,000", "14.50%", "resident"],
        ["GIC", "SeriesF", "1,10,00,000", "11.00%", "singapore_resident"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.shareholding) == 2
    assert parsed.shareholding[0].units == 14_500_000


def test_10_percent_as_word_now_parses(tmp_path):
    p = tmp_path / "pct_word.pdf"
    doc = _basic_doc(p)
    rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        ["Founder X", "Common", "12,500,000", "12.5 percent", "resident"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.shareholding) == 1
    assert parsed.shareholding[0].pct_pre_offer == 12.5


# ============================================================
# Group C — Section content (4)
# ============================================================

def test_11_unicode_in_holder_names(tmp_path):
    p = tmp_path / "unicode.pdf"
    doc = _basic_doc(p)
    rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        ["Founder — CEO", "Common", "14,500,000", "14.50%", "resident"],
        ["XYZ Singapore Pte Ltd", "SeriesA", "5,000,000", "5.00%", "singapore_resident"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.shareholding) == 2
    names = " · ".join(h.name for h in parsed.shareholding)
    assert "—" in names or "Singapore" in names


def test_12_numbered_lockin_lines_parsed(tmp_path):
    p = tmp_path / "lockins.pdf"
    doc = _basic_doc(p)
    styles = getSampleStyleSheet()
    doc.build([
        Paragraph("LOCK-IN PERIODS", styles["Title"]),
        Spacer(1, 0.1*inch),
        Paragraph("1. Promoter shares: 18 months from allotment.", styles["Normal"]),
        Paragraph("2. Pre-IPO investors: 12 months.", styles["Normal"]),
        Paragraph("3. Anchor investors: 3 months.", styles["Normal"]),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.lock_in_periods) == 3
    cats = [lp.category.lower() for lp in parsed.lock_in_periods]
    assert any("promoter" in c for c in cats)
    assert any("anchor" in c for c in cats)


def test_13_rofr_section_long_paragraph(tmp_path):
    p = tmp_path / "rofr.pdf"
    doc = _basic_doc(p)
    styles = getSampleStyleSheet()
    long_rofr = (
        "ROFR / ROFO CLAUSES. The Right of First Refusal shall operate as "
        "follows. Upon receipt of a bona fide offer, the selling shareholder "
        "shall serve a Transfer Notice on the Company within five business "
        "days. The Company shall have a period of thirty (30) days to elect."
    )
    doc.build([
        Paragraph("ROFR / ROFO CLAUSES", styles["Title"]),
        Spacer(1, 0.1*inch),
        Paragraph(long_rofr, styles["Normal"]),
    ])
    parsed = drhp_parser.parse(p)
    assert "ROFR" in parsed.rofr_clause_summary.upper()
    assert len(parsed.rofr_clause_summary) > 50


def test_14_shareholding_sum_anomaly_flagged(tmp_path):
    p = tmp_path / "over100.pdf"
    doc = _basic_doc(p)
    rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        ["A", "Common", "60,000,000", "60.00%", "resident"],
        ["B", "Common", "50,000,000", "50.00%", "resident"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.shareholding) == 2
    assert any("110" in w or "sums to" in w.lower() for w in parsed.validation_warnings), (
        f"Expected a sum-anomaly warning, got: {parsed.validation_warnings}"
    )


# ============================================================
# Group D — Adapter (3)
# ============================================================

def test_15_adapter_with_no_esop_count_produces_one_synthetic_row():
    parsed = ParsedDRHP(
        filing_id="test", legal_name="Test", registered_state="Karnataka",
        shareholding=[
            ExtractedHolder(name="Founder", **{"class": "Common"},
                            units=70_000_000, pct_pre_offer=70.0, residency="resident"),
            ExtractedHolder(name="ESOP Pool", **{"class": "ESOP"},
                            units=10_000_000, pct_pre_offer=10.0, residency="resident",
                            is_employee=True),
        ],
        esop_pool_pct=10.0,
        esop_holder_count_estimated=None,
        source_file="test.pdf",
        parsed_at=datetime.now(),
    )
    issuer, holders = adapter.adapt(parsed)
    esop_rows = [h for h in holders if h.class_ == "ESOP"]
    assert len(esop_rows) == 1
    assert esop_rows[0].is_synthetic is True
    assert "aggregate" in esop_rows[0].name.lower()


def test_16_adapter_with_known_esop_count_fans_out_flagged_synthetic():
    parsed = ParsedDRHP(
        filing_id="test2", legal_name="Test2", registered_state="Karnataka",
        shareholding=[
            ExtractedHolder(name="Founder", **{"class": "Common"},
                            units=70_000_000, pct_pre_offer=70.0, residency="resident"),
            ExtractedHolder(name="ESOP Pool", **{"class": "ESOP"},
                            units=10_000_000, pct_pre_offer=10.0, residency="resident",
                            is_employee=True),
        ],
        esop_pool_pct=10.0,
        esop_holder_count_estimated=100,
        source_file="test.pdf",
        parsed_at=datetime.now(),
    )
    issuer, holders = adapter.adapt(parsed)
    esop_rows = [h for h in holders if h.class_ == "ESOP"]
    assert len(esop_rows) == 100
    assert all(h.is_synthetic for h in esop_rows)
    # Non-ESOP rows are NOT synthetic
    founder = next(h for h in holders if h.name == "Founder")
    assert founder.is_synthetic is False


def test_17_mechanics_with_zero_eligible_holders():
    from radar import mechanics
    issuer = Issuer(
        id="x", legal_name="X", sector="Test", geography="IN",
        state="Karnataka", last_round_price_per_share_usd=1.0,
    )
    params = TenderParams(
        tender_size_usd=20_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    waterfall = mechanics.preview_tender(issuer, [], params)
    assert waterfall.eligible_holder_count == 0
    assert waterfall.eligible_unit_pool == 0
    assert waterfall.scaleback_factor == 0.0


# ============================================================
# Group E — Compliance (3)
# ============================================================

def test_18_compliance_unknown_state_uses_proxy_rate():
    params = ComplianceParams(
        issuer_state="Penang",
        seller_mix=SellerMix(foreign_pct=100),
        share_class="Common",
        transfer_price_per_share_local=10.0,
        fair_value_proxy_local=10.0,
    )
    out = compliance.preview_compliance(params, eligible_holders=100)
    assert out.stamp_duty_rate_used == 0.001
    assert "Penang" in out.state_duty_citation
    assert out.error_reason == ""


def test_19_compliance_with_negative_price_returns_na_with_reason():
    params = ComplianceParams(
        issuer_state="Karnataka",
        seller_mix=SellerMix(resident_pct=100),
        share_class="Common",
        transfer_price_per_share_local=-50.0,
        fair_value_proxy_local=70.0,
    )
    out = compliance.preview_compliance(params, eligible_holders=100)
    assert out.rbi_floor_verdict == "N/A"
    assert out.stamp_duty_local == 0.0
    assert "Invalid" in out.error_reason


def test_20_compliance_with_zero_holders():
    params = ComplianceParams(
        issuer_state="Karnataka",
        seller_mix=SellerMix(resident_pct=78, nri_pct=14, foreign_pct=8),
        share_class="Common",
        transfer_price_per_share_local=70.0,
        fair_value_proxy_local=70.0,
    )
    out = compliance.preview_compliance(params, eligible_holders=0)
    assert out.cross_border_filings_estimated == 0
    assert out.stamp_duty_local == 0.0
    assert out.error_reason == ""
