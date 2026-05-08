"""Rebuild fixture_02_typical_messy/cap_table.xlsx with realistic structural mess.

Real client cap-tables often have:
- A merged title row across all columns
- Blank spacer rows
- A subheader row referencing the round closing
- Subtotal rows embedded mid-data ("Subtotal — Preferred")
- A footnote/notes column with prose
- Mixed date formats (US %m/%d/%Y, ISO, prose)

This script replaces the existing tidy xlsx with a structurally messy one. Data
content is preserved (same share classes, same shares, same prices) so the
parser + checklist + waterfall still produce identical structured output once
the parser strips title rows and subtotal rows.

Run: .venv/bin/python scripts/rebuild_fixture_02_messy_xlsx.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).parent.parent / "fixtures" / "fixture_02_typical_messy" / "cap_table.xlsx"


def build():
    wb = Workbook()

    # --- Company tab (kept simple) ---
    ws_co = wb.active
    ws_co.title = "Company"
    ws_co.append(["Company", "Pelaut Logistics Pte. Ltd."])
    ws_co.append(["Jurisdiction", "Singapore"])
    ws_co.append(["Sector", "Cross-border logistics SaaS (SEA)"])
    ws_co.append(["Stage", "Series B"])
    ws_co.append(["Valuation Date", "2026-04-30"])
    ws_co.column_dimensions["A"].width = 22
    ws_co.column_dimensions["B"].width = 40

    # --- Cap Table tab — messy structure ---
    ws = wb.create_sheet("Cap Table")
    bold = Font(bold=True)
    title_font = Font(bold=True, size=12, color="1F2937")
    sub_font = Font(italic=True, color="475569", size=10)
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    subtotal_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    thin = Side(border_style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Row 1: merged title
    ws.cell(row=1, column=1, value="Pelaut Logistics Pte. Ltd. — Cap Table — As of 2026-04-30").font = title_font
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=11)
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 22

    # Row 2: blank spacer

    # Row 3: subheader
    ws.cell(row=3, column=1, value="Series B Round Closing — March 15, 2026 (USD)").font = sub_font
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=11)

    # Row 4: blank spacer

    # Row 5: actual headers
    headers = [
        "Class Name", "Class Type", "Quantity", "PPS (USD)", "Date Issued",
        "Seniority", "Liq Pref", "Liq Type", "Anti-Dilution", "Conv Ratio", "Footnote",
    ]
    ws.append([])  # row 4 blank
    ws.append([])  # this becomes row 5? No — append continues sequentially from current logic. Let's use explicit rows.

    # Reset: use explicit cell writes
    # Clear what we just appended (rows 4-5 from append)
    for r in [4, 5]:
        for c in range(1, 12):
            ws.cell(row=r, column=c, value=None)

    # Row 5 = headers
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=c, value=h)
        cell.font = bold
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="left", vertical="center")

    # Data rows — common, preferred classes (with stale dates / mixed formats), then subtotal,
    # then option pools, then total.

    # Row 6: Founders Common
    data_rows = [
        # (Class Name, Type, Qty, PPS, Date Issued, Seniority, Liq Pref, Liq Type, AD, ConvR, Footnote)
        ("Founders Common", "common", 5000000, 0.0001, "Sep 12, 2021", 99, None, None, None, None,
         "Common stock issued to founders at incorporation; restricted stock subject to 4-year vesting (fully vested as of 2025-09)."),
        ("Series Seed Preferred", "preferred", 1500000, 0.40, "11/4/2022", 3, 1, "non_participating",
         "broad_based_weighted_average", 1,
         "Seed round led by Surya Capital. Standard NVCA Series Seed terms."),
        ("Series A Preferred", "preferred", 3000000, 1.50, "2024-02-08", 2, 1, "non_participating",
         None, 1,
         "Series A led by ASEAN Ventures. AD variant blank — see disclosure note 4."),
        ("Series B Preferred", "preferred", 4000000, 4.00, "15-Mar-2026", 1, 1, "non_participating",
         "broad_based_weighted_average", 1,
         "Series B closing 15-Mar-2026. Strategic investor MFN side letter — see SL02-01."),
    ]

    row_cursor = 6
    for d in data_rows:
        for c, v in enumerate(d, start=1):
            cell = ws.cell(row=row_cursor, column=c, value=v)
            cell.border = border
            if c == 11:  # footnote column wraps
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        row_cursor += 1

    # Subtotal — Preferred (mid-data)
    subtotal_row_idx = row_cursor
    ws.cell(row=subtotal_row_idx, column=1, value="Subtotal — Preferred").font = bold
    ws.cell(row=subtotal_row_idx, column=3, value=8500000).font = bold  # 1.5M + 3M + 4M
    for c in range(1, 12):
        ws.cell(row=subtotal_row_idx, column=c).fill = subtotal_fill
        ws.cell(row=subtotal_row_idx, column=c).border = border
    row_cursor += 1

    # Blank spacer between preferred subtotal and option pools
    row_cursor += 1

    # Option pools
    pool_rows = [
        ("Option Pool (Granted)", "option_pool_granted", 1200000, None, "2025-03-01", 99, None, None, None, None,
         "Last grant date 2025-03-01 — pre-Series B. STALE per checklist rule."),
        ("Option Pool (Reserved)", "option_pool_reserved", 800000, None, "2026-03-15", 99, None, None, None, None,
         "Reserved at Series B closing. Excluded from waterfall per market practice."),
    ]
    for d in pool_rows:
        for c, v in enumerate(d, start=1):
            cell = ws.cell(row=row_cursor, column=c, value=v)
            cell.border = border
            if c == 11:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        row_cursor += 1

    # Total Fully Diluted (final row, often present in client files)
    total_idx = row_cursor + 1  # one blank row before total
    ws.cell(row=total_idx, column=1, value="Total Fully Diluted").font = bold
    ws.cell(row=total_idx, column=3, value=14500000).font = bold  # 5M + 8.5M + 1.2M (granted) — reserved excluded by analyst convention here
    for c in range(1, 12):
        ws.cell(row=total_idx, column=c).fill = subtotal_fill
        ws.cell(row=total_idx, column=c).border = border

    # Column widths
    widths = [26, 22, 14, 12, 14, 10, 10, 22, 28, 10, 60]
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w

    # --- Convertibles tab (preserved) ---
    ws_cv = wb.create_sheet("Convertibles")
    cv_headers = [
        "Instrument ID", "Type", "Holder / Counterparty", "Principal (USD)",
        "Valuation Cap (USD)", "Discount %", "Issue Date", "Trigger / Notes",
    ]
    for c, h in enumerate(cv_headers, start=1):
        cell = ws_cv.cell(row=1, column=c, value=h)
        cell.font = bold
        cell.fill = header_fill
    convertibles = [
        ("SAFE-2024-A", "SAFE (post-money)", "Bridge investor", 500000, 4500000, None, "2024-08-12",
         "Converts on next preferred financing >= $5M. Conversion at lower of round price or cap-implied price."),
        ("SAFE-2024-B", "SAFE (post-money)", "Bridge investor", 500000, 4500000, None, "2024-09-04",
         "Converts on next preferred financing >= $5M. Conversion at lower of round price or cap-implied price."),
        ("WAR02-01", "Warrant", "Northstar Marketing Pte. Ltd.", None, None, None, "2025-06-15",
         "Warrant for 50,000 Common shares @ $0.10/share. Expires 2030-06-15."),
    ]
    for r, row in enumerate(convertibles, start=2):
        for c, v in enumerate(row, start=1):
            ws_cv.cell(row=r, column=c, value=v)
    cv_widths = [16, 18, 32, 16, 18, 12, 14, 60]
    for c, w in enumerate(cv_widths, start=1):
        ws_cv.column_dimensions[get_column_letter(c)].width = w

    # --- Side Letters tab ---
    ws_sl = wb.create_sheet("Side Letters")
    ws_sl.append(["ID", "Title", "Summary"])
    for c in range(1, 4):
        ws_sl.cell(row=1, column=c).font = bold
        ws_sl.cell(row=1, column=c).fill = header_fill
    ws_sl.append([
        "SL02-01",
        "MFN — Strategic Investor (Series B)",
        "MFN clause grants the Series B strategic investor the right to elect more-favorable terms granted to subsequent investors. Scope undefined.",
    ])
    ws_sl.column_dimensions["A"].width = 12
    ws_sl.column_dimensions["B"].width = 38
    ws_sl.column_dimensions["C"].width = 80

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}")
    print(f"  Cap Table sheet has merged title row, subheader, headers on row 5,")
    print(f"  data rows 6-9 (preferred + common), subtotal row {subtotal_row_idx},")
    print(f"  pool rows, and total-fully-diluted row {total_idx}.")


if __name__ == "__main__":
    build()
