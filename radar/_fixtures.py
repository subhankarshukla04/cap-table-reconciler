"""Demo-only fixture enrichment. NOT touched by the production parse path.

The fixture_hint parameter to drhp_parser.parse() is the only door into this
module. Production parse calls do not pass fixture_hint.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import ExtractedHolder, LockInPeriod, ParsedDRHP

ROOT = Path(__file__).resolve().parent.parent
FACTS_PATH = ROOT / "data" / "drhp" / "_facts.json"


def enrich_from_fixture(parsed: ParsedDRHP, fixture_hint: str) -> ParsedDRHP:
    if not FACTS_PATH.exists():
        return parsed
    all_facts = json.loads(FACTS_PATH.read_text())
    facts = all_facts.get(fixture_hint)
    if not facts:
        return parsed

    update = parsed.model_dump()
    # Only fill in fields that the parser couldn't find
    if not parsed.legal_name or parsed.legal_name == parsed.source_file.replace(".pdf", ""):
        update["legal_name"] = facts.get("legal_name", parsed.legal_name)
    if not parsed.registered_state or parsed.registered_state == "Karnataka":
        update["registered_state"] = facts.get("registered_state", parsed.registered_state)
    if parsed.founded_year is None:
        update["founded_year"] = facts.get("founded_year")
    if parsed.filing_date is None and facts.get("filing_date"):
        update["filing_date"] = date.fromisoformat(facts["filing_date"])
    if "filing_type" in facts:
        update["filing_type"] = facts["filing_type"]
    if parsed.employee_count is None:
        update["employee_count"] = facts.get("employee_count")
    if parsed.issue_size_inr_cr is None:
        update["issue_size_inr_cr"] = facts.get("issue_size_inr_cr")
    update["fresh_issue_inr_cr"] = facts.get("fresh_issue_inr_cr", parsed.fresh_issue_inr_cr)
    update["ofs_inr_cr"] = facts.get("ofs_inr_cr", parsed.ofs_inr_cr)
    update["last_round_inr_per_share"] = facts.get(
        "last_round_inr_per_share", parsed.last_round_inr_per_share
    )
    if not parsed.shareholding and facts.get("shareholding"):
        update["shareholding"] = [
            ExtractedHolder.model_validate({**h, "class": h.get("class", "Common")})
            for h in facts["shareholding"]
        ]
    if parsed.esop_pool_pct is None:
        update["esop_pool_pct"] = facts.get("esop_pool_pct")
    if parsed.esop_holder_count_estimated is None:
        update["esop_holder_count_estimated"] = facts.get("esop_holder_count_estimated")
    if not parsed.foreign_holder_pct:
        update["foreign_holder_pct"] = facts.get("foreign_holder_pct", 0.0)
    if not parsed.lock_in_periods and facts.get("lock_in_periods"):
        update["lock_in_periods"] = [LockInPeriod(**lp) for lp in facts["lock_in_periods"]]
    if not parsed.rofr_clause_summary:
        update["rofr_clause_summary"] = facts.get("rofr_clause_summary", "")
    if parsed.risk_factors_count_extracted is None:
        update["risk_factors_count_extracted"] = facts.get("risk_factors_count_extracted")

    return ParsedDRHP.model_validate(update)
