"""Build fixture_04_down_round_ratchet/cap_table.xlsx — Surya Foods.

Tidy structure (no title rows, no subtotals) — F04 is the down-round / ratchet
story; the structural-mess story belongs to F02. This xlsx is the "clean upload"
target for the F04 demo path.

Run: .venv/bin/python scripts/build_fixture_04_xlsx.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


OUT = Path(__file__).parent.parent / "fixtures" / "fixture_04_down_round_ratchet" / "cap_table.xlsx"


def build():
    wb = Workbook()

    # --- Company tab ---
    ws_co = wb.active
    ws_co.title = "Company"
    rows = [
        ("Company", "Surya Foods Pvt. Ltd."),
        ("Jurisdiction", "India"),
        ("Sector", "B2B agritech SaaS"),
        ("Stage", "Series A2 (down-round)"),
        ("Valuation Date", "2026-04-30"),
        ("Currency", "INR"),
    ]
    for r in rows:
        ws_co.append(list(r))
    for row in ws_co.iter_rows(min_row=1, max_row=ws_co.max_row, max_col=1):
        for cell in row:
            cell.font = Font(bold=True)
    ws_co.column_dimensions["A"].width = 22
    ws_co.column_dimensions["B"].width = 40

    # --- Cap Table tab (tidy) ---
    ws = wb.create_sheet("Cap Table")
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    thin = Side(border_style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Class Name",
        "Class Type",
        "Quantity",
        "PPS (INR)",
        "Date Issued",
        "Seniority",
        "Liq Pref",
        "Liq Type",
        "Anti-Dilution",
        "Conv Ratio",
        "Footnote",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left", vertical="center")

    # post-trigger state
    data = [
        ("Founders Common", "Common", 5_000_000, 0.01, "2021-09-01", "", "", "", "", "", ""),
        (
            "Series Seed CCPS", "Preferred (CCPS)", 1_333_333, 50.00, "2022-06-15",
            3, 1.0, "Non-participating", "Full Ratchet", 1.667,
            "TRIGGERED 2026-03-12 — adjusted from 800,000 shares per SL04-02.",
        ),
        (
            "Series A CCPS", "Preferred (CCPS)", 1_500_000, 120.00, "2024-03-22",
            2, 1.0, "Non-participating", "Broad-based WA", 1.0,
            "Broad-based WA absorbed via formula; share count unchanged.",
        ),
        (
            "Series A2 CCPS", "Preferred (CCPS)", 2_000_000, 30.00, "2026-03-12",
            1, 1.0, "Non-participating", "Broad-based WA", 1.0,
            "Down-round at ₹30/sh — 75% PPS reduction vs prior. Triggered Seed ratchet.",
        ),
        ("Option Pool (Granted)", "Option Pool (Granted)", 800_000, "", "2026-03-15", "", "", "", "", "", ""),
        ("Option Pool (Reserved)", "Option Pool (Reserved)", 400_000, "", "2026-03-12", "", "", "", "", "", ""),
    ]
    for row in data:
        ws.append(list(row))

    widths = [26, 22, 14, 12, 14, 10, 10, 22, 22, 12, 60]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = w

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == 11)
            if cell.row > 1 and cell.column == 3:
                cell.number_format = "#,##0"
            if cell.row > 1 and cell.column == 4:
                cell.number_format = "₹#,##0.00"
            if cell.row > 1 and cell.column == 7:
                cell.number_format = "0.0\"x\""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
