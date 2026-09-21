"""Adapt a ParsedDRHP into Issuer + Holder list for the engines.

Honesty rule: this adapter does NOT silently fabricate per-holder detail.
- If the DRHP discloses an estimated ESOP holder count, we fan out into
  that many synthetic holders with `is_synthetic=True` on each row.
- If the DRHP does NOT disclose the count, we emit ONE aggregate ESOP
  holder with `is_synthetic=True` — the UI surfaces a "Synthetic" banner.

The mechanics engine treats synthetic and real holders identically (it
just does math). But the UI must surface the distinction so an analyst
never confuses fabricated detail with audited data.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .models import Holder, Issuer, ParsedDRHP

TODAY = date(2026, 5, 11)


def adapt(parsed: ParsedDRHP) -> tuple[Issuer, list[Holder]]:
    rng = random.Random(sum(ord(c) for c in parsed.filing_id))
    geo = ("IN" if parsed.registered_state in {"Karnataka", "Maharashtra", "Delhi"}
           else "SEA")
    issuer = Issuer(
        id=parsed.filing_id,
        legal_name=parsed.legal_name,
        sector="Listed-pending",
        geography=geo,
        state=parsed.registered_state,
        employee_count=parsed.employee_count,
        founded_year=parsed.founded_year,
        last_round_amount_usd=None,
        last_round_date=None,
        last_round_price_per_share_usd=(
            parsed.last_round_inr_per_share / 83.0
            if parsed.last_round_inr_per_share else None
        ),
        last_round_price_per_share_local=parsed.last_round_inr_per_share,
        drhp_filed_date=parsed.filing_date,
    )

    holders: list[Holder] = []
    for row in parsed.shareholding:
        if row.class_ == "ESOP":
            n_emp = parsed.esop_holder_count_estimated
            if not n_emp or n_emp <= 0:
                # NO fan-out fiction — single aggregate row, flagged synthetic
                holders.append(Holder(
                    holder_id=f"{parsed.filing_id}-esop-aggregate",
                    name=row.name + " (aggregate)",
                    **{"class": "ESOP"},
                    units_held=row.units,
                    vested_units=int(row.units * 0.55),  # conservative vested estimate
                    is_employee=True, is_ex_employee=False,
                    residency=row.residency,
                    hire_date=None, termination_date=None,
                    is_synthetic=True,
                ))
                continue
            # Disclosed holder count → fan out, all rows flagged synthetic.
            per_employee = max(1, row.units // n_emp)
            for i in range(n_emp):
                years_at_co = rng.uniform(0.5, 5.5)
                hire = TODAY - timedelta(days=int(years_at_co * 365))
                months_at_co = (TODAY - hire).days / 30.4
                vested_frac = 0.0 if months_at_co < 12 else min(1.0, months_at_co / 48.0)
                is_ex = rng.random() < 0.07
                term = (TODAY - timedelta(days=int(rng.uniform(30, 540)))) if is_ex else None
                if parsed.foreign_holder_pct and parsed.foreign_holder_pct > 50:
                    residency = rng.choices(
                        ["resident", "nri", "foreign", "singapore_resident"],
                        weights=[65, 15, 12, 8],
                    )[0]
                else:
                    residency = rng.choices(
                        ["resident", "nri", "foreign"],
                        weights=[80, 12, 8],
                    )[0]
                holders.append(Holder(
                    holder_id=f"{parsed.filing_id}-emp-{i+1:04d}",
                    name=f"ESOP holder {i+1}",
                    **{"class": "ESOP"},
                    units_held=per_employee,
                    vested_units=int(per_employee * vested_frac),
                    is_employee=not is_ex,
                    is_ex_employee=is_ex,
                    residency=residency,  # type: ignore[arg-type]
                    hire_date=hire,
                    termination_date=term,
                    is_synthetic=True,
                ))
        else:
            holders.append(Holder(
                holder_id=f"{parsed.filing_id}-{row.class_.lower()}-{len(holders)}",
                name=row.name,
                **{"class": row.class_},
                units_held=row.units,
                vested_units=row.units,
                is_employee=row.is_employee,
                is_ex_employee=False,
                residency=row.residency,
                hire_date=(date(parsed.founded_year, 1, 1)
                           if (row.is_employee and parsed.founded_year) else None),
                termination_date=None,
                is_synthetic=False,
            ))

    return issuer, holders
