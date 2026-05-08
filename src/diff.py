"""
Cap-table snapshot diff.

Compares two parsed CapTable instances and produces a structured diff
suitable for the audit memo's "Subsequent Events" section. Class names are
fuzzy-matched (Levenshtein-based) to handle minor renaming between
snapshots (e.g., "Series A Pref" → "Series A Preferred").

No valuation judgments — the tool only reports structural deltas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import CapTable, ShareClass


# ---- Levenshtein distance (no external dep) -------------------------------

def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _similarity(a: str, b: str) -> float:
    """Return [0, 1] where 1 is identical. Operates on normalized strings."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    d = _lev(na, nb)
    return 1.0 - d / max(len(na), len(nb))


# ---- Match candidates -----------------------------------------------------

@dataclass(frozen=True)
class ClassMatch:
    left_name: Optional[str]
    right_name: Optional[str]
    similarity: float  # 0 if one side is missing
    status: str  # "matched" | "added" | "removed" | "renamed"


def _match_classes(left: list[ShareClass], right: list[ShareClass], threshold: float = 0.6) -> list[ClassMatch]:
    """Greedy best-match by similarity, then leftover handling."""
    left_remaining = {sc.name: sc for sc in left}
    right_remaining = {sc.name: sc for sc in right}

    pairs: list[ClassMatch] = []

    # 1. Exact-match pass
    for name in list(left_remaining.keys()):
        if name in right_remaining:
            pairs.append(ClassMatch(name, name, 1.0, "matched"))
            del left_remaining[name]
            del right_remaining[name]

    # 2. Fuzzy-match pass — pick best similarity over threshold
    while left_remaining and right_remaining:
        best: tuple[float, str, str] | None = None
        for ln in left_remaining:
            for rn in right_remaining:
                s = _similarity(ln, rn)
                if best is None or s > best[0]:
                    best = (s, ln, rn)
        if best is None or best[0] < threshold:
            break
        s, ln, rn = best
        status = "renamed" if ln != rn else "matched"
        pairs.append(ClassMatch(ln, rn, s, status))
        del left_remaining[ln]
        del right_remaining[rn]

    # 3. Leftovers
    for ln in left_remaining:
        pairs.append(ClassMatch(ln, None, 0.0, "removed"))
    for rn in right_remaining:
        pairs.append(ClassMatch(None, rn, 0.0, "added"))

    return pairs


# ---- Per-class field deltas ----------------------------------------------

@dataclass
class FieldDelta:
    field: str
    left: object
    right: object


@dataclass
class ClassDiff:
    match: ClassMatch
    deltas: list[FieldDelta] = field(default_factory=list)


def _describe_lp(sc: Optional[ShareClass]) -> str:
    if sc is None or sc.liquidation_preference is None:
        return ""
    lp = sc.liquidation_preference
    parts = [f"{lp.multiple}x", lp.type.value]
    if lp.cap_multiple:
        parts.append(f"cap {lp.cap_multiple}x")
    return " ".join(parts)


def _diff_class(left: Optional[ShareClass], right: Optional[ShareClass]) -> list[FieldDelta]:
    deltas: list[FieldDelta] = []
    if left is None or right is None:
        return deltas
    if left.shares_outstanding != right.shares_outstanding:
        deltas.append(FieldDelta("shares_outstanding", left.shares_outstanding, right.shares_outstanding))
    if (left.issue_price or 0) != (right.issue_price or 0):
        deltas.append(FieldDelta("issue_price", left.issue_price, right.issue_price))
    if left.seniority_rank != right.seniority_rank:
        deltas.append(FieldDelta("seniority_rank", left.seniority_rank, right.seniority_rank))
    left_lp_desc = _describe_lp(left)
    right_lp_desc = _describe_lp(right)
    if left_lp_desc != right_lp_desc:
        deltas.append(FieldDelta("liquidation_preference", left_lp_desc, right_lp_desc))
    if (left.conversion_ratio or 1.0) != (right.conversion_ratio or 1.0):
        deltas.append(FieldDelta("conversion_ratio", left.conversion_ratio, right.conversion_ratio))
    left_ad = left.anti_dilution.variant.value if (left.anti_dilution and left.anti_dilution.variant) else None
    right_ad = right.anti_dilution.variant.value if (right.anti_dilution and right.anti_dilution.variant) else None
    if left_ad != right_ad:
        deltas.append(FieldDelta("anti_dilution_variant", left_ad, right_ad))
    return deltas


# ---- Public API -----------------------------------------------------------

@dataclass
class CapTableDiff:
    left_company: str
    right_company: str
    matches: list[ClassMatch]
    class_diffs: list[ClassDiff]
    side_letters_added: list[str]
    side_letters_removed: list[str]
    safes_added: list[str]
    safes_removed: list[str]
    warrants_added: list[str]
    warrants_removed: list[str]
    summary: str


def diff_cap_tables(left: CapTable, right: CapTable) -> CapTableDiff:
    matches = _match_classes(left.share_classes, right.share_classes)
    class_diffs: list[ClassDiff] = []
    left_by_name = {sc.name: sc for sc in left.share_classes}
    right_by_name = {sc.name: sc for sc in right.share_classes}
    for m in matches:
        l = left_by_name.get(m.left_name) if m.left_name else None
        r = right_by_name.get(m.right_name) if m.right_name else None
        deltas = _diff_class(l, r) if (l and r) else []
        class_diffs.append(ClassDiff(match=m, deltas=deltas))

    left_sl = {sl.id for sl in left.side_letters}
    right_sl = {sl.id for sl in right.side_letters}
    left_safes = {s.id for s in left.safes_outstanding}
    right_safes = {s.id for s in right.safes_outstanding}
    left_war = {w.id for w in left.warrants_outstanding}
    right_war = {w.id for w in right.warrants_outstanding}

    n_added = sum(1 for m in matches if m.status == "added")
    n_removed = sum(1 for m in matches if m.status == "removed")
    n_renamed = sum(1 for m in matches if m.status == "renamed")
    n_changed = sum(1 for cd in class_diffs if cd.deltas)
    summary = (
        f"{n_added} added · {n_removed} removed · {n_renamed} renamed · "
        f"{n_changed} class(es) with field changes."
    )

    return CapTableDiff(
        left_company=left.company.name,
        right_company=right.company.name,
        matches=matches,
        class_diffs=class_diffs,
        side_letters_added=sorted(right_sl - left_sl),
        side_letters_removed=sorted(left_sl - right_sl),
        safes_added=sorted(right_safes - left_safes),
        safes_removed=sorted(left_safes - right_safes),
        warrants_added=sorted(right_war - left_war),
        warrants_removed=sorted(left_war - right_war),
        summary=summary,
    )
