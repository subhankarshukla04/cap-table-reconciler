"""
Waterfall and breakpoint computation for the Cap Table Reconciler.

Given a validated CapTable, produces a list of breakpoints (with explanatory
events) and per-tranche marginal allocation matrices. The output is the
clean structured data that downstream OPM/Backsolve models consume as input
strikes.

The algorithm:
  1. Compute LP-paying breakpoints in seniority order.
  2. For each non-participating preferred, compute its conversion threshold:
     the equity value at which (its share of common-pool residual) = (its LP),
     assuming junior preferred have already converted and senior preferred
     are still in their LP state.
  3. For participating-with-cap preferred, compute (a) the cap-reach threshold
     where LP + participation = cap, and (b) the pure-conversion threshold
     where pure-converted-as-common payout = cap.
  4. For non-participating preferred above a participating-capped class,
     compute the conversion threshold in the regime where the capped class
     is frozen (no marginal flow to it).
  5. Sort all breakpoints, then for each tranche midpoint, determine the
     regime by simulation and compute the marginal allocation.

Scope: handles non-participating, participating-with-cap, and (trivially)
participating-uncapped (which is participating-capped with cap = ∞). Does
not yet handle pari-passu within-class subdivisions or staggered LP
multiples within a single class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import (
    CapTable,
    LPType,
    ShareClass,
    ShareClassType,
)


# -- Output types --------------------------------------------------------------


@dataclass(frozen=True)
class Breakpoint:
    id: str
    value: float
    event: str


@dataclass(frozen=True)
class Tranche:
    id: str
    range_low: float
    range_high: Optional[float]  # None = unbounded
    description: str
    common_pool_shares: Optional[int]
    marginal_allocation_pct: dict[str, float]


@dataclass
class WaterfallResult:
    breakpoints: list[Breakpoint] = field(default_factory=list)
    tranches: list[Tranche] = field(default_factory=list)
    conversion_thresholds: dict[str, float] = field(default_factory=dict)
    cap_reach_thresholds: dict[str, float] = field(default_factory=dict)
    pure_conversion_thresholds: dict[str, float] = field(default_factory=dict)
    lp_total: float = 0.0
    total_fully_diluted_shares: int = 0


# -- Regime state --------------------------------------------------------------


@dataclass(frozen=True)
class RegimeState:
    """
    For each preferred class, encodes its status at a given equity value:
      - "lp": still holding LP (non-participating, below conversion threshold;
              or participating, before cap reached)
      - "converted": has converted to common (forfeits LP)
      - "capped": participating-with-cap, total payout frozen at cap
      - "pure_converted": participating-with-cap, abandoned cap to pure-convert
    """
    states: dict[str, str]


def _make_state(cap_table: CapTable, **overrides: str) -> RegimeState:
    states = {sc.name: "lp" for sc in cap_table.share_classes if sc.type == ShareClassType.preferred}
    states.update(overrides)
    return RegimeState(states=states)


def _pool_share_count(sc: ShareClass) -> float:
    """Common-equivalent share count for pool computation.

    For preferred classes, applies the conversion_ratio (e.g. a triggered
    full-ratchet that resets conv_ratio from 1.0 to 1.667 means the class
    receives 1.667 common-equivalent shares per held preferred when it
    contributes to the residual pool — whether by participation or by
    conversion). Common and granted-pool classes have no conv ratio.
    """
    if sc.type == ShareClassType.preferred:
        ratio = sc.conversion_ratio if sc.conversion_ratio is not None else 1.0
        return sc.shares_outstanding * ratio
    return float(sc.shares_outstanding)


# -- LP breakpoint computation -------------------------------------------------


def _compute_lp_breakpoints(cap_table: CapTable) -> list[Breakpoint]:
    bps: list[Breakpoint] = [Breakpoint(id="BP1", value=0.0, event="origin")]
    cum = 0.0
    for sc in cap_table.preferred_classes_by_seniority:
        cum += sc.liquidation_preference.amount
        bps.append(
            Breakpoint(
                id=f"BP{len(bps) + 1}",
                value=cum,
                event=f"{sc.name} LP satisfied",
            )
        )
    return bps


def _lp_total(cap_table: CapTable) -> float:
    return sum(
        sc.liquidation_preference.amount
        for sc in cap_table.share_classes
        if sc.liquidation_preference is not None
    )


# -- Common pool computation given a regime ------------------------------------


def _common_pool_for_marginal(cap_table: CapTable, state: RegimeState) -> float:
    """Common-equivalent shares sharing the marginal $1 above LPs.

    Preferred contributions are weighted by their conversion_ratio (a
    triggered full-ratchet that bumps a preferred's conv_ratio above 1
    enlarges its pool share when it converts or participates).
    """
    pool = 0.0
    for sc in cap_table.share_classes:
        if sc.excluded_from_waterfall:
            continue
        if sc.is_common_pool_member:
            pool += _pool_share_count(sc)
            continue
        s = state.states.get(sc.name, "lp")
        if s in ("converted", "pure_converted"):
            pool += _pool_share_count(sc)
        elif s == "lp":
            lp = sc.liquidation_preference
            if lp is not None and lp.type in (LPType.participating_uncapped, LPType.participating_capped):
                pool += _pool_share_count(sc)
    return pool


def _residual_lps(cap_table: CapTable, state: RegimeState) -> float:
    """Sum of LPs still being paid as 'preferred LP' (i.e., not consumed by cap, not converted)."""
    total = 0.0
    for sc in cap_table.share_classes:
        if sc.liquidation_preference is None:
            continue
        s = state.states.get(sc.name, "lp")
        # When in LP state, LP is being paid separately. When capped or
        # pure-converted, LP is consumed within the cap or forgone.
        # When converted (non-participating that converted), LP forgone.
        if s == "lp":
            total += sc.liquidation_preference.amount
    return total


def _alloc_marginal(cap_table: CapTable, state: RegimeState) -> dict[str, float]:
    """Fraction of marginal $1 to each waterfall-relevant share class."""
    pool = _common_pool_for_marginal(cap_table, state)
    out: dict[str, float] = {}
    for sc in cap_table.share_classes:
        if sc.excluded_from_waterfall:
            continue
        s = state.states.get(sc.name, "lp")
        share = _pool_share_count(sc)
        if sc.is_common_pool_member:
            out[sc.name] = share / pool if pool > 0 else 0.0
        else:
            lp = sc.liquidation_preference
            if s in ("converted", "pure_converted"):
                out[sc.name] = share / pool if pool > 0 else 0.0
            elif s == "lp" and lp is not None and lp.type in (LPType.participating_uncapped, LPType.participating_capped):
                out[sc.name] = share / pool if pool > 0 else 0.0
            else:
                out[sc.name] = 0.0
    return out


# -- Threshold computations ----------------------------------------------------


def _conversion_threshold_non_participating(target: ShareClass, cap_table: CapTable) -> float:
    """Where target's converted-as-common payout = LP, assuming juniors converted."""
    assert target.liquidation_preference is not None
    state = _make_state(cap_table)
    # Juniors converted; target converted; seniors still LP
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred:
            continue
        if sc.seniority_rank > target.seniority_rank:
            state.states[sc.name] = "converted"
        elif sc.name == target.name:
            state.states[sc.name] = "converted"
    pool = _common_pool_for_marginal(cap_table, state)
    senior_lp_total = sum(
        sc.liquidation_preference.amount
        for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred and sc.seniority_rank < target.seniority_rank
    )
    target_share = _pool_share_count(target) / pool
    return target.liquidation_preference.amount / target_share + senior_lp_total


def _participation_cap_threshold(target: ShareClass, cap_table: CapTable) -> float:
    """Where target's LP + participation share = cap, assuming juniors converted."""
    lp = target.liquidation_preference
    assert lp is not None and lp.type == LPType.participating_capped
    state = _make_state(cap_table)
    for sc in cap_table.share_classes:
        if sc.type == ShareClassType.preferred and sc.seniority_rank > target.seniority_rank:
            state.states[sc.name] = "converted"
    pool = _common_pool_for_marginal(cap_table, state)
    a_share = _pool_share_count(target) / pool

    # LPs above target (B's LP) plus target's own LP form the senior LP base
    senior_lp_for_residual = sum(
        sc.liquidation_preference.amount
        for sc in cap_table.share_classes
        if sc.type == ShareClassType.preferred
        and sc.seniority_rank <= target.seniority_rank
    )
    cap = lp.cap_amount if lp.cap_amount else (lp.cap_multiple * lp.amount if lp.cap_multiple else float("inf"))
    target_residual_at_cap = cap - lp.amount
    return senior_lp_for_residual + target_residual_at_cap / a_share


def _pure_conversion_threshold(target: ShareClass, cap_table: CapTable) -> float:
    """Where target's pure-converted payout exceeds the cap.

    Assumes everyone else has reached their final state (juniors converted,
    seniors converted too if their threshold has been crossed).
    """
    lp = target.liquidation_preference
    assert lp is not None and lp.type == LPType.participating_capped
    cap = lp.cap_amount if lp.cap_amount else (lp.cap_multiple * lp.amount if lp.cap_multiple else float("inf"))

    # In pure-conversion regime, target is pure-converted; we assume seniors
    # have also converted (otherwise target would not pure-convert ahead of
    # seniors). Juniors already converted by assumption.
    state = _make_state(cap_table)
    for sc in cap_table.share_classes:
        if sc.type == ShareClassType.preferred:
            state.states[sc.name] = "converted"
    state.states[target.name] = "pure_converted"

    pool = _common_pool_for_marginal(cap_table, state)
    return cap * pool / _pool_share_count(target)


def _conversion_threshold_above_capped(
    target: ShareClass,
    cap_table: CapTable,
    capped_class: ShareClass,
) -> float:
    """For a non-participating preferred SENIOR to a capped class (e.g., B above capped A).

    In this regime: capped class is frozen, juniors converted. Target converts when
    its converted-as-common payout = LP.

    Total payout up to V = cap_payout + share_of_marginal_pool * (V - cap_payout).
    Target converts when (target_shares / pool) * (V - cap_payout) = LP_target.
    """
    cap = capped_class.liquidation_preference.cap_amount or (
        capped_class.liquidation_preference.cap_multiple * capped_class.liquidation_preference.amount
    )
    state = _make_state(cap_table)
    state.states[capped_class.name] = "capped"
    state.states[target.name] = "converted"
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred:
            continue
        if sc.seniority_rank > target.seniority_rank and sc.name != capped_class.name:
            state.states[sc.name] = "converted"
    pool = _common_pool_for_marginal(cap_table, state)
    target_share = _pool_share_count(target) / pool
    return cap + target.liquidation_preference.amount / target_share


# -- Main entry point ----------------------------------------------------------


def _normalize_degenerate_caps(cap_table: CapTable) -> CapTable:
    """Treat participating_capped with cap_multiple<=1 as non_participating.

    cap_amount = LP × cap_multiple. When cap_multiple ≤ 1, cap ≤ LP, meaning
    the participation residual is zero or negative. Economically the class
    receives only its LP — same as non_participating. The engine produces a
    cleaner regime walk if we collapse this case.
    """
    new_classes = []
    changed = False
    for sc in cap_table.share_classes:
        lp = sc.liquidation_preference
        if (lp is not None
            and lp.type == LPType.participating_capped
            and lp.cap_multiple is not None
            and lp.cap_multiple <= 1.0 + 1e-9
            and lp.cap_amount is None):
            new_lp = lp.model_copy(update={
                "type": LPType.non_participating,
                "cap_multiple": None,
            })
            new_classes.append(sc.model_copy(update={"liquidation_preference": new_lp}))
            changed = True
        else:
            new_classes.append(sc)
    if not changed:
        return cap_table
    return cap_table.model_copy(update={"share_classes": new_classes})


def compute_waterfall(cap_table: CapTable) -> WaterfallResult:
    # Normalize: a participating_capped class with cap_multiple <= 1.0 has
    # cap == LP (no participation residual). Economically equivalent to
    # non_participating; treating it that way avoids an infinitesimal dead-
    # zone tranche between LP-paid and cap-reached.
    cap_table = _normalize_degenerate_caps(cap_table)

    result = WaterfallResult()
    result.lp_total = _lp_total(cap_table)
    result.total_fully_diluted_shares = cap_table.total_fully_diluted_for_waterfall

    # 1. LP breakpoints
    lp_bps = _compute_lp_breakpoints(cap_table)

    # 2. Conversion thresholds for non-participating preferred, and
    #    participation thresholds for capped preferred.
    capped_classes = [
        sc for sc in cap_table.preferred_classes_by_seniority
        if sc.liquidation_preference and sc.liquidation_preference.type == LPType.participating_capped
    ]
    non_part_classes = [
        sc for sc in cap_table.preferred_classes_by_seniority
        if sc.liquidation_preference and sc.liquidation_preference.type == LPType.non_participating
    ]

    # Non-participating conversion thresholds (assuming no capped class
    # interactions for the plain case; for fixture 03, B is non-participating
    # SENIOR to a capped class — handled below)
    for sc in non_part_classes:
        # If a capped class is JUNIOR to this one, the capped class's behavior
        # affects this class's conversion math.
        capped_juniors = [c for c in capped_classes if c.seniority_rank > sc.seniority_rank]
        if capped_juniors:
            # The senior-above-capped formula
            result.conversion_thresholds[sc.name] = _conversion_threshold_above_capped(
                sc, cap_table, capped_juniors[0]
            )
        else:
            result.conversion_thresholds[sc.name] = _conversion_threshold_non_participating(sc, cap_table)

    for sc in capped_classes:
        cap_v = _participation_cap_threshold(sc, cap_table)
        pure_v = _pure_conversion_threshold(sc, cap_table)
        # If cap_reach and pure_conversion are within tight relative tolerance
        # for the same class, the "capped" state is an infinitesimal regime
        # that produces a dead-zone tranche. Collapse to pure_conversion only —
        # economically the class always prefers conversion in that case.
        if pure_v > cap_v and (pure_v - cap_v) / max(pure_v, 1.0) < 5e-3:
            result.pure_conversion_thresholds[sc.name] = cap_v  # collapse to cap_reach
        else:
            result.cap_reach_thresholds[sc.name] = cap_v
            result.pure_conversion_thresholds[sc.name] = pure_v

    # 3. Build the full sorted breakpoint list
    candidate_values: dict[float, str] = {}
    for bp in lp_bps:
        candidate_values[bp.value] = bp.event
    for name, v in result.conversion_thresholds.items():
        candidate_values[v] = f"{name} converts to common"
    for name, v in result.cap_reach_thresholds.items():
        candidate_values[v] = f"{name} participation cap reached"
    for name, v in result.pure_conversion_thresholds.items():
        # only include if pure-conversion threshold is above cap-reach threshold
        cap_reach = result.cap_reach_thresholds.get(name)
        if cap_reach is None or v > cap_reach:
            candidate_values[v] = f"{name} pure-converts to common"

    # Deduplicate within tolerance
    sorted_values = _dedupe_close_values(sorted(candidate_values.keys()))
    result.breakpoints = [
        Breakpoint(id=f"BP{i+1}", value=v, event=candidate_values[v])
        for i, v in enumerate(sorted_values)
    ]

    # 4. Build tranches by simulating regime at each midpoint
    result.tranches = _build_tranches(cap_table, sorted_values, result)
    return result


def _dedupe_close_values(values: list[float], tol: float = 0.01) -> list[float]:
    """Merge breakpoints within `tol` of each other.

    Uses a relative tolerance (1ppm of the largest value) when that's larger
    than the absolute floor. Without this, large-cap-table breakpoints from
    different formulas converge to within float-noise but produce dead-zone
    tranches in between.
    """
    if not values:
        return []
    rel_tol = max(values) * 1e-6
    effective = max(tol, rel_tol)
    out = [values[0]]
    for v in values[1:]:
        if abs(v - out[-1]) > effective:
            out.append(v)
    return out


def _regime_at_value(cap_table: CapTable, value: float, result: WaterfallResult) -> RegimeState:
    """Determine the state at a given equity value, given the result's threshold bookkeeping."""
    state = _make_state(cap_table)
    for sc in cap_table.share_classes:
        if sc.type != ShareClassType.preferred:
            continue
        lp = sc.liquidation_preference
        if lp is None:
            continue
        if lp.type == LPType.non_participating:
            t = result.conversion_thresholds.get(sc.name)
            if t is not None and value > t + 1e-6:
                state.states[sc.name] = "converted"
        elif lp.type == LPType.participating_capped:
            cap_reach = result.cap_reach_thresholds.get(sc.name)
            pure_t = result.pure_conversion_thresholds.get(sc.name)
            if pure_t is not None and value > pure_t + 1e-6:
                state.states[sc.name] = "pure_converted"
            elif cap_reach is not None and value > cap_reach + 1e-6:
                state.states[sc.name] = "capped"
            else:
                state.states[sc.name] = "lp"
    return state


def _build_tranches(
    cap_table: CapTable,
    breakpoints: list[float],
    result: WaterfallResult,
) -> list[Tranche]:
    tranches: list[Tranche] = []
    preferred_by_seniority = cap_table.preferred_classes_by_seniority

    for i, low in enumerate(breakpoints):
        high = breakpoints[i + 1] if i + 1 < len(breakpoints) else None
        mid = (low + high) / 2 if high is not None else low + 1.0

        # Determine: are we still in LP-paying region?
        cum = 0.0
        lp_class = None
        for sc in preferred_by_seniority:
            prev = cum
            cum += sc.liquidation_preference.amount
            # LP-paying tranches only exist when no conversions/caps have happened.
            # At very low values, all classes still in "lp" state.
            state = _regime_at_value(cap_table, mid, result)
            if state.states[sc.name] == "lp" and prev <= mid < cum:
                lp_class = sc
                break

        if lp_class is not None:
            alloc = {
                sc.name: 100.0 if sc.name == lp_class.name else 0.0
                for sc in cap_table.share_classes
                if not sc.excluded_from_waterfall
            }
            tranches.append(
                Tranche(
                    id=f"T{i+1}",
                    range_low=low,
                    range_high=high,
                    description=f"{lp_class.name} LP being paid",
                    common_pool_shares=None,
                    marginal_allocation_pct=alloc,
                )
            )
        else:
            state = _regime_at_value(cap_table, mid, result)
            frac = _alloc_marginal(cap_table, state)
            pool = _common_pool_for_marginal(cap_table, state)
            alloc = {name: f * 100 for name, f in frac.items()}
            tranches.append(
                Tranche(
                    id=f"T{i+1}",
                    range_low=low,
                    range_high=high,
                    description=_describe_regime(cap_table, state),
                    common_pool_shares=pool,
                    marginal_allocation_pct=alloc,
                )
            )
    return tranches


def _describe_regime(cap_table: CapTable, state: RegimeState) -> str:
    parts = []
    for sc in cap_table.preferred_classes_by_seniority:
        s = state.states.get(sc.name, "lp")
        if s == "converted":
            parts.append(f"{sc.name}=converted")
        elif s == "capped":
            parts.append(f"{sc.name}=capped")
        elif s == "pure_converted":
            parts.append(f"{sc.name}=pure-converted")
        else:
            parts.append(f"{sc.name}=LP")
    return "Residual to common pool. Regime: " + ", ".join(parts)


# -- Cumulative payout curves (for chart visualization) -----------------------


def cumulative_payouts_at_breakpoints(
    cap_table: CapTable, result: WaterfallResult
) -> dict[str, list[tuple[float, float]]]:
    """For each share class, compute its cumulative payout at each breakpoint.

    Returns: {class_name: [(V_at_breakpoint, cumulative_payout), ...]}.
    The chart layer connects these points as a stepped line per class.
    """
    classes = [sc for sc in cap_table.share_classes if not sc.excluded_from_waterfall]
    curves: dict[str, list[tuple[float, float]]] = {sc.name: [(0.0, 0.0)] for sc in classes}

    cumulative: dict[str, float] = {sc.name: 0.0 for sc in classes}

    finite_breakpoints = [bp.value for bp in result.breakpoints if bp.value > 0]
    last_bp = max(finite_breakpoints) if finite_breakpoints else 1_000_000
    chart_max = last_bp * 1.3

    for tr in result.tranches:
        low = tr.range_low
        high = tr.range_high
        if high is None:
            high = chart_max
        delta = high - low
        for sc in classes:
            pct = tr.marginal_allocation_pct.get(sc.name, 0.0) / 100.0
            cumulative[sc.name] += delta * pct
            curves[sc.name].append((high, cumulative[sc.name]))
    return curves


def breakpoint_explanations(cap_table: CapTable, result: WaterfallResult) -> list[dict]:
    """Return a per-breakpoint math walk-through.

    Each entry: {id, value, event, formula, steps[]} where formula is the
    symbolic equation and steps are concrete numeric substitutions.

    The walk-through is the transparency layer — Evelyn's team can audit the
    math line by line rather than trust a black-box output.
    """
    out: list[dict] = []
    sym = cap_table.company.currency_symbol

    def fmt(v: float) -> str:
        if abs(v) >= 1_000_000_000:
            return f"{sym}{v/1_000_000_000:,.2f}B"
        if abs(v) >= 1_000_000:
            return f"{sym}{v/1_000_000:,.2f}M"
        if abs(v) >= 1_000:
            return f"{sym}{v/1_000:,.0f}K"
        return f"{sym}{v:,.0f}"

    for bp in result.breakpoints:
        entry = {"id": bp.id, "value": bp.value, "event": bp.event,
                 "formula": "", "steps": []}

        if bp.event == "origin":
            entry["formula"] = "Origin"
            entry["steps"] = ["Lower bound of any waterfall."]
        elif "LP satisfied" in bp.event:
            class_name = bp.event.replace(" LP satisfied", "")
            cum_lp = 0.0
            steps = []
            for sc in cap_table.preferred_classes_by_seniority:
                cum_lp += sc.liquidation_preference.amount
                steps.append(f"+ {sc.name}: {fmt(sc.liquidation_preference.amount)} → cumulative {fmt(cum_lp)}")
                if sc.name == class_name:
                    break
            entry["formula"] = f"Cumulative LP through {class_name}"
            entry["steps"] = steps
        elif "converts to common" in bp.event:
            class_name = bp.event.replace(" converts to common", "")
            try:
                target = next(sc for sc in cap_table.preferred_classes_by_seniority if sc.name == class_name)
            except StopIteration:
                continue
            # Reproduce the formula assumptions used in the synthetic regime
            target_lp = target.liquidation_preference.amount
            target_shares = target.shares_outstanding
            # Build pool = sum of pool-member shares in synthetic regime
            state = _make_state(cap_table)
            for sc in cap_table.share_classes:
                if sc.type != ShareClassType.preferred:
                    continue
                if sc.seniority_rank > target.seniority_rank:
                    if (sc.liquidation_preference is not None
                            and sc.liquidation_preference.type == LPType.participating_capped):
                        state.states[sc.name] = "capped"
                    else:
                        state.states[sc.name] = "converted"
                elif sc.name == target.name:
                    state.states[sc.name] = "converted"
            pool = _common_pool_for_marginal(cap_table, state)
            # Overhang
            overhang = 0.0
            overhang_terms = []
            for sc in cap_table.preferred_classes_by_seniority:
                if sc.name == class_name:
                    continue
                s = state.states.get(sc.name, "lp")
                if s == "lp":
                    overhang += sc.liquidation_preference.amount
                    overhang_terms.append(f"{sc.name} LP {fmt(sc.liquidation_preference.amount)}")
                elif s == "capped":
                    cap_amt = sc.liquidation_preference.cap_amount or (
                        (sc.liquidation_preference.cap_multiple or 1.0) * sc.liquidation_preference.amount
                    )
                    overhang += cap_amt
                    overhang_terms.append(f"{sc.name} cap {fmt(cap_amt)}")
            entry["formula"] = (
                f"{class_name} converted-share = LP / share_in_pool. "
                "Threshold = senior_overhang + LP × pool / shares."
            )
            entry["steps"] = [
                f"senior overhang = {' + '.join(overhang_terms) if overhang_terms else '0'} = {fmt(overhang)}",
                f"pool (synthetic regime) = {pool:,} shares",
                f"target LP = {fmt(target_lp)}, target shares = {target_shares:,}",
                f"= {fmt(overhang)} + {fmt(target_lp)} × {pool:,} / {target_shares:,}",
                f"= {fmt(bp.value)}",
            ]
        elif "participation cap reached" in bp.event:
            class_name = bp.event.replace(" participation cap reached", "")
            try:
                target = next(sc for sc in cap_table.preferred_classes_by_seniority if sc.name == class_name)
            except StopIteration:
                continue
            lp = target.liquidation_preference
            cap_amt = lp.cap_amount or ((lp.cap_multiple or 1.0) * lp.amount)
            entry["formula"] = (
                f"{class_name} participation cap reached. "
                "Threshold = cumulative LPs through target + (cap − LP) × pool / shares."
            )
            entry["steps"] = [
                f"cap amount = {lp.cap_multiple or '?'}x × {fmt(lp.amount)} = {fmt(cap_amt)}",
                f"residual at cap = {fmt(cap_amt)} − {fmt(lp.amount)} = {fmt(cap_amt - lp.amount)}",
                f"= cumulative LP + residual × pool / shares = {fmt(bp.value)}",
            ]
        elif "pure-converts to common" in bp.event:
            class_name = bp.event.replace(" pure-converts to common", "")
            entry["formula"] = (
                f"{class_name} abandons cap and pure-converts. "
                "Threshold = cap × pool / shares (pure-converted regime)."
            )
            entry["steps"] = [
                f"At this exit value, pure-conversion payout exceeds the cap; class flips state.",
                f"= {fmt(bp.value)}",
            ]
        out.append(entry)
    return out


def chart_payload(cap_table: CapTable, result: WaterfallResult) -> dict:
    """Produce a Chart.js-friendly payload for the waterfall visualization.

    Color hierarchy is type-aware rather than index-based:
    - Common gets charcoal so it reads distinctly (it's the line being valued).
    - Preferred classes get a desaturated blue→teal→amber spread, ordered by
      seniority (most-senior darkest).
    - Granted pool gets pale slate so it pairs visually with common.
    """
    curves = cumulative_payouts_at_breakpoints(cap_table, result)

    preferred_palette = ["#1e3a8a", "#0e7490", "#047857", "#b45309", "#7c3aed"]
    color_for: dict[str, str] = {}
    preferred_idx = 0
    sorted_preferred = cap_table.preferred_classes_by_seniority
    for sc in sorted_preferred:
        color_for[sc.name] = preferred_palette[preferred_idx % len(preferred_palette)]
        preferred_idx += 1
    for sc in cap_table.share_classes:
        if sc.name in color_for:
            continue
        if sc.type == ShareClassType.common:
            color_for[sc.name] = "#0f172a"
        elif sc.type == ShareClassType.option_pool_granted:
            color_for[sc.name] = "#94a3b8"
        else:
            color_for[sc.name] = "#475569"

    datasets = []
    for name, pts in curves.items():
        c = color_for.get(name, "#475569")
        datasets.append(
            {
                "label": name,
                "data": [{"x": v, "y": y} for v, y in pts],
                "borderColor": c,
                "backgroundColor": c + "20",
                "stepped": False,
                "fill": False,
                "pointRadius": 2,
                "borderWidth": 2,
                "tension": 0,
                "order": 2,
            }
        )

    # y=x reference line: total exit value. Proves no leakage — the sum of
    # per-class payouts at any x equals x. Drawn behind the class lines.
    finite_breakpoints = [bp.value for bp in result.breakpoints if bp.value > 0]
    last_bp = max(finite_breakpoints) if finite_breakpoints else 1_000_000
    chart_max = last_bp * 1.3
    datasets.append(
        {
            "label": "Total exit value (reference)",
            "data": [{"x": 0.0, "y": 0.0}, {"x": chart_max, "y": chart_max}],
            "borderColor": "rgba(148, 163, 184, 0.55)",
            "backgroundColor": "rgba(148, 163, 184, 0.10)",
            "borderDash": [6, 4],
            "stepped": False,
            "fill": False,
            "pointRadius": 0,
            "borderWidth": 1,
            "tension": 0,
            "order": 3,
        }
    )

    return {
        "datasets": datasets,
        "breakpoints": [
            {"id": bp.id, "value": bp.value, "event": bp.event}
            for bp in result.breakpoints
        ],
        "currency_symbol": cap_table.company.currency_symbol,
        "currency": cap_table.company.currency,
        "chart_max": chart_max,
    }
