"""Structured snapshot diff with provenance (SYSTEM_SPEC §4.4).

Replaces the fuzzy class-name-matching `src/diff.py` (Phase-0) with a
field-level, path-aware diff that feeds the audit memo's subsequent-events
section. Every change carries:

  - `path`: canonical CapTable path, e.g.
      "share_classes[Series B-1].liquidation_preference.cap_multiple"
  - `change_type`: added | removed | modified | renamed
  - `old_value`, `new_value`: pre-/post-change values
  - `source_snapshot`: the snapshot ID where the change was introduced (or
    "RHS" when no snapshot IDs are provided)
  - `rule_implications`: list of rule IDs whose firing differs across
    the two CapTables (computed by running each side through the rule pack)

Determinism: same (left, right, pack) inputs → same FieldDiff list, in the
same order, on every run (SYSTEM_SPEC §6.6 + §8.10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .checklist import run_checklist
from .models import CapTable
from .rule_pack import RulePack


ChangeType = str  # Literal["added", "removed", "modified", "renamed"]


@dataclass(frozen=True)
class FieldDiff:
    path: str
    change_type: ChangeType
    old_value: Any
    new_value: Any
    source_snapshot: str
    rule_implications: tuple[str, ...] = ()


@dataclass
class StructuredDiff:
    diffs: list[FieldDiff] = field(default_factory=list)
    left_snapshot_id: Optional[str] = None
    right_snapshot_id: Optional[str] = None

    @property
    def change_count(self) -> int:
        return len(self.diffs)

    def by_path_prefix(self, prefix: str) -> list[FieldDiff]:
        return [d for d in self.diffs if d.path.startswith(prefix)]


# ---- Helpers ---------------------------------------------------------------


def _ct_to_dict(ct: CapTable) -> dict:
    """Canonical JSON-serializable representation of a CapTable."""
    return json.loads(ct.model_dump_json())


def _walk(prefix: str, value: Any):
    """Yield (path, scalar_value) pairs from a nested JSON structure.

    Lists of share classes / side letters etc. are keyed by their `name` /
    `id` so reordering doesn't show as change. Other lists are positional.
    """
    if isinstance(value, dict):
        for k in sorted(value.keys()):
            yield from _walk(f"{prefix}.{k}" if prefix else k, value[k])
    elif isinstance(value, list):
        if value and isinstance(value[0], dict) and ("name" in value[0] or "id" in value[0]):
            key_attr = "name" if "name" in value[0] else "id"
            for item in value:
                key = item.get(key_attr) or "(unnamed)"
                yield from _walk(f"{prefix}[{key}]", item)
        else:
            for i, item in enumerate(value):
                yield from _walk(f"{prefix}[{i}]", item)
    else:
        yield prefix, value


def _flatten(ct: CapTable) -> dict[str, Any]:
    return dict(_walk("", _ct_to_dict(ct)))


def _name_aliases(left_ct: CapTable, right_ct: CapTable) -> dict[str, str]:
    """Detect class renames so a rename does not show as remove+add of
    every nested field.

    Conservative: if (a) exactly one class is unique to each side, and
    (b) their attributes other than `name` are identical, treat as rename.
    More complex rename detection (e.g., based on fuzzy name match) is
    deferred to Phase 3 enhancement.
    """
    left_names = {sc.name for sc in left_ct.share_classes}
    right_names = {sc.name for sc in right_ct.share_classes}
    only_left = sorted(left_names - right_names)
    only_right = sorted(right_names - left_names)
    if len(only_left) != 1 or len(only_right) != 1:
        return {}
    l_name, r_name = only_left[0], only_right[0]
    l_sc = next(sc for sc in left_ct.share_classes if sc.name == l_name)
    r_sc = next(sc for sc in right_ct.share_classes if sc.name == r_name)
    l_dump = l_sc.model_dump()
    r_dump = r_sc.model_dump()
    l_dump.pop("name", None)
    r_dump.pop("name", None)
    if l_dump == r_dump:
        return {l_name: r_name}
    return {}


# ---- Main diff entry -------------------------------------------------------


def diff_snapshots(
    left: CapTable,
    right: CapTable,
    pack: Optional[RulePack] = None,
    left_snapshot_id: Optional[str] = None,
    right_snapshot_id: Optional[str] = None,
) -> StructuredDiff:
    """Compute the field-level diff from `left` to `right`.

    Optionally runs the rule pack on each side to fill `rule_implications`
    per field (the set of rule IDs whose firing differs across the two).
    """
    renames = _name_aliases(left, right)

    # Apply rename normalisation: rewrite left class name to its right
    # counterpart before flattening, so paths align.
    if renames:
        l_dict = _ct_to_dict(left)
        for sc in l_dict.get("share_classes", []):
            if sc.get("name") in renames:
                sc["name"] = renames[sc["name"]]
        left_flat = dict(_walk("", l_dict))
    else:
        left_flat = _flatten(left)
    right_flat = _flatten(right)

    diffs: list[FieldDiff] = []
    snapshot_label = right_snapshot_id or "RHS"

    # Surface the rename itself, if any.
    for old, new in renames.items():
        diffs.append(FieldDiff(
            path=f"share_classes[{new}].name",
            change_type="renamed",
            old_value=old,
            new_value=new,
            source_snapshot=snapshot_label,
        ))

    all_paths = sorted(set(left_flat.keys()) | set(right_flat.keys()))
    for path in all_paths:
        l_val = left_flat.get(path, _MISSING)
        r_val = right_flat.get(path, _MISSING)
        if l_val == r_val:
            continue
        if l_val is _MISSING:
            change_type = "added"
            old_v, new_v = None, r_val
        elif r_val is _MISSING:
            change_type = "removed"
            old_v, new_v = l_val, None
        else:
            change_type = "modified"
            old_v, new_v = l_val, r_val
        diffs.append(FieldDiff(
            path=path,
            change_type=change_type,
            old_value=old_v,
            new_value=new_v,
            source_snapshot=snapshot_label,
        ))

    # Optional: fill rule_implications by running the pack on each side.
    if pack is not None:
        l_findings = {f.code for f in run_checklist(left, pack=pack)}
        r_findings = {f.code for f in run_checklist(right, pack=pack)}
        only_left = l_findings - r_findings
        only_right = r_findings - l_findings
        if only_left or only_right:
            implications = tuple(sorted(only_left | only_right))
            # Attach to the engagement-level pseudo-path so the memo can
            # surface it without binding to a specific field.
            diffs.append(FieldDiff(
                path="$rule_pack.findings_delta",
                change_type="modified",
                old_value=sorted(only_left),
                new_value=sorted(only_right),
                source_snapshot=snapshot_label,
                rule_implications=implications,
            ))

    return StructuredDiff(
        diffs=diffs,
        left_snapshot_id=left_snapshot_id,
        right_snapshot_id=right_snapshot_id,
    )


# Sentinel for "field present on one side, absent on the other."
class _Missing:
    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()
