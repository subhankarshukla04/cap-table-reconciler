"""Rule-pack v2026.6.0 — depth pack (W5.6).

10 more rules pushing total to 60:
  India FEMA pricing-floor depth (3): IN-FEMA-FCY-PRICE-FLOOR,
    IN-FEMA-DOWNROUND-CONSIDERATION, IN-CCPS-CONVERSION-WINDOW
  Singapore IRAS (2): SG-IRAS-DEEMED-CONSIDERATION, SG-IRAS-FY-BOUNDARY
  US §409A specifics (2): US-409A-PRESUMED-REASONABLENESS-LAPSE,
    US-409A-MATERIAL-EVENT
  AICPA Cheap Stock §4 OPM allocation triggers (2): AICPA-OPM-COMMON-NEAR-ZERO,
    AICPA-OPM-DEEP-OTM-PREFERRED
  Convertible mechanics (1): CONV-NOTE-MATURITY-PAST

Cross-cutting determinism rule (W4-AUDIT §10.6): no rule uses
date.today(); all date comparisons anchor against
cap_table.company.valuation_date or share-class issue_date.
"""

from __future__ import annotations

from .checklist import Finding
from .models import CapTable, LPType, ShareClassType
from .rule_pack import rule


# ---- India FEMA depth ------------------------------------------------------


@rule(
    id="G-IN-002",
    severity="warning",
    category="india_fema_fcy_price_floor",
    summary=(
        "India + foreign currency on a preferred class — FEMA pricing-floor "
        "discipline applies."
    ),
    citation="RBI Master Direction on Foreign Investment §B.7; FEMA 20(R).",
    jurisdictions=("IN", "INDIA"),
    introduced_in_pack="v2026.6.0",
)
def _rule_in_fema_fcy(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "INDIA" not in juris and juris != "IN":
        return []
    currency = (cap_table.company.currency or "").upper()
    if currency in ("INR", ""):
        return []
    # Indian company holding preferred in foreign currency → FEMA §B.7
    # pricing floor (must price >= fair value).
    has_preferred = any(
        sc.type == ShareClassType.preferred for sc in cap_table.share_classes
    )
    if not has_preferred:
        return []
    return [Finding(
        code="IN-FEMA-FCY-PRICE-FLOOR",
        severity="warning",
        category="india_fema_fcy_price_floor",
        summary=(
            f"India-incorporated company with preferred class denominated in "
            f"{currency}. RBI FEMA §B.7 pricing-floor rules require issue "
            f"price >= fair value per registered valuer's DCF / NAV / equivalent. "
            f"Confirm the latest FC-GPR filing references a fair-value report."
        ),
        fields_referenced=("company.jurisdiction", "company.currency"),
    )]


@rule(
    id="G-IN-003",
    severity="warning",
    category="india_fema_downround_consideration",
    summary=(
        "India + later round at lower PPS — FEMA fair-value rules constrain "
        "downward repricing of foreign-held shares."
    ),
    citation="RBI Master Direction on Foreign Investment §B.8; FEMA 20(R) Sch 1.",
    jurisdictions=("IN", "INDIA"),
    introduced_in_pack="v2026.6.0",
)
def _rule_in_fema_downround(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "INDIA" not in juris and juris != "IN":
        return []
    priced = sorted(
        ((sc.issue_date, sc.issue_price, sc.name)
         for sc in cap_table.share_classes
         if sc.type == ShareClassType.preferred
         and sc.issue_date is not None and sc.issue_price is not None),
        key=lambda t: t[0],
    )
    seen_max = 0.0
    out = []
    for d, p, name in priced:
        if p < seen_max - 1e-9:
            out.append(Finding(
                code=f"IN-FEMA-DOWNROUND-{name}",
                severity="warning",
                category="india_fema_downround_consideration",
                summary=(
                    f"India jurisdiction: {name} at PPS {p} is below prior max "
                    f"PPS {seen_max}. Confirm FEMA fair-value compliance for "
                    f"any foreign-held tranche in this round (downward "
                    f"repricing requires valuation justification)."
                ),
                fields_referenced=(f"share_classes[{name}].issue_price",),
            ))
        if p > seen_max:
            seen_max = p
    return out


@rule(
    id="G-IN-004",
    severity="info",
    category="india_ccps_conversion_window",
    summary=(
        "India CCPS / CCD — confirm conversion window (typically 18-20 yrs) "
        "is recorded against the security."
    ),
    citation="RBI Master Direction §B.6; Companies Act §43.",
    jurisdictions=("IN", "INDIA"),
    introduced_in_pack="v2026.6.0",
)
def _rule_in_ccps_window(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "INDIA" not in juris and juris != "IN":
        return []
    out = []
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred:
            continue
        subtype = (sc.instrument_subtype or "").upper()
        if "CCPS" in subtype or "CCD" in subtype:
            note = (sc.note or "").lower()
            if "convert" not in note and "yr" not in note and "year" not in note:
                out.append(Finding(
                    code=f"IN-CCPS-CONV-WINDOW-{sc.name}",
                    severity="info",
                    category="india_ccps_conversion_window",
                    summary=(
                        f"India CCPS/CCD ({sc.name}) — Companies Act §43 caps "
                        f"the conversion window. Confirm the trigger (rounds, "
                        f"IPO, time horizon) is recorded against the security."
                    ),
                    fields_referenced=(
                        f"share_classes[{sc.name}].instrument_subtype",
                        f"share_classes[{sc.name}].note",
                    ),
                ))
    return out


# ---- Singapore IRAS --------------------------------------------------------


@rule(
    id="G-SG-001",
    severity="info",
    category="sg_iras_deemed_consideration",
    summary=(
        "Singapore-incorporated company — confirm IRAS deemed-consideration "
        "rules applied to share issuance below fair value."
    ),
    citation="IRAS e-Tax Guide on Stock Options & Awards §3.4; ITA s.10G.",
    jurisdictions=("SG", "SINGAPORE"),
    introduced_in_pack="v2026.6.0",
)
def _rule_sg_iras(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "SINGAPORE" not in juris and juris != "SG":
        return []
    return [Finding(
        code="SG-IRAS-DEEMED",
        severity="info",
        category="sg_iras_deemed_consideration",
        summary=(
            "Singapore jurisdiction detected. IRAS e-Tax §3.4 deemed-"
            "consideration rules apply where shares are issued below fair "
            "value (founders, employees, sweat-equity). Confirm any below-"
            "FV issuance has a corresponding IRAS disclosure."
        ),
        fields_referenced=("company.jurisdiction",),
    )]


@rule(
    id="G-SG-002",
    severity="info",
    category="sg_iras_fy_boundary",
    summary=(
        "Singapore + valuation date near IRAS FY boundary (Mar 31) — confirm "
        "alignment with the financial-year-end for reporting."
    ),
    citation="IRAS Year of Assessment guidance.",
    jurisdictions=("SG", "SINGAPORE"),
    introduced_in_pack="v2026.6.0",
)
def _rule_sg_fy_boundary(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if "SINGAPORE" not in juris and juris != "SG":
        return []
    vd = cap_table.company.valuation_date
    if vd is None:
        return []
    # FY-end is typically Mar 31 in SG; flag valuation dates within 30
    # days of that boundary.
    distance_to_mar31 = min(
        abs((vd.replace(month=3, day=31) - vd).days),
        abs((vd.replace(month=3, day=31).replace(year=vd.year + 1) - vd).days),
    )
    if distance_to_mar31 > 30:
        return []
    return [Finding(
        code="SG-IRAS-FY-BOUNDARY",
        severity="info",
        category="sg_iras_fy_boundary",
        summary=(
            f"Singapore valuation date {vd.isoformat()} is within 30 days of "
            f"the Mar-31 IRAS FY boundary. Confirm whether the valuation aligns "
            f"with the YA reporting year-end."
        ),
        fields_referenced=("company.valuation_date",),
    )]


# ---- US §409A specifics ----------------------------------------------------


@rule(
    id="G-US-001",
    severity="warning",
    category="us_409a_presumed_reasonableness_stale",
    summary=(
        "US Delaware preferred + valuation date >12 months after most recent "
        "priced round — §409A presumed reasonableness lapses."
    ),
    citation=(
        "Treasury Reg §1.409A-1(b)(5)(iv)(B)(2) — 12-month presumption window; "
        "AICPA Cheap Stock §3.7."
    ),
    jurisdictions=("US", "US-DE", "DELAWARE"),
    introduced_in_pack="v2026.6.0",
)
def _rule_us_409a_stale(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if not any(tag in juris for tag in ("US", "DELAWARE")):
        return []
    vd = cap_table.company.valuation_date
    if vd is None:
        return []
    priced_dates = [
        sc.issue_date for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred and sc.issue_date is not None
    ]
    if not priced_dates:
        return []
    most_recent = max(priced_dates)
    gap = (vd - most_recent).days
    if gap > 365:
        return [Finding(
            code="US-409A-PRESUMPTION-LAPSED",
            severity="warning",
            category="us_409a_presumed_reasonableness_stale",
            summary=(
                f"Valuation date {vd.isoformat()} is {gap // 30} months after "
                f"most recent priced round ({most_recent.isoformat()}). The "
                f"Treas. Reg. §1.409A-1(b)(5)(iv)(B)(2) 12-month presumption "
                f"of reasonableness no longer applies. The memo must explicitly "
                f"justify the valuation methodology."
            ),
            fields_referenced=("company.valuation_date",),
        )]
    return []


@rule(
    id="G-US-002",
    severity="info",
    category="us_409a_material_event_reminder",
    summary=(
        "US + recent down-round detected — §409A material-event re-valuation "
        "expected."
    ),
    citation="Treas. Reg §1.409A-1(b)(5)(iv)(B)(1); AICPA Cheap Stock §3.8.",
    jurisdictions=("US", "US-DE", "DELAWARE"),
    introduced_in_pack="v2026.6.0",
)
def _rule_us_material_event(cap_table: CapTable) -> list[Finding]:
    juris = (cap_table.company.jurisdiction or "").upper()
    if not any(tag in juris for tag in ("US", "DELAWARE")):
        return []
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
            return [Finding(
                code="US-409A-MATERIAL-EVENT",
                severity="info",
                category="us_409a_material_event_reminder",
                summary=(
                    f"US jurisdiction + down-round detected at {name} "
                    f"({d.isoformat()}, PPS {p} below prior max {seen_max}). "
                    f"§1.409A-1(b)(5)(iv)(B)(1) treats a down-round as a "
                    f"material event requiring re-valuation; confirm the memo "
                    f"date is at or after this event."
                ),
                fields_referenced=(f"share_classes[{name}].issue_price",),
            )]
        if p > seen_max:
            seen_max = p
    return []


# ---- AICPA OPM allocation triggers ----------------------------------------


@rule(
    id="G-AICPA-003",
    severity="info",
    category="aicpa_opm_common_near_zero",
    summary=(
        "Aggregate LP overhang exceeds 80% of PPS-implied EV proxy — common "
        "stock is deep-OTM, OPM strongly indicated."
    ),
    citation="AICPA Cheap Stock §4.16 (OPM common-stock allocation triggers).",
    introduced_in_pack="v2026.6.0",
)
def _rule_aicpa_opm_common_near_zero(cap_table: CapTable) -> list[Finding]:
    lp_total = sum(
        sc.liquidation_preference.amount for sc in cap_table.share_classes
        if sc.liquidation_preference is not None
    )
    priced = [
        sc for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred
        and sc.issue_price is not None and sc.issue_price > 0
    ]
    if not priced:
        return []
    latest = max(priced, key=lambda sc: sc.issue_date or __import__("datetime").date.min)
    pps = latest.issue_price
    total_shares = cap_table.total_fully_diluted_for_waterfall
    ev_proxy = pps * total_shares
    if ev_proxy <= 0:
        return []
    ratio = lp_total / ev_proxy
    if ratio > 0.8:
        return [Finding(
            code="AICPA-OPM-COMMON-NEAR-ZERO",
            severity="info",
            category="aicpa_opm_common_near_zero",
            summary=(
                f"LP overhang ({lp_total:,.0f}) is {ratio:.0%} of PPS-implied "
                f"EV proxy. Per AICPA §4.16 the common stock is deep-OTM; OPM "
                f"or PWERM with explicit IPO-scenario allocation is the "
                f"recommended fair-value methodology."
            ),
            fields_referenced=("share_classes[*].liquidation_preference",),
        )]
    return []


@rule(
    id="G-AICPA-004",
    severity="info",
    category="aicpa_opm_deep_otm_preferred",
    summary=(
        "Senior preferred LP exceeds PPS-implied EV — junior preferred deep "
        "out-of-the-money, OPM allocation required."
    ),
    citation="AICPA Cheap Stock §4.18 (OPM allocation across classes).",
    introduced_in_pack="v2026.6.0",
)
def _rule_aicpa_opm_deep_otm(cap_table: CapTable) -> list[Finding]:
    preferred = [
        sc for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred
        and sc.liquidation_preference is not None
    ]
    if len(preferred) < 2:
        return []
    most_senior = min(preferred, key=lambda sc: sc.seniority_rank)
    priced = [
        sc for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred
        and sc.issue_price is not None and sc.issue_price > 0
    ]
    if not priced:
        return []
    pps = max(priced, key=lambda sc: sc.issue_date or __import__("datetime").date.min).issue_price
    total_shares = cap_table.total_fully_diluted_for_waterfall
    ev_proxy = pps * total_shares
    senior_lp = most_senior.liquidation_preference.amount
    if ev_proxy > 0 and senior_lp > ev_proxy:
        return [Finding(
            code=f"AICPA-OPM-JUNIOR-OTM-{most_senior.name}",
            severity="info",
            category="aicpa_opm_deep_otm_preferred",
            summary=(
                f"Most-senior preferred {most_senior.name} carries LP "
                f"{senior_lp:,.0f} alone exceeding the PPS-implied EV proxy "
                f"({ev_proxy:,.0f}). Junior preferred + common are deep-OTM; "
                f"per AICPA §4.18 a backsolve-OPM allocation is required."
            ),
            fields_referenced=(
                f"share_classes[{most_senior.name}].liquidation_preference",
            ),
        )]
    return []


# ---- Convertible mechanics ------------------------------------------------


@rule(
    id="G-CONV-002",
    severity="warning",
    category="convertible_note_maturity_past",
    summary=(
        "Convertible note maturity before valuation date — note is overdue, "
        "treat as either converted or in default."
    ),
    citation="AICPA Cheap Stock §3.32 (convertible-note lifecycle).",
    introduced_in_pack="v2026.6.0",
)
def _rule_conv_maturity(cap_table: CapTable) -> list[Finding]:
    vd = cap_table.company.valuation_date
    if vd is None:
        return []
    out = []
    for n in cap_table.convertible_notes_outstanding:
        # Convertible-note model doesn't carry a maturity date directly
        # in the canonical schema today — use issue_date + 24 months as
        # a heuristic ceiling for the typical SAFE/convertible window.
        if n.issue_date is None:
            continue
        # 730 days ≈ 24 months
        if (vd - n.issue_date).days > 730:
            out.append(Finding(
                code=f"CONV-MATURITY-PAST-{n.id}",
                severity="warning",
                category="convertible_note_maturity_past",
                summary=(
                    f"Convertible note {n.id} issued {n.issue_date.isoformat()}, "
                    f"more than 24 months before the valuation date "
                    f"({vd.isoformat()}). Standard convertible windows are "
                    f"12-24 months; confirm the note has converted, been "
                    f"extended, or is in default."
                ),
                fields_referenced=(
                    f"convertible_notes_outstanding[{n.id}].issue_date",
                ),
            ))
    return out
