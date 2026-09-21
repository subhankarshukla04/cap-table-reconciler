"""Multi-snapshot timeline + N-way diff primitives (W7).

The wave-7 analyst workflow: select 2+ snapshots from a chronological
timeline → compute the cross-snapshot drift table → render side-by-side
in the HTMX UI OR export as an xlsx + pdf workpaper.

This module is the pure-compute core. No Flask, no HTML, no I/O beyond
reading the supplied CapTable objects. The engagement_routes layer
plumbs the route + permission check; the templates layer renders.

Design choice: instead of N(N-1)/2 pairwise diffs the analyst has to
glue together mentally, this module produces a SINGLE per-class row
with N value cells side-by-side. That matches the way an analyst
actually reads a chronological cap-table comparison — "did Series A
shares drift" is one question, not C(N,2) questions.

Magnitude classification (closes audit ask for visible drift cues):

  | Tier      | Trigger |
  |---|---|
  | none      | identical across all snapshots                 |
  | minor     | value moves within ±5%                         |
  | material  | value moves between 5% and 20%                 |
  | major     | value moves more than 20%, OR class added /     |
  |           | removed, OR LP variant changes, OR seniority    |
  |           | changes                                        |

The class is reported per (class_name, field) cell; the row's overall
tier is the max of its cells.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .models import CapTable, ShareClass


# ---- Tiers + thresholds ---------------------------------------------------


MINOR_FRAC = 0.05
MATERIAL_FRAC = 0.20


def _classify_pct(prior: Optional[float], current: Optional[float]) -> str:
    """Return drift tier for a numeric field."""
    if prior is None and current is None:
        return "none"
    # W9.6 / closes SD-AUD-W7-m3: cap-table numeric fields should never
    # be NaN. If a corrupt CapTable smuggles one in, surface it at the
    # diff layer instead of silently classifying as 'major'.
    import math as _math
    for v, label in ((prior, "prior"), (current, "current")):
        if v is not None and isinstance(v, float) and _math.isnan(v):
            raise ValueError(
                f"_classify_pct received NaN for {label!r} — corrupt CapTable"
            )
    if prior is None or current is None:
        # presence change is structurally material
        return "major"
    if prior == 0 and current == 0:
        return "none"
    if prior == 0:
        return "major"
    delta = abs(current - prior) / abs(prior)
    if delta < 1e-9:
        return "none"
    if delta <= MINOR_FRAC:
        return "minor"
    if delta <= MATERIAL_FRAC:
        return "material"
    return "major"


def _max_tier(tiers: list[str]) -> str:
    order = ["none", "minor", "material", "major"]
    if not tiers:
        return "none"
    return max(tiers, key=order.index)


# ---- Per-snapshot, per-class view ----------------------------------------


@dataclass
class _ClassView:
    """One share-class snapshot in the N-way grid."""
    snapshot_id: str
    class_name: Optional[str]  # None if class is absent from this snapshot
    shares_outstanding: Optional[int]
    issue_price: Optional[float]
    seniority_rank: Optional[int]
    lp_amount: Optional[float]
    lp_multiple: Optional[float]
    lp_type: Optional[str]
    lp_variant_label: Optional[str]
    anti_dilution_variant: Optional[str]
    conversion_ratio: Optional[float]


def _project_class(snap_id: str, sc: Optional[ShareClass]) -> _ClassView:
    if sc is None:
        return _ClassView(
            snapshot_id=snap_id, class_name=None,
            shares_outstanding=None, issue_price=None, seniority_rank=None,
            lp_amount=None, lp_multiple=None, lp_type=None,
            lp_variant_label=None, anti_dilution_variant=None,
            conversion_ratio=None,
        )
    lp = sc.liquidation_preference
    return _ClassView(
        snapshot_id=snap_id,
        class_name=sc.name,
        shares_outstanding=sc.shares_outstanding,
        issue_price=sc.issue_price,
        seniority_rank=sc.seniority_rank,
        lp_amount=lp.amount if lp else None,
        lp_multiple=lp.multiple if lp else None,
        lp_type=lp.type.value if lp else None,
        lp_variant_label=(
            f"{lp.multiple}x {lp.type.value}"
            + (f" cap {lp.cap_multiple}x" if lp and lp.cap_multiple else "")
        ) if lp else None,
        anti_dilution_variant=(
            sc.anti_dilution.variant.value
            if sc.anti_dilution and sc.anti_dilution.variant else None
        ),
        conversion_ratio=sc.conversion_ratio,
    )


# ---- Top-level grid -------------------------------------------------------


@dataclass
class SnapshotMeta:
    """Lightweight metadata about a snapshot for header rendering."""
    id: str
    created_at: datetime
    source_filename: Optional[str]
    created_by: str
    change_note: Optional[str] = None


@dataclass
class ClassRow:
    """One row across all N snapshots for one share class."""
    class_name: str
    views: list[_ClassView]
    field_tiers: dict[str, str] = field(default_factory=dict)
    overall_tier: str = "none"
    # First snapshot where the class appears, for "added at snapshot X" UX.
    first_seen_idx: Optional[int] = None
    last_seen_idx: Optional[int] = None


@dataclass
class TimelineDiff:
    """The full N-way diff result, ready to render."""
    snapshots: list[SnapshotMeta]
    class_rows: list[ClassRow]
    # Aggregate counters for the summary banner.
    classes_added: int = 0
    classes_removed: int = 0
    classes_changed: int = 0


def _compute_field_tier(views: list[_ClassView], field_name: str) -> str:
    """Walk the chronological sequence of values for one field across
    snapshots; report the max tier observed between consecutive non-None
    pairs. None→value transitions are 'major' (presence change)."""
    values = [getattr(v, field_name) for v in views]
    tiers = []
    for i in range(1, len(values)):
        prior = values[i - 1]
        current = values[i]
        if field_name in ("lp_variant_label", "lp_type",
                          "anti_dilution_variant"):
            # categorical: any inequality is a major event (variant change
            # matters legally; presence change is also legally material).
            # We don't try to quantify "more vs less generous".
            tiers.append("major" if prior != current else "none")
        elif field_name == "seniority_rank":
            # categorical-ish: a change in seniority always matters.
            tiers.append("major" if prior != current else "none")
        else:
            # numeric
            tiers.append(_classify_pct(prior, current))
    return _max_tier(tiers)


_NUMERIC_FIELDS = (
    "shares_outstanding", "issue_price", "lp_amount", "lp_multiple",
    "conversion_ratio",
)
_CATEGORICAL_FIELDS = (
    "lp_variant_label", "lp_type", "anti_dilution_variant", "seniority_rank",
)


def compute_timeline_diff(
    snapshot_metas: list[SnapshotMeta],
    cap_tables: list[Optional[CapTable]],
) -> TimelineDiff:
    """Build the N-way diff.

    `snapshot_metas` and `cap_tables` must be the same length; each
    `cap_tables[i]` is the parsed CapTable for `snapshot_metas[i]` (or
    None if the snapshot is redacted — those columns render as blanks).
    Both lists must be in chronological order (oldest first).
    """
    if len(snapshot_metas) != len(cap_tables):
        raise ValueError("snapshot_metas and cap_tables length mismatch")
    if len(snapshot_metas) < 2:
        raise ValueError("need at least 2 snapshots to diff")

    # Union of class names across all non-redacted snapshots, preserving
    # the order they first appeared.
    all_class_names: list[str] = []
    seen: set[str] = set()
    for ct in cap_tables:
        if ct is None:
            continue
        for sc in ct.share_classes:
            if sc.name not in seen:
                seen.add(sc.name)
                all_class_names.append(sc.name)

    class_rows: list[ClassRow] = []
    classes_added = 0
    classes_removed = 0
    classes_changed = 0
    for class_name in all_class_names:
        views: list[_ClassView] = []
        first_seen_idx: Optional[int] = None
        last_seen_idx: Optional[int] = None
        for i, ct in enumerate(cap_tables):
            sc = None
            if ct is not None:
                sc = next(
                    (s for s in ct.share_classes if s.name == class_name),
                    None,
                )
            view = _project_class(
                snap_id=snapshot_metas[i].id, sc=sc,
            )
            if sc is not None:
                if first_seen_idx is None:
                    first_seen_idx = i
                last_seen_idx = i
            views.append(view)

        field_tiers: dict[str, str] = {}
        for fld in _NUMERIC_FIELDS + _CATEGORICAL_FIELDS:
            field_tiers[fld] = _compute_field_tier(views, fld)
        # presence transitions: a None→value or value→None move is
        # already encoded by _classify_pct → 'major', but for non-numeric
        # fields we mark it explicitly.
        presence = [v.class_name is not None for v in views]
        if any(p1 != p2 for p1, p2 in zip(presence, presence[1:])):
            field_tiers["presence"] = "major"
        else:
            field_tiers["presence"] = "none"

        overall = _max_tier(list(field_tiers.values()))
        class_rows.append(ClassRow(
            class_name=class_name,
            views=views,
            field_tiers=field_tiers,
            overall_tier=overall,
            first_seen_idx=first_seen_idx,
            last_seen_idx=last_seen_idx,
        ))

        if overall != "none":
            classes_changed += 1
        # added/removed aggregate counters: class added means absent in
        # snapshot[0] and present somewhere later; removed means present
        # earlier but absent in snapshot[-1].
        if not presence[0] and any(presence[1:]):
            classes_added += 1
        if presence[0] and not presence[-1]:
            classes_removed += 1

    return TimelineDiff(
        snapshots=snapshot_metas,
        class_rows=class_rows,
        classes_added=classes_added,
        classes_removed=classes_removed,
        classes_changed=classes_changed,
    )
