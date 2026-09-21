"""DCF input sidecar exporter (SYSTEM_SPEC §5.3).

Produces an Excel workbook with named ranges that an analyst-built DCF
model in Excel can link to. The tool deliberately does NOT produce a
DCF — judgment work (terminal value, WACC, comp set selection) lives
with the analyst. The sidecar contains only the cap-table layer
underneath the DCF: share counts, LP amounts, conversion ratios, by
class.

Named ranges (per spec):
  - `share_count_<ClassName>`: integer
  - `lp_amount_<ClassName>`: number (currency)
  - `conv_ratio_<ClassName>`: float (default 1.0)
  - `total_fully_diluted`: integer (sum of waterfall-relevant shares)
  - `lp_total`: number (sum of LP amounts)

Class-name characters that Excel rejects in defined-names ([ ] , : / \\ etc.)
are sanitised. The sanitisation table is logged in a sidecar sheet so the
analyst can map the named-range slug back to the class.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter

from .models import CapTable


_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")
_LEADING_DIGIT = re.compile(r"^[0-9]")
_EXCEL_RESERVED = {"C", "R", "TRUE", "FALSE"}


def _slug_for_defined_name(raw: str) -> str:
    """Excel defined-name rules: letters/digits/underscores, no leading digit,
    not equal to a reserved cell-reference token, max length conservative."""
    s = _INVALID_NAME_CHARS.sub("_", raw)
    if _LEADING_DIGIT.match(s):
        s = "_" + s
    if s.upper() in _EXCEL_RESERVED or len(s) == 0:
        s = "_" + s
    return s[:200]


def _full_range_ref(sheet: str, row: int, col: int) -> str:
    return f"'{sheet}'!${get_column_letter(col)}${row}"


def build_dcf_sidecar(cap_table: CapTable, vol_pack_readback=None) -> Workbook:
    """Build the DCF input sidecar. If `vol_pack_readback` is supplied
    (W9.3), the Read-me sheet surfaces volatility / TTL / risk-free /
    DLOM as analyst-overridable SUGGESTIONS — never as bound values.
    Preserves the "expert-led, not algorithm-only" register: the analyst
    still types the final number into their DCF model."""
    wb = Workbook()
    # Remove default sheet
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    ws = wb.create_sheet("Cap Inputs")
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="DDDDDD")
    yellow_fill = PatternFill("solid", fgColor="FFF2C8")
    headers = ["Class", "Type", "Share count", "LP amount",
               "Conversion ratio", "Issue PPS", "Issue date", "Slug"]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill

    slug_table: list[tuple[str, str]] = []
    total_shares = 0
    lp_total = 0.0
    # SD-AUD-B1: the slug-collision counter MUST iterate the same set as
    # dcf_template (non-excluded only) or the two files emit divergent
    # `share_count_<slug>` defined-names, and the template's cross-workbook
    # external reference silently points at the wrong class. We still show
    # excluded classes in the Cap Inputs sheet for analyst transparency,
    # but they receive no defined-name (the DCF template never references
    # them anyway).
    _seen_slugs: dict[str, int] = {}

    def _unique_slug(name: str) -> str:
        base = _slug_for_defined_name(name)
        n = _seen_slugs.get(base, 0)
        _seen_slugs[base] = n + 1
        if n == 0:
            return base
        return f"{base}_{n + 1}"

    for i, sc in enumerate(cap_table.share_classes):
        r = i + 2
        lp_amt = sc.liquidation_preference.amount if sc.liquidation_preference else 0.0
        conv = sc.conversion_ratio if sc.conversion_ratio is not None else 1.0

        ws.cell(row=r, column=1, value=sc.name)
        ws.cell(row=r, column=2, value=sc.type.value)
        share_cell = ws.cell(row=r, column=3, value=int(sc.shares_outstanding))
        share_cell.fill = yellow_fill
        lp_cell = ws.cell(row=r, column=4, value=lp_amt)
        lp_cell.fill = yellow_fill
        conv_cell = ws.cell(row=r, column=5, value=conv)
        conv_cell.fill = yellow_fill
        ws.cell(row=r, column=6, value=sc.issue_price if sc.issue_price is not None else "")
        ws.cell(row=r, column=7, value=sc.issue_date.isoformat() if sc.issue_date else "")

        if sc.excluded_from_waterfall:
            ws.cell(row=r, column=8, value="(excluded)")
        else:
            slug = _unique_slug(sc.name)
            slug_table.append((sc.name, slug))
            ws.cell(row=r, column=8, value=slug)
            wb.defined_names.add(DefinedName(
                f"share_count_{slug}", attr_text=_full_range_ref("Cap Inputs", r, 3)
            ))
            wb.defined_names.add(DefinedName(
                f"lp_amount_{slug}", attr_text=_full_range_ref("Cap Inputs", r, 4)
            ))
            wb.defined_names.add(DefinedName(
                f"conv_ratio_{slug}", attr_text=_full_range_ref("Cap Inputs", r, 5)
            ))
            total_shares += int(sc.shares_outstanding)
        lp_total += lp_amt

    # Totals row + named scalars.
    totals_row = len(cap_table.share_classes) + 3
    ws.cell(row=totals_row, column=1, value="Total fully diluted (waterfall basis)").font = header_font
    ws.cell(row=totals_row, column=3, value=total_shares).font = header_font
    wb.defined_names.add(DefinedName(
        "total_fully_diluted", attr_text=_full_range_ref("Cap Inputs", totals_row, 3)
    ))

    ws.cell(row=totals_row + 1, column=1, value="LP total").font = header_font
    ws.cell(row=totals_row + 1, column=4, value=lp_total).font = header_font
    wb.defined_names.add(DefinedName(
        "lp_total", attr_text=_full_range_ref("Cap Inputs", totals_row + 1, 4)
    ))

    # Auto-size columns.
    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 18

    # Named-range map: class display name -> sanitised slug.
    ns = wb.create_sheet("Named Range Map")
    ns.cell(row=1, column=1, value="Class name").font = header_font
    ns.cell(row=1, column=2, value="Slug used in defined names").font = header_font
    for i, (display, slug) in enumerate(slug_table, start=2):
        ns.cell(row=i, column=1, value=display)
        ns.cell(row=i, column=2, value=slug)
    ns.column_dimensions["A"].width = 30
    ns.column_dimensions["B"].width = 30

    # Read-me sheet.
    rm = wb.create_sheet("Read me")
    rm["A1"] = "Cap-table DCF input sidecar"
    rm["A1"].font = Font(bold=True, size=14)
    rm["A3"] = (
        "Yellow cells are inputs you can edit safely. Defined-name slugs "
        "in the 'Named Range Map' sheet let your DCF model reference each "
        "class without depending on row positions. Example formulas to use "
        "in your DCF workbook:"
    )
    rm["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    rm.row_dimensions[3].height = 60
    rm["A5"] = "=share_count_Common"
    rm["A6"] = "=lp_amount_Series_A"
    rm["A7"] = "=total_fully_diluted"
    rm.column_dimensions["A"].width = 80

    # W9.3: vol-pack-derived suggestions. Surfaced as text the analyst
    # reads, NOT as defined names the DCF formulas auto-pull. The
    # analyst types the final values into their WACC / cost-of-equity
    # cells themselves.
    # SD-AUD-W9-m5: row positions computed dynamically off rm.max_row
    # so future Read-me additions can't silently overwrite this block.
    # SD-AUD-W9-m7: the vol_pack_readback.sourcing dict (analyst's
    # provenance per input) is surfaced verbatim so the defensibility
    # trail survives into the DCF workpaper.
    if vol_pack_readback is not None and vol_pack_readback.is_valid:
        m = vol_pack_readback.market
        next_row = rm.max_row + 2
        header_cell = rm.cell(row=next_row, column=1,
            value="— OPM vol pack suggestions (analyst-overridable) —")
        header_cell.font = Font(bold=True)
        items = [
            f"Volatility (annualised): {m.volatility:.2%}",
            f"Time-to-liquidity (years): {m.time_to_liquidity_years:.2f}",
            f"Risk-free rate (continuous): {m.risk_free_rate:.2%}",
        ]
        if m.dividend_yield:
            items.append(f"Dividend yield: {m.dividend_yield:.2%}")
        if m.dlom:
            items.append(f"DLOM (common): {m.dlom:.2%}")
        for i, txt in enumerate(items, start=1):
            rm.cell(row=next_row + i, column=1, value=txt)
        sourcing_start = next_row + len(items) + 2
        if vol_pack_readback.sourcing:
            rm.cell(row=sourcing_start, column=1,
                value="Sourcing notes (analyst-supplied):").font = Font(bold=True)
            for j, (k, v) in enumerate(
                sorted(vol_pack_readback.sourcing.items()), start=1
            ):
                rm.cell(row=sourcing_start + j, column=1,
                    value=f"  {k}: {v}")
            footer_row = sourcing_start + len(vol_pack_readback.sourcing) + 2
        else:
            footer_row = sourcing_start
        footer = rm.cell(row=footer_row, column=1, value=(
            "These are suggestions sourced from the analyst-supplied "
            "vol pack. Defend the final WACC / cost-of-equity numbers "
            "in the memo; do not auto-link these cells into the DCF."
        ))
        footer.alignment = Alignment(wrap_text=True, vertical="top")
        rm.row_dimensions[footer_row].height = 45

    # Ensure deterministic sheet order.
    wb.move_sheet("Cap Inputs", offset=-len(wb.sheetnames))

    return wb


def build_dcf_sidecar_bytes(cap_table: CapTable, vol_pack_readback=None) -> bytes:
    """Convenience for HTTP / file export paths."""
    wb = build_dcf_sidecar(cap_table, vol_pack_readback=vol_pack_readback)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
