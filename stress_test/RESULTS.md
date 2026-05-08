# Stress Test Results — Northwind Robotics

**Test:** Fresh real-world Series-B cap table built without consulting parser internals (see `COMPANY_PROFILE.md` for the sealed design).

**Verdict:** Tool **fails open** in a dangerous way. It accepts the file, renders a confident-looking waterfall, but **silently drops 7 of 9 share classes** during parse and produces a meaningless $0-LP waterfall. The analyst would be misled.

---

## What the analyst sees

After uploading `northwind_cap_table.xlsx`, the /review page shows:

- **Cleaned cap table: 2 share classes** (Lin Chen advisor + Aditya Bose ex-engineer common — both incidental rows)
- **No headline warning** that the cap table is incomplete
- **Findings: 4 warnings** (all about side-letter labeling — none flagging the dropped rows)
- The /waterfall page renders with **Total LP: $0**, **Fully diluted: 750,000 shares**, **1 breakpoint** (origin only)

The 7 missing classes (founder common ×2, Series Seed, Series A, Series B-1, Series B-2, ESOP granted, ESOP reserved) — **$16.85M in liquidation preferences, $50M+ in preferred capital, the entire economic core of the company** — are not in the cap table at all. They appear only as `share_class_validation_failed` lines in a "Parser handled" expander section that an analyst would scroll past.

If this output were trusted, the resulting valuation would be off by roughly 100%.

---

## Bugs found, in priority order

### #1 — IndexError crash on free-text side-letters sheet *(fixed during test)*

`src/parser.py:688`. `_read_side_letters_tab` accessed `row[1]` and `row[2]` without bounds check. Any side-letter sheet with single-column rows (the natural format) crashed the entire upload.

**Fix applied:** padded short rows with `None` before unpacking. One-line change. `src/parser.py:682-693`. The full test would not have run without this fix.

### #2 — Class-type "Common (super-voting)" defaults to PREFERRED *(critical, not fixed)*

The `_coerce_class_type` heuristic falls back to `preferred` when no alias matches. A label that literally starts with the word "Common" — "Common (super-voting)", "Common (Options Pool)", "Preferred (Strategic side-car)" — gets misclassified as preferred, then fails pydantic validation (preferred without LP), then the row is silently dropped.

**Impact on this test:** all 5 founder/ESOP rows dropped (4.8M founder shares + 800K ESOP).

**Right fix:** when the class-type string contains the substring "common", default to common (and analogously for "preferred", "option"). Falling back to preferred is the wrong default both statistically (most unknown labels in real cap tables are common variants) and operationally (it produces silent data loss instead of safe-by-default behavior).

### #3 — All preferred classes dropped because LP multiples live in free-text Notes *(architectural, not fixed)*

Real client cap tables encode LP multiple, participation, and AD variant in the Notes column as free text: `"1x non-participating LP, BBWA AD, 1:1 conversion"` or `"1.5x non-participating LP, BBWA AD, 1:1 conversion"`. The parser ignores this content — it has no LP-from-notes extractor — and then pydantic validation rejects every preferred row for lacking an `LiquidationPreference`. The class is dropped silently.

**Impact on this test:** Series Seed, Series A, Series B-1, Series B-2 all dropped. The tool was unable to recover any preferred class from a perfectly readable cap table.

**Right fix paths (pick one):**
- (a) Heuristic regex in Notes: `r"(\d+(?:\.\d+)?)\s*[x×]\s*(non[- ]participating|participating)"` with confidence flag.
- (b) Make LP optional at parse time (default 1× non-participating, flag as `lp_inferred`), let the analyst confirm.
- (c) Force a one-screen LP-confirmation step after parse that lists every preferred and asks the analyst to confirm/edit each LP. This is the most defensible for a valuations team.

### #4 — Validation failures presented as "Parser handled", not as blockers *(UX)*

The /review page lists `share_class_validation_failed` events under a section titled **"Parser handled"** with the description *"Header heuristics matched these columns... The parser also normalized inconsistent date formats, currency symbols, and instrument-type spellings."* This framing tells the analyst that everything was successfully handled when in fact rows were dropped.

The headline section of the page should say, prominently: **"7 share classes could not be parsed — see details below"** with a link to the details. Currently the analyst has to count manually.

### #5 — Pydantic stack-trace strings shown verbatim to the user *(UX)*

Each `share_class_validation_failed` warning includes the raw multiline pydantic error message, including `For further information visit https://errors.pydantic.dev/2.13/v/value_error`. The user-facing string should be sanitized — that's developer noise.

### #6 — Side-letter sheet expects rigid 3-column schema *(architectural)*

The parser expects `Side Letters` sheet rows to be `(id, title, summary)`. The Northwind sheet uses the format every actual law firm uses: one row "SL-01: Atlas Ventures — MFN + Board Observer" (title), next row contains the full body text in column A. The parser produced 4 garbage entries (each title row + each body row treated as a separate side letter, all titled "Untitled").

**Right fix:** detect free-text format vs. structured format — if rows are 1-column, assume `title-on-bold-row, body-on-next-row` pattern.

### #7 — `Convertibles` sheet ignored entirely *(coverage gap)*

The parser detects `Side Letters` and `Company` tabs but has no logic for `Convertibles`. The outstanding SAFE ($750K Pinnacle Strategic) and Hercules Capital warrant (75K shares) — both legally relevant for the valuation — were not picked up. The `safes_outstanding` and `warrants_outstanding` lists were both empty. There's no documentation that this sheet is read; an analyst would reasonably expect a sheet titled "Convertibles" to be read.

### #8 — Company name not extracted from title rows *(low impact)*

The cap-table sheet has "Northwind Robotics, Inc." in row 1 column A (merged across A:H). The parser correctly skipped row 1 as a title row but did not extract the company name from it. Result: the company name is "Unnamed Company". A simple rule — if no Company tab exists, take the first non-empty pre-header row as the company name candidate — would fix this.

### #9 — "Class" column unmapped, "Holder" used as class_name *(critical heuristic miss)*

Headers detected: `class_name → Holder`, `class_type → Class Type`. The literal column **`Class`** (containing "Series Seed Preferred", "Series A Preferred", etc.) was reported under unmapped headers. The parser keys the cap table by holder NAME — so "Lin Chen (Advisor)" becomes a class name instead of "Common Stock", and identical class types get split into multiple "classes" by holder.

This is a column-mapping bug that would happen on every real cap table, because the typical column ordering puts Holder first and Class second.

**Fix:** the alias list for `class_name` should prefer `Class`, `Share Class`, `Stock Class` over `Holder`/`Investor`/`Name`. As-is, the alias priority is inverted from real-world frequency.

---

## What worked

To be fair, the following did work:

1. **Subtotal-row detection.** The parser correctly identified and skipped 4 subtotal rows ("Subtotal — Common Stock", "Subtotal — Preferred Stock", etc.). This is non-trivial heuristic work.
2. **Header-row offset.** The parser found the header row on row 5 after correctly skipping 4 title/blank rows above it.
3. **Mixed date formats survived.** Two rows (Series B-1 and B-2) had dates as text strings ("April 15, 2026") instead of datetimes — these were accepted without a crash. (Whether they were correctly parsed I haven't verified, but they weren't fatal.)
4. **Footnote rows didn't crash.** The "(1) See..." and "(2) See..." rows were attempted as share classes and rejected by pydantic — but the parser surfaced them as warnings rather than crashing. (They should be filtered upstream as footnotes, but the failure mode is graceful.)
5. **Upload-error surfacing.** Before the parser fix, the upload page caught the IndexError and rendered a clear "Could not parse file: tuple index out of range" message rather than serving a 500. Good error boundary.

---

## Honest assessment

The tool **demos beautifully on its bundled fixtures** because those fixtures were authored to fit what the parser knows. On a fresh real-world cap table — built without a peek at the parser — it loses the majority of the data and silently produces a wrong waterfall.

This is the gap a Big-Four valuations partner would find in the first 5 minutes of using it on a live deal. It is fixable, but the fixes are not "polish" — they're a parser overhaul:

1. **Heuristic LP-extraction from Notes column** (or a one-screen LP-confirmation prompt).
2. **Better default for unknown class types** (look for "common"/"preferred" substring before falling back).
3. **Failure-disclosure banner** at the top of /review when row-drop count > 0.
4. **Convertibles sheet reader.**
5. **Free-text side-letter format support.**
6. **Class-name alias priority inversion** (Class > Holder).
7. **Title-row company-name extraction.**
8. **Sanitize pydantic errors** before showing them to users.

The first three are the only ones that would make this safe to put in front of Evelyn. The rest are quality improvements.

---

## What I would NOT change

The waterfall math, the live-formula workbook, the resolve forms, the diff page, the comparison panel, the what-if slider, the audit memo, the SQLite persistence — these all worked correctly on the fixtures and the design is sound. The failure is concentrated in **the input layer**: the parser's coverage of real-world Excel structure. Fix the parser and everything downstream remains useful.
