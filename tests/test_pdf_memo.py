"""PDF audit memo tests (SYSTEM_SPEC §3.4, §8.16 XSS escaping)."""

from __future__ import annotations

from datetime import date

import pytest

from src.checklist import Finding, run_checklist
from src.models import (
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.pdf_memo import (
    PDFBlockersOutstanding,
    PDFInputs,
    PDFNoReviewer,
    ReviewerInfo,
    render_pdf_memo,
    render_pdf_memo_html,
)
from src.waterfall import compute_waterfall


def _ct_with_anti_dilution() -> CapTable:
    return CapTable(
        company=Company(name="Demo Co", currency="USD"),
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


def _ct_clean() -> CapTable:
    from src.models import AntiDilution, AntiDilutionVariant
    return CapTable(
        company=Company(name="Clean Co", currency="USD"),
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
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )


def test_refuses_without_named_reviewer():
    ct = _ct_clean()
    inputs = PDFInputs(
        cap_table=ct,
        waterfall=compute_waterfall(ct),
        findings=run_checklist(ct),
        resolutions=[],
        reviewer=None,
    )
    with pytest.raises(PDFNoReviewer) as exc:
        render_pdf_memo_html(inputs)
    assert exc.value.error_code == "pdf-no-reviewer"


def test_refuses_blocker_outstanding():
    ct = _ct_with_anti_dilution()
    inputs = PDFInputs(
        cap_table=ct,
        waterfall=compute_waterfall(ct),
        findings=run_checklist(ct),
        resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="A Reviewer"),
    )
    with pytest.raises(PDFBlockersOutstanding) as exc:
        render_pdf_memo_html(inputs)
    assert exc.value.error_code == "pdf-blockers-outstanding"
    assert exc.value.http_status == 409


def test_renders_when_blocker_resolved():
    ct = _ct_with_anti_dilution()
    findings = run_checklist(ct)
    blocker_code = next(f.code for f in findings if f.severity == "blocker")
    inputs = PDFInputs(
        cap_table=ct,
        waterfall=compute_waterfall(ct),
        findings=findings,
        resolutions=[
            {
                "finding_code": blocker_code,
                "decision_summary": "Broad-based weighted-average per Charter §4.3(a).",
                "citation": "Charter §4.3(a)",
                "resolved_by": "an-analyst",
            }
        ],
        reviewer=ReviewerInfo(reviewer_name="A Reviewer"),
    )
    html = render_pdf_memo_html(inputs)
    assert "Audit Memo" in html
    assert "A Reviewer" in html


def test_pdf_bytes_have_pdf_header():
    ct = _ct_clean()
    inputs = PDFInputs(
        cap_table=ct,
        waterfall=compute_waterfall(ct),
        findings=run_checklist(ct),
        resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="A Reviewer"),
    )
    pdf = render_pdf_memo(inputs)
    assert pdf[:4] == b"%PDF"
    # Sanity: more than just a stub
    assert len(pdf) > 5000


def test_xss_escaping_in_rendered_html():  # SYSTEM_SPEC §8.16
    """Holder/class names containing HTML special chars must be escaped."""
    from src.models import AntiDilution, AntiDilutionVariant
    ct = CapTable(
        company=Company(name="<script>alert(1)</script>", currency="USD"),
        share_classes=[
            ShareClass(name="Common </td><td>injection", type=ShareClassType.common, shares_outstanding=1),
            ShareClass(
                name="Series A & B",
                type=ShareClassType.preferred,
                shares_outstanding=1,
                issue_price=1.0,
                issue_date=date(2024, 1, 1),
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1, type=LPType.non_participating
                ),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )
    inputs = PDFInputs(
        cap_table=ct,
        waterfall=compute_waterfall(ct),
        findings=run_checklist(ct),
        resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="A Reviewer"),
    )
    html = render_pdf_memo_html(inputs)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "</td><td>injection" not in html
    assert "Series A &amp; B" in html
