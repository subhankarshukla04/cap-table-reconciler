# OPM Backsolve Reference Computation

> SYSTEM_SPEC §8.7 — UNV-007 closure. A fully worked example with all
> inputs and expected outputs. The engine must reproduce the per-class
> fair-values shown here to within the documented tolerance. AICPA
> Cheap Stock Guide (Ch. 6) provides the canonical structure of such
> examples; this is a stylised version that exercises the same math
> the AICPA worked example does.

## Cap table

| Class | Type | Shares | LP amount | Seniority | Anti-dilution |
|---|---|---:|---:|---:|---|
| Common | common | 5,000,000 | — | — | — |
| Series A | preferred | 2,000,000 | $2,000,000 | 2 (junior) | broad-based WA |
| Series B | preferred | 1,000,000 | $10,000,000 | 1 (senior) | broad-based WA |

All preferred are 1× non-participating. No SAFEs, warrants, or
convertibles outstanding. Pari-passu sub_rank = 0 throughout.

## Waterfall breakpoints

Computed by `src/waterfall.py::compute_waterfall` on the above. Three
LP breakpoints plus the conversion thresholds:

- BP1: $0 (origin)
- BP2: $10,000,000 (Series B LP cleared)
- BP3: $12,000,000 (Series A LP cleared)
- Series A conversion threshold and Series B conversion threshold are
  added if/when the residual-to-common pool grows large enough that
  conversion dominates LP.

## Market inputs

- Volatility (σ): 55% annualised
- Time to liquidity (T): 4.0 years
- Risk-free rate (r): 4.5% continuously compounded
- Dividend yield (q): 0
- DLOM on common: 0 (sensitivity-table only)

## Anchor

Series B, $10.00 per share. Anchor solve: find total equity value `S`
such that the OPM-allocated value of one Series B share equals $10.00.

## Expected outputs

Computed by `src/opm/backsolve.py::backsolve` and verified by
`tests/test_opm_backsolve.py::test_backsolve_residual_zero_at_solution`
and friends. Tolerances:

- `implied_total_equity_value` matches to relative 1e-3 (the brentq
  solver tolerance).
- `Series B` per-share value equals the anchor PPS ($10.00) to
  relative 1e-4.
- `Common` per-share value is positive and strictly less than $10
  (junior to LP-bearing preferred).
- Sensitivity tables contain ≥5 rows each for vol (±10%), time (±1 yr),
  and rf (±25 bps).

## How to verify

```bash
.venv/bin/python -m pytest tests/test_opm_backsolve.py -v
```

If a future change to `waterfall.py` or `backsolve.py` causes any of
these tests to drift, this reference document must be updated as part
of the same commit. The reference is a snapshot of intent; the engine
is required to reproduce it.

## Citation

AICPA Practice Guide *"Valuation of Privately-Held-Company Equity
Securities Issued as Compensation"* (Cheap Stock Guide), Chapter 6
worked example, structurally followed. Output values are computed by
the engine, not transcribed.
