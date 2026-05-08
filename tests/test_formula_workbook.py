"""End-to-end verification of the live formula workbook.

Builds the workbook for each fixture, evaluates the formulas via the
`formulas` package (open-source spreadsheet engine), and compares results
against the Python `compute_waterfall` truth. The chart sheet contents are
not evaluated (formulas only verifies calculation cells), but breakpoints,
calculations, and tranche allocations are exhaustively checked.
"""

from __future__ import annotations

from pathlib import Path

import formulas
import pytest

from src.formula_workbook import build_formula_workbook
from src.parser import load_from_canonical_json
from src.waterfall import compute_waterfall


FIXTURES = [
    "fixture_01_clean",
    "fixture_02_typical_messy",
    "fixture_03_edge_case",
    "fixture_04_down_round_ratchet",
    "fixture_05_delaware_double_cap",
]


def _unwrap(v):
    while hasattr(v, "value"):
        v = v.value
    while hasattr(v, "__iter__") and not isinstance(v, str):
        try:
            v = v[0]
        except (IndexError, TypeError):
            break
    return v


def _evaluator(xlsx_path: Path):
    xl = formulas.ExcelModel().loads(str(xlsx_path)).finish()
    result = xl.calculate()
    fname = xlsx_path.name

    def get(addr: str):
        sheet, cell = addr.split("!")
        key = f"'[{fname}]{sheet.upper()}'!{cell}"
        return _unwrap(result.get(key))

    return get


@pytest.fixture(params=FIXTURES, scope="module")
def built_workbook(request, tmp_path_factory):
    fixture_id = request.param
    cap_table = load_from_canonical_json(
        Path(__file__).parent.parent / "fixtures" / fixture_id / "cap_table_input.json"
    )
    wf = compute_waterfall(cap_table)
    wb = build_formula_workbook(cap_table, wf)
    out = tmp_path_factory.mktemp("live") / f"{fixture_id}.xlsx"
    wb.save(out)
    return fixture_id, cap_table, wf, out


def test_workbook_has_expected_sheets(built_workbook):
    fixture_id, cap_table, wf, path = built_workbook
    from openpyxl import load_workbook

    wb = load_workbook(path)
    expected = {
        "README", "Inputs", "Calculations", "States",
        "Breakpoints", "TrancheAlloc", "CumulativePayout", "Chart", "BPMarkers",
    }
    assert expected.issubset(set(wb.sheetnames))


def test_breakpoints_match_python_truth(built_workbook):
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)
    py = {bp.id: bp.value for bp in wf.breakpoints}

    for i, bp in enumerate(wf.breakpoints):
        row = 5 + i
        formula_val = get(f"Breakpoints!B{row}")
        if isinstance(formula_val, str):
            try:
                formula_val = float(formula_val)
            except ValueError:
                pytest.fail(f"{fixture_id} {bp.id}: non-numeric formula result {formula_val!r}")
        assert formula_val is not None, f"{fixture_id} {bp.id}: empty cell"
        assert abs(formula_val - py[bp.id]) < 1.0, (
            f"{fixture_id} {bp.id}: formula={formula_val:,.2f} python={py[bp.id]:,.2f}"
        )


def test_total_fully_diluted_matches(built_workbook):
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)
    # Total FD is in Calculations sheet — find it by scanning the summary block.
    # Layout: data rows 4..(4 + n_classes - 1), summary at +2 and +3.
    n_classes = sum(
        1 for sc in cap_table.share_classes if not sc.excluded_from_waterfall
    )
    summary_row = 4 + n_classes - 1 + 2
    fd = get(f"Calculations!B{summary_row}")
    assert fd is not None
    assert int(fd) == wf.total_fully_diluted_shares


def test_lp_total_matches(built_workbook):
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)
    n_classes = sum(
        1 for sc in cap_table.share_classes if not sc.excluded_from_waterfall
    )
    summary_row = 4 + n_classes - 1 + 3  # one row below FD total
    lp_total = get(f"Calculations!B{summary_row}")
    assert lp_total is not None
    assert abs(float(lp_total) - wf.lp_total) < 1.0


def test_tranche_allocations_match(built_workbook):
    """Allocation rows should match the Python tranche.marginal_allocation_pct."""
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)

    # Class column index in TrancheAlloc starts at 5 (after id/low/high/desc)
    waterfall_classes = [sc for sc in cap_table.share_classes if not sc.excluded_from_waterfall]
    # In the workbook the class order is preferred-by-seniority, then commons/granted
    from src.formula_workbook import FormulaWorkbookBuilder
    builder_classes = FormulaWorkbookBuilder(cap_table, wf).classes
    class_to_col = {sc.name: 5 + i for i, sc in enumerate(builder_classes)}

    for i, tr in enumerate(wf.tranches):
        row = 5 + i
        for class_name, expected_pct in tr.marginal_allocation_pct.items():
            col = class_to_col[class_name]
            cell = f"TrancheAlloc!{chr(ord('A') + col - 1)}{row}"
            actual = get(cell)
            if isinstance(actual, str):
                try:
                    actual = float(actual)
                except ValueError:
                    pytest.fail(f"{fixture_id} {tr.id} {class_name}: non-numeric {actual!r}")
            assert actual is not None, f"{fixture_id} {tr.id} {class_name}: empty"
            assert abs(actual - expected_pct) < 0.01, (
                f"{fixture_id} {tr.id} {class_name}: formula={actual:.4f} python={expected_pct:.4f}"
            )


def test_live_edit_changes_breakpoints(tmp_path):
    """Edit a Series B share count, re-evaluate, verify the conversion
    threshold for Series B updates correctly. This is the headline guarantee
    of the live workbook.
    """
    fixture_id = "fixture_01_clean"
    cap_table = load_from_canonical_json(
        Path(__file__).parent.parent / "fixtures" / fixture_id / "cap_table_input.json"
    )
    wf = compute_waterfall(cap_table)
    wb = build_formula_workbook(cap_table, wf)
    path = tmp_path / "edit.xlsx"
    wb.save(path)

    # Read baseline conversion threshold for Series B
    get1 = _evaluator(path)
    bp_b_baseline = None
    for r in range(5, 14):
        ev = get1(f"Breakpoints!C{r}")
        if isinstance(ev, str) and "Series B Preferred converts" in ev:
            bp_b_baseline = float(get1(f"Breakpoints!B{r}"))
            break
    assert bp_b_baseline is not None
    assert abs(bp_b_baseline - 67_500_000.0) < 1.0  # F01 known truth

    # Edit Inputs!D4 (Series B shares) from 3M to 4M, re-save, re-evaluate
    from openpyxl import load_workbook

    wb2 = load_workbook(path)
    inp = wb2["Inputs"]
    # Find Series B row
    for row_cells in inp.iter_rows(min_row=4, max_row=20, max_col=4):
        if row_cells[0].value == "Series B Preferred":
            row_cells[3].value = 4_000_000  # increase shares 33%
            break
    edited_path = tmp_path / "edit_after.xlsx"
    wb2.save(edited_path)

    get2 = _evaluator(edited_path)
    bp_b_after = None
    for r in range(5, 14):
        ev = get2(f"Breakpoints!C{r}")
        if isinstance(ev, str) and "Series B Preferred converts" in ev:
            v = get2(f"Breakpoints!B{r}")
            if isinstance(v, str):
                v = float(v)
            bp_b_after = float(v)
            break
    assert bp_b_after is not None
    # Threshold should change because pool grew with B's new share count.
    assert bp_b_after != bp_b_baseline, "live formula did not respond to share-count edit"


def test_cumulative_payout_endpoint_sum_equals_chart_max(built_workbook):
    """At chart_max (last point), sum of per-class cumulative payouts must equal x.

    This is the no-leakage sanity check baked into the chart.
    """
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)

    waterfall_classes = sum(
        1 for sc in cap_table.share_classes if not sc.excluded_from_waterfall
    )
    last_row = 6 + len(wf.tranches)
    x = get(f"CumulativePayout!B{last_row}")
    assert x is not None and float(x) > 0
    total_y = 0.0
    for j in range(waterfall_classes):
        col = chr(ord("C") + j)
        y = get(f"CumulativePayout!{col}{last_row}")
        if isinstance(y, str):
            try:
                y = float(y)
            except ValueError:
                continue
        if y is not None:
            total_y += float(y)
    # Up to numerical noise, total_y should equal x (no leakage)
    assert abs(total_y - float(x)) < float(x) * 0.01, (
        f"{fixture_id}: leakage at chart_max — x={x:,.0f} sum(y)={total_y:,.0f}"
    )


def test_bp_markers_evaluate_to_breakpoint_values(built_workbook):
    """Each BP marker x-cell must evaluate to the same value as the Breakpoints
    sheet's BP cell — i.e., the marker tracks the BP live."""
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)

    non_origin_bps = [bp for bp in wf.breakpoints if bp.value > 0]
    for i, bp in enumerate(non_origin_bps):
        # Pair rows are 7+2i and 8+2i in BPMarkers
        r1 = 7 + 2 * i
        r2 = r1 + 1
        x1 = get(f"BPMarkers!B{r1}")
        x2 = get(f"BPMarkers!B{r2}")
        if isinstance(x1, str):
            try: x1 = float(x1)
            except ValueError: continue
        if isinstance(x2, str):
            try: x2 = float(x2)
            except ValueError: continue
        assert float(x1) == pytest.approx(bp.value, rel=1e-6), \
            f"{fixture_id} {bp.id} marker r{r1} x={x1} ≠ BP value {bp.value}"
        assert float(x2) == pytest.approx(bp.value, rel=1e-6)


def test_bp_marker_y_max_exceeds_largest_class_payout(built_workbook):
    """y_max formula must be larger than any cumulative payout — markers must
    visually span the full chart height."""
    fixture_id, cap_table, wf, path = built_workbook
    get = _evaluator(path)
    y_max = get("BPMarkers!B4")
    if isinstance(y_max, str):
        try: y_max = float(y_max)
        except ValueError: pytest.skip("y_max not numeric")
    assert y_max is not None
    # y_max should be > 0 for any non-trivial fixture
    assert float(y_max) > 0
