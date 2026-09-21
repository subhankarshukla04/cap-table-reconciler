"""Snapshot-diff workpaper export (W7.5).

Renders a `TimelineDiff` as a multi-tab xlsx workpaper that an analyst
can hand to a reviewer or attach to a memo. Tabs:

  - Summary       — engagement id, snapshot headers, aggregate counts
  - Class Drift   — one row per (class, field) with N snapshot columns +
                    magnitude tier
  - Snapshots     — full metadata per snapshot (id, created_at, by,
                    source_filename, change_note)

Cell colour-coding mirrors the HTML UI's magnitude tiers so the analyst
sees the same visual cues in the workpaper.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .snapshot_timeline import TimelineDiff
from .xlsx_stability import pin_workbook_properties, stabilise_xlsx_bytes


# SD-AUD-W7-B2: openpyxl rejects these via IllegalCharacterError. The
# upload route validates new uploads, but legacy snapshots written before
# the validator landed could still carry control chars; strip defensively
# at every ws.cell site that takes free-form user text.
_ILLEGAL_XLSX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _safe_cell(v: Optional[str]) -> str:
    if not v:
        return ""
    cleaned = _ILLEGAL_XLSX.sub("", str(v))
    # SD-AUD-W7-m2: Excel cell text limit is 32767 chars.
    return cleaned[:32767]


_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="1F4D8A")
_TIER_FILLS = {
    "none": None,
    "minor": PatternFill("solid", fgColor="E6F0FB"),
    "material": PatternFill("solid", fgColor="FFF0C8"),
    "major": PatternFill("solid", fgColor="FDE2E2"),
}


def _hdr(cell, text: str) -> None:
    cell.value = text
    cell.font = _HEADER_FONT
    cell.fill = _HEADER_FILL
    cell.alignment = Alignment(vertical="center")


def _fill_for_tier(tier: str):
    return _TIER_FILLS.get(tier)


# Back-compat: prior tests imported `_pin_xlsx_properties` from this
# module. Re-export the shared helper under the old name so they keep
# working (closes SD-AUD-W8-m1's shared-helper requirement without
# breaking the wave-8 test surface).
_pin_xlsx_properties = pin_workbook_properties


def build_diff_workpaper_xlsx(diff: TimelineDiff) -> bytes:
    """Render the TimelineDiff as xlsx bytes. Pure function; no I/O."""
    wb = Workbook()
    # W8.4: pin core.xml timestamps to the oldest snapshot's created_at
    # so two calls produce identical bytes.
    anchor = diff.snapshots[0].created_at if diff.snapshots else None
    pin_workbook_properties(wb, anchor)

    # ---- Summary tab ----
    ws = wb.active
    ws.title = "Summary"
    _hdr(ws["A1"], "Snapshot-diff workpaper")
    ws.merge_cells("A1:F1")
    ws["A3"] = "Snapshots compared"
    ws["B3"] = len(diff.snapshots)
    ws["A4"] = "Classes changed"
    ws["B4"] = diff.classes_changed
    ws["A5"] = "Classes added"
    ws["B5"] = diff.classes_added
    ws["A6"] = "Classes removed"
    ws["B6"] = diff.classes_removed

    _hdr(ws["A8"], "#")
    _hdr(ws["B8"], "Snapshot id")
    _hdr(ws["C8"], "Created at (UTC)")
    _hdr(ws["D8"], "By")
    _hdr(ws["E8"], "Source filename")
    _hdr(ws["F8"], "Change note")
    for i, s in enumerate(diff.snapshots, start=1):
        r = 8 + i
        ws.cell(row=r, column=1, value=f"S{i}")
        ws.cell(row=r, column=2, value=s.id)
        ws.cell(row=r, column=3, value=s.created_at.strftime("%Y-%m-%d %H:%M"))
        ws.cell(row=r, column=4, value=_safe_cell(s.created_by))
        ws.cell(row=r, column=5, value=_safe_cell(s.source_filename))
        ws.cell(row=r, column=6, value=_safe_cell(s.change_note))
    for col, width in zip("ABCDEF", (6, 38, 18, 16, 28, 60)):
        ws.column_dimensions[col].width = width

    # ---- Class Drift tab ----
    cd = wb.create_sheet("Class Drift")
    _hdr(cd.cell(row=1, column=1), "Class")
    _hdr(cd.cell(row=1, column=2), "Field")
    _hdr(cd.cell(row=1, column=3), "Magnitude")
    for i, _ in enumerate(diff.snapshots, start=1):
        _hdr(cd.cell(row=1, column=3 + i), f"S{i}")

    row = 2
    field_specs = [
        ("shares_outstanding", lambda v: v.shares_outstanding),
        ("issue_price", lambda v: v.issue_price),
        ("seniority_rank", lambda v: v.seniority_rank),
        ("lp_variant_label", lambda v: v.lp_variant_label),
        ("conversion_ratio", lambda v: v.conversion_ratio),
        ("anti_dilution_variant", lambda v: v.anti_dilution_variant),
    ]
    for cr in diff.class_rows:
        for fld, accessor in field_specs:
            tier = cr.field_tiers.get(fld, "none")
            cd.cell(row=row, column=1, value=cr.class_name)
            cd.cell(row=row, column=2, value=fld)
            tier_cell = cd.cell(row=row, column=3, value=tier)
            fill = _fill_for_tier(tier)
            if fill is not None:
                tier_cell.fill = fill
            for i, v in enumerate(cr.views, start=1):
                val = accessor(v)
                # Strings may carry control chars (legacy data); numeric
                # values pass through as-is.
                if isinstance(val, str):
                    val = _safe_cell(val)
                cell = cd.cell(row=row, column=3 + i,
                                value=val if val is not None else "")
                if fill is not None:
                    cell.fill = fill
            row += 1
    cd.column_dimensions["A"].width = 22
    cd.column_dimensions["B"].width = 24
    cd.column_dimensions["C"].width = 12
    for i in range(len(diff.snapshots)):
        cd.column_dimensions[get_column_letter(4 + i)].width = 18

    # ---- Snapshots tab (raw metadata for traceability) ----
    sn = wb.create_sheet("Snapshots")
    headers = ["#", "Snapshot id", "Created at (UTC)", "Created by",
               "Source filename", "Change note"]
    for c, h in enumerate(headers, start=1):
        _hdr(sn.cell(row=1, column=c), h)
    for i, s in enumerate(diff.snapshots, start=1):
        sn.cell(row=1 + i, column=1, value=f"S{i}")
        sn.cell(row=1 + i, column=2, value=s.id)
        sn.cell(row=1 + i, column=3, value=s.created_at.isoformat())
        sn.cell(row=1 + i, column=4, value=_safe_cell(s.created_by))
        sn.cell(row=1 + i, column=5, value=_safe_cell(s.source_filename))
        sn.cell(row=1 + i, column=6, value=_safe_cell(s.change_note))
    for col, width in zip("ABCDEF", (6, 38, 24, 16, 28, 60)):
        sn.column_dimensions[col].width = width

    buf = BytesIO()
    wb.save(buf)
    return stabilise_xlsx_bytes(buf.getvalue())


# Back-compat re-export for code that still imports the old internal name.
def _rewrite_zip_with_epoch_mtimes(blob: bytes) -> bytes:
    return stabilise_xlsx_bytes(blob)
