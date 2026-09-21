"""Big-4 PDF audit memo via WeasyPrint (SYSTEM_SPEC §3.4, §8.16).

Renders the audit memo as a paginated PDF instead of Markdown. Big 4
reviewers do not accept Markdown deliverables. The PDF includes:

  - Cover sheet with engagement metadata + memo version + named reviewer slot
  - Per-page header/footer (engagement id, page X of N, confidentiality stamp)
  - Capital-structure table, findings table, breakpoints table
  - Methodology disclosures
  - Explicit ANALYST INPUT REQUIRED blocks
  - Signature block (prepared by / reviewed by)
  - Provenance appendix citing every rule applied

Refusals:
  - PDF cannot be generated when the bound snapshot has unresolved blocker
    findings (`pdf-blockers-outstanding`).
  - PDF cannot be generated without a named reviewer (`pdf-no-reviewer`).

EVELYN-BLOCKED:
  - Qapita house-style overrides: typeface, color palette, cover-page layout.
    The current template uses a generic Big-4-defensible style. Replace
    `templates/memo/base.html` CSS when Qapita's template lands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

try:
    from weasyprint import HTML
    _WEASY_AVAILABLE = True
except ImportError:  # pragma: no cover
    HTML = None  # type: ignore[assignment]
    _WEASY_AVAILABLE = False

from .checklist import Finding
from .models import CapTable, LPType
from .rule_pack import RulePack, finding_provenance_map, rule_metadata
from .waterfall import WaterfallResult


# ---- Errors ----------------------------------------------------------------


class PDFMemoError(Exception):
    error_code: str = "pdf-error"
    http_status: int = 400


class PDFBlockersOutstanding(PDFMemoError):
    error_code = "pdf-blockers-outstanding"
    http_status = 409


class PDFNoReviewer(PDFMemoError):
    error_code = "pdf-no-reviewer"
    http_status = 400


@dataclass(frozen=True)
class ReviewerInfo:
    reviewer_name: str
    preparer: Optional[str] = None


@dataclass(frozen=True)
class PDFInputs:
    cap_table: CapTable
    waterfall: WaterfallResult
    findings: list[Finding]
    resolutions: list[dict]  # [{"finding_code", "decision_summary", "citation", "resolved_by"}]
    reviewer: Optional[ReviewerInfo]
    engagement_id: Optional[str] = None
    pack: Optional[RulePack] = None
    engine_version: Optional[str] = None
    memo_version: str = "1.0"
    standard_of_value: str = "ifrs13"
    # W3.1: optional subsequent-events rollup. When supplied, the memo
    # renders a "Subsequent Events" section auto-populated from the
    # engagement's snapshot chain.
    subsequent_events: Optional[object] = None
    # W8.11: optional N-way snapshot drift table. When supplied (typically
    # the result of `compute_timeline_diff` over the engagement's
    # snapshot chain), the memo renders a "Snapshot Drift" section with
    # the magnitude-tiered per-class table the analyst sees in the HTMX
    # diff page.
    timeline_diff: Optional[object] = None
    # SD-AUD-M1: when set, the cover-sheet timestamp is pinned to this value
    # (typically engagement.created_at) instead of wall-clock. Makes the PDF
    # bit-stable per engagement state, strictly stronger than spec §8.10
    # carve-out for the cover timestamp.
    generated_at: Optional[datetime] = None


_STANDARD_LABELS = {
    "ifrs13": "IFRS 13 Fair Value Measurement",
    "asc820": "ASC 820 Fair Value Measurement",
    "sec409a": "Section 409A Internal Revenue Code",
    "ifrs2": "IFRS 2 Share-Based Payment",
}


_NUMERIC_RE = re.compile(r"[^\d.\-]")


def _money(v: Optional[float], symbol: str) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1_000_000_000:
        return f"{symbol}{v/1_000_000_000:,.2f}B"
    if abs(v) >= 1_000_000:
        return f"{symbol}{v/1_000_000:,.2f}M"
    if abs(v) >= 1_000:
        return f"{symbol}{v/1_000:,.0f}K"
    return f"{symbol}{v:,.2f}"


def _commas(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v)


def _describe_lp(lp) -> str:
    if lp is None:
        return "—"
    base = f"{lp.multiple}x {lp.type.value.replace('_', ' ')}"
    if lp.cap_multiple:
        base += f" (cap {lp.cap_multiple}x)"
    return base


def _ensure_eligible(inputs: PDFInputs) -> None:
    """Apply SYSTEM_SPEC §3.4 refusals before rendering."""
    blockers = [f for f in inputs.findings if f.severity == "blocker"]
    if blockers:
        unresolved = {f.code for f in blockers}
        for r in inputs.resolutions:
            unresolved.discard(r.get("finding_code"))
        if unresolved:
            raise PDFBlockersOutstanding(
                f"Cannot generate PDF memo while {len(unresolved)} blocker finding(s) "
                f"remain unresolved: {sorted(unresolved)}"
            )
    if inputs.reviewer is None or not inputs.reviewer.reviewer_name.strip():
        raise PDFNoReviewer(
            "PDF memo requires a named reviewer per SYSTEM_SPEC §3.4. "
            "Pass a ReviewerInfo with a non-empty reviewer_name."
        )


def _build_context(inputs: PDFInputs) -> dict:
    ct = inputs.cap_table
    wf = inputs.waterfall
    sym = ct.company.currency_symbol

    cap_structure_rows = []
    for sc in ct.share_classes:
        cap_structure_rows.append({
            "name": sc.name,
            "type": sc.type.value,
            "shares": _commas(sc.shares_outstanding),
            "pps": _money(sc.issue_price, sym) if sc.issue_price else "—",
            "issue_date": sc.issue_date.isoformat() if sc.issue_date else "—",
            "seniority": (
                f"{sc.seniority_rank}.{sc.seniority_sub_rank}"
                if sc.type.value == "preferred" else "—"
            ),
            "lp": _describe_lp(sc.liquidation_preference),
            "anti_dilution": (
                sc.anti_dilution.variant.value.replace("_", " ")
                if sc.anti_dilution and sc.anti_dilution.variant else "—"
            ),
        })

    breakpoints = []
    for bp in wf.breakpoints:
        breakpoints.append({
            "id": bp.id,
            "value": _money(bp.value, sym),
            "event": bp.event,
        })

    # W9.1: build a finding.code → rule_id + citation map so each row in
    # the findings table can show "why" (rule citation + emitting
    # rule_id). Cheap re-run of the pack against the head cap table.
    # SD-AUD-W9-M3: pass jurisdiction so cross-jurisdiction code reuse
    # (two rules in different jurisdictions emitting the same code
    # template) doesn't last-write-win on the dict.
    try:
        jurisdiction = (
            ct.company.jurisdiction if ct.company and ct.company.jurisdiction
            else None
        )
        prov_map = finding_provenance_map(
            ct, pack=inputs.pack, engagement_jurisdiction=jurisdiction,
        )
    except Exception:
        prov_map = {}

    findings_ctx = []
    blocker_count = warning_count = info_count = 0
    for f in inputs.findings:
        prov = prov_map.get(f.code, {})
        findings_ctx.append({
            "code": f.code,
            "severity": f.severity,
            "summary": f.summary,
            "fields_str": ", ".join(f.fields_referenced) if f.fields_referenced else "",
            "rule_id": prov.get("rule_id"),  # W9.1
            "citation": prov.get("citation"),
            "pack_version": prov.get("pack_version"),
        })
        if f.severity == "blocker": blocker_count += 1
        elif f.severity == "warning": warning_count += 1
        elif f.severity == "info": info_count += 1
    findings_summary = (
        f"{blocker_count} blocker(s), {warning_count} warning(s), {info_count} info note(s)."
    )

    # Methodology disclosures (mirrors src/audit_memo.py logic)
    methodology = []
    capped = [
        sc for sc in ct.preferred_classes_by_seniority
        if sc.liquidation_preference
        and sc.liquidation_preference.type == LPType.participating_capped
    ]
    if capped:
        names = ", ".join(sc.name for sc in capped)
        methodology.append(
            f"Participating-with-cap classes: {names}. Each capped class produces "
            f"additional waterfall breakpoints (cap-reach, junior-converts, "
            f"pure-converts). Each is a separate strike for any OPM Backsolve."
        )
    ratchet = [
        sc for sc in ct.preferred_classes_by_seniority
        if sc.anti_dilution and sc.anti_dilution.variant
        and sc.anti_dilution.variant.value == "full_ratchet"
    ]
    if ratchet:
        names = ", ".join(sc.name for sc in ratchet)
        methodology.append(
            f"Full-ratchet anti-dilution: {names}. Confirm trigger status. Where "
            f"triggered, the cap table reflects post-trigger adjusted share counts."
        )
    dual = [sc for sc in ct.share_classes if sc.voting_differential]
    if dual:
        names = ", ".join(sc.name for sc in dual)
        methodology.append(
            f"Dual-class voting: {names}. Per VIMA/Cyril Amarchand convention, "
            f"identical-economic dual-class structures are modeled as one "
            f"economic class for waterfall purposes."
        )

    # Provenance: list citations for every rule in the bound pack.
    # W3-AUDIT B2: previous version parsed finding.code with a regex that
    # only matched G-XXX-NNN. The wave-3 rules (PP-EMPTY, DRAG-CLASSES-
    # EMPTY, XREF-DRAG-NO-ROFR, etc.) use different code shapes and
    # never appeared in the appendix. Enumerate from the pack instead;
    # the appendix is now complete and rule-pack-version stable.
    from .rule_pack import head_pack as _head_pack, rule_metadata as _rm
    provenance = []
    pack = inputs.pack or _head_pack()
    for rid in pack.rule_ids:
        meta = _rm(rid)
        if meta is None:
            continue
        provenance.append({"id": rid, "citation": meta.citation})

    # W3.1: subsequent-events section context
    se = inputs.subsequent_events
    se_by_category = None
    if se is not None:
        from .subsequent_events import group_events_by_category
        se_by_category = group_events_by_category(se)

    return {
        "company": ct.company,
        "cap_structure_rows": cap_structure_rows,
        "total_shares": _commas(ct.total_fully_diluted_for_waterfall),
        "lp_total": _money(wf.lp_total, sym),
        "findings": findings_ctx,
        "findings_summary": findings_summary,
        "resolutions": inputs.resolutions,
        "breakpoints": breakpoints,
        "methodology_disclosures": methodology,
        "reviewer": inputs.reviewer.__dict__ if inputs.reviewer else None,
        "engagement": {"id": inputs.engagement_id} if inputs.engagement_id else None,
        "standard_of_value_label": _STANDARD_LABELS.get(
            inputs.standard_of_value, inputs.standard_of_value
        ),
        "pack_version": inputs.pack.version if inputs.pack else None,
        "engine_version": inputs.engine_version,
        "memo_version": inputs.memo_version,
        "generated_at": (
            inputs.generated_at.astimezone(timezone.utc)
            if inputs.generated_at is not None
            else datetime.now(timezone.utc)
        ).strftime("%Y-%m-%d %H:%M UTC"),
        "provenance": provenance,
        "subsequent_events": se,
        "subsequent_events_by_category": se_by_category,
        # W8.11: pass through the N-way drift table.
        "timeline_diff": inputs.timeline_diff,
        "analyst_placeholder": lambda what: f"[ANALYST: {what}]",
    }


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "memo"


def render_pdf_memo(inputs: PDFInputs) -> bytes:
    """Render the audit memo to PDF bytes. Raises PDFMemoError subclasses
    if refusal conditions apply."""
    _ensure_eligible(inputs)
    if not _WEASY_AVAILABLE:  # pragma: no cover
        raise PDFMemoError(
            "WeasyPrint not installed. pip install weasyprint to enable PDF memos."
        )

    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("base.html")
    html = template.render(**_build_context(inputs))
    return HTML(string=html).write_pdf()


def render_diff_workpaper_pdf(engagement, diff, generated_at=None) -> bytes:
    """W8.12: render the N-way snapshot diff as a stand-alone PDF
    workpaper (cover sheet + drift table). Pure function — caller
    supplies the engagement headers + the TimelineDiff produced by
    `compute_timeline_diff`. `generated_at` defaults to the engagement's
    created_at so the cover timestamp is byte-stable per engagement
    state (mirrors SD-AUD-M1)."""
    if not _WEASY_AVAILABLE:  # pragma: no cover
        raise PDFMemoError(
            "WeasyPrint not installed. pip install weasyprint to enable PDF memos."
        )
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    if generated_at is None:
        generated_at = engagement.created_at
    ts = generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    template = env.get_template("diff.html")
    html = template.render(
        engagement=engagement, diff=diff, generated_at=ts,
    )
    return HTML(string=html).write_pdf()


def render_pdf_memo_html(inputs: PDFInputs) -> str:
    """Return the rendered HTML (used by tests to inspect structure without
    needing the WeasyPrint native deps in CI)."""
    _ensure_eligible(inputs)
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("base.html")
    return template.render(**_build_context(inputs))
