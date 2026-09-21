"""Rule-pack v2026.4.0 — protective provisions / ROFR / drag-along
structured-field rules (W3.6 / closes GAP-14).

Now that CapTable carries structured ProtectiveProvision, ROFRTerms,
and DragAlongTerms fields, the rules below query them directly rather
than scraping side-letter body text. Brings total registered rules from
30 → 37.
"""

from __future__ import annotations

from .checklist import Finding
from .models import CapTable, ShareClassType
from .rule_pack import rule


# ---- Protective provisions ------------------------------------------------


@rule(
    id="G-PP-001",
    severity="warning",
    category="protective_provisions_empty",
    summary="Preferred class exists but no structured protective provisions enumerated.",
    citation="NVCA Model Charter §6 (Protective Provisions).",
    introduced_in_pack="v2026.4.0",
)
def _rule_pp_empty(cap_table: CapTable) -> list[Finding]:
    has_preferred = any(sc.type == ShareClassType.preferred for sc in cap_table.share_classes)
    if not has_preferred:
        return []
    if cap_table.protective_provisions:
        return []
    return [Finding(
        code="PP-EMPTY",
        severity="warning",
        category="protective_provisions_empty",
        summary=(
            "Preferred class exists but cap_table.protective_provisions is empty. "
            "Per NVCA §6, the protective-provisions list should be enumerated "
            "structurally — not just narrated in a side letter."
        ),
        fields_referenced=("protective_provisions",),
    )]


@rule(
    id="G-PP-002",
    severity="info",
    category="protective_provisions_supermajority_threshold",
    summary="A protective provision requires >2/3 consent — confirm voting class.",
    citation="NVCA Model Charter §6.2(b) (supermajority consent thresholds).",
    introduced_in_pack="v2026.4.0",
)
def _rule_pp_supermajority(cap_table: CapTable) -> list[Finding]:
    out = []
    for pp in cap_table.protective_provisions:
        if pp.consent_threshold_pct is not None and pp.consent_threshold_pct > 66.67:
            classes = ", ".join(pp.consenting_class_names) or "—"
            out.append(Finding(
                code=f"PP-SUPERMAJORITY-{pp.name}",
                severity="info",
                category="protective_provisions_supermajority_threshold",
                summary=(
                    f"Protective provision '{pp.name}' requires "
                    f"{pp.consent_threshold_pct:.1f}% consent from {classes}. "
                    f"Confirm in memo that the voting class is well-defined "
                    f"and the threshold is satisfiable."
                ),
                fields_referenced=(f"protective_provisions[{pp.name}].consent_threshold_pct",),
            ))
    return out


@rule(
    id="G-PP-003",
    severity="warning",
    category="protective_provisions_consenting_class_missing",
    summary="Protective provision lists no consenting class — meaningless without one.",
    citation="NVCA Model Charter §6 (requires named consenting class).",
    introduced_in_pack="v2026.4.0",
)
def _rule_pp_no_consenting_class(cap_table: CapTable) -> list[Finding]:
    out = []
    for pp in cap_table.protective_provisions:
        if not pp.consenting_class_names:
            out.append(Finding(
                code=f"PP-NO-CONSENTER-{pp.name}",
                severity="warning",
                category="protective_provisions_consenting_class_missing",
                summary=(
                    f"Protective provision '{pp.name}' has no consenting_class_names. "
                    f"A consent threshold without a defined voting class is "
                    f"unenforceable; confirm the charter language."
                ),
                fields_referenced=(f"protective_provisions[{pp.name}].consenting_class_names",),
            ))
    return out


# ---- ROFR / ROFO ---------------------------------------------------------


@rule(
    id="G-ROFR-002",
    severity="info",
    category="rofr_notice_period_short",
    summary="ROFR notice period < 15 days is unusually short.",
    citation="NVCA Model ROFR §2.2; standard 30/60-day windows.",
    introduced_in_pack="v2026.4.0",
)
def _rule_rofr_short_notice(cap_table: CapTable) -> list[Finding]:
    rt = cap_table.rofr_terms
    if rt is None or rt.notice_period_days is None:
        return []
    if rt.notice_period_days < 15:
        return [Finding(
            code="ROFR-SHORT-NOTICE",
            severity="info",
            category="rofr_notice_period_short",
            summary=(
                f"ROFR notice_period_days={rt.notice_period_days} is below the "
                f"15-day common floor. Confirm the analyst's intent — this may "
                f"be a transcription error from the charter."
            ),
            fields_referenced=("rofr_terms.notice_period_days",),
        )]
    return []


# ---- Drag-along ----------------------------------------------------------


@rule(
    id="G-DRAG-002",
    severity="warning",
    category="drag_along_threshold_atypical",
    summary="Drag-along threshold outside 50-75% range is unusual.",
    citation="NVCA Model Voting Agreement §3; AICPA Cheap Stock §2.22.",
    introduced_in_pack="v2026.4.0",
)
def _rule_drag_threshold_band(cap_table: CapTable) -> list[Finding]:
    dt = cap_table.drag_along_terms
    if dt is None or dt.threshold_pct is None:
        return []
    if dt.threshold_pct < 50 or dt.threshold_pct > 75:
        return [Finding(
            code="DRAG-THRESHOLD-ATYPICAL",
            severity="warning",
            category="drag_along_threshold_atypical",
            summary=(
                f"Drag-along threshold={dt.threshold_pct:.1f}% is outside the "
                f"50-75% common range. Confirm the threshold and the class "
                f"composition it applies to."
            ),
            fields_referenced=("drag_along_terms.threshold_pct",),
        )]
    return []


@rule(
    id="G-DRAG-003",
    severity="warning",
    category="drag_along_classes_empty",
    summary="Drag-along terms present but no drag_classes named.",
    citation="NVCA Model Voting Agreement §3.1 (must name dragged class).",
    introduced_in_pack="v2026.4.0",
)
def _rule_drag_classes_empty(cap_table: CapTable) -> list[Finding]:
    dt = cap_table.drag_along_terms
    if dt is None:
        return []
    if not dt.drag_classes:
        return [Finding(
            code="DRAG-CLASSES-EMPTY",
            severity="warning",
            category="drag_along_classes_empty",
            summary=(
                "drag_along_terms exists but drag_classes is empty. Per NVCA "
                "§3.1, the dragged class list must be named explicitly."
            ),
            fields_referenced=("drag_along_terms.drag_classes",),
        )]
    return []


# ---- Cross-check ---------------------------------------------------------


@rule(
    id="G-XREF-001",
    severity="info",
    category="rofr_drag_inconsistent",
    summary="Drag-along present but no ROFR/ROFO terms — uncommon pairing.",
    citation="NVCA Model Voting Agreement structure (ROFR + drag typically co-exist).",
    introduced_in_pack="v2026.4.0",
)
def _rule_rofr_drag_consistency(cap_table: CapTable) -> list[Finding]:
    if cap_table.drag_along_terms is not None and cap_table.rofr_terms is None:
        return [Finding(
            code="XREF-DRAG-NO-ROFR",
            severity="info",
            category="rofr_drag_inconsistent",
            summary=(
                "Drag-along terms present but ROFR/ROFO terms are missing. "
                "These typically co-exist in NVCA-style voting agreements; "
                "confirm whether the ROFR was carved out intentionally."
            ),
            fields_referenced=("drag_along_terms", "rofr_terms"),
        )]
    return []
