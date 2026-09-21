"""Shared xlsx-determinism helpers (W8.4 + SD-AUD-W8-m1 hardening).

openpyxl's `Workbook().save()` writes docProps/core.xml with wall-clock
`dcterms:modified` even when we pin `wb.properties.modified` on the
Workbook object. The zip envelope also embeds per-entry mtimes. Two
calls 1.1s apart therefore produce different bytes despite identical
cell content.

This module is the single canonical post-process. Apply at the end of
every xlsx producer that ships into a bundle / workpaper / digestible
artifact.

Usage:
    from src.xlsx_stability import pin_workbook_properties, stabilise_xlsx_bytes

    wb = Workbook()
    pin_workbook_properties(wb, anchor=eng.created_at)
    # ... build the sheets ...
    buf = BytesIO()
    wb.save(buf)
    return stabilise_xlsx_bytes(buf.getvalue())
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook


# DOS epoch — minimum representable date for zip entry mtime.
_BUNDLE_EPOCH = (1980, 1, 1, 0, 0, 0)

# Fallback anchor when caller has no stored timestamp to pin against.
# Pinned literal so every producer in the project agrees; documented in
# SYSTEM_SPEC §13.3 / §13.10.
_FALLBACK_ANCHOR = datetime(2026, 1, 1, tzinfo=timezone.utc)


def pin_workbook_properties(wb: Workbook, anchor: Optional[datetime]) -> None:
    """Pin the four `docProps/core.xml` timestamps + creator strings.
    Caller usually passes a stored timestamp (engagement.created_at,
    snapshot.created_at, or cap_table.company.valuation_date)."""
    if anchor is None:
        anchor = _FALLBACK_ANCHOR
    if anchor.tzinfo is not None:
        anchor = anchor.astimezone(timezone.utc).replace(tzinfo=None)
    wb.properties.created = anchor
    wb.properties.modified = anchor
    wb.properties.creator = "qapita-engine"
    wb.properties.lastModifiedBy = "qapita-engine"


def stabilise_xlsx_bytes(blob: bytes) -> bytes:
    """Post-process the xlsx envelope:
      1. Rewrite every ZipInfo entry's `date_time` to the DOS epoch.
      2. Scrub `dcterms:modified` in `docProps/core.xml` so it matches
         `dcterms:created` (openpyxl overrides our pinned modified
         time at save() with wall-clock).
      3. Write entries in sorted name order (stable central directory).

    Two calls of any producer that pipes through this helper produce
    byte-identical output. Verified across diff_workpaper, formula_workbook.
    """
    src = ZipFile(BytesIO(blob), "r")
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as dst:
        for name in sorted(n.filename for n in src.infolist()):
            data = src.read(name)
            if name == "docProps/core.xml":
                data = _scrub_core_xml_modified(data)
            info = ZipInfo(filename=name, date_time=_BUNDLE_EPOCH)
            info.compress_type = ZIP_DEFLATED
            dst.writestr(info, data)
    src.close()
    return out.getvalue()


def _scrub_core_xml_modified(xml: bytes) -> bytes:
    """Replace the wall-clock `dcterms:modified` with the value already
    in `dcterms:created` (which is pinned via `wb.properties.created`).
    Leaves the rest of the XML untouched."""
    text = xml.decode("utf-8")
    created = re.search(
        r"<dcterms:created[^>]*>([^<]+)</dcterms:created>", text
    )
    if not created:
        return xml
    pinned = created.group(1)
    text = re.sub(
        r"<dcterms:modified[^>]*>[^<]+</dcterms:modified>",
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{pinned}</dcterms:modified>',
        text,
    )
    return text.encode("utf-8")
