"""DCF model template (W4.3).

Generates a full-DCF Excel workbook with explicit projection, WACC,
terminal-value, and per-class allocation sheets. Yellow cells are
analyst inputs; grey cells are computed via formulas referencing the
companion DCF sidecar's named ranges (src/dcf_sidecar.py) and the
volatility input pack (src/opm/vol_pack.py).

The tool fills the STRUCTURE only. No judgment numbers. Per the §7
"expert-led" register, every projection assumption (Revenue growth,
EBITDA margins, WACC, terminal growth) is the analyst's input. The
template's job is to make those inputs unmistakable.

Sheets created (in deterministic order):

  1. "Read Me"          — how to use the workbook
  2. "Assumptions"      — yellow cells for revenue growth, margins, WACC,
                          terminal-g, tax rate
  3. "Projection"       — 5-year FCFF rollout, computed from Assumptions
  4. "Terminal Value"   — Gordon-growth TV at year 5
  5. "Equity Bridge"    — EV → equity value (subtract net debt, add cash)
  6. "Per-Class FV"     — equity allocated to each class via DCF Sidecar's
                          named ranges (share_count_*, lp_amount_*).
                          References cells like =share_count_Common.
"""

from __future__ import annotations

from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from .models import CapTable
from .dcf_sidecar import _slug_for_defined_name


# Styling ------------------------------------------------------------------

_INPUT_FILL = PatternFill("solid", fgColor="FFF2C8")  # yellow
_DERIVED_FILL = PatternFill("solid", fgColor="EAEAEA")  # grey
_HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
_HEADER_FONT = Font(bold=True)


def _full_range_ref(sheet: str, row: int, col: int) -> str:
    return f"'{sheet}'!${get_column_letter(col)}${row}"


def _yellow(cell, value=None):
    cell.value = value
    cell.fill = _INPUT_FILL


def _grey(cell, value=None):
    cell.value = value
    cell.fill = _DERIVED_FILL


def _hdr(cell, value):
    cell.value = value
    cell.fill = _HEADER_FILL
    cell.font = _HEADER_FONT


# ---- Public entry --------------------------------------------------------


PROJECTION_YEARS = 5

# W5.4 (closes wave-4 audit M-5): the DCF template references named
# ranges that live in the companion DCF sidecar workbook. Excel needs
# an explicit `[<filename>]<sheet>!<name>` external-reference syntax to
# resolve them across files; bare `=share_count_X` only resolves
# locally. The default sidecar filename is documented in the Read Me
# sheet and used in the external-reference formulas; the analyst can
# rename either file and Excel's "Edit Links → Change Source" dialog
# handles re-binding.
DEFAULT_SIDECAR_FILENAME = "dcf_sidecar.xlsx"


def _sidecar_ref(name: str, sidecar_filename: str) -> str:
    """Excel external-reference syntax for a defined name in another
    workbook. The sidecar's named ranges are workbook-scoped so the
    sheet qualifier isn't strictly required, but including it makes
    the formula resolve even when Excel can't open the sidecar live."""
    return f"'[{sidecar_filename}]Cap Inputs'!{name}"


def build_dcf_template(
    cap_table: CapTable,
    sidecar_filename: str = DEFAULT_SIDECAR_FILENAME,
) -> Workbook:
    """Build the DCF template workbook for an analyst to fill.

    Per-class allocation references defined names from the companion
    DCF sidecar (build via src/dcf_sidecar.build_dcf_sidecar). The
    sidecar's defined names are referenced via Excel external-link
    syntax (W5.4), so on first open Excel either resolves them live
    (when both workbooks are open) or prompts the analyst via "Edit
    Links → Change Source" to point at the sidecar file. The
    `sidecar_filename` argument controls the filename embedded in the
    external references; default matches the recommended convention.
    """
    wb = Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    _build_read_me(wb, sidecar_filename)
    _build_assumptions(wb)
    _build_projection(wb)
    _build_terminal_value(wb)
    _build_equity_bridge(wb)
    _build_per_class_fv(wb, cap_table, sidecar_filename)

    # Ensure deterministic order: Read Me first, Per-Class FV last.
    desired = ["Read Me", "Assumptions", "Projection", "Terminal Value",
               "Equity Bridge", "Per-Class FV"]
    for i, name in enumerate(desired):
        wb.move_sheet(name, offset=i - wb.sheetnames.index(name))
    return wb


def build_dcf_template_bytes(
    cap_table: CapTable,
    sidecar_filename: str = DEFAULT_SIDECAR_FILENAME,
) -> bytes:
    wb = build_dcf_template(cap_table, sidecar_filename=sidecar_filename)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---- Sheets --------------------------------------------------------------


def _build_read_me(wb: Workbook, sidecar_filename: str) -> None:
    rm = wb.create_sheet("Read Me")
    rm["A1"] = "DCF Input Template"
    rm["A1"].font = Font(bold=True, size=14)
    rm["A3"] = (
        f"This is the DCF INPUT template — a structured scaffold the analyst fills "
        f"in. Yellow cells are inputs YOU fill (revenue, margins, WACC, terminal-g, "
        f"tax). Grey cells are formulas computed from those inputs.\n\n"
        f"Per-Class FV references defined names from the companion DCF Sidecar "
        f"workbook (default filename: {sidecar_filename!r}). The references use "
        f"Excel external-link syntax — when the sidecar is open in the same Excel "
        f"session, lookups resolve live; otherwise use 'Edit Links → Change Source' "
        f"to point Excel at wherever you saved the sidecar.\n\n"
        f"The tool does NOT auto-pick any judgment number. Every yellow cell is a "
        f"defensible choice you must source and document (the volatility pack "
        f"contains the standardised sourcing fields)."
    )
    rm["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    rm.row_dimensions[3].height = 160
    rm.column_dimensions["A"].width = 90
    rm["A6"] = f"Expected sidecar filename: {sidecar_filename}"
    rm["A6"].font = Font(italic=True, color="555555")


def _build_assumptions(wb: Workbook) -> None:
    ws = wb.create_sheet("Assumptions")
    _hdr(ws.cell(row=1, column=1), "Assumption")
    _hdr(ws.cell(row=1, column=2), "Value")
    _hdr(ws.cell(row=1, column=3), "Slug")

    rows = [
        ("Base year revenue ($)", 10_000_000, "base_revenue"),
        ("Year 1 revenue growth (%)", 0.40, "rev_growth_y1"),
        ("Year 2 revenue growth (%)", 0.30, "rev_growth_y2"),
        ("Year 3 revenue growth (%)", 0.25, "rev_growth_y3"),
        ("Year 4 revenue growth (%)", 0.20, "rev_growth_y4"),
        ("Year 5 revenue growth (%)", 0.15, "rev_growth_y5"),
        ("EBITDA margin (%)", 0.20, "ebitda_margin"),
        ("D&A as % of revenue", 0.05, "da_pct"),
        ("Capex as % of revenue", 0.07, "capex_pct"),
        ("Change in NWC as % of revenue", 0.02, "nwc_pct"),
        ("Effective tax rate (%)", 0.21, "tax_rate"),
        ("WACC (%)", 0.12, "wacc"),
        ("Terminal growth rate (%)", 0.025, "terminal_g"),
        ("Net debt ($)", 0, "net_debt"),
        ("Cash ($)", 0, "cash"),
    ]
    for i, (label, default, slug) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=label)
        _yellow(ws.cell(row=i, column=2), default)
        ws.cell(row=i, column=3, value=slug)
        wb.defined_names.add(DefinedName(
            slug, attr_text=_full_range_ref("Assumptions", i, 2),
        ))

    for col, w in enumerate([35, 18, 28], start=1):
        ws.column_dimensions[get_column_letter(col)].width = w


def _build_projection(wb: Workbook) -> None:
    ws = wb.create_sheet("Projection")
    _hdr(ws.cell(row=1, column=1), "Year")
    for y in range(1, PROJECTION_YEARS + 1):
        _hdr(ws.cell(row=1, column=1 + y), f"Y{y}")

    # Revenue = prior × (1 + growth)
    _hdr(ws.cell(row=2, column=1), "Revenue")
    for y in range(1, PROJECTION_YEARS + 1):
        prior = "base_revenue" if y == 1 else _full_range_ref("Projection", 2, y)
        formula = f"={prior}*(1+rev_growth_y{y})"
        _grey(ws.cell(row=2, column=1 + y), formula)

    # EBITDA, D&A, Capex, ΔNWC, Tax, FCFF
    _hdr(ws.cell(row=3, column=1), "EBITDA")
    _hdr(ws.cell(row=4, column=1), "D&A")
    _hdr(ws.cell(row=5, column=1), "EBIT")
    _hdr(ws.cell(row=6, column=1), "Capex")
    _hdr(ws.cell(row=7, column=1), "ΔNWC")
    _hdr(ws.cell(row=8, column=1), "Tax on EBIT")
    _hdr(ws.cell(row=9, column=1), "FCFF")
    _hdr(ws.cell(row=10, column=1), "Discount factor")
    _hdr(ws.cell(row=11, column=1), "PV of FCFF")

    for y in range(1, PROJECTION_YEARS + 1):
        col = 1 + y
        rev_ref = _full_range_ref("Projection", 2, col)
        ebitda = f"={rev_ref}*ebitda_margin"
        da = f"={rev_ref}*da_pct"
        ebit = f"={_full_range_ref('Projection', 3, col)}-{_full_range_ref('Projection', 4, col)}"
        capex = f"={rev_ref}*capex_pct"
        nwc = f"={rev_ref}*nwc_pct"
        tax = f"={_full_range_ref('Projection', 5, col)}*tax_rate"
        fcff = (f"={_full_range_ref('Projection', 5, col)}-"
                f"{_full_range_ref('Projection', 8, col)}+"
                f"{_full_range_ref('Projection', 4, col)}-"
                f"{_full_range_ref('Projection', 6, col)}-"
                f"{_full_range_ref('Projection', 7, col)}")
        df = f"=1/(1+wacc)^{y}"
        pv = f"={_full_range_ref('Projection', 9, col)}*{_full_range_ref('Projection', 10, col)}"
        _grey(ws.cell(row=3, column=col), ebitda)
        _grey(ws.cell(row=4, column=col), da)
        _grey(ws.cell(row=5, column=col), ebit)
        _grey(ws.cell(row=6, column=col), capex)
        _grey(ws.cell(row=7, column=col), nwc)
        _grey(ws.cell(row=8, column=col), tax)
        _grey(ws.cell(row=9, column=col), fcff)
        _grey(ws.cell(row=10, column=col), df)
        _grey(ws.cell(row=11, column=col), pv)

    # Sum of PV of FCFF
    _hdr(ws.cell(row=13, column=1), "Sum of PV(FCFF)")
    start = _full_range_ref("Projection", 11, 2)
    end = _full_range_ref("Projection", 11, 1 + PROJECTION_YEARS)
    _grey(ws.cell(row=13, column=2), f"=SUM({start}:{end})")
    wb.defined_names.add(DefinedName(
        "sum_pv_fcff", attr_text=_full_range_ref("Projection", 13, 2),
    ))

    for col_idx in range(1, 2 + PROJECTION_YEARS):
        ws.column_dimensions[get_column_letter(col_idx)].width = 18


def _build_terminal_value(wb: Workbook) -> None:
    ws = wb.create_sheet("Terminal Value")
    _hdr(ws.cell(row=1, column=1), "Field")
    _hdr(ws.cell(row=1, column=2), "Value")

    rows_and_formulas = [
        ("FCFF in terminal year (Y5)", f"={_full_range_ref('Projection', 9, 1 + PROJECTION_YEARS)}"),
        ("Terminal FCFF (Y6) = Y5 × (1+g)", "=B2*(1+terminal_g)"),
        ("Terminal Value at end of Y5 = TFCFF / (WACC - g)", "=B3/(wacc-terminal_g)"),
        ("Discount factor to today", f"=1/(1+wacc)^{PROJECTION_YEARS}"),
        ("PV of Terminal Value", "=B4*B5"),
    ]
    for i, (label, formula) in enumerate(rows_and_formulas, start=2):
        ws.cell(row=i, column=1, value=label)
        _grey(ws.cell(row=i, column=2), formula)

    wb.defined_names.add(DefinedName(
        "pv_terminal_value", attr_text=_full_range_ref("Terminal Value", 6, 2),
    ))
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 20


def _build_equity_bridge(wb: Workbook) -> None:
    ws = wb.create_sheet("Equity Bridge")
    _hdr(ws.cell(row=1, column=1), "Field")
    _hdr(ws.cell(row=1, column=2), "Value")

    rows = [
        ("Enterprise Value = Sum PV(FCFF) + PV(TV)", "=sum_pv_fcff+pv_terminal_value"),
        ("Less: Net Debt", "=net_debt"),
        ("Add: Cash", "=cash"),
        ("Equity Value (total)", "=B2-B3+B4"),
    ]
    for i, (label, formula) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=label)
        _grey(ws.cell(row=i, column=2), formula)

    wb.defined_names.add(DefinedName(
        "enterprise_value", attr_text=_full_range_ref("Equity Bridge", 2, 2),
    ))
    wb.defined_names.add(DefinedName(
        "equity_value_total", attr_text=_full_range_ref("Equity Bridge", 5, 2),
    ))
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 20


def _build_per_class_fv(
    wb: Workbook,
    cap_table: CapTable,
    sidecar_filename: str,
) -> None:
    ws = wb.create_sheet("Per-Class FV")
    _hdr(ws.cell(row=1, column=1), "Class")
    _hdr(ws.cell(row=1, column=2), "Slug")
    _hdr(ws.cell(row=1, column=3), "Share count (from Sidecar)")
    _hdr(ws.cell(row=1, column=4), "% of total")
    _hdr(ws.cell(row=1, column=5), "Pro-rata Equity Value")
    _hdr(ws.cell(row=1, column=6), "Per-share FV")

    # W4-AUDIT M-4 fix: filter THEN enumerate so excluded classes don't
    # leave blank rows mid-table.
    included = [sc for sc in cap_table.share_classes if not sc.excluded_from_waterfall]
    # W5.4: collision-detection slug-unique pattern mirrors sidecar so
    # the references match what the sidecar exports for the same input.
    seen: dict[str, int] = {}

    def _slug(name: str) -> str:
        base = _slug_for_defined_name(name)
        n = seen.get(base, 0)
        seen[base] = n + 1
        return base if n == 0 else f"{base}_{n + 1}"

    total_fd_ref = _sidecar_ref("total_fully_diluted", sidecar_filename)

    for i, sc in enumerate(included, start=2):
        slug = _slug(sc.name)
        ws.cell(row=i, column=1, value=sc.name)
        ws.cell(row=i, column=2, value=slug)
        # W5.4: Excel external-link references so the sidecar resolves
        # cross-workbook instead of showing #NAME?.
        share_ref = _sidecar_ref(f"share_count_{slug}", sidecar_filename)
        _grey(ws.cell(row=i, column=3), f"={share_ref}")
        _grey(ws.cell(row=i, column=4),
              f"={_full_range_ref('Per-Class FV', i, 3)}/{total_fd_ref}")
        _grey(ws.cell(row=i, column=5),
              f"={_full_range_ref('Per-Class FV', i, 4)}*equity_value_total")
        _grey(ws.cell(row=i, column=6),
              f"=IF({_full_range_ref('Per-Class FV', i, 3)}=0,0,"
              f"{_full_range_ref('Per-Class FV', i, 5)}/"
              f"{_full_range_ref('Per-Class FV', i, 3)})")

    for col_idx in range(1, 7):
        ws.column_dimensions[get_column_letter(col_idx)].width = 24
