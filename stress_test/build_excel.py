"""Build the Northwind Robotics stress-test workbook.

Deliberately realistic mess: title rows, subtitle, blank separator, mixed
date formats, subtotal rows, free-text Notes column carrying LP multiples
and AD variants, side letters and convertibles on separate sheets.

This file is constructed without consulting parser internals. The intent
is to test how the tool behaves on a fresh client deliverable.
"""

from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


wb = Workbook()

# ---------- Sheet 1: Cap Table ----------
ws = wb.active
ws.title = "Cap Table"

# Title block (rows 1-3) and blank (row 4)
ws["A1"] = "Northwind Robotics, Inc."
ws["A1"].font = Font(bold=True, size=14)
ws.merge_cells("A1:H1")

ws["A2"] = "Capitalization Table — Pro Forma as of April 30, 2026"
ws["A2"].font = Font(italic=True, size=11)
ws.merge_cells("A2:H2")

ws["A3"] = "Confidential — Prepared for Atlas Ventures and Series B Lead"
ws["A3"].font = Font(italic=True, size=10, color="6B7280")
ws.merge_cells("A3:H3")

# Row 4 intentionally blank

# Row 5: headers
headers = ["Holder", "Class", "Class Type", "Issue Date", "Price per Share ($)",
           "Shares", "Fully Diluted %", "Notes"]
for i, h in enumerate(headers):
    c = ws.cell(row=5, column=i + 1, value=h)
    c.font = Font(bold=True)
    c.fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")

# Data rows starting at row 6.
# Mixed date formats: most are real datetime, two are text strings (rows 13 & 14).
data = [
    # Founder common (Class F super-voting)
    ("Alana Park (Co-founder, CEO)", "Founder Common (F)", "Common (super-voting)",
     date(2021, 3, 15), 0.0001, 2_800_000, None,
     "Class F super-voting (10x votes per share); identical economic rights to ordinary common"),
    ("Mateus Silva (Co-founder, CTO)", "Founder Common (F)", "Common (super-voting)",
     date(2021, 3, 15), 0.0001, 2_000_000, None,
     "Class F super-voting (10x votes per share); identical economic rights to ordinary common"),
    # Ordinary common
    ("Lin Chen (Advisor)", "Common Stock", "Common",
     date(2022, 9, 1), 0.05, 250_000, None,
     "Advisor grant; fully vested as of 2024-09-01"),
    ("Aditya Bose (ex-engineer)", "Common Stock", "Common",
     date(2023, 4, 12), 0.20, 500_000, None,
     "Exercised 500,000 ISO post-departure (2023 cashless exercise)"),
    # Series Seed
    ("Series Seed Investors (3 angels, aggregated)", "Series Seed Preferred", "Preferred",
     date(2022, 6, 30), 0.65, 1_650_000, None,
     "1x non-participating LP, BBWA AD, 1:1 conversion; aggregate of 3 angel investors per Series Seed Stock Purchase Agreement"),
    # Series A
    ("Series A Investors (4 firms)", "Series A Preferred", "Preferred",
     date(2024, 2, 14), 1.85, 2_400_000, None,
     "1x non-participating LP, BBWA AD, 1:1 conversion"),
    # Series B-1
    ("Atlas Ventures + co-leads", "Series B-1 Preferred", "Preferred",
     "April 15, 2026", 4.20, 1_800_000, None,  # date as text — realistic mess
     "1x non-participating LP, BBWA AD, 1:1 conversion; pari passu with B-2 in seniority"),
    # Series B-2 — strategic side car at 1.5x
    ("Pinnacle Strategic Investments LLC", "Series B-2 Preferred", "Preferred (Strategic side-car)",
     "April 15, 2026", 4.20, 600_000, None,  # date as text
     "1.5x non-participating LP, BBWA AD, 1:1 conversion; pari passu with B-1 in seniority but with sweetened LP multiple per Pinnacle side letter"),
    # ESOP granted
    ("ESOP Granted (19 employees, various dates)", "Common Stock — ISOs (granted)", "Common (Options Pool)",
     date(2022, 6, 1), 1.10, 420_000, None,
     "Grants made 2022-06 through 2026-04; current FMV $1.10 per 12/31/2025 409A; 4-year vest with 1-year cliff"),
    # ESOP reserved
    ("ESOP Reserved (refresh per Series B closing)", "Common Stock — ISOs (reserved)", "Common (Options Pool)",
     None, None, 380_000, None,
     "Reserved per Series B-1 closing condition; not yet granted"),
]

for i, row in enumerate(data):
    for j, val in enumerate(row):
        ws.cell(row=6 + i, column=1 + j, value=val)
    # FD% will be a formula; leave blank for now and fill at end
    ws.cell(row=6 + i, column=7).value = None

# Subtotal rows
sub_row = 6 + len(data)
ws.cell(row=sub_row, column=1, value="Subtotal — Common Stock").font = Font(bold=True, italic=True)
ws.cell(row=sub_row, column=6, value=2_800_000 + 2_000_000 + 250_000 + 500_000).font = Font(bold=True)

ws.cell(row=sub_row + 1, column=1, value="Subtotal — Preferred Stock").font = Font(bold=True, italic=True)
ws.cell(row=sub_row + 1, column=6, value=1_650_000 + 2_400_000 + 1_800_000 + 600_000).font = Font(bold=True)

ws.cell(row=sub_row + 2, column=1, value="Subtotal — Options Pool").font = Font(bold=True, italic=True)
ws.cell(row=sub_row + 2, column=6, value=420_000 + 380_000).font = Font(bold=True)

# Grand total
ws.cell(row=sub_row + 3, column=1, value="Total Issued + Reserved (FD basis)").font = Font(bold=True)
ws.cell(row=sub_row + 3, column=6, value=12_800_000).font = Font(bold=True)

# FD% formulas for data rows referencing the grand total (row sub_row + 3)
total_row = sub_row + 3
for i in range(len(data)):
    r = 6 + i
    ws.cell(row=r, column=7, value=f"=F{r}/$F${total_row}")
    ws.cell(row=r, column=7).number_format = "0.00%"

# Footnotes
ws.cell(row=sub_row + 5, column=1,
        value='(1) See "Side Letters" tab for material side-letter terms (Atlas MFN + observer; Pinnacle ROFR).')
ws.cell(row=sub_row + 5, column=1).font = Font(italic=True, size=9, color="6B7280")
ws.cell(row=sub_row + 6, column=1,
        value='(2) See "Convertibles" tab for outstanding SAFE and warrant detail.')
ws.cell(row=sub_row + 6, column=1).font = Font(italic=True, size=9, color="6B7280")

# Column widths
widths = {"A": 36, "B": 30, "C": 28, "D": 16, "E": 14, "F": 14, "G": 14, "H": 80}
for col, w in widths.items():
    ws.column_dimensions[col].width = w


# ---------- Sheet 2: Side Letters ----------
ws_sl = wb.create_sheet("Side Letters")
ws_sl["A1"] = "Side Letters — Material Terms Summary"
ws_sl["A1"].font = Font(bold=True, size=12)

ws_sl["A3"] = "SL-01: Atlas Ventures — MFN + Board Observer"
ws_sl["A3"].font = Font(bold=True)
ws_sl["A4"] = (
    'If, in any subsequent priced round prior to a Qualified IPO, the Company grants any '
    'holder of preferred stock economic terms more favorable than the Series B-1 1x non-participating '
    'preference (excluding the Series B-2 1.5x preference granted concurrently with the Series B-1 closing), '
    'the Series B-1 holders shall be entitled to elect such terms. Atlas Ventures shall additionally have '
    'the right to designate one (1) board observer.'
)
ws_sl["A4"].alignment = Alignment(wrap_text=True, vertical="top")

ws_sl["A6"] = "SL-02: Pinnacle Strategic — ROFR + Commercial Intent"
ws_sl["A6"].font = Font(bold=True)
ws_sl["A7"] = (
    'Pinnacle shall have a right of first refusal on any future financing rounds at Series B-1 or earlier '
    'seniority, exercisable for up to 25% of the round. Pinnacle shall additionally have a non-binding '
    'commercial intent to integrate Northwind robotics into Pinnacle\'s logistics network upon achievement '
    'of $5M ARR.'
)
ws_sl["A7"].alignment = Alignment(wrap_text=True, vertical="top")

ws_sl.column_dimensions["A"].width = 100
for r in (4, 7):
    ws_sl.row_dimensions[r].height = 80


# ---------- Sheet 3: Convertibles ----------
ws_cv = wb.create_sheet("Convertibles")
ws_cv["A1"] = "Outstanding Convertible Instruments"
ws_cv["A1"].font = Font(bold=True, size=12)

# SAFE
ws_cv["A3"] = "SAFE — Pinnacle Strategic Investments LLC"
ws_cv["A3"].font = Font(bold=True)
safe_rows = [
    ("Issued", "2025-11-30"),
    ("Principal", "$750,000"),
    ("Form", "Y Combinator post-money standard SAFE"),
    ("Valuation cap", "$30,000,000 post-money"),
    ("Discount", "20%"),
    ("MFN", "Yes"),
    ("Conversion event", "Equity Financing (priced round)"),
    ("Status at 2026-04-30",
     'NOT converted — SAFE language carved out "side-car priced participations" from the Series B-1 closing; the legal opinion on whether the Series B-2 closing triggers conversion is pending. Analyst should resolve before relying on the cap table for valuation.'),
]
for i, (k, v) in enumerate(safe_rows):
    ws_cv.cell(row=4 + i, column=1, value=k).font = Font(bold=True)
    ws_cv.cell(row=4 + i, column=2, value=v)

# Warrant
ws_cv["A14"] = "Warrant — Hercules Capital"
ws_cv["A14"].font = Font(bold=True)
warrant_rows = [
    ("Issued", "2025-08-04"),
    ("Underlying class", "Series A Preferred"),
    ("Strike price", "$1.85 per share"),
    ("Shares", "75,000"),
    ("Tenor", "7 years (expires 2032-08-04)"),
    ("Trigger", "Cashless exercise upon Qualified IPO or change of control"),
    ("Source", "Hercules Capital venture-debt facility, $3.0M term loan dated 2025-08-04"),
]
for i, (k, v) in enumerate(warrant_rows):
    ws_cv.cell(row=15 + i, column=1, value=k).font = Font(bold=True)
    ws_cv.cell(row=15 + i, column=2, value=v)

ws_cv.column_dimensions["A"].width = 28
ws_cv.column_dimensions["B"].width = 80
for r in range(4, 23):
    ws_cv.row_dimensions[r].height = 18
ws_cv.row_dimensions[11].height = 64  # the long Status row

out = "/Users/subhankarshukla/Desktop/qapita/stress_test/northwind_cap_table.xlsx"
wb.save(out)
print(f"wrote {out}")
