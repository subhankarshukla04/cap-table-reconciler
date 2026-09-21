"""BSM / IFRS 2 ESOP sibling (SYSTEM_SPEC §5.2).

Per-grant fair value via Black-Scholes-Merton, then amortise that fair
value over the vesting period (straight-line for cliff-only, graded for
tranche schedules), producing the per-reporting-period P&L impact line
the analyst books under IFRS 2 / ASC 718.

Scope discipline:
  - Single-grant input → single-grant output. Caller aggregates.
  - Vesting models: cliff (single-date) and graded (list of (date, pct)).
  - No early-exercise / suboptimal-exercise multiple (the AICPA / FASB
    "early-exercise multiplier" m). Defer; analyst can compute T_effective
    externally and pass it as `time_to_expiry_years`.
  - No forfeiture probability adjustment. Use grant fair value as the
    base; the analyst applies expected forfeiture separately.

Cross-references:
  - GAP-14 protective provisions: not relevant here.
  - The engine produces deterministic outputs (SYSTEM_SPEC §6.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .bsm import bsm_call_value


@dataclass(frozen=True)
class VestingTranche:
    """One vest event in a graded schedule."""
    vest_date: date
    fraction: float  # 0..1, sum across tranches must be 1.0


@dataclass(frozen=True)
class ESOPGrant:
    """One grant. All amounts in the company's home currency."""
    id: str
    grantee: str
    grant_date: date
    shares: int
    strike_price: float  # K
    spot_price_at_grant: float  # S (from latest 409A / IFRS 13 valuation)
    time_to_expiry_years: float  # T_effective; analyst supplies
    volatility: float
    risk_free_rate: float
    dividend_yield: float = 0.0
    # Vesting: either a single cliff date or a graded schedule.
    cliff_date: Optional[date] = None
    graded_schedule: Optional[tuple[VestingTranche, ...]] = None


@dataclass(frozen=True)
class AmortizationRow:
    period_start: date
    period_end: date
    expense_for_period: float
    cumulative_expense: float


@dataclass
class GrantValuation:
    grant_id: str
    fair_value_per_option: float  # BSM
    fair_value_aggregate: float  # per_option * shares
    vesting_start: date
    vesting_end: date
    schedule: list[AmortizationRow] = field(default_factory=list)


def value_grant(grant: ESOPGrant) -> float:
    """BSM fair value PER OPTION at grant date."""
    return bsm_call_value(
        S=grant.spot_price_at_grant,
        K=grant.strike_price,
        T=grant.time_to_expiry_years,
        sigma=grant.volatility,
        r=grant.risk_free_rate,
        q=grant.dividend_yield,
    )


def _vesting_window(grant: ESOPGrant) -> tuple[date, date]:
    if grant.graded_schedule:
        end = max(t.vest_date for t in grant.graded_schedule)
    elif grant.cliff_date:
        end = grant.cliff_date
    else:
        raise ValueError(
            f"Grant {grant.id} has no cliff_date or graded_schedule; cannot amortise."
        )
    return grant.grant_date, end


def amortise_grant(
    grant: ESOPGrant, period: str = "annual"
) -> GrantValuation:
    """Compute per-period expense rows.

    `period` is "annual" or "monthly". Straight-line for cliff vesting;
    front-loaded (per IFRS 2 standard) for graded vesting where each
    tranche is treated as its own award amortised over its vesting period.
    """
    if period not in ("annual", "monthly"):
        raise ValueError("period must be 'annual' or 'monthly'")

    fv_per = value_grant(grant)
    total_fv = fv_per * grant.shares
    start, end = _vesting_window(grant)

    rows: list[AmortizationRow] = []
    if grant.graded_schedule:
        # Sum each tranche's amortisation contribution per period boundary.
        # Per IFRS 2 each tranche is a separate award amortised straight-
        # line from grant_date to its own vest_date.
        period_boundaries = _period_boundaries(start, end, period)
        per_boundary_expense = [0.0] * (len(period_boundaries) - 1)
        for tranche in grant.graded_schedule:
            tranche_fv = total_fv * tranche.fraction
            tranche_days = max((tranche.vest_date - start).days, 1)
            for i in range(len(period_boundaries) - 1):
                p_start = max(period_boundaries[i], start)
                p_end = min(period_boundaries[i + 1], tranche.vest_date)
                if p_end <= p_start:
                    continue
                days_in_period = (p_end - p_start).days
                per_boundary_expense[i] += tranche_fv * (days_in_period / tranche_days)
        cum = 0.0
        for i in range(len(period_boundaries) - 1):
            cum += per_boundary_expense[i]
            rows.append(AmortizationRow(
                period_start=period_boundaries[i],
                period_end=period_boundaries[i + 1],
                expense_for_period=per_boundary_expense[i],
                cumulative_expense=cum,
            ))
    else:
        # Cliff: straight-line from grant_date to cliff_date over period
        # boundaries.
        period_boundaries = _period_boundaries(start, end, period)
        total_days = max((end - start).days, 1)
        cum = 0.0
        for i in range(len(period_boundaries) - 1):
            p_start = period_boundaries[i]
            p_end = period_boundaries[i + 1]
            days_in_period = (p_end - p_start).days
            expense = total_fv * (days_in_period / total_days)
            cum += expense
            rows.append(AmortizationRow(
                period_start=p_start, period_end=p_end,
                expense_for_period=expense,
                cumulative_expense=cum,
            ))

    return GrantValuation(
        grant_id=grant.id,
        fair_value_per_option=fv_per,
        fair_value_aggregate=total_fv,
        vesting_start=start,
        vesting_end=end,
        schedule=rows,
    )


def _period_boundaries(start: date, end: date, period: str) -> list[date]:
    """Return boundaries aligned to year-end (annual) or month-end (monthly)
    between `start` and `end`, with `start` as the first boundary and `end`
    as the last."""
    from datetime import date as _d

    out: list[date] = [start]
    if period == "annual":
        y = start.year
        while True:
            year_end = _d(y, 12, 31)
            if year_end >= end:
                break
            if year_end > start:
                out.append(year_end)
            y += 1
    else:  # monthly
        # Walk to the last day of each subsequent month.
        from calendar import monthrange

        y, m = start.year, start.month
        while True:
            _, last = monthrange(y, m)
            month_end = _d(y, m, last)
            if month_end >= end:
                break
            if month_end > start:
                out.append(month_end)
            if m == 12:
                y += 1
                m = 1
            else:
                m += 1
    if out[-1] != end:
        out.append(end)
    return out
