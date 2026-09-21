# Code Audit — Pre-Build Hardening Pass
> Independent review by an external auditor. Findings ranked by severity. Each cites file:line. Each says whether the fix is local (safe to apply now) or architectural (defer to build).

## 0. Auditor's stance

I read every file under `src/` (`models.py`, `parser.py`, `checklist.py`, `waterfall.py`, `formula_workbook.py`, `pdf_intake.py`, `diff.py`, `audit_memo.py`, `persistence.py`, `cli.py`) and `app.py`, plus targeted sections of `SYSTEM_SPEC.md` (Phases 0 contract: §1.1, §1.2, §1.3, §1.9, §1.10, and the SAFE-UNCONVERTED rule in §1.5). I did NOT read anything under `tests/`, `fixtures/`, `stress_test/`, `precedent/`, `AUDIT_PLAN.md`, `CURRENT_STATE.md`, `BUG_REPORT.md`, `VERIFICATION_MATRIX.md`, `PLAN*.md`, or any other planning artifact, on instruction.

Methodology: read each module once cover-to-cover, treating docstrings and the spec as contract; flag any place where the code's runtime behavior diverges from a reasonable reading of the contract or from common sense. Where a bug was reproducible from the Python REPL using only `src/*` imports, I ran it through `.venv/bin/python -c` to confirm and capture the wrong output. Findings that depend on assumptions I could not check (test fixtures, downstream UI templates) are marked accordingly. Severity is calibrated to: blocker = wrong numbers on plausible input, major = silent data loss / spec drift / resource leak that compounds, minor = code smell / hardening opportunity.

---

## 1. Blockers (must fix before any build starts)

### BUG-001 — Parser silently drops share-class rows whose Type cell is an unrecognized synonym

- **File:line:** `src/parser.py:511,599-608`; flow is `_row_to_share_class` line 511 (`sc_type = _coerce_class_type(raw_type) or ShareClassType.preferred`) → row 583 attempts `ShareClass(...)` → Pydantic raises because preferred-without-LP is forbidden → row 599 catches and returns `None` → caller `parse_excel` at line 425 skips the row.
- **What the bug is:** When the workbook's Type column contains a value not in the alias table (`founders`, `founder common`, `seed preferred`, `series-seed`, anything not in the hand-curated map on lines 207-229), the parser silently defaults the type to `preferred`. That forces the LP-required validator to fire (`models.py:121`), which raises, which gets caught at parser line 599, which appends a `share_class_validation_failed` warning and *drops the entire row*. The downstream waterfall, fully-diluted total, audit memo, and live workbook are computed against the wrong cap table. The user sees no shares missing — they see a warning buried in the parse report. This is the worst kind of bug: wrong-numbers output with a smiley face on top.
- **Reproduction (run from project root):**
  ```
  .venv/bin/python -c "
  import tempfile, openpyxl
  from src.parser import parse_excel
  wb = openpyxl.Workbook(); ws = wb.active; ws.title='Cap Table'
  ws.append(['Class Name','Type','Shares','Issue Price','Issue Date'])
  ws.append(['Founders Stock','Founders',100000,0.001,'2020-01-01'])
  ws.append(['Common Stock','Common',50000,0.01,'2020-01-02'])
  p = tempfile.mktemp(suffix='.xlsx'); wb.save(p)
  ct, report = parse_excel(p)
  print('classes kept:', [(sc.name, sc.type.value, sc.shares_outstanding) for sc in ct.share_classes])
  "
  ```
  Output: `classes kept: [('Common Stock', 'common', 50000)]`. The 100,000-share Founders row vanished. Fully-diluted total reported by the waterfall is 50,000 not 150,000.
- **Fix recommendation (local):** Change `_row_to_share_class` so unknown class types are NOT silently coerced to `preferred`. Either (a) default unknown to `ShareClassType.common` with a warning (safer default — common always validates), or (b) refuse to construct the row and emit a `class_type_unknown` warning at `blocker` level so the caller surfaces it. Option (a) preserves data; option (b) preserves analyst trust. Pick one — both are local edits inside `_row_to_share_class`.
- **Severity rationale:** Wrong totals in the artifact a third-party will rely on for fair-value work. Defensibility is the product. Silent loss of 100k shares fails the brief.

### BUG-002 — `_detect_field_for_header` second-pass `in`-match maps "share class type" → `class_name` (wrong field)

- **File:line:** `src/parser.py:139-143`.
- **What the bug is:** The second pass uses `if norm.startswith(syn) or syn in norm`. The synonym list for `class_name` includes "share class". The synonym list for `class_type` includes "class type". A real-world header `"Share Class Type"` is checked against `class_name` synonyms first (line 102 puts class_name before class_type in `SYNONYM_TABLE`); `"share class type".startswith("share class")` is True, so the column gets mapped to `class_name`. The actual class-type column is then unmapped, causing every row's type to fall through to the default-preferred path (BUG-001) and drop.
- **Reproduction:**
  ```
  .venv/bin/python -c "from src.parser import _detect_field_for_header; print(_detect_field_for_header('share class type'))"
  ```
  Output: `class_name`. Expected: `class_type`.
- **Same root cause hits:** `"Comments on shares"` → `shares` (expected `notes`), `"Outstanding shares"` → `shares` (right answer, wrong reason — would also catch `"shares outstanding count and price"`), `"Shareholder Name"` → `class_name` (defensible). The bug is the order-dependent prefix match over a flat synonym table where prefixes overlap.
- **Fix recommendation (local):** Score every (field, synonym) match in both passes and return the longest exact-substring match, not the first found. Or, more conservatively, score by (exact_match=3, full_word_match=2, substring=1) and take the max. Or split the table into "primary" vs "fallback" tiers with explicit precedence. The first match is a structural mistake — a two-line scoring loop replaces it. Local fix.
- **Severity rationale:** Combined with BUG-001, a single mislabeled header in a real client cap table drops the entire share-class population. Both bugs need to land together.

### BUG-003 — `SAFE-UNCONVERTED` rule violates spec: only checks the FIRST subsequent priced round, not "at least one"

- **File:line:** `src/checklist.py:201-209`.
- **What the bug is:** Spec §1.5 line 227 (rule 5) says: "Triggered when a SAFE has `conversion_trigger_threshold` set and **at least one** preferred class has `issue_date > safe.issue_date` and a derived round-size meeting/exceeding the threshold." The code on line 205 takes `subsequent[0]` (the earliest priced round AFTER the SAFE) and tests only that one. If the earliest round is sub-threshold but a later round qualifies, the rule silently fails to fire — the unconverted SAFE goes unflagged, and the audit memo's blocker count is wrong.
- **Reproduction:**
  ```
  .venv/bin/python -c "
  from src.models import CapTable, Company, ShareClass, ShareClassType, LiquidationPreference, LPType, SAFE
  from src.checklist import run_checklist
  from datetime import date
  ct = CapTable(company=Company(name='T'), share_classes=[
      ShareClass(name='C', type=ShareClassType.common, shares_outstanding=1000),
      ShareClass(name='A', type=ShareClassType.preferred, shares_outstanding=1000, issue_price=0.5, issue_date=date(2022,1,1), seniority_rank=2,
                 liquidation_preference=LiquidationPreference(multiple=1, amount=500, type=LPType.non_participating)),
      ShareClass(name='B', type=ShareClassType.preferred, shares_outstanding=10000, issue_price=2.0, issue_date=date(2023,1,1), seniority_rank=1,
                 liquidation_preference=LiquidationPreference(multiple=1, amount=20000, type=LPType.non_participating)),
  ], safes_outstanding=[SAFE(id='SAFE-1', principal=5000, issue_date=date(2021,6,1), conversion_trigger_threshold=10000)])
  print([f.code for f in run_checklist(ct) if 'SAFE' in f.code])
  "
  ```
  Output: `[]`. Series A raised 500 (sub-threshold). Series B raised 20,000 (10x the threshold). Spec says one such round should trigger; code raises zero findings.
- **Fix recommendation (local):** Replace `first_after_amount >= threshold` with `any(amt >= threshold for d, amt, name in subsequent)`; cite the first qualifying round in the summary. Five-line change in `_rule_unrecorded_safe_conversion`.
- **Severity rationale:** Direct spec violation on a `blocker`-severity rule. Means audit memos signed off on are missing a fairness flag that the SYSTEM_SPEC promises will fire.

### BUG-004 — `audit_memo.build_audit_memo` does not escape `|` in share-class names or company name; corrupts the Markdown tables

- **File:line:** `src/audit_memo.py:91-94` (cap structure row), `183` (tranche table header), `155` (only finding.summary is escaped). Same risk in audit_memo `_describe_lp` outputs that go into the same table cells.
- **What the bug is:** The function generates a Markdown pipe table. It correctly escapes `|` inside `f.summary` (line 155), but does not escape any other field. A share class literally named `"Common | Voting"` (which spec §1.3 allows — "any character openpyxl accepts") breaks the table into mis-aligned columns. The audit memo is the output the analyst hands to the partner — it must not silently corrupt itself.
- **Reproduction:**
  ```
  .venv/bin/python -c "
  from src.audit_memo import build_audit_memo
  from src.models import CapTable, Company, ShareClass, ShareClassType, LiquidationPreference, LPType
  from src.waterfall import compute_waterfall
  from src.checklist import run_checklist
  ct = CapTable(company=Company(name='Acme | Co'), share_classes=[
      ShareClass(name='Common|Stock', type=ShareClassType.common, shares_outstanding=1000),
      ShareClass(name='A', type=ShareClassType.preferred, shares_outstanding=100, seniority_rank=1,
                 liquidation_preference=LiquidationPreference(multiple=1, amount=100, type=LPType.non_participating)),
  ])
  for ln in build_audit_memo(ct, compute_waterfall(ct), run_checklist(ct)).split('\n'):
      if 'Common|Stock' in ln: print(ln)
  "
  ```
  Output: `| Common|Stock | common | 1,000 | — | — | — | — | — |` — the `|` inside the class name renders as a column delimiter in any Markdown renderer.
- **Fix recommendation (local):** Add `_md(s)` helper that returns `str(s).replace("|", "\\|").replace("\n", " ")` and apply uniformly to every field placed inside a pipe table — `sc.name`, `co.name`, side letter title, lp_desc, ad, holder, etc. Twenty-line change confined to `audit_memo.py`.
- **Severity rationale:** Workpaper integrity. A memo that reformats itself is non-defensible.

### BUG-005 — `SessionStore` leaks SQLite connections on every operation (the 179 ResourceWarnings)

- **File:line:** `src/persistence.py:101-104` (`_connect`); every call site uses `with self._connect() as conn:` (lines 97, 138, 170, 179, 212, 216, 222, 259). The Python stdlib `sqlite3` context manager calls commit/rollback on `__exit__`, *not* `close()`. The connection lives until the garbage collector reclaims it.
- **What the bug is:** Every read or write through `SessionStore` opens a brand-new SQLite connection and never explicitly closes it. The 179 ResourceWarnings in the persistence test suite are the symptom; in production, this means the Flask process leaks file descriptors at the rate of every dict lookup. `/healthz` (which calls `len(SESSIONS)` and therefore opens a new connection) on a load balancer's health probe will add tens of leaked descriptors per minute. The cache mitigates this for reads of warm sessions but not for `__contains__`, `__len__`, `list_sessions`, `delete`, or any first-touch read.
- **Reproduction:**
  ```
  .venv/bin/python -W always -c "
  import tempfile, gc
  from pathlib import Path
  from src.persistence import SessionStore
  from src.models import CapTable, Company, ShareClass, ShareClassType
  p = Path(tempfile.mktemp(suffix='.db'))
  store = SessionStore(p)
  ct = CapTable(company=Company(name='X'), share_classes=[ShareClass(name='C', type=ShareClassType.common, shares_outstanding=1)])
  store['t1'] = {'cap_table': ct, 'parse_report': None}
  len(store); 't1' in store; store.get('t1'); store.delete('t1')
  del store; gc.collect()
  "
  ```
  Output: at least 4 lines of `ResourceWarning: unclosed database in <sqlite3.Connection object ...>` for a single minimal flow.
- **Fix recommendation (local):** Wrap `_connect` so callers do `with closing(self._connect()) as conn: with conn: ...` (the inner `with conn` keeps the commit-on-exit semantics). Or refactor `SessionStore` to hold one long-lived connection per instance and add a `with self._lock:` around mutating operations. The second is architectural-ish (need to verify threading model — Flask debug reload threads, gunicorn workers). The `contextlib.closing` wrap is a local two-line fix and eliminates the warnings immediately.
- **Severity rationale:** Resource leak under any production-like load. Even single-tenant: a screen-shared demo that runs an hour through `/healthz` accumulates hundreds of FDs.

---

## 2. Majors (should fix before build, but not blocking)

### BUG-006 — `parse_excel` upload path hardcoded to `/tmp`, not OS-portable; double-handles bytes through disk

- **File:line:** `app.py:177-186`, also `app.py:1139-1140` (`/diff` route).
- **What the bug is:** `tmp = Path("/tmp") / f"cap_{secrets.token_hex(4)}.xlsx"` is POSIX-only. Breaks on Windows. Also: the route reads the file into memory (`data = file.read()`), then writes to disk, then re-reads via `load_workbook(path)`. openpyxl can `load_workbook(BytesIO(data))` directly — eliminating the disk hop, the cleanup branch (lines 182-186), and the swallow-OSError dance. The current code also leaves orphan `.xlsx` files in `/tmp` if the process crashes between write and unlink.
- **Reproduction:** N/A on macOS but `Path("/tmp")` does not exist on a default Windows install. Visual code inspection.
- **Fix recommendation (local):** Use `tempfile.NamedTemporaryFile(suffix=".xlsx", delete=True)` and pass its `.name` to `parse_excel`, or refactor `parse_excel` to accept `BytesIO`. The second is the cleaner refactor and trivially testable.
- **Severity rationale:** Portability + minor resource leak under failure. Demo-time on a Mac, nobody dies.

### BUG-007 — `/healthz` returns `active_sessions` count, spec promises `{"status": "ok"}` only; also opens leaked SQLite connection

- **File:line:** `app.py:1159-1161`; spec §1.10 row "GET /healthz" line 432 promises `JSON {"status": "ok"}, 200`.
- **What the bug is:** Spec drift (extra field) plus the `len(SESSIONS)` triggers BUG-005's connection leak on every health probe. A liveness probe at 10-second intervals over an 8-hour workday = 2,880 leaked SQLite connections.
- **Fix recommendation (local):** Either (a) remove `active_sessions` to match spec, or (b) update spec to acknowledge the field. Independently, fix BUG-005 so the count call doesn't leak.
- **Severity rationale:** Spec drift on a contract that infrastructure depends on; compounds the connection leak.

### BUG-008 — `parser._read_convertibles_tab` hardcodes warrant `share_class = "Common"`, ignoring the source row's actual class

- **File:line:** `src/parser.py:651-661`. Line 656: `share_class="Common"` is a literal regardless of what the workbook says.
- **What the bug is:** A vendor warrant exercisable into Series A Preferred (common in venture deals — strategic warrants struck at the round's PPS) is recorded as Common in the model. Downstream the warrant exercise math (price × shares) is computed against the wrong class's PPS, the wrong LP entitlements get triggered, the wrong seniority is applied in the waterfall.
- **Reproduction:** Static; the literal is on line 656. The notes-text regex on lines 649-650 only extracts share *count* and *strike price*, never share class.
- **Fix recommendation (local):** Parse a "Share Class" column from the convertibles tab if present; default to `"Common"` with a `warrant_share_class_assumed` warning. Add the column to spec §1.1's convertibles tab description.
- **Severity rationale:** Wrong cap-table inputs for any warrant that isn't common-stock. Hidden because today's fixtures may all use Common warrants.

### BUG-009 — `load_from_canonical_json` silently drops `cap_amount` when both `cap_multiple` and `cap_amount` are supplied; no consistency check

- **File:line:** `src/parser.py:731-735`.
- **What the bug is:** Comment says "If both given and consistent, drop cap_amount" but the code never checks consistency: it just zeroes `cap_amt_in` when both are present. A fixture authored with `cap_multiple=2.0` and `cap_amount=$10M` on a class with `amount=$1M` (so the consistent answer is `cap=$2M`, but the fixture says `cap=$10M`) silently keeps the multiple and discards the amount, producing a 5x-too-low cap with no warning.
- **Fix recommendation (local):** When both are present, compute `expected = cap_multiple * amount`; if `abs(expected - cap_amount) / max(expected, 1) > 1e-6`, raise a `ValueError` referencing the file and the class. Don't silently drop.
- **Severity rationale:** Fixture-authoring footgun. Spec §1.3 says the validator forbids both being set; the loader strips one without checking — the contract is preserved structurally but violated semantically.

### BUG-010 — `/whatif` divide-by-zero fallback makes LP amount ignore the override

- **File:line:** `app.py:606-612`. `shares_ratio = (new_shares / sc.shares_outstanding) if sc.shares_outstanding else 1.0`.
- **What the bug is:** If the baseline class has `shares_outstanding == 0` and the analyst types a non-zero value into the what-if slider, `shares_ratio` falls back to `1.0` to avoid division by zero. Then `lp.amount * 1.0 * mult_ratio` keeps LP at its baseline value, which (because baseline shares=0 implies LP base of 0) stays at 0 regardless of override. The override silently has no economic effect.
- **Fix recommendation (local):** When `sc.shares_outstanding == 0` and `new_shares > 0`, recompute LP from `new_shares × issue_price × new_mult` rather than scaling. Or refuse the override and surface "cannot scale zero-baseline class — re-export to make structural changes" inline.
- **Severity rationale:** Edge case unlikely on real cap tables (zero-share classes are rare), but the silent no-op violates the what-if contract.

### BUG-011 — Parser `_read_convertibles_tab` never sets `conversion_trigger_threshold` from spreadsheet input

- **File:line:** `src/parser.py:637-646` (SAFE construction).
- **What the bug is:** The `SAFE` model has `conversion_trigger_threshold: Optional[float]` (models.py:165). The convertibles-tab reader never reads or populates it. Combined with BUG-003: the rule defaults missing threshold to `0.0`, meaning "any priced round triggers conversion" — so every parsed SAFE-with-subsequent-round fires SAFE-UNCONVERTED regardless of the intended trigger size. Mirror bug: convertible notes lose `qualified_financing_threshold`.
- **Fix recommendation (local):** Add header detection for "Trigger Threshold (USD)" / "Conversion Trigger" / "Qualified Financing" and populate the field. Two lookups in the existing `idx` table.
- **Severity rationale:** Causes the wrong set of SAFE-UNCONVERTED findings on real input. Combined with BUG-003, the rule is effectively unreliable in both directions (false negatives on subsequent rounds, false positives on missing thresholds).

### BUG-012 — `app.py /upload` and `/diff` swallow every `Exception` as a generic "Could not parse file"

- **File:line:** `app.py:187-188`, `app.py:1152-1153`.
- **What the bug is:** A broad `except Exception as e:` catches `MemoryError`, `RecursionError`, `OSError` from disk-full conditions, and any internal bug — and stringifies the exception into a user-facing template. Hides genuine system failures behind a friendly message; complicates debugging (no stack trace in logs); and the only structured error response is the rendered template, which means CI smoke tests can't distinguish "bad input" from "broken parser."
- **Fix recommendation (local):** Narrow the catch to `(ValueError, KeyError, openpyxl.utils.exceptions.InvalidFileException, pydantic.ValidationError)`. Re-raise everything else; let Flask 500 with a traceback in dev. Log the caught exceptions with `app.logger.exception(...)` either way.
- **Severity rationale:** Diagnosability regression. The kind of bug that becomes blocking only after something else fails.

### BUG-013 — `parser._read_company_tab` key-normalization differs from default lookup; `"Company Name"` row silently becomes `Unnamed Company`

- **File:line:** `src/parser.py:467-489`. Key normalization is `_normalize(row[0]).replace(" ", "_")`. Default lookups use literal keys `"company"`, `"jurisdiction"`, `"sector"`, `"stage"`, `"currency"`, etc.
- **What the bug is:** A workbook with a header label `"Company Name"` produces the key `company_name`, which doesn't match `fields.get("company", ...)` → falls through to the `Unnamed Company` default. Same for `"Date of Valuation"` → `date_of_valuation` vs `valuation_date`. Same for `"Currency Code"` → `currency_code` vs `currency`. Silent default. The Company tab is "optional" per spec, so the user has no upstream indication their metadata was discarded.
- **Fix recommendation (local):** Build a small alias table for company-field lookups, mirroring the share-class synonym pattern. Five-line change.
- **Severity rationale:** Silent fact-loss on the company metadata that prints on the cover sheet of the memo.

### BUG-014 — `diff._diff_class` treats `None` and `0` as equal for `issue_price` and `conversion_ratio`; loses a real signal

- **File:line:** `src/diff.py:134` (`(left.issue_price or 0) != (right.issue_price or 0)`), `src/diff.py:142` (`(left.conversion_ratio or 1.0) != ...`).
- **What the bug is:** Spec promises "fuzzy matched and structured deltas." A class that gains a `conversion_ratio` of `1.0` after a ratchet adjustment (from `None`) registers no delta because `None or 1.0 == 1.0`. A class whose `issue_price` was `None` before (unknown) and is `0` after (intentionally zero) registers no delta. The "no change" rendering for a meaningful semantic change misleads the analyst reviewing the subsequent-events section.
- **Fix recommendation (local):** Compare with `!=` directly; format `None` separately from `0` / `1.0` in display. Three-line change.
- **Severity rationale:** Less common than the others, but a documented spec promise ("structured diff suitable for the audit memo") is being silently weakened.

---

## 3. Minors (track in backlog, fix opportunistically)

### BUG-015 — `parse_excel` signature differs from spec: `manual_column_mapping: dict[str, int]` vs spec's `dict[canonical_field → actual_header_string]`

- **File:line:** `src/parser.py:361`; spec §1.1 input-contract paragraph "Optional `manual_column_mapping: dict[canonical_field → actual_header_string]`."
- The code uses column index. Either update spec or refactor the parameter; today no caller passes the param.

### BUG-016 — `parser._to_int(value)` truncates floats with `int(v)` instead of rounding; `"1500.7"` → `1500`

- **File:line:** `src/parser.py:291` (`if isinstance(v, float): return int(v)`).
- Share counts come in as whole numbers normally, but openpyxl returns numeric cells as `float`. A cell value `1500.0` is safe; `1500.7` (corrupted data) silently truncates. Use `round()` and warn if non-integer.

### BUG-017 — `parser._to_float` strips `"x"` and `"X"` unconditionally; turns the literal `"1.5x"` LP-multiple correctly into `1.5`, but also turns `"6x4 grid"` notes-cell into `64`

- **File:line:** `src/parser.py:278`.
- Low-impact today because the strip is on a column already typed as numeric, but if `_to_float` is ever pointed at a free-text column, surprises follow.

### BUG-018 — `pdf_intake.extract_text` returns `("", warnings)` on any pdfplumber exception, even fatal ones

- **File:line:** `src/pdf_intake.py:51-53`.
- A bad PDF returns a SideLetter with empty body and a warning string. Spec line 117 says scanned PDFs should return `("", ["pdf-no-text-recovered"])` (a specific code). Code returns `("", ["pdfplumber failed: <exception text>"])` — different code, raw exception text leaking into the UI. Normalize to the spec's code.

### BUG-019 — `diff._match_classes` greedy by max-similarity, not optimal (Hungarian)

- **File:line:** `src/diff.py:78-92`.
- With three classes where `A-A'=0.85`, `B-A'=0.95`, `B-B'=0.6`, greedy picks `B-A'`, leaving `A` unmatched even though the optimal pairing is `A-A'`, `B-B'`. Real cap-table diffs rarely hit this, but documented "greedy" should be acknowledged in the docstring or upgraded to assignment.

### BUG-020 — `formula_workbook` named-range slug strips characters but doesn't guarantee Excel-valid names

- **File:line:** `src/formula_workbook.py:295`.
- `sc.name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")` — leaves `,`, `&`, `'`, leading digits, leading `_`, and Excel-reserved names (`C`, `R`, `R1C1`, `A1`) untouched. A class named `"Series A & B Pref"` produces a defined-name `Series_A_&_B_Pref` which Excel rejects. Workbook generation throws silently inside openpyxl (or worse, succeeds but the named ranges are broken).

### BUG-021 — `app.py /upload` accepts only `.xlsx`, not `.xlsm`

- **File:line:** `app.py:172-173`.
- Spec §1.1 says `.xlsx`. But openpyxl can read `.xlsm` (macro-enabled) cleanly. Real client cap tables often arrive as `.xlsm`. Either accept or document the rejection more clearly than "Only .xlsx files are supported."

### BUG-022 — `app.py /export/<token>.zip` uses `import zipfile` inside the function

- **File:line:** `app.py:941`. Cosmetic; move to module top.

### BUG-023 — `app.py /resolve/<token>/anti_dilution/<path:class_name>` uses `<path:...>` converter; class names with `/` or `..` make the URL ambiguous, but lookup is by literal `sc.name` match

- **File:line:** `app.py:294`. Not a security bug (no filesystem access), but a class name like `"Series A/B"` is URL-encoded to `Series%20A%2FB` then path-decoded to `Series A/B` — Flask routes this through `<path>`, which can swallow slashes in unexpected ways depending on WSGI. Worth a test.

### BUG-024 — `app.py /upload_side_letter` filename check is `.lower().endswith(".pdf")` — accepts `evil.exe.pdf` by extension only

- **File:line:** `app.py:513`. The file is then passed to pdfplumber, which validates the magic bytes — so this is not a real RCE path. But the validation should be magic-bytes anyway. Minor hardening.

### BUG-025 — `audit_memo.build_audit_memo` `[ANALYST: ...]` markers are not validated for completion in any exporter

- **File:line:** `src/audit_memo.py:243-249`.
- If an analyst exports the `.md` without filling the placeholders, no warning. A nice-to-have linter at export time.

---

## 4. Contract drift (docstring or spec says X, code does Y)

| Where | Spec / docstring says | Code does | Decision |
|---|---|---|---|
| `parser.py:361` | Spec §1.1: `manual_column_mapping: dict[canonical_field → actual_header_string]` | `dict[str, int]` (column index) | Update spec; using index is less brittle. |
| `checklist.py:201-209` | Spec §1.5 rule 5: "at least one preferred class … meeting the threshold" | Only first subsequent round checked | **Fix code** — see BUG-003. |
| `app.py:1161` | Spec §1.10: `/healthz → JSON {"status": "ok"}` | Returns `{"status": "ok", "active_sessions": N}` | Either: drop `active_sessions` (match spec) or update spec. Independent of BUG-005. |
| `pdf_intake.py:52` | Spec §1.2: image-only PDFs return `["pdf-no-text-recovered"]` | Returns `["pdfplumber failed: <raw exception>"]` | Fix code to match spec — see BUG-018. |
| `audit_memo.py` table cells | Spec §1.7 implies Markdown that renders correctly | No pipe escaping → table corruption | **Fix code** — see BUG-004. |
| `parser.py:511` | Spec §1.1: "If a row constructs a ShareClass that fails Pydantic validation → row is skipped; a warning is appended." | Yes, but the failure is *caused by* the parser's own default-to-preferred coercion, not by the input data | **Fix code** — see BUG-001. Spec is silent on the coercion choice; the choice causes the data loss. |
| `formula_workbook.py:188-199` README banner | "Live formulas valid for input edits preserving threshold ordering" | True for simple edits, but no runtime check warns the user if Excel formulas evaluate to a different breakpoint order than the baked literals on the States sheet | Document limitation more sharply OR add a SUMPRODUCT-based assertion cell that flashes red when regimes flip; defer to a later phase. |
| `persistence.py:62-78` | "Lazy-write cache: reads come from memory first, falling back to the DB; writes are flushed to disk via flush(token)" | True, but `__contains__` and `__len__` always hit the DB even when the cache is warm | Minor; spec doesn't promise cache-only `__contains__`. Acceptable. |

---

## 5. Resource and performance concerns

- **SQLite connection leak** (BUG-005): the headline. Every call site of `SessionStore` leaks a connection. 4 leaks per minimal CRUD cycle in my reproduction; the test-suite count of 179 is consistent with running ~40 test cases that each exercise a handful of operations.
- **`app.py /healthz`** opens a fresh connection on every probe (BUG-007).
- **`app.py /upload`** writes the uploaded bytes to disk in `/tmp`, then reads them back — 2x memory + disk hop. openpyxl supports `BytesIO`; eliminate the disk leg (BUG-006).
- **PDF processing** (`/upload_side_letter`): the entire blob is `file.read()` into memory (`app.py:516`). 8 MB cap from `MAX_CONTENT_LENGTH` bounds this — acceptable.
- **`_build_clean_workbook` and `build_formula_workbook`** keep the entire workbook in memory then serialize via `BytesIO`. For cap tables with <100 classes (the realistic ceiling), bounded; for the 1000-class stress test, memory is openpyxl-dominated and out of scope here.
- **`waterfall._dedupe_close_values`** O(n) over sorted breakpoints — fine; tolerance based on `max(values) * 1e-6` could in principle merge legitimately close breakpoints in very-large-cap-table scenarios. Defer.
- **`diff._lev`** is O(len_a × len_b) per pair; the matcher in `_match_classes` recomputes similarity in an inner loop. For a cap table with N classes on each side, that's O(N² × max_name_len²). N is small. Fine.
- **Flask debug reloader's `extra_files`** (`app.py:1170-1176`) globs every template/css/js on every import-tick. Harmless in dev. Don't ship to prod.

---

## 6. Test-suite gaps surfaced

(Reasoned from code inspection alone — I did not read the tests.)

- **Unknown-class-type drop (BUG-001)** — would be caught only by a test that asserts `len(cap_table.share_classes) == len(input_rows)` for a fixture containing a `Type` value not in the alias table. If tests only use the 5 curated fixtures, this is invisible.
- **Header ambiguity (BUG-002)** — needs an adversarial header set including `"Share Class Type"`, `"Class Number"`, `"Comments on shares"`. The 93% coverage on `parser.py` likely comes from happy paths; the second-pass `in`-match branch is hit but not asserted to produce a *correct* mapping for ambiguous inputs.
- **SAFE rule with N≥2 subsequent rounds (BUG-003)** — needs a fixture where the SAFE's threshold sits between the first and second post-SAFE round. The 5 curated fixtures probably don't exercise this.
- **`audit_memo` pipe escaping (BUG-004)** — needs a fixture with `|` in a class name or company name. Unlikely in curated data.
- **SessionStore connection counting** — would be caught by an explicit `lsof`-style probe or a `gc.get_referrers` test, neither of which is a normal pytest pattern. The 179 `ResourceWarning` is the only signal; if `-W ignore::ResourceWarning` is set anywhere, the signal vanishes.
- **`_to_int` float-truncation (BUG-016)** — a unit test passing `1500.7` would expose it.
- **`/whatif` zero-share fallback (BUG-010)** — needs a baseline class with shares=0 in a fixture; nobody writes those.
- **`Warrant` share-class hardcoded to "Common" (BUG-008)** — would be caught by parsing a convertibles tab containing a warrant struck against preferred and asserting `warrant.share_class != "Common"`.
- **Path traversal / Excel-invalid named ranges (BUG-020)** — would need a class named `"Series A & B"` and an assertion that the live workbook opens in Excel without error. openpyxl will let you write invalid names; only Excel itself complains.

The pattern: high coverage of the call graph, low coverage of the *contract* on adversarial inputs. Most of these are one-fixture or one-test-case fixes.

---

## 7. Security review

- **Path traversal in upload routes:** `app.py:177` uses `Path("/tmp") / f"cap_{secrets.token_hex(4)}.xlsx"` — the filename component is random, not user-controlled. Safe. Same in `/diff` (lines 1139-1140) and the implicit PDF blob route (which reads from memory, no disk write). The `<path:class_name>` converter on `/resolve/<token>/anti_dilution/<path:class_name>` is matched against in-memory cap-table data — no filesystem access. Safe.
- **XSS in rendered cell content:** Jinja2 autoescape is enabled by default and the templates I saw (`templates/index.html`) use `{{ error }}` without `|safe`. Safe. The `audit_memo.md` is rendered server-side, not displayed in the browser; if a user uploads it back somewhere that renders Markdown without escaping, the unescaped `|` (BUG-004) is the issue, not script injection.
- **Pickling / eval / unsafe YAML:** none found. The codebase uses `json` only. Good.
- **Secrets in code:** none. The Flask app has no `secret_key` set explicitly — Flask's session signing is unused (no `flask.session` usage that I saw); `secrets.token_urlsafe(8)` is used for session tokens. 8-byte URL-safe is ~48 bits of entropy — fine for a local-only tool but undersized for any internet-exposed deployment. Spec §1.10 acknowledges no auth, no multi-user. OK for Phase 0.
- **File upload size enforcement:** `MAX_CONTENT_LENGTH = 8 * 1024 * 1024` covers `/upload`, `/upload_side_letter`, and `/diff`. Flask returns 413 above it. Spec-compliant.
- **No-cache header behavior:** `_no_cache` after-request hook sets `Cache-Control: no-store, max-age=0` on every response (`app.py:52-55`). Applies even to `/healthz` and static files. Slight perf cost; for a local tool, fine.
- **CSRF:** Flask has no built-in CSRF protection and the codebase doesn't add `flask-wtf`. Every POST route (upload, resolve_*, whatif, sessions/<token>/delete) is vulnerable to CSRF on any deployment where another origin can reach the host. Spec §1.10 acknowledges no multi-tenancy; for local-only, acceptable.
- **Open redirect:** routes that `redirect(url_for(...))` always use named-endpoint URLs; no `request.args.get('next')` style. Safe.
- **Class-name path parameter:** `/resolve/<token>/anti_dilution/<path:class_name>` and `/resolve/<token>/pool/<path:pool_name>` accept arbitrary path content. The handler looks up by exact `sc.name` match against in-memory data; no filesystem access. No injection vector visible. Worth a unit test for `class_name == ".."`.

No critical security findings. The architectural acknowledgment in the spec ("no auth, no multi-user, no audit log") aligns with the implementation.

---

## 8. Specific things I looked at and found CLEAN

- `models.py` — Pydantic validators are tight; the `cap_required_when_capped` and `preferred_must_have_lp` and `share_class_names_unique` and `preferred_seniority_unique` validators each guard a real failure mode. The `extra="forbid"` config on every model catches typos at construction.
- `waterfall._normalize_degenerate_caps` — collapsing `cap_multiple <= 1.0` capped LPs to non-participating is a thoughtful, documented edge-case handler that avoids dead-zone tranches. Good.
- `waterfall._dedupe_close_values` — relative-tolerance merging of float-noise breakpoints, with clear rationale. Good.
- `waterfall.compute_waterfall` — the regime walker is the technically hardest code in the repo and reads cleanly; the `_make_state` + `_alloc_marginal` + `_regime_at_value` decomposition is principled.
- `formula_workbook._sheet_inputs` — yellow-for-editable, grey-for-derived convention is exactly right; the README banner explicitly calls out the structural-edit limitations.
- `cli.py` — small, no surprises; the artifact-emission helper is clean.
- `app.py` route handlers — the `<token>` validation pattern is consistent; every route checks `sess is None` and returns the right `session_expired.html` template + 404.
- `pdf_intake.extract_text` — text-only, no OCR, no LLM, honest about scope. Matches spec.
- The `INPUT_FILL` / `DERIVED_FILL` / `HEADER_FILL` style separation in `formula_workbook` is consistent and clear.
- `Finding` is a frozen dataclass with a stable `code` field — good for downstream UI hyperlinks.

---

## 9. The fix-now-vs-defer decision per finding

| ID | Severity | Fix scope | Recommendation |
|---|---|---|---|
| BUG-001 | Blocker | Local | Fix now — silent data loss |
| BUG-002 | Blocker | Local | Fix now — combines with BUG-001 |
| BUG-003 | Blocker | Local | Fix now — direct spec violation |
| BUG-004 | Blocker | Local | Fix now — workpaper corruption |
| BUG-005 | Blocker | Local (closing-wrap) or Architectural (long-lived conn) | Local closing-wrap now; architectural cleanup in build phase |
| BUG-006 | Major | Local | Fix in build — Windows portability + cleaner stream-based parse |
| BUG-007 | Major | Local | Fix now — trivial; spec match + amplifies BUG-005 |
| BUG-008 | Major | Local | Fix now — wrong cap-table inputs for non-common warrants |
| BUG-009 | Major | Local | Fix now — fixture-authoring safety net |
| BUG-010 | Major | Local | Fix in build — edge case, low priority |
| BUG-011 | Major | Local | Fix now — combines with BUG-003 |
| BUG-012 | Major | Local | Fix now — diagnosability |
| BUG-013 | Major | Local | Fix now — silent metadata loss |
| BUG-014 | Major | Local | Fix in build — diff fidelity |
| BUG-015 | Minor | Spec-only | Update spec text |
| BUG-016 | Minor | Local | Fix opportunistically |
| BUG-017 | Minor | Local | Fix opportunistically |
| BUG-018 | Minor | Local | Fix in build — normalize error codes |
| BUG-019 | Minor | Local | Document as known limitation |
| BUG-020 | Minor | Local | Fix in build — Excel name sanitization |
| BUG-021 | Minor | Local | Decide whether to accept `.xlsm` |
| BUG-022 | Minor | Cosmetic | Fix opportunistically |
| BUG-023 | Minor | Local | Add test |
| BUG-024 | Minor | Local | Magic-bytes check; low priority |
| BUG-025 | Minor | Local | Defer; not in Phase 0 contract |

**Recommended sequencing:** before any build starts, land BUG-001 / BUG-002 / BUG-003 / BUG-004 / BUG-005 together — they are the five that produce wrong output or wrong artifacts on plausible input. The rest can ride in the build's normal review cadence.
