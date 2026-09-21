"""
Rule-based gap detector for the Cap Table Reconciler.

Inspects a parsed CapTable and surfaces findings the analyst should review
before computing fair-value or downstream OPM/Backsolve. This module makes
zero valuation judgments — it only points out structural and completeness
gaps, ranked by severity:

  - blocker: cap table is incomplete in a way that breaks defensibility
             (e.g., anti-dilution variant unspecified on a preferred class,
             SAFEs outstanding but conversion not reflected after a round)
  - warning: data anomaly that needs analyst confirmation but doesn't block
             the waterfall calculation (stale option pool, side letter with
             missing terms)
  - info:    unusual but valid structures that need explicit memo treatment
             (full ratchet, participating-with-cap, dual-class voting)

Each finding includes a stable code (G-prefix) so the UI can hyperlink to
remediation guidance and the audit memo can cite the rule applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import (
    AntiDilutionVariant,
    CapTable,
    LPType,
    ShareClass,
    ShareClassType,
)
from .rule_pack import rule


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "blocker" | "warning" | "info"
    category: str
    summary: str
    detail: Optional[str] = None
    fields_referenced: tuple[str, ...] = ()


# ---- Individual rules --------------------------------------------------------


@rule(
    id="G-AD-001",
    severity="blocker",
    category="anti_dilution_unspecified",
    summary="Anti-dilution variant blank on a preferred class.",
    citation="NVCA Model Charter §4.4; AICPA Cheap Stock Guide Ch. 2.",
)
def _rule_anti_dilution_unspecified(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred:
            continue
        if sc.anti_dilution is None or sc.anti_dilution.variant is None:
            out.append(
                Finding(
                    code=f"AD-MISSING-{sc.name}",
                    severity="blocker",
                    category="anti_dilution_unspecified",
                    summary=f"Anti-dilution variant for {sc.name} is blank.",
                    detail=(
                        "Anti-dilution variant materially affects share count under any future "
                        "down-round scenario. Confirm broad-based weighted-average, narrow-based "
                        "weighted-average, or full ratchet from charter."
                    ),
                    fields_referenced=(f"share_classes[{sc.name}].anti_dilution.variant",),
                )
            )
    return out


@rule(
    id="G-AD-002",
    severity="info",
    category="anti_dilution_full_ratchet_documented",
    summary="Full-ratchet anti-dilution requires explicit memo footnote.",
    citation="AICPA Cheap Stock Guide §2.18; Cooley GO term sheet primer.",
)
def _rule_full_ratchet_documented(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if (
            sc.type == ShareClassType.preferred
            and sc.anti_dilution is not None
            and sc.anti_dilution.variant == AntiDilutionVariant.full_ratchet
        ):
            out.append(
                Finding(
                    code=f"AD-RATCHET-{sc.name}",
                    severity="info",
                    category="anti_dilution_full_ratchet_documented",
                    summary=f"{sc.name} carries full-ratchet anti-dilution.",
                    detail=(
                        "Full ratchet does not affect waterfall at the present valuation date "
                        "unless a triggering event has occurred. Flag for audit memo footnote in "
                        "the methodology section."
                    ),
                    fields_referenced=(f"share_classes[{sc.name}].anti_dilution.variant",),
                )
            )
    return out


@rule(
    id="G-LP-001",
    severity="info",
    category="participating_with_cap_documented",
    summary="Participating-with-cap preferred requires explicit waterfall walkthrough.",
    citation="NVCA Model Charter §2.1.2(b); AICPA Cheap Stock Guide Ch. 4.",
)
def _rule_participating_with_cap_documented(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if (
            sc.type == ShareClassType.preferred
            and sc.liquidation_preference is not None
            and sc.liquidation_preference.type == LPType.participating_capped
        ):
            cap_x = sc.liquidation_preference.cap_multiple
            out.append(
                Finding(
                    code=f"LP-PART-CAP-{sc.name}",
                    severity="info",
                    category="participating_with_cap_documented",
                    summary=(
                        f"{sc.name} is participating-with-cap"
                        + (f" ({cap_x}x of LP)." if cap_x else ".")
                    ),
                    detail=(
                        "Participating-with-cap produces additional waterfall breakpoints "
                        "(cap-reach, junior-converts, pure-converts). Each breakpoint is a "
                        "separate strike for OPM Backsolve purposes. Walk through explicitly "
                        "in the audit memo."
                    ),
                    fields_referenced=(f"share_classes[{sc.name}].liquidation_preference.type",),
                )
            )
    return out


_STALE_POOL_THRESHOLD_DAYS = 270  # ~9 months — beyond a typical pool-refresh window


@rule(
    id="G-POOL-001",
    severity="warning",
    category="stale_option_pool",
    summary="Option pool last-grant date is older than the most recent round.",
    citation="AICPA Cheap Stock Guide §3.42 (option grant pricing relative to round events).",
)
def _rule_stale_option_pool(cap_table: CapTable) -> list[Finding]:
    granted_pools = [
        sc for sc in cap_table.share_classes if sc.type == ShareClassType.option_pool_granted
    ]
    preferred_dates = [
        sc.issue_date
        for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred and sc.issue_date is not None
    ]
    if not preferred_dates:
        return []
    most_recent_round: date = max(preferred_dates)

    out = []
    for pool in granted_pools:
        if pool.issue_date is None:
            continue
        gap_days = (most_recent_round - pool.issue_date).days
        if gap_days > _STALE_POOL_THRESHOLD_DAYS:
            out.append(
                Finding(
                    code=f"POOL-STALE-{pool.name}",
                    severity="warning",
                    category="stale_option_pool",
                    summary=(
                        f"Option pool last-grant date ({pool.issue_date.isoformat()}) is older "
                        f"than the most recent funding round ({most_recent_round.isoformat()})."
                    ),
                    detail=(
                        "Option grants made before a new round are typically issued at the prior "
                        "409A FMV. Confirm whether any post-round grants were issued at refreshed "
                        "FMV and whether the pool was expanded at the new round closing."
                    ),
                    fields_referenced=(
                        f"share_classes[{pool.name}].issue_date",
                        "preferred_class_issue_dates",
                    ),
                )
            )
    return out


@rule(
    id="G-SAFE-001",
    severity="blocker",
    category="unrecorded_safe_conversion",
    summary="SAFE listed as outstanding but a qualifying priced round has closed.",
    citation="Y Combinator SAFE primer; AICPA Cheap Stock Guide §3.31.",
)
def _rule_unrecorded_safe_conversion(cap_table: CapTable) -> list[Finding]:
    """SAFEs outstanding whose trigger has been satisfied by a subsequent priced round."""
    out = []
    preferred_dates_amounts = sorted(
        [
            (sc.issue_date, sc.shares_outstanding * (sc.issue_price or 0.0), sc.name)
            for sc in cap_table.share_classes
            if sc.type == ShareClassType.preferred
            and sc.issue_date is not None
            and sc.issue_price is not None
        ]
    )
    if not preferred_dates_amounts:
        return out

    for safe in cap_table.safes_outstanding:
        if safe.issue_date is None:
            out.append(
                Finding(
                    code=f"SAFE-NODATE-{safe.id}",
                    severity="warning",
                    category="safe_missing_data",
                    summary=f"SAFE {safe.id} has no issue date; cannot verify conversion status.",
                    detail="Add issue date to assess whether the SAFE should have converted at a subsequent priced round.",
                    fields_referenced=(f"safes_outstanding[{safe.id}].issue_date",),
                )
            )
            continue
        # Find priced rounds AFTER this SAFE
        subsequent = [(d, raise_amt, name) for d, raise_amt, name in preferred_dates_amounts if d > safe.issue_date]
        if not subsequent:
            continue

        # Spec §1.5 rule 5: fire on *any* subsequent round meeting the threshold,
        # not just the first. Cite the earliest qualifying round.
        threshold = safe.conversion_trigger_threshold or 0.0
        qualifying = [(d, amt, name) for d, amt, name in subsequent if amt >= threshold]
        if qualifying:
            trig_date, trig_amount, trig_name = qualifying[0]
            out.append(
                Finding(
                    code=f"SAFE-UNCONVERTED-{safe.id}",
                    severity="blocker",
                    category="unrecorded_safe_conversion",
                    summary=(
                        f"SAFE {safe.id} (issued {safe.issue_date.isoformat()}, "
                        f"principal {safe.principal:,.0f}) is listed as outstanding but its "
                        f"conversion trigger appears to have been satisfied at the {trig_name} "
                        f"closing on {trig_date.isoformat()}."
                    ),
                    detail=(
                        "Confirm whether the SAFE has been converted and add the resulting shares "
                        "to the cap table tab. Conversion math typically: principal / "
                        "min(round_price, cap_implied_price)."
                    ),
                    fields_referenced=(f"safes_outstanding[{safe.id}]",),
                )
            )
    return out


@rule(
    id="G-WAR-001",
    severity="warning",
    category="unrecorded_warrant",
    summary="Warrant listed as outstanding but not represented on cap table.",
    citation="AICPA Cheap Stock Guide §3.27 (deep-ITM warrants in fully-diluted count).",
)
def _rule_warrants_outstanding(cap_table: CapTable) -> list[Finding]:
    out = []
    for war in cap_table.warrants_outstanding:
        out.append(
            Finding(
                code=f"WARRANT-{war.id}",
                severity="warning",
                category="unrecorded_warrant",
                summary=(
                    f"Warrant {war.id} ({war.shares:,} {war.share_class} shares "
                    f"to {war.holder}) is listed but not represented as shares on cap table."
                ),
                detail=(
                    "Vendor or strategic warrants struck below current FMV are deep-in-the-money "
                    "and should typically be added to fully-diluted share count. Confirm exercise "
                    "status and either add to cap table or document exclusion policy."
                ),
                fields_referenced=(f"warrants_outstanding[{war.id}]",),
            )
        )
    return out


@rule(
    id="G-SL-001",
    severity="warning",
    category="side_letter_terms_missing",
    summary="Side letter exists but terms or scope are not fully entered.",
    citation="NVCA Model Side Letter; AICPA Cheap Stock Guide §2.21.",
)
def _rule_side_letter_terms_missing(cap_table: CapTable) -> list[Finding]:
    out = []
    for sl in cap_table.side_letters:
        body_empty = sl.body is None or not str(sl.body).strip()
        summary_thin = not (sl.summary and len(sl.summary.strip()) > 30)
        if body_empty and summary_thin:
            out.append(
                Finding(
                    code=f"SIDE-LETTER-{sl.id}",
                    severity="warning",
                    category="side_letter_terms_missing",
                    summary=f"Side letter {sl.id} ('{sl.title}') exists but no specific terms entered.",
                    detail=(
                        "Side-letter rights (MFN, super pro-rata, voting differentials) can "
                        "affect future-round modeling and conversion math. Capture the "
                        "specific trigger and scope."
                    ),
                    fields_referenced=(f"side_letters[{sl.id}]",),
                )
            )
            continue
        if sl.unresolved_questions:
            out.append(
                Finding(
                    code=f"SIDE-LETTER-SCOPE-{sl.id}",
                    severity="warning",
                    category="side_letter_scope_unresolved",
                    summary=(
                        f"Side letter {sl.id} ('{sl.title}') has {len(sl.unresolved_questions)} "
                        "unresolved scope question" + ("s" if len(sl.unresolved_questions) > 1 else "") + "."
                    ),
                    detail="Open questions: " + " | ".join(sl.unresolved_questions),
                    fields_referenced=(f"side_letters[{sl.id}].unresolved_questions",),
                )
            )
    return out


@rule(
    id="G-VOTE-001",
    severity="info",
    category="dual_class_voting_documented",
    summary="Class carries a voting differential and needs audit-memo disclosure.",
    citation="VIMA model docs (Singapore); Cyril Amarchand Indian dual-class convention.",
)
def _rule_dual_class_voting_documented(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if sc.voting_differential and str(sc.voting_differential).strip():
            out.append(
                Finding(
                    code=f"VOTING-DIFF-{sc.name}",
                    severity="info",
                    category="dual_class_voting_documented",
                    summary=f"{sc.name} carries a voting differential.",
                    detail=(
                        "Voting differential is disclosed in the audit memo's capital structure "
                        "section. Per VIMA / Cyril Amarchand convention for Indian dual-class "
                        "structures, identical economic rights with voting differentials are "
                        "modeled as one economic class for waterfall purposes."
                    ),
                    fields_referenced=(f"share_classes[{sc.name}].voting_differential",),
                )
            )
    return out


# ---- Main entry --------------------------------------------------------------


ALL_RULES = [
    _rule_anti_dilution_unspecified,
    _rule_full_ratchet_documented,
    _rule_participating_with_cap_documented,
    _rule_stale_option_pool,
    _rule_unrecorded_safe_conversion,
    _rule_warrants_outstanding,
    _rule_side_letter_terms_missing,
    _rule_dual_class_voting_documented,
]


def run_checklist(
    cap_table: CapTable,
    pack=None,
    engagement_jurisdiction: Optional[str] = None,
) -> list[Finding]:
    """Run the checklist rules against a CapTable.

    By default, runs the rule pack effective today. Pass `pack` to pin a
    specific RulePack (engagement-bound or otherwise). Pass
    `engagement_jurisdiction` to filter to rules tagged for that jurisdiction
    (per GAP-26).
    """
    from .rule_pack import run_pack

    return run_pack(cap_table, pack=pack, engagement_jurisdiction=engagement_jurisdiction)
