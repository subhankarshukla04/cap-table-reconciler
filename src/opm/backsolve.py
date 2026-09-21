"""OPM Backsolve sibling (SYSTEM_SPEC §5.1, §8.7).

Given:
  - a clean CapTable (with computed WaterfallResult)
  - a market-input pack (vol, time, rf, DLOM, dividend_yield)
  - the latest-round price-per-share and target class

Solve for total equity value S such that the OPM-modeled value of one share
in the anchor (target) class equals the price-per-share paid by the latest
round. Then derive every other class's per-share fair value from the same
OPM at the solved S; apply DLOM to common; output sensitivity tables.

Math (Option-Pricing Method, allocation form):
  - Each waterfall breakpoint K_i defines a tranche [K_i, K_{i+1}).
  - The aggregate equity is treated as a portfolio of European calls on
    total equity value, with strike K_i, maturity T, vol sigma, rfr r.
  - Per-tranche value = C(S, K_i) - C(S, K_{i+1}). (Last tranche is just
    C(S, K_last).)
  - Each tranche's value is allocated to share classes by that tranche's
    marginal-allocation matrix (already computed in WaterfallResult).
  - Per-class value = sum over tranches of (tranche_value * alloc_pct/100).
  - Per-share value = per-class value / total shares in that class
    (for participating classes the "share count" is post-conversion).

Refusal: cannot run on a CapTable with unresolved blocker findings
(spec §5.1). The caller passes `findings` and we check.

Reference computation in `references/opm_backsolve_reference.md` (worked
example matching AICPA Cheap Stock Guide Ch.6 style).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from scipy.optimize import brentq

from ..checklist import Finding
from ..models import CapTable, ShareClassType
from ..waterfall import (
    Tranche,
    WaterfallResult,
    compute_waterfall,
)
from .bsm import bsm_call_value


# ---- Errors ----------------------------------------------------------------


class BacksolveError(Exception):
    error_code: str = "backsolve-error"


class BacksolveBlockersOutstanding(BacksolveError):
    error_code = "backsolve-blockers-outstanding"


class BacksolveSolverFailed(BacksolveError):
    error_code = "backsolve-solver-failed"


class BacksolveAnchorMissing(BacksolveError):
    error_code = "backsolve-anchor-missing"


# ---- Inputs / outputs ------------------------------------------------------


@dataclass(frozen=True)
class MarketInputs:
    """All inputs the analyst sources and defends. Tool does NOT pick these.

    SD-AUD-W9-M2: domain checks in __post_init__. Black-Scholes squares
    σ, so a sign typo on volatility silently produces a "defendable"
    answer the analyst would paste into a memo. Reject NaN/Inf and
    out-of-range values at construction so the bad number never reaches
    the solver.
    """
    volatility: float  # annualised, e.g. 0.55 for 55%
    time_to_liquidity_years: float  # e.g. 4.0
    risk_free_rate: float  # continuously-compounded annual, e.g. 0.045
    dividend_yield: float = 0.0
    dlom: float = 0.0  # discount for lack of marketability on common, 0..1

    def __post_init__(self):
        import math as _math
        for name, value in (
            ("volatility", self.volatility),
            ("time_to_liquidity_years", self.time_to_liquidity_years),
            ("risk_free_rate", self.risk_free_rate),
            ("dividend_yield", self.dividend_yield),
            ("dlom", self.dlom),
        ):
            if not isinstance(value, (int, float)) or _math.isnan(value) or _math.isinf(value):
                raise BacksolveError(
                    f"MarketInputs.{name} must be a finite number; got {value!r}"
                )
        if self.volatility < 0:
            raise BacksolveError(
                f"volatility must be >= 0; got {self.volatility}. "
                "Sign typo? Black-Scholes squares σ so a negative input "
                "silently behaves like its positive twin."
            )
        if not (0 < self.time_to_liquidity_years <= 50):
            raise BacksolveError(
                f"time_to_liquidity_years must be in (0, 50]; got "
                f"{self.time_to_liquidity_years}"
            )
        if not (-0.10 <= self.risk_free_rate <= 1.0):
            raise BacksolveError(
                f"risk_free_rate must be in [-0.10, 1.0]; got "
                f"{self.risk_free_rate}"
            )
        if not (0.0 <= self.dividend_yield <= 1.0):
            raise BacksolveError(
                f"dividend_yield must be in [0, 1]; got {self.dividend_yield}"
            )
        if not (0.0 <= self.dlom <= 1.0):
            raise BacksolveError(
                f"dlom must be in [0, 1]; got {self.dlom}"
            )


@dataclass(frozen=True)
class AnchorInputs:
    """The latest priced round used as the calibration anchor."""
    class_name: str
    price_per_share: float
    # Total dollars raised at the anchor round (informational; not required
    # for the solve, included in the audit memo footnote).
    raise_amount: Optional[float] = None


@dataclass(frozen=True)
class ClassFairValue:
    name: str
    total_value: float
    shares_for_fv: int  # the share count used in per-share computation
    fair_value_per_share: float
    fair_value_per_share_after_dlom: Optional[float] = None  # common only


@dataclass
class BacksolveResult:
    implied_total_equity_value: float
    market_inputs: MarketInputs
    anchor: AnchorInputs
    per_class: list[ClassFairValue] = field(default_factory=list)
    sensitivity: dict[str, list[dict]] = field(default_factory=dict)
    # {"volatility": [{"label": "+10%", "common_fmv": ...}, ...], "time": ..., "rfr": ...}

    @property
    def common_fmv_per_share(self) -> Optional[float]:
        for c in self.per_class:
            if c.name.lower() in ("common", "common stock", "founders common"):
                # Prefer post-DLOM if set
                return c.fair_value_per_share_after_dlom or c.fair_value_per_share
        # Fall back to the first non-preferred class
        return next(
            (c.fair_value_per_share_after_dlom or c.fair_value_per_share
             for c in self.per_class if "preferred" not in c.name.lower()),
            None,
        )


# ---- Tranche values --------------------------------------------------------


def _tranche_value(
    tranche: Tranche, S: float, market: MarketInputs
) -> float:
    """C(S, low) - C(S, high). For unbounded high, just C(S, low)."""
    c_low = bsm_call_value(
        S=S, K=tranche.range_low, T=market.time_to_liquidity_years,
        sigma=market.volatility, r=market.risk_free_rate, q=market.dividend_yield,
    )
    if tranche.range_high is None:
        return c_low
    c_high = bsm_call_value(
        S=S, K=tranche.range_high, T=market.time_to_liquidity_years,
        sigma=market.volatility, r=market.risk_free_rate, q=market.dividend_yield,
    )
    return max(c_low - c_high, 0.0)


def _allocate_to_classes(
    waterfall: WaterfallResult, S: float, market: MarketInputs
) -> dict[str, float]:
    """Per-class aggregate OPM value (sum of allocated tranche values)."""
    out: dict[str, float] = {}
    for tr in waterfall.tranches:
        v = _tranche_value(tr, S, market)
        for class_name, pct in tr.marginal_allocation_pct.items():
            out[class_name] = out.get(class_name, 0.0) + v * (pct / 100.0)
    return out


def _shares_for_fv(cap_table: CapTable, class_name: str) -> int:
    sc = next((c for c in cap_table.share_classes if c.name == class_name), None)
    if sc is None:
        return 0
    return int(sc.shares_outstanding)


def _per_class_pps(
    cap_table: CapTable, allocation: dict[str, float]
) -> dict[str, float]:
    pps: dict[str, float] = {}
    for name, total in allocation.items():
        n = _shares_for_fv(cap_table, name)
        pps[name] = (total / n) if n > 0 else 0.0
    return pps


# ---- Solver ----------------------------------------------------------------


# Spec §5.1 brentq bounds:
_S_LOWER = 1.0
_S_UPPER = 1e12


def _check_findings(findings: list[Finding]) -> None:
    blockers = [f for f in findings if f.severity == "blocker"]
    if blockers:
        codes = [f.code for f in blockers]
        raise BacksolveBlockersOutstanding(
            f"Cannot run OPM Backsolve while {len(blockers)} blocker finding(s) "
            f"remain unresolved: {codes}"
        )


def backsolve(
    cap_table: CapTable,
    findings: list[Finding],
    market: MarketInputs,
    anchor: AnchorInputs,
    waterfall: Optional[WaterfallResult] = None,
) -> BacksolveResult:
    """Solve for implied total equity value matching the anchor PPS."""
    _check_findings(findings)

    wf = waterfall or compute_waterfall(cap_table)

    anchor_class = next(
        (c for c in cap_table.share_classes if c.name == anchor.class_name), None
    )
    if anchor_class is None:
        raise BacksolveAnchorMissing(
            f"Anchor class {anchor.class_name!r} not found in cap table."
        )
    anchor_shares = int(anchor_class.shares_outstanding)
    if anchor_shares <= 0:
        raise BacksolveAnchorMissing(
            f"Anchor class {anchor.class_name!r} has 0 shares; cannot calibrate."
        )

    def residual(S: float) -> float:
        alloc = _allocate_to_classes(wf, S, market)
        anchor_total = alloc.get(anchor.class_name, 0.0)
        anchor_pps_model = anchor_total / anchor_shares
        return anchor_pps_model - anchor.price_per_share

    try:
        S_star = brentq(residual, _S_LOWER, _S_UPPER, xtol=1e-3, rtol=1e-9)
    except (ValueError, RuntimeError) as e:
        raise BacksolveSolverFailed(
            f"brentq could not bracket a solution on [{_S_LOWER}, {_S_UPPER}]: {e}"
        )

    # Build per-class result at the solved S.
    allocation = _allocate_to_classes(wf, S_star, market)
    per_class: list[ClassFairValue] = []
    for sc in cap_table.share_classes:
        if sc.type == ShareClassType.option_pool_reserved:
            continue  # excluded from waterfall
        n = int(sc.shares_outstanding)
        total = allocation.get(sc.name, 0.0)
        pps = (total / n) if n > 0 else 0.0
        post_dlom = None
        if sc.type == ShareClassType.common and market.dlom > 0:
            post_dlom = pps * (1.0 - market.dlom)
        per_class.append(ClassFairValue(
            name=sc.name, total_value=total,
            shares_for_fv=n, fair_value_per_share=pps,
            fair_value_per_share_after_dlom=post_dlom,
        ))

    sensitivity = _sensitivity_tables(
        cap_table, wf, market, anchor, S_star
    )

    return BacksolveResult(
        implied_total_equity_value=S_star,
        market_inputs=market,
        anchor=anchor,
        per_class=per_class,
        sensitivity=sensitivity,
    )


# ---- Sensitivity -----------------------------------------------------------


def _solve_with_market(
    cap_table: CapTable, wf: WaterfallResult, market: MarketInputs,
    anchor: AnchorInputs,
) -> tuple[float, float]:
    anchor_class = next(c for c in cap_table.share_classes if c.name == anchor.class_name)
    anchor_shares = int(anchor_class.shares_outstanding)

    def residual(S: float) -> float:
        alloc = _allocate_to_classes(wf, S, market)
        return alloc.get(anchor.class_name, 0.0) / anchor_shares - anchor.price_per_share

    S_star = brentq(residual, _S_LOWER, _S_UPPER, xtol=1e-3, rtol=1e-9)
    alloc = _allocate_to_classes(wf, S_star, market)
    common = next(
        (sc for sc in cap_table.share_classes if sc.type == ShareClassType.common),
        None,
    )
    common_pps = 0.0
    if common is not None and common.shares_outstanding > 0:
        common_pps = alloc.get(common.name, 0.0) / common.shares_outstanding
        if market.dlom > 0:
            common_pps *= (1.0 - market.dlom)
    return S_star, common_pps


def _sensitivity_tables(
    cap_table: CapTable, wf: WaterfallResult, base: MarketInputs,
    anchor: AnchorInputs, base_S: float,
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"volatility": [], "time": [], "rfr": []}
    for delta in (-0.1, -0.05, 0.0, 0.05, 0.10):
        mkt = MarketInputs(
            volatility=max(base.volatility + delta, 0.01),
            time_to_liquidity_years=base.time_to_liquidity_years,
            risk_free_rate=base.risk_free_rate,
            dividend_yield=base.dividend_yield,
            dlom=base.dlom,
        )
        try:
            s, common_pps = _solve_with_market(cap_table, wf, mkt, anchor)
        except (ValueError, RuntimeError):
            continue
        out["volatility"].append({
            "label": f"vol={mkt.volatility:.0%}",
            "delta": delta,
            "implied_equity_value": s,
            "common_fmv_per_share": common_pps,
        })
    for delta in (-1.0, -0.5, 0.0, 0.5, 1.0):
        mkt = MarketInputs(
            volatility=base.volatility,
            time_to_liquidity_years=max(base.time_to_liquidity_years + delta, 0.25),
            risk_free_rate=base.risk_free_rate,
            dividend_yield=base.dividend_yield,
            dlom=base.dlom,
        )
        try:
            s, common_pps = _solve_with_market(cap_table, wf, mkt, anchor)
        except (ValueError, RuntimeError):
            continue
        out["time"].append({
            "label": f"T={mkt.time_to_liquidity_years:.2f}y",
            "delta": delta,
            "implied_equity_value": s,
            "common_fmv_per_share": common_pps,
        })
    for bp in (-0.0025, -0.00125, 0.0, 0.00125, 0.0025):
        mkt = MarketInputs(
            volatility=base.volatility,
            time_to_liquidity_years=base.time_to_liquidity_years,
            risk_free_rate=max(base.risk_free_rate + bp, 0.0),
            dividend_yield=base.dividend_yield,
            dlom=base.dlom,
        )
        try:
            s, common_pps = _solve_with_market(cap_table, wf, mkt, anchor)
        except (ValueError, RuntimeError):
            continue
        out["rfr"].append({
            "label": f"rf={mkt.risk_free_rate:.4f}",
            "delta_bps": int(bp * 10000),
            "implied_equity_value": s,
            "common_fmv_per_share": common_pps,
        })
    return out
