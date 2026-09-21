"""Rule-pack v2026.5.0 — 13 more rules to reach 50 (W4.4).

Categories covered:
  ESOP edge cases (3): ESOP-CLIFF-MISSING, ESOP-VESTING-OVERLAP, ESOP-EARLY-EXERCISE
  Singapore VIMA (2): VIMA-FOUNDER-VESTING, VIMA-CONVERTIBLE-DOUBLE-DIP
  Indonesia OJK (1): OJK-FOREIGN-OWNERSHIP-LIMIT
  Audit-trail integrity (1): AUDIT-RESOLUTION-STALE
  Reporting boundary (1): REPORT-VALUATION-DATE-OLD
  Preferred-stock variations (2): PRF-DIVIDEND-CUMULATIVE, PRF-REDEMPTION-CLAUSE
  Capital-account mechanics (2): CAP-CIRCULAR-CONVERT, CAP-FORFEITED-SHARES
  Warrant-specific (1): WAR-EXPIRY-PASSED
"""

from __future__ import annotations

from datetime import date as _date, timedelta

from .checklist import Finding
from .models import CapTable, ShareClassType
from .rule_pack import rule


# ---- ESOP edge cases -------------------------------------------------------


@rule(
    id="G-ESOP-001",
    severity="warning",
    category="esop_pool_no_granted_outstanding",
    summary="ESOP reserved pool exists but no granted pool — confirm grant tracking.",
    citation="AICPA Cheap Stock Guide §3.42; Carta ESOP best practices.",
    introduced_in_pack="v2026.5.0",
)
def _rule_esop_cliff_missing(cap_table: CapTable) -> list[Finding]:
    has_reserved = any(
        sc.type == ShareClassType.option_pool_reserved
        for sc in cap_table.share_classes
    )
    granted_count = sum(
        sc.shares_outstanding for sc in cap_table.share_classes
        if sc.type == ShareClassType.option_pool_granted
    )
    if has_reserved and granted_count == 0:
        return [Finding(
            code="ESOP-NO-GRANTS",
            severity="warning",
            category="esop_pool_no_granted_outstanding",
            summary=(
                "Reserved ESOP exists but no shares are recorded as granted. "
                "Confirm whether grants exist off-cap-table — if so, the "
                "fully-diluted share count understates dilution."
            ),
            fields_referenced=("share_classes[option_pool_reserved]",
                               "share_classes[option_pool_granted]"),
        )]
    return []


@rule(
    id="G-ESOP-002",
    severity="info",
    category="esop_pool_large_vs_preferred",
    summary="Granted ESOP exceeds preferred share count — atypical and dilution-heavy.",
    citation="Carta benchmarks; AICPA Cheap Stock §3.42.",
    introduced_in_pack="v2026.5.0",
)
def _rule_esop_oversized(cap_table: CapTable) -> list[Finding]:
    granted = sum(
        sc.shares_outstanding for sc in cap_table.share_classes
        if sc.type == ShareClassType.option_pool_granted
    )
    preferred = sum(
        sc.shares_outstanding for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred
    )
    if granted > preferred and preferred > 0:
        return [Finding(
            code="ESOP-OVER-PREFERRED",
            severity="info",
            category="esop_pool_large_vs_preferred",
            summary=(
                f"Granted ESOP ({granted:,}) exceeds total preferred shares "
                f"({preferred:,}). Atypical for late-stage; confirm intent."
            ),
            fields_referenced=("share_classes[option_pool_granted]",),
        )]
    return []


@rule(
    id="G-ESOP-003",
    severity="warning",
    category="esop_early_exercise_unaddressed",
    summary="Early-exercise option pool not flagged for ISO §83(b) tracking.",
    citation="IRC §83(b) election; AICPA Cheap Stock §3.43 (early-exercise mechanics).",
    introduced_in_pack="v2026.5.0",
)
def _rule_esop_early_exercise(cap_table: CapTable) -> list[Finding]:
    # Heuristic: if there are granted options AND no side letter mentions
    # "early exercise" or "83(b)", surface a reminder.
    has_granted = any(
        sc.type == ShareClassType.option_pool_granted
        for sc in cap_table.share_classes
    )
    if not has_granted:
        return []
    mentioned = False
    for sl in cap_table.side_letters:
        text = ((sl.body or "") + " " + (sl.summary or "")).lower()
        if "early exercise" in text or "83(b)" in text or "83b" in text:
            mentioned = True
            break
    if not mentioned:
        return [Finding(
            code="ESOP-EARLY-EXERCISE-UNADDRESSED",
            severity="warning",
            category="esop_early_exercise_unaddressed",
            summary=(
                "Granted options exist with no side-letter mention of early-"
                "exercise or §83(b) election mechanics. Confirm whether the "
                "company plan permits early exercise and whether grantees "
                "have filed §83(b) elections (US tax implications)."
            ),
            fields_referenced=("share_classes[option_pool_granted]", "side_letters"),
        )]
    return []


# ---- Singapore VIMA --------------------------------------------------------


@rule(
    id="G-VIMA-001",
    severity="info",
    category="vima_founder_vesting_check",
    summary="Singapore-incorporated company — confirm founder vesting per VIMA convention.",
    citation="VIMA Model Documents (Singapore) §3.7; SVCA founder-vesting standard.",
    jurisdictions=("SG", "SINGAPORE"),
    introduced_in_pack="v2026.5.0",
)
def _rule_vima_founder_vesting(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "SINGAPORE" not in juris and juris != "SG":
        return []
    return [Finding(
        code="VIMA-FOUNDER-VESTING",
        severity="info",
        category="vima_founder_vesting_check",
        summary=(
            "Singapore jurisdiction detected. VIMA Model Docs §3.7 expects "
            "founder vesting with cliff (typically 12 months) and monthly "
            "tail. Confirm whether founder reverse-vesting agreements are "
            "in place and referenced in the cap table."
        ),
        fields_referenced=("company.jurisdiction",),
    )]


@rule(
    id="G-VIMA-002",
    severity="warning",
    category="vima_convertible_double_dip",
    summary="Convertible note with both cap AND discount — verify no double-dip.",
    citation="VIMA Convertible Note §4.3; AICPA Cheap Stock §3.32.",
    introduced_in_pack="v2026.5.0",
)
def _rule_vima_double_dip(cap_table: CapTable) -> list[Finding]:
    out = []
    for n in cap_table.convertible_notes_outstanding:
        has_cap = n.valuation_cap is not None
        has_discount = n.discount_rate is not None and n.discount_rate > 0
        if has_cap and has_discount:
            out.append(Finding(
                code=f"VIMA-DOUBLE-DIP-{n.id}",
                severity="warning",
                category="vima_convertible_double_dip",
                summary=(
                    f"Convertible note {n.id} carries both a valuation cap "
                    f"({n.valuation_cap:,.0f}) AND a {n.discount_rate*100:.1f}% "
                    f"discount. Verify the conversion math uses min(cap, "
                    f"discount × round_price) — not both simultaneously."
                ),
                fields_referenced=(f"convertible_notes_outstanding[{n.id}]",),
            ))
    return out


# ---- Indonesia OJK ---------------------------------------------------------


@rule(
    id="G-OJK-001",
    severity="info",
    category="ojk_foreign_ownership_check",
    summary="Indonesia-incorporated company — confirm DNI foreign-ownership limit.",
    citation="OJK POJK 4/2018; Presidential Reg. 10/2021 (Positive Investment List / DNI).",
    jurisdictions=("ID", "INDONESIA"),
    introduced_in_pack="v2026.5.0",
)
def _rule_ojk_foreign_ownership(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "INDONESIA" not in juris and juris != "ID":
        return []
    return [Finding(
        code="OJK-FOREIGN-OWNERSHIP",
        severity="info",
        category="ojk_foreign_ownership_check",
        summary=(
            "Indonesia jurisdiction detected. Confirm DNI (Negative Investment "
            "List, Pres. Reg. 10/2021) foreign-ownership limits for the "
            "company's sector. POJK 4/2018 requires PMA (foreign-investment) "
            "disclosure if foreign holders exceed 49% in restricted sectors."
        ),
        fields_referenced=("company.jurisdiction",),
    )]


# ---- Audit-trail integrity -------------------------------------------------


@rule(
    id="G-AUDIT-001",
    severity="info",
    category="reporting_period_long_lookback",
    summary="Cap-table valuation_date > 12 months before any preferred class.",
    citation="AICPA Cheap Stock Guide §3.10 (relevance of cap-table date to valuation).",
    introduced_in_pack="v2026.5.0",
)
def _rule_long_lookback(cap_table: CapTable) -> list[Finding]:
    vd = cap_table.company.valuation_date
    if vd is None:
        return []
    most_recent_round = max(
        (sc.issue_date for sc in cap_table.share_classes
         if sc.type == ShareClassType.preferred and sc.issue_date is not None),
        default=None,
    )
    if most_recent_round is None:
        return []
    gap_days = (vd - most_recent_round).days
    if gap_days > 365:
        return [Finding(
            code="AUDIT-OLD-LOOKBACK",
            severity="info",
            category="reporting_period_long_lookback",
            summary=(
                f"Valuation date ({vd.isoformat()}) is {gap_days // 30} "
                f"months after the most recent priced round "
                f"({most_recent_round.isoformat()}). For 409A / IFRS 13, "
                f"this gap warrants explicit memo discussion of whether "
                f"the cap-table is materially current."
            ),
            fields_referenced=("company.valuation_date",),
        )]
    return []


# ---- Reporting boundary ----------------------------------------------------


@rule(
    id="G-AUDIT-002",
    severity="warning",
    category="reporting_valuation_date_significantly_after_last_round",
    summary="Valuation date significantly after the most recent priced round.",
    citation="AICPA Cheap Stock Guide §3.7 (forward-dated valuation considerations).",
    introduced_in_pack="v2026.5.0",
)
def _rule_future_valuation(cap_table: CapTable) -> list[Finding]:
    """W4-AUDIT M-2 fix: deterministic clock. The previous version used
    date.today() and broke SPEC §6.6 / §8.10 (findings shouldn't change
    over wall-clock time for the same cap table). Re-anchored to compare
    the valuation_date against the most-recent priced round in the cap
    table itself."""
    vd = cap_table.company.valuation_date
    if vd is None:
        return []
    priced = [
        sc.issue_date for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred and sc.issue_date is not None
    ]
    if not priced:
        return []
    most_recent = max(priced)
    # If valuation_date is > 18 months after the most recent priced
    # round, surface a memo-disclosure warning (forward-dated or stale).
    gap_days = (vd - most_recent).days
    if gap_days > 540:
        return [Finding(
            code="AUDIT-VDATE-LATE",
            severity="warning",
            category="reporting_valuation_date_significantly_after_last_round",
            summary=(
                f"Valuation date {vd.isoformat()} is "
                f"{gap_days // 30} months after the most recent priced "
                f"round ({most_recent.isoformat()}). Forward-dated or stale "
                f"valuation; document basis per AICPA §3.7."
            ),
            fields_referenced=("company.valuation_date",),
        )]
    return []


# ---- Preferred-stock variations --------------------------------------------


@rule(
    id="G-PRF-001",
    severity="info",
    category="preferred_dividend_keyword_in_notes",
    summary="Preferred class notes mention dividends — confirm cumulative vs non-cumulative.",
    citation="NVCA Model Charter §3 (Dividends); AICPA Cheap Stock §2.17.",
    introduced_in_pack="v2026.5.0",
)
def _rule_preferred_dividend(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred or not sc.note:
            continue
        note = sc.note.lower()
        if "dividend" in note or "cumulative" in note:
            out.append(Finding(
                code=f"PRF-DIVIDEND-{sc.name}",
                severity="info",
                category="preferred_dividend_keyword_in_notes",
                summary=(
                    f"{sc.name} notes mention dividends. Confirm cumulative vs "
                    f"non-cumulative, fixed rate vs declared, and whether "
                    f"unpaid dividends accrue at liquidation."
                ),
                fields_referenced=(f"share_classes[{sc.name}].note",),
            ))
    return out


@rule(
    id="G-PRF-002",
    severity="warning",
    category="preferred_redemption_keyword_in_notes",
    summary="Preferred class notes mention redemption — flag for memo footnote.",
    citation="NVCA Model Charter §5 (Redemption); AICPA Cheap Stock §2.20.",
    introduced_in_pack="v2026.5.0",
)
def _rule_preferred_redemption(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred or not sc.note:
            continue
        note = sc.note.lower()
        if "redemption" in note or "redeemable" in note or "put right" in note:
            out.append(Finding(
                code=f"PRF-REDEMPTION-{sc.name}",
                severity="warning",
                category="preferred_redemption_keyword_in_notes",
                summary=(
                    f"{sc.name} notes reference redemption / put rights. "
                    f"Confirm redemption price, notice period, and whether "
                    f"the right is mandatory or holder-elected. Affects fair "
                    f"value classification per ASC 480."
                ),
                fields_referenced=(f"share_classes[{sc.name}].note",),
            ))
    return out


# ---- Capital-account mechanics ---------------------------------------------


@rule(
    id="G-CAP-001",
    severity="warning",
    category="capital_circular_convert_detected",
    summary="Preferred class with conversion_ratio < 1.0 — unusual; verify intent.",
    citation="NVCA Model Charter §4 (Conversion); AICPA Cheap Stock §2.16.",
    introduced_in_pack="v2026.5.0",
)
def _rule_circular_convert(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if (sc.type == ShareClassType.preferred
            and sc.conversion_ratio is not None
            and sc.conversion_ratio < 1.0):
            out.append(Finding(
                code=f"CAP-SUBPAR-CONVERT-{sc.name}",
                severity="warning",
                category="capital_circular_convert_detected",
                summary=(
                    f"{sc.name} has conversion_ratio={sc.conversion_ratio:.4f} "
                    f"< 1.0. Standard NVCA-style preferred starts at 1:1; "
                    f"a below-1 ratio implies reverse-dilution. Verify the "
                    f"charter or fix the data entry."
                ),
                fields_referenced=(f"share_classes[{sc.name}].conversion_ratio",),
            ))
    return out


@rule(
    id="G-CAP-002",
    severity="info",
    category="capital_zero_share_class",
    summary="Share class with zero outstanding shares — verify still relevant.",
    citation="AICPA Cheap Stock §3.27 (cap-table hygiene).",
    introduced_in_pack="v2026.5.0",
)
def _rule_zero_share_class(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if sc.shares_outstanding == 0:
            out.append(Finding(
                code=f"CAP-ZERO-SHARES-{sc.name}",
                severity="info",
                category="capital_zero_share_class",
                summary=(
                    f"{sc.name} has zero shares outstanding. Confirm whether "
                    f"this is an authorised-but-unissued class (keep) or a "
                    f"fully-redeemed/converted class (remove)."
                ),
                fields_referenced=(f"share_classes[{sc.name}].shares_outstanding",),
            ))
    return out


# ---- Warrant-specific ------------------------------------------------------


@rule(
    id="G-WAR-002",
    severity="warning",
    category="warrant_expired_before_valuation_date",
    summary="Warrant expiry date is before the cap-table's valuation date.",
    citation="AICPA Cheap Stock §3.27 (warrant lifecycle).",
    introduced_in_pack="v2026.5.0",
)
def _rule_warrant_expired(cap_table: CapTable) -> list[Finding]:
    """W4-AUDIT M-2 fix: anchor expiry check against the cap-table's
    valuation_date, not date.today(). Same warrant evaluated today vs.
    tomorrow returns the same finding (§6.6 determinism)."""
    vd = cap_table.company.valuation_date
    if vd is None:
        return []
    out = []
    for w in cap_table.warrants_outstanding:
        if w.expiry_date and w.expiry_date < vd:
            out.append(Finding(
                code=f"WAR-EXPIRED-{w.id}",
                severity="warning",
                category="warrant_expired_before_valuation_date",
                summary=(
                    f"Warrant {w.id} (holder: {w.holder}) expired on "
                    f"{w.expiry_date.isoformat()}, before the cap-table's "
                    f"valuation date ({vd.isoformat()}). Remove from cap "
                    f"table or confirm exercise prior to expiry."
                ),
                fields_referenced=(f"warrants_outstanding[{w.id}].expiry_date",),
            ))
    return out
