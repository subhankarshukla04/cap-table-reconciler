"""
Generates a realistic Qapita-style messy cap table + side-letter PDFs for
Sundar Foods Pvt. Ltd. — a fictional Indian D2C health-foods Series B-1.

Constraints respected (from src/models.py and src/parser.py):
- Share class types: common / preferred / option_pool_granted / option_pool_reserved
- LP types: non-participating / participating_uncapped / participating_capped
- AD variants: broad-based WA / narrow-based WA / full-ratchet
- Seniority rank: 1-99, unique among preferred
- Currency: INR (₹)

Run from project root:
    .venv/bin/python sample_uploads/sundar_foods/_generate.py
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUT = Path(__file__).parent


# ----------------------------------------------------------------------------
# Excel: Sundar_CapTable_v7_FINAL_v3.xlsx
# ----------------------------------------------------------------------------

THIN = Side(style="thin", color="999999")
MED = Side(style="medium", color="333333")
HEADER_FILL = PatternFill("solid", fgColor="1F2A44")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(bold=True, size=14, color="1F2A44")
SUBTOTAL_FILL = PatternFill("solid", fgColor="FFF4D2")
WARN_FILL = PatternFill("solid", fgColor="FBE4E4")
SECTION_FILL = PatternFill("solid", fgColor="E8ECF7")


def _autosize(ws, min_w=8, max_w=42):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        longest = 0
        for cell in col:
            v = cell.value
            if v is None:
                continue
            longest = max(longest, len(str(v)))
        ws.column_dimensions[col_letter].width = max(min_w, min(max_w, longest + 2))


def _header(ws, row, headers):
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=j, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)


def build_excel():
    wb = Workbook()
    wb.remove(wb.active)

    # ---- Sheet 1: Cover ----------------------------------------------------
    ws = wb.create_sheet("Cover")
    ws["B2"] = "SUNDAR FOODS PVT. LTD."
    ws["B2"].font = Font(bold=True, size=20, color="1F2A44")
    ws["B3"] = "Capitalisation Table — INTERNAL"
    ws["B3"].font = Font(size=12, italic=True, color="555555")
    ws["B5"] = "Prepared by:"
    ws["C5"] = "Aarav Mehta (CFO)"
    ws["B6"] = "Email:"
    ws["C6"] = "aarav@sundarfoods.in"
    ws["B7"] = "Version:"
    ws["C7"] = "v7 (FINAL_v3) — superseded v7-FINAL.xlsx and v7-FINAL-CORRECTED.xlsx"
    ws["B8"] = "As of:"
    ws["C8"] = "30 April 2026 (Series B-1 closing)"
    ws["B10"] = "Note to investor / auditor:"
    ws["B10"].font = Font(bold=True)
    ws["B11"] = (
        "Pls refer to the READ ME tab BEFORE making changes. Some of the SAFE/CCD entries "
        "have NOT been ported into the Cap Table tab yet — these are in the Conv. Instruments "
        "tab and we will roll them up at the next 409A. Side letters are circulated separately by email."
    )
    ws["B11"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[11].height = 60
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 70

    # ---- Sheet 2: READ ME --------------------------------------------------
    ws = wb.create_sheet("READ ME")
    ws["A1"] = "READ ME — do not delete this tab"
    ws["A1"].font = TITLE_FONT
    lines = [
        "",
        "1. The CAP TABLE tab is holder-level — one row per shareholder, not per share class.",
        "   This is how we have always maintained it. If you need a class roll-up, sum by 'Type of Security'.",
        "",
        "2. ESOP tab is per-grant. Total granted = sum of Granted column. Pool reserve = 5,00,000 minus granted minus lapsed.",
        "",
        "3. CONV. INSTRUMENTS — SAFEs from US investors are USD-denominated; the rest are INR.",
        "   None have been converted yet on this sheet; the Series B-1 closing technically triggered "
        "   the YC SAFE caps but our company secretary is still working on the conversion paperwork.",
        "",
        "4. Strategic Investor (Mira Capital Mauritius) — terms are in the side letter, NOT in this file.",
        "   Their economic LP is different from what is shown for 'CCPS Series B-1'.",
        "",
        "5. Founder Equity is split into two rows because Karthik and Priya hold via different trusts.",
        "   Both rows are 'Equity Common' (same class). Do NOT consolidate without checking with us.",
        "",
        "6. Mehta Family Trust shares (8,50,000) — still being verified by our CS. Treat as common for now.",
        "",
        "TBC items (open, as of upload):",
        "  - Surya Capital Series A — possible AD reset triggered by Series B-1 down-tranche pricing?",
        "  - NRI investor TDS withholding on dividend declared Mar 2026 — pending RBI clarification",
        "  - Classification of Aman Verma's vested-but-unexercised options (he left Feb 2026)",
    ]
    for i, line in enumerate(lines, start=2):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 120

    # ---- Sheet 3: Rounds Summary ------------------------------------------
    ws = wb.create_sheet("Rounds Summary")
    ws["A1"] = "Funding rounds — Sundar Foods Pvt. Ltd."
    ws["A1"].font = TITLE_FONT
    _header(ws, 3, ["Round", "Date", "Lead", "Raised (INR)", "Pre-money (INR)", "Instrument", "LP", "AD", "Notes"])
    rounds = [
        ("Founder seed", "12-Aug-2019", "Karthik & Priya Iyer (self-funded)", "₹25,00,000", "—", "Equity Common", "n/a", "n/a", "Two co-founders, 50/50, vesting 4y/1y cliff"),
        ("Pre-Seed", "03-Mar-2020", "Angel syndicate (LetsVenture)", "₹1.20 Cr", "₹5.5 Cr", "CCPS Series Seed", "1x non-cum, non-part", "broad-based WA", "11 angels, smallest cheque ₹5L"),
        ("Seed", "21-Sep-2021", "Surya Capital", "₹8.5 Cr", "₹35 Cr", "CCPS Series A1", "1x non-part", "broad-based WA", ""),
        ("Seed extension", "17-Nov-2022", "Surya Capital (follow-on) + RB Investments", "₹6 Cr", "₹52 Cr", "CCPS Series A2", "1x non-part", "broad-based WA", "Bridge to Series B; same price as A1 + 8% premium"),
        ("Series A", "08-Aug-2023", "Lightbox Ventures", "₹62 Cr", "₹240 Cr", "CCPS Series A3", "1x non-part", "broad-based WA", "Tag-along rights for Surya"),
        ("Series A bridge", "14-Feb-2025", "Mira Capital Mauritius (strategic)", "₹40 Cr", "₹300 Cr (flat)", "CCPS Series A3-Ext.", "see side letter", "see side letter", "Off-charter terms — refer Mira side letter dated 14-Feb-2025"),
        ("Series B-1", "15-Mar-2026", "TigerLion India II + Mira (pro-rata)", "₹120 Cr", "₹560 Cr (down from prev mark of ₹700 Cr)", "CCPS Series B-1", "1x non-cum, non-part w/ catch-up", "see SHA §4.6", "Down-round vs prior preferred mark; AD impl. TBC"),
    ]
    for i, r in enumerate(rounds, start=4):
        for j, v in enumerate(r, start=1):
            ws.cell(row=i, column=j, value=v)
    _autosize(ws)

    # ---- Sheet 4: Cap Table (HOLDER-LEVEL — the killer) -------------------
    ws = wb.create_sheet("Cap Table")
    ws.merge_cells("A1:K1")
    ws["A1"] = "SUNDAR FOODS PVT. LTD. — Capitalisation as of 30-Apr-2026 (post Series B-1)"
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.merge_cells("A2:K2")
    ws["A2"] = "All amounts in INR unless stated. Share counts on a Fully Diluted basis except where noted."
    ws["A2"].font = Font(italic=True, color="666666", size=9)
    ws["A2"].alignment = Alignment(horizontal="center")

    headers = [
        "Sr.", "Stakeholder", "Type of Security", "Issue Date", "# Shares Held",
        "Issue Price (₹)", "Paid-up Capital (₹)", "% on FD Basis",
        "Seniority", "LP Type", "Anti-Dilution",
    ]
    _header(ws, 4, headers)

    # SECTION: Founders Common
    ws.cell(row=5, column=2, value="— FOUNDERS —").fill = SECTION_FILL
    ws.cell(row=5, column=2).font = Font(bold=True, size=10, color="1F2A44")

    rows = [
        # Founders (split — same class name, two rows; will fail unique-name validator)
        (1,  "Karthik Iyer (via KI Family Trust)", "Equity Common", "12-Aug-2019", "30,00,000", 0.10, "3,00,000", "21.43%", "", "", ""),
        (2,  "Priya Iyer (via Iyer Holdings LLP)", "Equity Common",  "12-Aug-2019", "30,00,000", 0.10, "3,00,000", "21.43%", "", "", ""),
        (3,  "Mehta Family Trust (TBC)",          "Equity Common",  "12-Aug-2019", "8,50,000",  0.10, "85,000",   "6.07%",  "", "", ""),
    ]
    for i, r in enumerate(rows, start=6):
        for j, v in enumerate(r, start=1):
            ws.cell(row=i, column=j, value=v)

    # Subtotal row (parser should skip — starts with "Sub-total")
    ws.cell(row=9, column=2, value="Sub-total Founders").fill = SUBTOTAL_FILL
    ws.cell(row=9, column=2).font = Font(bold=True)
    ws.cell(row=9, column=5, value="68,50,000").font = Font(bold=True)
    ws.cell(row=9, column=8, value="48.93%").font = Font(bold=True)

    # SECTION: Pre-Seed CCPS
    ws.cell(row=11, column=2, value="— PRE-SEED CCPS (Mar 2020) —").fill = SECTION_FILL
    pre_seed = [
        ("Aakash Bhansali",     "CCPS Series Seed", "03/03/2020", "1,20,000", 1.00, "1,20,000", "0.86%", 5, "1x non-cum, non-part", "broad-based WA"),
        ("Bhavna Khanna",       "CCPS Series Seed", "03/03/2020", "60,000",   1.00, "60,000",   "0.43%", 5, "1x non-cum, non-part", "broad-based WA"),
        ("LetsVenture Syndicate (9 angels — pooled)", "CCPS Series Seed", "03/03/2020", "10,20,000", 1.00, "10,20,000", "7.29%", 5, "1x non-cum, non-part", "broad-based WA"),
    ]
    for i, r in enumerate(pre_seed, start=12):
        ws.cell(row=i, column=1, value=4 + i - 12)
        for j, v in enumerate(r, start=2):
            ws.cell(row=i, column=j, value=v)

    # SECTION: A1 / A2 / A3
    ws.cell(row=16, column=2, value="— SERIES A (A1 / A2 / A3) —").fill = SECTION_FILL
    series_a = [
        ("Surya Capital Fund I",         "CCPS Series A1",     "21-Sep-2021", "8,50,000",  10.00,  "85,00,000", "6.07%", 4, "1x non-part", "broad-based WA"),
        ("Surya Capital Fund I",         "CCPS Series A2",     "17-Nov-2022", "5,50,000",  10.80,  "59,40,000", "3.93%", 4, "1x non-part", ""),  # AD blank
        ("RB Investments Pte Ltd (SGP)", "CCPS Series A2",     "17-Nov-2022", "50,000",    10.80,  "5,40,000",  "0.36%", 4, "1x non-part", "broad-based WA"),
        ("Lightbox Ventures III",        "CCPS Series A3",     "08-Aug-2023", "20,66,667", 30.00,  "6,20,00,010", "14.76%", 3, "1x non-part", "broad-based WA"),
        ("Surya Capital Fund I",         "CCPS Series A3",     "08-Aug-2023", "1,33,333",  30.00,  "40,00,000", "0.95%", 3, "1x non-part", "broad-based WA"),
    ]
    for i, r in enumerate(series_a, start=17):
        ws.cell(row=i, column=1, value=7 + i - 17)
        for j, v in enumerate(r, start=2):
            ws.cell(row=i, column=j, value=v)

    # Series A3-Ext (Mira)
    ws.cell(row=22, column=2, value="— SERIES A3 EXT. (strategic / off-charter) —").fill = SECTION_FILL
    ws.cell(row=23, column=1, value=12)
    ws.cell(row=23, column=2, value="Mira Capital Mauritius Pte Ltd").fill = WARN_FILL
    ws.cell(row=23, column=3, value="CCPS Series A3-Ext.")
    ws.cell(row=23, column=4, value="14th Feb '25")  # date format the parser won't recognise
    ws.cell(row=23, column=5, value="13,33,333")
    ws.cell(row=23, column=6, value=30.00)
    ws.cell(row=23, column=7, value="4,00,00,000")
    ws.cell(row=23, column=8, value="9.52%")
    ws.cell(row=23, column=9, value=2)
    ws.cell(row=23, column=10, value="See side letter")
    ws.cell(row=23, column=11, value="See side letter")

    # SECTION: Series B-1
    ws.cell(row=25, column=2, value="— SERIES B-1 (Mar 2026) —").fill = SECTION_FILL
    series_b = [
        ("TigerLion India II Mauritius",   "CCPS Series B-1", "15-Mar-2026", "16,00,000", 50.00, "8,00,00,000",  "11.43%", 1, "1x non-cum, non-part w/ catch-up", "see SHA §4.6"),
        ("Mira Capital Mauritius Pte Ltd", "CCPS Series B-1", "15-Mar-2026", "5,33,333",  50.00, "2,66,66,650",  "3.81%",  1, "1x non-cum, non-part w/ catch-up", "see SHA §4.6"),
        ("Endiya Special Situations II",   "CCPS Series B-1", "15-Mar-2026", "2,66,667",  50.00, "1,33,33,350",  "1.90%",  1, "1x non-cum, non-part w/ catch-up", "see SHA §4.6"),
    ]
    for i, r in enumerate(series_b, start=26):
        ws.cell(row=i, column=1, value=13 + i - 26)
        for j, v in enumerate(r, start=2):
            ws.cell(row=i, column=j, value=v)

    # SECTION: Strategic Investor (mystery)
    ws.cell(row=30, column=2, value="— OTHER —").fill = SECTION_FILL
    ws.cell(row=31, column=1, value=16)
    ws.cell(row=31, column=2, value="Veritas Industries Ltd. (strategic)").fill = WARN_FILL
    ws.cell(row=31, column=3, value="(see Side Letter)")
    ws.cell(row=31, column=4, value="29-Mar-2026")
    ws.cell(row=31, column=5, value="2,00,000")
    # price, paid-up, %, seniority, LP, AD all blank — that's the mess
    ws.cell(row=31, column=11, value="See Veritas SHA — terms not in this file")

    # ESOP rollup line — wrong: it's HERE in the cap table but per-employee is on ESOP tab.
    ws.cell(row=33, column=2, value="— ESOP —").fill = SECTION_FILL
    ws.cell(row=34, column=1, value=17)
    ws.cell(row=34, column=2, value="ESOP — Granted (per ESOP tab)")
    ws.cell(row=34, column=3, value="ESOP Granted")
    ws.cell(row=34, column=4, value="(various)")
    ws.cell(row=34, column=5, value="3,67,500")
    ws.cell(row=34, column=6, value=10.00)
    ws.cell(row=34, column=7, value="36,75,000")
    ws.cell(row=34, column=8, value="2.62%")

    ws.cell(row=35, column=1, value=18)
    ws.cell(row=35, column=2, value="ESOP — Reserved (uncommitted)")
    ws.cell(row=35, column=3, value="ESOP Reserved")
    ws.cell(row=35, column=4, value="—")
    ws.cell(row=35, column=5, value="1,32,500")
    ws.cell(row=35, column=8, value="0.94%")

    # Grand total
    ws.cell(row=37, column=2, value="Grand total (Fully Diluted)").fill = SUBTOTAL_FILL
    ws.cell(row=37, column=2).font = Font(bold=True)
    ws.cell(row=37, column=5, value="1,40,00,000").font = Font(bold=True)
    ws.cell(row=37, column=8, value="100.00%").font = Font(bold=True)

    _autosize(ws)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[4].height = 34

    # ---- Sheet 5: ESOP (per-employee, parser won't read) ------------------
    ws = wb.create_sheet("ESOP")
    ws["A1"] = "ESOP grants register (per-employee). Pool size: 5,00,000 shares."
    ws["A1"].font = TITLE_FONT
    _header(ws, 3, ["Empl. ID", "Name", "Designation", "Grant Date", "Total Granted", "Vested", "Strike (₹)", "Status", "Notes"])
    grants = [
        ("E001", "Aman Verma",       "Head of Supply Chain",  "12-Aug-2019", 80000, 80000, 0.10, "Lapsed (left Feb 2026, unexercised)", "TBC by CS — see READ ME"),
        ("E002", "Neha Saxena",      "Head of Marketing",     "03-Mar-2020", 60000, 60000, 1.00, "Active", ""),
        ("E003", "Rohan Kapoor",     "VP Engineering",        "21-Sep-2021", 90000, 67500, 10.00, "Active", "Vesting continues"),
        ("E004", "Megha Pillai",     "VP Finance",            "08-Aug-2023", 50000, 18750, 30.00, "Active", "1y cliff just cleared"),
        ("E005", "Suresh Iyer",      "COO (joined SerB-1)",   "15-Mar-2026", 40000, 0,     50.00, "Active", "4y vest from Mar 2026"),
        ("E006", "(various — 14 ICs, see HR)", "—", "various", 47500, 31000, "various", "Active", "Pooled summary row"),
    ]
    for i, g in enumerate(grants, start=4):
        for j, v in enumerate(g, start=1):
            ws.cell(row=i, column=j, value=v)
    _autosize(ws)

    # ---- Sheet 6: Conv. Instruments (parser won't detect this tab name) ---
    ws = wb.create_sheet("Conv. Instruments")
    ws["A1"] = "SAFEs / CCDs / Warrants outstanding (none converted on Cap Table tab yet)"
    ws["A1"].font = TITLE_FONT
    _header(ws, 3, ["Instrument ID", "Type", "Counterparty", "Principal", "Currency",
                    "Valuation Cap", "Discount", "Issue Date", "Trigger / Notes"])
    instruments = [
        ("CONV-001", "SAFE (post-money, YC v1.1)", "500 Global Fund VI",
         "1,75,000", "USD", "30,00,000 USD", "20%", "11-Jan-2024",
         "Converts at next priced round ≥ USD 5M. Series B-1 (Mar-2026) satisfies threshold; conversion pending."),
        ("CONV-002", "SAFE (post-money, YC v1.1)", "Hustle Fund III",
         "2,50,000", "USD", "30,00,000 USD", "—", "11-Jan-2024",
         "Same trigger as CONV-001. Pending conversion."),
        ("CONV-003", "CCD (10% coupon, INR)", "Stride Ventures (venture debt)",
         "10,00,00,000", "INR", "n/a", "n/a", "04-Jun-2024",
         "Coupon 10% p.a., quarterly. Convertible at lender option at Series B-1 price - 15% OR fixed ₹42/share, whichever lower. Maturity 04-Jun-2027. NOT yet exercised."),
        ("WAR-001", "Warrant (vendor)", "Equator Logistics Pvt Ltd",
         "—", "INR", "n/a", "n/a", "01-Sep-2024",
         "75,000 Equity Common at ₹0.50/share strike, expiry 01-Sep-2029. Issued in lieu of cash for warehousing services."),
        ("WAR-002", "Warrant (advisor)", "Dr. R. Subramanian (board observer)",
         "—", "INR", "n/a", "n/a", "08-Aug-2023",
         "25,000 Equity Common at ₹1.00/share, expiry 08-Aug-2028."),
    ]
    for i, r in enumerate(instruments, start=4):
        for j, v in enumerate(r, start=1):
            ws.cell(row=i, column=j, value=v)
    _autosize(ws)

    # ---- Sheet 7: Co. Info (parser won't detect — wrong tab name) ---------
    ws = wb.create_sheet("Co. Info")
    info = [
        ("Company",        "Sundar Foods Pvt. Ltd."),
        ("CIN",            "U15400MH2019PTC329887"),
        ("Jurisdiction",   "India (Maharashtra) — Pvt. Ltd."),
        ("Registered Office", "Plot 14, MIDC Andheri (E), Mumbai 400093"),
        ("Sector",         "D2C Foods (Health snacking & cold-press)"),
        ("Stage",          "Series B-1"),
        ("Valuation Date", "30-Apr-2026"),
        ("Currency",       "INR"),
        ("Currency Symbol", "₹"),
        ("Auditor",        "K.M. Doshi & Co., Mumbai"),
        ("Company Secretary", "Priti Bhatt (CS-Inhouse)"),
    ]
    for i, (k, v) in enumerate(info, start=1):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=v)
    _autosize(ws)

    # ---- Sheet 8: Notes ---------------------------------------------------
    ws = wb.create_sheet("Notes")
    notes = [
        ("Pending CS items", ""),
        ("",  "1. Mehta Family Trust shares — need to confirm if equity-common or CCPS Series A1. Records inconsistent between RTA and our internal sheet."),
        ("",  "2. Aman Verma's lapsed options — board resolution dated 28-Feb-2026 says forfeited; payroll records show partial vesting credit."),
        ("",  "3. Surya AD reset — Series B-1 is a down-round vs the implied A3-Ext mark (₹300 Cr pre flat at Feb-2025 → ₹560 Cr post on ₹440 Cr pre is a notional uptick, but vs the prior ₹700 Cr mark on the new tranche, it's a down-round). Surya's lawyers raised this in March 2026 — open."),
        ("",  ""),
        ("Off-charter terms (in side letters, NOT this file)", ""),
        ("",  "- Mira (Series A3-Ext): 2x LP, MFN scope per side letter, no AD adjustment"),
        ("",  "- TigerLion (Series B-1): full-ratchet override clause for any down-round in next 24 months"),
        ("",  "- Veritas Industries: redemption right at the 7-year mark, IPO veto for any sub-₹2000 Cr valuation listing"),
    ]
    for i, (k, v) in enumerate(notes, start=1):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, color="1F2A44")
        ws.cell(row=i, column=2, value=v).alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 100

    out = OUT / "Sundar_CapTable_v7_FINAL_v3.xlsx"
    wb.save(out)
    print(f"wrote {out}")


# ----------------------------------------------------------------------------
# PDFs
# ----------------------------------------------------------------------------

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], spaceAfter=10, fontSize=14, textColor=colors.HexColor("#1F2A44"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceAfter=6, fontSize=11.5, textColor=colors.HexColor("#1F2A44"))
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=8)
META = ParagraphStyle("Meta", parent=styles["BodyText"], fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=12)
QUESTION = ParagraphStyle("Question", parent=BODY, textColor=colors.HexColor("#7B1B1B"))


def _doc(filename, title):
    return SimpleDocTemplate(
        str(OUT / filename),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title,
    )


def pdf_mira_side_letter():
    d = _doc("01_Mira_Capital_Side_Letter_2025-02-14.pdf",
             "Mira Capital — Side Letter (Series A3-Ext.)")
    story = [
        Paragraph("SIDE LETTER — SERIES A3-EXT. PREFERRED FINANCING", H1),
        Paragraph("Counterparty: Mira Capital Mauritius Pte Ltd. (\"Investor\")<br/>"
                  "Company: Sundar Foods Pvt. Ltd. (\"Company\")<br/>"
                  "Effective: 14 February 2025 (Series A3-Ext. closing)<br/>"
                  "Reference: Share Subscription Agreement of even date and Articles of Association",
                  META),

        Paragraph("1. Liquidation Preference (overriding Articles)", H2),
        Paragraph(
            "Notwithstanding anything in the Articles or the Shareholders' Agreement to the contrary, the "
            "Investor's CCPS Series A3-Ext. shall be entitled to a liquidation preference equal to "
            "<b>two times (2.0x)</b> the subscription amount paid (non-participating, non-cumulative), payable "
            "in priority to all junior series and pari passu with any subsequent CCPS Series B or later issuance "
            "unless otherwise expressly subordinated by written agreement of the Investor.",
            BODY),

        Paragraph("2. Anti-Dilution", H2),
        Paragraph(
            "The Investor's CCPS Series A3-Ext. shall <b>not be subject to any anti-dilution adjustment</b> on "
            "issuances of equity securities at a price per share lower than the Investor's Issue Price. The "
            "Investor's economic protection in a down-round shall be limited to the 2.0x liquidation preference "
            "in Clause 1 above.",
            BODY),

        Paragraph("3. Most-Favoured-Nation", H2),
        Paragraph(
            "If, prior to the earlier of (a) an IPO of the Company and (b) the third anniversary of this letter, "
            "the Company grants to any subsequent investor terms that are, in the aggregate, more favourable to "
            "such investor than the terms granted to the Investor herein (excluding, for the avoidance of doubt, "
            "the Articles entitlements available to all preferred holders), the Investor shall have the right, "
            "exercisable by written notice within forty-five (45) days of receiving disclosure, to elect to apply "
            "such more-favourable terms to the Investor's holdings on a <i>clause-by-clause</i> basis.",
            BODY),

        Paragraph("4. Information Rights", H2),
        Paragraph(
            "Monthly unaudited management accounts within 21 days of month-end; quarterly board pack; annual "
            "audited financials within 120 days of fiscal year-end.",
            BODY),

        Paragraph("5. Open Items (initialled at closing)", H2),
        Paragraph("Q: Does Clause 3 (MFN) extend to anti-dilution variants granted to subsequent CCPS series, "
                  "or is it limited to economic (LP / participation / dividend) terms only?", QUESTION),
        Paragraph("Q: Is the 2.0x LP under Clause 1 carved out from MFN cherry-picking by subsequent investors "
                  "(i.e., can a later investor claim 2.0x via MFN by waiving its own AD)?", QUESTION),
        Paragraph("TODO: Tax counsel to opine on whether 2.0x LP triggers withholding under Section 115O on "
                  "deemed dividend characterisation in a wind-up scenario.", QUESTION),

        Spacer(1, 16),
        Paragraph(
            "_____________________________________<br/>"
            "For and on behalf of Sundar Foods Pvt. Ltd.<br/>"
            "Karthik Iyer, Director",
            BODY),
        Paragraph(
            "_____________________________________<br/>"
            "For and on behalf of Mira Capital Mauritius Pte Ltd<br/>"
            "Ramesh Lim, Authorised Signatory",
            BODY),
    ]
    d.build(story)
    print(f"wrote {d.filename}")


def pdf_tigerlion_sha_excerpt():
    d = _doc("02_TigerLion_SHA_Excerpt_Section_4-6_2026-03-15.pdf",
             "TigerLion India II — SHA Excerpt §4.6")
    story = [
        Paragraph("SHAREHOLDERS' AGREEMENT — EXCERPT", H1),
        Paragraph("Sundar Foods Pvt. Ltd. — Series B-1 Financing<br/>"
                  "Excerpt: Section 4 (Investor Protections) — extracted by company counsel, 18 March 2026<br/>"
                  "FOR DUE DILIGENCE USE ONLY. Full SHA available on request.",
                  META),

        Paragraph("4.6  Anti-Dilution Adjustment — Series B-1 Preferred", H2),
        Paragraph(
            "(a) <b>Standard Adjustment.</b> Subject to clause 4.6(b) below, the Conversion Price of each "
            "CCPS Series B-1 share shall be adjusted in the event of an Additional Issuance at a Lower Price "
            "on a <i>broad-based weighted average</i> basis, using the formula set forth in Schedule 4.6-A.",
            BODY),
        Paragraph(
            "(b) <b>Full-Ratchet Override.</b> Notwithstanding clause 4.6(a), if any Additional Issuance occurs "
            "within twenty-four (24) months of the Series B-1 Closing Date and at a price per share less than "
            "75% of the Series B-1 Issue Price (₹50.00), then the Conversion Price of each CCPS Series B-1 share "
            "held by the Lead Investor (TigerLion India II Mauritius) shall be adjusted on a <b>full-ratchet</b> "
            "basis to equal the Additional Issuance price. The Full-Ratchet Override shall <i>not</i> apply to "
            "any other holder of CCPS Series B-1 unless such holder is expressly designated in this Agreement.",
            BODY),
        Paragraph(
            "(c) <b>Carve-outs.</b> The following issuances shall not trigger any adjustment under this Section 4.6: "
            "(i) ESOP grants up to the Authorised Pool; (ii) issuances on conversion of any then-outstanding SAFE or "
            "CCD that was issued prior to the Series B-1 Closing Date; (iii) issuances in connection with a bona "
            "fide strategic partnership, joint venture, or commercial agreement, subject to a maximum of 2.0% of the "
            "fully diluted share capital in any 12-month period.",
            BODY),

        Paragraph("4.7  Pay-to-Play", H2),
        Paragraph(
            "If any holder of CCPS Series B-1 fails to subscribe for at least its Pro Rata Share in a future "
            "Qualified Financing, such holder's CCPS Series B-1 shall automatically convert into Equity Common "
            "on a 1:1 basis and the holder shall forfeit the benefit of Section 4.6.",
            BODY),

        Paragraph("Schedule 4.6-A — Broad-Based Weighted Average Formula (reference)", H2),
        Paragraph(
            "CP' = CP × (A + B) / (A + C)<br/>"
            "where —<br/>"
            "CP  = Conversion Price in effect immediately prior to the Additional Issuance<br/>"
            "CP' = Conversion Price after adjustment<br/>"
            "A   = Total outstanding Equity Common on a fully diluted as-converted basis (incl. all options and SAFEs)<br/>"
            "B   = Shares that would be issued at CP for the consideration received<br/>"
            "C   = Shares actually issued in the Additional Issuance",
            BODY),

        Paragraph("Open items (counsel note)", H2),
        Paragraph("Q: Does the Section 4.6(c)(ii) carve-out cover SAFEs that converted AFTER the Series B-1 "
                  "Closing Date but were ISSUED prior? (Plain reading suggests yes; investor counsel disagrees.)",
                  QUESTION),
        Paragraph("Q: Is the 24-month window in 4.6(b) tolled by an IPO filing?", QUESTION),
    ]
    d.build(story)
    print(f"wrote {d.filename}")


def pdf_veritas_strategic_letter():
    d = _doc("03_Veritas_Industries_Strategic_Investment_Letter_2026-03-29.pdf",
             "Veritas Industries — Strategic Investment Letter")
    story = [
        Paragraph("STRATEGIC INVESTMENT — SIDE LETTER", H1),
        Paragraph("Counterparty: Veritas Industries Ltd. (\"Strategic\")<br/>"
                  "Company: Sundar Foods Pvt. Ltd.<br/>"
                  "Date: 29 March 2026<br/>"
                  "Subject: Subscription to 2,00,000 equity-linked instruments — terms summary",
                  META),

        Paragraph("1. Instrument", H2),
        Paragraph(
            "The Strategic shall subscribe to 2,00,000 Compulsorily Convertible Preference Shares (CCPS) of "
            "the Company, designated <b>\"CCPS Series Strategic\"</b>, at an Issue Price of ₹150.00 per share, "
            "for an aggregate subscription of ₹30,00,00,000 (Rupees Thirty Crores only). Closing on or before "
            "15 April 2026 subject to definitive documentation.",
            BODY),

        Paragraph("2. Liquidation Preference", H2),
        Paragraph(
            "1.0x non-participating, non-cumulative. Pari passu with CCPS Series B-1.",
            BODY),

        Paragraph("3. Redemption Right", H2),
        Paragraph(
            "The Strategic shall have the right (but not the obligation) to require the Company to redeem "
            "all or any portion of its CCPS Series Strategic at the higher of (a) the Issue Price plus 8% "
            "p.a. compounded annually, or (b) Fair Market Value as determined by an independent valuer "
            "appointed by mutual agreement, exercisable at any time after the <b>seventh (7th) anniversary</b> "
            "of the Closing Date.",
            BODY),

        Paragraph("4. IPO Veto", H2),
        Paragraph(
            "The Company shall not undertake an Initial Public Offering at a pre-money valuation less than "
            "<b>₹2,000 crore</b> without the prior written consent of the Strategic, such consent not to be "
            "unreasonably withheld.",
            BODY),

        Paragraph("5. Commercial Arrangement", H2),
        Paragraph(
            "The Strategic and the Company shall enter into a separate Master Supply Agreement under which "
            "the Company shall offtake a minimum of ₹15 crores of organic-grade jaggery and seed inputs per "
            "annum from the Strategic's group entities for an initial term of five (5) years. The Strategic "
            "Investment is conditional upon execution of the Master Supply Agreement.",
            BODY),

        Paragraph("6. Anti-Dilution", H2),
        Paragraph("Not applicable. The Strategic waives all anti-dilution protections in consideration of "
                  "the redemption right under Clause 3 above.", BODY),

        Paragraph("Open / TBC", H2),
        Paragraph("Q: How does Clause 4 (IPO veto) interact with the TigerLion drag-along right in the main SHA?",
                  QUESTION),
        Paragraph("Q: Is the redemption right under Clause 3 enforceable under Indian Companies Act §55 "
                  "(redeemable preference shares must be redeemed out of profits or fresh issue)? "
                  "Counsel to confirm whether CCPS qualifies.", QUESTION),
        Paragraph("TODO: Confirm seniority rank — pari passu with B-1, or junior? Drafting is ambiguous.",
                  QUESTION),
    ]
    d.build(story)
    print(f"wrote {d.filename}")


def pdf_safe_500_global():
    d = _doc("04_SAFE_500_Global_2024-01-11.pdf",
             "Post-money SAFE — 500 Global Fund VI")
    story = [
        Paragraph("SIMPLE AGREEMENT FOR FUTURE EQUITY", H1),
        Paragraph(
            "(Post-Money, YC v1.1 — Discount, Cap)<br/>"
            "Investor: 500 Global Fund VI L.P.<br/>"
            "Company: Sundar Foods Pvt. Ltd.<br/>"
            "Purchase Amount: <b>USD 175,000</b><br/>"
            "Post-Money Valuation Cap: <b>USD 30,000,000</b><br/>"
            "Discount Rate: <b>80%</b> (i.e., 20% discount)<br/>"
            "Date: 11 January 2024",
            META),

        Paragraph("1. Events", H2),
        Paragraph(
            "1(a) <b>Equity Financing.</b> If there is an Equity Financing before the termination of this Safe, on "
            "the initial closing of such Equity Financing, this Safe will automatically convert into the number "
            "of shares of Safe Preferred Stock equal to the Purchase Amount divided by the Conversion Price. "
            "For purposes of this Safe, \"Equity Financing\" means a bona fide transaction or series of "
            "transactions with the principal purpose of raising capital, pursuant to which the Company issues "
            "and sells Preferred Stock at a fixed valuation, with aggregate proceeds of at least "
            "<b>USD 5,000,000</b> (the \"Threshold Amount\").",
            BODY),

        Paragraph("2. Definitions", H2),
        Paragraph(
            "\"Conversion Price\" means the lower of (a) the Safe Price and (b) the Discount Price.<br/>"
            "\"Safe Price\" means the price per share equal to the Post-Money Valuation Cap divided by the "
            "Company Capitalization immediately prior to the Equity Financing.<br/>"
            "\"Discount Price\" means the price per share of the Standard Preferred Stock sold in the Equity "
            "Financing multiplied by the Discount Rate.",
            BODY),

        Paragraph("3. Conversion Mechanic — Worked Example (illustrative only)", H2),
        Paragraph(
            "Assume Series B-1 closes at INR 50.00/share. At the spot rate of INR 83.50 / USD on the closing "
            "date, the Series B-1 price is USD 0.5988/share, and the Discount Price would be USD 0.4790/share. "
            "The Safe Price equals USD 30,000,000 divided by the pre-money Company Capitalization (TBD at "
            "closing). The Conversion Price is the lower of those two — which depends on the actual "
            "capitalization count on the conversion date.",
            BODY),

        Paragraph("4. MFN (\"Most Favored Nation\")", H2),
        Paragraph(
            "If the Company issues any other Safes or convertible securities prior to the termination of this "
            "Safe with terms that are more favorable to the holder thereof (including, without limitation, a "
            "lower Valuation Cap or a higher Discount Rate), the Company shall promptly inform the Investor "
            "and the Investor may elect to amend this Safe to incorporate such more-favorable terms.",
            BODY),

        Paragraph("Open / TBC", H2),
        Paragraph(
            "Q: Series B-1 closed on 15 March 2026 at gross proceeds of ₹120 crore (~USD 14.4M). This "
            "exceeds the USD 5M Threshold — does this Safe automatically convert, even though the company "
            "secretary has not yet issued the conversion notice?",
            QUESTION),
        Paragraph(
            "Q: Does the Hustle Fund III Safe (also dated 11-Jan-2024) have identical terms? If not, does MFN "
            "trigger here? (Hustle Fund's term sheet referenced \"no discount\" — but our copy shows 20%.)",
            QUESTION),
    ]
    d.build(story)
    print(f"wrote {d.filename}")


def pdf_scanned_lookalike():
    # A PDF that LOOKS like a scan but is actually a vector PDF with text — except
    # we'll render the body as a single image-style block via TableStyle to mimic
    # a real scanned doc that pdfplumber will still extract poorly.
    # Simulating an actual scan is non-trivial; instead, we generate a PDF where the
    # body is laid out in a way that pdfplumber returns minimal usable text.
    d = _doc("05_Surya_Capital_AD_Reset_Notice_SCAN.pdf",
             "Surya Capital — AD reset notice (scan)")
    style = ParagraphStyle("ScanStyle", parent=BODY, fontName="Courier", fontSize=8.5,
                            leading=11, textColor=colors.HexColor("#222222"))
    story = [
        Paragraph("[ Scanned document — original signed paper letter ]", META),
        Paragraph("SURYA CAPITAL FUND I", style),
        Paragraph("c/o Surya Capital Advisors LLP, Bangalore — 560001", style),
        Paragraph("To: The Board of Directors, Sundar Foods Pvt. Ltd.", style),
        Paragraph("Date: 21 March 2026", style),
        Spacer(1, 12),
        Paragraph("Re: Series B-1 issuance — anti-dilution adjustment under SHA §4.4(b)", style),
        Spacer(1, 8),
        Paragraph(
            "Dear Sirs,<br/><br/>"
            "We refer to the Series B-1 closing of 15 March 2026 at an issue price of ₹50.00 per CCPS, "
            "and to clause 4.4(b) of the Shareholders' Agreement dated 21 September 2021. The price at "
            "which CCPS Series B-1 has been issued represents a Lower Price as compared to the issue price "
            "of CCPS Series A1 (₹10.00) on a broad-based weighted average basis, and accordingly the "
            "Conversion Ratio of CCPS Series A1 (currently 1:1) requires recalculation. We have computed "
            "the revised Conversion Ratio as approximately 1.073:1 (subject to verification). Please "
            "confirm by return.<br/><br/>"
            "Yours faithfully,<br/>"
            "[ illegible signature ]<br/>"
            "Vivek Rao, Partner — Surya Capital",
            style),
        Spacer(1, 18),
        Paragraph(
            "                                  -- end of page --",
            ParagraphStyle("Footer", parent=style, alignment=1, textColor=colors.HexColor("#888888")),
        ),
    ]
    d.build(story)
    print(f"wrote {d.filename}")


def write_readme():
    readme = OUT / "README.md"
    readme.write_text(
        "# Sundar Foods Pvt. Ltd. — sample upload set\n\n"
        "Fictional Indian D2C health-foods company, Series B-1 just closed (Mar 2026). "
        "These files are designed to be **uploaded into the Cap Table Reconciler at "
        "http://127.0.0.1:5050/** and behave like a real client hand-off — not a fixture "
        "tuned to the parser.\n\n"
        "## Files\n\n"
        "- `Sundar_CapTable_v7_FINAL_v3.xlsx` — the cap table (upload this on the home page).\n"
        "- `01_Mira_Capital_Side_Letter_2025-02-14.pdf` — 2x LP override, MFN, no AD for Mira.\n"
        "- `02_TigerLion_SHA_Excerpt_Section_4-6_2026-03-15.pdf` — full-ratchet override for lead.\n"
        "- `03_Veritas_Industries_Strategic_Investment_Letter_2026-03-29.pdf` — 7-yr redemption, IPO veto.\n"
        "- `04_SAFE_500_Global_2024-01-11.pdf` — YC post-money SAFE, conversion pending.\n"
        "- `05_Surya_Capital_AD_Reset_Notice_SCAN.pdf` — letter formatted to mimic a scan.\n\n"
        "## What the tool should flag (without being told)\n\n"
        "- Holder-level cap-table instead of class-level — same class name appears across many rows.\n"
        "- Two **Equity Common** rows for Karthik / Priya (duplicate class name → Pydantic).\n"
        "- Mehta Family Trust (8,50,000 sh.) — type marked 'Equity Common' but flagged TBC in READ ME.\n"
        "- Series A2 row for Surya has blank anti-dilution column.\n"
        "- Mira Series A3-Ext. row — LP, AD, seniority all say 'See side letter'.\n"
        "- Series B-1 LP type '1x non-cum, non-part w/ catch-up' — engine won't recognise the alias.\n"
        "- Veritas Industries row — no price, no LP, no class type, just 2,00,000 shares + a note.\n"
        "- `Conv. Instruments` tab name doesn't match the parser's whitelist → SAFEs / CCDs / warrants invisible.\n"
        "- `Co. Info` tab name doesn't match → company defaults to 'Unnamed Company'.\n"
        "- `ESOP` tab is per-employee with a 'Lapsed' row — not the granted/reserved split the engine expects.\n"
        "- Date formats: `15-Mar-2026`, `15/03/2026`, `14th Feb '25` (last one will not parse).\n"
        "- Mira side letter (PDF 01) — 2x LP overrides charter 1x.\n"
        "- TigerLion SHA (PDF 02) — full-ratchet override for the lead but BB-WA for everyone else.\n"
        "- Veritas (PDF 03) — redemption + IPO veto, neither modelled by engine; class designation in dispute.\n"
        "- 500 Global SAFE (PDF 04) — Series B-1 satisfied the trigger, but conversion paperwork pending.\n"
        "- Surya AD reset (PDF 05) — laid out as a scan with Courier body; pdfplumber will return text but the "
        "  parser's heuristic title detection will pick the wrong line.\n\n"
        "## Constraints respected (engine limits)\n\n"
        "- Share class types limited to: common, preferred, option_pool_granted, option_pool_reserved\n"
        "- LP types: non-participating, participating-uncapped, participating-capped\n"
        "- AD variants: BB-WA, NB-WA, full-ratchet\n"
        "- Currency: INR (₹), engine maps `INR` → `₹` automatically\n"
        "- No off-engine instruments (the redemption right and IPO veto are mentioned in PDFs only, not in xlsx)\n"
    )
    print(f"wrote {readme}")


if __name__ == "__main__":
    build_excel()
    pdf_mira_side_letter()
    pdf_tigerlion_sha_excerpt()
    pdf_veritas_strategic_letter()
    pdf_safe_500_global()
    pdf_scanned_lookalike()
    write_readme()
    print("\nAll artifacts written to:", OUT)
