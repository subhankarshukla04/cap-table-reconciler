# Wave 3 Code Audit

## 0. Stance

Auditor: independent reviewer, not the builder. Audit scope: the seven
W3.x deltas listed in the brief, against `SYSTEM_SPEC.md` §3.2 / §4.1 /
§5.1 / §5.3 / §7 / §8.10 / §8.16.

Headline: shipping is acceptable with two **Blocker**-class fixes
landed first — the W3.4 vol-pack ignores §5.1 numeric bounds (lets the
analyst feed -50% vol into OPM), and W3.6 finding codes never appear
in the PDF memo's provenance appendix (regex contract broken; this
also breaks the pre-existing W2.5 rules, but W3.6 ships 7 more rules
into the same hole, so the deliverable is materially worse). Several
**Majors** around determinism, tenancy leakage in the new list route,
and a misclassified-/noisy- diff stream into the new subsequent-events
section. The rest is **Minor** polish.

523-test baseline is preserved; none of these are caught by tests.

---

## 1. Blockers

### B1. `read_vol_pack` accepts numeric values outside SYSTEM_SPEC §5.1 bounds
**File:** `src/opm/vol_pack.py:166-211`
**Spec contract:** §5.1 — `volatility ∈ [0,2]`, `time_to_liquidity > 0`,
`risk_free_rate ∈ [-0.05, 0.20]`, `dlom ∈ [0, 0.50]`.
**Observed:** the readback only checks "present" and "is numeric". No
range enforcement. A pack with `volatility=-0.5, time_to_liquidity=0,
risk_free_rate=5.0, dlom=10.0` returns `is_valid=True` and a fully
populated `MarketInputs`. Downstream `bsm_call_value` happily computes
on garbage; the OPM Backsolve refusal contract (§5.1, "Never computes
its own volatility... Both are required inputs sourced by the analyst")
is preserved in spirit only — the analyst can source an invalid input
and the tool does not refuse.
**Repro:**
```
.venv/bin/python -c "
from src.opm.vol_pack import build_vol_pack_template, read_vol_pack
from io import BytesIO
wb = build_vol_pack_template(); ws = wb['Market Inputs']
fill = {'vol_peer_tickers':'AAPL','vol_window_months':'12','vol_citation':'X',
        'time_basis':'PWERM','rfr_source':'T','dlom_basis':'F',
        'volatility':-0.5,'time_to_liquidity_years':0,'risk_free_rate':5.0,'dlom':10.0}
for r in range(1,200):
    s = ws.cell(row=r,column=4).value
    if s in fill: ws.cell(row=r,column=2,value=fill[s])
buf=BytesIO(); wb.save(buf); buf.seek(0)
print(read_vol_pack(buf).is_valid, read_vol_pack(buf).market)"
# True MarketInputs(volatility=-0.5,...,dlom=10.0)
```
**Fix-now:** add a `_validate_bounds()` step inside `read_vol_pack`
that appends to `missing_required` (rename to `invalid` or
`refusals`) when any numeric is out of its §5.1 band. The vol-pack
module's whole purpose is "the tool surfaces them, the analyst defends
them" (module docstring lines 9-13). Without bounds, the analyst can
defend nonsense and the tool blesses it.

### B2. New W3.6 rule findings vanish from the PDF provenance appendix
**File:** `src/pdf_memo.py:236-248` (regex) ↔ `src/rules_v2026_4.py`
(finding codes).
**Spec contract:** §6.2 "every finding cites the field/cell it came
from" and §1.8 audit-memo provenance contract — provenance appendix
must enumerate every rule that fired.
**Observed:** the provenance loop extracts the rule id from
`Finding.code` via regex `^(G-[A-Z]+-\\d+)`. Every W3.6 rule emits a
code with a **different prefix** than its rule id:

| Rule id | Finding code emitted |
|---|---|
| `G-PP-001` | `PP-EMPTY` |
| `G-PP-002` | `PP-SUPERMAJORITY-{name}` |
| `G-PP-003` | `PP-NO-CONSENTER-{name}` |
| `G-ROFR-002` | `ROFR-SHORT-NOTICE` |
| `G-DRAG-002` | `DRAG-THRESHOLD-ATYPICAL` |
| `G-DRAG-003` | `DRAG-CLASSES-EMPTY` |
| `G-XREF-001` | `XREF-DRAG-NO-ROFR` |

None match `^G-[A-Z]+-\\d+`. The provenance regex `m = re.match(...)`
returns None → `continue` → seven new rules silently absent from the
PDF appendix. (Pre-existing W2.5 rules — `NVCA-PP-MISSING`,
`AICPA-DLOM-REMINDER`, `DRAG-{sl.id}`, `ROFR-NOTICE-{sl.id}` — have
the same hole.)
**Repro:**
```
.venv/bin/python -c "
import src.checklist, src.rules_v2026_2, src.rules_v2026_3, src.rules_v2026_4
from src.models import *
from src.rule_pack import run_pack, load_pack_from_file
pack = load_pack_from_file('rule_packs/v2026.4.0.json')
ct = CapTable(company=Company(name='X',currency='USD'),
  share_classes=[ShareClass(name='C',type=ShareClassType.common,shares_outstanding=100),
                 ShareClass(name='A',type=ShareClassType.preferred,shares_outstanding=10,seniority_rank=1,
                            liquidation_preference=LiquidationPreference(multiple=1.0,amount=1.0,type=LPType.non_participating),
                            anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average))],
  drag_along_terms=DragAlongTerms(threshold_pct=99.0,drag_classes=['A']),
  protective_provisions=[ProtectiveProvision(name='amend',consent_threshold_pct=80.0,consenting_class_names=['A'])])
import re
for f in run_pack(ct,pack=pack):
    print(f.code, '->', bool(re.match(r'^(G-[A-Z]+-\\d+)', f.code)))"
# All False except none.
```
**Fix-now:** the durable fix is to store the source rule id on the
`Finding` itself (a new optional `rule_id: Optional[str] = None`
field) and populate it in every `@rule`-decorated function; the
provenance loop reads `f.rule_id` directly. The cheap fix is to look
up via category match against `rule_metadata` (since every W3.6 rule's
`category` is unique per rule id), but that's a band-aid that will
break the moment two rules share a category. Either way, this is a
**memo-content correctness regression** and the PDF audit trail Big-4
acceptance criterion (§3.4) is materially weakened — and it lands in
the wave that explicitly promises §6.2 traceability.

---

## 2. Majors

### M1. Cross-tenancy leak in the new `GET /engagement/` list route
**File:** `src/engagement_routes.py:203-264`
**Spec contract:** §3.2 `reviewer` "All analyst permissions on
engagements **assigned to them as reviewer**"; `partner` "engagements
**they sponsor**." `analyst` "May NOT read other analysts' engagements"
(strictly enforced via `e.created_by == user.id` at line 227 — good).
**Observed:** the analyst branch is correct. The `read_only_auditor`
branch correctly returns `[]`. **Both `reviewer` and `partner` fall
through every filter and see every engagement in the database**, with
no assignment-table check. Pre-W3.2 there was no engagement list
route, so this gap had no exposure surface. W3.2 ships the exposure
surface without the gate. The brief explicitly calls this out as an
audit target.
**Risk:** any reviewer or partner can `GET /engagement/?q=secret-
client` and enumerate every other team's pipeline. GAP-39 (engagement-
level tenancy ACL) is described in `audit_log` (line 535-541) as
"deferred to a later wave" — fine for detail routes pre-W3.2, but the
list route is now the easiest way to **discover engagement ids** to
hit those detail routes. W3.2 should at minimum have stub-filtered
reviewer/partner to `created_by == user.id` (the same conservative
filter analyst uses) until the assignment table lands.
**Fix-now:** mirror the analyst filter for reviewer + partner until
GAP-39 ships:
```python
if user.role in (Role.analyst, Role.reviewer, Role.partner):
    engagements = [e for e in engagements if e.created_by == user.id]
```
Yes, this temporarily makes reviewer/partner only see engagements they
*created*, not engagements assigned to them. That is the conservative
choice — the spec says they should NOT see arbitrary engagements, and
"engagements they created" is a strict subset of "engagements
assigned to them." Document and tag as GAP-39.

### M2. Subsequent-events diff produces noise + misclassified events for the new structured fields
**File:** `src/subsequent_events.py:46-72` (`_classify`) ↔
`src/structured_diff.py:66-89` (`_walk`).
**Spec contract:** §4.4 — diff feeds the subsequent-events section
"automatically"; the field paths should map to memo bullet categories
deterministically.
**Observed:** when an engagement transitions from a CapTable that
omits the new structured fields (`protective_provisions=[]`,
`rofr_terms=None`, `drag_along_terms=None`) to one that populates
them — exactly the common W3.6 workflow — the diff stream contains
two pathological shapes:

1. **Phantom "removed" event for None→subtree transitions**:
   ```
   removed drag_along_terms <-> None -> None
   ```
   LHS `drag_along_terms=None` flattens to a single `(path, None)`
   pair; RHS flattens to nested subpaths only, so `drag_along_terms`
   key itself appears in LHS but not RHS → reported as
   `change_type=removed, old_value=None, new_value=None`. The
   description function (`_describe` line 78) renders this as
   `"Removed: drag_along_terms (was None)"` — false; it was NOT
   removed.

2. **Noise "added X = None" rows** for every optional sub-field that
   the analyst left unset on the new side (e.g. `added
   drag_along_terms.minimum_consideration_per_share = None`,
   `added drag_along_terms.notes = None`, `added
   protective_provisions[amend].description = None`). These are not
   changes; they are the consequence of flattening Pydantic optionals.

Then `_classify` doesn't recognise any of `drag_along_terms.*`,
`rofr_terms.*`, or `protective_provisions[*].*` paths → all fall into
the **"Other"** bucket. The W3.6 deliverable that is supposed to
power the GAP-14 closure surface is buried under "Other" rather than
its intended structural categories.

**Repro:** see the diff transcript in §0 of this audit's notes;
reproduced via `diff_snapshots(a, b)` with `a` lacking and `b`
populating the new fields.

**Fix-now:**
- Suppress emit of `added X = None` (treat None values as "field
  absent" in `_walk`, OR filter `(change_type='added' and new_value
  is None)` in `subsequent_events.compute_subsequent_events`).
- Suppress the phantom `removed X <-> None -> None` event by
  skipping LHS scalars whose value is None when RHS has nested
  expansion of the same prefix.
- Extend `_classify` with three new buckets: `protective_provisions
  → "Protective provisions"`, `rofr_terms → "ROFR / ROFO"`,
  `drag_along_terms → "Drag-along"`. Otherwise W3.6 invisibly
  defeats W3.1's grouping promise.

### M3. Subsequent-events ordering is non-deterministic when timestamps tie
**File:** `src/engagement.py:540, 612` (no tiebreaker on `ORDER BY
created_at` / `ORDER BY resolved_at`); `src/subsequent_events.py:115-
117` (iterates snapshots in that order, then resolutions in that
order).
**Spec contract:** §8.10 — PDF audit memo is bit-for-bit deterministic
except for cover-sheet timestamp + PDF metadata. The subsequent-
events section is body content, so it MUST be deterministic.
**Observed:** SQLite returns rows in unspecified order on ties. ISO
timestamps with microsecond precision tie rarely, but the engagement
store creates snapshots + audit events in tight bursts (e.g., create
engagement → upload → resolve all within one HTTP turn) and on
machines without a high-resolution monotonic clock (some Docker
hosts), microsecond ties happen.
**Fix-now:** add `, id` as tiebreaker to both
`ORDER BY created_at, id` (line 540) and `ORDER BY resolved_at, id`
(line 612). The audit_event query at line 793 already does this
(`ORDER BY ts, id`) — same fix, two more places.

### M4. Snapshot Stamp sheet timestamp breaks payload-level determinism of the live-formula workbook
**File:** `src/formula_workbook.py:1037-1057`
**Spec contract:** §8.10 row "Live-formula `.xlsx` export: cell-
value-and-formula determinism; zip metadata not guaranteed." The
Snapshot Stamp sheet is **cell-value payload**, not zip metadata.
**Observed:** when caller does NOT pre-compute `generated_at`, every
call writes `datetime.now(timezone.utc).isoformat()` into cell B7. Two
calls one second apart produce different cell payloads → §8.10
determinism contract violated on the cell-value axis (not just the
metadata axis).
**Fix-now:** either (a) require `generated_at` in the
`snapshot_stamp` dict and raise if absent, or (b) default it to the
snapshot's own `snapshot.created_at` (passed in by the caller). Don't
silently call `datetime.now()`.

---

## 3. Minors

### m1. `compute_subsequent_events` reads engagement but never uses it
**File:** `src/subsequent_events.py:95` — `eng = store.get_engagement(
engagement_id)` is assigned and discarded. The call DOES serve a
purpose (raises `EngagementNotFound` if missing), but the dead
binding is misleading. Either drop the assignment or pivot the engagement
metadata into the rollup (e.g. so the memo can surface
`eng.pack_version` next to "Subsequent Events").

### m2. `_rule_pp_supermajority` threshold compared as `> 66.67` — misses common 2/3 entries
**File:** `src/rules_v2026_4.py:58`. Two-thirds = 66.666...%. An
analyst typing `66.67` triggers (correct). An analyst typing `66.66`
does NOT trigger (wrong direction). Worse, an analyst typing `66.6`
(the more common shorthand) is silently below the band. Use
`>= 66.67` and lower the bar to `>= 65.0` if you want to catch the
shorthand cases; or compare against `2/3 + tolerance` instead of a
hard-coded `66.67`.

### m3. Duplicate Finding.code possible for protective provisions with duplicate names
**File:** `src/rules_v2026_4.py:61, 88` — `code=f"PP-SUPERMAJORITY-
{pp.name}"`. `CapTable.protective_provisions` does not enforce
unique `name` (no model validator). Two PPs both named `amend_charter`
produce two `PP-SUPERMAJORITY-amend_charter` Findings, which the memo
renders as two rows with identical code. Fix in `models.py`:
```python
@model_validator(mode='after')
def pp_names_unique(self): ...
```

### m4. `list_engagements` date_from / date_to silently accept malformed input
**File:** `src/engagement_routes.py:239-248`. `date_from=zzzz` filters
out every engagement; `date_from=2026` (no day) partially matches by
lexical string compare. No 400 returned. Per §3.2 the API surface
should be predictable; add a `try: date.fromisoformat(...)` validation
and 400 with `error_code=bad-date` on parse failure.

### m5. `engagement.id[:8]` in CSS `@top-right { content: "..." }` is unescaped
**File:** `templates/memo/base.html:11`. Engagement id is a UUID
(safe), but the `company.name` on line 10 is interpolated into the
same CSS string-literal context without CSS-string escaping. Jinja
autoescape only HTML-entity-encodes `"`; inside `<style>` HTML5 parsers
do NOT decode entities, so a name with a `"` in it shows literally as
`&#34;` in the header (cosmetic) but cannot actually break out of the
CSS string. **Not exploitable today**, but if a future parser (or
WeasyPrint upgrade) decodes entities in `<style>` blocks, this becomes
a real injection. Defence in depth: pre-escape with a custom
`|css_string` filter that replaces `"` with `\\22`, `\\` with `\\5c`.

### m6. Subsequent-events resolutions block omits `decision_summary`
**File:** `templates/memo/base.html:184-202` renders only
finding_code, citation, resolved_by, resolved_at. The main
"Resolutions applied" section (lines 120-135) renders
`decision_summary` too. Inconsistency: the historical block hides the
substance of what was decided — useless for a reviewer scanning the
subsequent-events appendix. Add `<td>{{ r.decision_json | e }}</td>`
column (or run it through a `_summarise_decision()` helper).

### m7. `_enforce_export_limit` duplicates `RateLimitResult.triggered_hard_alert`
**File:** `src/engagement_routes.py:111` — re-computes `rl.current_count
== rl.hard_limit` instead of reading `rl.triggered_hard_alert` (which
exists for exactly this reason at `rate_limit.py:114`). Functionally
identical today; risk is future drift if the rate-limiter changes its
edge-trigger definition (e.g. to fire ONCE per user-lifetime instead
of once per hour). Use the canonical flag.

### m8. Vol-pack template stored slug in column D is the schema; analyst can edit it and silently break readback
**File:** `src/opm/vol_pack.py:107, 122` writes the field slug into
column D as the lookup key for `read_vol_pack`. An analyst opening
the workbook and "tidying" by deleting column D (looks redundant —
the label is in column A) breaks the readback, which then returns
"missing required" for fields the analyst DID populate. At minimum
mark column D `hidden=True` via
`ws.column_dimensions['D'].hidden = True`; better, define openpyxl
DefinedName / Named Ranges and read by name instead of by adjacent-
column convention.

---

## 4. Spec drift table

| Spec § | Promise | W3 reality | Severity |
|---|---|---|---|
| §3.2 | "reviewer assigned to them" / "partner sponsors" | reviewer + partner see ALL engagements via new list route | M1 |
| §4.4 | diff feeds subsequent-events automatically; categorised | W3.6's new fields all bucket under "Other" + emit phantom None events | M2 |
| §5.1 | vol ∈ [0,2], time>0, rfr ∈ [-0.05,0.20], dlom ∈ [0,0.50] | `read_vol_pack` enforces only "numeric"; accepts -0.5, 0, 5.0, 10.0 | B1 |
| §5.3 | DCF sidecar is sidecar; tool does NOT compute WACC etc. | W3.5 is in scope; no drift here. Note Snapshot Stamp sheet leaks engagement_id (UUID) as cell value — not PII but a tenancy hint | (note) |
| §6.2 | every finding cites field/rule | new W3.6 findings missing from PDF provenance appendix | B2 |
| §7 #9 | "no volatility peer-set engine" | W3.4 honours the refusal; module is template-only. CLEAN | ✓ |
| §8.10 | live-formula workbook deterministic on cell payload | Snapshot Stamp sheet writes `datetime.now()` when caller omits stamp | M4 |
| §8.10 | PDF memo deterministic except cover timestamp | subsequent-events body ordering can tie on `created_at` / `resolved_at` | M3 |
| §8.16 | escaping in WeasyPrint, CSS-safe | jinja autoescape works in HTML body; CSS string interpolation safe today, brittle | m5 |
| §8.17 | every export route rate-limited per user | memo route rate-limits AFTER permission gate (correct, m3 fix from W2). vol-pack has no HTTP route. CLEAN | ✓ |

---

## 5. Resource / perf

- `read_vol_pack` calls `load_workbook(path, data_only=True)` with no
  upload-size cap. A 5 GiB crafted `.xlsx` is loadable by openpyxl
  (it'll OOM the process). Caller — currently programmatic only — must
  bound. If a route is later added (`POST /opm/vol-pack`), add the
  same `MAX_CONTENT_LENGTH` Flask config the upload route relies on
  implicitly. **Track as deferred.**
- `_cell_value` (vol_pack.py:157) does a linear scan of 200 rows per
  field, 12 fields → 2,400 cell reads per readback. Trivial.
- `compute_subsequent_events` calls `list_resolutions` per snapshot;
  N snapshots × M resolutions = N DB round-trips. Fine for current
  scale (< 100 snapshots/engagement), but if an engagement grows to
  thousands of snapshots (Phase 4 platform-play), single-query SELECT
  joining snapshot → resolution beats this. Defer to a real bottleneck.
- `diff_snapshots` is O((n_left_paths + n_right_paths) log(...)) due to
  sorting in `_walk`. For two 50-class cap tables with W3.6 structured
  fields the path count is ~600 each. Well under §4.4's 500 ms SLO.

---

## 6. Security

- **List-filter injection (`q`, `client_id`, `status`,
  `standard_of_value`, `date_from`, `date_to`)**: all of these flow
  into the `list_engagements(client_id=...)` SQLite parameter-binding
  call (line 223) or into pure-Python `in` / `==` filters (lines 232-
  255). No SQL string concatenation. Safe. ✓
- **Pack-version pattern bypass**: `RulePack.version` uses
  `_PACK_VERSION_RE = "^v\\d+\\.\\d+\\.\\d+(?:-[A-Za-z0-9.\\-]+)?$"`
  (`rule_pack.py:46`) and a defence-in-depth `_no_path_traversal_in_
  version` validator. `v2026.4.0` passes; no W3 surface bypasses the
  regex. ✓
- **XSS in subsequent-events memo section**: every dynamic field uses
  `| e` jinja escape. `r.resolved_at.isoformat()` is unescaped but
  isoformat output is ASCII-safe. Snapshot ids are UUIDs. ✓
- **XSS in cover-sheet CSS context**: see m5 — not exploitable today,
  brittle.
- **Pagination integer-overflow**: `int("999999999999999999")`
  succeeds; `min(..., 200)` caps `limit`; `max(0, ...)` floors
  `offset`; Python slice on huge offset returns `[]`. Safe. ✓
- **Auth on list route**: `_auth_guard` runs before every route via
  `bp.before_request` (line 173-175). The list route does not call
  `can(user, 'engagement.read')` explicitly — all four roles have the
  permission anyway, so functionally fine. But the absence is a
  pattern-break vs detail routes that DO call `can`; the next added
  role with no `engagement.read` (e.g. a hypothetical `finance` role)
  would see the list without any code change here. Add the explicit
  gate for consistency. **Minor pattern issue, not a vuln.**
- **Snapshot Stamp leaks `engagement_id` and `snapshot_id` as
  unhidden values when a user un-hides the sheet** (openpyxl
  `sheet_state='hidden'` is one-click reversible in Excel). UUIDs
  alone aren't PII, but combined with an exported workbook shared
  externally they're a tenancy beacon. Defer. **Document, do not
  fix.**

---

## 7. Things checked CLEAN

- Backward-compat for old CapTable JSON: the new `protective_provisions
  = []` / `rofr_terms = None` / `drag_along_terms = None` defaults
  validate against old payloads that omit the fields. Verified via
  `CapTable.model_validate` on a stripped fixture. ✓
- `extra="forbid"` discipline preserved on all new models
  (`ProtectiveProvision`, `ROFRTerms`, `DragAlongTerms`). ✓
- v2026.4.0 pack registers all 37 rule_ids in the registry. No META-
  RULE-MISSING surfaced. ✓
- Snapshot-supersession invariant: `add_snapshot` still holds the
  write lock across version check + UPDATE + INSERT + supersede; W3
  did not touch this code path. ✓
- Audit-log append-only invariant: W3.5 snapshot stamp does NOT touch
  `audit_event` rows. ✓
- W3.4 honours §7 #9 explicitly in module docstring (lines 15-21);
  no peer-set computation, no LLM, no fabrication path. ✓
- Memo route's M3-fix ordering preserved: permission check (line
  457) BEFORE export-rate consumption (line 463). ✓
- W3.6 rules correctly guard on `cap_table.protective_provisions` /
  `rofr_terms` / `drag_along_terms` being empty/None — no
  AttributeError on legacy CapTables. ✓

---

## 8. Fix-now vs defer table

| Id | Title | Fix-now | Defer | Notes |
|---|---|---|---|---|
| B1 | vol_pack bounds | ✓ |  | Spec contract; analyst defensibility hole |
| B2 | provenance regex misses W3.6 finding codes | ✓ |  | Memo Big-4 acceptance regression |
| M1 | list-route reviewer/partner tenancy leak | ✓ |  | New exposure surface this wave |
| M2 | subsequent-events noise + misclassification | ✓ |  | Defeats W3.6 + W3.1 jointly |
| M3 | subsequent-events ordering ties | ✓ |  | One-line SQL fix; §8.10 contract |
| M4 | formula_workbook stamp `datetime.now()` |  | ✓ | Caller-controlled; document |
| m1 | `eng` assigned and unused |  | ✓ | Cosmetic |
| m2 | `> 66.67` threshold |  | ✓ | Tune in next pack version |
| m3 | duplicate PP name → duplicate Finding code |  | ✓ | Add model validator next time |
| m4 | date filters accept garbage |  | ✓ | UX polish |
| m5 | CSS string interpolation brittle |  | ✓ | Not exploitable today |
| m6 | historical-resolutions block missing decision col |  | ✓ | Cosmetic |
| m7 | `_enforce_export_limit` duplicates flag |  | ✓ | Drift risk only |
| m8 | column D slug editable by analyst |  | ✓ | Make column hidden when fixing B1 |

Recommended sequence: land B1, B2, M1 in one fix-PR (each is a
self-contained change ≤ 30 LOC); land M2 + M3 in a second PR (they
touch the same modules); defer the rest to a quality-pass at the end
of Phase 3.

---

End of W3 audit. Hand back to builder for fix-then-test.
