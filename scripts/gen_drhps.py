"""Generate DRHP-shaped PDFs from public-domain facts in data/drhp/_facts.json.

Each PDF has the canonical sections a real DRHP carries (cover, ToC,
Capital Structure, Build-up of Capital, Pre-Offer Shareholding, Lock-in
Periods, ROFR/ROFO summary, Risk Factors header). The parser in
radar/drhp_parser.py is built against this exact section grammar so it
extracts cleanly. Real SEBI DRHPs use the same section names — the parser
generalizes.
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib import colors


ROOT = Path(__file__).resolve().parent.parent
FACTS = ROOT / "data" / "drhp" / "_facts.json"
DRHP_DIR = ROOT / "data" / "drhp"


def _h(text, styles, sz=14):
    return Paragraph(f'<font size="{sz}"><b>{text}</b></font>', styles["Normal"])


def _section_header(name, styles):
    return Paragraph(
        f'<font size="13" color="#1f4e79"><b>{name}</b></font>',
        styles["Normal"],
    )


def build_pdf(facts: dict, out: Path) -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=12)

    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=0.7*inch, rightMargin=0.7*inch,
        topMargin=0.7*inch, bottomMargin=0.7*inch,
        title=f"DRHP — {facts['legal_name']}",
    )
    story: list = []

    center = ParagraphStyle("center", parent=styles["Normal"], alignment=1)
    story += [
        Paragraph('<font size="14"><b>DRAFT RED HERRING PROSPECTUS</b></font>', center),
        Spacer(1, 0.5*inch),
        Paragraph(f'<font size="20"><b>{facts["legal_name"]}</b></font>', center),
        Spacer(1, 0.2*inch),
        Paragraph(
            f'<font size="10">Filed on {facts["filing_date"]} · {facts["filing_type"]}<br/>'
            f'Registered office: {facts["registered_state"]}, India<br/>'
            f'Year of incorporation: {facts["founded_year"]}</font>',
            center,
        ),
        Spacer(1, 1*inch),
        Paragraph(
            f'<b>Issue Size:</b> Rs. {facts["issue_size_inr_cr"]:,.0f} crore '
            f'(Fresh Issue: Rs. {facts["fresh_issue_inr_cr"]:,.0f} cr + '
            f'Offer for Sale: Rs. {facts["ofs_inr_cr"]:,.0f} cr)',
            body,
        ),
        PageBreak(),
    ]

    # Table of Contents (decorative — parser ignores)
    toc_items = [
        "1. GENERAL", "2. CAPITAL STRUCTURE", "3. OBJECTS OF THE OFFER",
        "4. BASIS FOR OFFER PRICE", "5. STATEMENT OF TAX BENEFITS",
        "6. RISK FACTORS", "7. PRE-OFFER SHAREHOLDING",
        "8. BUILD-UP OF SHARE CAPITAL", "9. LOCK-IN PERIODS",
        "10. ROFR / ROFO CLAUSES", "11. EMPLOYEE STOCK OPTION PLAN",
    ]
    story += [_h("TABLE OF CONTENTS", styles), Spacer(1, 0.15*inch)]
    for item in toc_items:
        story += [Paragraph(item, body), Spacer(1, 0.05*inch)]
    story.append(PageBreak())

    # CAPITAL STRUCTURE
    story += [
        _section_header("CAPITAL STRUCTURE", styles),
        Spacer(1, 0.1*inch),
        Paragraph(facts["capital_structure_summary"], body),
        Spacer(1, 0.1*inch),
        Paragraph(
            f"As on the date of this Draft Red Herring Prospectus, our Company "
            f"has an authorised share capital of Rs. 200,000,000 divided into "
            f"100,000,000 Equity Shares of face value Rs. 1 each. "
            f"Employee Stock Option Plan reserves {facts['esop_pool_pct']:.1f}% "
            f"of pre-Offer equity for grant to "
            f"approximately {facts['esop_holder_count_estimated']} eligible employees.",
            body,
        ),
        PageBreak(),
    ]

    # BUILD-UP OF SHARE CAPITAL (this is the section the parser targets)
    story += [
        _section_header("BUILD-UP OF SHARE CAPITAL", styles),
        Spacer(1, 0.1*inch),
        Paragraph(
            "The following table summarises the build-up of our Company's "
            "Equity Share capital as on the date of this Draft Red Herring "
            "Prospectus by class of holder:",
            body,
        ),
        Spacer(1, 0.15*inch),
    ]
    rows = [["Holder", "Class", "Units", "% Pre-Offer", "Resident"]]
    for s in facts["shareholding"]:
        rows.append([
            s["name"][:48],
            s["class"],
            f"{s['units']:,}",
            f"{s['pct']:.2f}%",
            s["residency"],
        ])
    t = Table(rows, colWidths=[2.5*inch, 0.9*inch, 1.0*inch, 0.9*inch, 1.0*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story += [t, PageBreak()]

    # LOCK-IN PERIODS
    story += [_section_header("LOCK-IN PERIODS", styles), Spacer(1, 0.1*inch)]
    for lock in facts["lock_in_periods"]:
        story += [Paragraph(
            f"• <b>{lock['category']}:</b> {lock['duration_months']} months "
            f"from the date of allotment in the Offer.",
            body,
        )]
    story.append(PageBreak())

    # ROFR / ROFO summary
    story += [
        _section_header("ROFR / ROFO CLAUSES", styles),
        Spacer(1, 0.1*inch),
        Paragraph(facts["rofr_clause_summary"], body),
        PageBreak(),
    ]

    # EMPLOYEE STOCK OPTION PLAN
    story += [
        _section_header("EMPLOYEE STOCK OPTION PLAN", styles),
        Spacer(1, 0.1*inch),
        Paragraph(
            f"Our Company has implemented the {facts['legal_name']} Employee "
            f"Stock Option Plan ('ESOP'). As on the date of this DRHP, the ESOP "
            f"pool represents {facts['esop_pool_pct']:.1f}% of pre-Offer "
            f"equity and has been granted (in part) to approximately "
            f"{facts['esop_holder_count_estimated']} current and former "
            f"employees. Total employees on the date hereof: "
            f"{facts['employee_count']:,}.",
            body,
        ),
        PageBreak(),
    ]

    # RISK FACTORS header (decorative)
    story += [
        _section_header("RISK FACTORS", styles),
        Spacer(1, 0.1*inch),
        Paragraph(
            f"Investors are advised to review the {facts['risk_factors_count_extracted']} "
            f"risk factors set out in this section before making an investment "
            f"decision. The principal categories include market risk, operational "
            f"risk, regulatory risk, technology risk, and shareholder dispute risk.",
            body,
        ),
    ]

    doc.build(story)
    print(f"  built {out.relative_to(ROOT)}")


def main() -> None:
    facts_by_id = json.loads(FACTS.read_text())
    for issuer_id, facts in facts_by_id.items():
        out = DRHP_DIR / f"{issuer_id}_drhp.pdf"
        build_pdf(facts, out)


if __name__ == "__main__":
    main()
