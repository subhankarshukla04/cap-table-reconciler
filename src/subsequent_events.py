"""Subsequent-events memo section (W3.1).

Computes a structured "subsequent events" rollup for the audit memo by
diffing the engagement's first snapshot against its current head. Reuses
src/structured_diff.diff_snapshots and groups the FieldDiffs into
human-readable categories that map to memo-section bullet points.

This also addresses audit M7 (memo loses prior resolutions): when the
analyst re-uploads and creates a new head snapshot, all prior
resolutions are surfaced in the subsequent-events block via the
engagement's full resolution history — not lost to the new snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .engagement import EngagementStore, Resolution
from .rule_pack import RulePack
from .structured_diff import FieldDiff, StructuredDiff, diff_snapshots


@dataclass(frozen=True)
class SubsequentEvent:
    category: str
    description: str
    source_snapshot_id: str
    field_path: Optional[str] = None
    rule_implications: tuple[str, ...] = ()


@dataclass
class SubsequentEventsRollup:
    engagement_id: str
    original_snapshot_id: Optional[str]
    head_snapshot_id: Optional[str]
    events: list[SubsequentEvent] = field(default_factory=list)
    historical_resolutions: list[Resolution] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.events) or bool(self.historical_resolutions)


def _classify(diff: FieldDiff) -> str:
    """Map a FieldDiff path to a memo-bucket category.

    W3-AUDIT M2: added classifications for the new structured fields
    introduced in W3.6 (protective_provisions, rofr_terms,
    drag_along_terms) so they don't all land in "Other".
    """
    p = diff.path
    if p == "$rule_pack.findings_delta":
        return "Rule-pack findings delta"
    if "protective_provisions" in p:
        return "Protective provisions"
    if "rofr_terms" in p:
        return "ROFR / ROFO"
    if "drag_along_terms" in p:
        return "Drag-along"
    if "liquidation_preference" in p:
        return "Liquidation preference"
    if ".shares_outstanding" in p:
        return "Share count"
    if ".issue_price" in p:
        return "Issue price"
    if ".conversion_ratio" in p:
        return "Conversion ratio (anti-dilution)"
    if ".anti_dilution" in p:
        return "Anti-dilution variant"
    if ".voting_differential" in p:
        # M-5 fix (compiled system audit): voting-rights changes are
        # consequential and must not be buried in "Share-class structure".
        return "Voting / governance"
    if "share_classes[" in p and (".name" in p):
        return "Class rename"
    if "share_classes[" in p:
        return "Share-class structure"
    if "side_letters[" in p:
        return "Side letters"
    if "safes_outstanding" in p or "convertible_notes" in p or "warrants_outstanding" in p:
        return "Convertibles / warrants"
    if "company." in p:
        return "Company metadata"
    return "Other"


def _describe(diff: FieldDiff) -> str:
    if diff.change_type == "added":
        return f"Added: {diff.path} = {diff.new_value!r}"
    if diff.change_type == "removed":
        return f"Removed: {diff.path} (was {diff.old_value!r})"
    if diff.change_type == "renamed":
        return f"Renamed {diff.old_value!r} → {diff.new_value!r}"
    return f"Changed: {diff.path}: {diff.old_value!r} → {diff.new_value!r}"


def compute_subsequent_events(
    store: EngagementStore,
    engagement_id: str,
    pack: Optional[RulePack] = None,
) -> SubsequentEventsRollup:
    """Build the rollup for an engagement.

    Walks the engagement's snapshot chain head-to-genesis to find the
    original (first) snapshot, diffs it against the current head, and
    collects every resolution across all snapshots in the chain.
    """
    eng = store.get_engagement(engagement_id)
    snapshots = store.list_snapshots(engagement_id)
    if not snapshots:
        return SubsequentEventsRollup(
            engagement_id=engagement_id,
            original_snapshot_id=None,
            head_snapshot_id=None,
        )

    # M-1 fix (compiled system audit): head is the engagement's recorded
    # head_snapshot_id, NOT list[-1]. Two snapshots with identical
    # created_at would sort by UUID-lex which is unrelated to chain
    # order; trusting head_snapshot_id is authoritative. Walk
    # superseded_by backward from head to find the original.
    head = store.get_snapshot(eng.head_snapshot_id) if eng.head_snapshot_id else snapshots[-1]
    by_id = {s.id: s for s in snapshots}
    # Walk back to original: a snapshot is original if it has no parent
    # (no other snapshot points to it via superseded_by). Build the
    # parent map and walk from head backward.
    parent_of: dict[str, str] = {}
    for s in snapshots:
        if s.superseded_by:
            parent_of[s.superseded_by] = s.id
    cursor = head.id
    while cursor in parent_of:
        cursor = parent_of[cursor]
    original = by_id.get(cursor, snapshots[0])

    rollup = SubsequentEventsRollup(
        engagement_id=engagement_id,
        original_snapshot_id=original.id,
        head_snapshot_id=head.id,
    )

    # Collect resolutions across the entire chain — closes audit M7.
    for snap in snapshots:
        for res in store.list_resolutions(snap.id):
            rollup.historical_resolutions.append(res)

    if original.id == head.id:
        # No subsequent snapshots → no diff events; only resolutions.
        return rollup

    original_ct = original.load_cap_table()
    head_ct = head.load_cap_table()
    if original_ct is None or head_ct is None:
        # One side is redacted; cannot meaningfully diff.
        return rollup

    diff: StructuredDiff = diff_snapshots(
        left=original_ct, right=head_ct, pack=pack,
        left_snapshot_id=original.id, right_snapshot_id=head.id,
    )
    for d in diff.diffs:
        rollup.events.append(SubsequentEvent(
            category=_classify(d),
            description=_describe(d),
            source_snapshot_id=d.source_snapshot,
            field_path=d.path,
            rule_implications=d.rule_implications,
        ))
    return rollup


def group_events_by_category(rollup: SubsequentEventsRollup) -> dict[str, list[SubsequentEvent]]:
    out: dict[str, list[SubsequentEvent]] = {}
    for ev in rollup.events:
        out.setdefault(ev.category, []).append(ev)
    return out
