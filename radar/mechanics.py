"""Tender mechanics engine — eligibility filter + waterfall + scaleback.

Pure functions. Tested for <50ms on a 500-holder fixture.
"""
from __future__ import annotations

from datetime import date
from collections import defaultdict
from typing import Iterable

from .models import (
    ClassAllocation, EligibilityFilter, Holder, Issuer,
    TenderParams, WaterfallPreview,
)

TODAY = date(2026, 5, 11)


def _months_between(a: date | None, b: date) -> float:
    if a is None:
        return 0.0
    return (b - a).days / 30.4


def is_eligible(holder: Holder, f: EligibilityFilter) -> bool:
    if holder.class_ not in f.include_classes:
        return False
    if f.exclude_foreign_holders and holder.residency == "foreign":
        return False
    if holder.is_ex_employee:
        if f.include_ex_employees_within_months is None:
            return False
        months_since = _months_between(holder.termination_date, TODAY)
        if months_since > f.include_ex_employees_within_months:
            return False
    if holder.class_ == "ESOP":
        if not f.include_vested_esops:
            return False
        months_at_co = _months_between(holder.hire_date, TODAY)
        if months_at_co < f.min_vesting_months:
            return False
        if holder.vested_units <= 0:
            return False
    return True


def _sellable_units(holder: Holder) -> int:
    if holder.class_ == "ESOP":
        return holder.vested_units
    return holder.units_held


def preview_tender(
    issuer: Issuer,
    holders: Iterable[Holder],
    params: TenderParams,
) -> WaterfallPreview:
    # System-boundary validation: a slider misfire or stale param must not
    # surface negative allocations to the analyst.
    price = max(0.0, float(params.price_per_share_usd or 0.0))
    demand_usd = max(0.0, float(params.tender_size_usd or 0.0))

    eligible = [h for h in holders if is_eligible(h, params.eligibility_filter)]
    pool_units = sum(_sellable_units(h) for h in eligible)
    pool_usd = pool_units * price

    if pool_usd > 0:
        scaleback = min(1.0, demand_usd / pool_usd)
        scaleback_2x = min(1.0, demand_usd / (pool_usd * 2))
    else:
        scaleback = 0.0
        scaleback_2x = 0.0

    sorted_h = sorted(eligible, key=_sellable_units, reverse=True)
    top10 = sorted_h[:10]
    top10_units = sum(_sellable_units(h) for h in top10)
    top10_pct = (top10_units / pool_units * 100) if pool_units else 0.0

    per_class: dict[str, list[Holder]] = defaultdict(list)
    for h in eligible:
        per_class[h.class_].append(h)
    breakdown = []
    for cls, hs in sorted(per_class.items(), key=lambda kv: -sum(_sellable_units(h) for h in kv[1])):
        cls_units = sum(_sellable_units(h) for h in hs)
        breakdown.append(ClassAllocation(
            class_name=cls,
            eligible_holders=len(hs),
            eligible_units=cls_units,
            allocation_usd=cls_units * price * scaleback,
        ))

    return WaterfallPreview(
        eligible_holder_count=len(eligible),
        eligible_unit_pool=pool_units,
        eligible_pool_usd=pool_usd,
        scaleback_factor=scaleback,
        scaleback_factor_if_2x=scaleback_2x,
        top_10_concentration_pct=top10_pct,
        per_class_breakdown=breakdown,
    )
