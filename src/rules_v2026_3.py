"""Rule-pack v2026.3.0 — NVCA + Delaware + AICPA coverage (W2.5).

Adds 7 more rules: NVCA charter idioms, Delaware §251 conversion
mechanics, AICPA Cheap Stock Guide cross-references, US protective-
provision keyword scan, drag-along scope, ROFR notice-period sanity.
Brings total registered rules from 23 → 30.
"""

from __future__ import annotations

import re
from datetime import date as _date

from .checklist import Finding
from .models import CapTable, LPType, ShareClassType
from .rule_pack import rule


# ---- NVCA / Delaware structural -------------------------------------------


@rule(
    id="G-DE-001",
    severity="info",
    category="delaware_jurisdiction_check",
    summary="Delaware-incorporated company: confirm DGCL §251 conversion mechanics applied.",
    citation="Delaware General Corporation Law (DGCL) §251; NVCA Model Charter §4.A.",
    jurisdictions=("US-DE", "DELAWARE", "US"),
    introduced_in_pack="v2026.3.0",
)
def _rule_delaware_overlay(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if not any(tag in juris for tag in ("US-DE", "DELAWARE", "DE,")):
        return []
    return [Finding(
        code="DE-DGCL-OVERLAY",
        severity="info",
        category="delaware_jurisdiction_check",
        summary=(
            "Delaware jurisdiction detected. Confirm DGCL §251 mechanics, "
            "appraisal-rights exclusions, and NVCA Model Charter §4.A "
            "conversion provisions are addressed."
        ),
        fields_referenced=("company.jurisdiction",),
    )]


@rule(
    id="G-NVCA-001",
    severity="info",
    category="nvca_optional_clause_detected",
    summary="Side letter language matches an NVCA Model optional clause; verify scope.",
    citation="NVCA Model Legal Documents (latest); optional-clause appendix.",
    introduced_in_pack="v2026.3.0",
)
def _rule_nvca_optional_clause(cap_table: CapTable) -> list[Finding]:
    out = []
    triggers = (
        "co-sale", "co sale",
        "drag-along", "drag along",
        "registration rights",
        "redemption right",
        "pay-to-play", "pay to play",
        "protective provision",
    )
    for sl in cap_table.side_letters:
        body = ((sl.body or "") + " " + (sl.summary or "")).lower()
        hits = [t for t in triggers if t in body]
        if hits:
            out.append(Finding(
                code=f"NVCA-CLAUSE-{sl.id}",
                severity="info",
                category="nvca_optional_clause_detected",
                summary=(
                    f"Side letter {sl.id} ('{sl.title}') mentions NVCA-style "
                    f"clause(s): {sorted(set(hits))}. Verify clause scope is "
                    f"reflected in the cap-table model."
                ),
                fields_referenced=(f"side_letters[{sl.id}].body",),
            ))
    return out


@rule(
    id="G-AICPA-001",
    severity="info",
    category="aicpa_lp_overhang_significant",
    summary="LP overhang > 50% of fully-diluted value warrants AICPA Ch.4 disclosure.",
    citation="AICPA Cheap Stock Guide §4.18 (LP overhang and OPM allocation).",
    introduced_in_pack="v2026.3.0",
)
def _rule_aicpa_lp_overhang(cap_table: CapTable) -> list[Finding]:
    lp_total = sum(
        sc.liquidation_preference.amount for sc in cap_table.share_classes
        if sc.liquidation_preference is not None
    )
    # Use latest priced round PPS × total fully diluted as a rough enterprise
    # proxy. (The real check requires the OPM-implied value; this is the
    # checklist-time approximation.)
    priced = [
        sc for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred
        and sc.issue_price is not None and sc.issue_price > 0
    ]
    if not priced:
        return []
    latest = max(priced, key=lambda sc: sc.issue_date or _date.min)
    pps = latest.issue_price
    total_shares = cap_table.total_fully_diluted_for_waterfall
    enterprise_proxy = pps * total_shares
    if enterprise_proxy <= 0:
        return []
    ratio = lp_total / enterprise_proxy
    if ratio > 0.5:
        return [Finding(
            code="AICPA-LP-OVERHANG",
            severity="info",
            category="aicpa_lp_overhang_significant",
            summary=(
                # M8 fix: surface that this is an upper-bound PROXY, not
                # an OPM-implied EV. Analysts copy-paste these summaries
                # so it must read accurately.
                f"LP overhang ({lp_total:,.0f}) is {ratio:.0%} of the "
                f"PPS-implied upper-bound EV proxy "
                f"(latest preferred PPS × fully-diluted shares). "
                f"This is a checklist heuristic, not the OPM-allocated EV; "
                f"per AICPA §4.18, the memo should compute the OPM-implied "
                f"EV and re-evaluate the ratio there."
            ),
            fields_referenced=("share_classes[*].liquidation_preference",),
        )]
    return []


@rule(
    id="G-NVCA-002",
    severity="warning",
    category="nvca_protective_provisions_unenumerated",
    summary="Preferred class exists but no protective-provisions side letter present.",
    citation="NVCA Model Charter §6 (Protective Provisions).",
    introduced_in_pack="v2026.3.0",
)
def _rule_protective_provisions_missing(cap_table: CapTable) -> list[Finding]:
    has_preferred = any(
        sc.type == ShareClassType.preferred for sc in cap_table.share_classes
    )
    if not has_preferred:
        return []
    found_pp = False
    for sl in cap_table.side_letters:
        text = ((sl.body or "") + " " + (sl.summary or "") + " " + sl.title).lower()
        if "protective" in text and "provision" in text:
            found_pp = True
            break
    if not found_pp:
        return [Finding(
            code="NVCA-PP-MISSING",
            severity="warning",
            category="nvca_protective_provisions_unenumerated",
            summary=(
                "Preferred class exists but no protective-provisions side "
                "letter found. NVCA Model Charter §6 protective-provisions "
                "list is typically separately enumerated in a side letter "
                "or charter exhibit; confirm whether absence is intentional."
            ),
            fields_referenced=("share_classes[*].type", "side_letters"),
        )]
    return []


@rule(
    id="G-DRAG-001",
    severity="info",
    category="drag_along_keyword_in_side_letter",
    summary="Side letter mentions drag-along; verify threshold is captured.",
    citation="NVCA Model Voting Agreement §3; AICPA Cheap Stock Guide §2.22.",
    introduced_in_pack="v2026.3.0",
)
def _rule_drag_along_keyword(cap_table: CapTable) -> list[Finding]:
    out = []
    for sl in cap_table.side_letters:
        text = ((sl.body or "") + " " + (sl.summary or "")).lower()
        if "drag-along" in text or "drag along" in text:
            # Look for a percentage immediately near the keyword.
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
            threshold = f" (matched {m.group(0)})" if m else " (no explicit % threshold found)"
            out.append(Finding(
                code=f"DRAG-{sl.id}",
                severity="info",
                category="drag_along_keyword_in_side_letter",
                summary=(
                    f"Side letter {sl.id} ('{sl.title}') references drag-along"
                    f"{threshold}. Verify the threshold and the class of "
                    f"shareholders subject to drag is captured."
                ),
                fields_referenced=(f"side_letters[{sl.id}]",),
            ))
    return out


@rule(
    id="G-ROFR-001",
    severity="info",
    category="rofr_notice_period_unspecified",
    summary="Side letter mentions ROFR/ROFO but no notice period detected.",
    citation="NVCA Model ROFR/Co-Sale Agreement §2; standard 30/60/90-day windows.",
    introduced_in_pack="v2026.3.0",
)
def _rule_rofr_notice_period(cap_table: CapTable) -> list[Finding]:
    out = []
    for sl in cap_table.side_letters:
        text = ((sl.body or "") + " " + (sl.summary or "")).lower()
        if "rofr" not in text and "rofo" not in text and "right of first" not in text:
            continue
        # Detect any "N day(s)" or "N business days" mention.
        m = re.search(r"(\d+)\s*(?:business\s*)?days?", text)
        if not m:
            out.append(Finding(
                code=f"ROFR-NOTICE-{sl.id}",
                severity="info",
                category="rofr_notice_period_unspecified",
                summary=(
                    f"Side letter {sl.id} ('{sl.title}') references ROFR/ROFO "
                    f"but no notice period found. Confirm the window."
                ),
                fields_referenced=(f"side_letters[{sl.id}]",),
            ))
    return out


@rule(
    id="G-AICPA-002",
    severity="info",
    category="aicpa_dlom_band_required",
    summary="Common-stock-only cap table: AICPA expects explicit DLOM band justification.",
    citation="AICPA Cheap Stock Guide §5 (DLOM); Finnerty / Chaffe references.",
    introduced_in_pack="v2026.3.0",
)
def _rule_aicpa_dlom_band(cap_table: CapTable) -> list[Finding]:
    has_common = any(sc.type == ShareClassType.common for sc in cap_table.share_classes)
    if not has_common:
        return []
    # Always fires when common exists — DLOM is always an analyst input
    # the memo must justify. The rule is a reminder, not a defect.
    return [Finding(
        code="AICPA-DLOM-REMINDER",
        severity="info",
        category="aicpa_dlom_band_required",
        summary=(
            "Common stock present. Per AICPA Cheap Stock Guide §5, the memo "
            "must justify the DLOM band (e.g., 15-35%) with reference to "
            "Finnerty, Chaffe, or restricted-stock studies."
        ),
        fields_referenced=("share_classes[type=common]",),
    )]
