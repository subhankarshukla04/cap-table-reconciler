"""Rule-pack expansion v2026.2.0: 15 new rules added to the baseline 8.

Each rule has: stable G-prefix ID, severity, category, citation to a
published precedent, optional jurisdiction predicate. Rules registered
here via the @rule decorator at import time; the pack JSON references
them by ID.

Categories covered (per SYSTEM_SPEC §4.1 / PRODUCTION_ROADMAP §4.1):
  - Anti-dilution mechanics (G-AD-003, G-AD-004, G-AD-005)
  - Participation/cap mechanics (G-LP-002, G-LP-003)
  - SAFE/convertible mechanics (G-SAFE-002, G-SAFE-003)
  - Option pool mechanics (G-POOL-002, G-POOL-003)
  - Voting / governance (G-VOTE-002)
  - Round mechanics (G-ROUND-001, G-ROUND-002)
  - Side-letter integrity (G-SL-002)
  - Jurisdiction-specific (G-IN-001 India FEMA proxy, G-CURR-001 currency mismatch)
"""

from __future__ import annotations

from .checklist import Finding
from .models import (
    AntiDilutionVariant,
    CapTable,
    LPType,
    ShareClassType,
)
from .rule_pack import rule


# ---- Anti-dilution mechanics -----------------------------------------------


@rule(
    id="G-AD-003",
    severity="warning",
    category="anti_dilution_narrow_basket_used",
    summary="Narrow-based weighted-average reduces dilution to other holders; flag for memo.",
    citation="NVCA Model Charter §4.4(b)(ii); AICPA Cheap Stock Guide §2.18.",
    introduced_in_pack="v2026.2.0",
)
def _rule_narrow_based_ad_flag(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if (sc.type == ShareClassType.preferred
            and sc.anti_dilution
            and sc.anti_dilution.variant == AntiDilutionVariant.narrow_based_weighted_average):
            out.append(Finding(
                code=f"AD-NARROW-{sc.name}",
                severity="warning",
                category="anti_dilution_narrow_basket_used",
                summary=f"{sc.name} carries narrow-based weighted-average AD.",
                detail=(
                    "Narrow-based denominator excludes options pool, increasing "
                    "the AD effect on a future down-round. Confirm denominator "
                    "definition in charter and document in memo."
                ),
                fields_referenced=(f"share_classes[{sc.name}].anti_dilution.variant",),
            ))
    return out


@rule(
    id="G-AD-004",
    severity="info",
    category="anti_dilution_triggered_conv_ratio_recorded",
    summary="Conversion ratio > 1.0 indicates a triggered anti-dilution adjustment.",
    citation="NVCA Model Charter §4.4(d); Cooley GO down-round mechanics primer.",
    introduced_in_pack="v2026.2.0",
)
def _rule_triggered_ad_conv_ratio(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        if (sc.type == ShareClassType.preferred
            and sc.conversion_ratio is not None
            and sc.conversion_ratio > 1.0 + 1e-9):
            out.append(Finding(
                code=f"AD-TRIGGERED-{sc.name}",
                severity="info",
                category="anti_dilution_triggered_conv_ratio_recorded",
                summary=(
                    f"{sc.name} has conversion_ratio={sc.conversion_ratio:.4f} > 1.0; "
                    f"confirm trigger event (down-round, ratchet) and document basis."
                ),
                fields_referenced=(f"share_classes[{sc.name}].conversion_ratio",),
            ))
    return out


@rule(
    id="G-AD-005",
    severity="warning",
    category="anti_dilution_inconsistent_across_pari_passu",
    summary="Pari-passu classes carry different AD variants; usually a misclassification.",
    citation="Practitioner observation; AICPA Cheap Stock Guide §2.18 commentary on round-mate symmetry.",
    introduced_in_pack="v2026.2.0",
)
def _rule_ad_consistent_across_pari_passu(cap_table: CapTable) -> list[Finding]:
    out = []
    by_rank: dict[int, list] = {}
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred:
            continue
        by_rank.setdefault(sc.seniority_rank, []).append(sc)
    for rank, classes in by_rank.items():
        if len(classes) < 2:
            continue
        variants = {
            (sc.anti_dilution.variant.value if sc.anti_dilution and sc.anti_dilution.variant else None)
            for sc in classes
        }
        if len(variants) > 1:
            names = sorted(sc.name for sc in classes)
            out.append(Finding(
                code=f"AD-PARI-PASSU-INCONSISTENT-{rank}",
                severity="warning",
                category="anti_dilution_inconsistent_across_pari_passu",
                summary=(
                    f"Pari-passu group at rank {rank} ({', '.join(names)}) has "
                    f"differing AD variants {sorted(v for v in variants if v)}; "
                    f"verify intent."
                ),
                fields_referenced=tuple(
                    f"share_classes[{n}].anti_dilution.variant" for n in names
                ),
            ))
    return out


# ---- Participation / cap mechanics ----------------------------------------


@rule(
    id="G-LP-002",
    severity="blocker",
    category="participating_cap_below_lp",
    summary="Participating-with-cap with cap_multiple < 1.0 is economically contradictory.",
    citation="Engine validator (src/models.py:cap_required_when_capped); AICPA Cheap Stock §4.x.",
    introduced_in_pack="v2026.2.0",
)
def _rule_cap_below_lp(cap_table: CapTable) -> list[Finding]:
    """Defence-in-depth: the pydantic validator already raises on this, but
    if the CapTable was constructed via a path that bypassed validation
    (e.g., test fixture), surface explicitly."""
    out = []
    for sc in cap_table.share_classes:
        lp = sc.liquidation_preference
        if lp is None or lp.type != LPType.participating_capped:
            continue
        if lp.cap_multiple is not None and lp.cap_multiple < 1.0:
            out.append(Finding(
                code=f"LP-CAP-BELOW-LP-{sc.name}",
                severity="blocker",
                category="participating_cap_below_lp",
                summary=f"{sc.name} cap_multiple={lp.cap_multiple} < 1.0.",
                fields_referenced=(f"share_classes[{sc.name}].liquidation_preference.cap_multiple",),
            ))
    return out


@rule(
    id="G-LP-003",
    severity="info",
    category="lp_multiple_above_one",
    summary="Liquidation preference multiple > 1.0× attracts auditor scrutiny.",
    citation="AICPA Cheap Stock Guide §2.16; NVCA Model Charter §2.1.",
    introduced_in_pack="v2026.2.0",
)
def _rule_lp_multiple_above_one(cap_table: CapTable) -> list[Finding]:
    out = []
    for sc in cap_table.share_classes:
        lp = sc.liquidation_preference
        if lp is not None and lp.multiple > 1.0 + 1e-9:
            out.append(Finding(
                code=f"LP-MULT-ABOVE-1-{sc.name}",
                severity="info",
                category="lp_multiple_above_one",
                summary=f"{sc.name} carries a {lp.multiple}× liquidation preference.",
                detail=(
                    "Multiples above 1.0× are common in down-round or distressed "
                    "rounds and should be documented in the memo's methodology "
                    "section."
                ),
                fields_referenced=(f"share_classes[{sc.name}].liquidation_preference.multiple",),
            ))
    return out


# ---- SAFE / convertible mechanics -----------------------------------------


@rule(
    id="G-SAFE-002",
    severity="warning",
    category="safe_mfn_only_unflagged",
    summary="MFN-only SAFE (no cap, no discount) is invisible to the default SAFE rule.",
    citation="Y Combinator MFN-only SAFE template; GAP-19 in AUDIT_PLAN.md.",
    introduced_in_pack="v2026.2.0",
)
def _rule_safe_mfn_only(cap_table: CapTable) -> list[Finding]:
    """Spec GAP-19 closure: an MFN-only SAFE has no cap, no discount, and
    no explicit trigger_threshold — it converts at the next priced round at
    that round's terms via MFN. The default G-SAFE-001 rule doesn't fire on
    it because trigger_threshold is None. Flag explicitly when any preferred
    round exists post-SAFE."""
    out = []
    preferred_dates = sorted(
        sc.issue_date for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred and sc.issue_date is not None
    )
    if not preferred_dates:
        return out
    for s in cap_table.safes_outstanding:
        if s.issue_date is None:
            continue
        has_cap = s.valuation_cap is not None
        has_discount = s.discount_rate is not None and s.discount_rate > 0
        has_threshold = s.conversion_trigger_threshold is not None
        if has_cap or has_discount or has_threshold:
            continue
        later_round = next((d for d in preferred_dates if d > s.issue_date), None)
        if later_round is None:
            continue
        out.append(Finding(
            code=f"SAFE-MFN-ONLY-{s.id}",
            severity="warning",
            category="safe_mfn_only_unflagged",
            summary=(
                f"SAFE {s.id} (issued {s.issue_date.isoformat()}) has no cap, "
                f"no discount, and no explicit trigger threshold. A preferred "
                f"round closed on {later_round.isoformat()}; confirm MFN "
                f"conversion terms were applied."
            ),
            fields_referenced=(f"safes_outstanding[{s.id}]",),
        ))
    return out


@rule(
    id="G-SAFE-003",
    severity="warning",
    category="convertible_note_qualified_threshold_unset",
    summary="Convertible note outstanding without a qualified_financing_threshold cannot be checked.",
    citation="AICPA Cheap Stock Guide §3.32 (convertible-note conversion triggers).",
    introduced_in_pack="v2026.2.0",
)
def _rule_convertible_threshold_missing(cap_table: CapTable) -> list[Finding]:
    out = []
    for n in cap_table.convertible_notes_outstanding:
        if n.qualified_financing_threshold is None:
            out.append(Finding(
                code=f"CONV-NO-THRESHOLD-{n.id}",
                severity="warning",
                category="convertible_note_qualified_threshold_unset",
                summary=(
                    f"Convertible note {n.id} has no qualified_financing_threshold; "
                    f"cannot evaluate whether subsequent rounds triggered conversion."
                ),
                fields_referenced=(f"convertible_notes_outstanding[{n.id}].qualified_financing_threshold",),
            ))
    return out


# ---- Option pool mechanics -------------------------------------------------


@rule(
    id="G-POOL-002",
    severity="info",
    category="option_pool_size_atypical",
    summary="Option pool > 25% of fully-diluted is atypical for late-stage; flag.",
    citation="Carta benchmarks; Cooley GO option-pool sizing primer.",
    introduced_in_pack="v2026.2.0",
)
def _rule_pool_size_atypical(cap_table: CapTable) -> list[Finding]:
    total = cap_table.total_fully_diluted_for_waterfall
    if total <= 0:
        return []
    pool_shares = sum(
        sc.shares_outstanding for sc in cap_table.share_classes
        if sc.type == ShareClassType.option_pool_granted
    )
    if total == 0:
        return []
    pct = pool_shares / total
    if pct > 0.25:
        return [Finding(
            code="POOL-SIZE-ATYPICAL",
            severity="info",
            category="option_pool_size_atypical",
            summary=f"Granted option pool is {pct:.1%} of fully-diluted shares.",
            detail="Above ~25% is unusual outside of very-early or recap stages.",
            fields_referenced=("share_classes[option_pool_granted].shares_outstanding",),
        )]
    return []


@rule(
    id="G-POOL-003",
    severity="warning",
    category="option_pool_reserved_without_granted",
    summary="Reserved pool present but no granted pool — confirm no grants outstanding.",
    citation="Carta cap-table hygiene checklist.",
    introduced_in_pack="v2026.2.0",
)
def _rule_pool_reserved_no_granted(cap_table: CapTable) -> list[Finding]:
    has_reserved = any(
        sc.type == ShareClassType.option_pool_reserved
        for sc in cap_table.share_classes
    )
    has_granted = any(
        sc.type == ShareClassType.option_pool_granted
        for sc in cap_table.share_classes
    )
    if has_reserved and not has_granted:
        return [Finding(
            code="POOL-RESERVED-NO-GRANTED",
            severity="warning",
            category="option_pool_reserved_without_granted",
            summary="Reserved pool present but no granted pool. Confirm.",
            fields_referenced=("share_classes[option_pool_reserved]",),
        )]
    return []


# ---- Voting / governance ---------------------------------------------------


@rule(
    id="G-VOTE-002",
    severity="info",
    category="voting_differential_more_than_ten_to_one",
    summary="Voting differential exceeds 10:1; document carefully for memo.",
    citation="VIMA model docs (Singapore); Snap / Pinterest IPO precedents.",
    introduced_in_pack="v2026.2.0",
)
def _rule_voting_ratio_extreme(cap_table: CapTable) -> list[Finding]:
    import re
    out = []
    for sc in cap_table.share_classes:
        v = sc.voting_differential
        if not v:
            continue
        m = re.search(r"(\d+)\s*[:x]\s*1", str(v))
        if not m:
            continue
        try:
            ratio = int(m.group(1))
        except ValueError:
            continue
        if ratio > 10:
            out.append(Finding(
                code=f"VOTE-RATIO-{sc.name}",
                severity="info",
                category="voting_differential_more_than_ten_to_one",
                summary=f"{sc.name} voting differential {ratio}:1.",
                fields_referenced=(f"share_classes[{sc.name}].voting_differential",),
            ))
    return out


# ---- Round mechanics -------------------------------------------------------


@rule(
    id="G-ROUND-001",
    severity="warning",
    category="down_round_detected",
    summary="A later preferred class was issued at a lower PPS than an earlier one.",
    citation="AICPA Cheap Stock Guide §2.18 (down-round triggers); NVCA AD primer.",
    introduced_in_pack="v2026.2.0",
)
def _rule_down_round(cap_table: CapTable) -> list[Finding]:
    out = []
    priced = sorted(
        ((sc.issue_date, sc.issue_price, sc.name)
         for sc in cap_table.share_classes
         if sc.type == ShareClassType.preferred
         and sc.issue_date is not None and sc.issue_price is not None),
        key=lambda t: t[0],
    )
    seen_max = 0.0
    for d, p, name in priced:
        if p < seen_max - 1e-9:
            out.append(Finding(
                code=f"DOWN-ROUND-{name}",
                severity="warning",
                category="down_round_detected",
                summary=(
                    f"{name} (PPS {p}) was issued after a higher-PPS round "
                    f"(prior max {seen_max}); confirm AD triggers and ratchet."
                ),
                fields_referenced=(f"share_classes[{name}].issue_price",),
            ))
        if p > seen_max:
            seen_max = p
    return out


@rule(
    id="G-ROUND-002",
    severity="info",
    category="multiple_rounds_same_date",
    summary="Two preferred classes share the same issue_date — likely pari-passu.",
    citation="Practitioner observation; VIMA same-day-close convention.",
    introduced_in_pack="v2026.2.0",
)
def _rule_same_date_rounds(cap_table: CapTable) -> list[Finding]:
    by_date: dict = {}
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred or sc.issue_date is None:
            continue
        by_date.setdefault(sc.issue_date, []).append(sc)
    out = []
    for d, classes in by_date.items():
        if len(classes) < 2:
            continue
        names = sorted(sc.name for sc in classes)
        ranks = {sc.seniority_rank for sc in classes}
        if len(ranks) > 1:
            # Not flagged as pari-passu in the model; surface as note.
            out.append(Finding(
                code=f"SAME-DATE-{d.isoformat()}",
                severity="info",
                category="multiple_rounds_same_date",
                summary=(
                    f"{len(classes)} preferred classes ({', '.join(names)}) "
                    f"closed on {d.isoformat()} with different seniority ranks; "
                    f"verify they are not pari-passu."
                ),
                fields_referenced=tuple(f"share_classes[{n}].issue_date" for n in names),
            ))
    return out


# ---- Side-letter integrity -------------------------------------------------


@rule(
    id="G-SL-002",
    severity="warning",
    category="side_letter_mfn_keyword_unresolved",
    summary="Side letter body mentions MFN — verify scope is captured in cap-table model.",
    citation="NVCA Model Side Letter §X (MFN clauses); Cooley GO MFN primer.",
    introduced_in_pack="v2026.2.0",
)
def _rule_side_letter_mfn(cap_table: CapTable) -> list[Finding]:
    out = []
    for sl in cap_table.side_letters:
        body = (sl.body or "") + " " + (sl.summary or "")
        if "mfn" in body.lower() or "most-favored" in body.lower() or "most favored" in body.lower():
            out.append(Finding(
                code=f"SL-MFN-{sl.id}",
                severity="warning",
                category="side_letter_mfn_keyword_unresolved",
                summary=(
                    f"Side letter {sl.id} ('{sl.title}') mentions MFN. Confirm "
                    f"scope (rights ratchet vs term ratchet) is reflected."
                ),
                fields_referenced=(f"side_letters[{sl.id}]",),
            ))
    return out


# ---- Jurisdiction-specific -------------------------------------------------


@rule(
    id="G-IN-001",
    severity="info",
    category="india_jurisdiction_check_required",
    summary="India-jurisdiction cap table: confirm FEMA / SEBI compliance overlay.",
    citation="RBI FEMA Pricing Guidelines; SEBI (ICDR) Regulations 2018.",
    jurisdictions=("IN", "INDIA"),
    introduced_in_pack="v2026.2.0",
)
def _rule_india_compliance_overlay(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "INDIA" not in juris and juris != "IN":
        return []
    return [Finding(
        code="IN-FEMA-OVERLAY",
        severity="info",
        category="india_jurisdiction_check_required",
        summary=(
            "India jurisdiction detected. Confirm FEMA fair-value floor, "
            "SEBI pricing constraints, and CCPS/RCPS conversion mechanics are "
            "addressed in the memo."
        ),
        fields_referenced=("company.jurisdiction",),
    )]


@rule(
    id="G-CURR-001",
    severity="info",
    category="currency_mismatch_with_jurisdiction",
    summary="Cap-table currency does not match the jurisdiction's typical local currency.",
    citation="Practitioner observation; common audit-memo footnote requirement.",
    introduced_in_pack="v2026.2.0",
)
def _rule_currency_mismatch(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    currency = (cap_table.company.currency or "").upper()
    expected = {
        "INDIA": "INR", "IN": "INR",
        "SINGAPORE": "SGD", "SG": "SGD",
        "USA": "USD", "US": "USD", "UNITED STATES": "USD",
        "INDONESIA": "IDR", "ID": "IDR",
    }
    exp = expected.get(juris)
    if exp and exp != currency:
        return [Finding(
            code="CURR-JURIS-MISMATCH",
            severity="info",
            category="currency_mismatch_with_jurisdiction",
            summary=(
                f"Jurisdiction {juris} typically uses {exp}; cap table is in "
                f"{currency}. Confirm reporting-currency choice and document FX "
                f"convention."
            ),
            fields_referenced=("company.currency", "company.jurisdiction"),
        )]
    return []
