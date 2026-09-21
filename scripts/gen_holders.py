"""Generate realistic synthetic cap-table holder fixtures per issuer.

Output shape per issuer: ~500 holders with realistic distribution:
- 2-3 founders (5-20% each)
- 5-10% ESOP pool spread across 350-450 employees with 4-yr vest + 1-yr cliff
- 5-8 institutional Pref holders (Series A through latest)
- 10-20 angels
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "fixtures"
ISSUERS_PATH = FIXTURES / "issuers.json"
HOLDERS_DIR = FIXTURES / "holders"


def gen_holders(issuer: dict, seed: int) -> list[dict]:
    rng = random.Random(seed)
    today = date(2026, 5, 11)
    holders: list[dict] = []
    total_units = 100_000_000

    # Founders: 2-3, holding 30-55% combined
    n_founders = rng.choice([2, 3])
    founder_share = rng.uniform(0.30, 0.55)
    for i in range(n_founders):
        units = int(total_units * (founder_share / n_founders))
        holders.append({
            "holder_id": f"{issuer['id']}-founder-{i+1}",
            "name": f"Founder {i+1}",
            "class": "Common",
            "units_held": units,
            "vested_units": units,
            "is_employee": True,
            "is_ex_employee": False,
            "residency": "resident",
            "hire_date": str(date(issuer["founded_year"], 1, 1)),
            "termination_date": None,
        })

    # ESOP pool: 5-10% of cap; ~400 employees with realistic vesting
    esop_pct = rng.uniform(0.05, 0.10)
    esop_units = int(total_units * esop_pct)
    n_employees = rng.randint(350, 450)
    per_employee = esop_units // n_employees
    for i in range(n_employees):
        # Hire dates spread over last 6 years; older employees get more vested
        years_ago = rng.uniform(0.5, 6.0)
        hire_date = today - timedelta(days=int(years_ago * 365))
        # Vest: 4-year linear, 1-year cliff
        months_at_co = (today - hire_date).days / 30.4
        if months_at_co < 12:
            vested_frac = 0.0
        else:
            vested_frac = min(1.0, months_at_co / 48.0)
        # Some employees have terminated
        is_ex = rng.random() < 0.08
        termination = None
        if is_ex:
            term_months_ago = rng.uniform(0.5, 18.0)
            termination = today - timedelta(days=int(term_months_ago * 30.4))
        # Residency: weighted to issuer geography
        if issuer["geography"] == "IN":
            residency = rng.choices(
                ["resident", "nri", "foreign"], weights=[78, 14, 8]
            )[0]
        elif issuer["geography"] == "SEA":
            residency = rng.choices(
                ["singapore_resident", "sea_resident", "foreign", "nri"],
                weights=[45, 35, 12, 8],
            )[0]
        else:  # Cross
            residency = rng.choices(
                ["resident", "nri", "foreign", "singapore_resident"],
                weights=[55, 18, 15, 12],
            )[0]
        holders.append({
            "holder_id": f"{issuer['id']}-emp-{i+1:04d}",
            "name": f"Employee {i+1}",
            "class": "ESOP",
            "units_held": per_employee,
            "vested_units": int(per_employee * vested_frac),
            "is_employee": not is_ex,
            "is_ex_employee": is_ex,
            "residency": residency,
            "hire_date": str(hire_date),
            "termination_date": str(termination) if termination else None,
        })

    # Institutional Pref holders: 5-8 rounds, each a single Pref entity
    n_pref = rng.randint(5, 8)
    pref_remaining = total_units - sum(h["units_held"] for h in holders)
    series_labels = ["SeedPref", "SeriesA", "SeriesB", "SeriesC",
                     "SeriesD", "SeriesE", "SeriesF", "SeriesG"]
    for i in range(n_pref):
        units = int(pref_remaining * rng.uniform(0.06, 0.15))
        holders.append({
            "holder_id": f"{issuer['id']}-pref-{i+1}",
            "name": f"{series_labels[i]} Investor",
            "class": series_labels[i],
            "units_held": units,
            "vested_units": units,
            "is_employee": False,
            "is_ex_employee": False,
            "residency": rng.choice(["foreign", "foreign", "singapore_resident", "resident"]),
            "hire_date": None,
            "termination_date": None,
        })

    # Angels: 10-20
    n_angels = rng.randint(10, 20)
    angel_pool = max(0, total_units - sum(h["units_held"] for h in holders))
    per_angel = angel_pool // max(n_angels, 1)
    for i in range(n_angels):
        holders.append({
            "holder_id": f"{issuer['id']}-angel-{i+1:02d}",
            "name": f"Angel {i+1}",
            "class": "Common",
            "units_held": per_angel,
            "vested_units": per_angel,
            "is_employee": False,
            "is_ex_employee": False,
            "residency": rng.choices(
                ["resident", "nri", "foreign", "singapore_resident"],
                weights=[40, 25, 20, 15],
            )[0],
            "hire_date": None,
            "termination_date": None,
        })

    return holders


def main() -> None:
    issuers = json.loads(ISSUERS_PATH.read_text())["issuers"]
    HOLDERS_DIR.mkdir(parents=True, exist_ok=True)
    targets = sys.argv[1:] or [i["id"] for i in issuers]
    for issuer in issuers:
        if issuer["id"] not in targets:
            continue
        seed = sum(ord(c) for c in issuer["id"])
        holders = gen_holders(issuer, seed)
        out = HOLDERS_DIR / f"{issuer['id']}.json"
        out.write_text(json.dumps({"issuer_id": issuer["id"], "holders": holders}, indent=2))
        print(f"  wrote {len(holders):4d} holders -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
