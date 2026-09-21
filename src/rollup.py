"""Holder-level Indian-CFO Excel rollup (SYSTEM_SPEC §3.3).

Real Indian CFO Excels are *holder-level*: one row per individual
shareholder, no class-level aggregation. The class structure is implied by
repeated values in adjacent columns or by shared issue dates. Without a
rollup layer, the standard parser drops these rows because preferred
without an LP fails validation.

This module sits BEFORE `parse_excel`. Given an arbitrary workbook, it:

  1. Decides whether the workbook is holder-level (one row per shareholder)
     or class-level (one row per share class) — the format the canonical
     parser already handles. Class-level workbooks pass through unchanged.

  2. For holder-level workbooks, applies four heuristics in priority order:
       (a) Explicit class column ("Class", "Security Type", "Instrument")
       (b) (issue_date, issue_price, instrument_type_alias) cluster
       (c) Name-pattern cluster ("Series A Investor Mr. X" -> "Series A")
       (d) Manual mapping fallback if confidence < 0.80

  3. Emits a class-level workbook AND a holder-detail sidecar (used later
     for ESOP grant-level work, never for the waterfall).

  4. Records every aggregation decision in the parse report so an auditor
     can verify which heuristic ran and which rows it grouped.

Confidence is a heuristic score in [0, 1]. Below 0.80 we refuse to ship a
guess and surface the manual-mapping UI (the analyst's escape hatch). The
spec is explicit: refusal beats fabrication.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from openpyxl import Workbook, load_workbook

from .parser import (
    CAP_TABLE_TAB_NAMES,
    ParseReport,
    ParseWarning,
    _detect_cap_table_sheet,
    _detect_columns,
    _find_header_row,
    _normalize,
    _parse_date,
    _to_float,
    _to_int,
)


# Indicators that a workbook is HOLDER-level rather than class-level. Any
# one of these in a header → likely holder-level.
_HOLDER_HEADER_HINTS = {
    "holder", "holder name", "shareholder", "shareholder name",
    "name of shareholder", "investor", "investor name",
    "name", "name of holder",
}


@dataclass
class RollupGroup:
    """One synthesised share class plus the holder rows that compose it."""
    class_name: str
    heuristic: str  # "explicit_column" | "date_price_cluster" | "name_pattern"
    confidence: float  # [0, 1]
    rows: list[dict] = field(default_factory=list)  # one dict per holder

    @property
    def total_shares(self) -> int:
        return sum(int(r.get("shares") or 0) for r in self.rows)


@dataclass
class HolderRollupResult:
    """Output of `aggregate_holders`. Either a class-level workbook is
    materialised (path) OR a manual-mapping suggestion is surfaced."""
    requires_manual_mapping: bool
    groups: list[RollupGroup] = field(default_factory=list)
    holder_sidecar: list[dict] = field(default_factory=list)  # full per-holder detail
    rollup_confidence: float = 0.0  # min(group.confidence)
    notes: list[str] = field(default_factory=list)


# ---- Detection --------------------------------------------------------------


def is_holder_level_workbook(path: Path | str) -> bool:
    """Heuristic: are >50% of cap-table-tab data rows likely individual
    shareholders rather than share classes? A "yes" means the standard
    parser will drop them; we should rollup first."""
    wb = load_workbook(Path(path), data_only=True, read_only=False)
    try:
        sheet = _detect_cap_table_sheet(wb)
        if sheet is None:
            return False
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return False
        header_idx = _find_header_row(rows)
        header = [_normalize(h or "") for h in rows[header_idx]]
        if any(h in _HOLDER_HEADER_HINTS for h in header):
            return True
        # Fallback: look at data rows. If many rows have human-name shaped
        # values in column 0 (mixed-case, contains a space), likely
        # holder-level.
        data = rows[header_idx + 1 :]
        if not data:
            return False
        name_like = 0
        nonempty = 0
        for r in data:
            if r and r[0] is not None:
                nonempty += 1
                s = str(r[0]).strip()
                if re.search(r"\b(mr|ms|mrs|dr)\.?\b", s, re.I) or (
                    " " in s and not any(k in s.lower() for k in ("series", "common", "preferred", "pool", "options", "esop"))
                ):
                    name_like += 1
        return nonempty > 0 and (name_like / nonempty) > 0.5
    finally:
        wb.close()


# ---- Aggregation ------------------------------------------------------------


def _detect_class_column(header: list[str]) -> Optional[int]:
    """Find an explicit class/instrument column, if present."""
    candidates = {"class", "share class", "security type", "instrument",
                  "instrument type", "round", "series"}
    for i, h in enumerate(header):
        if h in candidates:
            return i
    # Substring fallback (looser).
    for i, h in enumerate(header):
        if "class" in h or "instrument" in h or "security" in h or "series" in h:
            return i
    return None


def _normalize_class_label(raw: Any) -> Optional[str]:
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip()
    # Tidy: collapse whitespace, title-case common patterns
    s = re.sub(r"\s+", " ", s)
    return s


_NAME_SERIES_RE = re.compile(
    r"\b(series\s+[A-Z][0-9A-Z\-]*|seed|common|founders?|esop|option\s+pool)",
    re.I,
)


def _extract_class_from_name(holder_name: str) -> Optional[str]:
    """A holder name like 'Series A Investor — Mr. X' implies the class."""
    if not holder_name:
        return None
    m = _NAME_SERIES_RE.search(holder_name)
    if not m:
        return None
    label = m.group(1).strip().title()
    # Canonicalise "Series A" capitalisation: keep series letter uppercase.
    label = re.sub(r"^Series\s+([A-Za-z][0-9A-Za-z\-]*)$",
                   lambda m_: f"Series {m_.group(1).upper()}", label)
    return label


def _aggregate_explicit_column(
    rows: list[dict], class_col: int, header: list[str]
) -> list[RollupGroup]:
    """Aggregate by the value in `class_col` per row."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        label = _normalize_class_label(r.get("_row_raw")[class_col]) if r.get("_row_raw") else None
        if label is None:
            label = "Unclassified"
        groups[label].append(r)
    return [
        RollupGroup(
            class_name=k, heuristic="explicit_column",
            confidence=0.95 if k != "Unclassified" else 0.5,
            rows=v,
        )
        for k, v in groups.items()
    ]


def _aggregate_date_price_cluster(rows: list[dict]) -> list[RollupGroup]:
    """Group rows by (issue_date, issue_price) tuple."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("issue_date"), r.get("issue_price"))
        groups[key].append(r)
    out: list[RollupGroup] = []
    n = 1
    for (d, p), rs in groups.items():
        if d is None and p is None:
            label = "Unclassified holders"
            conf = 0.40
        else:
            d_str = d.isoformat() if isinstance(d, date) else "unknown-date"
            p_str = f"@{p}" if p is not None else ""
            label = f"Cluster {n} ({d_str}{p_str})"
            conf = 0.85
            n += 1
        out.append(RollupGroup(
            class_name=label, heuristic="date_price_cluster",
            confidence=conf, rows=rs,
        ))
    return out


def _aggregate_name_pattern(rows: list[dict]) -> list[RollupGroup]:
    groups: dict[str, list[dict]] = defaultdict(list)
    matched = 0
    for r in rows:
        label = _extract_class_from_name(str(r.get("holder_name") or ""))
        if label:
            matched += 1
            groups[label].append(r)
        else:
            groups["Unclassified"].append(r)
    if not rows:
        return []
    match_ratio = matched / len(rows)
    return [
        RollupGroup(
            class_name=k, heuristic="name_pattern",
            confidence=match_ratio if k != "Unclassified" else 0.30,
            rows=v,
        )
        for k, v in groups.items()
    ]


def aggregate_holders(
    path: Path | str, report: Optional[ParseReport] = None
) -> HolderRollupResult:
    """Run the rollup pipeline. Returns a HolderRollupResult; the caller
    decides whether to write the class-level workbook or surface the
    manual-mapping UI based on `requires_manual_mapping`."""
    report = report or ParseReport()
    wb = load_workbook(Path(path), data_only=True)
    try:
        sheet = _detect_cap_table_sheet(wb)
        if sheet is None:
            raise ValueError(
                f"No cap-table tab found. Expected one of: {CAP_TABLE_TAB_NAMES}"
            )
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise ValueError(f"Cap-table tab '{sheet}' is empty.")

        header_idx = _find_header_row(rows)
        header = [_normalize(h or "") for h in rows[header_idx]]
        col_map, _ = _detect_columns(list(rows[header_idx]))

        # Detect the holder-name column. Prefer class_name's column from the
        # standard parser detection (it doubles as holder-name in
        # holder-level workbooks); else fall back to first nonempty column.
        holder_col = col_map.get("class_name", 0)

        # Build a list of normalized row dicts.
        norm_rows: list[dict] = []
        for raw in rows[header_idx + 1 :]:
            if not raw or all(v is None or str(v).strip() == "" for v in raw):
                continue
            def at(field_name: str) -> Any:
                idx = col_map.get(field_name)
                if idx is None or idx >= len(raw):
                    return None
                return raw[idx]
            holder_name = raw[holder_col] if holder_col < len(raw) else None
            norm_rows.append({
                "holder_name": str(holder_name).strip() if holder_name is not None else "",
                "shares": _to_int(at("shares")) or 0,
                "issue_price": _to_float(at("price")),
                "issue_date": _parse_date(at("date")),
                "_row_raw": raw,
            })

        # Run heuristics in priority order.
        class_col = _detect_class_column(header)
        if class_col is not None:
            groups = _aggregate_explicit_column(norm_rows, class_col, header)
            heuristic_used = "explicit_column"
        else:
            distinct_dates = {r["issue_date"] for r in norm_rows if r["issue_date"] is not None}
            distinct_prices = {r["issue_price"] for r in norm_rows if r["issue_price"] is not None}
            if len(distinct_dates) >= 1 and (len(distinct_dates) + len(distinct_prices)) >= 2:
                groups = _aggregate_date_price_cluster(norm_rows)
                heuristic_used = "date_price_cluster"
            else:
                groups = _aggregate_name_pattern(norm_rows)
                heuristic_used = "name_pattern"

        rollup_conf = min((g.confidence for g in groups), default=0.0)
        requires_manual = rollup_conf < 0.80

        report.warnings.append(ParseWarning(
            code="holder_rollup_applied",
            message=(
                f"Holder-level workbook detected. Heuristic: {heuristic_used}. "
                f"{len(norm_rows)} holders grouped into {len(groups)} synthesised classes "
                f"with min-confidence {rollup_conf:.2f}."
            ),
            sheet=sheet,
        ))
        if requires_manual:
            report.warnings.append(ParseWarning(
                code="holder_rollup_low_confidence",
                message=(
                    f"Rollup confidence {rollup_conf:.2f} < 0.80 threshold. "
                    f"Manual mapping required before this workbook can be used "
                    f"for waterfall computation."
                ),
                sheet=sheet,
            ))

        # Record every grouping decision for audit defensibility.
        for g in groups:
            sample = ", ".join(r["holder_name"] for r in g.rows[:3])
            more = f", +{len(g.rows) - 3} more" if len(g.rows) > 3 else ""
            report.warnings.append(ParseWarning(
                code="holder_rollup_group",
                message=(
                    f"Class '{g.class_name}' (heuristic={g.heuristic}, "
                    f"conf={g.confidence:.2f}): {len(g.rows)} holders. "
                    f"Sample: {sample}{more}"
                ),
                sheet=sheet,
            ))

        return HolderRollupResult(
            requires_manual_mapping=requires_manual,
            groups=groups,
            holder_sidecar=norm_rows,
            rollup_confidence=rollup_conf,
            notes=[f"heuristic={heuristic_used}"],
        )
    finally:
        wb.close()


# ---- Synthesised class-level workbook --------------------------------------


def synthesised_class_level_workbook(result: HolderRollupResult, currency: str = "USD") -> Workbook:
    """Materialise the rollup as a class-level workbook the standard parser
    will accept. Used after manual mapping is confirmed."""
    wb = Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    ws = wb.create_sheet("Cap Table")
    ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date"])
    for g in result.groups:
        # Aggregate: total shares, weighted-avg price, earliest issue_date.
        total_shares = g.total_shares
        priced = [r for r in g.rows if r["issue_price"] is not None]
        if priced:
            total_pv = sum(int(r["shares"] or 0) * float(r["issue_price"]) for r in priced)
            avg_price = total_pv / max(sum(int(r["shares"] or 0) for r in priced), 1)
        else:
            avg_price = None
        dates = [r["issue_date"] for r in g.rows if r["issue_date"] is not None]
        earliest = min(dates) if dates else None
        # Default to "common" unless the class name unambiguously says
        # otherwise. Holder-level rows usually lack LP detail, and a
        # "preferred" default would silently drop rows at the preferred-
        # must-have-LP validator. The analyst re-tags preferred classes
        # during the manual-mapping step; until then, shares are preserved.
        lower = g.class_name.lower()
        if "option" in lower or "esop" in lower:
            type_label = "option_pool_granted"
        else:
            type_label = "common"
        ws.append([
            g.class_name,
            type_label,
            total_shares,
            avg_price if avg_price is not None else "",
            earliest.isoformat() if earliest else "",
        ])
    return wb
