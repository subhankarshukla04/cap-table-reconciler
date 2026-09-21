"""
Live formula workbook for the Cap Table Reconciler.

Generates an Excel workbook where the breakpoints, tranche allocations, and
cumulative-payout chart are driven by formulas referencing editable input
cells. The analyst can edit any preferred class's share count, price-per-
share, LP multiple, or option-pool size — and the chart, breakpoints, and
allocation matrix recompute live, in Excel, with no Python runtime needed.

Design constraint (per Day 2-3 plan): the *regime ordering* (which class
converts first, which classes participate in which pool, etc.) is encoded as
literal strings on a hidden States sheet. Numeric inputs flow through
formulas; structural inputs do not. This is the "live formulas valid for
input edits preserving threshold ordering" guarantee printed on the README
banner.

Sheet layout:
  README           — purpose, edit limits, named-range index
  Inputs           — editable inputs (shares, PPS, LP multiple, LP type label)
  Calculations     — derived: LP amount per class, cumulative LPs, FD total
  Breakpoints      — formula-driven BP values
  States           — literal regime per (tranche × class), with pool membership
  TrancheAlloc     — formula-driven marginal allocation matrix
  CumulativePayout — long-form chart data (x = exit value, y per class)
  Chart            — native Excel scatter chart
"""

from __future__ import annotations

from typing import Optional

from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.legend import Legend
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.fill import ColorChoice
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from .models import CapTable, LPType, ShareClassType
from .waterfall import (
    WaterfallResult,
    _common_pool_for_marginal,
    _make_state,
    _regime_at_value,
)


# ---- Style constants -----------------------------------------------------

HEADER_FILL = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")
INPUT_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
DERIVED_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
BANNER_FILL = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
BANNER_FONT = Font(bold=True, color="FFFFFF", size=11)

THIN = Side(border_style="thin", color="CBD5E1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _fmt_currency(symbol: str) -> str:
    return f'{symbol}#,##0'


def _state_pool_member(state_str: str, lp_type_str: str) -> int:
    """Return 1 if this regime state contributes shares to the marginal pool, else 0.

    Mirrors `_common_pool_for_marginal` from waterfall.py:
    - "common" / "granted_pool": always 1
    - "lp" + non_participating: 0
    - "lp" + participating: 1
    - "converted" / "pure_converted": 1
    - "capped": 0
    """
    if state_str in ("common", "granted_pool"):
        return 1
    if state_str == "lp":
        return 1 if lp_type_str in ("participating_uncapped", "participating_capped") else 0
    if state_str in ("converted", "pure_converted"):
        return 1
    if state_str == "capped":
        return 0
    return 0


class FormulaWorkbookBuilder:
    """Build a live formula-driven xlsx for a given cap table + waterfall."""

    def __init__(self, cap_table: CapTable, waterfall: WaterfallResult):
        self.cap_table = cap_table
        self.waterfall = waterfall
        self.wb = Workbook()
        # W8.4: pin docProps timestamps so the workbook is bit-stable
        # across regenerations. Anchor against the company's valuation_date
        # when known (so two analysts in different timezones don't see
        # different bytes); fall back to a fixed epoch otherwise.
        from datetime import datetime as _dt, timezone as _tz
        anchor = None
        try:
            vd = cap_table.company.valuation_date
            if vd is not None:
                anchor = _dt(vd.year, vd.month, vd.day, tzinfo=_tz.utc)
        except AttributeError:
            anchor = None
        if anchor is None:
            anchor = _dt(2026, 1, 1, tzinfo=_tz.utc)
        self.wb.properties.created = anchor.replace(tzinfo=None)
        self.wb.properties.modified = anchor.replace(tzinfo=None)
        self.wb.properties.creator = "qapita-engine"
        self.wb.properties.lastModifiedBy = "qapita-engine"
        # Remove default sheet — we'll create README explicitly first
        del self.wb["Sheet"]

        # Waterfall-relevant classes in stable order: preferred (most-senior first),
        # then common, then granted pool. Reserved pool excluded.
        self.preferred = cap_table.preferred_classes_by_seniority
        self.classes = list(self.preferred)
        for sc in cap_table.share_classes:
            if sc.excluded_from_waterfall:
                continue
            if sc not in self.preferred:
                self.classes.append(sc)
        # Header row in Inputs is row 4 (rows 1-3 are titles); data starts row 4
        self.inputs_data_start = 4
        self.input_row: dict[str, int] = {
            sc.name: self.inputs_data_start + i for i, sc in enumerate(self.classes)
        }
        self.currency_symbol = cap_table.company.currency_symbol
        self.currency_fmt = _fmt_currency(self.currency_symbol)

    # ---- public ---------------------------------------------------------

    def build(self) -> Workbook:
        self._sheet_readme()
        self._sheet_inputs()
        self._sheet_calculations()
        self._sheet_states()
        self._sheet_breakpoints()
        self._sheet_tranches()
        self._sheet_cumulative_payout()
        self._sheet_chart()
        return self.wb

    # ---- helpers --------------------------------------------------------

    def _state_string(self, sc, regime_state) -> str:
        """One of: 'common', 'granted_pool', 'lp', 'converted', 'capped', 'pure_converted'."""
        if sc.type == ShareClassType.common:
            return "common"
        if sc.type == ShareClassType.option_pool_granted:
            return "granted_pool"
        return regime_state.states.get(sc.name, "lp")

    def _lp_type_str(self, sc) -> str:
        if sc.liquidation_preference is None:
            return ""
        return sc.liquidation_preference.type.value

    def _effective_shares_ref(self, sc) -> str:
        """Pool-contribution share reference: shares × conv_ratio for preferred,
        shares for common/granted-pool. Mirrors waterfall._pool_share_count.
        """
        d = self._input_cell(sc.name, "D")
        if sc.type == ShareClassType.preferred:
            i = self._input_cell(sc.name, "I")
            return f"({d}*{i})"
        return d

    def _input_cell(self, name: str, col_letter: str) -> str:
        """Return absolute reference like Inputs!$C$4 for class `name`."""
        row = self.input_row[name]
        return f"Inputs!${col_letter}${row}"

    def _add_named_range(self, name: str, ref: str) -> None:
        """Add a workbook-level named range. ref must be a sheet-qualified absolute ref."""
        # Strip leading '=' if present
        if ref.startswith("="):
            ref = ref[1:]
        self.wb.defined_names[name] = DefinedName(name=name, attr_text=ref)

    # ---- sheets ---------------------------------------------------------

    def _sheet_readme(self) -> None:
        ws = self.wb.create_sheet("README", 0)
        ws.column_dimensions["A"].width = 110

        ws["A1"] = (
            f"{self.cap_table.company.name} — Live Formula Cap-Table Workbook"
        )
        ws["A1"].font = Font(bold=True, size=14, color="0F172A")

        ws["A2"] = (
            f"Generated by Cap Table Reconciler. Currency: {self.cap_table.company.currency} "
            f"({self.currency_symbol}). Valuation date: "
            f"{self.cap_table.company.valuation_date or '—'}."
        )
        ws["A2"].font = Font(italic=True, color="475569")

        # Banner
        ws["A4"] = (
            "EDIT LIMITS: These formulas remain valid for input edits that preserve "
            "the threshold ordering of the breakpoints. Edits to share counts, "
            "prices-per-share, LP multiples, and option-pool sizes will propagate "
            "live through the workbook. Edits that change LP type, seniority, "
            "participation-cap structure, or that flip the order of conversion "
            "thresholds will silently produce incorrect output — re-export the "
            "workbook from the tool after any structural change."
        )
        ws["A4"].fill = BANNER_FILL
        ws["A4"].font = BANNER_FONT
        ws["A4"].alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[4].height = 96

        ws["A6"] = "Sheet index"
        ws["A6"].font = Font(bold=True, size=12)
        sheets = [
            ("Inputs", "Editable: shares, PPS, LP multiple. Yellow cells are user-editable."),
            ("Calculations", "Derived: LP amounts, cumulative LPs, fully-diluted total."),
            ("States", "Pre-computed regime per (tranche × class). DO NOT EDIT."),
            ("Breakpoints", "Formula-driven equity-value breakpoints. Updates with Inputs."),
            ("TrancheAlloc", "Marginal allocation matrix. Updates with Inputs."),
            ("CumulativePayout", "Per-class cumulative payout at each breakpoint. Drives chart."),
            ("Chart", "Native Excel scatter chart of the cumulative-payout curves."),
        ]
        for i, (sheet, desc) in enumerate(sheets):
            ws.cell(row=7 + i, column=1, value=f"  {sheet}: {desc}").alignment = Alignment(wrap_text=True)

        ws["A16"] = "Named ranges"
        ws["A16"].font = Font(bold=True, size=12)
        ws["A17"] = (
            "Workbook-level named ranges are defined for each preferred class's "
            "core inputs (e.g., shares, PPS, LP multiple). Excel: Formulas → Name "
            "Manager to inspect."
        )
        ws["A17"].alignment = Alignment(wrap_text=True)

    def _sheet_inputs(self) -> None:
        ws = self.wb.create_sheet("Inputs", 1)

        # Title rows
        ws["A1"] = "Editable inputs"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = (
            "Yellow cells are editable. Grey cells are derived from yellow cells "
            "and should not be edited directly."
        )
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        # Header row 3
        headers = [
            "Class Name",
            "Type",
            "Seniority",
            "Shares",
            "Price-per-share",
            "LP Multiple",
            "LP Type",
            "Cap Multiple (if capped)",
            "Conversion Ratio",
            "LP base amount",
        ]
        for i, h in enumerate(headers):
            c = ws.cell(row=3, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER

        widths = [28, 22, 12, 14, 16, 14, 24, 22, 18, 18]
        for i, w in enumerate(widths):
            ws.column_dimensions[get_column_letter(i + 1)].width = w

        # Data rows
        for sc in self.classes:
            row = self.input_row[sc.name]
            ws.cell(row=row, column=1, value=sc.name)
            ws.cell(row=row, column=2, value=sc.type.value)
            ws.cell(row=row, column=3, value=sc.seniority_rank if sc.type == ShareClassType.preferred else "")
            ws.cell(row=row, column=4, value=sc.shares_outstanding)
            ws.cell(row=row, column=5, value=sc.issue_price if sc.issue_price else "")
            lp = sc.liquidation_preference
            ws.cell(row=row, column=6, value=lp.multiple if lp else "")
            ws.cell(row=row, column=7, value=lp.type.value if lp else "")
            ws.cell(row=row, column=8, value=lp.cap_multiple if lp and lp.cap_multiple else "")
            ws.cell(row=row, column=9, value=sc.conversion_ratio if sc.conversion_ratio else 1.0)
            ws.cell(row=row, column=10, value=lp.amount if lp else "")

            # Style: yellow for editable, grey for derived/locked
            for col in (4, 5, 6, 8, 9, 10):  # editable numerics
                c = ws.cell(row=row, column=col)
                c.fill = INPUT_FILL
                c.font = Font(bold=True)
            for col in (1, 2, 3, 7):  # locked metadata
                c = ws.cell(row=row, column=col)
                c.fill = DERIVED_FILL
            for col in range(1, 11):
                ws.cell(row=row, column=col).border = BORDER
                if col == 4:
                    ws.cell(row=row, column=col).number_format = "#,##0"
                if col in (5,):
                    ws.cell(row=row, column=col).number_format = self.currency_symbol + "#,##0.0000"
                if col in (6, 8, 9):
                    ws.cell(row=row, column=col).number_format = "0.000"
                if col == 10:
                    ws.cell(row=row, column=col).number_format = self.currency_fmt

        # Named ranges per preferred class
        for sc in self.preferred:
            base = sc.name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
            self._add_named_range(f"{base}_Shares", self._input_cell(sc.name, "D"))
            self._add_named_range(f"{base}_PPS", self._input_cell(sc.name, "E"))
            self._add_named_range(f"{base}_LPMult", self._input_cell(sc.name, "F"))

    def _sheet_calculations(self) -> None:
        ws = self.wb.create_sheet("Calculations", 2)

        ws["A1"] = "Derived calculations"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = "All values below are formula-derived from Inputs."
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        headers = [
            "Class",
            "Shares (= Inputs.D)",
            "LP amount (= shares × PPS × mult)",
            "Cumulative LP (seniority order)",
        ]
        for i, h in enumerate(headers):
            c = ws.cell(row=3, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER
        for i, w in enumerate([28, 22, 28, 28]):
            ws.column_dimensions[get_column_letter(i + 1)].width = w

        # One row per class (preferred listed first by seniority for cumulative LP semantics)
        # We compute LP only for preferred; common/pool show shares with blank LP.
        cum_so_far_formula = ""
        prev_cum_addr: Optional[str] = None
        for i, sc in enumerate(self.classes):
            row = 4 + i
            ws.cell(row=row, column=1, value=sc.name).fill = DERIVED_FILL
            shares_ref = self._input_cell(sc.name, "D")
            ws.cell(row=row, column=2, value=f"={shares_ref}")
            ws.cell(row=row, column=2).number_format = "#,##0"

            if sc.type == ShareClassType.preferred and sc.liquidation_preference is not None:
                # LP = LP_base × multiple. LP_base is an editable input (defaults
                # to shares × PPS for vanilla classes, but is independent for
                # ratchet-adjusted classes where shares grew without LP growing).
                lp_base_ref = self._input_cell(sc.name, "J")
                mult_ref = self._input_cell(sc.name, "F")
                ws.cell(row=row, column=3, value=f"={lp_base_ref}*{mult_ref}")
                ws.cell(row=row, column=3).number_format = self.currency_fmt
                cum_addr = f"D{row}"
                if prev_cum_addr is None:
                    ws.cell(row=row, column=4, value=f"=C{row}")
                else:
                    ws.cell(row=row, column=4, value=f"={prev_cum_addr}+C{row}")
                ws.cell(row=row, column=4).number_format = self.currency_fmt
                prev_cum_addr = cum_addr
            else:
                ws.cell(row=row, column=3, value="—")
                ws.cell(row=row, column=4, value="—")

            for col in range(1, 5):
                ws.cell(row=row, column=col).border = BORDER

        # Summary block at bottom
        last_data_row = 4 + len(self.classes) - 1
        summary_row = last_data_row + 2
        ws.cell(row=summary_row, column=1, value="Total fully diluted shares").font = Font(bold=True)
        ws.cell(row=summary_row, column=2, value=f"=SUM(B4:B{last_data_row})")
        ws.cell(row=summary_row, column=2).number_format = "#,##0"
        ws.cell(row=summary_row, column=2).font = Font(bold=True)

        ws.cell(row=summary_row + 1, column=1, value="Total LP overhang").font = Font(bold=True)
        ws.cell(row=summary_row + 1, column=2, value=f"=SUM(C4:C{last_data_row})")
        ws.cell(row=summary_row + 1, column=2).number_format = self.currency_fmt
        ws.cell(row=summary_row + 1, column=2).font = Font(bold=True)

        # Track cumulative-LP cell per preferred class for downstream formulas
        self.calc_cumlp_row: dict[str, int] = {}
        for i, sc in enumerate(self.classes):
            if sc.type == ShareClassType.preferred:
                self.calc_cumlp_row[sc.name] = 4 + i
        self.calc_lp_row: dict[str, int] = {}
        for i, sc in enumerate(self.classes):
            if sc.type == ShareClassType.preferred:
                self.calc_lp_row[sc.name] = 4 + i
        self.calc_shares_row: dict[str, int] = {sc.name: 4 + i for i, sc in enumerate(self.classes)}
        self.calc_total_fd_row = summary_row

    def _sheet_states(self) -> None:
        """Pre-computed regime per (tranche × class) as literal strings.

        Two horizontal bands per tranche row:
          - state[class] (string)
          - pool_member[class] (1/0) — derived from state via formula

        Plus a column 'lp_paying_class' identifying which class is in pure-LP
        regime in this tranche (or empty if past LP region).
        """
        ws = self.wb.create_sheet("States", 3)
        ws.sheet_state = "visible"  # keep visible for transparency; could hide

        ws["A1"] = "Regime states per tranche (literals — DO NOT EDIT)"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = (
            "Each tranche's regime is pre-computed by the tool from the breakpoint "
            "ordering. Pool membership recomputes via formula from these literals "
            "if Inputs change in ways that don't reorder breakpoints."
        )
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        # Row 4 header: Tranche | LP-paying class | <state per class> | <pool_member per class>
        headers = ["Tranche ID", "Range Low", "Range High", "LP-paying class"]
        for sc in self.classes:
            headers.append(f"state[{sc.name}]")
        for sc in self.classes:
            headers.append(f"poolMember[{sc.name}]")
        for i, h in enumerate(headers):
            c = ws.cell(row=4, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER
            c.alignment = Alignment(horizontal="center")

        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 28
        n_classes = len(self.classes)
        for i in range(n_classes):
            ws.column_dimensions[get_column_letter(5 + i)].width = 22
            ws.column_dimensions[get_column_letter(5 + n_classes + i)].width = 22

        self.states_data_start = 5
        for i, tr in enumerate(self.waterfall.tranches):
            row = self.states_data_start + i
            ws.cell(row=row, column=1, value=tr.id)
            ws.cell(row=row, column=2, value=tr.range_low).number_format = self.currency_fmt
            ws.cell(row=row, column=3, value=tr.range_high if tr.range_high is not None else "").number_format = self.currency_fmt

            # Determine LP-paying class for this tranche by parsing description
            lp_paying = ""
            if "LP being paid" in tr.description:
                lp_paying = tr.description.replace(" LP being paid", "")
            ws.cell(row=row, column=4, value=lp_paying)

            # Compute regime at midpoint of tranche
            mid = (tr.range_low + (tr.range_high or tr.range_low + 1)) / 2
            regime = _regime_at_value(self.cap_table, mid, self.waterfall)

            # State columns
            for j, sc in enumerate(self.classes):
                state_str = self._state_string(sc, regime)
                # If LP-paying tranche, the LP-paying class is in "lp" but treat as "lp"
                ws.cell(row=row, column=5 + j, value=state_str)

            # Pool member columns — formula referencing state column + LP type from Inputs
            for j, sc in enumerate(self.classes):
                state_col = get_column_letter(5 + j)
                pm_col = get_column_letter(5 + n_classes + j)
                lp_type_ref = self._input_cell(sc.name, "G")
                # Formula: =IF(state="common",1,IF(state="granted_pool",1,IF(state="converted",1,
                #            IF(state="pure_converted",1,IF(state="capped",0,IF(AND(state="lp",
                #            OR(lp_type="participating_uncapped",lp_type="participating_capped")),1,0))))))
                state_ref = f"{state_col}{row}"
                formula = (
                    f'=IF({state_ref}="common",1,'
                    f'IF({state_ref}="granted_pool",1,'
                    f'IF({state_ref}="converted",1,'
                    f'IF({state_ref}="pure_converted",1,'
                    f'IF({state_ref}="capped",0,'
                    f'IF(AND({state_ref}="lp",OR({lp_type_ref}="participating_uncapped",{lp_type_ref}="participating_capped")),1,0))))))'
                )
                ws.cell(row=row, column=5 + n_classes + j, value=formula)

            for col in range(1, 4 + 2 * n_classes + 1):
                ws.cell(row=row, column=col).border = BORDER
                ws.cell(row=row, column=col).alignment = Alignment(horizontal="center")

        self.states_n_classes = n_classes
        self.states_last_row = self.states_data_start + len(self.waterfall.tranches) - 1

    def _sheet_breakpoints(self) -> None:
        """Formula-driven breakpoints.

        For LP-cleared events: BP = Calculations cumulative LP cell (formula chain).
        For conversion / cap-reach / pure-conversion events: encode using regime
        from the States sheet for the corresponding tranche.

        The breakpoint at index i is the boundary between tranche i and tranche
        i+1. If we have N tranches, we have N+1 boundaries. We display the
        non-zero breakpoints (BP1 = origin = 0 is included for completeness).
        """
        ws = self.wb.create_sheet("Breakpoints", 4)

        ws["A1"] = "Breakpoints (formula-driven)"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = "Each breakpoint value is a formula referencing Inputs and States."
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        headers = ["BP ID", "Value", "Event", "Notes"]
        for i, h in enumerate(headers):
            c = ws.cell(row=4, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER

        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 22
        ws.column_dimensions["C"].width = 50
        ws.column_dimensions["D"].width = 56

        bps = list(self.waterfall.breakpoints)
        self.breakpoint_rows: dict[str, int] = {}
        for i, bp in enumerate(bps):
            row = 5 + i
            ws.cell(row=row, column=1, value=bp.id)
            ws.cell(row=row, column=3, value=bp.event)

            # Formula synthesis
            value_formula, note = self._breakpoint_formula(bp)
            ws.cell(row=row, column=2, value=value_formula)
            ws.cell(row=row, column=2).number_format = self.currency_fmt
            ws.cell(row=row, column=2).font = Font(bold=True)
            ws.cell(row=row, column=4, value=note)

            for col in range(1, 5):
                ws.cell(row=row, column=col).border = BORDER

            self.breakpoint_rows[bp.id] = row

    def _breakpoint_formula(self, bp) -> tuple[str | float, str]:
        """Return (formula_or_value, note) for a breakpoint."""
        event = bp.event

        if event == "origin":
            return 0.0, "Origin (literal)"

        if "LP satisfied" in event:
            class_name = event.replace(" LP satisfied", "")
            row = self.calc_cumlp_row.get(class_name)
            if row is None:
                return bp.value, "literal (class not found)"
            return f"=Calculations!D{row}", f"Cumulative LP through {class_name}"

        if "converts to common" in event:
            class_name = event.replace(" converts to common", "")
            return self._conversion_threshold_formula(class_name, bp.value), (
                f"Conversion threshold for {class_name} (regime literal from States)"
            )

        if "participation cap reached" in event:
            class_name = event.replace(" participation cap reached", "")
            return self._cap_reach_formula(class_name, bp.value), (
                f"Participation cap reached for {class_name}"
            )

        if "pure-converts to common" in event:
            class_name = event.replace(" pure-converts to common", "")
            return self._pure_conversion_formula(class_name, bp.value), (
                f"Pure-conversion threshold for {class_name}"
            )

        return bp.value, "literal (unknown event type)"

    def _find_tranche_index_for_event(self, class_name: str, event_substr: str) -> Optional[int]:
        """Return the tranche index whose lower bound corresponds to this event,
        i.e., the tranche that *starts* at this breakpoint."""
        # We scan tranches: the tranche whose range_low equals the event's bp value
        # is the one entering the new regime.
        for idx, tr in enumerate(self.waterfall.tranches):
            if class_name in tr.description and event_substr in self._regime_summary_for_tranche(idx, class_name):
                return idx
        return None

    def _regime_summary_for_tranche(self, idx: int, class_name: str) -> str:
        tr = self.waterfall.tranches[idx]
        mid = (tr.range_low + (tr.range_high or tr.range_low + 1)) / 2
        regime = _regime_at_value(self.cap_table, mid, self.waterfall)
        return regime.states.get(class_name, "lp")

    def _state_cell_ref(self, tranche_row_in_states: int, class_idx: int) -> str:
        """Reference to State sheet cell at (state-row, state-col) for this class."""
        col = get_column_letter(5 + class_idx)
        return f"States!{col}{tranche_row_in_states}"

    def _pool_member_cell_ref(self, tranche_row: int, class_idx: int) -> str:
        col = get_column_letter(5 + self.states_n_classes + class_idx)
        return f"States!{col}{tranche_row}"

    def _synthetic_regime_for_conversion(self, class_name: str):
        """Mirror waterfall._conversion_threshold_non_participating /
        _conversion_threshold_above_capped: build a regime where the target
        is converted, juniors are converted, seniors are LP, and any capped
        junior is 'capped' (cap locked).
        """
        target = next(sc for sc in self.preferred if sc.name == class_name)
        state = _make_state(self.cap_table)
        for sc in self.preferred:
            if sc.seniority_rank > target.seniority_rank:
                # Junior — converts
                if (sc.liquidation_preference is not None
                        and sc.liquidation_preference.type == LPType.participating_capped):
                    # Capped junior stays capped (the senior-above-capped case)
                    state.states[sc.name] = "capped"
                else:
                    state.states[sc.name] = "converted"
            elif sc.name == target.name:
                state.states[sc.name] = "converted"
            # else: senior — stays "lp"
        return state

    def _conversion_threshold_formula(self, class_name: str, fallback_value: float) -> str:
        """Emit the threshold formula using a SYNTHETIC regime baked inline.

        For target T converting:
            threshold = senior_overhang + LP_T × pool / shares_T
        where senior_overhang = (for each senior LP-state class: its LP) +
              (for each capped class: its cap amount)
        and pool = sum of shares for classes in pool-state in this regime.
        """
        target_class = next((sc for sc in self.preferred if sc.name == class_name), None)
        if target_class is None:
            return str(fallback_value)
        target_lp_row = self.calc_lp_row[class_name]
        target_shares_ref = self._effective_shares_ref(target_class)
        target_lp_amount_ref = f"Calculations!C{target_lp_row}"

        regime = self._synthetic_regime_for_conversion(class_name)

        # Build overhang
        overhang_terms: list[str] = []
        for sc in self.preferred:
            if sc.name == class_name:
                continue
            sc_state = regime.states.get(sc.name, "lp")
            lp_row = self.calc_lp_row[sc.name]
            cap_mult_ref = self._input_cell(sc.name, "H")
            if sc_state == "lp":
                # Always the senior path — but this should only fire for
                # seniors (rank < target.rank).
                overhang_terms.append(f"Calculations!C{lp_row}")
            elif sc_state == "capped":
                overhang_terms.append(f"({cap_mult_ref}*Calculations!C{lp_row})")
        overhang_expr = "+".join(overhang_terms) if overhang_terms else "0"

        # Build pool from synthetic regime literals
        pool_terms = []
        for sc in self.classes:
            shares_ref = self._effective_shares_ref(sc)
            lp_type = self._lp_type_str(sc)
            sc_state = self._state_string(sc, regime)
            pm = _state_pool_member(sc_state, lp_type)
            if pm:
                pool_terms.append(shares_ref)
        pool_expr = "+".join(pool_terms) if pool_terms else "1"

        return (
            f"=({overhang_expr})+{target_lp_amount_ref}*({pool_expr})/{target_shares_ref}"
        )

    def _cap_reach_formula(self, class_name: str, fallback_value: float) -> str:
        """For participating-capped class reaching its cap:
            threshold = senior_LP_(cumulative through target) + (cap_amount - LP_target) / target_share_in_pool
            where target_share_in_pool = target_shares / pool_in_pre-cap_regime
        """
        # Find tranche where this class is in 'capped' state
        target_idx = None
        for idx, tr in enumerate(self.waterfall.tranches):
            mid = (tr.range_low + (tr.range_high or tr.range_low + 1)) / 2
            regime = _regime_at_value(self.cap_table, mid, self.waterfall)
            if regime.states.get(class_name) == "capped":
                target_idx = idx
                break
        if target_idx is None:
            return str(fallback_value)

        # Use the regime BEFORE capping (the previous tranche, in which class is 'lp')
        if target_idx > 0:
            pre_idx = target_idx - 1
        else:
            pre_idx = target_idx
        pre_row = self.states_data_start + pre_idx

        target_class = next(sc for sc in self.classes if sc.name == class_name)
        target_lp_row = self.calc_lp_row[class_name]
        target_lp_ref = f"Calculations!C{target_lp_row}"
        target_shares_ref = self._effective_shares_ref(target_class)
        cap_mult_ref = self._input_cell(class_name, "H")

        # cap_amount = cap_mult × LP_amount (in NVCA convention where cap is multiple of LP)
        cap_amount_expr = f"({cap_mult_ref}*{target_lp_ref})"

        # Senior LP cumulative through target = Calculations!D for target's row
        cum_lp_target_row = self.calc_cumlp_row[class_name]
        senior_lp_through_target = f"Calculations!D{cum_lp_target_row}"

        # Pool in pre-cap regime
        pool_terms = []
        for i, sc in enumerate(self.classes):
            pm_ref = self._pool_member_cell_ref(pre_row, i)
            shares_ref = self._effective_shares_ref(sc)
            pool_terms.append(f"{pm_ref}*{shares_ref}")
        pool_expr = "+".join(pool_terms)

        # target_share_in_pool = target_shares / pool
        # threshold = senior_LP_through_target_minus_target_LP + (cap - LP) / share_in_pool
        # Note: senior_LP_for_residual in waterfall.py is CUMULATIVE THROUGH target,
        # then residual_at_cap = cap - LP_target, divided by share fraction. So:
        # value = senior_lp_through_target + (cap - LP_target) × pool / target_shares
        return (
            f"={senior_lp_through_target}+({cap_amount_expr}-{target_lp_ref})*({pool_expr})/{target_shares_ref}"
        )

    def _pure_conversion_formula(self, class_name: str, fallback_value: float) -> str:
        """For participating-capped class abandoning cap and pure-converting:
            threshold = cap_amount × pool_in_pure_converted_regime / target_shares
        """
        target_idx = None
        for idx, tr in enumerate(self.waterfall.tranches):
            mid = (tr.range_low + (tr.range_high or tr.range_low + 1)) / 2
            regime = _regime_at_value(self.cap_table, mid, self.waterfall)
            if regime.states.get(class_name) == "pure_converted":
                target_idx = idx
                break
        if target_idx is None:
            return str(fallback_value)

        target_row = self.states_data_start + target_idx
        target_class = next(sc for sc in self.classes if sc.name == class_name)
        target_lp_row = self.calc_lp_row[class_name]
        target_lp_ref = f"Calculations!C{target_lp_row}"
        target_shares_ref = self._effective_shares_ref(target_class)
        cap_mult_ref = self._input_cell(class_name, "H")
        cap_amount_expr = f"({cap_mult_ref}*{target_lp_ref})"

        pool_terms = []
        for i, sc in enumerate(self.classes):
            pm_ref = self._pool_member_cell_ref(target_row, i)
            shares_ref = self._effective_shares_ref(sc)
            pool_terms.append(f"{pm_ref}*{shares_ref}")
        pool_expr = "+".join(pool_terms)

        return f"={cap_amount_expr}*({pool_expr})/{target_shares_ref}"

    def _sheet_tranches(self) -> None:
        """Marginal allocation matrix as formulas keyed off the States sheet."""
        ws = self.wb.create_sheet("TrancheAlloc", 5)

        ws["A1"] = "Tranche allocation matrix (formula-driven)"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = (
            "Each cell is the marginal $1 allocation for a class in that tranche. "
            "LP-paying tranches go 100% to the LP-paying class; common-pool tranches "
            "split by share-of-pool from the States sheet."
        )
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        headers = ["Tranche ID", "Range Low", "Range High", "Description"]
        for sc in self.classes:
            headers.append(sc.name)
        for i, h in enumerate(headers):
            c = ws.cell(row=4, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER

        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 50
        for i in range(len(self.classes)):
            ws.column_dimensions[get_column_letter(5 + i)].width = 16

        self.tranche_alloc_data_start = 5
        for i, tr in enumerate(self.waterfall.tranches):
            row = self.tranche_alloc_data_start + i
            states_row = self.states_data_start + i
            ws.cell(row=row, column=1, value=tr.id)
            ws.cell(row=row, column=2, value=f"=States!B{states_row}")
            ws.cell(row=row, column=2).number_format = self.currency_fmt
            ws.cell(row=row, column=3, value=f"=States!C{states_row}")
            ws.cell(row=row, column=3).number_format = self.currency_fmt
            ws.cell(row=row, column=4, value=tr.description)

            # For each class column: allocation formula
            for j, sc in enumerate(self.classes):
                lp_paying_ref = f"States!D{states_row}"
                pm_ref = self._pool_member_cell_ref(states_row, j)
                shares_ref = self._effective_shares_ref(sc)
                # pool = SUMPRODUCT of pool_member × shares for all classes
                pool_terms = []
                for k, sc2 in enumerate(self.classes):
                    pm_k = self._pool_member_cell_ref(states_row, k)
                    sh_k = self._effective_shares_ref(sc2)
                    pool_terms.append(f"{pm_k}*{sh_k}")
                pool_expr = "+".join(pool_terms)
                # Formula:
                #   if LP-paying tranche: only LP-paying class gets 100, all others 0
                #   else: pool-share allocation
                formula = (
                    f'=IF({lp_paying_ref}<>"",'
                    f'IF({lp_paying_ref}="{sc.name}",100,0),'
                    f"IF({pm_ref}=1,100*{shares_ref}/({pool_expr}),0))"
                )
                ws.cell(row=row, column=5 + j, value=formula)
                ws.cell(row=row, column=5 + j).number_format = '0.00"%"'

            for col in range(1, 5 + len(self.classes)):
                ws.cell(row=row, column=col).border = BORDER

    def _sheet_cumulative_payout(self) -> None:
        """Long-form chart data: x = exit value at each breakpoint, y per class.

        Cumulative payout for class C at breakpoint k:
            = sum over tranches t≤k of (alloc_pct[t, C] / 100) × (range_high[t] - range_low[t])

        Range_high of the last (open) tranche = chart_max = last_finite_BP × 1.3
        """
        ws = self.wb.create_sheet("CumulativePayout", 6)

        ws["A1"] = "Cumulative payout per class (chart data)"
        ws["A1"].font = Font(bold=True, size=12)

        # Compute chart_max
        finite_bps = [bp.value for bp in self.waterfall.breakpoints if bp.value > 0]
        last_bp = max(finite_bps) if finite_bps else 1_000_000
        chart_max = last_bp * 1.3
        ws["A3"] = "chart_max"
        ws["B3"] = chart_max
        ws["B3"].number_format = self.currency_fmt
        self._add_named_range("ChartMax", "CumulativePayout!$B$3")

        # Row 5: header
        headers = ["Point", "x (exit value)"]
        for sc in self.classes:
            headers.append(sc.name)
        for i, h in enumerate(headers):
            c = ws.cell(row=5, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER

        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 18
        for i in range(len(self.classes)):
            ws.column_dimensions[get_column_letter(3 + i)].width = 18

        # The chart points are the breakpoints + chart_max as the rightmost.
        # For each row, x = breakpoint value (or chart_max for last), y[C] = cumulative_payout(C, x)
        # Cumulative payout formula: sum over tranches t with range_high <= x of
        # alloc[t, C]/100 × (rh - rl), plus partial for the tranche containing x.
        # For our chart we only evaluate at exact breakpoint boundaries, so each
        # row corresponds to one tranche boundary and we accumulate the previous
        # row + delta-this-tranche × alloc.
        n_tranches = len(self.waterfall.tranches)
        bps = list(self.waterfall.breakpoints)

        # Origin row (row 6)
        ws.cell(row=6, column=1, value="P0")
        ws.cell(row=6, column=2, value=0.0).number_format = self.currency_fmt
        for j in range(len(self.classes)):
            ws.cell(row=6, column=3 + j, value=0.0).number_format = self.currency_fmt

        # For each tranche, one row at its range_high
        for i, tr in enumerate(self.waterfall.tranches):
            row = 7 + i  # rows 7..7+n_tranches-1
            ws.cell(row=row, column=1, value=f"P{i+1}")
            states_row = self.states_data_start + i
            tranche_row = self.tranche_alloc_data_start + i

            if tr.range_high is not None:
                ws.cell(row=row, column=2, value=f"=States!C{states_row}")
            else:
                ws.cell(row=row, column=2, value="=ChartMax")
            ws.cell(row=row, column=2).number_format = self.currency_fmt

            # delta_x = x_this_row - x_prev_row
            for j, sc in enumerate(self.classes):
                col = get_column_letter(3 + j)
                prev_y = f"{col}{row - 1}"
                # alloc cell is on TrancheAlloc sheet at (tranche_row, 5+j)
                alloc_cell = f"TrancheAlloc!{get_column_letter(5 + j)}{tranche_row}"
                # delta_x = B{row} - B{row-1}
                delta_x = f"(B{row}-B{row-1})"
                ws.cell(
                    row=row,
                    column=3 + j,
                    value=f"={prev_y}+{alloc_cell}/100*{delta_x}",
                )
                ws.cell(row=row, column=3 + j).number_format = self.currency_fmt

            for col in range(1, 3 + len(self.classes)):
                ws.cell(row=row, column=col).border = BORDER

        for col in range(1, 3 + len(self.classes)):
            ws.cell(row=6, column=col).border = BORDER

        self.chart_data_start_row = 6
        self.chart_data_end_row = 6 + n_tranches
        self.chart_n_classes = len(self.classes)

    def _build_bp_markers_sheet(self) -> tuple[str, list[tuple[str, int, int]]]:
        """Create a hidden-utility sheet of (x, y) pairs for vertical BP marker
        lines on the chart. Returns (sheet_name, [(bp_id, x_row1, x_row2), ...])
        for each non-origin breakpoint, where the rows hold (bp_x, 0) and
        (bp_x, y_max). The chart adds a 2-point line series per pair.

        Layout (BPMarkers sheet):
          A1: title
          B2: y_max (=MAX of cumulative payout block)
          A4 / B4 / C4 headers: BP ID | x | y
          A5..: rows for each non-origin BP, two rows per BP
        """
        ws = self.wb.create_sheet("BPMarkers", 8)
        ws["A1"] = "Breakpoint marker data (chart annotations)"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = (
            "Each non-origin breakpoint becomes a vertical dashed line on the chart. "
            "y_max is recomputed from CumulativePayout so the markers always span the "
            "full chart height after edits."
        )
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        last_y_col = get_column_letter(2 + self.chart_n_classes)
        last_y_row = self.chart_data_end_row
        ws["A4"] = "y_max"
        ws["B4"] = (
            f"=MAX(CumulativePayout!C{self.chart_data_start_row}:"
            f"{last_y_col}{last_y_row})*1.05"
        )
        ws["B4"].number_format = self.currency_fmt

        headers = ["BP ID", "x", "y"]
        for i, h in enumerate(headers):
            c = ws.cell(row=6, column=i + 1, value=h)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.border = BORDER
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 18

        marker_specs: list[tuple[str, int, int]] = []
        row = 7
        for bp in self.waterfall.breakpoints:
            if bp.value <= 0:
                continue  # skip origin
            bp_row_in_breakpoints = self.breakpoint_rows[bp.id]
            x_formula = f"=Breakpoints!B{bp_row_in_breakpoints}"
            r1, r2 = row, row + 1
            ws.cell(row=r1, column=1, value=bp.id)
            ws.cell(row=r1, column=2, value=x_formula).number_format = self.currency_fmt
            ws.cell(row=r1, column=3, value=0)
            ws.cell(row=r2, column=1, value=bp.id)
            ws.cell(row=r2, column=2, value=x_formula).number_format = self.currency_fmt
            ws.cell(row=r2, column=3, value="=BPMarkers!$B$4")
            for col in (1, 2, 3):
                ws.cell(row=r1, column=col).border = BORDER
                ws.cell(row=r2, column=col).border = BORDER
            marker_specs.append((bp.id, r1, r2))
            row += 2

        return "BPMarkers", marker_specs

    def _sheet_chart(self) -> None:
        """Native Excel scatter line chart pulling from CumulativePayout.

        Adds vertical dashed marker lines at each non-origin breakpoint so the
        analyst can see exactly where slope transitions occur. Markers update
        live whenever Inputs or breakpoint formulas change, since each marker
        x-cell references the Breakpoints sheet.
        """
        ws = self.wb.create_sheet("Chart", 7)
        ws["A1"] = "Cumulative payout chart"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = (
            "Live chart driven by CumulativePayout. Edit Inputs and watch the curves "
            "update. Vertical dashed lines mark breakpoint x-values; they update "
            "automatically when LP multiples, share counts, or cap multiples change."
        )
        ws["A2"].font = Font(italic=True, color="475569", size=10)

        chart = ScatterChart()
        chart.title = f"{self.cap_table.company.name} — cumulative payout per class"
        chart.style = 2
        chart.x_axis.title = f"Exit value ({self.currency_symbol})"
        chart.y_axis.title = f"Cumulative payout ({self.currency_symbol})"
        chart.width = 24
        chart.height = 14
        chart.legend = Legend()
        chart.legend.position = "r"

        cp = self.wb["CumulativePayout"]
        x_ref = Reference(
            cp,
            min_col=2,
            max_col=2,
            min_row=self.chart_data_start_row,
            max_row=self.chart_data_end_row,
        )
        for j in range(self.chart_n_classes):
            y_ref = Reference(
                cp,
                min_col=3 + j,
                max_col=3 + j,
                min_row=5,  # include header for series title
                max_row=self.chart_data_end_row,
            )
            series = Series(y_ref, x_ref, title_from_data=True)
            series.smooth = False
            chart.series.append(series)

        # Append vertical BP marker series — thin dashed gray, 2 points each.
        bp_sheet_name, marker_specs = self._build_bp_markers_sheet()
        bp_ws = self.wb[bp_sheet_name]
        for bp_id, r1, r2 in marker_specs:
            mx_ref = Reference(bp_ws, min_col=2, max_col=2, min_row=r1, max_row=r2)
            my_ref = Reference(bp_ws, min_col=3, max_col=3, min_row=r1, max_row=r2)
            m_series = Series(my_ref, mx_ref, title=bp_id)
            m_series.smooth = False
            line = LineProperties(
                solidFill=ColorChoice(srgbClr="94A3B8"),
                w=6350,  # ~0.5pt
                prstDash="dash",
            )
            m_series.graphicalProperties = GraphicalProperties(ln=line)
            chart.series.append(m_series)

        ws.add_chart(chart, "A4")


def build_formula_workbook(
    cap_table: CapTable,
    waterfall: WaterfallResult,
    snapshot_stamp: Optional[dict] = None,
) -> Workbook:
    """Convenience entry point.

    `snapshot_stamp` (W3.5 / closes GAP-32): when supplied, a hidden
    "Snapshot Stamp" sheet records engagement_id, snapshot_id,
    memo_version, engine_version, and generated_at. Lets a downstream
    DCF builder detect a stale sidecar by comparing the stamp's
    snapshot_id to the engagement's current head_snapshot_id.
    """
    wb = FormulaWorkbookBuilder(cap_table, waterfall).build()
    if snapshot_stamp:
        # W3-AUDIT M4: refuse to silently inject datetime.now(). Wall-
        # clock timestamps break SYSTEM_SPEC §8.10 cell-payload
        # determinism. The caller must pass an explicit `generated_at`
        # (snapshot.created_at is the natural deterministic source).
        if not snapshot_stamp.get("generated_at"):
            raise ValueError(
                "snapshot_stamp.generated_at is required (use snapshot.created_at "
                "or another deterministic source). Auto-filling with "
                "datetime.now() breaks SYSTEM_SPEC §8.10 determinism."
            )
        ws = wb.create_sheet("Snapshot Stamp")
        rows = [
            ("Field", "Value"),
            ("engagement_id", str(snapshot_stamp.get("engagement_id", ""))),
            ("snapshot_id", str(snapshot_stamp.get("snapshot_id", ""))),
            ("memo_version", str(snapshot_stamp.get("memo_version", ""))),
            ("engine_version", str(snapshot_stamp.get("engine_version", ""))),
            ("pack_version", str(snapshot_stamp.get("pack_version", ""))),
            ("generated_at", snapshot_stamp["generated_at"]),
            ("schema_version", "1"),
        ]
        for r, (k, v) in enumerate(rows, start=1):
            ws.cell(row=r, column=1, value=k)
            ws.cell(row=r, column=2, value=v)
        ws.column_dimensions["A"].width = 20
        ws.column_dimensions["B"].width = 50
        # Hide so the analyst's DCF model doesn't render it.
        ws.sheet_state = "hidden"
    return wb
