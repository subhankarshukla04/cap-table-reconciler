"""Audit-firm PDF advisory memo. Renders a Verdict with letterhead, primary
verdict block, secondary perspectives, and a numbered citation footer.

Built on reportlab so there's no native-binary dependency (no Pango / Cairo).
Memo styling mimics a Big-4 advisory deliverable: monospaced numerics,
muted blue letterhead, tight typography, no gradients.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import Rule, Verdict


NAVY = colors.HexColor("#1F4E79")
GREY_BORDER = colors.HexColor("#D8DEE6")
GREY_LABEL = colors.HexColor("#45556A")
GREY_LIGHT = colors.HexColor("#F4F6F9")
INK = colors.HexColor("#16202C")


def _styles() -> dict:
    base = getSampleStyleSheet()
    out = {
        "Letterhead": ParagraphStyle(
            "Letterhead", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=16, textColor=NAVY, spaceAfter=2, alignment=TA_LEFT,
        ),
        "LetterheadSub": ParagraphStyle(
            "LetterheadSub", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=GREY_LABEL, spaceAfter=12, alignment=TA_LEFT,
        ),
        "H1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=12, textColor=NAVY, spaceBefore=10, spaceAfter=6,
        ),
        "H2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=10, textColor=NAVY, spaceBefore=8, spaceAfter=4,
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=INK, leading=12, spaceAfter=4,
        ),
        "Label": ParagraphStyle(
            "Label", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=GREY_LABEL, leading=11,
        ),
        "Value": ParagraphStyle(
            "Value", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=INK, leading=12,
        ),
        "Mono": ParagraphStyle(
            "Mono", parent=base["Normal"], fontName="Courier",
            fontSize=9, textColor=INK, leading=12,
        ),
        "CiteAuthority": ParagraphStyle(
            "CiteAuthority", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=NAVY, leading=10,
        ),
        "CiteBody": ParagraphStyle(
            "CiteBody", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=INK, leading=10,
        ),
        "Caveat": ParagraphStyle(
            "Caveat", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=GREY_LABEL, leading=11, leftIndent=10, spaceAfter=2,
        ),
        "Footer": ParagraphStyle(
            "Footer", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=GREY_LABEL, leading=9,
        ),
    }
    return out


def _kv_table(pairs: list[tuple[str, str]], styles: dict, col_widths=(45*mm, 130*mm)) -> Table:
    data = []
    for k, v in pairs:
        data.append([
            Paragraph(k, styles["Label"]),
            Paragraph(v.replace("\n", "<br/>"), styles["Value"]),
        ])
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, GREY_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, GREY_BORDER),
        ("BACKGROUND", (0, 0), (0, -1), GREY_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _rule_section(rule: Rule, heading: str, citation_offset: int, styles: dict) -> list:
    """Render one Rule as a heading + KV table + caveats + numbered citations starting at citation_offset.
    Returns a list of flowables and the citation indices used."""
    parts: list = []
    parts.append(Paragraph(heading, styles["H2"]))
    pairs: list[tuple[str, str]] = [
        ("Rule ID", rule.rule_id),
        ("Taxing jurisdiction", rule.taxing_jurisdiction.value),
        ("Tax treatment", rule.tax_treatment.value.replace("_", " ")),
        ("Rate / description", rule.rate_description),
        ("Withholding", rule.withholding + (f" — {rule.withholding_note}" if rule.withholding_note else "")),
        ("Filing", rule.filing_requirement or "—"),
        ("Documents", "; ".join(rule.documents_required) if rule.documents_required else "—"),
        ("Confidence", rule.confidence.value.replace("_", " ")),
    ]
    # Append citation reference indices to the rate row
    indices = list(range(citation_offset, citation_offset + len(rule.citations)))
    if indices:
        idx_str = ", ".join(f"[{i}]" for i in indices)
        pairs.append(("Authorities cited", idx_str))
    parts.append(_kv_table(pairs, styles))

    if rule.caveats:
        parts.append(Spacer(1, 4))
        parts.append(Paragraph("Caveats", styles["Label"]))
        for c in rule.caveats:
            parts.append(Paragraph(f"• {c}", styles["Caveat"]))
    return parts


def verdict_to_pdf(verdict: Verdict, *, firm_name: str = "ESOP Atlas Advisory") -> bytes:
    """Render the verdict to a printable PDF advisory memo (bytes)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=20*mm,
        title=f"ESOP Atlas Advisory — {verdict.primary_rule.rule_id}",
        author=firm_name,
    )
    styles = _styles()
    story: list = []

    # Letterhead
    story.append(Paragraph(firm_name, styles["Letterhead"]))
    story.append(Paragraph(
        f"Cross-Border ESOP Compliance Memo — generated {date.today().isoformat()}",
        styles["LetterheadSub"],
    ))
    story.append(HRFlowable(width="100%", thickness=0.6, color=NAVY, spaceAfter=8))

    # Query block
    q = verdict.query
    story.append(Paragraph("Query inputs", styles["H1"]))
    inputs_pairs = [
        ("Parent jurisdiction", q.parent_jurisdiction.value),
        ("Employee jurisdiction", q.employee_jurisdiction.value),
        ("Event", q.event.value.replace("_", " ")),
        ("Tax status", q.tax_status.value.replace("_", " ")),
        ("Grant date", q.grant_date.isoformat() if q.grant_date else "—"),
        ("Vesting date", q.vesting_date.isoformat() if q.vesting_date else "—"),
        ("Event date", q.event_date.isoformat() if q.event_date else "—"),
        ("FMV at event", f"{q.fmv_at_event:,.2f}" if q.fmv_at_event is not None else "—"),
        ("Exercise price", f"{q.exercise_price:,.2f}" if q.exercise_price is not None else "—"),
        ("Options in event", f"{q.options_in_event:,}" if q.options_in_event is not None else "—"),
        ("Computed taxable amount",
         f"{verdict.computed_amount_taxable:,.2f}" if verdict.computed_amount_taxable is not None else "—"),
        ("Weakest confidence (across rules)", verdict.weakest_confidence.value.replace("_", " ")),
    ]
    story.append(_kv_table(inputs_pairs, styles))
    story.append(Spacer(1, 10))

    # Summary
    story.append(Paragraph("Verdict summary", styles["H1"]))
    story.append(Paragraph(verdict.summary, styles["Body"]))

    # Rules
    citation_offset = 1
    all_citations: list[tuple[int, Rule, "Citation"]] = []  # type: ignore[name-defined]
    primary_block = _rule_section(verdict.primary_rule, "Primary rule — employee-jurisdiction view", citation_offset, styles)
    for i, c in enumerate(verdict.primary_rule.citations):
        all_citations.append((citation_offset + i, verdict.primary_rule, c))
    citation_offset += len(verdict.primary_rule.citations)
    story.extend(primary_block)

    for sec in verdict.secondary_rules:
        story.append(Spacer(1, 6))
        sec_block = _rule_section(sec, f"Secondary rule — {sec.taxing_jurisdiction.value} perspective", citation_offset, styles)
        for i, c in enumerate(sec.citations):
            all_citations.append((citation_offset + i, sec, c))
        citation_offset += len(sec.citations)
        story.extend(sec_block)

    # Citations footer
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.4, color=GREY_BORDER, spaceAfter=4))
    story.append(Paragraph("Authorities cited", styles["H1"]))
    cite_rows = []
    for idx, rule, c in all_citations:
        cite_rows.append([
            Paragraph(f"[{idx}]", styles["CiteAuthority"]),
            Paragraph(
                f"<b>{c.authority}</b><br/>"
                f"{c.reference}"
                + (f"<br/><font color='#45556A'>Source: {c.source_url}</font>" if c.source_url else "")
                + (f"<br/><font color='#45556A'>Retrieved: {c.retrieved_on.isoformat()}</font>" if c.retrieved_on else ""),
                styles["CiteBody"],
            ),
        ])
    t = Table(cite_rows, colWidths=(10*mm, 165*mm))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # Footer note
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.4, color=GREY_BORDER, spaceAfter=4))
    story.append(Paragraph(
        "Engine output is deterministic and rule-citable. This memo is an audit-grade compliance "
        "verdict generated by ESOP Atlas; it is not tax advice. Verify against current statutory text "
        "before client delivery.",
        styles["Footer"],
    ))

    doc.build(story)
    return buf.getvalue()
