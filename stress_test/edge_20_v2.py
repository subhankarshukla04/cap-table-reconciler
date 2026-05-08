"""20 NEW edge-case probes — covers ground edge_20.py missed.

Focus areas not previously probed:
- SAFEs, warrants, convertible notes attached to a cap table
- Currency variation (INR, IDR with non-USD symbols)
- Validator interactions (negative values, inconsistent LP/share/price)
- conv_ratio extremes (now that the engine reads it)
- Mixed participating-capped at multiple cap multiples
- Many-class stress (50 preferred)
- Pool granted + reserved coexistence
- Float-noise BPs at the dedup boundary
- Side-letter shape variants
- Warrants referencing nonexistent share class
- Class-name collision via case
- Cap mult equal to LP mult (NVCA-style "1×NP-or-NP-with-1× cap" no-op)
- Common at very-high price (high-vote founder share)

Run: .venv/bin/python stress_test/edge_20_v2.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.formula_workbook import build_formula_workbook
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    ConvertibleNote,
    LiquidationPreference,
    LPType,
    SAFE,
    ShareClass,
    ShareClassType,
    SideLetter,
    Warrant,
)
from src.waterfall import compute_waterfall


def co(name="EdgeCo", currency="USD", symbol="$"):
    return Company(name=name, jurisdiction="Singapore", currency=currency, currency_symbol=symbol)


def C(name, shares, price=0.001, rank=99):
    return ShareClass(
        name=name, type=ShareClassType.common, shares_outstanding=shares,
        issue_price=price, issue_date=date(2020, 1, 1), seniority_rank=rank,
    )


def P(name, shares, price, rank, mult=1.0, lp_type=LPType.non_participating,
      cap_mult=None, cap_amt=None, conv=1.0):
    return ShareClass(
        name=name, type=ShareClassType.preferred, shares_outstanding=shares,
        issue_price=price, issue_date=date(2021, 1, 1), seniority_rank=rank,
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
        issue_date=date(2022, 1, 1) if granted else None, seniority_rank=99,
    )


@dataclass
class Probe:
    n: int
    name: str
    desc: str
    builder: callable
    expect: str = "pass"


PROBES: list[Probe] = []


def add(n, name, desc, expect="pass"):
    def deco(fn):
        PROBES.append(Probe(n, name, desc, fn, expect))
        return fn
    return deco


# ============================================================================

@add(21, "INR-currency-with-rupee", "Rupee-denominated cap table — currency symbol roundtrip.")
def e21():
    return CapTable(
        company=co("Bharat AI", currency="INR", symbol="₹"),
        share_classes=[
            C("Promoter", 5_000_000, price=10),
            P("Series A CCPS", 1_000_000, 100.0, 1, mult=1.5),
        ],
    )


@add(22, "IDR-billion-amounts", "Indonesian Rupiah — values in billions, float precision.")
def e22():
    return CapTable(
        company=co("PT Tokovel", currency="IDR", symbol="Rp"),
        share_classes=[
            C("Founders", 4_000_000, price=1000),
            P("Series A", 1_000_000, 50_000.0, 1, mult=1.0,
              lp_type=LPType.participating_capped, cap_mult=2.0),
        ],
    )


@add(23, "warrant-on-existing-class", "Outstanding warrant referencing existing common class.")
def e23():
    ct = CapTable(
        company=co(),
        share_classes=[
            C("Common", 5_000_000),
            P("Series A", 1_000_000, 1.0, 1, mult=1.0),
        ],
        warrants_outstanding=[
            Warrant(id="W1", holder="Hercules Capital", shares=100_000,
                    share_class="Common", strike_price=0.50,
                    issue_date=date(2024, 1, 1)),
        ],
    )
    return ct


@add(24, "warrant-references-nonexistent-class", "Warrant points to a class that doesn't exist.")
def e24():
    return CapTable(
        company=co(),
        share_classes=[C("Common", 5_000_000), P("Series A", 1_000_000, 1.0, 1)],
        warrants_outstanding=[
            Warrant(id="W1", holder="Pinnacle", shares=50_000,
                    share_class="Series Z (DNE)", strike_price=1.0),
        ],
    )


@add(25, "unconverted-safe", "Outstanding SAFE that hasn't converted — should not affect waterfall.")
def e25():
    return CapTable(
        company=co(),
        share_classes=[C("Common", 5_000_000), P("Series A", 1_000_000, 1.0, 1)],
        safes_outstanding=[
            SAFE(id="SAFE-1", principal=500_000, valuation_cap=10_000_000,
                 discount_rate=0.20, issue_date=date(2023, 6, 1)),
        ],
    )


@add(26, "conv-note-no-cap", "Convertible note with discount but no cap.")
def e26():
    return CapTable(
        company=co(),
        share_classes=[C("Common", 5_000_000), P("Series A", 1_000_000, 1.0, 1)],
        convertible_notes_outstanding=[
            ConvertibleNote(id="CN-1", principal=750_000, discount_rate=0.25,
                            interest_rate=0.06, issue_date=date(2023, 1, 1)),
        ],
    )


@add(27, "duplicate-class-name-case", "Class names 'Common' and 'common' (case differs).")
def e27():
    return CapTable(
        company=co(),
        share_classes=[
            C("Common", 5_000_000),
            C("common", 1_000_000),  # case differs
            P("Series A", 1_000_000, 1.0, 1),
        ],
    )


@add(28, "exact-duplicate-class-name", "Two classes named exactly 'Common' — validator should reject.",
     expect="validator_reject")
def e28():
    return CapTable(
        company=co(),
        share_classes=[
            C("Common", 5_000_000), C("Common", 1_000_000),
            P("Series A", 1_000_000, 1.0, 1),
        ],
    )


@add(29, "negative-shares", "Negative shares_outstanding — validator must reject.",
     expect="validator_reject")
def e29():
    return CapTable(company=co(), share_classes=[C("Common", -1_000_000)])


@add(30, "preferred-without-LP-rejected", "Preferred type with liquidation_preference=None — reject.",
     expect="validator_reject")
def e30():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        ShareClass(name="Series A", type=ShareClassType.preferred,
                   shares_outstanding=1_000_000, issue_price=1.0,
                   seniority_rank=1, liquidation_preference=None),
    ])


@add(31, "common-with-LP-rejected", "Common type carrying a liquidation_preference — reject.",
     expect="validator_reject")
def e31():
    bogus_lp = LiquidationPreference(multiple=1.0, amount=1_000_000, type=LPType.non_participating)
    return CapTable(company=co(), share_classes=[
        ShareClass(name="Common", type=ShareClassType.common,
                   shares_outstanding=5_000_000, issue_price=0.001,
                   seniority_rank=99, liquidation_preference=bogus_lp),
    ])


@add(32, "fifty-preferred-stack", "50 NP preferred — extreme stack, perf + correctness.")
def e32():
    classes = [C("Common", 1_000_000)]
    classes += [P(f"Series {i:02d}", 100_000, 1.0 + i * 0.1, 50 - i + 1) for i in range(50)]
    return CapTable(company=co(), share_classes=classes)


@add(33, "extreme-conv-ratio-100", "Triggered ratchet pushes conv_ratio to 100 (post-down-round catastrophe).")
def e33():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A (post-ratchet)", 100_000, 1.0, 1, conv=100.0),
    ])


@add(34, "conv-ratio-tiny-fraction", "conv_ratio=0.01 (1:100 reverse split — preferred barely contributes).")
def e34():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 5_000_000, 1.0, 1, conv=0.01),
    ])


@add(35, "two-pools-granted-and-reserved", "Both granted and reserved option pools coexist.")
def e35():
    return CapTable(company=co(), share_classes=[
        C("Founders", 4_000_000),
        Pool("Pool granted", 800_000, granted=True),
        Pool("Pool reserved", 1_200_000, granted=False),
        P("Series A", 1_000_000, 1.0, 1),
    ])


@add(36, "mixed-cap-multiples", "Three classes participating-capped at 1.5×, 2×, 3× — different cap reaches.")
def e36():
    return CapTable(company=co(), share_classes=[
        C("Common", 4_000_000),
        P("Seed", 500_000, 0.50, 3, lp_type=LPType.participating_capped, cap_mult=3.0),
        P("Series A", 1_000_000, 1.00, 2, lp_type=LPType.participating_capped, cap_mult=2.0),
        P("Series B", 800_000, 2.00, 1, lp_type=LPType.participating_capped, cap_mult=1.5),
    ])


@add(37, "high-priced-common", "Common at $1000/share (insider founder shares with valuation step-up).")
def e37():
    return CapTable(company=co(), share_classes=[
        C("Founders Class B", 50_000, price=1000.0),
        C("Employee Common", 1_000_000, price=0.10),
        P("Series A", 200_000, 50.0, 1, mult=1.0),
    ])


@add(38, "cap-mult-equals-lp-mult", "2× LP with 2× cap — degenerate (cap = LP, no participation residual).")
def e38():
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A", 1_000_000, 1.0, 1, mult=2.0,
          lp_type=LPType.participating_capped, cap_mult=1.0),  # cap_mult applies to LP_amount
    ])


@add(39, "side-letter-empty-body", "Side letter with no body, just title.")
def e39():
    return CapTable(
        company=co(),
        share_classes=[C("Common", 5_000_000), P("Series A", 1_000_000, 1.0, 1)],
        side_letters=[SideLetter(id="SL-1", title="Pro-rata rights — Series A")],
    )


@add(40, "BPs-near-dedup-tolerance", "Engineered BPs near $0.01 absolute tolerance (relative-tol path).")
def e40():
    # Two preferred at almost-identical LP amounts — close LP BPs at small scale
    return CapTable(company=co(), share_classes=[
        C("Common", 5_000_000),
        P("Series A1", 999_999, 1.0, 2, mult=1.0),  # LP = $999,999
        P("Series A2", 1_000_000, 1.0, 1, mult=1.0),  # LP = $1,000,000
    ])


# ============================================================================


def run():
    print(f"{'#':>3} {'name':<40} {'expect':<18} status   notes")
    print("-" * 130)

    for p in PROBES:
        try:
            ct = p.builder()
        except Exception as e:
            ok = (p.expect == "validator_reject")
            mark = "OK " if ok else "BAD"
            print(f"{p.n:>3} {p.name:<40} {p.expect:<18} {mark} VALIDATOR_REJECT  {type(e).__name__}: {str(e).split(chr(10))[0][:70]}")
            continue

        try:
            wr = compute_waterfall(ct)
        except Exception as e:
            mark = "BAD"
            print(f"{p.n:>3} {p.name:<40} {p.expect:<18} {mark} ENGINE_CRASH      {type(e).__name__}: {str(e).split(chr(10))[0][:70]}")
            continue

        notes = []
        if wr.lp_total < 0 or wr.lp_total != wr.lp_total:
            notes.append(f"lp_total={wr.lp_total}")
        if not wr.tranches:
            notes.append("no tranches")
        for tr in wr.tranches:
            tot = sum(tr.marginal_allocation_pct.values())
            if abs(tot - 100.0) > 0.5 and tot != 0:
                notes.append(f"{tr.id} alloc sum {tot:.2f}")
            if tot == 0 and tr.range_high is not None:
                notes.append(f"{tr.id} ZERO-alloc tranche [{tr.range_low:.0f},{tr.range_high:.0f}]")
        bps = [bp.value for bp in wr.breakpoints]
        if bps != sorted(bps):
            notes.append("BPs not sorted")
        # check infinity
        for bp in wr.breakpoints:
            if bp.value != bp.value or bp.value == float("inf") or bp.value == float("-inf"):
                notes.append(f"{bp.id} non-finite")

        try:
            wb = build_formula_workbook(ct, wr)
        except Exception as e:
            notes.append(f"workbook crash: {type(e).__name__}: {str(e)[:50]}")

        if notes:
            mark = "BAD"
            status = "ENGINE_RAN_BUT"
            note = "; ".join(notes[:3])
        else:
            mark = "OK "
            status = f"clean ({len(wr.breakpoints)} BPs, {len(wr.tranches)} tr, {wr.lp_total:,.0f} LP)"
            note = ""

        if p.expect != "pass" and mark == "OK ":
            mark = "??"
        print(f"{p.n:>3} {p.name:<40} {p.expect:<18} {mark} {status:<35} {note}")


if __name__ == "__main__":
    run()
