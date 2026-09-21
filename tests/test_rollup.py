"""Holder-level Indian-CFO Excel rollup tests (SYSTEM_SPEC §3.3)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import openpyxl
import pytest

from src.rollup import (
    aggregate_holders,
    is_holder_level_workbook,
    synthesised_class_level_workbook,
)


def _make_holder_xlsx(rows: list[tuple], header: list[str]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cap Table"
    ws.append(header)
    for r in rows:
        ws.append(list(r))
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
        wb.save(fh.name)
    return Path(fh.name)


def test_is_holder_level_detects_holder_column():
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A Sharma", 100, 1.0, "2023-01-01"),
            ("Mrs. B Iyer", 200, 1.0, "2023-01-01"),
        ],
        header=["Holder Name", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        assert is_holder_level_workbook(p)
    finally:
        p.unlink(missing_ok=True)


def test_is_holder_level_detects_name_shape_without_header_hint():
    """Workbook without an explicit 'Holder' header but with name-shaped
    data should still trigger holder-level detection."""
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A Sharma", 100, 1.0, "2023-01-01"),
            ("Ms. B Iyer", 200, 1.0, "2023-01-01"),
            ("Dr. C Patel", 50, 1.0, "2023-01-01"),
        ],
        header=["Name", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        assert is_holder_level_workbook(p)
    finally:
        p.unlink(missing_ok=True)


def test_is_holder_level_returns_false_for_class_level():
    p = _make_holder_xlsx(
        rows=[
            ("Common Stock", "common", 1000),
            ("Series A Preferred", "preferred", 500),
        ],
        header=["Class Name", "Type", "Shares"],
    )
    try:
        assert not is_holder_level_workbook(p)
    finally:
        p.unlink(missing_ok=True)


def test_rollup_explicit_class_column_high_confidence():
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A", "Series A", 100, 0.50, "2023-01-01"),
            ("Ms. B", "Series A", 50, 0.50, "2023-01-01"),
            ("Mr. C", "Series Seed", 200, 0.10, "2022-06-15"),
        ],
        header=["Holder", "Class", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        result = aggregate_holders(p)
        labels = {g.class_name for g in result.groups}
        assert "Series A" in labels
        assert "Series Seed" in labels
        assert not result.requires_manual_mapping
    finally:
        p.unlink(missing_ok=True)


def test_rollup_date_price_cluster_when_no_class_column():
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A", 100, 0.50, "2023-01-01"),
            ("Ms. B", 50, 0.50, "2023-01-01"),
            ("Mr. C", 200, 0.10, "2022-06-15"),
        ],
        header=["Holder", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        result = aggregate_holders(p)
        # Two clusters: (2023, 0.50) and (2022, 0.10).
        assert len([g for g in result.groups if "Cluster" in g.class_name]) == 2
        assert result.rollup_confidence >= 0.80
    finally:
        p.unlink(missing_ok=True)


def test_rollup_low_confidence_triggers_manual_mapping():
    """No class column, no useful clustering, name patterns mostly miss →
    rollup_confidence < 0.80 → requires_manual_mapping = True."""
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A", 100, None, None),
            ("Ms. B", 200, None, None),
            ("Dr. C", 300, None, None),
        ],
        header=["Holder", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        result = aggregate_holders(p)
        assert result.requires_manual_mapping
    finally:
        p.unlink(missing_ok=True)


def test_rollup_records_every_grouping_decision():
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A", "Series A", 100, 0.50, "2023-01-01"),
            ("Ms. B", "Series A", 50, 0.50, "2023-01-01"),
        ],
        header=["Holder", "Class", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        from src.parser import ParseReport
        report = ParseReport()
        aggregate_holders(p, report)
        codes = [w.code for w in report.warnings]
        assert "holder_rollup_applied" in codes
        assert "holder_rollup_group" in codes
    finally:
        p.unlink(missing_ok=True)


def test_synthesised_workbook_parses_back_through_standard_parser():
    """Rollup output must be ingestable by the standard parser."""
    p = _make_holder_xlsx(
        rows=[
            ("Mr. A", "Common Stock", 100, 0.001, "2020-01-01"),
            ("Ms. B", "Common Stock", 200, 0.001, "2020-01-01"),
            ("Mr. C", "Series Seed", 500, 0.10, "2022-06-15"),
        ],
        header=["Holder", "Class", "Shares", "Issue Price", "Issue Date"],
    )
    try:
        result = aggregate_holders(p)
        wb = synthesised_class_level_workbook(result)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
            wb.save(fh.name)
            out_path = Path(fh.name)
        try:
            from src.parser import parse_excel
            ct, _ = parse_excel(out_path)
            # All rolled-up classes default to "common" pending analyst
            # re-tag in manual-mapping. Shares are preserved (the key
            # property — never silently drop a row).
            assert any(sc.name == "Common Stock" for sc in ct.share_classes)
            assert any(sc.name == "Series Seed" for sc in ct.share_classes)
            for sc in ct.share_classes:
                assert sc.type.value == "common"
        finally:
            out_path.unlink(missing_ok=True)
    finally:
        p.unlink(missing_ok=True)
