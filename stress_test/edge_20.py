"""20 hand-built edge-case probes against the engine + data model.

Built blind. Each scenario tests a real-world edge the analyst at Evelyn's
team might hit: degenerate structures, boundary conditions, oddly-shaped
cap tables. We do NOT design these to fit the engine.

Run: .venv/bin/python stress_test/edge_20.py
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.formula_workbook import build_formula_workbook
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.waterfall import compute_waterfall


def co(name: str = "EdgeCo") -> Company:
    return Company(name=name, jurisdiction="Singapore", currency="USD", currency_symbol="$")


def C(name: str, shares: int, rank: int = 99, price: float = 0.001) -> ShareClass:
    return ShareClass(
        name=name, type=ShareClassType.common,
        shares_outstanding=shares, issue_price=price,
        issue_date=date(2020, 1, 1), seniority_rank=rank,
    )


def P(name, shares, price, rank, mult=1.0, lp_type=LPType.non_participating,
      cap_mult=None, cap_amt=None, conv=1.0):
    return ShareClass(
        name=name, type=ShareClassType.preferred,
        shares_outstanding=shares, issue_price=price,
        issue_date=date(2021, 1, 1), seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=mult, amount=shares * price * mult,
            type=lp_type, cap_multiple=cap_mult, cap_amount=cap_amt,
        ),
        conversion_ratio=conv,
    )


def Pool(name, shares, granted=True):
    return ShareClass(
        name=name,
        type=ShareClassType.option_pool_granted if granted else ShareClassType.option_pool_reserved,
        shares_outstanding=shares, issue_price=0.10 if granted else None,
        issue_date=date(2022, 1, 1) if granted else None,
        seniority_rank=99,
    )


@dataclass
class Probe:
    n: int
    name: str
    desc: str
    builder: callable
    expect: str  # "pass", "validator_reject", "engine_should_handle"


PROBES: list[Probe] = []


def add(n, name, desc, expect="pass"):
    def deco(fn):
        PROBES.append(Probe(n, name, desc, fn, expect))
        return fn
    return deco


# ============================================================================

@add(1, "founders-only", "Pre-money common only — two founders, no preferred.")
def e1():
    return CapTable(company=co("FounderCo"), share_classes=[
        C("Founder A", 5_000_000), C("Founder B", 5_000_000),
    ])


@add(2, "preferred-only-no-common", "Series A only — common entirely zeroed out (anomaly but legal).")
def e2():
    return CapTable(company=co(), share_classes=[
        C("Common", 0), P("Series A", 1_000_000, 1.00, 1),
    ])


@add(3, "massive-option-pool", "60% of fully-diluted is option pool granted (employee co).")
def e3():
    return CapTable(company=co(), share_classes=[
        C("Founder", 2_000_000), Pool("Pool granted", 6_000_000),
        P("Series A", 2_000_000, 1.00, 1),
    ])


@add(4, "zero-option-pool", "No options of any kind — pure equity.")
def e4():
    return CapTable(company=co(), share_classes=[
        C("Founders", 5_000_000),
        P("Series A", 2_000_000, 1.00, 1),
    ])


@add(5, "stock-split-conv-ratio-2", "Pre-IPO 2:1 split — Series A conv_ratio=2.0 (gets 2 shares per share).")
def e5():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 1, conv=2.0),
    ])


@add(6, "reverse-split-conv-half", "Reverse split — conv_ratio=0.5 (each preferred → 0.5 common).")
def e6():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 2_000_000, 1.00, 1, conv=0.5),
    ])


@add(7, "all-uncapped-participating", "Stack of 3 participating-uncapped — pure dual-dip nightmare.")
def e7():
    return CapTable(company=co(), share_classes=[
        C("Common", 4_000_000),
        P("Seed", 1_000_000, 0.50, 3, lp_type=LPType.participating_uncapped),
        P("Series A", 1_500_000, 1.00, 2, lp_type=LPType.participating_uncapped),
        P("Series B", 1_000_000, 2.00, 1, lp_type=LPType.participating_uncapped),
    ])


@add(8, "inverted-senior-NP-junior-participating", "Senior is non-participating, junior is participating-uncapped.")
def e8():
    return CapTable(company=co(), share_classes=[
        C("Common", 4_000_000),
        P("Seed", 1_000_000, 0.50, 2, lp_type=LPType.participating_uncapped),
        P("Series A", 1_500_000, 1.00, 1, lp_type=LPType.non_participating),
    ])


@add(9, "cap-multiple-exactly-1", "participating_capped with cap_multiple=1.0 (E1 boundary).")
def e9():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 1, lp_type=LPType.participating_capped, cap_mult=1.0),
    ])


@add(10, "both-cap-amount-and-multiple", "cap_amount AND cap_multiple both set — undefined-precedence.")
def e10():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 1, lp_type=LPType.participating_capped,
          cap_mult=2.0, cap_amt=5_000_000),
    ])


@add(11, "tiny-shares-precision", "1 share per class — float precision floor.")
def e11():
    return CapTable(company=co(), share_classes=[
        C("Common", 1),
        P("Series A", 1, 1_000_000.0, 1),
    ])


@add(12, "huge-shares-billion", "5 billion shares Series H — float precision ceiling.")
def e12():
    return CapTable(company=co(), share_classes=[
        C("Common", 100_000_000),
        P("Series H", 5_000_000_000, 1.50, 1),
    ])


@add(13, "lp-amount-zero-multiple-zero", "LP multiple=0, amount=0 — preferred with no LP (degenerate).")
def e13():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 1, mult=0.0),
    ])


@add(14, "participating-uncapped-with-zero-LP", "LP=0 but participating-uncapped (LP-free dual-dip).")
def e14():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 1, mult=0.0, lp_type=LPType.participating_uncapped),
    ])


@add(15, "cap-below-LP", "3x participating with cap=1.5x — cap below LP itself (broken term).",
     expect="validator_reject")
def e15():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 1, mult=3.0,
          lp_type=LPType.participating_capped, cap_mult=1.5),
    ])


@add(16, "ten-preferred-deep-stack", "10 NP preferred, no common, no pool — pure preferred stack.")
def e16():
    return CapTable(company=co(), share_classes=[
        C("Common", 1_000_000),  # need at least 1 common for waterfall
    ] + [P(f"Series {chr(ord('A')+i)}", 100_000, 1.0 + i*0.5, 10-i) for i in range(10)])


@add(17, "pool-granted-only-no-common", "No issued common — only option pool granted + preferred.")
def e17():
    return CapTable(company=co(), share_classes=[
        Pool("Pool", 2_000_000),
        P("Series A", 1_000_000, 1.00, 1),
    ])


@add(18, "rank-gap-50", "Single preferred with seniority_rank=50 (gap in numbering).")
def e18():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.00, 50),
    ])


@add(19, "duplicate-rank-pari-passu", "B-1 and B-2 both rank=2 (intended pari passu).",
     expect="validator_reject")
def e19():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 500_000, 0.50, 1),
        P("Series B-1", 500_000, 1.00, 2),
        P("Series B-2", 500_000, 1.00, 2),
    ])


@add(20, "negative-issue-price", "Issue price = 0 (free shares from advisory grant).",
     expect="pass")
def e20():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 0.0, 1, mult=1.0),
    ])


# ============================================================================


def run():
    print(f"{'#':>2} {'name':<40} {'expect':<20} status   notes")
    print("-" * 120)

    for p in PROBES:
        try:
            ct = p.builder()
        except Exception as e:
            status = "VALIDATOR_REJECT"
            note = type(e).__name__ + ": " + str(e).split("\n")[0][:80]
            ok = (p.expect == "validator_reject")
            mark = "OK " if ok else "BAD"
            print(f"{p.n:>2} {p.name:<40} {p.expect:<20} {mark} {status:<18} {note}")
            continue

        try:
            wr = compute_waterfall(ct)
        except Exception as e:
            status = "ENGINE_CRASH"
            note = type(e).__name__ + ": " + str(e).split("\n")[0][:80]
            mark = "BAD"
            print(f"{p.n:>2} {p.name:<40} {p.expect:<20} {mark} {status:<18} {note}")
            continue

        # invariants
        notes = []
        if wr.lp_total < 0 or wr.lp_total != wr.lp_total:  # NaN
            notes.append(f"lp_total={wr.lp_total}")
        if not wr.tranches:
            notes.append("no tranches")
        for tr in wr.tranches:
            tot = sum(tr.marginal_allocation_pct.values())
            if abs(tot - 100.0) > 0.5 and tot != 0:
                notes.append(f"{tr.id} alloc sum {tot:.2f}")
            if tot == 0 and tr.range_high is not None:
                notes.append(f"{tr.id} ZERO-alloc tranche [{tr.range_low:.0f}, {tr.range_high:.0f}]")
        bps = [bp.value for bp in wr.breakpoints]
        if bps != sorted(bps):
            notes.append("BPs not sorted")

        # workbook
        try:
            wb = build_formula_workbook(ct, wr)
        except Exception as e:
            notes.append(f"workbook crash: {type(e).__name__}: {str(e)[:60]}")

        if notes:
            mark = "BAD"
            status = "ENGINE_RAN_BUT"
            note = "; ".join(notes[:3])
        else:
            mark = "OK "
            status = f"clean ({len(wr.breakpoints)} BPs, {len(wr.tranches)} tr, ${wr.lp_total:,.0f} LP)"
            note = ""

        ok = (p.expect == "pass" and mark == "OK ")
        if p.expect != "pass" and mark == "OK ":
            mark = "??"  # passed but expected to be rejected — interesting
        print(f"{p.n:>2} {p.name:<40} {p.expect:<20} {mark} {status:<35} {note}")


if __name__ == "__main__":
    run()
