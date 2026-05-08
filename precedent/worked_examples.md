# Worked Waterfall and Backsolve Examples — Reference

> Real published cap-table structures and breakpoint patterns. Use as benchmarks for hand-computing fixture ground truth. If our fixture math produces a breakpoint pattern with no analogue here, we've assembled something pathological.

---

## Example 1 — Eqvista "McGlynn Ltd" (canonical small Series A waterfall)

**Source:** [Eqvista — How Liquidation Waterfalls Work](https://eqvista.com/waterfall-analysis/liquidation-waterfalls/)

### Cap Table

| Class | Shares | Price/Share | Total Invested |
|---|---|---|---|
| Common | 6,000,000 | $0.00 | $0 |
| Seed Preference | 2,500,000 | $0.50 | $1,250,000 |
| Series A | 2,000,000 | $1.25 | $2,500,000 |
| Series A-1 | 1,500,000 | $2.50 | $3,750,000 |
| **Total** | **12,000,000** | — | **$7,500,000** |

### Liquidation Preferences

| Class | Multiplier | Conversion Ratio | Participating | Note |
|---|---|---|---|---|
| Seed Preference | 1.0x | 1:1 | No | Non-participating |
| Series A | 1.0x | 1:1 | No | Non-participating |
| Series A-1 | 1.5x | 1:1 | No | Non-participating |

### Breakpoints (5 tranches)

| Tranche | Range (exit value) | Distribution |
|---|---|---|
| 1 | $0 — $9,375,000 | All preferred classes take their LPs sequentially; common gets nothing |
| 2 | $9,375,000 — $11,875,000 | Seed converts to common; Series A and A-1 still take preference |
| 3 | $11,875,000 — $16,250,000 | Seed and Series A both convert; A-1 still takes preference |
| 4 | $16,250,000 — $27,500,000 | All but A-1 convert; A-1 still on its 1.5x preference |
| 5 | $27,500,000+ | All preferred convert to common; pro-rata distribution |

**Tranche 1 ceiling math:** Seed (1.0x × $1.25M) + Series A (1.0x × $2.5M) + Series A-1 (1.5x × $3.75M) = $1.25M + $2.5M + $5.625M = **$9.375M**.

### Exit at $20M (Tranche 4) — actual payouts

| Class | Payout | Reasoning |
|---|---|---|
| Series A-1 | $5,625,000 | Takes 1.5x preference (still below conversion threshold) |
| Common (after others convert) | $7,565,789 | Pro-rata of remainder |
| Seed Preference | $3,782,895 | Converts; pro-rata |
| Series A | $3,026,316 | Converts; pro-rata |

### Conversion Decision Rule

> "If there are sufficient returns to distribute to investors, converting to common stock and receiving the price per share for that stock may be worthwhile."

**Mathematical statement.** A preferred holder converts when (per-share residual to common after senior preferences) × (its as-converted share count) > (its liquidation preference). The conversion threshold is the exit value at which these two equate.

### Why this example matters

It's the cleanest published five-tranche waterfall available, with explicit dollar breakpoints and a per-class conversion-vs-take-LP decision. Our Fixture 1 (clean baseline) should produce a breakpoint pattern very close to this — same structure (Seed + Series A + Series A-1, with one class having a higher LP multiplier).

---

## Example 2 — Eqvista "Kertzmann Group" (Series B with 1.5x preference)

**Source:** [Eqvista — Waterfall Analysis & Cap Table](https://eqvista.com/equity/waterfall-analysis-cap-table-determining-equity-distribution/)

### Cap Table

| Class | Shares | Price/Share | Total Invested |
|---|---|---|---|
| Common | 5,000,000 | $0.40 | $2,000,000 |
| Seed Preference | 2,000,000 | $1.00 | $2,000,000 |
| Series A | 4,000,000 | $1.00 | $4,000,000 |
| Series B | 3,000,000 | $3.00 | $9,000,000 |

### Liquidation Preferences

| Class | Conversion Rate | Liquidation Multiple |
|---|---|---|
| Seed | 1:1 | 1.0x |
| Series A | 1:1 | 1.0x |
| Series B | 1:1 | 1.5x |

### Exit at $50M — actual payouts

| Class | Payout | Distribution Method |
|---|---|---|
| Series B | $13,500,000 | Takes 1.5x preference (= $9M × 1.5) |
| Common | $17,176,471 | Converts pro-rata |
| Seed | $10,735,294 | Converts pro-rata |
| Series A | $8,588,235 | Converts pro-rata |

**Total = $50M check.** $13.5M + $17.18M + $10.74M + $8.59M ≈ $50M (small rounding).

**Implication:** at $50M exit, only Series B is still better off taking its preference; Seed and Series A convert because their pro-rata as-converted share exceeds 1x of their investment. Series B's 1.5x preference creates a higher conversion threshold.

### Why this example matters

This is the closest published proxy for Fixture 1 (Series B SaaS company). Use this structure as a starting template, modify share counts and prices to fictional values, and verify the breakpoint pattern matches.

---

## Example 3 — Aranca CHF Series C (multi-class, with DLOM)

**Source:** Aranca published case study (extracted via Eqvista whitepaper analysis since Aranca's PDF source returned binary errors).

### Cap Table (CHF-denominated Swiss Series C)

| Class | Price/Share (CHF) | Shares | Total (CHF) |
|---|---|---|---|
| Series C Preferred | 45.74 | 702,121 | 32,149,505 |
| Series B Preferred | 31.50–35.00 | 1,711,653 | 40,665,433 |
| Series A Preferred | 24.54 | 430,784 | 7,077,159 |
| Series Seed Preferred | 18.79–24.76 | 147,172 | 2,292,293 |
| Common Stock (voting) | 13.41 | 105,000 | 1,407,806 |
| Common Stock (non-voting) | 13.41 | 602,557 | 8,078,887 |
| Stock Options | various | 201,209 | 1,610,927 |
| **Total** | — | **3,855,496** | **93,282,010** |

### Result

- Backsolved total equity value: **CHF 93.28M** (derived from Series C price)
- Common shareholders receive zero in any exit below **CHF 114.4M** (waterfall threshold)
- Common (voting) FMV: **CHF 10.66/share** (after 20.5% DLOM + 3% voting discount)
- Common (non-voting) FMV: **CHF 10.34/share** (same DLOM + voting discount)

### Why this example matters

- Multi-class waterfall (4 preferred classes + 2 common classes) — closest to Fixture 3 (SEA edge case).
- Non-voting common class — proxy for the dual-class structure we'll model in Fixture 3.
- DLOM at 20.5% sits in the typical 15-35% range cited in AICPA practice.
- Voting discount at 3% is on the low end but defensible (Damodaran cites 2-5% for marginal voting differential).

---

## Example 4 — Aranca Healthcare Convertible Notes Case (13 breakpoints, with notes and warrants)

**Source:** Aranca case study (same as above).

### Cap Table

| Class | Price/Share ($) | Shares | Total ($) |
|---|---|---|---|
| Common Stock | 1.22 (pre-discount) | 4,310,977 | 5,239,260 |
| Preferred @ 1.0344 | 1.47 | 681,855 | 1,004,948 |
| Preferred @ 1.1493 | 1.51 | 147,816 | 223,132 |
| Preferred @ 1.2642 | 1.55 | 175,760 | 271,834 |
| Preferred @ 1.7239 | 1.71 | 1,008,259 | 1,721,944 |
| Preferred @ 2.2986 | 1.94 | 203,963 | 395,095 |
| Preferred @ 3.6777 | 2.58 | 473,221 | 1,218,645 |
| Conv. Notes (6M Cap) | 1.42 | 889,995 | 1,263,150 |
| Conv. Notes (12M Cap) | 1.70 | 1,367,082 | 2,321,860 |
| Warrants @ 0.51 | 1.03 | 2,929 | 3,011 |
| Warrants @ 1.0124 | 0.87 | 22,622 | 19,711 |
| Warrants @ 1.44 | 0.76 | 38,048 | 28,857 |
| **Total** | — | **9,322,527** | **13,711,447** |

### Result

- **13 breakpoints** computed using a 5-year exit horizon.
- Total equity value: **$13.71M** (backsolved from convertible note conversion).
- Common stock FMV after 39% DLOM: **$0.74/share**.
- Convertible Notes (12M cap) FMV: **$1.04**.
- Preferred range (across all 6 series): **$0.90–$1.57/share**.

### Why this example matters

- Demonstrates how convertible notes and warrants insert breakpoints into the waterfall.
- 13 breakpoints in a multi-class structure with notes/warrants is a realistic upper bound; our edge case fixture should have 6-9 breakpoints, not 13.
- 39% DLOM on common is at the high end of the AICPA-cited range — defensible for an early-stage healthcare company but warrants explicit justification in the memo.

---

## Example 5 — Breaking Into Wall Street downside-protection tutorial

**Source:** [Breaking Into Wall Street — Liquidation Preference Tutorial](https://breakingintowallstreet.com/kb/venture-capital/liquidation-preference/)

### Cap Table

| Group | Investment | Ownership % | LP Multiple |
|---|---|---|---|
| Seed | $2M | 15% | 1x |
| Series A | $5M | 25% | 1x |
| Co-Founders/Employees | — | 60% | — |

### Exit Scenarios

**$100M exit (success):** Both investors convert because pro-rata > 1x.
- Seed: $15M (7.5x cash-on-cash from conversion)
- Series A: $25M (5.0x)

**$10M exit (downside):** Both stay in preferred.
- Seed: $2M (1x preference)
- Series A: $5M (1x preference)
- Common: $3M residual

**$5M exit (insufficient proceeds):**
- Without pari passu: Series A gets $5M (full LP), Seed gets $0.
- With pari passu: Series A gets $3.57M (5/7), Seed gets $1.43M (2/7).

### Decision Logic

```
IF (exit_equity_value >= total_LP):
    investor_choice = MAX(LP_multiple × invested, ownership_pct × exit_value)
    election = "Convert" if pro_rata > LP else "Take LP"
ELSE IF (exit_equity_value < total_LP):
    IF pari_passu:
        proceeds = (group_LP / total_LP) × exit_value
    ELSE:
        senior_paid_first; juniors_get_remainder
    election = "Stay in Preferred"
```

### Why this example matters

- Cleanest published statement of the conversion-vs-take-LP decision logic. Use as the reference algorithm for `src/waterfall.py`.
- Pari passu treatment of two preferred classes at the same seniority level is a real edge case worth modeling.

---

## Example 6 — Qapita's "Company X" Founder's Guide

**Source:** [Qapita — How to Model Exit Scenarios with Waterfall Analysis](https://www.qapita.com/blog/how-to-model-exit-scenarios-with-waterfall-analysis-a-founders-guide)

### Cap Table

| Group | Ownership | LP / Rights |
|---|---|---|
| Seed | 10% | 1x non-participating |
| Series A | 25% | 2x participating |
| SAFE | 5% | (converts at financing) |
| ESOP | 10% | (vests over time) |
| Founders | 50% | — |

### Exit at $25M

- Seed receives $1M (its 1x preference).
- Series A receives $8M (its 2x preference; assumed $4M invested, so 2x = $8M).
- Remaining $16M distributes pro-rata among the rest.

### Why this example matters

- Direct reference from Qapita's own marketing — terminology Evelyn's team uses.
- 2x participating preferred is a more aggressive structure; the participation kicks in *after* the 2x preference, creating a follow-on tranche that flows pro-rata (not to common only).
- Use this voice and framing in the demo narrative.

---

## Howell's Top 10 OPM Backsolve Checks

**Source:** [Howell on LinkedIn — Top 10 things to check](https://www.linkedin.com/pulse/your-opm-backsolve-valuation-correct-top-10-things-check-howell)

The de facto auditor checklist. Each item below is a check the Cap Table Reconciler should support either directly (mark items with ✓) or facilitate as a downstream gate (✗ — out of scope for our tool but flagged in README).

1. ✓ **Cap Table — Count Capital Interests Wisely.** All shares, options, warrants, exercise prices reflected as of valuation date. — Direct fit for the tool's reconciliation layer.
2. ✓ **Preferences — Who's On First.** Liquidation prefs, dividends, participation, caps, conversion rights documented from legal docs. — Direct fit.
3. ✓ **Thresholds — Know When To Cross The Line.** Conversion / exercise / participation thresholds documented; conversion happens when as-if-converted value exceeds preferred value. — Direct fit.
4. ✗ **Volatility.** Peer-group log-normal annualized basis. — Out of scope for waterfall tool; flagged as next-step input to OPM.
5. ✗ **Expected Term.** Time-to-liquidity assumption tied to stage and funding status. — Out of scope; flagged.
6. ✗ **Discounts & Premiums.** DLOM via professional quantitative method. — Out of scope; flagged.
7. ✗ **Black-Scholes Calculator.** Modified BSM template, not online calculator. — Out of scope.
8. ✗ **Basis of Value.** Non-controlling, non-marketable; grant-date fair value for ASC 718. — Out of scope.
9. ✓ **Valuation Date.** Last round / business value / transaction not more than 12 months before valuation date. — Tool can flag stale inputs in checklist.
10. ✗ **Technology and Models.** Each valuation unique; requires professional review. — Out of scope; reinforced in README's "expert-led" framing.

The four items the tool directly addresses (1, 2, 3, 9) are exactly the cap-table-cleanup grunt work documented as the team's largest hour drain.

---

## Summary — Benchmark Patterns for Fixture Validation

| Aspect | Fixture 1 (clean) target | Fixture 2 (typical messy) target | Fixture 3 (SEA edge) target |
|---|---|---|---|
| Total equity value | $30-50M | $40-60M | $60-100M |
| Number of preferred classes | 3 (Seed, A, B) | 3-4 (with SAFE-converted) | 4-5 (with CCPS layer) |
| Number of breakpoints | 4-5 | 5-7 | 7-9 |
| LP multipliers | 1x across | 1x with one 1.5x | 1x with one 2x or capped-participating |
| Anti-dilution | Broad-based weighted average | Broad-based weighted average | Mix: BBWA on most, full ratchet on one |
| Special structures | None | Stale option pool, unrecorded SAFEs, vendor warrant, MFN side letter | CCPS layer, dual-class common (econ identical), super-pro-rata side letter |
| Common FMV after DLOM (rough) | 50-65% of latest preferred | 40-55% of latest preferred | 35-50% of latest preferred |

If a fixture's hand-computed waterfall produces breakpoint counts or common FMV ratios outside these ranges, sanity-check against published worked examples before locking the ground truth.

---

## Sources

- [Eqvista — How Liquidation Waterfalls Work](https://eqvista.com/waterfall-analysis/liquidation-waterfalls/)
- [Eqvista — Waterfall Analysis & Cap Table](https://eqvista.com/equity/waterfall-analysis-cap-table-determining-equity-distribution/)
- [Aranca Backsolve Whitepaper (PDF)](https://www.aranca.com/assets/uploads/resources/special-reports/The-Backsolve-Method_10_22_191024_154016.pdf) — content extracted via secondary references; primary PDF returned binary
- [Breaking Into Wall Street — Liquidation Preference Tutorial](https://breakingintowallstreet.com/kb/venture-capital/liquidation-preference/)
- [Qapita — How to Model Exit Scenarios with Waterfall Analysis](https://www.qapita.com/blog/how-to-model-exit-scenarios-with-waterfall-analysis-a-founders-guide)
- [Howell on LinkedIn — Top 10 OPM Backsolve checks](https://www.linkedin.com/pulse/your-opm-backsolve-valuation-correct-top-10-things-check-howell)
- [CBV Institute — Critical examination of Backsolve (Jain)](http://cbvinstitute.com/wp-content/uploads/2024/01/CBV-Matters_Whitepaper_Backsolve_Jain.pdf) — primary PDF returned binary; included as bibliographic reference only
