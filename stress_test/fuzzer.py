"""Property-based fuzzer for the waterfall engine.

Generates thousands of random valid CapTable instances and checks invariants
that must hold for ANY waterfall output. Failures are recorded with the
exact CapTable input that triggered them so they can be reproduced and fixed.

Invariants checked:
  I1  Engine does not raise an exception
  I2  lp_total >= 0 and finite
  I3  Tranches are sorted ascending by range_low
  I4  Tranches form a contiguous partition starting at 0
  I5  Last tranche has range_high = None
  I6  Each tranche's marginal_allocation_pct sums to ~100% (tol 0.5)
  I7  Breakpoints are sorted ascending and finite
  I8  Adjacent breakpoints don't have huge negative gaps
  I9  lp_total == sum of class LP amounts (within float tol)
  I10 total_fully_diluted_shares > 0
  I11 No NaN / inf anywhere in breakpoints or tranches
  I12 cap_reach_thresholds[X] >= LP queue total above X (cap reach can't precede LP)
  I13 chart_payload generates without crashing
  I14 build_formula_workbook generates without crashing
  I15 No tranche has all-zero allocation (means a "dead zone" — engine bug)
"""

from __future__ import annotations

import math
import random
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

# Make local src importable
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
from src.waterfall import chart_payload, compute_waterfall


FUZZ_WORKBOOK_EVERY = 50  # sample every Nth seed for workbook gen (expensive)


@dataclass
class FuzzFailure:
    seed: int
    invariant: str
    detail: str
    cap_table_summary: str
    traceback: Optional[str] = None


@dataclass
class FuzzReport:
    runs: int = 0
    successes: int = 0
    failures: list[FuzzFailure] = field(default_factory=list)

    def by_invariant(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.failures:
            out[f.invariant] = out.get(f.invariant, 0) + 1
        return out


def _rand_lp_type(rng: random.Random) -> LPType:
    return rng.choice([
        LPType.non_participating,
        LPType.non_participating,
        LPType.non_participating,  # weight non-participating heavier (real-world freq)
        LPType.participating_capped,
        LPType.participating_uncapped,
    ])


def _rand_ad(rng: random.Random) -> Optional[AntiDilution]:
    if rng.random() < 0.7:
        return AntiDilution(
            variant=rng.choice([
                AntiDilutionVariant.broad_based_weighted_average,
                AntiDilutionVariant.broad_based_weighted_average,
                AntiDilutionVariant.narrow_based_weighted_average,
                AntiDilutionVariant.full_ratchet,
            ])
        )
    return None


def pathological_cap_table(seed: int) -> CapTable:
    """Intentionally adversarial generator — extreme ratios, mixed orders of magnitude.

    Designed to stress the engine in ways a real cap table almost never would,
    to find float-precision bugs and regime-walk edge cases.
    """
    rng = random.Random(seed)
    n_preferred = rng.randint(2, 10)

    classes: list[ShareClass] = []

    # Mix orders of magnitude: tiny + huge classes
    for i in range(n_preferred):
        rank = i + 1
        # Wildly varied share counts
        shares = rng.choice([rng.randint(100, 1_000), rng.randint(10_000_000, 100_000_000)])
        # Wildly varied prices
        price = rng.choice([round(rng.uniform(0.0001, 0.01), 6),
                            round(rng.uniform(100.0, 1000.0), 4)])
        multiple = rng.choice([0.5, 1.0, 1.5, 2.0, 3.0, 5.0])
        amount = shares * price * multiple
        # Heavy participating bias to stress regime walker
        lp_type = rng.choice([
            LPType.participating_capped,
            LPType.participating_uncapped,
            LPType.non_participating,
        ])
        cap = None
        if lp_type == LPType.participating_capped:
            cap = rng.choice([1.5, 2.0, 3.0, 10.0])
        lp = LiquidationPreference(multiple=multiple, amount=amount, type=lp_type, cap_multiple=cap)
        # Conversion ratio variance (down-round like)
        conv = rng.choice([0.5, 0.8, 1.0, 1.5, 3.0])
        classes.append(ShareClass(
            name=f"Series {chr(ord('A') + i)} Preferred",
            type=ShareClassType.preferred,
            shares_outstanding=shares,
            issue_price=price,
            issue_date=date(2024 - (i % 4), 1, 1),
            seniority_rank=rank,
            liquidation_preference=lp,
            anti_dilution=_rand_ad(rng),
            conversion_ratio=conv,
        ))

    # Always at least 1 common to absorb residual
    classes.append(ShareClass(
        name="Common Stock",
        type=ShareClassType.common,
        shares_outstanding=rng.randint(100_000, 50_000_000),
        issue_price=round(rng.uniform(0.0001, 0.5), 4),
        issue_date=date(2021, 6, 1),
        seniority_rank=99,
    ))

    return CapTable(
        company=Company(name=f"Patho Co {seed}", currency="USD", currency_symbol="$"),
        share_classes=classes,
    )


def random_cap_table(seed: int) -> CapTable:
    """Generate a plausible-but-random cap table — pushes edges of the data model."""
    rng = random.Random(seed)

    n_preferred = rng.randint(1, 12)  # up to 12 series (extreme: late-stage stack)
    n_common = rng.randint(0, 4)      # may have zero common (degenerate)
    has_pool = rng.random() < 0.7
    has_reserved_pool = rng.random() < 0.4

    classes: list[ShareClass] = []

    # NOTE: data model rejects pari-passu (duplicate seniority ranks). Documented gap.
    # Generator uses unique ranks only.
    for i in range(n_preferred):
        rank = i + 1

        # Push share count edges: tiny class (5K), normal, huge (50M)
        shares = rng.choice([
            rng.randint(5_000, 50_000),       # tiny
            rng.randint(50_000, 5_000_000),   # normal
            rng.randint(5_000_000, 50_000_000),  # huge
        ])

        # Push price edges: micro ($0.001), normal, ICO-priced ($100+)
        price = rng.choice([
            round(rng.uniform(0.001, 0.10), 4),
            round(rng.uniform(0.10, 10.0), 4),
            round(rng.uniform(10.0, 250.0), 4),
        ])

        # Push multiple edges
        multiple = rng.choice([0.5, 1.0, 1.0, 1.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0])
        amount = shares * price * multiple

        lp_type = _rand_lp_type(rng)
        cap_multiple = None
        if lp_type == LPType.participating_capped:
            # include cap_multiple == 1 (degenerate: cap == LP)
            cap_multiple = rng.choice([1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0])

        lp = LiquidationPreference(
            multiple=multiple,
            amount=amount,
            type=lp_type,
            cap_multiple=cap_multiple,
        )

        # Push conversion ratio edges
        conv = rng.choice([1.0, 1.0, 1.0, 1.5, 2.0])

        classes.append(ShareClass(
            name=f"Series {chr(ord('A') + i)} Preferred",
            type=ShareClassType.preferred,
            shares_outstanding=shares,
            issue_price=price,
            issue_date=date(2024 - (i % 4), 1, 1),
            seniority_rank=rank,
            liquidation_preference=lp,
            anti_dilution=_rand_ad(rng),
            conversion_ratio=conv,
        ))

    # Common
    for i in range(n_common):
        classes.append(ShareClass(
            name=f"Common {i+1}" if n_common > 1 else "Common Stock",
            type=ShareClassType.common,
            shares_outstanding=rng.randint(100_000, 10_000_000),
            issue_price=round(rng.uniform(0.0001, 0.5), 4),
            issue_date=date(2021, 6, 1),
            seniority_rank=99,
        ))

    if has_pool:
        classes.append(ShareClass(
            name="Option Pool (Granted)",
            type=ShareClassType.option_pool_granted,
            shares_outstanding=rng.randint(100_000, 1_500_000),
            issue_price=round(rng.uniform(0.05, 2.0), 4),
            issue_date=date(2023, 1, 1),
            seniority_rank=99,
        ))

    if has_reserved_pool:
        classes.append(ShareClass(
            name="Option Pool (Reserved)",
            type=ShareClassType.option_pool_reserved,
            shares_outstanding=rng.randint(50_000, 800_000),
            issue_price=None,
            issue_date=None,
            seniority_rank=99,
        ))

    return CapTable(
        company=Company(
            name=f"Test Co {seed}",
            jurisdiction="Singapore",
            currency="USD",
            currency_symbol="$",
        ),
        share_classes=classes,
    )


def _summarize(ct: CapTable) -> str:
    parts = []
    for sc in ct.share_classes:
        if sc.type == ShareClassType.preferred:
            lp = sc.liquidation_preference
            parts.append(
                f"{sc.name} (sh={sc.shares_outstanding:,}, px=${sc.issue_price:.2f}, "
                f"LP={lp.multiple}x {lp.type.value}"
                f"{f', cap={lp.cap_multiple}x' if lp.cap_multiple else ''}, sen={sc.seniority_rank})"
            )
        else:
            parts.append(f"{sc.name} (sh={sc.shares_outstanding:,}, type={sc.type.value})")
    return " | ".join(parts)


def _is_finite(v) -> bool:
    if v is None:
        return True
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def check_invariants(seed: int, ct: CapTable, report: FuzzReport) -> None:
    """Run engine, check all invariants, accumulate failures into report."""
    summary = _summarize(ct)

    # I1 — engine doesn't raise
    try:
        wf = compute_waterfall(ct)
    except Exception as e:
        tb = traceback.format_exc()
        report.failures.append(FuzzFailure(seed, "I1_engine_crash", str(e), summary, tb))
        return

    # I2 — lp_total finite and non-negative
    if not _is_finite(wf.lp_total) or wf.lp_total < 0:
        report.failures.append(FuzzFailure(seed, "I2_lp_total_invalid", f"lp_total={wf.lp_total}", summary))

    # I9 — lp_total = sum of class LP
    expected_lp = sum(
        sc.liquidation_preference.amount
        for sc in ct.share_classes
        if sc.liquidation_preference is not None
    )
    if abs(wf.lp_total - expected_lp) > 1.0:
        report.failures.append(FuzzFailure(
            seed, "I9_lp_total_mismatch",
            f"engine={wf.lp_total:,.2f} vs sum_classes={expected_lp:,.2f}", summary
        ))

    # I10 — total FD positive
    if wf.total_fully_diluted_shares <= 0:
        report.failures.append(FuzzFailure(seed, "I10_fd_shares_zero",
                                            f"FD={wf.total_fully_diluted_shares}", summary))

    # I3, I4, I5 — tranche partition
    sorted_tr = sorted(wf.tranches, key=lambda t: t.range_low)
    if sorted_tr != list(wf.tranches):
        report.failures.append(FuzzFailure(seed, "I3_tranches_unsorted",
                                            "tranches not sorted by range_low", summary))
    if sorted_tr and sorted_tr[0].range_low != 0:
        report.failures.append(FuzzFailure(seed, "I4_first_tranche_not_at_zero",
                                            f"first range_low={sorted_tr[0].range_low}", summary))
    for i in range(len(sorted_tr) - 1):
        a, b = sorted_tr[i], sorted_tr[i + 1]
        if a.range_high is None:
            report.failures.append(FuzzFailure(
                seed, "I4_inner_tranche_unbounded",
                f"tranche {a.id} (idx {i}) has range_high=None but is not last", summary
            ))
            break
        if abs(a.range_high - b.range_low) > 0.01:
            report.failures.append(FuzzFailure(
                seed, "I4_tranche_gap",
                f"tranche {a.id}.high={a.range_high} != tranche {b.id}.low={b.range_low}", summary
            ))
            break
    if sorted_tr and sorted_tr[-1].range_high is not None:
        report.failures.append(FuzzFailure(
            seed, "I5_last_tranche_bounded",
            f"last tranche {sorted_tr[-1].id} has range_high={sorted_tr[-1].range_high}, want None",
            summary
        ))

    # I6 — allocation per tranche sums to 100
    for t in wf.tranches:
        s = sum(t.marginal_allocation_pct.values())
        if abs(s - 100.0) > 0.5:
            report.failures.append(FuzzFailure(
                seed, "I6_allocation_sum",
                f"tranche {t.id} allocations sum to {s:.4f}, want 100", summary
            ))
            break  # one tranche per seed is enough to log

    # I7, I8, I11 — breakpoint values
    for bp in wf.breakpoints:
        if not _is_finite(bp.value):
            report.failures.append(FuzzFailure(seed, "I11_bp_nonfinite",
                                                f"BP {bp.id} value={bp.value}", summary))
            break
    for i in range(len(wf.breakpoints) - 1):
        a, b = wf.breakpoints[i], wf.breakpoints[i + 1]
        if b.value < a.value - 0.01:
            report.failures.append(FuzzFailure(
                seed, "I7_breakpoints_unsorted",
                f"BP {a.id}={a.value} > BP {b.id}={b.value}", summary
            ))
            break

    # I12 — cap_reach >= senior LP total
    for class_name, cap_v in wf.cap_reach_thresholds.items():
        target = next((s for s in ct.share_classes if s.name == class_name), None)
        if target is None or target.liquidation_preference is None:
            continue
        senior_lp = sum(
            s.liquidation_preference.amount
            for s in ct.share_classes
            if (s.liquidation_preference is not None
                and s.seniority_rank < target.seniority_rank)
        )
        # cap_reach should be at or above the point where senior LPs are paid
        if cap_v < senior_lp - 1.0:
            report.failures.append(FuzzFailure(
                seed, "I12_cap_reach_before_senior_lp",
                f"{class_name} cap_reach={cap_v:,.0f} < senior_lp={senior_lp:,.0f}", summary
            ))

    # I15 — no all-zero tranche
    for t in wf.tranches:
        if all(v == 0 for v in t.marginal_allocation_pct.values()):
            # Origin tranche T0 may legitimately exist with 0% if engine generates one
            if t.range_low > 0 or (t.range_high or 0) > 0:
                report.failures.append(FuzzFailure(
                    seed, "I15_dead_zone_tranche",
                    f"tranche {t.id} ({t.range_low:,.0f}→{t.range_high:,.0f}) all-zero allocation",
                    summary
                ))
                break

    # I13 — chart_payload doesn't crash
    try:
        chart_payload(ct, wf)
    except Exception as e:
        tb = traceback.format_exc()
        report.failures.append(FuzzFailure(seed, "I13_chart_crash", str(e), summary, tb))

    # I14 — formula workbook builds (sample only — expensive)
    if seed % FUZZ_WORKBOOK_EVERY == 0:
        try:
            build_formula_workbook(ct, wf)
        except Exception as e:
            tb = traceback.format_exc()
            report.failures.append(FuzzFailure(seed, "I14_workbook_crash", str(e), summary, tb))

    report.successes += 1
    report.runs += 1


def run(n: int = 1000, base_seed: int = 1, verbose: bool = False, mode: str = "normal") -> FuzzReport:
    report = FuzzReport()
    gen = pathological_cap_table if mode == "patho" else random_cap_table
    for i in range(n):
        seed = base_seed + i
        try:
            ct = gen(seed)
        except Exception as e:
            # Generator itself failed — skip
            if verbose:
                print(f"  seed {seed}: generator error: {e}")
            continue
        check_invariants(seed, ct, report)
        if verbose and i % 100 == 99:
            print(f"  ran {i+1}/{n}, failures so far: {len(report.failures)}")
    return report


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-n", type=int, default=1000, help="number of fuzz runs")
    p.add_argument("--seed", type=int, default=1, help="base seed")
    p.add_argument("-v", action="store_true")
    p.add_argument("--mode", choices=["normal", "patho"], default="normal")
    p.add_argument("--workbook-every", type=int, default=50,
                   help="sample every Nth seed for workbook-gen invariant")
    args = p.parse_args()
    globals()["FUZZ_WORKBOOK_EVERY"] = args.workbook_every

    print(f"Fuzzing {args.n} cap tables, base seed {args.seed} ({args.mode} mode)…")
    rep = run(n=args.n, base_seed=args.seed, verbose=args.v, mode=args.mode)

    print(f"\n=== Fuzz Report ===")
    print(f"Runs: {rep.runs} | Successes: {rep.successes} | Failures: {len(rep.failures)}")
    print()
    print("Failures by invariant:")
    for inv, count in sorted(rep.by_invariant().items(), key=lambda kv: -kv[1]):
        print(f"  {inv}: {count}")

    if rep.failures:
        print("\nFirst 5 failures:")
        for f in rep.failures[:5]:
            print(f"\n  seed {f.seed} | {f.invariant}")
            print(f"    detail: {f.detail}")
            print(f"    cap table: {f.cap_table_summary}")
            if f.traceback:
                print(f"    traceback (last line): {f.traceback.strip().splitlines()[-1]}")
