# Stress Test — Northwind Robotics, Inc.

This file is sealed before the tool is run. The cap table below is constructed without consulting the parser/checklist/waterfall code, deliberately as a fresh Series B warehouse-robotics company that the analyst would actually receive from a portfolio CFO. No cherry-picking to suit the tool.

## Company

- **Name:** Northwind Robotics, Inc.
- **Jurisdiction:** Delaware C-corp (incorporated 2021-03-15)
- **Sector:** Warehouse automation (mobile picking robots)
- **Stage:** Series B closed 2026-04-15
- **Last 409A:** 2025-12-31, FMV common $1.10 (pre-Series-B)
- **Currency:** USD
- **Total raised:** $23.7M cumulative

## Cap structure

| Holder | Class | Type | Issue date | Price/sh | Shares | Notes |
|---|---|---|---|---|---|---|
| Alana Park (Co-founder, CEO) | Founder Common (F) | common (10× voting) | 2021-03-15 | $0.0001 | 2,800,000 | Class F super-voting; identical economics |
| Mateus Silva (Co-founder, CTO) | Founder Common (F) | common (10× voting) | 2021-03-15 | $0.0001 | 2,000,000 | Class F super-voting; identical economics |
| Lin Chen (Advisor) | Common Stock | common | 2022-09-01 | $0.05 | 250,000 | Advisor grant, fully vested |
| Aditya Bose (ex-eng, exercised) | Common Stock | common | 2023-04-12 | $0.20 | 500,000 | Exercised options post-departure |
| Series Seed (3 angels, aggregated) | Series Seed Preferred | preferred | 2022-06-30 | $0.65 | 1,650,000 | 1× non-participating LP, BBWA |
| Series A investors (4 firms) | Series A Preferred | preferred | 2024-02-14 | $1.85 | 2,400,000 | 1× non-participating LP, BBWA |
| Atlas Ventures + co-leads | Series B-1 Preferred | preferred | 2026-04-15 | $4.20 | 1,800,000 | 1× non-participating LP, BBWA |
| Pinnacle Strategic (corporate VC) | Series B-2 Preferred | preferred | 2026-04-15 | $4.20 | 600,000 | **1.5× non-participating LP, BBWA — strategic side car** |
| ESOP — granted (19 employees) | Common (options granted) | option_pool_granted | varies (2022–2026) | $1.10 (current grants) | 420,000 | 4-yr vest, 1-yr cliff |
| ESOP — reserved (refresh) | Common (options reserved) | option_pool_reserved | n/a | n/a | 380,000 | Series B closing condition refresh |
| Hercules Capital | Warrant | warrant | 2025-08-04 | $1.85 strike | 75,000 | Venture-debt sweetener; 7-yr tenor |
| Pinnacle Strategic | SAFE | safe | 2025-11-30 | post-money, $30M cap, 20% disc. | $750,000 principal | Not yet converted (Series B-2 was a separate priced participation) |

**LP totals (preferred only):**
- Series Seed: 1,650,000 × $0.65 × 1.0 = $1,072,500
- Series A: 2,400,000 × $1.85 × 1.0 = $4,440,000
- Series B-1: 1,800,000 × $4.20 × 1.0 = $7,560,000
- Series B-2: 600,000 × $4.20 × 1.5 = $3,780,000
- **Total LP: $16,852,500**

**Seniority (typical "standard" stack):** B-1 and B-2 pari passu (same closing, same series), then A, then Seed.

But the side car B-2 has a 1.5× LP which is unusual within a same-tranche pari passu — would normally be subject to scrutiny.

## Side letters (separate sheet in workbook)

- **SL-01: Atlas Ventures MFN + board observer.** "If, in any subsequent priced round prior to a Qualified IPO, the Company grants any holder of preferred stock economic terms more favorable than the Series B-1 1× non-participating preference (excluding the Series B-2 1.5× preference granted concurrently with the Series B-1 closing), the Series B-1 holders shall be entitled to elect such terms. Atlas Ventures shall additionally have the right to designate one (1) board observer."
- **SL-02: Pinnacle Strategic ROFR + commercial.** "Pinnacle shall have a right of first refusal on any future financing rounds at Series B-1 or earlier seniority, exercisable for up to 25% of the round. Pinnacle shall additionally have a non-binding commercial intent to integrate Northwind robotics into Pinnacle's logistics network upon achievement of $5M ARR."

## Convertibles (separate sheet)

**SAFE (Pinnacle Strategic):** Y Combinator post-money standard, $750,000 principal, $30,000,000 valuation cap, 20% discount, MFN. Issued 2025-11-30 — 4 months before the Series B-1 closing. Note: did NOT auto-convert at Series B because the SAFE language carved out "side-car priced participations" — this is a real-world ambiguity that the analyst would need to adjudicate.

**Warrant (Hercules Capital):** 75,000 shares of Series A Preferred at $1.85 strike, issued 2025-08-04 with the Hercules venture-debt facility ($3M loan). 7-year exercise window. Exercise dilutes Series A pool.

## Realistic Excel mess (intentional)

The .xlsx file will contain:
1. Title row spanning columns A:H with the company name
2. Subtitle row with "Capitalization Table — Pro Forma as of April 30, 2026"
3. Confidentiality notice row
4. Blank separator row
5. Header row: `Holder | Class | Class Type | Issue Date | Price per Share ($) | Shares | Fully Diluted % | Notes`
6. Data rows for each holder (12 rows)
7. Subtotal row "Subtotal — Common Stock"
8. Subtotal row "Subtotal — Preferred Stock"
9. Subtotal row "Subtotal — Options Pool"
10. Grand total row "Total Issued + Reserved (FD basis)"
11. Footnote rows: `(1) See "Side Letters" tab`, `(2) See "Convertibles" tab`

Date formats deliberately mixed: most dates are real datetime values, but two rows have date as text string `"April 15, 2026"` instead of a proper date — this happens often when CFOs hand-type cells.

The "Class Type" column uses a mix of terminology: `"Common"`, `"Preferred"`, `"Common (Options Pool)"`, `"Preferred (Strategic side-car)"` — to test whether the parser is rigid about exact phrasing.

The Notes column carries the LP multiples (1×, 1.5×) and anti-dilution (BBWA) — i.e., the structural data is encoded as free-text annotations, not as separate columns. **This is realistic of every cap-table I have ever seen.** The tool will need to either (a) extract these via heuristic, or (b) flag them as missing and force the analyst to enter them via the resolve forms.

## Honest evaluation framework

After running the tool, I'll evaluate against:
1. **Did it parse without crashing?** (binary)
2. **Did it correctly identify share classes by name?** (count: classes recognized / classes present)
3. **Did it correctly tag class TYPE?** (common vs preferred vs option-pool, etc.)
4. **Did it pick up share counts and prices?**
5. **Did it detect missing structural fields** (LP multiples, AD variants, conversion ratios)?
6. **Did it detect outstanding SAFE / warrant?** (it can't, since those are in a separate sheet)
7. **Did it detect side letters?** (same)
8. **Did the waterfall produce numerically sensible breakpoints?** (vs my hand-computation below)
9. **Where did the UX get in the way?** (paper cuts during the resolve flow)

## Hand-computed waterfall for ground truth

(Computed before running the tool, with all preferred at 1× non-participating except B-2 at 1.5×, all classes pari passu within their tranche.)

**LP queue (most senior first):** Series B (B-1 + B-2 pari passu, $11.34M) → Series A ($4.44M) → Series Seed ($1.07M) → Total $16.85M.

**Within the Series B tranche, B-1 and B-2 share pari passu, but B-2 takes 1.5× while B-1 takes 1×.** This means at low-V exits where B's LP is the binding constraint, B-2 absorbs more per share than B-1 — they're "pari passu" in seniority but not in the LP amount per share. This is a real structural quirk the engine may or may not handle.

**FD shares for waterfall (excluding reserved pool, SAFE, warrant):** 4.8M + 0.75M + 1.65M + 2.4M + 1.8M + 0.6M + 0.42M = **12,420,000 shares**

**Conversion threshold for Series Seed (smallest senior):**
- LP if not converted: $1,072,500
- Pro-rata if converted: 1.65M / 12.42M × (V – senior_LP) where senior_LP includes B and A LPs only (Seed converted)
- Indifference: 1,072,500 = 1.65/12.42 × (V – $11,340,000 – $4,440,000)
- V – $15,780,000 = $1,072,500 × 12.42 / 1.65 = $8,073,818
- V_Seed_convert ≈ **$23,853,818**

**Conversion threshold for Series A:**
- LP if not converted: $4,440,000
- Pro-rata if converted: 2.4M / 12.42M × (V – $11,340,000)
- Indifference: 4,440,000 = 2.4/12.42 × (V – $11,340,000)
- V – $11,340,000 = 4,440,000 × 12.42 / 2.4 = $22,977,000
- V_A_convert ≈ **$34,317,000**

**Conversion threshold for Series B-1:**
- LP if not converted: $7,560,000 (just B-1's portion of the B tranche)
- Pro-rata if converted: 1.8M / 12.42M × V (no senior LP above B-1)
- Indifference: 7,560,000 = 1.8/12.42 × V
- V_B1_convert ≈ **$52,164,000**

**Conversion threshold for Series B-2:**
- LP if not converted: $3,780,000 (1.5× × $2.52M base)
- Pro-rata if converted: 0.6M / 12.42M × V
- Indifference: 3,780,000 = 0.6/12.42 × V
- V_B2_convert ≈ **$78,246,000**

(Note: B-2 converts at MUCH higher V than B-1 because B-2 has a sweetened 1.5× LP — they're more reluctant to give up the LP. So the conversion sequence is Seed → A → B-1 → B-2, even though pari-passu B-1 and B-2 are at the same seniority.)

So expected breakpoints (after sorting + dedup, smallest first):

- BP1: $0 origin
- BP2: $11,340,000 — Series B LP fully paid (B-1 + B-2 LPs)
- BP3: $15,780,000 — Series A LP fully paid
- BP4: $16,852,500 — Series Seed LP fully paid (all LPs paid)
- BP5: $23,853,818 — Series Seed converts to common
- BP6: $34,317,000 — Series A converts to common
- BP7: $52,164,000 — Series B-1 converts to common
- BP8: $78,246,000 — Series B-2 converts to common

## What I expect to break

Predictions before running (these are bets, not pre-tested):

1. **Parser will probably miss the LP-multiple-in-Notes-column** because notes are free text. It should fall back to "no LP multiple — assume 1×" or flag MISSING.
2. **Parser may miss the 1.5× on B-2** specifically, because that's encoded in Notes column free text.
3. **Parser will probably miss the SAFE and Warrant** because they're on separate sheets, not in the cap-table sheet.
4. **Parser will probably miss the side letters** for the same reason.
5. **Pari-passu B-1 + B-2 with different LP multiples** — the engine may or may not get this right; it depends on how seniority + LP-amount interact in the regime walker.
6. **Subtotal rows may be parsed as share classes** if not filtered. The "Subtotal — Common Stock" row has a number in column F that could be misread as shares.
7. **Mixed-format dates** may produce parser warnings.
8. **Class Type labels** like "Common (Options Pool)" and "Preferred (Strategic side-car)" may not match the parser's expected aliases.

These predictions are recorded BEFORE running. They are not guidance for the tool — they are honest expectations.
