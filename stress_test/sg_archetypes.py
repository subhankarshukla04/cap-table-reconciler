"""10 Singapore-flavored cap-table archetypes pulled from real deal patterns.

Each is a fictional company built using publicly-known structural patterns from
Singapore / SEA tech deals (Sea, Grab, Carousell, Ninja Van, Xendit, Akulaku,
Ruangguru, etc.) — not literal cap tables of those companies but the structural
DNA. None of these were built with the engine in mind; they're pushed through
the engine blind to see where it holds up and where it breaks.

Sources for structural patterns:
- VIMA (Venture Investing Model Agreements, SVCA) — Singapore standard
- TechInAsia / DealStreetAsia public deal coverage
- NVCA Model Charter (US backbone)
- Companies Act 2013 (India CCPS) for cross-border
- Public S-1 / IPO prospectus filings (Sea, Grab)

Run with: .venv/bin/python stress_test/sg_archetypes.py
"""

from __future__ import annotations

import json
import sys
import traceback
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
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.waterfall import compute_waterfall


def _bbwa() -> AntiDilution:
    return AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average)


def _common(name: str, shares: int, price: float = 0.001, when: date = date(2018, 1, 1)) -> ShareClass:
    return ShareClass(
        name=name, type=ShareClassType.common,
        shares_outstanding=shares, issue_price=price, issue_date=when,
        seniority_rank=99,
    )


def _pref(
    name: str, shares: int, price: float, rank: int, when: date,
    multiple: float = 1.0, lp_type: LPType = LPType.non_participating,
    cap_multiple: float | None = None, conv: float = 1.0,
    ad_variant: AntiDilutionVariant = AntiDilutionVariant.broad_based_weighted_average,
) -> ShareClass:
    return ShareClass(
        name=name, type=ShareClassType.preferred,
        shares_outstanding=shares, issue_price=price, issue_date=when,
        seniority_rank=rank,
        liquidation_preference=LiquidationPreference(
            multiple=multiple, amount=shares * price * multiple,
            type=lp_type, cap_multiple=cap_multiple,
        ),
        anti_dilution=AntiDilution(variant=ad_variant),
        conversion_ratio=conv,
    )


def _pool(name: str, shares: int, granted: bool = True) -> ShareClass:
    return ShareClass(
        name=name,
        type=ShareClassType.option_pool_granted if granted else ShareClassType.option_pool_reserved,
        shares_outstanding=shares,
        issue_price=0.10 if granted else None,
        issue_date=date(2022, 6, 1) if granted else None,
        seniority_rank=99,
    )


# ============================================================================
# 10 archetypes — each is a complete, plausible Singapore-flavored cap table.
# ============================================================================


def a1_super_app_late_stage() -> CapTable:
    """A1: Super-app (Grab/Sea style) — many late-stage rounds, mixed terms.

    7 preferred classes (Seed → Series F), strategic Tencent-style at Series D
    with 1.5x non-participating, SoftBank-style at Series E with 1x participating-
    capped at 2x. Pre-IPO Series F at 1x non-participating large round.
    """
    return CapTable(
        company=Company(name="Velocita Pte. Ltd.", jurisdiction="Singapore",
                        sector="Super-app (mobility + payments)", currency="USD",
                        currency_symbol="$"),
        share_classes=[
            _common("Founders Common (Class B)", 28_000_000, 0.001, date(2018, 1, 15)),
            _pool("ESOP Granted", 4_500_000),
            _pool("ESOP Reserved", 2_000_000, granted=False),
            _pref("Series Seed", 6_000_000, 0.50, rank=7, when=date(2018, 8, 1)),
            _pref("Series A", 8_000_000, 1.20, rank=6, when=date(2019, 5, 12)),
            _pref("Series B", 10_000_000, 2.80, rank=5, when=date(2020, 4, 8)),
            _pref("Series C", 12_000_000, 5.50, rank=4, when=date(2021, 3, 22)),
            _pref("Series D (Tencent strategic)", 14_000_000, 9.00, rank=3,
                  when=date(2022, 2, 14), multiple=1.5),
            _pref("Series E (SoftBank Vision)", 18_000_000, 12.50, rank=2,
                  when=date(2023, 6, 30), lp_type=LPType.participating_capped,
                  cap_multiple=2.0),
            _pref("Series F (Pre-IPO)", 22_000_000, 15.00, rank=1,
                  when=date(2024, 9, 18)),
        ],
    )


def a2_indo_fintech_topco() -> CapTable:
    """A2: Indonesian fintech with Singapore TopCo (Xendit/Akulaku style).

    Common + Series Seed/A/B/C. Strategic at Series B from a Japanese megabank
    with 1x participating-uncapped. Series C lead is Tiger Global with standard
    1x non-participating. Pre-A bridge SAFE converted at Series A.
    """
    return CapTable(
        company=Company(name="Bayar Sekarang Pte. Ltd.",
                        jurisdiction="Singapore (operating: PT in Indonesia)",
                        sector="B2B payments", currency="USD", currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 12_000_000, 0.0001, date(2019, 3, 1)),
            _common("Pre-seed advisor common", 600_000, 0.05, date(2019, 8, 1)),
            _pool("ESOP Granted", 1_800_000),
            _pref("Series Seed", 3_500_000, 0.40, rank=4, when=date(2020, 2, 15)),
            _pref("Series A", 5_500_000, 1.10, rank=3, when=date(2021, 6, 30)),
            _pref("Series B (MUFG strategic)", 4_800_000, 2.60, rank=2,
                  when=date(2022, 11, 10), lp_type=LPType.participating_uncapped),
            _pref("Series C (Tiger Global)", 7_200_000, 4.80, rank=1,
                  when=date(2024, 1, 22)),
        ],
    )


def a3_b2b_saas_clean_stack() -> CapTable:
    """A3: Clean B2B SaaS with US VC stack (PatSnap / Carousell style).

    Vanilla 4-round stack, all 1x non-participating, BBWA. The "clean" baseline
    that the engine should handle without breaking a sweat — but with realistic
    SEA share-count scale.
    """
    return CapTable(
        company=Company(name="Lattice Cloud Pte. Ltd.", jurisdiction="Singapore",
                        sector="B2B SaaS (HR analytics)", currency="USD",
                        currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 8_000_000, 0.001, date(2020, 1, 10)),
            _pool("ESOP Granted", 1_200_000),
            _pool("ESOP Reserved", 800_000, granted=False),
            _pref("Series Seed", 2_500_000, 0.80, rank=4, when=date(2021, 4, 20)),
            _pref("Series A (Sequoia SEA)", 3_000_000, 2.40, rank=3,
                  when=date(2022, 8, 15)),
            _pref("Series B (Vertex Ventures)", 3_500_000, 5.20, rank=2,
                  when=date(2024, 3, 8)),
            _pref("Series C (Insight Partners)", 4_000_000, 8.75, rank=1,
                  when=date(2025, 11, 30)),
        ],
    )


def a4_climate_deeptech_safe_heavy() -> CapTable:
    """A4: Climate deep-tech, SAFE-heavy seed, Series A priced.

    Founders + multiple seed-stage SAFEs (modeled as converted into Series Seed
    Preferred). Series A 1x non-participating with full-ratchet AD.
    """
    return CapTable(
        company=Company(name="Carbonix Labs Pte. Ltd.",
                        jurisdiction="Singapore", sector="Climate / direct air capture",
                        currency="USD", currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 6_000_000, 0.0001, date(2022, 3, 1)),
            _common("Co-founder #2 separate", 2_000_000, 0.0001, date(2022, 6, 15)),
            _pool("ESOP Granted", 900_000),
            _pref("Series Seed (5 SAFE conversions)", 4_200_000, 0.65,
                  rank=2, when=date(2024, 4, 4)),
            _pref("Series A (Temasek climate)", 6_500_000, 1.95, rank=1,
                  when=date(2025, 9, 12), ad_variant=AntiDilutionVariant.full_ratchet),
        ],
    )


def a5_logistics_late_stage_8_rounds() -> CapTable:
    """A5: Logistics with 8-round preferred stack (Ninja Van / J&T style).

    Many rounds, no participation, mixed multiples. Series G strategic from
    a regional postal authority with 2x non-participating. Stress-tests the
    engine on a long preferred chain.
    """
    when = lambda y, m: date(y, m, 1)
    return CapTable(
        company=Company(name="ParcelPath Pte. Ltd.", jurisdiction="Singapore",
                        sector="Last-mile logistics", currency="USD",
                        currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 18_000_000, 0.001, when(2017, 1)),
            _pool("ESOP Granted", 3_000_000),
            _pref("Series Seed", 5_000_000, 0.30, rank=8, when=when(2017, 11)),
            _pref("Series A", 6_500_000, 0.85, rank=7, when=when(2018, 6)),
            _pref("Series B", 8_000_000, 1.80, rank=6, when=when(2019, 4)),
            _pref("Series C", 10_000_000, 3.20, rank=5, when=when(2020, 2)),
            _pref("Series D", 12_000_000, 5.50, rank=4, when=when(2021, 1)),
            _pref("Series E", 14_000_000, 8.00, rank=3, when=when(2022, 5)),
            _pref("Series F", 16_000_000, 10.50, rank=2, when=when(2023, 8)),
            _pref("Series G (SingPost strategic)", 9_000_000, 12.00, rank=1,
                  when=when(2025, 3), multiple=2.0),
        ],
    )


def a6_edtech_bridge_round() -> CapTable:
    """A6: Edtech with post-2022 bridge round between Series B and C.

    Bridge structured as Series B-1 (1.5x non-participating) — common pattern
    when the company can't raise a full Series C at the prior valuation but
    needs runway. Tests pari-passu... wait, model rejects pari-passu, so I
    structure the bridge with a separate seniority rank.
    """
    return CapTable(
        company=Company(name="Skillbridge Asia Pte. Ltd.",
                        jurisdiction="Singapore", sector="Edtech (test-prep)",
                        currency="USD", currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 7_000_000, 0.001, date(2019, 5, 1)),
            _common("Acqui-hire common (CTO)", 800_000, 0.10, date(2021, 3, 1)),
            _pool("ESOP Granted", 1_400_000),
            _pref("Series Seed", 3_000_000, 0.50, rank=5, when=date(2020, 1, 15)),
            _pref("Series A", 4_500_000, 1.40, rank=4, when=date(2021, 7, 22)),
            _pref("Series B", 5_500_000, 3.20, rank=3, when=date(2022, 11, 8)),
            _pref("Series B-1 (bridge, sweetened)", 2_500_000, 3.20, rank=2,
                  when=date(2024, 5, 16), multiple=1.5),
            _pref("Series C (down-flat)", 6_500_000, 3.00, rank=1,
                  when=date(2025, 8, 30), ad_variant=AntiDilutionVariant.full_ratchet),
        ],
    )


def a7_crypto_token_equity_dual() -> CapTable:
    """A7: Crypto/Web3 with multi-cap SAFE seed + Series A token+equity.

    Multiple Seed SAFEs at different valuation caps converted into Series Seed
    classes (each cap = different priced Seed). Series A from crypto-native
    fund. Token-warrant economics modeled as simple participating-capped.
    """
    return CapTable(
        company=Company(name="Trireme Protocol Pte. Ltd.",
                        jurisdiction="Singapore", sector="Web3 infrastructure",
                        currency="USD", currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 10_000_000, 0.0001, date(2021, 6, 1)),
            _pool("ESOP Granted", 1_500_000),
            _pref("Series Seed-1 ($8M cap SAFE conv)", 1_200_000, 0.40,
                  rank=4, when=date(2022, 3, 10)),
            _pref("Series Seed-2 ($15M cap SAFE conv)", 1_400_000, 0.85,
                  rank=3, when=date(2022, 9, 1)),
            _pref("Series A (Pantera + Paradigm)", 5_000_000, 2.20, rank=2,
                  when=date(2024, 1, 8), lp_type=LPType.participating_capped,
                  cap_multiple=3.0),
            _pref("Series B (a16z crypto)", 6_500_000, 4.50, rank=1,
                  when=date(2025, 6, 22)),
        ],
    )


def a8_acquihire_corporate_spinout() -> CapTable:
    """A8: Corporate spinout with parent-co founder shares + new VC preferred.

    Singapore parent corp spins out a subsidiary, takes founder shares.
    External VCs come in at Series A (1x non-participating) and Series B
    (1.5x non-participating) — typical spinout pattern where parent retains
    significant common.
    """
    return CapTable(
        company=Company(name="Aether Robotics Pte. Ltd.",
                        jurisdiction="Singapore", sector="Industrial robotics spinout",
                        currency="USD", currency_symbol="$"),
        share_classes=[
            _common("ParentCo Common (Singapore Tech Holdings)", 15_000_000, 0.01,
                    date(2023, 8, 1)),
            _common("Spinout management common", 4_000_000, 0.10, date(2023, 8, 1)),
            _pool("ESOP Granted", 2_000_000),
            _pref("Series A (East Ventures + Wavemaker)", 6_000_000, 1.50,
                  rank=2, when=date(2024, 6, 18)),
            _pref("Series B (B Capital strategic)", 8_000_000, 3.00, rank=1,
                  when=date(2025, 11, 12), multiple=1.5),
        ],
    )


def a9_pre_ipo_pipe_round() -> CapTable:
    """A9: Pre-IPO PIPE round with massive late-stage capital.

    Mature company on IPO path. Series F (Pre-IPO) at 1x non-participating but
    with conversion ratio adjusted for stock split (post-1.5:1). Tests
    conv_ratio handling.
    """
    return CapTable(
        company=Company(name="Marina Bay Health Pte. Ltd.",
                        jurisdiction="Singapore", sector="Digital health",
                        currency="USD", currency_symbol="$"),
        share_classes=[
            _common("Founders Common", 30_000_000, 0.0001, date(2017, 3, 1)),
            _pool("ESOP Granted", 6_000_000),
            _pool("ESOP Reserved", 3_000_000, granted=False),
            _pref("Series Seed", 8_000_000, 0.25, rank=6, when=date(2017, 9, 1)),
            _pref("Series A", 10_000_000, 0.85, rank=5, when=date(2018, 11, 1)),
            _pref("Series B", 12_000_000, 2.40, rank=4, when=date(2020, 5, 1)),
            _pref("Series C (with 1.5:1 stock-split adj)", 14_000_000, 5.00,
                  rank=3, when=date(2021, 8, 1), conv=1.5),
            _pref("Series D", 16_000_000, 8.50, rank=2, when=date(2023, 4, 1)),
            _pref("Series E (Pre-IPO PIPE)", 24_000_000, 12.00, rank=1,
                  when=date(2025, 10, 15)),
        ],
    )


def a10_distressed_recap() -> CapTable:
    """A10: Distressed recapitalization — punitive Series D wipes out juniors.

    Company that survived a near-death event in 2024. New lead (Series D) at
    deeply punitive terms: 2x participating-capped at 5x cap, full-ratchet AD
    that triggers and tanks Series A/B/C conversion ratios. Tests the engine
    on AD-triggered conversion-ratio adjustments combined with participating-cap.

    Note: AD-triggered ratchet is encoded by setting the affected class's
    conv_ratio > 1 (more shares post-conversion). The model accepts this; the
    waterfall engine should respect it in the conversion math.
    """
    return CapTable(
        company=Company(name="Nimbus Cargo Pte. Ltd.",
                        jurisdiction="Singapore", sector="B2B air cargo (distressed)",
                        currency="USD", currency_symbol="$"),
        share_classes=[
            _common("Founders Common (heavily diluted)", 5_000_000, 0.001,
                    date(2019, 2, 1)),
            _pool("ESOP Granted", 800_000),
            _pref("Series Seed (post-ratchet)", 3_500_000, 0.40, rank=5,
                  when=date(2020, 3, 1), conv=2.5,
                  ad_variant=AntiDilutionVariant.full_ratchet),
            _pref("Series A (post-ratchet)", 4_200_000, 1.20, rank=4,
                  when=date(2021, 6, 1), conv=2.0,
                  ad_variant=AntiDilutionVariant.full_ratchet),
            _pref("Series B (post-ratchet)", 5_000_000, 2.80, rank=3,
                  when=date(2022, 9, 1), conv=1.5,
                  ad_variant=AntiDilutionVariant.full_ratchet),
            _pref("Series C (modest ratchet)", 6_000_000, 4.50, rank=2,
                  when=date(2023, 11, 1), conv=1.2),
            _pref("Series D (distressed recap)", 18_000_000, 0.80, rank=1,
                  when=date(2025, 4, 15), multiple=2.0,
                  lp_type=LPType.participating_capped, cap_multiple=5.0,
                  ad_variant=AntiDilutionVariant.full_ratchet),
        ],
    )


# ============================================================================
# Test runner
# ============================================================================

ARCHETYPES = [
    ("A1", "Super-app late stage (Grab/Sea-flavored)", a1_super_app_late_stage),
    ("A2", "Indonesian fintech Singapore TopCo", a2_indo_fintech_topco),
    ("A3", "Clean B2B SaaS with US VC stack", a3_b2b_saas_clean_stack),
    ("A4", "Climate deep-tech, SAFE-heavy seed", a4_climate_deeptech_safe_heavy),
    ("A5", "Logistics 8-round late stage", a5_logistics_late_stage_8_rounds),
    ("A6", "Edtech with bridge round + down Series C", a6_edtech_bridge_round),
    ("A7", "Crypto multi-cap SAFE + participating-cap Series A", a7_crypto_token_equity_dual),
    ("A8", "Corporate spinout with parent-co common", a8_acquihire_corporate_spinout),
    ("A9", "Pre-IPO PIPE with conv-ratio adjustment", a9_pre_ipo_pipe_round),
    ("A10", "Distressed recap with stacked ratchets", a10_distressed_recap),
]


@dataclass
class ArchResult:
    id: str
    name: str
    success: bool
    n_classes: int = 0
    n_breakpoints: int = 0
    n_tranches: int = 0
    lp_total: float = 0.0
    fd_shares: int = 0
    notes: list[str] = None
    error: str | None = None
    traceback: str | None = None


def _check_invariants(ct: CapTable, wf) -> list[str]:
    """Return list of invariant violation messages (empty = clean)."""
    msgs = []
    # I6: tranches sum to 100
    for t in wf.tranches:
        s = sum(t.marginal_allocation_pct.values())
        if abs(s - 100.0) > 0.5:
            msgs.append(f"tranche {t.id} allocations sum to {s:.2f}, not 100")
    # I9: lp_total matches sum of class LP
    expected = sum(sc.liquidation_preference.amount for sc in ct.share_classes
                   if sc.liquidation_preference)
    if abs(wf.lp_total - expected) > 1.0:
        msgs.append(f"lp_total mismatch: engine={wf.lp_total:,.0f} vs sum={expected:,.0f}")
    # I7: BPs sorted
    for i in range(len(wf.breakpoints) - 1):
        if wf.breakpoints[i + 1].value < wf.breakpoints[i].value - 0.01:
            msgs.append(f"BP {wf.breakpoints[i].id}>{wf.breakpoints[i+1].id}")
    # Tranche partition
    sorted_tr = sorted(wf.tranches, key=lambda t: t.range_low)
    for i in range(len(sorted_tr) - 1):
        if sorted_tr[i].range_high is None:
            msgs.append("inner tranche unbounded")
        elif abs(sorted_tr[i].range_high - sorted_tr[i + 1].range_low) > 0.01:
            msgs.append(
                f"gap between {sorted_tr[i].id}.high={sorted_tr[i].range_high:,.0f}"
                f" and {sorted_tr[i+1].id}.low={sorted_tr[i+1].range_low:,.0f}"
            )
    # Dead zones
    for t in wf.tranches:
        if all(v == 0 for v in t.marginal_allocation_pct.values()) and t.range_low > 0:
            msgs.append(f"{t.id} dead zone {t.range_low:,.0f}→{t.range_high:,.0f}")
    return msgs


def run_one(aid: str, name: str, builder) -> ArchResult:
    try:
        ct = builder()
    except Exception as e:
        return ArchResult(id=aid, name=name, success=False, error=f"build failed: {e}",
                          traceback=traceback.format_exc())
    try:
        wf = compute_waterfall(ct)
    except Exception as e:
        return ArchResult(id=aid, name=name, success=False, error=f"engine crash: {e}",
                          traceback=traceback.format_exc())
    notes = _check_invariants(ct, wf)
    # Workbook generation
    try:
        build_formula_workbook(ct, wf)
    except Exception as e:
        notes.append(f"workbook gen failed: {e}")
    return ArchResult(
        id=aid, name=name, success=(not notes),
        n_classes=len(ct.share_classes),
        n_breakpoints=len(wf.breakpoints),
        n_tranches=len(wf.tranches),
        lp_total=wf.lp_total,
        fd_shares=wf.total_fully_diluted_shares,
        notes=notes,
    )


def main():
    print(f"Running {len(ARCHETYPES)} Singapore-flavored archetypes blind through engine…\n")
    print(f"{'ID':<4} {'Status':<8} {'Cls':>4} {'BPs':>4} {'Tr':>4} {'LP total':>16} {'FD shares':>14}  Name")
    print("-" * 110)
    results = []
    for aid, name, builder in ARCHETYPES:
        r = run_one(aid, name, builder)
        results.append(r)
        if r.error:
            print(f"{r.id:<4} FAIL     {'':>4} {'':>4} {'':>4} {'':>16} {'':>14}  {r.name}")
            print(f"     ERROR: {r.error}")
        else:
            status = "OK" if r.success else "WARN"
            print(f"{r.id:<4} {status:<8} {r.n_classes:>4} {r.n_breakpoints:>4} "
                  f"{r.n_tranches:>4} ${r.lp_total:>14,.0f} {r.fd_shares:>14,}  {r.name}")
            if r.notes:
                for n in r.notes:
                    print(f"       ⚠ {n}")
    print("-" * 110)
    n_ok = sum(1 for r in results if r.success and not r.error)
    n_warn = sum(1 for r in results if r.notes and not r.error)
    n_fail = sum(1 for r in results if r.error)
    print(f"\nClean: {n_ok}/{len(results)}  Warnings: {n_warn}  Crashes: {n_fail}")
    return results


if __name__ == "__main__":
    main()
