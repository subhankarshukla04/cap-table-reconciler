# System Specification — Cap Table Reconciler
Per-phase functional contract. The auditor tests against this.

This document is the sole source of truth for what the system promises. It stands alone — no other repo artifact is required to interpret it. Where a Phase 0 fact is grounded in current source, the fact is copied into this spec rather than referenced.

---

## 0. Glossary

- **CapTable**: The validated, in-memory root object representing one company at one point in time. Pydantic-enforced; contains a Company, a list of ShareClass, and lists of SideLetter, SAFE, Warrant, ConvertibleNote.
- **Company**: Metadata block — name, jurisdiction, sector, stage, valuation_date, currency (string, default "USD"), currency_symbol, summary.
- **ShareClass**: One class of equity (common, preferred, granted option pool, reserved option pool). Carries shares_outstanding, issue_price, issue_date, seniority_rank, liquidation_preference, anti_dilution, conversion_ratio, participation, instrument_subtype, voting_differential, note.
- **LiquidationPreference (LP)**: Stored as both `multiple` (float ≥ 0) and absolute `amount` (float ≥ 0) plus an `LPType`. May carry `cap_multiple` and/or `cap_amount` for participating-capped LPs.
- **LPType**: One of `non_participating`, `participating_uncapped`, `participating_capped`.
- **AntiDilution**: A variant flag (`broad_based_weighted_average`, `narrow_based_weighted_average`, or `full_ratchet`) with optional notes.
- **Participation**: Mode (`none`, `with_cap`, `without_cap`) plus optional cap-as-multiple-of-LP.
- **SideLetter**: A free-form attached agreement carrying id, title, summary, body, unresolved_questions.
- **SAFE**: An outstanding SAFE — principal, valuation_cap, discount_rate, issue_date, conversion_trigger_threshold, notes.
- **Warrant**: An outstanding warrant — holder, shares, share_class, strike_price, issue_date, expiry_date, notes.
- **ConvertibleNote**: An outstanding note — principal, valuation_cap, discount_rate, interest_rate, issue_date, qualified_financing_threshold, notes.
- **Snapshot** (Phase 2+): An immutable cap-table state stored once and linked forward via `superseded_by`. Phase 0 has only Sessions (mutable).
- **Session** (Phase 0): A transient, token-keyed working state in SQLite. Mutable. Pre-multi-tenancy.
- **Engagement** (Phase 2+): A durable, named container for a valuation deliverable. Holds one or more snapshots, resolutions, audit events, and a bound rule pack.
- **RulePack** (Phase 3+): A semver-versioned, jurisdiction-tagged collection of rules with effective-from/effective-to dates. Frozen onto an engagement at engagement-open.
- **Finding**: A checklist output — code, severity (blocker/warning/info), category, summary, detail, fields_referenced.
- **Resolution**: An analyst decision against a finding — finding_code, decision payload, citation, actor, timestamp.
- **Breakpoint**: An equity-value event in the waterfall — id, value, event description (origin, "X LP satisfied", "X converts to common", "X participation cap reached", "X pure-converts to common").
- **Tranche**: A contiguous equity-value range between two consecutive breakpoints — id, range_low, range_high, description, common_pool_shares, marginal_allocation_pct per class.
- **RegimeState**: A per-class state used by the waterfall walker — one of `lp`, `converted`, `capped`, `pure_converted`.
- **WaterfallResult**: The output of `compute_waterfall(cap_table)` — breakpoints, tranches, conversion_thresholds, cap_reach_thresholds, pure_conversion_thresholds, lp_total, total_fully_diluted_shares.
- **ParseReport**: Parser-side diagnostics — detected sheet name, column mapping, unmapped headers, ordered list of ParseWarning.
- **ParseWarning**: A structured warning — code, message, optional sheet name, optional row number.
- **CapTableDiff**: The structured comparison of two CapTables — fuzzy class-name matches, per-field deltas, set differences across side letters / SAFEs / warrants.
- **AuditMemo (Phase 0)**: A Markdown skeleton with `[ANALYST: ...]` placeholders.
- **AuditMemo (Phase 2+)**: A PDF document with cover sheet, version stamp, page numbers, named reviewer, signature block, citations to snapshot cells.
- **HolderDetail (Phase 2+)**: A sidecar table of per-shareholder rows, stored alongside the class-level CapTable when a holder-level workbook is rolled up.
- **AuditEvent (Phase 2+)**: An append-only event — actor, action, payload, ts, engagement_id.
- **Role (Phase 2+)**: One of `analyst | reviewer | partner | read_only_auditor`. Determines permitted actions per engagement.
- **Pari-passu** (Phase 3+): Two or more preferred classes sharing the same seniority tier, paid LP proportionally as a group.
- **Sibling consumer (Phase 4)**: A downstream calculator (OPM Backsolve, BSM, DCF sidecar) that consumes a validated CapTable as input.

---

## 1. Phase 0 — Current State (the baseline contract)

The contract the system honors **today** at commit head. Production targets in later phases do not alter Phase 0 unless explicitly noted as a migration.

### 1.1 Excel ingestion (`src/parser.py`)

**Input contract:**
- One `.xlsx` file, ≤ 8 MB.
- One or more sheets. The cap-table sheet name must match a member of the `CAP_TABLE_TAB_NAMES` whitelist (e.g., "Cap Table", "Capitalization", "Shareholding", and case-insensitive variants).
- The cap-table sheet must contain a header row within the first 12 rows. The header row must contain at minimum a column matching synonyms for `class_name` and a column matching synonyms for `shares`.
- Optional sibling tabs: `Company` (metadata), `Convertibles` (SAFE/warrant/note free-text rows), `SideLetter` (one row per attached side letter).
- Optional `manual_column_mapping: dict[canonical_field → actual_header_string]` argument that overrides synonym detection.
- Character set: any character openpyxl accepts. No additional restriction.

**Output contract:**
- A tuple `(CapTable, ParseReport)` on success.
- `CapTable`: a Pydantic-validated instance as defined in §1.3.
- `ParseReport` fields: `cap_table_sheet: Optional[str]`, `column_mapping: dict[canonical_field → actual_header]`, `unmapped_headers: list[str]`, `warnings: list[ParseWarning]`.
- `ParseWarning` fields: `code: str`, `message: str`, `sheet: Optional[str]`, `row: Optional[int]`.

**Behaviors:**
- Header-row detection scans the first 12 rows scoring each by the count of recognized synonyms; selects the row with the highest score (ties → earliest row).
- Column detection runs synonyms two-pass: exact-match first, then prefix/contains fallback.
- Date coercion attempts 13 documented formats including ISO (`YYYY-MM-DD`), `DD/MM/YYYY`, `MM/DD/YYYY`, `D-MMM-YYYY`, `D MMMM YYYY`, `MMMM D YYYY`, ordinal-suffixed (`14th Feb '25`), among others. Unparseable dates become `None` with no warning emitted on that row.
- Number coercion strips currency symbols (`$`, `₹`, `S$`, `Rs.`), commas, "x" suffix on multiples.
- Enum coercion maps `CCPS`, `RCPS`, `Ordinary`, `Equity Shares`, etc. to canonical `ShareClassType`. LP type aliases (`1x non-part`, `1x participating`, `1x part w/ 3x cap`) map to canonical `LPType`. AntiDilution variants (`BBWA`, `NBWA`, `full ratchet`) map likewise.
- Subtotal/total rows are detected by class-name prefix match against `_SUBTOTAL_PREFIXES` (Subtotal, Total, Sum, Fully Diluted, etc.) and silently skipped.
- Optional `Company` tab populates company metadata if present and well-formed.
- Optional `Convertibles` tab attempts regex extraction of SAFE/warrant/note rows; failures emit warnings, not exceptions.
- Optional `SideLetter` tab creates one SideLetter per row.
- Class-type defaults to `preferred` if blank or unrecognized; a `class-type-unknown` warning is emitted.

**Refusals:**
- If the file cannot be opened by openpyxl → upstream `InvalidFileException` propagates; route returns HTTP 400 with error banner.
- If no sheet name matches `CAP_TABLE_TAB_NAMES` → `ValueError("no cap-table tab found")`.
- If the header row contains neither a `class_name` nor a `shares` synonym → `ValueError("required columns class_name and/or shares not found")`.
- If a row constructs a `ShareClass` that fails Pydantic validation (e.g., preferred without LP, negative shares, duplicate name within the workbook) → row is skipped; a warning is appended; parsing continues.
- If the resulting `CapTable` itself fails model validation (e.g., zero share classes survived, duplicate names, duplicate preferred seniority ranks) → Pydantic `ValidationError` propagates to the caller; the route returns HTTP 400 with the validation message.
- File size > 8 MB → Flask returns HTTP 413.

**Performance contract:**
- No latency or throughput SLO promised in Phase 0. The system is local-only.

**Persistence contract:**
- Parser itself is pure — no state. The parsed CapTable + ParseReport are persisted only when the calling route writes them to SessionStore (see §1.9, §1.10).

---

### 1.2 PDF intake (`src/pdf_intake.py`)

**Input contract:**
- A file path or in-memory blob containing a PDF.
- A `sl_id: str` (caller-assigned side-letter id).
- A `fallback_title: str` used if title heuristic fails.

**Output contract:**
- `extract_text(blob_or_path) → (str, list[str])` returns full extracted text (or empty string) and a list of warning strings.
- `parse_pdf_to_side_letter(blob_or_path, sl_id, fallback_title) → dict` returns a SideLetter-shaped dict with keys `id`, `title`, `summary`, `body`, `unresolved_questions`.

**Behaviors:**
- Extraction is `pdfplumber`-based, text only.
- Title heuristic: first non-blank line < 120 characters, not ending with a period.
- Unresolved-question heuristic: lines matching case-insensitive regex `^\s*(q\d*\.|question:|todo:)` are appended to `unresolved_questions`.
- The full text is returned as `body`.

**Refusals:**
- Image-only PDFs (no extractable text) return `("", ["pdf-no-text-recovered"])` and a SideLetter dict with empty body. No OCR is attempted. No LLM fallback. No fabrication.
- Non-PDF uploads are rejected by the route layer (see §1.10) with HTTP 400.

**Performance contract:**
- None promised.

**Persistence contract:**
- PDF intake is pure; persistence happens only when the calling route appends the extracted SideLetter to the session's CapTable.

---

### 1.3 Cap-table data model (`src/models.py`)

**Field constraints (exhaustive):**

`Company`:
- `name: str` (required).
- `jurisdiction: Optional[str]`.
- `sector: Optional[str]`.
- `stage: Optional[str]`.
- `valuation_date: Optional[date]`.
- `currency: str = "USD"`.
- `currency_symbol: str = "$"`.
- `summary: Optional[str]`.

`LiquidationPreference`:
- `multiple: float`, must be ≥ 0.
- `amount: float`, must be ≥ 0 (units: company home currency).
- `type: LPType` (required).
- `cap_multiple: Optional[float]`, if present must be ≥ 0.
- `cap_amount: Optional[float]`, if present must be ≥ 0.
- Validator `cap_required_when_capped`:
  - If `type == participating_capped`: exactly one of `cap_multiple` or `cap_amount` must be set (not zero, not both).
  - If `cap_multiple` set: must be ≥ 1.0.
  - If `cap_amount` set: must be ≥ `amount`.
  - Violations raise `ValueError` (Pydantic `ValidationError` at construction).

`AntiDilution`:
- `variant: Optional[AntiDilutionVariant]` (one of `broad_based_weighted_average`, `narrow_based_weighted_average`, `full_ratchet`).
- `notes: Optional[str]`.

`Participation`:
- `mode: ParticipationMode = none` (one of `none`, `with_cap`, `without_cap`).
- `cap_multiple_of_lp: Optional[float]`, if present must be ≥ 0.
- `notes: Optional[str]`.

`ShareClass`:
- `name: str` (required, unique within CapTable).
- `type: ShareClassType` (one of `common`, `preferred`, `option_pool_granted`, `option_pool_reserved`).
- `shares_outstanding: int`, must be ≥ 0.
- `issue_price: Optional[float]`, if present must be ≥ 0.
- `issue_date: Optional[date]`.
- `seniority_rank: int`, default 99, must be in [1, 99] inclusive.
- `liquidation_preference: Optional[LiquidationPreference]`.
- `anti_dilution: Optional[AntiDilution]`.
- `conversion_ratio: Optional[float]`, if present must be ≥ 0.
- `participation: Optional[Participation]`.
- `instrument_subtype: Optional[str]`.
- `voting_differential: Optional[str]`.
- `note: Optional[str]`.
- Validator `preferred_must_have_lp`:
  - If `type == preferred`: `liquidation_preference` must be non-null. Violation → `ValueError`.
  - If `type ∈ {common, option_pool_granted, option_pool_reserved}`: `liquidation_preference` must be null. Violation → `ValueError`.
- Property `is_common_pool_member`: True iff type ∈ {common, option_pool_granted}.
- Property `excluded_from_waterfall`: True iff type == option_pool_reserved.

`SideLetter`:
- `id: str`, `title: str`, `summary: Optional[str]`, `body: Optional[str]`, `unresolved_questions: list[str]` (default empty).

`SAFE`:
- `id: str`, `principal: float ≥ 0`, `valuation_cap: Optional[float] ≥ 0`, `discount_rate: Optional[float] ∈ [0,1]`, `issue_date: Optional[date]`, `conversion_trigger_threshold: Optional[float] ≥ 0`, `notes: Optional[str]`.

`Warrant`:
- `id: str`, `holder: str`, `shares: int ≥ 0`, `share_class: str`, `strike_price: float ≥ 0`, `issue_date: Optional[date]`, `expiry_date: Optional[date]`, `notes: Optional[str]`.

`ConvertibleNote`:
- `id: str`, `principal: float ≥ 0`, `valuation_cap: Optional[float] ≥ 0`, `discount_rate: Optional[float] ∈ [0,1]`, `interest_rate: Optional[float] ∈ [0,1]`, `issue_date: Optional[date]`, `qualified_financing_threshold: Optional[float] ≥ 0`, `notes: Optional[str]`.

`CapTable`:
- `company: Company` (required).
- `share_classes: list[ShareClass]`, must contain at least 1 element.
- `side_letters: list[SideLetter]` (default empty).
- `safes_outstanding: list[SAFE]` (default empty).
- `warrants_outstanding: list[Warrant]` (default empty).
- `convertible_notes_outstanding: list[ConvertibleNote]` (default empty).
- Validator `share_class_names_unique`: duplicate names → `ValueError("duplicate share class names: [...]")`.
- Validator `preferred_seniority_unique`: duplicate seniority_rank among preferred classes → `ValueError("duplicate seniority ranks among preferred classes: [...]")`.
- Validator `at_least_one_class`: empty list → `ValueError("cap table must have at least one share class")`.
- Property `total_fully_diluted_for_waterfall`: sum of `shares_outstanding` across non-excluded classes (everything except reserved pools).
- Property `preferred_classes_by_seniority`: preferred classes sorted ascending by seniority_rank (rank 1 = most senior).

**All Pydantic models** use `ConfigDict(extra="forbid")` — unknown keys raise `ValidationError`.

**Refusals:**
- Any field violation, model validator violation, or unknown field → `pydantic.ValidationError`.
- Currency mismatch within a single CapTable: not enforced (the system assumes the caller has converted to the company's home currency; see §1.11).

**Persistence contract:**
- The model is in-memory only. JSON serialization is via `model_dump_json()` for storage.

---

### 1.4 Checklist — 8 rules (`src/checklist.py`)

**Input contract:**
- A validated `CapTable`.

**Output contract:**
- `list[Finding]` sorted ascending by severity rank (blocker → warning → info) then by `code`.
- `Finding` fields: `code: str`, `severity: str ∈ {blocker, warning, info}`, `category: str`, `summary: str`, `detail: Optional[str]`, `fields_referenced: tuple[str, ...]` (dot-path references like `share_classes[Series A].anti_dilution.variant`).

**Rules (exhaustive, in code order):**

1. **AD-MISSING** — category `anti_dilution`, severity `blocker`. Triggered when a preferred ShareClass has either `anti_dilution is None` or `anti_dilution.variant is None`. `fields_referenced` cites `share_classes[<name>].anti_dilution.variant`.
2. **AD-RATCHET** — category `anti_dilution`, severity `info`. Triggered when a preferred ShareClass has `anti_dilution.variant == full_ratchet`. Cites `share_classes[<name>].anti_dilution.variant`.
3. **LP-PART-CAP** — category `liquidation_preference`, severity `info`. Triggered when a preferred ShareClass has `liquidation_preference.type == participating_capped`. Cites `share_classes[<name>].liquidation_preference.cap_multiple` (or `cap_amount`).
4. **POOL-STALE** — category `option_pool`, severity `warning`. Triggered when a granted option pool's `issue_date` is more than 270 days before the most recent preferred round's `issue_date`. Cites `share_classes[<pool_name>].issue_date`.
5. **SAFE-UNCONVERTED** — category `safe`, severity `blocker`. Triggered when a SAFE has `conversion_trigger_threshold` set and at least one preferred class has `issue_date > safe.issue_date` and a derived round-size meeting/exceeding the threshold. Cites `safes_outstanding[<id>].conversion_trigger_threshold`.
6. **WARRANT** — category `warrant`, severity `warning`. Triggered when any `Warrant` is present in `warrants_outstanding`. Cites `warrants_outstanding[<id>]`.
7. **SIDE-LETTER** — category `side_letter`, severity `warning`. Triggered when a side letter has (a) no body and no summary, OR summary length < 30 characters, OR a non-empty `unresolved_questions` list. Cites `side_letters[<id>].body` (or `.summary` or `.unresolved_questions`).
8. **VOTING-DIFF** — category `governance`, severity `info`. Triggered when any ShareClass has a non-null, non-empty `voting_differential` string. Cites `share_classes[<name>].voting_differential`.

**Refusals:**
- No analyst judgment baked in. No probabilistic scoring. No findings beyond the 8 codes above.

**Persistence contract:**
- Findings are derived; not persisted. Recomputed on each session read in Phase 0.

---

### 1.5 Waterfall engine (`src/waterfall.py`)

**Input contract:**
- A validated `CapTable`.

**Output contract:**
- `WaterfallResult` with:
  - `breakpoints: list[Breakpoint]` (sorted ascending by `value`, deduplicated within tolerance).
  - `tranches: list[Tranche]` (one per consecutive breakpoint pair; last tranche has `range_high=None` meaning unbounded above).
  - `conversion_thresholds: dict[class_name → float]`.
  - `cap_reach_thresholds: dict[class_name → float]`.
  - `pure_conversion_thresholds: dict[class_name → float]`.
  - `lp_total: float` (sum of LP amounts across all preferred classes).
  - `total_fully_diluted_shares: int` (sum across non-excluded classes).
- `Breakpoint`: `id: str`, `value: float`, `event: str` (one of "origin", "{name} LP satisfied", "{name} converts to common", "{name} participation cap reached", "{name} pure-converts to common").
- `Tranche`: `id: str`, `range_low: float`, `range_high: Optional[float]`, `description: str`, `common_pool_shares: Optional[int]`, `marginal_allocation_pct: dict[class_name → float]` (values in [0, 1]; sum to 1.0 within float tolerance per tranche).

**Auxiliary outputs:**
- `cumulative_payouts_at_breakpoints(cap_table, result) → dict[class_name → list[(V, cumulative_payout)]]`.
- `breakpoint_explanations(cap_table, result) → list[dict]` — per-breakpoint formula and numeric walk-through.
- `chart_payload(cap_table, result) → dict` — Chart.js-friendly payload with datasets per class, breakpoint markers, color scheme.

**Behaviors:**
- LP-cleared breakpoints computed in seniority order (most-senior first), cumulative LP thresholds.
- For each non-participating preferred: conversion threshold V such that converted-as-common payout equals LP, accounting for senior LP overhang.
- For each participating-capped preferred: cap-reach threshold V_cap (where LP + participation share = cap) and pure-conversion threshold V_pure (where pure-converted payout exceeds cap).
- Senior-above-capped handling: when a non-participating senior sits above a capped junior, the regime walker reflects the senior's conversion timing in the junior's available pool.
- Degenerate normalization: if a class has `cap_multiple ≤ 1.0`, the class is treated as `non_participating` for waterfall purposes.
- Breakpoint deduplication: values within 1e-6 relative tolerance OR 0.01 absolute (whichever larger) are merged. Adaptive per max value across the run.
- Pool weighting: common pool contributions weighted by `conversion_ratio` (defaults to 1.0 when None) to reflect post-ratchet share counts.
- Reserved option pool (`option_pool_reserved`) excluded from waterfall entirely.
- Tranches are built by simulating regime at each tranche midpoint; marginal allocation per regime is the per-class share of the marginal dollar in that tranche.

**Refusals:**
- Pari-passu preferred classes are rejected upstream by `preferred_seniority_unique` in the model. The waterfall never sees them.
- The waterfall does **not** convert SAFEs, warrants, or convertible notes. They remain as outstanding instruments; the checklist flags them.
- No fair value, no DLOM, no PWERM, no Backsolve.

**Performance contract:**
- Deterministic and pure. Same input → same output, bit-for-bit, within the dedup tolerance window stated above.
- No SLO promised. Tested against 23,300+ random cap tables with zero invariant violations.

**Persistence contract:**
- Result is derived; not persisted. Recomputed on each session read in Phase 0.

---

### 1.6 Live-formula Excel exporter (`src/formula_workbook.py`)

**Input contract:**
- A validated `CapTable` and a `WaterfallResult`.

**Output contract:**
- An `openpyxl.Workbook` with the following sheets in order: `README`, `Inputs`, `Calculations`, `States`, `Breakpoints`, `TrancheAlloc`, `CumulativePayout`, `Chart`, `BPMarkers` (hidden).
- All breakpoint values, allocation percentages, and chart series are driven by Excel formulas referencing named input ranges on the `Inputs` sheet — not literal values.

**Behaviors:**
- `Inputs` sheet contains editable (yellow-filled) cells: per-class `shares`, `PPS`, `LP_multiple`, `cap_multiple`, `conversion_ratio`.
- `Calculations` derives LP amounts (`= shares * PPS * LP_multiple`) and cumulative LPs in seniority order.
- `States` encodes regime per `(tranche, class)` as a literal string in `{lp, converted, capped, pure_converted}`, plus pool-membership formulas.
- `Breakpoints` sheet contains formulas synthesized from the regime literals on `States`, referencing `Calculations` for LP and conversion math.
- `TrancheAlloc` cells are formulas referencing `States` pool-membership × share counts.
- `CumulativePayout` accumulates allocation × value-delta down the breakpoint sequence.
- `Chart` is a native Excel scatter chart sourced from `CumulativePayout` with vertical dashed marker lines drawn from `BPMarkers`.

**Refusals:**
- If an analyst edits cells in a way that reorders breakpoints (e.g., raises a Seed LP above a Series A threshold), the regime literals on `States` are stale and the workbook output is silently incorrect. The `README` sheet states this limitation. The workbook does NOT attempt to detect or warn about this.
- Structural edits (adding/removing classes, changing LP type) are not supported in Excel; the user must re-export from Python.

**Performance contract:**
- None promised.

**Persistence contract:**
- The workbook is generated on-demand by the `/export/<token>_live.xlsx` route; not stored server-side.

---

### 1.7 Snapshot diff (`src/diff.py`)

**Input contract:**
- Two validated `CapTable` instances (left and right).

**Output contract:**
- `CapTableDiff` with:
  - `left_company: str`, `right_company: str`.
  - `matches: list[ClassMatch]`.
  - `class_diffs: list[ClassDiff]`.
  - `side_letters_added: list[str]`, `side_letters_removed: list[str]`.
  - `safes_added: list[str]`, `safes_removed: list[str]`.
  - `warrants_added: list[str]`, `warrants_removed: list[str]`.
  - `summary: str` (human-readable count of adds/removes/renames/changes).
- `ClassMatch`: `left_name: Optional[str]`, `right_name: Optional[str]`, `similarity: float ∈ [0, 1]`, `status: str ∈ {matched, added, removed, renamed}`.
- `FieldDelta`: `field: str`, `left: object`, `right: object`.
- `ClassDiff`: `match: ClassMatch`, `deltas: list[FieldDelta]`.

**Behaviors:**
- Class-name matching: exact-match pass first (O(n)), then greedy best-match by Levenshtein similarity > 0.6, then remaining left → `removed`, remaining right → `added`.
- Compared fields per matched class: `shares_outstanding`, `issue_price`, `seniority_rank`, LP description string (multiple + type), `conversion_ratio`, `anti_dilution.variant`.

**Refusals:**
- No semantic interpretation of deltas. No "rule implications" produced in Phase 0 (that arrives in Phase 3 — see §4.4).

**Persistence contract:**
- Pure function. Output not persisted.

---

### 1.8 Markdown audit memo (`src/audit_memo.py`)

**Input contract:**
- A validated `CapTable`, a `WaterfallResult`, a `list[Finding]`, and an optional `resolutions: list[dict]`.

**Output contract:**
- A single Markdown string.

**Required sections (in order):**
1. Capital structure table — columns: class, type, shares, PPS, issue_date, seniority, LP description, anti-dilution.
2. Side letters — title, summary, open questions, plus prompt: `[ANALYST: confirm effect on present-date waterfall]`.
3. Convertibles / warrants — SAFE/warrant summary plus prompt: `[ANALYST: assess deep-ITM treatment]`.
4. Gap-detection findings — table of code, severity, summary; applied resolutions appended below.
5. Waterfall breakpoints — id, value, event.
6. Tranche allocation matrix — tranche, range, % per class.
7. Methodology disclosures — participating-with-cap, full-ratchet, dual-class voting (flagged only when present).
8. Analyst sign-off checklist — blockers adjudicated, fair-value method `[ANALYST: ...]`, DLOM band `[ANALYST: confirm 25–35%]`, subsequent events `[ANALYST: ...]`.

**Refusals:**
- No PDF output in Phase 0. Markdown only.
- No fair value, no DLOM number, no OPM output. Those are `[ANALYST: ...]` placeholders by design.
- No automatic citation hyperlinks. The Markdown is plain text.

**Persistence contract:**
- Generated on-demand; not stored.

---

### 1.9 Persistence (`src/persistence.py`)

**Input contract:**
- `SessionStore` provides a dict-like interface backed by SQLite.

**Output contract:**
- API: `__contains__(token) → bool`, `__getitem__(token) → dict`, `get(token, default)`, `__setitem__(token, sess)`, `flush(token)`, `clear()`, `__len__()`, `list_sessions() → list[dict]`, `delete(token) → bool`.
- Session dict shape: `{cap_table, original_cap_table, parse_report, raw_excerpt, fixture_id, resolutions, waterfall (derived), findings (derived)}`.

**Schema:**
- Single table `sessions(token TEXT PRIMARY KEY, created_at TEXT NOT NULL, fixture_id TEXT, cap_table_json TEXT NOT NULL, original_cap_table_json TEXT, parse_report_json TEXT, raw_excerpt_json TEXT, resolutions_json TEXT DEFAULT '[]')`.
- DB file at `data/sessions.db`.

**Behaviors:**
- Reads check in-memory cache first, fall back to DB.
- Writes update cache and immediately persist via `INSERT ... ON CONFLICT DO UPDATE`.
- Waterfall and findings are NOT persisted; recomputed on read.
- Migration helper `_ensure_columns()` adds `original_cap_table_json` if missing (idempotent).

**Refusals:**
- No multi-user isolation. Anyone with a session token can read or mutate that session.
- No audit log of who read/wrote what.
- No backup. DB loss = sessions loss.

**Persistence contract:**
- Sessions survive process restart. In-memory cache is empty on startup; hydrated on-demand from DB.

---

### 1.10 Flask app surface (`app.py`) — exhaustive route contract

App configuration:
- Upload cap: 8 MB (Flask's `MAX_CONTENT_LENGTH`).
- All responses receive `Cache-Control: no-store` via after-request hook.
- SQLite session store at `data/sessions.db`.

Routes:

| Method | Path | Input | Behavior | Output / status |
|---|---|---|---|---|
| GET | `/` | none | Render landing | `index.html`, 200 |
| POST | `/upload` | multipart with `.xlsx` ≤ 8 MB | Parse, validate, create session | 302 → `/review/<token>` on success; 200 with error re-render on failure |
| GET | `/demo/<fixture_id>` | path param | Load one of 5 built-in fixtures | 302 → `/review/<token>`; 404 if fixture unknown |
| GET | `/review/<token>` | path param | Render review page | `review.html`, 200; 404 if token unknown |
| POST | `/resolve/<token>/safe/<safe_id>` | form: target class, share count | Add shares to class, remove SAFE, append resolution, recompute | 302 → `/review/<token>`; 404 if unknown |
| POST | `/resolve/<token>/anti_dilution/<path:class_name>` | form: variant, citation | Set `anti_dilution.variant`, append resolution, recompute | 302 → `/review/<token>`; 404 if unknown |
| POST | `/resolve/<token>/warrant/<warrant_id>` | form: action (include/exclude), shares | Mutate class or document exclusion, append resolution, recompute | 302 → `/review/<token>`; 404 if unknown |
| POST | `/resolve/<token>/side_letter/<sl_id>` | form: scope adjudication, body addition | Append to SideLetter body, append resolution, recompute | 302 → `/review/<token>`; 404 if unknown |
| POST | `/resolve/<token>/pool/<path:pool_name>` | form: action (document gap / update date) | Mutate pool or document, append resolution, recompute | 302 → `/review/<token>`; 404 if unknown |
| POST | `/upload_side_letter/<token>` | multipart PDF | Extract text via pdfplumber, append SideLetter, append resolution, recompute | 302 → `/review/<token>`; 400 on non-PDF; 404 if token unknown |
| GET | `/waterfall/<token>` | path param | Render waterfall page with breakpoints, tranches, chart | `waterfall.html`, 200; 404 if unknown |
| POST | `/whatif/<token>` | form: overrides for shares / LP mult | Compute scenario waterfall in-memory (no persist); return fragment | `_whatif_panel.html` partial, 200; 404 if unknown |
| GET | `/export/<token>.xlsx` | path param | Render static workbook (Company / Cap Table / Breakpoints / Tranches / Findings / Convertibles / Side Letters) | binary, 200; 404 if unknown |
| GET | `/export/<token>_live.xlsx` | path param | Render live-formula workbook (§1.6) | binary, 200; 404 if unknown |
| GET | `/export/<token>.json` | path param | Structured JSON dump | JSON, 200; 404 if unknown |
| GET | `/export/<token>.md` | path param | Audit memo Markdown | text/markdown, 200; 404 if unknown |
| GET | `/export/<token>.zip` | path param | Bundle: JSON + static xlsx + live xlsx + memo | binary, 200; 404 if unknown |
| GET | `/compare/<token>` | path param | Render before/after comparison of original vs current cap table | `compare.html`, 200; 404 if unknown |
| GET | `/sessions` | none | List all persisted sessions, newest first | `sessions.html`, 200 |
| POST | `/sessions/<token>/delete` | path param | Delete session from cache + DB | 302 → `/sessions` |
| GET | `/diff` | none | Render diff form | `diff.html`, 200 |
| POST | `/diff` | multipart with two `.xlsx` | Parse both, compute diff, render inline | `diff.html` with results, 200 |
| GET | `/healthz` | none | Liveness probe | JSON `{"status": "ok"}`, 200 |

**Session token contract:**
- 8 characters, URL-safe random (generated by `_new_token()`).
- No expiration in Phase 0.
- No auth check; anyone with the token can access.

**Template filters:**
- `money(value, symbol)`, `pct(value)`, `commas(value)`.

**Refusals:**
- No CSRF protection (local-only assumption).
- No login.
- No rate limiting.
- HTTP 413 on uploads > 8 MB.

---

### 1.11 Explicit Phase 0 refusals

The system promises NOT to do the following in Phase 0:

1. **No LLM in the calculation pipeline.** No clause extraction, no field inference, no narrative generation. Side letters are stored verbatim.
2. **No fair-value output.** Waterfall produces breakpoints and allocations; fair value is the analyst's next step.
3. **No OPM Backsolve.**
4. **No DLOM calculation.**
5. **No PWERM.**
6. **No DCF.**
7. **No automatic SAFE / warrant / convertible-note conversion math.** Analyst computes shares and enters via resolve form.
8. **No automatic anti-dilution adjustment.** If a down-round triggers full-ratchet, the analyst enters post-trigger shares and `conversion_ratio` manually.
9. **No multi-currency FX conversion.** All amounts assumed to be in the company's home currency.
10. **No OCR for image-only PDFs.** `pdf-no-text-recovered` warning emitted.
11. **No pari-passu seniority.** Model rejects duplicate preferred seniority ranks.
12. **No auth, no multi-tenancy, no audit log.** Local-only, anyone-with-token access.
13. **No PDF audit memo.** Markdown only.
14. **No deployment beyond `localhost:5050`.**
15. **No external API beyond Flask routes and the CLI.**
16. **No backup of the session DB.**
17. **No confidence scoring on findings.**

---

## 2. Phase 1 — Observe (Days 1–30 at Qapita)

Phase 1 produces **artifacts**, not code. The contract is on what those artifacts must contain and the decision they support.

### 2.1 The workflow map

**Output contract:**
- A document of at least 6 pages, one per workflow phase: Client kickoff, Data intake, Model build, Memo drafting, Auditor handoff, Re-engagement.
- For each phase, fields:
  - **Engagement column header**: name and short id for at least 3 shadowed engagements.
  - **Observed activities**: bulleted list of distinct steps performed.
  - **Time tally** (hours, decimal): per engagement per activity.
  - **Tool intersection**: marked as `would-have-helped` / `would-have-hurt` / `irrelevant` for each step, with one-line justification.
  - **Data format observed**: Excel / Qapita platform export / PDF / email / other (specify).
  - **Owner**: which role on the team performed the step (analyst / reviewer / partner / external client / auditor).

**Evidence rule:**
- Every time tally must be backed by a contemporaneous shadow note (timestamp + free-text observation). Time tallies fabricated from memory or estimated post-hoc are out of contract.

**Refusals:**
- No anonymized aggregate ("teams typically take 6 hours") in place of concrete per-engagement observation.
- No tool advocacy phrasing in the map itself; the map is descriptive only.

### 2.2 The Day-30 pitch

**Output contract:**
- A single document (one page recommended, up to two pages) delivered to Evelyn at the Day-30 1:1.
- Sections (in order):
  1. **What I observed** — Concrete time tallies from the three engagements. Numbers come from §2.1.
  2. **What would have changed with the tool** — Per-engagement quantified delta in hours, by activity. Must include at least one explicit `would-have-saved-nothing` line where applicable. No selling.
  3. **The proposal** — Two paths spelled out: Path A (internalize) and Path B (keep external). Decision-criteria for each.

**Quantification requirements:**
- Hours saved / lost must be expressed as a per-engagement number with a directionality (+ for time saved, − for time added by tool friction).
- Total weekly time impact must be expressed in hours/week based on observed engagement volume.

**Refusals:**
- No revenue figures.
- No headcount-savings claims.
- No timeline commitments embedded in the pitch (timelines are negotiated separately if Path A is chosen).

### 2.3 Go/no-go decision criteria

The pitch must declare the objective conditions under which each path is selected:

**Path A — internalize — is chosen iff:**
- Evelyn agrees that the tool reduces analyst hours per engagement by a measurable amount on at least one of the three shadowed engagements.
- Engineering greenlight (Vamsee) is reachable for adding a new internal service (or sidecar).
- At least one upcoming engagement in Months 2–3 can serve as the first internal pilot.

**Path B — keep external — is chosen iff:**
- Any of the above three conditions fails, OR Evelyn explicitly prefers focus on engagement work.

The criteria are stated; Evelyn's decision is recorded verbatim in the pitch document after the meeting.

### 2.4 Code contract for Phase 1

**Zero new production code is shipped in Phase 1.**

This is an explicit refusal. The tool is not modified between Aug 1 and the Day-30 1:1 except for personal-laptop fixes that have zero observable effect on the public artifact.

---

## 3. Phase 2 — Internal Pilot (Months 2–3)

Assumes Path A from §2.3. Phase 2 closes four production gaps.

### 3.1 Qapita data ingestion

**Input contract:**
- A read-only adapter `ingestion/qapita_api.py` that consumes Qapita's internal cap-table data source (API or DB, depending on infra decision in Phase 1).
- Input parameters: `client_id: str`, `as_of: date`, `engagement_id: uuid`.

**Output contract:**
- A validated `CapTable` matching the Phase 0 Pydantic schema in §1.3 exactly.
- A `ParseReport` indicating field-level provenance per source column.

**Mapping completeness rule:**
- 100% of canonical `CapTable` field names defined in §1.3 must either be (a) populated from the Qapita source, or (b) explicitly marked as `unknown` in the `ParseReport`. No silent dropouts allowed.

**Failure modes:**
- If the Qapita source is missing a required `CapTable` field (e.g., anti-dilution variant, participation cap), the adapter:
  - Sets the field to `None` in the CapTable.
  - Appends a `ParseWarning` with code `qapita-source-missing-<field>` and source-row reference.
  - Does NOT fabricate a default value.
- If the Qapita source has a value that fails Pydantic validation, the adapter raises `QapitaIngestError` with the offending field path and value.

**Backwards compatibility:**
- The existing Excel ingestion path (§1.1) is unchanged. The two adapters are independent; both emit the same canonical `CapTable` shape.

**Performance contract:**
- Cold-start pull for a 50-class cap table: under 5 seconds wall-clock.

**Refusals:**
- The Qapita adapter NEVER writes back to Qapita's source. Read-only.
- The Qapita adapter NEVER infers missing fields via LLM or heuristic. Missing = explicitly marked unknown.

**Persistence contract:**
- The pulled CapTable becomes a Snapshot in the engagement's snapshot chain (see §3.2).

---

### 3.2 Multi-tenancy, auth, immutable audit log

**Engagement model — schema:**

```
engagement
  id: uuid (PK)
  client_id: str (FK to Qapita client)
  valuation_date: date
  standard_of_value: enum {ifrs13, asc820, sec409a, ifrs2}
  status: enum {open, review, signed, archived}
  created_by: user_id
  created_at: timestamp
  bound_rule_pack_id: uuid (set at engagement-open; immutable after)
```

**Engagement lifecycle transitions:**
- `open → review` — Triggered when analyst submits the engagement for reviewer attention. Allowed actors: `analyst`, `reviewer`, `partner`.
- `review → open` — Triggered by reviewer/partner sending back for rework. Allowed actors: `reviewer`, `partner`.
- `review → signed` — Triggered by partner sign-off. Allowed actors: `partner` only. Refused if any blocker finding is unresolved.
- `signed → archived` — Triggered after audit retention period (configurable; default 7 years per Big 4 norms). Allowed actors: system cron only.
- All other transitions are refused with HTTP 409 `engagement-invalid-transition`.

**Snapshot model — schema:**

```
snapshot
  id: uuid (PK)
  engagement_id: uuid (FK)
  source: enum {excel_upload, qapita_pull, manual_edit, resolution}
  source_filename: Optional[str]
  source_hash: str (SHA-256 of original bytes)
  cap_table_json: text (canonical, immutable)
  parse_report_json: text
  created_by: user_id
  created_at: timestamp
  superseded_by: Optional[uuid] (FK; NULL if current head)
```

**Snapshot immutability:**
- The `snapshots` table has NO `UPDATE` statement in any production code path.
- Any "edit" creates a new snapshot row with `source = manual_edit` or `source = resolution` and sets the previous head's `superseded_by` to the new id.
- A snapshot is the byte-for-byte cap table at one moment. Reading the engagement's history reads the chain.

**Authentication:**
- Qapita SSO. No custom user table.
- Session tokens issued by SSO; tool validates on every request.
- Read-only auditor role uses a scoped magic-link token issued by a partner; expires after configurable TTL (default 30 days).

**Role enum and per-role permissions (exhaustive):**

`analyst`:
- May create engagements assigned to themselves.
- May upload Excel and trigger Qapita pulls within their engagements.
- May create snapshots via edits/resolutions.
- May create resolutions.
- May read the audit log for their engagements.
- May export artifacts (XLSX, JSON, PDF memo draft).
- May NOT transition engagement to `signed`.
- May NOT delete snapshots, resolutions, or audit events.
- May NOT read other analysts' engagements.

`reviewer`:
- All analyst permissions on engagements assigned to them as reviewer.
- May transition `open ↔ review` on their assigned engagements.
- May add reviewer-note resolutions.
- May NOT transition to `signed`.
- May NOT delete anything.

`partner`:
- All reviewer permissions.
- May transition `review → signed` on engagements they sponsor.
- May issue read-only auditor magic-link tokens.
- May NOT delete snapshots, resolutions, or audit events.
- May NOT bypass blocker-finding gate on sign-off.

`read_only_auditor`:
- Scoped to a single engagement via magic-link token.
- May read all snapshots, resolutions, audit events, exports for that engagement.
- May NOT write anything.
- May NOT read other engagements.
- May NOT extend the token's TTL.

**Tenancy isolation:**
- Every read or write query takes `engagement_id` as a required argument.
- The data-access layer rejects queries without it (`TenancyError: engagement_id required`).
- Cross-engagement queries are forbidden at the query layer, not the application layer.

**Audit log — `audit_event` schema:**

```
audit_event
  id: uuid (PK)
  engagement_id: uuid (FK)
  event_type: str (e.g., "snapshot.created", "resolution.added", "engagement.signed")
  payload_json: text
  actor: user_id
  ts: timestamp
```

**Audit log behaviors:**
- Append-only. No `UPDATE`, no `DELETE` statement on `audit_event` in any code path.
- Every state-changing API call emits exactly one audit event.
- Queryable by engagement_id, by event_type, by actor, by time range.

**Refusals (HTTP / error signals):**
- `UPDATE` on any snapshot row → application raises `SnapshotImmutableError`; never reaches DB.
- `UPDATE` or `DELETE` on resolutions → application raises `ResolutionImmutableError`.
- `UPDATE` or `DELETE` on audit_event → application raises `AuditLogImmutableError`.
- Unauthorized action by a role → HTTP 403 with code `role-not-permitted`.
- Cross-engagement read attempt → HTTP 403 with code `tenancy-violation`.
- Engagement transition refused → HTTP 409 with code `engagement-invalid-transition`.
- Read-only auditor write attempt → HTTP 403 with code `read-only-token`.

**Persistence contract:**
- Engagements, snapshots, resolutions, audit_events persist in Qapita's managed DB (Postgres assumed). All survive restart and are backed up per Qapita infra policy.

---

### 3.3 Holder-level Indian-CFO Excel rollup

**Input contract:**
- A `.xlsx` workbook where rows are individual shareholders, not aggregated by class.
- May contain hundreds of holder rows.
- Class structure may be encoded in (a) an explicit class column, (b) repeated issue_date + issue_price clusters, or (c) name patterns in the holder column.

**Detection heuristics (priority order):**
1. **Explicit class column.** If a column matching `Class`, `Security Type`, `Instrument` (case-insensitive, synonym-matched) is found, group holders by its value.
2. **Issue-date + price clustering.** Group holders sharing identical `(issue_date, issue_price, instrument_type_alias)` triplets. Confidence weighted by cluster size.
3. **Name-pattern clustering.** Pattern-mine holder names for class hints (e.g., "Series A Investor Mr. X" → Series A cluster).
4. **Manual UI fallback.** If automated heuristics produce a grouping with overall confidence < 0.80, surface a UI step displaying proposed groupings with samples; analyst confirms or remaps each group.

**Output contract:**
- A class-level `CapTable` (Phase 0 shape) plus a `HolderDetail` sidecar table.
- `HolderDetail` rows: `holder_name`, `class_name`, `shares`, `issue_date`, `issue_price`, `source_row_index`.
- A `ParseReport` whose `warnings` list records every aggregation decision: code `rollup-applied`, message containing the heuristic used (e.g., `"Grouped 47 holders → Series A based on issue-date cluster 2023-04-15"`) and the count of holders grouped.

**Audit requirement:**
- Every aggregation decision is recorded in the `ParseReport`.
- The `HolderDetail` sidecar is queryable from the engagement so the auditor can drill from a class to its constituent holders.

**Refusal:**
- If heuristic confidence < 0.80 and no analyst confirmation is recorded → the parse returns no `CapTable` and a `HolderRollupAmbiguous` error with the proposed groupings as a payload. The system NEVER silently guesses.
- UI banner copy on the fallback step: `"Automated grouping confidence is below 80%. Please confirm or remap the proposed share classes."`.

**Persistence contract:**
- Both the class-level CapTable and the HolderDetail sidecar are persisted as part of the snapshot. HolderDetail is immutable alongside the snapshot.

---

### 3.4 Big-4 PDF audit memo

**Output contract:**
- A WeasyPrint-rendered PDF (system dep `libpangoft2-1.0-0` required).

**Required sections (in order, marked auto-populated `[A]` or analyst judgment `[J]`):**
1. **Cover sheet** `[A]` — engagement name, client, valuation date, standard of value, version stamp, named reviewer, named partner.
2. **Section 01 — Engagement** `[A]` — engagement id, scope of work, dates.
3. **Section 02 — Scope** `[A]` — Standard of Value (IFRS 13 / ASC 820 / 409A / IFRS 2) explicit.
4. **Section 03 — Methodology** `[A]` — declares the tool's role as data integrity, not valuation.
5. **Section 04 — Capital structure table** `[A]` — every cell cites `snapshot_id + cell_reference` as a hyperlink.
6. **Section 05 — Findings & resolutions** `[A]` — every finding lists code, severity, summary, fields_referenced, applied resolution.
7. **Section 06 — Waterfall breakpoints & tranches** `[A]` — full table.
8. **Section 07 — Assumptions** `[J]` — explicit `[ANALYST: ...]` blocks.
9. **Section 08 — Conclusion** `[J]` — explicit `[ANALYST: ...]` blocks.
10. **Appendix A — Provenance** `[A]` — every non-vanilla clause cites NVCA / VIMA / charter §.
11. **Appendix B — Changelog** `[A]` — snapshot history, who changed what when, sourced from `audit_event`.

**Page elements (on every page):**
- Footer with version stamp `vYYYY-MM-DD-HHMMSS-shortcommit`.
- Page numbers `page X of Y`.
- Engagement id watermark (light grey).
- Named reviewer in header.

**Signature block (last page):**
- Reviewer name + role + date.
- Partner name + role + date.

**Citation contract:**
- Every auto-populated fact is a hyperlink to the source snapshot cell. Hyperlink target format: `snapshot://<snapshot_id>/<sheet>/<cell_ref>`.

**Refusals:**
- The PDF cannot be generated if the engagement has any **unresolved blocker findings**. Error code: `pdf-blockers-outstanding`. UI banner copy: `"Cannot generate audit memo — N blocker findings unresolved. Resolve or document each before generating."`.
- The PDF cannot be generated without a named reviewer assigned. Error code: `pdf-no-reviewer`. UI banner copy: `"Cannot generate audit memo — no reviewer assigned to this engagement."`.
- The PDF cannot be generated by `analyst` role alone if the engagement status is `signed`. Error code: `pdf-signed-immutable`.

**Persistence contract:**
- Each PDF generation creates an immutable artifact record `pdf_export(id, engagement_id, snapshot_id, generated_by, generated_at, file_hash)`. The PDF file is stored in the engagement's artifact bucket; reads of the artifact are audit-logged.

---

### 3.5 Phase 2 cross-cutting acceptance criteria

The auditor verifies, at end of Month 3, the following exist:

1. **Two real engagements** have been run end-to-end in the tool, with analyst sign-off recorded in the audit log.
2. **All four gaps** (§3.1–§3.4) are closed at pilot-quality.

**Pilot-quality vs production-quality (definitions):**
- **Pilot-quality**: feature works on the two real pilot engagements; documented known limits are acceptable; analyst sign-off says "usable with stated caveats."
- **Production-quality**: feature works on any engagement matching the documented input contract without analyst caveat; load-tested; monitoring + alerting wired; runbook exists.

Phase 2 ships pilot-quality. Phase 3 is the production-quality hardening.

---

## 4. Phase 3 — Hardening (Months 4–6)

### 4.1 Rule-pack versioning

**Schema:**

```
rule_pack
  id: uuid (PK)
  version: str (semver, e.g., "2026.1.0")
  effective_from: date
  effective_to: Optional[date] (null for current head)
  jurisdictions: array<str> (e.g., ["IN", "SG", "US-DE", "ID"])
  standards: array<str> (e.g., ["ifrs13", "asc820", "sec409a"])
  rules_json: text (full ordered list of rules: code, logic, severity, citation, fields_referenced)

engagement_pack_binding
  engagement_id: uuid (FK)
  rule_pack_id: uuid (FK)
  bound_at: timestamp
```

**Binding behavior:**
- At engagement-open, the current "head" rule pack (the one with `effective_to IS NULL`) is bound to the engagement. The binding row is immutable.
- The engagement runs the checklist using the bound pack for its entire lifetime.
- Re-running the checklist on a historical snapshot uses the snapshot's engagement's bound pack.

**Rule add/remove process:**
- Adding or removing any rule creates a NEW rule pack version (semver bump per change category).
- The previous pack's `effective_to` is set to the new pack's `effective_from − 1 day`.
- The new pack becomes head.
- No existing engagement binding changes.

**Refusals:**
- A rule pack with `effective_to` in the past cannot be set as head. Error: `rule-pack-expired`.
- A rule pack cannot mutate after creation. Edits create a new version. Error on UPDATE: `rule-pack-immutable`.

**Coverage requirement:**
- At least 30 rules across the categories listed in §4.1 of the production roadmap: anti-dilution mechanics (6), participation/cap mechanics (4), SAFE/convertible mechanics (6), option pool mechanics (5), voting/governance (5), round mechanics (6), side-letter integrity (5), jurisdiction-specific (~12).
- Each rule carries a `citation` field referencing a published precedent (NVCA, VIMA, AICPA, FEMA, charter section).
- Each rule has at least one fixture and one regression test.

---

### 4.2 Pari-passu seniority

**Data model change:**
- `ShareClass.seniority_rank: int` replaced by `ShareClass.seniority_tier: tuple[int, int]` where `(rank, sub_rank)`.
- `(1, 0)` denotes a standalone rank-1 class.
- `(1, 1)` and `(1, 2)` denote two classes pari-passu within rank 1.
- The model validator `preferred_seniority_unique` is renamed `preferred_tier_unique` and rejects duplicate `(rank, sub_rank)` pairs (not duplicate ranks).

**Backwards compatibility:**
- Existing CapTable JSONs migrate via default mapping: `seniority_rank: N` → `seniority_tier: (N, 0)`.
- The migration is reversible for serialization back to legacy consumers (Phase 0 exports continue to emit `seniority_rank` for downstream readers that haven't been updated).

**Waterfall semantics:**
- Pari-passu classes within a rank share an LP-paying group.
- Within the group, the LP pool is allocated proportionally to each class's `LP_amount` share of the group's total LP.
- The regime walker treats the group as a single LP unit for breakpoint computation; per-class conversion thresholds are computed using the group's combined senior overhang.

**Refusals:**
- Duplicate `(rank, sub_rank)` pairs → `ValueError("duplicate seniority tier (rank, sub_rank): ...")`.

---

### 4.3 OCR for image-PDF side letters

**Pipeline:**
1. `pdfplumber.extract_text` first.
2. If yield < 100 characters or < 5% page-area coverage, fall back to OCR via a vendor-abstracted backend.

**Output contract:**
- `(text: str, confidence: float ∈ [0, 1])`.
- Raw extracted text stored verbatim alongside the snapshot.

**Refusals:**
- If `confidence < 0.85`, the side letter is stored but a UI banner appears with copy: `"OCR confidence below 0.85. Recommend manual review of the original PDF before relying on extracted text."`.
- NEVER any LLM extraction of structured fields from OCR text. The analyst reads it and enters structured SideLetter fields manually.

**Vendor abstraction:**
- OCR backend swappable via config.
- Default backend: Google Document AI (better Indian-script support and table-aware extraction).
- Fallback backend: self-hosted Tesseract + LayoutParser (used when data-residency forbids cloud OCR).

**Persistence contract:**
- OCR result (text + confidence + backend used) persists with the side letter as part of the snapshot.

---

### 4.4 Structured snapshot diff

**Input contract:**
- Two snapshots within the same engagement: `snapshot_a` and `snapshot_b`.

**Output contract:**
- A list of `FieldDiff` with fields:
  - `path: str` — dot/bracket path (e.g., `share_classes[Series B-1].liquidation_preference.cap_multiple`).
  - `old_value`, `new_value` — values before and after.
  - `change_type: enum {added, removed, modified}`.
  - `source_snapshot: uuid` — id of the snapshot the change is attributed to.
  - `rule_implications: list[str]` — codes of rules from the bound pack whose applicability changed (e.g., `["G-CAP-001 no longer applies"]`).

**Audit memo integration:**
- The diff feeds the subsequent-events section of the PDF memo automatically.
- Each diff row hyperlinks to both source-snapshot cells.

**Performance contract:**
- Diff of two 50-class cap tables completes in under 500 ms wall-clock.

---

### 4.5 Wider-team onboarding contract

**Documentation deliverables:**
- A per-role onboarding doc (analyst, reviewer, partner, read-only auditor): one page each.
- A per-jurisdiction quick reference (IN, SG, ID, US-DE, US-CA at minimum): one page each, listing applicable rules and citations.

**Support contract:**
- A known-issues triage list, updated whenever an analyst reports a defect.
- An escalation path: analyst → tool maintainer → engineering lead. Documented.

---

### 4.6 Phase 3 acceptance criteria

By end of Month 6:
1. ≥ 50% of new International Valuations engagements use the tool for intake.
2. Rule-pack count ≥ 30 with fixture + regression coverage per rule.
3. ≥ 1 Big 4 auditor has signed off on a tool-produced PDF memo without substantive pushback.
4. Tool runs on Qapita infrastructure (not the maintainer's laptop).
5. Identity is via Qapita SSO; no shadow user database.
6. Holder-level Excel parses cleanly on ≥ 5 real engagements without manual remapping.

---

## 5. Phase 4 — Platform Play (Months 7–12)

### 5.1 OPM Backsolve sibling

**Input contract:**
- A validated `CapTable` (with no unresolved blocker findings — see refusal below).
- A `MarketInputPack` with fields:
  - `volatility: float ∈ [0, 2]` (annualized).
  - `time_to_liquidity: float > 0` (years).
  - `risk_free_rate: float ∈ [-0.05, 0.20]`.
  - `dlom: float ∈ [0, 0.50]` (analyst-sourced, surfaced not computed).
  - `last_round_price_per_share: float > 0`.
  - `last_round_class: str` (must match an existing preferred class name).

**Output contract:**
- `implied_total_equity_value: float`.
- `per_class_fair_value: dict[class_name → float]`.
- `common_fmv: float` (common per-share fair market value, pre-DLOM and post-DLOM).
- `sensitivity_tables`:
  - Volatility: implied values at `vol ± 10%`.
  - Time: implied values at `time ± 1 year`.
  - Risk-free: implied values at `rf ± 25 bps`.

**Solver contract:**
- `scipy.optimize.brentq` with bounds `[1, 1e12]` (USD or home-currency units).
- Convergence tolerance: `xtol=1e-2`.
- If solver fails to converge: raise `BacksolveNoConvergence`.

**Refusals:**
- Cannot run on a CapTable belonging to an engagement with any unresolved blocker finding. Error: `backsolve-blockers-outstanding`.
- Cannot run if `last_round_class` is not present in the cap table. Error: `backsolve-unknown-anchor-class`.
- Never computes its own volatility or DLOM. Both are required inputs sourced by the analyst.

---

### 5.2 BSM for ESOPs / IFRS 2

**Input contract:**
- A validated `CapTable`.
- An ESOP grant schedule: list of grants, each with `grantee`, `grant_date`, `vesting_schedule`, `strike_price`, `shares`, `expected_term`.
- Market inputs: `volatility`, `risk_free_rate`, `dividend_yield` (default 0).

**Output contract:**
- Per-grant fair value (Black-Scholes-Merton).
- Amortization schedule over the vesting period.
- P&L impact per accounting period.

**Integration contract:**
- Output is consumable by Qapita's existing ESOP product. The cap-table reconciler does NOT duplicate Qapita's ESOP administration features; it computes the IFRS 2 / ASC 718 fair-value layer and hands it off.

---

### 5.3 DCF input sidecar

**Output contract:**
- An Excel sidecar workbook with named ranges:
  - `share_count_total`
  - `share_count_<class>` (one per class)
  - `lp_total`
  - `lp_<class>` (one per preferred class)
  - `conversion_ratio_<class>` (one per preferred class)
  - `valuation_date`
- The DCF model in Excel (built by the analyst) links to the sidecar.

**Refusal:**
- The tool does NOT produce a DCF.
- The tool does NOT compute WACC, terminal value, or projection horizon.
- The tool does NOT source comps.

---

### 5.4 US / ASC 820 expansion

**Coverage requirements:**
- NVCA Model Legal Documents v2 alias coverage in the parser's instrument-type alias map.
- Delaware-specific rules in the rule pack: Section 251 conversion mechanics, dual-class share classes, redemption rights, drag-along scope (at least 6 jurisdiction-tagged rules).
- AICPA Cheap Stock Guide citations in the memo template footnotes.
- California 25102(f) exemption rule.

---

### 5.5 Phase 4 acceptance criteria

By end of Month 12:
1. Three siblings (OPM Backsolve, BSM, DCF sidecar) live and used on real engagements.
2. ≥ 3 US (ASC 820 / 409A) engagements run through the tool.
3. Tool is referenced in at least one Qapita external artifact (Qonversation talk, blog post, sales deck) as house infrastructure.
4. The engine is spun out as a Qapita-internal service consumed by ≥ 2 other product teams (likely ESOP admin and Liquidity).

---

## 6. Cross-cutting invariants (apply at all phases)

1. **No LLM in the calculation pipeline.** Ever. Allowed only in optional editor-side drafting of analyst judgment paragraphs in the memo; never in the data path.
2. **Every finding cites the field/cell it came from.** Phase 0: `fields_referenced` tuple. Phase 2+: hyperlink to snapshot cell.
3. **Refusal beats fabrication.** When input ambiguity exceeds a stated threshold (parse confidence, OCR confidence, holder-rollup confidence), the system returns a structured refusal with a punch list. Never a guess.
4. **Snapshots are immutable from Phase 2 onward.** No `UPDATE` on snapshot rows in any code path.
5. **Audit log is append-only from Phase 2 onward.** No `UPDATE`, no `DELETE` on `audit_event`.
6. **Determinism.** Given the same input CapTable and the same bound rule pack, the system produces the same Findings, the same WaterfallResult (within the documented dedup tolerance), the same Memo body (modulo analyst judgment blocks).
7. **Currency.** Currency is metadata at the Company level. All amounts are floats in the company's home currency. Cross-currency arithmetic is the analyst's responsibility through Phase 4 (no FX engine planned).
8. **Pydantic forbids extra fields.** All models are `extra="forbid"`. Unknown keys raise `ValidationError`.

---

## 7. Out-of-scope refusals (every phase)

The system promises NEVER to do the following, in any phase, in any sibling consumer:

1. **DLOM computation.** Always an analyst input.
2. **PWERM / hybrid OPM-PWERM.** Out of scope.
3. **Fair-value-from-scratch OPM** (allocation OPM beyond Backsolve). Out of scope.
4. **Founder-facing cap-table editor.** Qapita's existing product owns this; the tool will not duplicate it.
5. **Tender administration / secondary market / buyer matching.** Out of scope (Qapita tender product owns this).
6. **Multi-tenant SaaS pricing or public deployment.** The tool is Qapita-internal.
7. **"AI-assisted" anything in the marketing.** The differentiator is deterministic, audit-grade, rule-based.
8. **LLM in the calculation pipeline.** Never.
9. **Volatility peer-set engine.** If built, it is a separate research project, not bolted into the reconciler.
10. **Automatic FX conversion across currencies.**
11. **Multi-tenant access without engagement scoping.** Even partners read only engagements they sponsor.
12. **Bypass of the blocker-finding gate** on engagement sign-off or PDF memo generation. No "force" flag exists.
13. **Edit of historical snapshots, resolutions, or audit events.** All append-only from Phase 2 forward.
14. **Inference of missing cap-table fields.** Missing fields are explicitly marked unknown, never guessed.
15. **Auto-conversion of SAFEs, warrants, convertible notes** into share classes. Always analyst-driven.
16. **Auto-application of full-ratchet anti-dilution.** Always analyst-driven entry of post-trigger shares and conversion ratio.

---

## 8. Spec amendments — round 1 (closes UNV-01..11 and blocker GAP set)

> Appended 2026-05-25 by the spec-custodian role, following the independent
> code-audit and verification-matrix passes. Closes ambiguities surfaced by
> `AUDIT_PLAN.md §5` (UNV-x items) and the blocker tier of `AUDIT_PLAN.md §6`
> (GAP-x items). Code already amended for the items marked "code-fix landed."
> All future amendments are appended below as `## 9.`, `## 10.`, etc., with
> dates, to preserve the diff record.

### 8.1 Closes UNV-001 — fuzz-run report is an artifact, not a claim

Cross-reference to a published `stress_test/AUDIT_REPORT.md` (existing in repo) which records: number of seeds, parameter ranges, invariants checked, pass count, and Singapore-archetype list. The fuzz-run report is regenerated on demand by `stress_test/fuzzer.py` and the count of "23,300+" refers to a specific historical run captured in that report, not a property of the engine.

### 8.2 Closes UNV-002 — live-formula workbook equivalence contract

For any `CapTable` accepted by the engine, calling `build_formula_workbook(cap_table)` and reading the breakpoint cells from the resulting workbook produces values equal to `compute_waterfall(cap_table).breakpoints[i].value` within absolute tolerance `1e-6` (or relative tolerance `1e-6 * max_breakpoint_value`, whichever is larger). This is the dedup tolerance from `waterfall._dedupe_close_values`. The Python truth is canonical; the workbook is a derivative.

### 8.3 Closes UNV-003 — reference environment for performance contracts

All performance SLOs in this spec (e.g., Phase 2 §3.1 "Qapita cold-start pull < 5s", Phase 3 §4.4 "diff < 500ms") are measured on the **reference environment**:

- CPU: 4 vCPU x86_64 baseline (e.g., AWS c6i.xlarge or equivalent), no spectre mitigations relaxed.
- Memory: 8 GiB available RSS to the process.
- Network: ≤ 20ms RTT to Qapita data source, ≤ 5ms to local SQLite/Postgres.
- Disk: SSD-class, ≥ 100 MB/s sequential write.
- Python: 3.11 or 3.12 on Linux glibc.
- Cold cache: process started fresh; no warm pages.

Local-laptop measurements are advisory, not contractual. The spec measurement environment is captured per phase in the audit deliverable PDF (per `AUDIT_PLAN.md §7.2` appendix C).

### 8.4 Closes UNV-004 — PDF citation URI scheme

The PDF memo's cell citations use the URI scheme `engagement://<engagement_id>/snapshots/<snapshot_id>#<sheet>!<cell_ref>` (HTTP-resolvable through the Qapita engagement viewer once Phase 2 deploys). For local-only Phase 0 memos, the URI is `local://snapshots/<snapshot_id>#<sheet>!<cell_ref>` and is informational only (no resolver). The scheme name `local://` does not collide with any registered IANA scheme.

### 8.5 Closes UNV-005 — OCR confidence normalization

OCR backend confidence is mapped to a normalized scale `[0.0, 1.0]` where:
- `1.0` is "the backend is certain at the per-token level"
- `0.0` is "the backend rejected the page"
- The mapping is documented per backend in `ingestion/ocr/<backend>.py`:
  - Google Document AI: page-mean of token-level `confidence` field, unchanged.
  - Tesseract: `conf` column of TSV output, divided by 100, clamped to `[0, 1]`, page-mean.
  - Manual upload: implicit `1.0` (analyst attested).
- The `0.85` threshold for the "low-confidence" banner refers to this normalized scale.

### 8.6 Closes UNV-006 — "runs on Qapita infrastructure" verifier list

For the Phase 3 acceptance criterion to count as met, four artifacts must exist and be linked in the audit deliverable PDF:
1. A deployment URL behind Qapita SSO (any environment: staging, prod, internal).
2. A monitoring dashboard URL (Grafana, Datadog, or equivalent) showing the service's uptime over the trailing 7 days.
3. An infra-as-code repository path (Terraform module, Pulumi project, or Helm chart) defining the service.
4. A backup configuration document naming RPO ≤ 1 hour and RTO ≤ 4 hours (see §8.10 below).

### 8.7 Closes UNV-007 — OPM Backsolve reference computation appendix

The Phase 4 spec will include `appendix/opm_backsolve_reference.md`, containing one fully worked example with all inputs (cap table, vol, time, rf, DLOM, dividend yield) and the expected outputs (implied total equity value, per-class fair value, per-share common FMV, sensitivity tables). Reference source: AICPA Cheap Stock Guide Ch.6 worked example, cited explicitly. The reference is a snapshot; the engine is required to reproduce its output bit-for-bit. Updates to the AICPA example update the reference (new reference appendix version), not the engine.

### 8.8 Closes UNV-008 + GAP-33 — `token-expired` error code

The read-only auditor magic-link role uses the following error codes in `WWW-Authenticate` headers and JSON error bodies:
- `token-expired` — token TTL exceeded (returned with HTTP 401).
- `token-revoked` — token explicitly revoked pre-expiry by partner action (HTTP 401). See GAP-39 (§8.16 below).
- `read-only-token` — token is valid but the requested operation requires write scope (HTTP 403).

### 8.9 Closes UNV-009 — "external artifact" verifier source

The Phase 4 acceptance criterion "tool referenced in at least one Qapita external artifact" is verified by linking, in the audit deliverable, a Qapita marketing publication log entry (the company's internal record of published blog posts, talks, sales decks) showing the tool's name or function referenced by a Qapita employee in a public artifact. External evidence: the URL of the artifact and its publication date.

### 8.10 Closes UNV-010 + GAP-35 — determinism with timestamps

The cross-cutting determinism invariant (§6.6) is qualified as follows:

| Output type | Determinism guarantee |
|---|---|
| `CapTable` Pydantic model serialized JSON | Bit-for-bit, ignoring key ordering (which is deterministic in Pydantic v2 anyway). |
| `WaterfallResult` | Bit-for-bit on every numeric and structural field. |
| `Finding` list | Bit-for-bit on `code`, `severity`, `category`, `summary`, `detail`, `fields_referenced`. |
| Static `.xlsx` export | Bit-for-bit on cell values; openpyxl may write differing low-level XML zip metadata (timestamps, redundant style entries). The deterministic claim covers the cell-value-and-format payload, NOT the zipfile bytes. |
| Live-formula `.xlsx` export | Same: cell-value-and-formula determinism; zip metadata not guaranteed. |
| Markdown audit memo | Bit-for-bit EXCEPT for the leading `*Generated by ... at <UTC timestamp>*` line. Memos are deterministic modulo this single timestamp line. |
| PDF audit memo (Phase 2+) | Bit-for-bit EXCEPT for the cover-sheet timestamp and any PDF-internal `/CreationDate` / `/ModDate` metadata. |
| Snapshot `created_at` | Determined at snapshot creation; not re-determined on re-read. |

Auditor verification of determinism uses content-level comparison (parse the artifact and compare the payload), not byte-level `diff`, for any output above whose row says "not bit-for-bit on metadata."

### 8.11 Closes UNV-011 — openpyxl exception abstraction

Spec §1.1 is amended: "If the uploaded file is not a valid `.xlsx` archive (cannot be opened by openpyxl as a workbook), the upload route returns HTTP 400 with the error banner `Could not parse file: <message>`. The specific upstream exception class is implementation-detail; the contract is the HTTP code and the banner format."

The current implementation catches `openpyxl.utils.exceptions.InvalidFileException` and `zipfile.BadZipFile` explicitly; if openpyxl renames or refactors these, the implementation must continue to honour the HTTP-400 contract.

### 8.12 Closes GAP-01 — concurrency on engagement edits

Phase 2 engagement edits use **optimistic concurrency control**:
- Every snapshot row carries a monotonic `version: int` (server-assigned at insert).
- Every mutating route accepts an `If-Match: <version>` header (HTTP) or `expected_version: int` field (programmatic).
- If the server's current head version for the engagement does not match, the route returns HTTP 409 with code `engagement-version-conflict` and a body containing the current head version + a diff summary, so the client can refresh and retry.
- The audit log records both the attempted action (with the stale version) and the conflict, so a malicious or buggy client cannot mask the conflict.

### 8.13 Closes GAP-03 — PDPA / GDPR / DPDPA right-of-erasure vs immutable audit log

The tool stores cap-table data including PII (holder names, shareholder addresses if supplied). For data-subject erasure requests under PDPA (Singapore), GDPR (EU), or DPDPA (India):

1. **Erasure does not delete audit-log rows.** Rows remain, providing tamper evidence.
2. **Erasure REDACTS the PII payload in place**, replacing it with the sentinel `{"_redacted": true, "redaction_event_id": "<uuid>", "redacted_at": "<iso>"}`. The redaction itself is logged as an `audit_event` of type `pii_redacted` with the actor (legal/compliance role), the request reference, and the legal basis.
3. **Snapshots referencing redacted PII** are not deleted; their JSON contains the same `_redacted` sentinel in the affected fields. The waterfall, findings, and breakpoints (which do not contain PII) remain unchanged.
4. **The redaction is a one-way operation.** Once redacted, the original PII cannot be recovered from this system.
5. **Cryptographic shredding** is an acceptable alternative for snapshots stored encrypted at rest (delete the per-snapshot key; ciphertext becomes unrecoverable). This is documented as an option for jurisdictions that require erasure beyond redaction.

### 8.14 Closes GAP-05 — audit-log tamper evidence

The `audit_event` table includes a `row_hash: TEXT NOT NULL` column computed as `SHA-256(prev_row_hash || canonical_serialized_payload)` where `prev_row_hash` is the row_hash of the immediately prior `audit_event` for the same engagement (or `"00"*32` for the first event). This forms a per-engagement hash chain that any auditor can recompute and compare.

- The current hash-chain head per engagement is published in the `engagement` row as `audit_head_hash`.
- An auditor verifies integrity by walking the chain from head to genesis, recomputing each `row_hash`, and comparing.
- If a DB admin tampers with a single row, every downstream row's hash mismatches; the audit deliverable surfaces the break point.

### 8.15 Closes GAP-07 — rule-pack vs engine-code version skew

Every `engagement_pack_binding` row carries an additional column `engine_version: TEXT NOT NULL`, populated at bind time with the git short-SHA of the engine code at the moment of binding. Re-runs:

- **Exact re-run:** the engine code at the bound `engine_version` is checked out (via a versioned engine artifact registry) and used. Output is bit-for-bit (subject to §8.10 carve-outs).
- **Approximate re-run:** if the bound `engine_version` is unavailable (rare; engine artifacts retained for 7+ years), the latest engine code may be used WITH a banner `engine-version-skew` recording the original and current versions. The audit deliverable flags this explicitly.
- Engine artifacts (built wheels) are retained for 7 years matching audit retention.

### 8.16 Closes GAP-36 — XSS / injection in cell content

Holder names, class names, company names, and side-letter text may contain any UTF-8. The tool's escaping promise:

1. **Jinja2 autoescape is on for all HTML templates** (Flask default). Untrusted strings rendered in templates are HTML-escaped.
2. **Markdown audit memo escapes pipe characters and newlines** in all dynamic cell content via `src.audit_memo._md()` (added in the audit-fix round). Verified by `tests/test_audit_fixes.py::test_bug004_audit_memo_escapes_pipe_characters`.
3. **PDF audit memo (Phase 2+)** uses WeasyPrint with autoescape; same escaping discipline as HTML.
4. **JSON exports** are produced via `json.dumps`; quote and backslash escaping is automatic.
5. **Excel exports** treat all dynamic strings as values, not formulas; a class named `=SUM(A1:A10)` is written as the literal string, not a formula. Verified by an explicit Phase 2 audit test.
6. **No string interpolation into raw HTML, SQL, or shell** anywhere in the codebase. Audited by the structural reviewer on every PR touching app.py or src/.

### 8.17 Closes GAP-40 — bulk-export rate limiting

Phase 2 onwards, every export route (`/export/<token>.json`, `.xlsx`, `.zip`, `/memo`) is rate-limited per user:

- Soft limit: 30 exports per hour per user. Above this, exports return HTTP 429 with code `export-rate-limit` and a `Retry-After` header.
- Hard alert: 100 exports per hour per user triggers an `audit_event` of type `bulk_export_alert` and an internal notification to the Risk role.
- The rate limit applies per user, not per IP, and uses the user ID from SSO.

Phase 0 (no auth) is exempt from rate limits because there are no users to attribute to.

---

This concludes spec amendment round 1. Audits running against this spec MUST use the spec version tagged `spec-r1-2026-05-25` in git, not the HEAD version. The spec-custodian commits this amendment as a single commit with the tag attached.

---

## 9. Spec amendments — round 2 (post compiled-system audit)

> Appended after the cross-cutting system audit closed three blockers
> and seven majors. This round covers spec drift that the audit
> identified between the engine's lifecycle table and §3.2's allowed
> transitions, plus a closure for the engagement-bound pack contract.

### 9.1 Lifecycle: partner reopen + partner archive (closes audit M-4)

The §3.2 lifecycle is amended to add two operational transitions the
implementation already supports and the practice has confirmed it needs:

| From | To | Allowed actors | Notes |
|---|---|---|---|
| `signed` | `review` | `partner` only | Subsequent-events reopen per `GAP-29`. Logged as audit_event `transition` with the prior signed-by actor + reopen reason in payload. |
| `open` | `archived` | `partner` only | Cancel before any review (e.g., client withdrew). |
| `signed` | `archived` | `partner` OR system cron | Archive after sign-off retention period elapses. |

`archived` remains terminal; no transitions leave it.

### 9.2 Engagement-bound pack contract (closes audit B-1)

The engagement-bound pack version is sticky for the engagement's
lifetime. Every memo, every checklist re-run, every subsequent-events
diff for an engagement MUST resolve the rule pack via the engagement's
`pack_version` field, NOT the global `head_pack()`. The implementation
helper for this is `src.rule_pack.load_engagement_bound_pack(version)`.

A bound pack that no longer exists on disk (e.g., file pruned in error)
causes every dependent route to raise `engagement-blockers-unresolved`
or `pdf-error` — the engagement is unusable until the pack file is
restored. This is the correct failure mode: silently substituting
`head_pack()` is forbidden.

### 9.3 Sign-off gate (closes audit B-3)

`review → signed` is explicitly refused with HTTP 409
`engagement-blockers-unresolved` when the head snapshot has any
unresolved blocker finding under the engagement's bound pack. The
implementation in `EngagementStore._enforce_blockers_resolved` is the
single authority for this check. No `?force=1` flag exists or will
ever exist.

### 9.4 Rule-pack effective-window closure (closes audit M-2)

When a new rule-pack is shipped, the prior pack's `effective_to` is set
to the new pack's `effective_from - 1 day` BEFORE the new pack is
published. The `list_available_packs()` loader is expected to refuse
overlapping windows in a future hardening; until then, the closure is a
data-only contract on the JSON files. Current closures:

- `v2026.1.0` effective 2026-01-01 → 2026-05-31
- `v2026.2.0` effective 2026-06-01 → 2026-08-31
- `v2026.3.0` effective 2026-09-01 → 2026-11-30
- `v2026.4.0` effective 2026-12-01 → null (head)

### 9.5 v0.0.0-dev pack refusal (closes audit M-7)

`load_engagement_bound_pack("v0.0.0-dev")` raises `ValueError` unless
the process env carries `QAPITA_ALLOW_DEV_PACK=1`. Production
deployments must NEVER set this flag. Pre-deployment checks SHOULD
grep `QAPITA_ALLOW_DEV_PACK=1` from every infrastructure manifest and
fail the deploy if present.

### 9.6 Spec error-code inventory (closes audit M-3)

Single canonical list of every error_code the implementation returns,
in the implementation's vocabulary:

| Code | HTTP | Where |
|---|---|---|
| `auth-required` | 401 | engagement_routes auth guard |
| `permission-denied` | 403 | engagement.py PermissionDenied + every route's `can()` check |
| `engagement-not-found` | 404 | engagement.py EngagementNotFound |
| `engagement-invalid-transition` | 409 | engagement.py IllegalStateTransition (M-3 renamed) |
| `engagement-version-conflict` | 409 | engagement.py EngagementVersionConflict (§8.12) |
| `engagement-blockers-unresolved` | 409 | engagement.py BlockerFindingsOutstanding (B-3 new) |
| `pdf-blockers-outstanding` | 409 | pdf_memo.py PDFBlockersOutstanding (§3.4) |
| `pdf-no-reviewer` | 400 | pdf_memo.py PDFNoReviewer (§3.4) |
| `pdf-error` | 400 | pdf_memo.py base PDFMemoError |
| `export-rate-limit` | 429 | rate_limit + engagement_routes _enforce_export_limit (§8.17) |
| `parse-failed` | 400 | engagement_routes upload route |
| `no-file` | 400 | engagement_routes upload route |
| `unsupported-file-type` | 400 | engagement_routes upload route |
| `no-snapshot` | 400 | engagement_routes memo route |
| `snapshot-redacted` | 410 | engagement_routes memo route after PDPA redaction |
| `client-id-required-for-role` | 400 | engagement_routes list_engagements (W3-AUDIT M1) |
| `client-id-required` | 400 | engagement_routes create |
| `missing-resolution-fields` | 400 | engagement_routes resolve |
| `missing-status` / `missing-expected-version` / `unknown-status` | 400 | engagement_routes transition |
| `missing-redaction-fields` | 400 | engagement_routes redact |
| `bad-pagination` | 400 | engagement_routes list_engagements |
| `immutable-violation` | 500 | engagement.py ImmutableViolation (defensive; not raised today) |
| `validation-failed` | 400 | engagement_routes generic pydantic ValidationError catch |
| `engagement-error` | 400 | engagement.py base class |
| `compute-rate-limit` | 429 | engagement_routes whatif compute limiter (W5.5) |
| `csrf-missing-cookie` | 403 | engagement_routes _auth_guard CSRF check (W6.1) |
| `csrf-mismatch` | 403 | engagement_routes _auth_guard CSRF check (W6.1) |
| `diff-needs-two-snapshots` | 400 | engagement_routes /diff + /diff.xlsx (W7.2) |
| `snapshot-engagement-mismatch` | 400 | engagement_routes /diff cross-engagement guard (W7.2) |
| `diff-too-many-snapshots` | 400 | engagement_routes /diff* cap of 20 snapshots (SD-AUD-W7-M2) |
| `change-note-illegal-character` | 400 | engagement_routes upload (SD-AUD-W7-B2) |
| `change-note-too-long` | 400 | engagement_routes upload (32767-char cap) |
| `snapshot-not-found` | 404 | SnapshotNotFound subclass (SD-AUD-W7-m6) |
| `phase-0-demo-disabled` | 404 | app.py phase-0 gate (W8.2) |
| `opm-bad-inputs` | 400 | engagement_routes /opm route (W9.2) |
| `bad-pagination` | 400 | engagement_routes /snapshots pagination guard (W9.7) |

Codes from spec §3.2 not yet implemented (deferred to future per-role
ACL work, GAP-39): `tenancy-violation`, `role-not-permitted`,
`read-only-token`, `token-expired`, `pdf-signed-immutable`. `token-revoked`
is now implemented in W6.4 — a revoked Bearer falls through to the same
`auth-required` 401 the missing-Bearer path produces; revocation is
recorded server-side in the deny list (`data/token_deny.db`).

### 9.7 valuation_date typing (defers audit M-6)

The engagement schema `valuation_date: Optional[str]` (ISO date string)
remains string-typed for now to avoid a DB-serialisation migration. A
future amendment will tighten to `date | None` and validate at the API
boundary; until then, route handlers SHOULD validate format with
`date.fromisoformat()` if filtering by date. This is intentionally
incomplete and tracked.

This concludes spec amendment round 2. Re-tag as `spec-r2-2026-05-25`.

---

## 10. Spec amendments — round 3 (post wave-4 compiled audit)

> Appended after the wave-4 compiled audit closed 2 blockers and 5
> majors. This round covers the four spec drifts the audit surfaced
> (SD-1 DCF template vs §5.3 refusal, SD-2 /whatif URL, SD-3
> bound_pack_json undocumented, SD-4 HTMX auth) plus the rule-pack
> chronology renumbering.

### 10.1 DCF template clarification (closes audit SD-1)

§5.3 ("Out-of-scope refusals") is amended: the system does NOT produce
a DCF MODEL. It DOES produce a **DCF input template** — an Excel
scaffold with yellow analyst-input cells, deterministic formulas, and
references to the companion DCF sidecar's named ranges. Every
judgment number (WACC, terminal growth, revenue projections, margins)
is a yellow cell the analyst fills and defends. The tool fills no
judgment numbers. This is the same posture as the volatility input
pack (§5.1 vol_pack).

The distinction:
- **DCF model** = a complete valuation produced by the tool, output
  is a fair-value number. **Refused** per §5.3.
- **DCF input template** = a scaffolded workbook the analyst fills,
  output is structure + formulas. **In scope.**

`src/dcf_template.py::build_dcf_template` produces the latter. The
"Read Me" sheet inside the template makes the distinction explicit
to the analyst.

### 10.2 /whatif URL (closes audit SD-2)

The canonical route is `POST /engagement/<engagement_id>/whatif`,
returning the `engagement/_whatif.html` partial when content-negotiation
selects HTML. Spec §3.x is corrected — the prior `/whatif/<token>`
reference was an artefact of the Phase-0 SessionStore design and is
removed.

### 10.3 `bound_pack_json` engagement column (closes audit SD-3)

The Engagement model carries `bound_pack_json: Optional[str]` — the
full JSON bytes of the rule pack the engagement was bound to at
create time. Wave-4 wave-2-audit-M4 closure. The bundle exporter
prefers these pinned bytes over disk lookup; the memo route does the
same after the wave-4-audit B-2 fix. Legacy engagements created
before the migration carry `bound_pack_json=None` and fall back to
disk-resolved pack.

Schema column: `bound_pack_json TEXT` (idempotent ALTER TABLE on
store init; tolerant of `duplicate column name` errors per wave-4
audit m-3 fix).

### 10.4 HTMX UI authentication contract (closes audit SD-4)

The HTMX UI (`templates/engagement/*.html`) is currently usable in
two modes:

1. **Test mode** (`app.config["TESTING"] = True`): `?token=<value>`
   query param is honored for auth. Used by `test_engagement_html.py`
   and friends.
2. **Production mode** (no `TESTING`): only `Authorization: Bearer
   <token>` HTTP header and `X-Auth-Token` header are honored.
   Browser links cannot attach `Authorization` headers natively, so
   the production HTMX UI requires a session-cookie auth layer —
   currently **stubbed for Evelyn** (per BUILD_WAVE_4.md §5). Until
   the SSO + session-cookie bridge ships, the HTMX UI is dev-only;
   API JSON callers continue to work via Bearer header.

The route surface itself is production-ready; only the browser-cookie
plumbing is pending Evelyn's session/SSO confirmation.

### 10.5 Rule-pack chronology renumbering (release-config fix)

Per the wave-4 audit's release-config finding, the rule packs are
renumbered to a non-overlapping monthly chronology ending at the
current head:

- `v2026.1.0` effective 2026-01-01 → 2026-01-31
- `v2026.2.0` effective 2026-02-01 → 2026-02-28
- `v2026.3.0` effective 2026-03-01 → 2026-03-31
- `v2026.4.0` effective 2026-04-01 → 2026-05-24
- `v2026.5.0` effective 2026-05-25 → 2026-05-25 (single-day window)
- `v2026.6.0` effective 2026-05-26 → null (head, 60 rules — wave-5)

The prior dates carried mixed-quarter windows that meant packs v2-v5
did not fire on engagements created in their notional release months.
The renumbering makes the head pack effective on engagement creation
today; all 60 rules fire on new engagements as of 2026-05-26.

The v2026.5.0 1-day window is intentional: it captured the wave-4
50-rule head pack for the calendar day before the wave-5 expansion
to 60 rules. Engagements created on 2026-05-25 bind to v2026.5.0;
engagements created on 2026-05-26 or later bind to v2026.6.0. Audit
log + bound_pack_json record the exact pack each engagement was bound
to; reproducibility holds independent of the chronology.

### 10.6 Rule determinism — anchor on cap-table dates, not wall-clock (closes audit M-2)

Cross-cutting rule-authoring constraint: rules MUST NOT call
`date.today()` or any wall-clock function. Date-sensitive rules
anchor against `cap_table.company.valuation_date` or, where
appropriate, the most-recent priced round's `issue_date`. This
preserves the §6.6 determinism invariant — same cap table → same
findings, regardless of when the rule runs.

Wave-4 rules `_rule_future_valuation` (G-AUDIT-002) and
`_rule_warrant_expired` (G-WAR-002) initially violated this and were
fixed in the wave-4 audit batch.

### 10.7 Error response content-negotiation (closes audit M-3)

The `_engagement_errors` decorator MUST respect content-negotiation
on 4xx/5xx responses. When `_wants_html()` returns True (HTMX form
submission, browser request), errors render
`engagement/base.html` with an error banner. When False (JSON API
client), errors return the existing `{error, error_code, ...}` JSON
body. The HTTP status code is identical in both branches.

This concludes spec amendment round 3. Re-tag as `spec-r3-2026-05-25`.

---

## 11. Spec amendments — round 4 (wave-6 hardening)

> Appended after wave 6 closed the deferred wave-5 audit items: CSRF,
> startup collision guard, Bearer revocation, cross-wave integration
> test harness, and the prod-checklist documentation.

### 11.1 CSRF on cookie-authenticated POSTs (closes wave-5 M-6)

Cookie-authenticated mutating routes MUST verify a double-submit CSRF
token before dispatch:

- Server issues `qapita_csrf` cookie (32-byte URL-safe random,
  `SameSite=Strict`, NOT HttpOnly so JS can read it) when `qapita_session`
  is issued at `/login`.
- Every mutating route in the engagement blueprint checks the request
  carries `X-CSRF-Token: <value>` header OR `csrf_token=<value>` form
  field matching the cookie. Mismatch returns 403 `csrf-mismatch`;
  missing cookie returns 403 `csrf-missing-cookie`.
- Bearer-authenticated requests are exempt: the bearer header IS the
  explicit credential, not an ambient session — matches the SD-AUD-B5
  precedence model. The auth guard threads `g.auth_source = "bearer" |
  "cookie"` and gates CSRF on the cookie source only.
- HTMX forms in `templates/engagement/*` render the hidden input AND set
  `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'` so the server
  receives the token via either path.
- `POST /logout` clears both `qapita_session` and `qapita_csrf` cookies.

### 11.2 Bearer revocation via deny list (closes SD-AUD-B5 second-half)

`POST /logout` with an `Authorization: Bearer <tok>` header (or
`X-Auth-Token: <tok>`) MUST revoke the supplied token server-side. A
revoked Bearer authenticates as nobody on subsequent requests; the
request falls through to the cookie path or returns 401.

- Storage: `TokenDenyList` (SQLite, hash-only — SHA-256(token), never
  the raw value).
- The `_require_user` auth guard consults the deny list before identity
  resolution. Denied tokens are dropped silently — the request proceeds
  with no Bearer attempt, so cookie-only auth still works.
- Operators MUST run `TokenDenyList.prune_older_than(...)` periodically
  using the SSO provider's max token lifetime as the cutoff; without
  pruning the table grows monotonically (correctness unaffected, disk
  usage degrades).
- `/logout` semantics: clears the cookie always; revokes the Bearer
  when one was supplied; replies 302 to the safe-next URL (`/login`
  default).

### 11.3 Startup finding-code collision guard

App boot MUST call `assert_no_collisions_at_startup(strict=True)` after
all rule modules import. The function runs every registered rule against
a programmatic representative cap table (common + ESOP pool + 2
preferred classes with mixed LP variants and AD) and raises
`RuntimeError` if any two rules emit the same `Finding.code`. Production
mode (non-TESTING) refuses to boot; TESTING mode soft-fails to log so
the test app can override the probe table.

This subsumes wave-5 audit M-10 ("collision check is CI-only").

### 11.4 Cross-wave integration test surface

The unit test suite is wave-scoped — wave-5 audit B-1..B-6 all shipped
green under unit tests because they lived at wave seams. Each
production-bound release MUST therefore include the
`tests/test_wave6_integration.py` harness or equivalent: a coverage
matrix that drives one engagement through every wave's surface
end-to-end (login → upload → resolve → transition → memo → bundle →
whatif) using both the cookie path (browser) and the Bearer path
(API client).

This concludes spec amendment round 4. Re-tag as `spec-r4-2026-05-26`.

---

## 12. Spec amendments — round 5 (wave-7 snapshot-diff surface)

> Appended after wave 7 added the chronological snapshot timeline, N-way
> diff endpoint, per-snapshot change-note annotation, and the xlsx
> workpaper export. The wave-7 analyst flow is "select 2+ snapshots
> from a timeline → see them side-by-side → export as a workpaper."

### 12.1 Snapshot.change_note (optional, analyst-supplied)

`Snapshot` gains an optional `change_note: Optional[str]` field. Set at
upload time via the form field `change_note=...` (empty/whitespace ↦ None).
Surfaces in the snapshot timeline and the N-way diff header. Schema
migration is idempotent (`ALTER TABLE snapshot ADD COLUMN change_note
TEXT` runs once on store init; "duplicate column name" is swallowed).
Legacy snapshots without the column read as `change_note=None`.

### 12.2 New routes

| Route | Auth | Description |
|---|---|---|
| `GET /engagement/<id>/snapshots` | `engagement.read` | Chronological listing of every snapshot. HTML view renders the compare checkbox form; JSON returns id + created_at + change_note + is_head per snapshot. |
| `GET /engagement/<id>/diff` | `engagement.read` | N-way diff across `?snap=` query params (repeated). Requires ≥2 snapshot ids; refuses cross-engagement snapshot ids with `snapshot-engagement-mismatch` 400. |
| `GET /engagement/<id>/diff.xlsx` | `export.xlsx` | Same N-way diff as a 3-tab xlsx workpaper (Summary / Class Drift / Snapshots). Consumes the export rate limit. Writes an `AuditEventType.snapshot_diff_exported` event to the engagement audit chain. |

### 12.3 Magnitude tiers

Per-field drift across consecutive snapshots is classified into one of:

| Tier | Trigger |
|---|---|
| `none` | identical across all snapshots |
| `minor` | numeric value moves within ±5% |
| `material` | numeric value moves 5%–20% |
| `major` | numeric value moves >20%, OR presence change (added/removed), OR any categorical field changes (LP variant, AD variant, seniority rank) |

Class-level overall tier is `max(field tiers)`. UI + xlsx render the
tier as a colour-coded cell (slate/blue/amber/red).

### 12.4 New error codes

| Code | HTTP | Where |
|---|---|---|
| `diff-needs-two-snapshots` | 400 | `/diff` + `/diff.xlsx` with `<2` snap params |
| `snapshot-engagement-mismatch` | 400 | snap id that belongs to a different engagement |

### 12.5 New audit event

| Event type | Payload |
|---|---|
| `snapshot_diff_exported` | `{snapshot_ids: [...], format: "xlsx", class_count: N}` |

The event is appended via the existing hash chain — the bundle picks it
up automatically, so a Big-4 reviewer pulling the bundle six months later
sees every workpaper export with chain-of-custody.

### 12.6 Workpaper byte stability

The xlsx workpaper has no determinism contract today (it's analyst-facing,
not auditor-facing). If a future wave promotes it to the bundle, apply
the same `ZipInfo(date_time=epoch)` treatment that the bundle uses
(SD-AUD-B2 fix).

This concludes spec amendment round 5. Re-tag as `spec-r5-2026-05-26`.

---

## 13. Spec amendments — round 6 (wave-8 prod-readiness sweep)

> Appended after wave 8 closed every deferred item the prior audits had
> flagged that didn't require Evelyn's input: hardened the demo surface,
> wired OCI engine versioning, made xlsx producers byte-stable, added
> /readyz + ops CLI, archival + restore mechanism, and folded the
> snapshot drift into the PDF memo.

### 13.1 Demo-surface gates

`StubSSOProvider.__init__` raises in non-TESTING unless `ALLOW_STUB_SSO=1`
is set in the environment or `allow_in_prod=True` is passed at
construction. The phase-0 demo routes (`/upload`, `/review/`,
`/waterfall/`, `/whatif/`, `/resolve/`, `/export/`, `/compare/`,
`/sessions`, `/upload_side_letter/`, `/demo/`, `/diff`) refuse to serve
with HTTP 404 `phase-0-demo-disabled` unless `ALLOW_PHASE_0_DEMO=1`
is set or Flask `TESTING` is on. Both gates are evaluated per-request
so test fixtures that flip `TESTING=True` after import are honoured.

### 13.2 Engine version via build-arg

`current_engine_commit()` consults `QAPITA_ENGINE_COMMIT` env var
before falling back to `git rev-parse`. OCI images that bake the SHA
in at build time no longer record `"unversioned"` against every
engagement they create. Result cached at module level so per-engagement
creation doesn't fork+exec.

### 13.3 xlsx byte stability

Both `diff_workpaper.build_diff_workpaper_xlsx` and
`formula_workbook.FormulaWorkbookBuilder` pin `wb.properties.created`,
`modified`, `creator`, `lastModifiedBy` at build time. `diff_workpaper`
additionally post-processes the zip envelope to rewrite every
ZipInfo entry's `date_time` to the DOS epoch and scrubs
`dcterms:modified` in `docProps/core.xml` (openpyxl overrides our
pinned value at save() time). Result: two builds of the same diff
produce identical bytes.

### 13.4 Snapshot redaction extends to `created_by`

`Snapshot.safe_created_by()` returns the literal `"[redacted]"` when
`snap.redacted` is True. Wired into the timeline JSON, the diff
`SnapshotMeta` construction (both /diff and /diff.xlsx and /diff.pdf
and the auto-embedded memo drift section), and the bundle exporter's
`model_copy(update={"created_by": "[redacted]"})`. Closes wave-7
m-W7-4.

### 13.5 /logout preserves CSRF cookie

`/logout` zeroes `qapita_session` but leaves `qapita_csrf` in place so
a second tab's next form POST does not 403 with `csrf-missing-cookie`.
The CSRF cookie has no security value once the session is gone (the
verify_csrf check only runs when `g.auth_source == "cookie"`); the
engagement blueprint's auto-heal hook re-mints it on the next
authenticated GET if it ever expires. Closes wave-6 m-W7-9.

### 13.6 /readyz endpoint

`GET /readyz` returns `{status, engine_commit,
rule_pack_head_version, deny_list_size, engagements_total,
audit_log_total, last_engagement_created_at}`. Liveness `GET /healthz`
remains the minimal `{"status":"ok"}` shape (probes fire often;
readyz hits the DB).

### 13.7 Ops CLI

| Command | Purpose |
|---|---|
| `flask --app app prune-deny-list` | Drop expired Bearer-revocation entries |
| `flask --app app prune-rate-limits` | Drop rate-limit bucket rows > 7 days old |
| `flask --app app hard-delete-archived` | Cascade-delete archived engagements past the restore window |

Operators schedule via systemd-timer / k8s CronJob. None run
automatically; absence is correctness-safe but disk usage degrades.

### 13.8 Engagement archival + restore

`Engagement` gains `archived_at: Optional[datetime]` and
`restore_eligibility_until: Optional[datetime]` columns (idempotent
ALTER migration). When `transition()` lands on `archived`, both are
stamped atomically with `archived_at = now`,
`restore_eligibility_until = now + ARCHIVAL_RESTORE_DAYS (90)`. Any
transition AWAY from archived clears both.

Allowed transitions now include `archived → open`, gated on the new
`engagement.restore_archived` permission (partner-only) AND the
restore window. `transition()` raises `IllegalStateTransition` if
called outside the window. New route `POST /engagement/<id>/restore`
wraps the transition for analyst UX.

`EngagementStore.hard_delete_expired_archived()` cascades to
snapshots + resolutions for engagements past the restore window;
audit_event rows are KEPT (legal-erasure preservation contract is
Evelyn-blocked; current implementation chooses preservation). Invoked
via the `flask hard-delete-archived` CLI.

§3.2 amendment: `archived` is NOT terminal in the strict sense — it
allows controlled restore within the window. The audit chain records
both archival and restore events so the lifecycle is observable.

### 13.9 PDF audit memo includes snapshot drift

`PDFInputs.timeline_diff: Optional[TimelineDiff]`. When supplied, the
memo renders a "Snapshot drift" section with the magnitude-tiered
per-class table. The engagement memo route auto-computes the drift
across the engagement's snapshot chain (skipped when fewer than 2
snapshots exist). Stand-alone PDF workpaper at
`GET /engagement/<id>/diff.pdf` (mirrors /diff.xlsx; permission
`export.memo_pdf`; writes the same `snapshot_diff_exported` audit
event with `payload.format = "pdf"`).

### 13.10 New error codes

| Code | HTTP | Where |
|---|---|---|
| `phase-0-demo-disabled` | 404 | app.py phase-0 gate when `ALLOW_PHASE_0_DEMO` unset |

This concludes spec amendment round 6. Re-tag as `spec-r6-2026-05-29`.

---

## 14. Spec amendments — round 7 (wave-9 feature + polish)

> Wave 9 closes deferred audit minors and ships three analyst-facing
> capabilities that didn't need Evelyn's input: rule provenance in the
> PDF memo, engagement-bound OPM Backsolve, and vol-pack → DCF sidecar
> suggestion plumbing.

### 14.1 Rule provenance in the PDF memo (W9.1)

`rule_pack.finding_provenance_map(cap_table, pack=None)` returns
`{finding.code: {"rule_id", "citation", "pack_version"}}` by replaying
the pack against the cap table and recording which rule emitted each
code. The PDF memo's findings table gains a "Rule provenance" column
showing `rule_id (pack_version)` + the rule's citation. Big-4 reviewers
reading the memo no longer have to cross-reference rule_packs/*.json
to find the legal basis for each finding.

### 14.2 Engagement-bound OPM Backsolve (W9.2)

New route `POST /engagement/<id>/opm`. Permission `engagement.read`.
Body (JSON or form):

```
volatility, time_to_liquidity_years, risk_free_rate,
dividend_yield (opt), dlom (opt),
anchor_class_name, anchor_price_per_share,
anchor_raise_amount (opt)
```

Runs `opm.backsolve` against the head snapshot's cap table; the
analyst supplies every input (the tool does NOT pick volatility or
DLOM). Compute-rate-limited. Writes `opm_backsolve_run` audit event
with inputs + solved equity value so the chain captures the
calibration moment.

New error codes:

| Code | HTTP | Where |
|---|---|---|
| `opm-bad-inputs` | 400 | Missing/invalid OPM input field |
| `backsolveblockersoutstanding` | 400 | Blocker findings unresolved (subclass) |
| `backsolvesolverfailed` | 400 | brentq couldn't bracket a solution |
| `backsolveanchormissing` | 400 | Anchor class not in cap table |

### 14.3 Vol pack → DCF sidecar suggestion (W9.3)

`build_dcf_sidecar(cap_table, vol_pack_readback=None)` and
`build_dcf_sidecar_bytes` accept an optional `VolPackReadback`. When
supplied, the "Read me" sheet surfaces volatility / TTL / risk-free /
DLOM as analyst-readable suggestions — explicitly NOT as defined
names the DCF model auto-pulls. Preserves the "expert-led, not
algorithm-only" register (§10.1 intent).

### 14.4 Phase-0 prefix anchoring (W9.4 / closes W8-m3)

`_PHASE_0_PREFIXES` split into `_PHASE_0_EXACT` (frozenset of exact
paths: `/upload`, `/diff`, `/sessions`) plus true prefixes with
trailing slash (`/diff/`, `/sessions/`, etc.). A future top-level
`/diffx` or `/sessions-list` route is no longer silently 404'd in
non-phase-0 deploys.

### 14.5 CSRF token rotation (W9.5 / closes wave-6 W6M-6)

CSRF tokens now carry an issuance-time prefix: `<unix_seconds>.<random>`.
The engagement blueprint's `after_request` hook rotates the cookie
when its age exceeds `CSRF_ROTATION_SECONDS` (3600). Pre-W9.5 opaque
tokens (no `.` prefix) are treated as stale and rotated immediately —
deploy upgrade path heals itself. A leaked token's blast radius drops
from 7 days to 1 hour.

### 14.6 NaN guard in `_classify_pct` (W9.6 / closes wave-7 W7m-3)

`snapshot_timeline._classify_pct` raises `ValueError` if either
`prior` or `current` is NaN. Cap-table numeric fields should never be
NaN; if a corrupt CapTable smuggles one in, surface it at the diff
layer instead of silently classifying as 'major'.

### 14.7 Snapshots pagination (W9.7)

`GET /engagement/<id>/snapshots?limit=N&offset=M` returns a sliced
window. Default `limit=50` (max 100), `offset=0` so the existing JSON
API stays compatible. HTML view renders `showing N of TOTAL` + prev/
next links. Bad pagination returns 400 `bad-pagination`.

### 14.8 Rule coverage CLI (W9.8)

`flask --app app rule-coverage` runs every registered rule against
every fixture and reports `rule_id → fixtures-where-it-fires`.
Surfaces rules with zero coverage (dead-code review prompt) without
running the test suite.

### 14.9 New audit event

| Event type | Payload |
|---|---|
| `opm_backsolve_run` | `{snapshot_id, anchor_class, anchor_pps, volatility, ttl_years, risk_free, dlom, implied_total_equity_value}` |

This concludes spec amendment round 7. Re-tag as `spec-r7-2026-05-30`.

