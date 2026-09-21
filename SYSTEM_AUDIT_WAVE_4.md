# Wave 4 Compiled Audit

## 0. Stance + methodology

Audit scope: wave-4 surfaces only — HTMX UI (templates/engagement/* + content negotiation), pack-bytes-at-bind (`bound_pack_json` column + bundle/memo read paths), DCF model template (`src/dcf_template.py`), rule pack v2026.5.0 (`src/rules_v2026_5.py`, 13 new rules), `valuation_date` retyping (`Optional[date]` + Pydantic validator), and the `/whatif` HTMX endpoint.

Excluded: tests/*, prior wave audits (CODE_AUDIT_WAVE_2.md, CODE_AUDIT_WAVE_3.md), SYSTEM_AUDIT_COMPILED.md, SYSTEM_AUDIT_RESULTS.md, BUILD_WAVE_*.md. Read: `src/*.py`, `templates/engagement/*.html`, `templates/memo/base.html`, `rule_packs/*.json`, `SYSTEM_SPEC.md` §5.3/§6.6/§8.10/§9.

Methodology: source read → repro scripts via `.venv/bin/python -c "..."` for every claim. All bugs below have a runnable repro. No bug was filed on inference alone.

Baseline: 603 active tests pass. Wave-4 modules total ≈ 1.5 kLoC.

---

## 1. Blockers (data integrity, auth bypass, audit-evidence break)

### B-1 — Pre-W4.5 engagements with non-ISO `valuation_date` are unreadable after the typing change

**Location**: `src/engagement.py:171-196` (validator) + `src/engagement.py:498` (`_row_to_engagement` passes raw column to constructor).

**Repro**: insert a row directly with `valuation_date='Q4 2025'` (legal under the pre-W4.5 `Optional[str]` contract). Then call `store.get_engagement('eid')` →

```
ValidationError: 1 validation error for Engagement
valuation_date
  Value error, valuation_date 'Q4 2025' is not a valid ISO date
```

**Impact**: any engagement created before W4.5 that contains a free-form date string ("Q4 2025", "EOY 2025", "May 25, 2026", literal "TBD") becomes permanently inaccessible. There is no migration that scrubs/coerces the column and no escape hatch in `_row_to_engagement`. Engagement detail, list, memo, bundle, audit-log, and verify endpoints all 500. This is an audit-evidence break for those engagements.

**Recommended fix**: either (a) one-shot migration in `__post_init__` that NULL-s any non-ISO `valuation_date`, or (b) `_row_to_engagement` swallows ValidationError on the date column and stores `None` plus a `_valuation_date_raw` shadow field for the audit trail.

### B-2 — Memo and bundle disagree on the bound rule pack when the on-disk JSON is mutated

**Location**: `src/engagement_routes.py:633` (memo: `pack = load_engagement_bound_pack(eng.pack_version)`) vs. `src/engagement_bundle.py:77-86` (bundle: prefers `eng.bound_pack_json`, falls back to disk).

**Repro**: edit `rule_packs/v2026.1.0.json` after an engagement was created. `bundle.zip` ships the original pack (DB bytes); `memo.pdf` runs the rules from the mutated disk file. Findings list diverges between memo and bundle for the same engagement.

**Impact**: violates SPEC §9.2 (engagement-bound pack is sticky for lifetime) and §8.10 determinism (same engagement → same memo bytes / same bundle bytes). An auditor re-verifying offline using bundle.zip cannot reproduce the memo's findings.

**Recommended fix**: memo route uses the same precedence as bundle — `bound_pack_json` first, disk fallback. Centralise into one helper.

---

## 2. Majors

### M-1 — DCF defined-name slug collision silently overwrites named ranges

**Location**: `src/dcf_sidecar.py:96-104` (the `wb.defined_names.add(...)` calls inside the per-class loop).

**Repro**: a cap table with classes `"Series A"` and `"Series-A"` both slugify to `"Series_A"` via `_slug_for_defined_name`. openpyxl silently overwrites the first `DefinedName` with the same key. Confirmed: after `wb.defined_names.add("share_count_Series_A", ...)` twice, `wb.defined_names["share_count_Series_A"]` points to the second class only. Persists across save+load.

**Impact**: the DCF template's `=share_count_Series_A` formula (template `_build_per_class_fv`) resolves to the wrong class's share count. Per-class FV column is silently wrong. No warning, no log line. Data-integrity break on legitimate class names (space-vs-hyphen, slash, dot).

**Recommended fix**: detect collision in `_slug_for_defined_name` or in the sidecar build loop — append `_2`, `_3` suffix on collision and surface the mapping in the "Named Range Map" sheet (which is already in the workbook).

### M-2 — Wave-4 W4.4 rules `_rule_future_valuation` and `_rule_warrant_expired` break determinism

**Location**: `src/rules_v2026_5.py:269` (`vd <= _date.today()`), `src/rules_v2026_5.py:418` (`today = _date.today(); ... if w.expiry_date < today`).

**Impact**: SPEC §6.6 + §8.10 row "Finding list" guarantees bit-for-bit determinism on `code, severity, category, summary, detail, fields_referenced`. Same cap table evaluated today vs. tomorrow → different findings as `today()` advances past `valuation_date` or `expiry_date`. Memo body §10 "Findings" diverges across runs. Existing rules in `rules_v2026_2/3/4.py` and `checklist.py` do not use `today()` — wave-4-specific regression.

**Recommended fix**: reference the engagement's `valuation_date` or `cap_table.company.valuation_date` as the clock, not `date.today()`. Add to `run_pack`/engine a single `as_of: date` parameter the rules consult.

### M-3 — HTML form submissions get JSON error responses on 4xx/5xx

**Location**: `src/engagement_routes.py:188-209` (`_engagement_errors` decorator emits `jsonify(...)` for every `EngagementError`, `PDFMemoError`, `ValidationError`).

**Repro**: `POST /engagement/<id>/transition?html=1` with stale `expected_version` →

```
Status: 409, Content-Type: application/json
{"current_version":0,"error":"...","error_code":"engagement-version-conflict","expected_version":999}
```

Browser session that submitted the `<form action="?html=1">` from `detail.html:68` lands on a raw-JSON page. HTMX swaps in `_whatif.html`'s target — same problem, JSON gets rendered as text into the swap target.

**Impact**: every concurrency conflict, malformed date, missing-snapshot, redacted-snapshot, rate-limit, or upload-parse error displays raw JSON to a browser user. Severe UX regression on the new HTMX surface. No data integrity issue but it kills the W4.1 HTML UI as soon as anything goes wrong.

**Recommended fix**: in `_engagement_errors.wrapper`, branch on `_wants_html()` and render `engagement/base.html` (or a new `engagement/_error.html`) with the error banner on the 4xx/5xx path.

### M-4 — DCF template's `_build_per_class_fv` leaves a blank row when the first class is excluded

**Location**: `src/dcf_template.py:286-302` — `for i, sc in enumerate(cap_table.share_classes, start=2): if sc.excluded_from_waterfall: continue`.

**Repro**: a cap table whose `share_classes[0]` is `ShareClassType.option_pool_reserved` (excluded via the computed property `excluded_from_waterfall`) produces:

```
Row 1: ['Class','Slug','Share count','% of total','Pro-rata Equity Value','Per-share FV']
Row 2: [None, None, None, None, None, None]   ← blank, but layout claims data here
Row 3: ['Common', 'Common', '=share_count_Common', ...]
```

**Impact**: visual layout broken (blank row in the middle of the per-class table). Any analyst who writes `=SUM('Per-Class FV'!E:E)` is unaffected (None → 0), but a `=COUNTA(...)` or pivot-on-this-range gives wrong row counts. Same cap table → same workbook, so determinism is preserved; this is a layout bug, not a numbers bug.

**Recommended fix**: iterate over `[sc for sc in cap_table.share_classes if not sc.excluded_from_waterfall]` and enumerate that filtered list.

### M-5 — DCF template's cross-workbook references have no external-link path

**Location**: `src/dcf_template.py:294-302` — `=share_count_{slug}` and `=total_fully_diluted` reference names that exist only in the companion sidecar workbook.

**Impact**: when the analyst opens the template workbook alone (or alongside a sidecar with a different filename than expected), Excel displays `#NAME?` for every per-class row. The Read Me sheet warns "Keep both workbooks open in the same Excel session," but openpyxl emits no `[sidecar.xlsx]Cap Inputs!...` external link, so even when both are open Excel typically asks the user to manually resolve the link via "Edit Links → Change Source." Workbook ships in a state where 4 of 6 sheets show errors on first open. Not a determinism break (the bytes are stable); a usability one.

**Recommended fix**: either (a) merge sidecar sheets into the DCF template workbook, (b) emit explicit external workbook references with a documented filename convention, or (c) document the manual re-link step in the Read Me explicitly.

---

## 3. Minors

### m-1 — `_wants_html` is case-sensitive on `Accept`

`src/engagement_routes.py:143` — `accept.startswith("text/html")`. RFC 7231 says media types are case-insensitive. Headers like `Accept: Text/HTML` (uncommon but legal) get JSON. Repro: `Accept='TEXT/HTML, application/json;q=0.9'` → `_wants_html()` returns False. Trivial fix: lowercase the header once before all checks.

### m-2 — `_wants_html` doesn't honour q-value preference, only first-token preference

`src/engagement_routes.py:141-143`. The heuristic "application/json explicit → JSON" only fires when `application/json` appears in `accept.split(",")[0]` — the first comma-separated token. `Accept: text/html;q=0.5, application/json;q=0.9` (JSON strictly preferred) returns HTML because `text/html` is the first token. Browsers don't typically send this so impact is low, but a future API client that follows q-value semantics gets unexpected HTML.

### m-3 — Migration race on multi-process startup

`src/engagement.py:370-378`. Two processes constructing `EngagementStore` simultaneously can both pass the `PRAGMA table_info` check and both try `ALTER TABLE ... ADD COLUMN bound_pack_json`. SQLite serialises schema writes, but the second `ALTER TABLE` errors `duplicate column name`. The whole `__post_init__` then raises and the process dies. Wrap the `ALTER TABLE` in `try/except sqlite3.OperationalError`.

### m-4 — Finding-code collisions across rules are not detected

The rule registry (`src/rule_pack.py:103`) refuses duplicate rule IDs but does not detect when two distinct rules emit `Finding(code=X)` with the same `X`. The engagement-bound blocker-gate (`src/engagement.py:789-793`) computes `blocker_codes - resolved_codes` as a set; resolving one instance of a colliding code silently resolves all. With the v2026.5.0 expansion to 50 rules, the risk surface grows. Currently no two registered rules use the same flat code (verified manually), but no test enforces this. Add a registry self-check at import time, or fuzz over `cap_table` fixtures.

### m-5 — `load_engagement_bound_pack` doesn't validate `pack_version` against the semver regex

`src/rule_pack.py:223-245`. The candidate path `_PACKS_DIR / f"{pack_version}.json"` is constructed directly from `pack_version`. The `_PACK_VERSION_RE` regex exists on the `RulePack` model but is not enforced here. If a `pack_version` ever flows from an untrusted source (currently it does not — `head_pack().version` is the only producer), `pack_version="../../etc/passwd"` would resolve to `rule_packs/../../etc/passwd.json` (no traversal escape because of the `.json` suffix). Defence-in-depth: validate against `_PACK_VERSION_RE` at the top of `load_engagement_bound_pack`.

### m-6 — `/whatif` has no rate limit at all

`src/engagement_routes.py:719-823`. Performs a full waterfall compute per request (more work than a plain JSON read), is gated only by `engagement.read`, doesn't consume the export budget. A read-only auditor or any analyst can spam `/whatif` and burn CPU without tripping any audit alert. Wave-4 introduced no new DOS surface for *exports*, but this is a new compute surface with no governor.

### m-7 — `valuation_date` field validator accepts tz-aware datetimes by silently dropping the timezone

`src/engagement.py:175-178` — `isinstance(v, datetime)` branch returns `v.date()`. `datetime(2026,5,25,23,30,0,tzinfo=SGT)` → date `2026-05-25` because `.date()` returns the naive local date, ignoring the timezone. A client in SGT submitting `2026-05-25T23:30:00+08:00` (which is `2026-05-25T15:30:00Z` UTC) ends up with the *local* May 25, not the UTC date. Not strictly a bug — but per SYSTEM_SPEC §3.2 the date is a calendar date for valuation purposes and the spec doesn't pin which calendar. Worth documenting.

### m-8 — HTMX UI link `Generate memo PDF` has no auth in production

`templates/engagement/detail.html:96` — `<a href="/engagement/{{ engagement.id }}/memo.pdf?reviewer=...">`. The query string has no `?token=`. The test harness uses `current_app.config["TESTING"]` to accept `?token=`, but in production this `<a>` 401s because browsers can't attach `Authorization: Bearer` to a plain link. The HTMX UI is effectively unusable in production without a session-cookie auth layer. Wave-4 shipped the UI without that layer. Document as a known gap or add a cookie-bridging auth provider.

### m-9 — `_build_terminal_value` defined name `pv_terminal_value` points to row 6, but the formula chain is correct only when rows aren't reordered

Already verified correct in current code (row 2..6 in deterministic order). But the code couples the named-range cell ref to a row index hardcoded as `6`. If anyone later inserts a row between FCFF-Y5 and PV-of-TV without updating the `DefinedName(..., attr_text=_full_range_ref(..., 6, 2))` line, the named range silently points to a wrong cell. Make the row index a single constant per sheet.

### m-10 — `excluded_from_waterfall` check in DCF template re-derives instead of reading from CapTable model

`src/dcf_template.py:288` uses the computed property — fine. But `src/dcf_sidecar.py:106` also reads it for `total_fully_diluted`. Consistent here. Note for symmetry, not a bug.

---

## 4. Cross-module contract table

| Caller | Callee | Contract | Status |
|---|---|---|---|
| `engagement_routes.memo` | `load_engagement_bound_pack(eng.pack_version)` | Bound pack must be sticky and identical to what bundle ships | **BROKEN** (B-2): memo uses disk; bundle uses `bound_pack_json` |
| `engagement_routes.bundle` | `build_engagement_bundle` → prefers `eng.bound_pack_json`, falls back to disk | Bundle ships self-contained pack | OK |
| `engagement.create_engagement` | `load_engagement_bound_pack` then stores `bound_pack_json` | Pack JSON bytes pinned at create time | OK (validated: 403 bytes stored for v2026.1.0) |
| `engagement.transition` (review→signed) | `_enforce_blockers_resolved` → `load_engagement_bound_pack` | Blocker-gate uses bound pack | OK (disk path; if pack missing, refuses transition with clear error) |
| `dcf_template._build_per_class_fv` | `dcf_sidecar` defined names (`share_count_<slug>`, `total_fully_diluted`) | Cross-workbook external references | FRAGILE (M-5): no `[sidecar.xlsx]` external link; analyst must manually re-link |
| `dcf_template` + `dcf_sidecar` | `_slug_for_defined_name` | Each class name → unique slug | **BROKEN** (M-1): `Series A` and `Series-A` collide silently |
| `engagement.add_snapshot`/`transition` | `_write_lock` + atomic conditional UPDATE | Optimistic-concurrency safe | OK (B2 fix from W2 holds) |
| `engagement_routes.transition` | `_engagement_errors` | Spec error codes wrap to HTTP | OK on JSON path, **BROKEN** (M-3) on HTML path |
| `engagement_routes.whatif` | `compute_waterfall` (read-only) | No state mutation, no version check needed | OK |
| `engagement_routes.create_engagement` | Pydantic `valuation_date` validator | Reject malformed strings, accept ISO dates and `date` objects | OK going forward; **BROKEN** (B-1) for legacy rows |
| `rate_limit.consume` | `engagement_routes._enforce_export_limit` | Edge-trigger hard-alert once at boundary | OK (M2 fix from W3 holds) |
| `rate_limit` | `/whatif` | None — whatif intentionally not metered | OK design; m-6 notes the DOS surface |

---

## 5. Determinism review

| Surface | Repeatable bit-for-bit (modulo carve-out)? | Notes |
|---|---|---|
| Same engagement → same memo bytes | **NO** (M-2): clock-based rules fire/don't fire as days pass. Also B-2 if disk pack mutated. | §8.10 carves out cover-sheet timestamp; does NOT carve out finding set. |
| Same engagement → same bundle bytes (modulo `manifest.generated_at`) | **NO** (same M-2 root cause flows into the audit log → into bundle). Disk-pack-mutated case (B-2) does NOT affect bundle because bundle uses `bound_pack_json` first. | Bundle preserves stable pack source, but findings re-run on demand inherit M-2. |
| Same cap table → same DCF template bytes | YES (verified: two `build_dcf_template_bytes(ct)` calls produce 9942 identical bytes). | Layout breakage (M-4) is stable across runs. |
| Same cap table → same DCF sidecar bytes | YES (verified: two calls produce 6689 identical bytes). | Slug collision (M-1) is also stable — silently wrong, but deterministically so. |
| HTMX detail-page render | YES (verified: two `GET /engagement/<id>?html=1` produce byte-identical HTML, len 6310). | No random IDs, no timestamps in the template. |
| HTMX list-page render | YES by inspection (template references `e.created_at` indirectly only via the data rows; pagination params are deterministic for a given query). | — |
| HTMX `_whatif.html` render | YES — depends only on `cap_table` + form-encoded overrides. | — |

**Net**: HTMX renders and DCF byte outputs are byte-stable. The cross-cutting determinism break is M-2 (clock-based rules) — it silently corrupts the SPEC §8.10 finding-list invariant. B-2 corrupts the cross-artefact agreement between memo and bundle.

---

## 6. Spec drift (since round 2)

### SD-1 — DCF template violates §5.3 refusal contract

`SYSTEM_SPEC.md:987-990`:

> Refusal:
> - The tool does NOT produce a DCF.
> - The tool does NOT compute WACC, terminal value, or projection horizon.
> - The tool does NOT source comps.

`src/dcf_template.py` produces a full 6-sheet workbook with WACC, terminal value (Gordon-growth), 5-year projection, equity bridge, and per-class FV allocation. Yes, the "judgment" cells are yellow analyst inputs with defaults the analyst is told to overwrite — but the structure IS a DCF. The spec hard-refuses this artefact.

Either the spec needs an amendment (§5.3 carves out "template-shaped DCF scaffolding where every judgment input is yellow and explicitly analyst-sourced"), or W4.3 must be reverted to sidecar-only (which is what §5.3 currently sanctions).

Note also `templates/engagement/detail.html:88` markets the panel as "(Form fields would be generated per preferred class once snapshot data is wired into this view in wave 5.)" — so the UI hook is partial and spec drift is documented as a known stub in the code itself.

### SD-2 — `/whatif` endpoint URL diverges from spec

`SYSTEM_SPEC.md:426`:

> | POST | `/whatif/<token>` | form: overrides for shares / LP mult | … |

Implementation: `POST /engagement/<id>/whatif` (engagement-scoped under the engagement blueprint, no `<token>` segment). Behaviour is correct (HTMX scenarios panel); URL is renamed. Either spec or impl needs an alignment edit. Functionally identical from the auditor's perspective.

### SD-3 — `bound_pack_json` column not in §3.2 schema documentation

The W4.2 column (`engagement.bound_pack_json`) is implemented and migrated cleanly, but `SYSTEM_SPEC.md` §3.2 (engagement schema) and §9 (round 2 amendments) don't enumerate the new column. SPEC §9.2 talks about the engagement-bound pack contract but in terms of pack_version + `load_engagement_bound_pack`, not bytes-at-bind. Add a §9.X amendment documenting the pinned-bytes column and the bundle-prefers-bytes / memo-uses-disk asymmetry (or fix B-2 and document the unified path).

### SD-4 — HTMX UI auth model is undocumented

Wave 4 introduced a HTML render surface. SPEC §3.2 documents Bearer tokens (production) and magic-link tokens (read-only auditors). It does not document how a browser-based HTMX UI authenticates. Currently it requires `TESTING=True` + `?token=...` query string — i.e., the HTMX UI is test-only by construction. Either document this constraint, or add a session-cookie auth provider (out of scope here; flag as known limitation).

---

## 7. Things checked CLEAN

- **HTMX templates use Jinja2 autoescape**: verified for `engagement/_whatif.html` and `engagement/list.html` (`app.jinja_env.autoescape(name)` returns True for both). Templates also belt-and-braces with explicit `| e` on `client_id`, `display_name`, `event`, `c` (changed rows).
- **XSS via `client_id`**: `POST /engagement/?client_id=Acme<script>alert(1)</script>` then GET `/engagement/?html=1&q=Acme<...>` — script tag escaped in both row data and `value="..."` attribute.
- **`/whatif` on engagement with no head snapshot**: returns 200 with empty-state partial (verified). Clean. No 500.
- **DCF template + sidecar are byte-deterministic** across two builds with the same cap table.
- **HTMX detail page is byte-deterministic** across two GETs.
- **Hash chain unchanged by `bound_pack_json` column**: `_canonical_payload` does not include the new column. Pre-W4.2 audit chains remain verifiable.
- **Pre-W4.2 engagement rows (NULL `bound_pack_json`)**: `_row_to_engagement` reads `None`; `build_engagement_bundle` falls back to disk lookup successfully; verified.
- **Bundle resilience to corrupted `bound_pack_json`**: setting the column to `'not valid json'` then calling `build_engagement_bundle` — bundle succeeds, falls back to disk, ships `rule_pack.json` correctly. (`engagement_bundle.py:79-86` wraps `RulePack.model_validate_json` in try/except.)
- **`engagement.create_engagement` rejects unknown pack version**: `pack_version='vfake.fake.fake'` raises `EngagementError("cannot create engagement bound to ...")`. No half-created engagement row.
- **`_slug_for_defined_name` blocks formula injection**: `=R[1]C[1]` → `_R_1_C_1_`. Reserved tokens (`C`, `R`, `TRUE`, `FALSE`) prefixed with underscore. Leading digit handled.
- **Rule registry has no duplicate IDs** at 50 rules (verified: `Counter(registered_rule_ids()).most_common(1) → ('G-AD-001', 1)`).
- **Pack JSON `rule_ids` list matches registered rules**: 50 = 50.
- **`load_engagement_bound_pack("v0.0.0-dev")` refuses unless `QAPITA_ALLOW_DEV_PACK=1`**: validated.
- **Pack-version regex blocks path traversal at the model layer**: `RulePack.version` Field has `pattern=_PACK_VERSION_RE`; constructor raises. Note: enforcement is at the *model* boundary, not at the `load_engagement_bound_pack` call site — see m-5 for the defence-in-depth gap.
- **`/whatif` form parsing handles negative / `nan` / `inf` shares gracefully**: `int(float(raw))` raises ValueError on `"nan"`, caught; `n >= 0` check filters negatives.
- **Optimistic concurrency on `/whatif` is non-issue**: endpoint is read-only, no version reservation needed.

---

## 8. Fix-now vs defer

### Fix now (before wave 5)
- **B-1** (valuation_date validator breaks legacy rows): one-shot migration + `_row_to_engagement` graceful degradation. Without this, any production deployment with pre-W4.5 rows breaks engagement reads on first cold start.
- **B-2** (memo vs bundle pack divergence): trivial fix — memo route uses the same `bound_pack_json`-first helper as bundle. Five-line patch.
- **M-2** (clock-based rules break §8.10 determinism): plumb `as_of` date through `run_pack` and use `cap_table.company.valuation_date` (already passed through). Surfaces in every memo / bundle / audit-log run.
- **M-3** (JSON errors on HTML form path): wrap `_engagement_errors` with a `_wants_html()` branch. Otherwise the HTMX UI is unusably brittle.

### Defer (with tracking)
- **M-1** (slug collision): defer until a cap table with colliding class names actually arrives. Add registry self-check that warns on slug collision at sidecar build time.
- **M-4** (DCF blank row): cosmetic; defer.
- **M-5** (cross-workbook external links): UX-only; defer with a Read Me update spelling out the manual re-link step.
- **SD-1** (DCF spec refusal violation): MUST be resolved at the spec/policy level before W4.3 ships externally to a Big-4 reviewer. Either amend §5.3 or rip out `dcf_template.py`.
- **SD-2** (`/whatif/<token>` URL drift): one-line spec edit or one-line route alias. Defer.
- **SD-3** (`bound_pack_json` undocumented): spec edit, defer.
- **SD-4** (HTMX auth model): defer — known production gap, no current users.

### Watch list (no-action, instrument)
- m-1, m-2 (`_wants_html` semantics): unlikely to bite real clients; add a regression test if a future ticket touches content negotiation.
- m-3 (multi-process migration race): add a try/except, defer rest.
- m-4 (finding-code collision detection): registry-time self-check, defer wider audit.
- m-5 (`load_engagement_bound_pack` validation): add a one-line regex check, defer.
- m-6 (`/whatif` DOS surface): instrument with logs first, decide on rate-limit later.
- m-7 (tz-aware datetime → naive date): document in the validator docstring, defer.
- m-8 (HTMX prod auth): tracked under SD-4.
- m-9 (DCF row-index hardcoding): defer until DCF template changes.

### Rule-pack timing observation (no action required)
Today's date is 2026-05-25, but rule pack `v2026.5.0` (the 50-rule pack containing the new 13 W4.4 rules) has `effective_from: 2027-03-01`. Every engagement created today binds to `v2026.1.0` (8 rules); the new W4.4 rules will not fire on any engagement opened before 2027-03-01. This is correct per the §4.1 binding model but means W4.4's coverage gain is invisible to production until 2027. If that timing is unintentional, edit `rule_packs/v2026.5.0.json` `effective_from`. Not a bug.
