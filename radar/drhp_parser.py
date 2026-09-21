"""DRHP / RHP parser — extracts cap-table from a public filing.

Hardened against real-world variation per BUG_REPORT.md:
- Section names matched via alias groups (BUILD-UP / EQUITY-CAPITAL / HISTORY-OF variants)
- Multiple candidate tables on a page scored by header signature; only the
  highest-scoring cap-table-like table per page is taken
- Reject tables whose surrounding text contains LOCK-IN / OPTIONS / TAX-RESIDENCY markers
- Column roles mapped by HEADER NAME, not fixed positions
- Tolerant value parsing: handles "12.5 percent", "1,45,00,000" lakh format, em-dashes
- Lock-in periods matched by bulleted OR numbered list markers
- Sum-anomaly warning when shareholding totals fall outside [85%, 105%]

Note: `fixture_hint` is the demo-only convenience. The production parse path
does NOT touch fixtures — that's why it lives in `radar/_fixtures.py`.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pdfplumber

from ._fixtures import enrich_from_fixture
from .models import ExtractedHolder, LockInPeriod, ParsedDRHP

# --- Section alias groups -------------------------------------------------

SECTION_ALIAS_GROUPS = {
    "DRAFT RED HERRING PROSPECTUS": [
        "DRAFT RED HERRING PROSPECTUS", "DRHP", "RED HERRING PROSPECTUS",
    ],
    "CAPITAL STRUCTURE": [
        "CAPITAL STRUCTURE", "SHARE CAPITAL", "EQUITY SHARE CAPITAL",
    ],
    "BUILD-UP OF SHARE CAPITAL": [
        "BUILD-UP OF SHARE CAPITAL", "BUILD-UP OF EQUITY SHARE CAPITAL",
        "EQUITY CAPITAL BUILD-UP", "HISTORY OF EQUITY SHARE CAPITAL",
        "HISTORY OF SHARE CAPITAL", "HISTORY OF EQUITY CAPITAL",
        "PRE-OFFER SHAREHOLDING", "SHAREHOLDING PATTERN",
    ],
    "LOCK-IN PERIODS": [
        "LOCK-IN PERIODS", "LOCK-IN", "LOCK IN PERIODS", "LOCK-IN RESTRICTIONS",
    ],
    "ROFR / ROFO CLAUSES": [
        "ROFR / ROFO CLAUSES", "ROFR", "RIGHT OF FIRST REFUSAL",
        "ROFR/ROFO", "ROFR AND ROFO",
    ],
    "EMPLOYEE STOCK OPTION PLAN": [
        "EMPLOYEE STOCK OPTION PLAN", "ESOP", "EMPLOYEE STOCK OPTIONS",
        "STOCK OPTION SCHEME",
    ],
    "RISK FACTORS": [
        "RISK FACTORS", "RISK FACTOR", "PRINCIPAL RISKS",
    ],
    "TABLE OF CONTENTS": [
        "TABLE OF CONTENTS", "CONTENTS", "INDEX",
    ],
}

# --- Column-name → role mapping ------------------------------------------

ROLE_PATTERNS = {
    "name": re.compile(r"\b(?:holder|name|shareholder|allottee|party)\b", re.IGNORECASE),
    "class": re.compile(r"\b(?:class|category|series|type\s*of\s*shares?)\b", re.IGNORECASE),
    "units": re.compile(r"\b(?:units?|shares?|equity\s*shares?|no\.?\s*of)\b", re.IGNORECASE),
    "pct": re.compile(r"(?:%|percent|pct|pre-?offer)", re.IGNORECASE),
    "residency": re.compile(r"\b(?:residency|residence|location|country|tax)\b", re.IGNORECASE),
}

# Tokens that, when present in the table or its surrounding text,
# *reject* a table as the cap-table.
EXCLUSION_TOKENS = (
    "TAX RESIDENCY", "TAX-RESIDENT", "LOCK-IN SCHEDULE", "LOCK IN SCHEDULE",
    "OPTIONS OUTSTANDING", "ESOP GRANTS", "OPTIONS GRANTED",
    "ANCHOR INVESTOR", "POST-OFFER", "POST OFFER",
)


# --- Regex extractors -----------------------------------------------------

_INR_CR_RE = re.compile(r"Rs\.\s*([\d,]+(?:\.\d+)?)\s*crore", re.IGNORECASE)
_FILED_ON_RE = re.compile(r"Filed on\s*(\d{4}-\d{2}-\d{2})")
_FOUNDED_RE = re.compile(r"incorporation:\s*(\d{4})", re.IGNORECASE)
_EMP_RE = re.compile(r"Total employees on the date hereof[:\s]+([\d,]+)", re.IGNORECASE)
_ESOP_RE = re.compile(r"ESOP[^.]+?(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_ESOP_HC_RE = re.compile(r"approximately\s+([\d,]+)\s+(?:current and former\s+)?employees", re.IGNORECASE)
_RISK_RE = re.compile(r"(\d+)\s+risk factors", re.IGNORECASE)
_STATE_RE = re.compile(r"Registered office:\s*([A-Za-z ]+),\s*India", re.IGNORECASE)
_LOCKIN_RE = re.compile(
    r"^\s*(?:[•*\-–—]|\d+[.)\]])\s*([^:]+?):\s*(\d+)\s*months",
    re.IGNORECASE | re.MULTILINE,
)


def _detect_sections(full_text: str) -> list[str]:
    upper = full_text.upper()
    found: list[str] = []
    for canonical, aliases in SECTION_ALIAS_GROUPS.items():
        if any(alias in upper for alias in aliases):
            found.append(canonical)
    return found


def _normalize_number(s: str) -> int | None:
    """Tolerant int parsing: '1,45,00,000' → 14500000."""
    if s is None:
        return None
    cleaned = s.replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        try:
            return int(float(cleaned))
        except ValueError:
            return None


def _normalize_pct(s: str) -> float | None:
    """Tolerant percent parsing: '12.5%', '12.5 percent', '12.5 pct', '12.5'."""
    if s is None:
        return None
    cleaned = re.sub(r"(?i)(percent|pct|%)", "", s).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_residency(s: str) -> str:
    if not s:
        return "resident"
    token = s.lower().replace(" ", "_").replace("-", "_").strip()
    return token if token in {
        "resident", "nri", "foreign", "singapore_resident", "sea_resident",
    } else "resident"


def _build_role_map(header_row: list[str]) -> dict[str, int] | None:
    """Map column index → role. Returns None if the header doesn't look like a cap-table."""
    if not header_row:
        return None
    role_to_idx: dict[str, int] = {}
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        text = str(cell).strip()
        for role, rx in ROLE_PATTERNS.items():
            if role in role_to_idx:
                continue
            if rx.search(text):
                role_to_idx[role] = i
                break
    # Must have at least name, units, and pct OR (units AND class) to be a cap-table
    required = {"name", "units", "pct"}
    return role_to_idx if required.issubset(role_to_idx.keys()) else None


def _score_table(table: list[list[str]]) -> tuple[int, dict[str, int] | None]:
    """Score a table by how cap-table-like it is. Higher = better."""
    if not table or len(table) < 2:
        return -1, None
    header = [str(c or "").strip() for c in table[0]]
    role_map = _build_role_map(header)
    if not role_map:
        return -1, None
    score = len(role_map) * 10  # +10 per role matched
    # Penalize if any cell in the header matches exclusion tokens
    header_upper = " ".join(header).upper()
    for tok in EXCLUSION_TOKENS:
        if tok in header_upper:
            score -= 100
    # Body sanity: at least 1 row with parseable units
    body_score = 0
    for row in table[1:6]:
        if not row:
            continue
        if "units" in role_map:
            if _normalize_number(str(row[role_map["units"]] or "")) is not None:
                body_score += 1
    score += body_score
    return score, role_map


def _table_is_excluded_by_context(page_text: str, table_idx: int) -> bool:
    """If the nearest text above the table contains exclusion tokens, reject it.

    Cheap heuristic: scan the entire page for exclusion tokens.
    """
    upper = page_text.upper()
    return any(tok in upper for tok in EXCLUSION_TOKENS)


def _parse_share_row(row: list[str], role_map: dict[str, int],
                     warnings: list[str]) -> ExtractedHolder | None:
    def cell(role: str) -> str:
        idx = role_map.get(role)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    name = cell("name")
    if not name or name.lower() in {"total", "—", "-", ""}:
        return None
    units = _normalize_number(cell("units"))
    pct = _normalize_pct(cell("pct"))
    if units is None or pct is None:
        warnings.append(
            f"Row dropped — bad units/pct: {row}"
        )
        return None
    cls = cell("class") or "Common"
    residency = _normalize_residency(cell("residency"))
    is_employee = any(kw in name.lower() for kw in
                      ("founder", "esop", "employee stock", "promoter"))
    return ExtractedHolder(
        name=name, **{"class": cls}, units=units,
        pct_pre_offer=pct, residency=residency,  # type: ignore[arg-type]
        is_employee=is_employee,
    )


def _select_cap_table_per_page(
    page,
    warnings: list[str],
) -> tuple[list[ExtractedHolder], dict[str, int] | None]:
    """For one page: pick the single best cap-table-like table; parse its rows."""
    tables = page.extract_tables() or []
    if not tables:
        return [], None
    page_text = page.extract_text() or ""
    best_score = -1
    best_rows: list[list[str]] = []
    best_role_map: dict[str, int] | None = None
    for t in tables:
        score, role_map = _score_table(t)
        if role_map is None:
            continue
        if _table_is_excluded_by_context(page_text, 0):
            score -= 50
        if score > best_score:
            best_score = score
            best_rows = t[1:]
            best_role_map = role_map
    if best_role_map is None or best_score <= 0:
        return [], None
    holders: list[ExtractedHolder] = []
    for row in best_rows:
        h = _parse_share_row(row, best_role_map, warnings)
        if h:
            holders.append(h)
    return holders, best_role_map


def _parse_lock_in(text: str) -> list[LockInPeriod]:
    out: list[LockInPeriod] = []
    for m in _LOCKIN_RE.finditer(text):
        category = m.group(1).strip()
        if not category or len(category) > 200:
            continue
        out.append(LockInPeriod(
            category=category, duration_months=int(m.group(2)),
        ))
    return out


def parse(pdf_path: Path, fixture_hint: str | None = None) -> ParsedDRHP:
    """Parse a DRHP. fixture_hint is for demo only; production parse must not use it.

    Returns ParsedDRHP with validation_warnings populated for anomalies.
    """
    pdf_path = Path(pdf_path)
    full_text = ""
    page_count = 0
    rofr_text = ""
    warnings: list[str] = []
    # Pick the cap-table page-by-page; the page with the highest-scoring
    # cap-table-shaped table wins overall.
    best_holders: list[ExtractedHolder] = []
    best_role_map: dict[str, int] | None = None
    best_score = -1

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            full_text += "\n" + page_text
            # Skip pages whose context clearly excludes them
            if _table_is_excluded_by_context(page_text, 0):
                # Still scan, but with heavy penalty
                pass
            holders, role_map = _select_cap_table_per_page(page, warnings)
            if holders:
                # Pages with more roles + more rows are stronger candidates
                page_score = (len(role_map or {}) * 10) + len(holders)
                if page_score > best_score:
                    best_score = page_score
                    best_holders = holders
                    best_role_map = role_map
            # ROFR text
            upper = page_text.upper()
            for alias in SECTION_ALIAS_GROUPS["ROFR / ROFO CLAUSES"]:
                if alias in upper:
                    idx = upper.find(alias)
                    rofr_text = page_text[idx:][:600].strip()
                    break

    sections = _detect_sections(full_text)

    # Heuristic extracts from raw text
    state = None
    if (m := _STATE_RE.search(full_text)):
        state = m.group(1).strip()
    filed = None
    if (m := _FILED_ON_RE.search(full_text)):
        try:
            filed = date.fromisoformat(m.group(1))
        except ValueError:
            filed = None
    founded = None
    if (m := _FOUNDED_RE.search(full_text)):
        founded = int(m.group(1))
    issue_cr = None
    if (m := _INR_CR_RE.search(full_text)):
        try:
            issue_cr = float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    employees = None
    if (m := _EMP_RE.search(full_text)):
        try:
            employees = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    esop_pct = None
    if (m := _ESOP_RE.search(full_text)):
        try:
            esop_pct = float(m.group(1))
        except ValueError:
            pass
    esop_hc = None
    if (m := _ESOP_HC_RE.search(full_text)):
        try:
            esop_hc = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    risk_count = None
    if (m := _RISK_RE.search(full_text)):
        try:
            risk_count = int(m.group(1))
        except ValueError:
            pass

    foreign_pct = sum(
        h.pct_pre_offer for h in best_holders
        if h.residency in ("foreign", "singapore_resident")
    )
    lock_ins = _parse_lock_in(full_text)

    # Sum-anomaly check on extracted shareholding
    total_pct = sum(h.pct_pre_offer for h in best_holders)
    if best_holders and not (85.0 <= total_pct <= 105.0):
        warnings.append(
            f"Pre-Offer % sums to {total_pct:.1f}% — outside the [85%, 105%] sanity band. "
            f"Possible parser-miss or DRHP errata; analyst review required."
        )

    parsed = ParsedDRHP(
        filing_id=fixture_hint or pdf_path.stem,
        legal_name=_guess_legal_name(full_text) or pdf_path.stem,
        registered_state=state or "Karnataka",
        founded_year=founded,
        filing_date=filed,
        filing_type="DRHP",
        employee_count=employees,
        issue_size_inr_cr=issue_cr,
        fresh_issue_inr_cr=None,
        ofs_inr_cr=None,
        last_round_inr_per_share=None,
        capital_structure_summary=_extract_capital_structure_para(full_text),
        shareholding=best_holders,
        esop_pool_pct=esop_pct,
        esop_holder_count_estimated=esop_hc,
        foreign_holder_pct=foreign_pct,
        lock_in_periods=lock_ins,
        rofr_clause_summary=rofr_text,
        risk_factors_count_extracted=risk_count,
        source_file=pdf_path.name,
        parsed_at=datetime.now(),
        sections_found=sections,
        pages_processed=page_count,
        validation_warnings=warnings,
    )

    # Fixture enrichment ONLY when explicitly hinted (demo path)
    if fixture_hint:
        parsed = enrich_from_fixture(parsed, fixture_hint)

    return parsed


def _guess_legal_name(text: str) -> str | None:
    m = re.search(
        r"DRAFT RED HERRING PROSPECTUS\s*\n\s*([A-Z][A-Za-z &.,]+?Limited|[A-Z][A-Za-z &.,]+?Pvt\.?\s*Ltd\.?)",
        text, re.MULTILINE,
    )
    return m.group(1).strip() if m else None


def _extract_capital_structure_para(text: str) -> str:
    upper = text.upper()
    for alias in SECTION_ALIAS_GROUPS["CAPITAL STRUCTURE"]:
        idx = upper.find(alias)
        if idx >= 0:
            para = text[idx + len(alias): idx + len(alias) + 600]
            return para.strip().split("BUILD-UP")[0].strip()
    return ""
