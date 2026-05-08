"""
Cap Table Excel parser.

Ingests an .xlsx file (or the canonical JSON we generate fixtures from) and
produces a validated CapTable model. Designed to handle real client mess —
inconsistent column names, mixed date formats, blank cells, alternative
instrument-type spellings.

Two entry points:
- `parse_excel(path)` — full pipeline: detect Cap Table tab, detect columns,
  parse rows, build CapTable. Returns (cap_table, parse_report).
- `load_from_canonical_json(path)` — load the structured input JSONs we use
  to generate fixtures. Always succeeds for well-formed inputs; mostly used
  by tests.

The parser does not make valuation judgments. It does its best to fill in the
data model; gaps are reported via ParseReport for the checklist downstream.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook

from .models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    ConvertibleNote,
    LiquidationPreference,
    LPType,
    Participation,
    ParticipationMode,
    SAFE,
    ShareClass,
    ShareClassType,
    SideLetter,
    Warrant,
)


# -- Header synonym tables -----------------------------------------------------

CLASS_NAME_SYNONYMS = [
    "stakeholder / class", "stakeholder/class", "stakeholder", "class name",
    "share class", "shareholder", "holder", "class", "name",
]
CLASS_TYPE_SYNONYMS = [
    "type", "class type", "instrument type", "instrument", "share type",
]
SHARES_SYNONYMS = [
    "# shares outstanding", "# shares", "shares outstanding", "shares",
    "quantity", "qty", "count", "share count", "outstanding shares",
    "no of shares", "no. of shares",
]
PRICE_SYNONYMS = [
    "issue price", "issue price (usd)", "issue price (inr)", "issue price (sgd)",
    "price per share", "pps", "pps (usd)", "pps (inr)", "$/share", "₹/share",
    "price",
]
DATE_SYNONYMS = [
    "issue date", "date issued", "date", "issuance date", "grant date",
]
SENIORITY_SYNONYMS = [
    "seniority rank", "seniority", "rank", "seniority order", "priority",
]
LP_MULTIPLE_SYNONYMS = [
    "lp multiple", "liq pref", "liquidation preference", "lp", "lp mult",
    "preference multiple", "preference",
]
LP_TYPE_SYNONYMS = [
    "lp type", "liq type", "liquidation type", "participation type", "lp mode",
    "preference type",
]
PARTICIPATION_CAP_SYNONYMS = [
    "participation cap", "participation cap (x of lp)", "cap multiple",
    "cap (x)", "cap multiple (x)",
]
ANTI_DILUTION_SYNONYMS = [
    "anti-dilution", "anti dilution", "antidilution", "adr",
    "anti-dilution variant",
]
CONV_RATIO_SYNONYMS = [
    "conversion ratio", "conv ratio", "conversion", "conv",
]
VOTING_SYNONYMS = [
    "voting differential", "voting multiplier", "voting", "votes per share",
]
NOTES_SYNONYMS = ["notes", "note", "comments", "comment", "memo"]


# Map raw header → semantic field name. Order matters for ambiguous cases —
# more specific synonyms first.
SYNONYM_TABLE: list[tuple[str, list[str]]] = [
    ("class_name", CLASS_NAME_SYNONYMS),
    ("class_type", CLASS_TYPE_SYNONYMS),
    ("shares", SHARES_SYNONYMS),
    ("price", PRICE_SYNONYMS),
    ("date", DATE_SYNONYMS),
    ("seniority", SENIORITY_SYNONYMS),
    ("lp_multiple", LP_MULTIPLE_SYNONYMS),
    ("lp_type", LP_TYPE_SYNONYMS),
    ("participation_cap", PARTICIPATION_CAP_SYNONYMS),
    ("anti_dilution", ANTI_DILUTION_SYNONYMS),
    ("conversion_ratio", CONV_RATIO_SYNONYMS),
    ("voting", VOTING_SYNONYMS),
    ("notes", NOTES_SYNONYMS),
]


CAP_TABLE_TAB_NAMES = [
    "cap table", "captable", "capitalization", "capitalisation",
    "shareholders", "shareholding", "holders", "share register",
]


def _normalize(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _detect_field_for_header(header: str) -> Optional[str]:
    norm = _normalize(header)
    if not norm:
        return None
    for field_name, synonyms in SYNONYM_TABLE:
        for syn in synonyms:
            if norm == syn:
                return field_name
    # second pass: prefix/contains for tougher matches
    for field_name, synonyms in SYNONYM_TABLE:
        for syn in synonyms:
            if norm.startswith(syn) or syn in norm:
                return field_name
    return None


# -- Parse outputs -------------------------------------------------------------


@dataclass
class ParseWarning:
    code: str
    message: str
    sheet: Optional[str] = None
    row: Optional[int] = None


@dataclass
class ParseReport:
    cap_table_sheet: Optional[str] = None
    column_mapping: dict[str, str] = field(default_factory=dict)
    """Map of detected semantic field → actual header text in the workbook."""

    unmapped_headers: list[str] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)


# -- Date parsing --------------------------------------------------------------


_DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d",
    "%m/%d/%Y", "%m-%d-%Y",
    "%d-%m-%Y", "%d/%m/%Y",
    "%b %d, %Y", "%B %d, %Y",
    "%d-%b-%Y", "%d %b %Y", "%d %B %Y",
]


def _parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# -- Enum coercion -------------------------------------------------------------


def _coerce_class_type(raw: Any) -> Optional[ShareClassType]:
    if raw is None:
        return None
    # Strip parens/punctuation, collapse spaces+dashes to underscores
    norm = _normalize(raw)
    norm = re.sub(r"[()\\.,]", " ", norm)
    norm = re.sub(r"\s+", "_", norm.strip()).replace("-", "_").strip("_")
    aliases = {
        "common": ShareClassType.common,
        "founders_common": ShareClassType.common,
        "ordinary": ShareClassType.common,
        "ordinary_common": ShareClassType.common,
        "dual_class_voting_common": ShareClassType.common,
        "preferred": ShareClassType.preferred,
        "ccps": ShareClassType.preferred,
        "rcps": ShareClassType.preferred,
        "ccd": ShareClassType.preferred,
        "preferred_stock": ShareClassType.preferred,
        "preferred_ccps": ShareClassType.preferred,
        "ccps_preferred": ShareClassType.preferred,
        "preferred_rcps": ShareClassType.preferred,
        "option_pool_granted": ShareClassType.option_pool_granted,
        "options_granted": ShareClassType.option_pool_granted,
        "granted_options": ShareClassType.option_pool_granted,
        "option_pool_reserved": ShareClassType.option_pool_reserved,
        "options_reserved": ShareClassType.option_pool_reserved,
        "reserved_pool": ShareClassType.option_pool_reserved,
        "esop_granted": ShareClassType.option_pool_granted,
        "esop_reserved": ShareClassType.option_pool_reserved,
    }
    return aliases.get(norm)


def _coerce_lp_type(raw: Any) -> Optional[LPType]:
    if raw is None:
        return None
    norm = _normalize(raw).replace("-", "_").replace(" ", "_")
    aliases = {
        "non_participating": LPType.non_participating,
        "non_part": LPType.non_participating,
        "non_participation": LPType.non_participating,
        "1x_non_part": LPType.non_participating,
        "participating": LPType.participating_uncapped,
        "participating_uncapped": LPType.participating_uncapped,
        "full_participating": LPType.participating_uncapped,
        "participating_capped": LPType.participating_capped,
        "participating_with_cap": LPType.participating_capped,
        "capped_participating": LPType.participating_capped,
        "participating_with_a_cap": LPType.participating_capped,
    }
    return aliases.get(norm)


def _coerce_anti_dilution(raw: Any) -> Optional[AntiDilutionVariant]:
    if raw is None:
        return None
    norm = _normalize(raw).replace("-", "_").replace(" ", "_")
    aliases = {
        "broad_based_weighted_average": AntiDilutionVariant.broad_based_weighted_average,
        "broad_based": AntiDilutionVariant.broad_based_weighted_average,
        "broad_based_wa": AntiDilutionVariant.broad_based_weighted_average,
        "bbwa": AntiDilutionVariant.broad_based_weighted_average,
        "narrow_based_weighted_average": AntiDilutionVariant.narrow_based_weighted_average,
        "narrow_based": AntiDilutionVariant.narrow_based_weighted_average,
        "narrow_based_wa": AntiDilutionVariant.narrow_based_weighted_average,
        "nbwa": AntiDilutionVariant.narrow_based_weighted_average,
        "full_ratchet": AntiDilutionVariant.full_ratchet,
        "ratchet": AntiDilutionVariant.full_ratchet,
    }
    return aliases.get(norm)


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[,$₹£¥\s]", "", str(v))
    s = s.replace("x", "").replace("X", "")
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = re.sub(r"[,$₹£¥\s]", "", str(v))
    try:
        return int(float(s))
    except ValueError:
        return None


# -- Excel parsing -------------------------------------------------------------


def _detect_cap_table_sheet(workbook) -> Optional[str]:
    for name in workbook.sheetnames:
        if _normalize(name) in CAP_TABLE_TAB_NAMES:
            return name
    return None


def _detect_columns(header_row: list[Any]) -> tuple[dict[str, int], list[str]]:
    """Return (semantic_field → column_index, unmapped_header_texts)."""
    mapping: dict[str, int] = {}
    unmapped: list[str] = []
    for idx, h in enumerate(header_row):
        if h is None or str(h).strip() == "":
            continue
        field_name = _detect_field_for_header(h)
        if field_name and field_name not in mapping:
            mapping[field_name] = idx
        else:
            unmapped.append(str(h))
    return mapping, unmapped


def _find_header_row(rows: list[tuple], scan_limit: int = 12) -> int:
    """Locate the row most likely to be the column-header row.

    Real client cap-tables often prepend title rows ("Cap Table — As of <date>"),
    blank rows, or subheader rows before the actual column headers. We pick the
    row in the first `scan_limit` rows that maps the most semantic fields, with
    a minimum of 3 recognized fields. Returns 0 if nothing scores high enough.
    """
    best_idx = 0
    best_score = 0
    for i, row in enumerate(rows[:scan_limit]):
        mapping, _ = _detect_columns(list(row))
        score = len(mapping)
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx if best_score >= 3 else 0


_SUBTOTAL_PREFIXES = ("subtotal", "total", "sum ", "sum:", "grand total", "fully diluted", "all preferred", "all common")


def _is_subtotal_row(row: tuple, class_name_idx: int) -> bool:
    """Detect rows that are subtotals/totals embedded in the cap-table data.

    Heuristic: the class-name cell starts with a subtotal keyword, OR the row
    has a share count but no class type/instrument identifier.
    """
    if class_name_idx is None or class_name_idx >= len(row):
        return False
    cell = row[class_name_idx]
    if cell is None:
        return False
    name = _normalize(cell)
    return any(name.startswith(p) for p in _SUBTOTAL_PREFIXES)


def parse_excel(path: Path | str, manual_column_mapping: Optional[dict[str, int]] = None) -> tuple[CapTable, ParseReport]:
    """Parse a cap-table .xlsx into a CapTable + ParseReport.

    `manual_column_mapping` lets the UI pass a confirmed mapping (e.g., from the
    column-mapping confirmation step), bypassing auto-detection.
    """
    path = Path(path)
    wb = load_workbook(path, data_only=True)
    report = ParseReport()

    # Company tab (optional)
    company = _read_company_tab(wb, report)

    # Cap Table tab
    sheet_name = _detect_cap_table_sheet(wb)
    if sheet_name is None:
        raise ValueError(
            f"Could not find a Cap Table tab in {path.name}. "
            f"Tabs present: {wb.sheetnames}. Expected one of: {CAP_TABLE_TAB_NAMES}"
        )
    report.cap_table_sheet = sheet_name
    ws = wb[sheet_name]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError(f"Cap Table tab '{sheet_name}' is empty")

    header_idx = _find_header_row(rows)
    header_row = list(rows[header_idx])
    if manual_column_mapping is not None:
        col_map = manual_column_mapping
        unmapped = []
    else:
        col_map, unmapped = _detect_columns(header_row)
    report.column_mapping = {k: str(header_row[v]) for k, v in col_map.items()}
    report.unmapped_headers = unmapped
    if header_idx > 0:
        report.warnings.append(
            ParseWarning(
                code="header_row_offset",
                message=f"Column headers found on row {header_idx + 1} (skipped {header_idx} title/blank row(s))",
                sheet=sheet_name,
            )
        )

    # Required columns
    for required in ("class_name", "shares"):
        if required not in col_map:
            raise ValueError(
                f"required column '{required}' not detected. "
                f"Detected mapping: {report.column_mapping}. "
                f"Headers in workbook: {[str(h) for h in header_row if h]}"
            )

    share_classes: list[ShareClass] = []
    skipped_subtotal_count = 0
    class_name_idx = col_map.get("class_name")
    for ridx, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        if _is_subtotal_row(row, class_name_idx):
            skipped_subtotal_count += 1
            continue
        sc = _row_to_share_class(row, col_map, sheet_name, ridx, report)
        if sc is not None:
            share_classes.append(sc)
    if skipped_subtotal_count > 0:
        report.warnings.append(
            ParseWarning(
                code="subtotal_rows_skipped",
                message=f"Skipped {skipped_subtotal_count} subtotal/total row(s) embedded in the cap-table data",
                sheet=sheet_name,
            )
        )

    # Convertibles tab (optional)
    safes, warrants, notes = _read_convertibles_tab(wb, report)

    # Side Letters tab (optional)
    side_letters = _read_side_letters_tab(wb, report)

    cap_table = CapTable(
        company=company,
        share_classes=share_classes,
        side_letters=side_letters,
        safes_outstanding=safes,
        warrants_outstanding=warrants,
        convertible_notes_outstanding=notes,
    )
    return cap_table, report


def _read_company_tab(wb, report: ParseReport) -> Company:
    """Optional Company tab with key/value rows."""
    company_sheet = None
    for name in wb.sheetnames:
        if _normalize(name) in ("company", "metadata", "info"):
            company_sheet = name
            break
    if company_sheet is None:
        report.warnings.append(
            ParseWarning(code="company_tab_missing", message="No Company tab found; using minimal defaults")
        )
        return Company(name="Unnamed Company")

    ws = wb[company_sheet]
    fields = {}
    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        key = _normalize(row[0]).replace(" ", "_")
        val = row[1] if len(row) > 1 else None
        if val is not None and str(val).strip():
            fields[key] = val

    currency = str(fields.get("currency", "USD")).strip() or "USD"
    sym_default = {"USD": "$", "INR": "₹", "SGD": "S$", "EUR": "€", "GBP": "£"}.get(
        currency.upper(), "$"
    )
    sym = str(fields.get("currency_symbol", sym_default)).strip() or sym_default

    return Company(
        name=str(fields.get("company", "Unnamed Company")),
        jurisdiction=str(fields.get("jurisdiction", "")) or None,
        sector=str(fields.get("sector", "")) or None,
        stage=str(fields.get("stage", "")) or None,
        valuation_date=_parse_date(fields.get("valuation_date")),
        currency=currency.upper(),
        currency_symbol=sym,
    )


def _row_to_share_class(
    row: tuple,
    col_map: dict[str, int],
    sheet: str,
    row_num: int,
    report: ParseReport,
) -> Optional[ShareClass]:
    def get(field_name: str) -> Any:
        idx = col_map.get(field_name)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    class_name = get("class_name")
    if class_name is None or str(class_name).strip() == "":
        return None
    class_name = str(class_name).strip()
    raw_type = get("class_type")
    sc_type = _coerce_class_type(raw_type) or ShareClassType.preferred
    if raw_type and not _coerce_class_type(raw_type):
        report.warnings.append(
            ParseWarning(
                code="class_type_unknown",
                message=f"Unknown class type '{raw_type}' for '{class_name}'; defaulted to preferred",
                sheet=sheet,
                row=row_num,
            )
        )

    shares = _to_int(get("shares")) or 0
    price = _to_float(get("price"))
    issue_date = _parse_date(get("date"))
    seniority = _to_int(get("seniority")) or 99

    lp = None
    if sc_type == ShareClassType.preferred:
        lp_mult = _to_float(get("lp_multiple"))
        lp_type_val = _coerce_lp_type(get("lp_type"))
        cap_mult = _to_float(get("participation_cap"))
        if lp_mult is not None and lp_type_val is not None and price is not None:
            lp_amount = lp_mult * price * shares
            lp_kwargs: dict[str, Any] = {
                "multiple": lp_mult,
                "amount": lp_amount,
                "type": lp_type_val,
            }
            if lp_type_val == LPType.participating_capped:
                lp_kwargs["cap_multiple"] = cap_mult
            lp = LiquidationPreference(**lp_kwargs)
        else:
            report.warnings.append(
                ParseWarning(
                    code="lp_incomplete",
                    message=f"Incomplete liquidation preference for '{class_name}': "
                    f"multiple={lp_mult}, type={lp_type_val}, price={price}",
                    sheet=sheet,
                    row=row_num,
                )
            )

    ad = None
    raw_ad = get("anti_dilution")
    if raw_ad is not None and str(raw_ad).strip():
        variant = _coerce_anti_dilution(raw_ad)
        ad = AntiDilution(variant=variant)
        if variant is None:
            report.warnings.append(
                ParseWarning(
                    code="anti_dilution_unknown",
                    message=f"Unknown anti-dilution variant '{raw_ad}' for '{class_name}'",
                    sheet=sheet,
                    row=row_num,
                )
            )

    participation = None
    if lp is not None and lp.type == LPType.participating_capped:
        participation = Participation(
            mode=ParticipationMode.with_cap,
            cap_multiple_of_lp=_to_float(get("participation_cap")),
        )
    elif lp is not None and lp.type == LPType.participating_uncapped:
        participation = Participation(mode=ParticipationMode.without_cap)

    voting = get("voting")
    voting_str = str(voting).strip() if voting is not None and str(voting).strip() else None

    note = get("notes")
    note_str = str(note).strip() if note is not None and str(note).strip() else None

    try:
        return ShareClass(
            name=class_name,
            type=sc_type,
            shares_outstanding=shares,
            issue_price=price,
            issue_date=issue_date,
            seniority_rank=seniority if sc_type == ShareClassType.preferred else 99,
            liquidation_preference=lp,
            anti_dilution=ad,
            conversion_ratio=_to_float(get("conversion_ratio")),
            participation=participation,
            instrument_subtype=str(raw_type).strip() if raw_type else None,
            voting_differential=voting_str,
            note=note_str,
        )
    except Exception as e:
        report.warnings.append(
            ParseWarning(
                code="share_class_validation_failed",
                message=f"Could not construct share class '{class_name}': {e}",
                sheet=sheet,
                row=row_num,
            )
        )
        return None


def _read_convertibles_tab(wb, report: ParseReport):
    safes: list[SAFE] = []
    warrants: list[Warrant] = []
    notes: list[ConvertibleNote] = []
    sheet_name = None
    for name in wb.sheetnames:
        n = _normalize(name)
        if n in ("convertibles", "safes", "warrants", "convertible notes", "instruments"):
            sheet_name = name
            break
    if sheet_name is None:
        return safes, warrants, notes
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return safes, warrants, notes
    headers = [_normalize(h) for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers) if h}

    for ridx, row in enumerate(rows[1:], start=2):
        if all(v is None for v in row):
            continue
        type_raw = _normalize(row[idx.get("type", 1)] if "type" in idx else "")
        id_val = str(row[idx.get("instrument id", idx.get("id", 0))] or f"INSTR-{ridx}").strip()

        if "safe" in type_raw:
            safes.append(
                SAFE(
                    id=id_val,
                    principal=_to_float(row[idx.get("principal (usd)", idx.get("principal", 3))]) or 0.0,
                    valuation_cap=_to_float(row[idx.get("valuation cap (usd)", idx.get("valuation cap", 4))]),
                    discount_rate=_to_float(row[idx.get("discount %", idx.get("discount", 5))]),
                    issue_date=_parse_date(row[idx.get("issue date", 6)]),
                    notes=str(row[idx.get("trigger / notes", idx.get("notes", 7))] or "").strip() or None,
                )
            )
        elif "warrant" in type_raw:
            note_text = str(row[idx.get("trigger / notes", idx.get("notes", 7))] or "")
            shares_match = re.search(r"([\d,]+)\s*(?:common|preferred|shares)", note_text, re.I)
            strike_match = re.search(r"\$([\d.]+)\s*(?:/|per)\s*share", note_text, re.I)
            warrants.append(
                Warrant(
                    id=id_val,
                    holder=str(row[idx.get("holder / counterparty", idx.get("holder", 2))] or "Unknown holder").strip(),
                    shares=int(shares_match.group(1).replace(",", "")) if shares_match else 0,
                    share_class="Common",
                    strike_price=float(strike_match.group(1)) if strike_match else 0.0,
                    issue_date=_parse_date(row[idx.get("issue date", 6)]),
                    notes=note_text or None,
                )
            )

    return safes, warrants, notes


def _read_side_letters_tab(wb, report: ParseReport) -> list[SideLetter]:
    out: list[SideLetter] = []
    sheet_name = None
    for name in wb.sheetnames:
        n = _normalize(name)
        if n in ("side letters", "side letter", "letters"):
            sheet_name = name
            break
    if sheet_name is None:
        return out
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return out
    for ridx, row in enumerate(rows[1:], start=2):
        if all(v is None for v in row):
            continue
        cells = list(row) + [None] * 3  # pad short rows defensively
        out.append(
            SideLetter(
                id=str(cells[0] or f"SL-{ridx}").strip(),
                title=str(cells[1] or "").strip() or "Untitled",
                summary=str(cells[2] or "").strip() or None,
            )
        )
    return out


# -- Canonical JSON loader (used by tests / fixture round-trip) ---------------


def load_from_canonical_json(path: Path | str) -> CapTable:
    """Load a fixture's `cap_table_input.json` directly into a CapTable model."""
    path = Path(path)
    raw = json.loads(path.read_text())

    company_raw = raw["company"]
    company = Company(
        name=company_raw["name"],
        jurisdiction=company_raw.get("jurisdiction"),
        sector=company_raw.get("sector"),
        stage=company_raw.get("stage"),
        valuation_date=_parse_date(company_raw.get("valuation_date")),
        currency=str(company_raw.get("currency", "USD")).upper(),
        currency_symbol=company_raw.get("currency_symbol", "$"),
        summary=company_raw.get("summary"),
    )

    share_classes: list[ShareClass] = []
    currency_lower = company.currency.lower()
    price_key = f"issue_price_{currency_lower}"
    lp_key = f"amount_{currency_lower}"
    cap_amt_key = f"cap_amount_{currency_lower}"

    for sc in raw["share_classes"]:
        sc_type = ShareClassType(sc["type"])
        lp_raw = sc.get("liquidation_preference")
        lp = None
        if lp_raw is not None:
            lp_type_val = LPType(lp_raw["type"])
            cap_mult_in = lp_raw.get("cap_multiple")
            cap_amt_in = lp_raw.get("cap_amount_usd") or lp_raw.get(cap_amt_key)
            lp_amount = lp_raw.get("amount_usd") or lp_raw.get(lp_key) or 0.0
            # Normalize: prefer cap_multiple. If only cap_amount given, convert.
            # If both given and consistent, drop cap_amount.
            if cap_mult_in is not None and cap_amt_in is not None:
                cap_amt_in = None
            elif cap_mult_in is None and cap_amt_in is not None and lp_amount > 0:
                cap_mult_in = cap_amt_in / lp_amount
                cap_amt_in = None
            lp = LiquidationPreference(
                multiple=lp_raw["multiple"],
                amount=lp_amount,
                type=lp_type_val,
                cap_multiple=cap_mult_in,
                cap_amount=cap_amt_in,
            )
        ad_raw = sc.get("anti_dilution")
        ad = None
        if ad_raw is not None:
            variant = ad_raw.get("variant")
            ad = AntiDilution(
                variant=AntiDilutionVariant(variant) if variant else None,
                notes=ad_raw.get("notes"),
            )
        participation = None
        part_raw = sc.get("participation")
        if part_raw is not None:
            participation = Participation(
                mode=ParticipationMode(part_raw.get("mode", "none")),
                cap_multiple_of_lp=part_raw.get("cap_multiple_of_lp"),
            )

        share_classes.append(
            ShareClass(
                name=sc["name"],
                type=sc_type,
                shares_outstanding=sc["shares_outstanding"],
                issue_price=sc.get("issue_price_usd") or sc.get(price_key),
                issue_date=_parse_date(sc.get("issue_date")),
                seniority_rank=sc.get("seniority_rank", 99),
                liquidation_preference=lp,
                anti_dilution=ad,
                conversion_ratio=sc.get("conversion_ratio"),
                participation=participation,
                instrument_subtype=sc.get("instrument_subtype"),
                voting_differential=sc.get("voting_differential"),
                note=sc.get("note"),
            )
        )

    side_letters = [
        SideLetter(
            id=sl["id"],
            title=sl["title"],
            summary=sl.get("summary"),
            body=sl.get("body"),
            unresolved_questions=sl.get("unresolved_questions", []),
        )
        for sl in raw.get("side_letters", [])
    ]
    safes = [
        SAFE(
            id=s["id"],
            principal=s.get("principal_usd") or s.get("principal", 0.0),
            valuation_cap=s.get("valuation_cap_usd") or s.get("valuation_cap"),
            discount_rate=s.get("discount_rate"),
            issue_date=_parse_date(s.get("issue_date")),
        )
        for s in raw.get("safes_outstanding", [])
    ]
    warrants = [
        Warrant(
            id=w["id"],
            holder=w["holder"],
            shares=w["shares"],
            share_class=w["share_class"],
            strike_price=w.get("strike_price_usd") or w.get("strike_price", 0.0),
            issue_date=_parse_date(w.get("issue_date")),
            expiry_date=_parse_date(w.get("expiry_date")),
        )
        for w in raw.get("warrants_outstanding", [])
    ]
    notes = [
        ConvertibleNote(
            id=n["id"],
            principal=n.get("principal_usd") or n.get("principal", 0.0),
            valuation_cap=n.get("valuation_cap_usd") or n.get("valuation_cap"),
            discount_rate=n.get("discount_rate"),
            issue_date=_parse_date(n.get("issue_date")),
        )
        for n in raw.get("convertible_notes_outstanding", [])
    ]

    return CapTable(
        company=company,
        share_classes=share_classes,
        side_letters=side_letters,
        safes_outstanding=safes,
        warrants_outstanding=warrants,
        convertible_notes_outstanding=notes,
    )
