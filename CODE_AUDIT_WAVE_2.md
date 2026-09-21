# Wave 2 Code Audit

## 0. Stance + methodology

Independent read of the seven Wave-2 modules + the modules they build on
(`src/engagement.py`, `src/identity.py`, `src/pdf_memo.py`,
`src/rule_pack.py`), the modified portions of `app.py`, `src/diff.py`,
`src/pdf_intake.py`, and the spec amendments in `SYSTEM_SPEC.md` §§3.2,
4.3, 8.5, 8.10, 8.12, 8.14, 8.16, 8.17. Tests, BUG_REPORT, CODE_AUDIT,
VERIFICATION_MATRIX, and PRODUCTION_ROADMAP were intentionally NOT read
to avoid anchoring on what Wave 1 / the original author already
catalogued.

Reproductions were run from `/Users/subhankarshukla/Desktop/claude code/qapita`
using `.venv/bin/python` on a temp DB; commands inline below.

Stance: this is a hardening audit. No feature suggestions. Every finding
is either a real defect (wrong output / silent failure / contract
violation) or measurable spec drift. Severities use the wave's existing
ladder: **Blocker** (data integrity, auth bypass, audit-evidence break),
**Major** (wrong-output edge case, missing spec refusal), **Minor** (UX /
clarity / efficiency).

The 474-test baseline confirms the happy paths work. Every blocker
below is a behaviour that the current test suite does not exercise.

---

## 1. Blockers (must fix before wave 3)

### B1. Audit-log hash chain breaks under concurrent appends

**`src/engagement.py:696-749` `_append_audit_event`**

The append sequence is:

1. `SELECT audit_head_hash` (read prev)
2. compute `row_hash = SHA-256(prev || payload)`
3. `INSERT audit_event`
4. `UPDATE engagement SET audit_head_hash = ?`

All four happen inside a `with conn: ... ` block, but SQLite in
default mode opens a **DEFERRED** transaction. The `SELECT` does not
upgrade to a write lock; a second concurrent call reads the SAME
`prev` between steps 1 and 4 of the first, then both try to commit.
SQLite serialises the writes via locking — but both rows have the
same `prev_row_hash`, the chain is forked, and
`verify_audit_log` fails on the second row.

Repro (8 threads, fresh store):

```python
# .venv/bin/python -c "..."
import tempfile, threading
from pathlib import Path
from src.engagement import EngagementStore, AuditEventType
from src.identity import User, Role
with tempfile.TemporaryDirectory() as td:
    store = EngagementStore(db_path=Path(td)/'e.db')
    actor = User(id='u1', email='a@b', role=Role.analyst, display_name='A')
    eng = store.create_engagement(actor=actor, client_id='c',
        standard_of_value='ifrs13', pack_version='v1', engine_version='abc')
    barrier = threading.Barrier(8)
    def w(i):
        barrier.wait()
        store._append_audit_event(engagement_id=eng.id,
            event_type=AuditEventType.snapshot_added,
            payload={'i':i}, actor=actor)
    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    for t in ts: t.start()
    for t in ts: t.join()
    print(store.verify_audit_log(eng.id))
```

Result: `(False, 'event ... has prev_row_hash bc4b8adb..., expected 74e34d23...')`.

This violates **SYSTEM_SPEC §8.14**: the per-engagement hash chain
is the tamper-evidence story. A break under normal concurrent load
means any honest re-verification fails identically to a tamper —
indistinguishable from malice.

Fix: open the transaction with `BEGIN IMMEDIATE` (acquires the
RESERVED lock on first statement), or move the
`SELECT audit_head_hash` into the same statement as the
`UPDATE engagement` via a CTE/`RETURNING`. Cheapest fix: a single
`threading.Lock` per `EngagementStore` instance protecting
`_append_audit_event`, paired with a doc note that the store is
process-local.

### B2. `add_snapshot` TOCTOU race — optimistic concurrency does not hold

**`src/engagement.py:431-505`**

```
eng = self.get_engagement(engagement_id)        # connection A
if eng.version != expected_version: raise ...    # check
with closing(self._connect()) as conn, conn:    # connection B
    INSERT snapshot ...
    UPDATE engagement SET version = version + 1
```

Two concurrent calls with `expected_version=0` both pass the check
and both increment. The "no concurrent edit" guarantee from
**SYSTEM_SPEC §8.12** ("HTTP 409 on stale version") silently fails
under concurrent uploads.

Repro (4 threads, same expected_version):

```python
# 4 add_snapshot calls, all expected_version=0
# Result: 'snapshots inserted: 4 conflicts: 0', 'final eng version: 4'
```

Spec §8.12 says: *"If the server's current head version for the
engagement does not match, the route returns HTTP 409 with code
`engagement-version-conflict`."* Today, all four succeed.

Fix: replace the read-then-check-then-write with an atomic
conditional UPDATE:

```sql
UPDATE engagement SET head_snapshot_id = ?, version = version + 1
WHERE id = ? AND version = ?
```

then check `cursor.rowcount == 1` and roll back the snapshot INSERT
if not. Same fix applies to `transition` at
`src/engagement.py:609-646` (same pattern).

### B3. Snapshot append-only invariant violated when an earlier head exists

**`src/engagement.py:481-486`**

```python
if eng.head_snapshot_id is not None:
    conn.execute(
        "UPDATE snapshot SET superseded_by = ? "
        "WHERE id = ? AND superseded_by IS NULL",
        (snap_id, eng.head_snapshot_id),
    )
```

This UPDATE is defended in the comment as "the only mutation on
snapshot," and it's logically harmless — but it lives in the **same
connection** as the version race in B2 and shares its TOCTOU.
Under the B2 race, two concurrent appends both see
`head_snapshot_id = X`, and both try to update X's `superseded_by`.
The `superseded_by IS NULL` guard fixes only the second-writer
issue (rowcount=0, silently); the new chain points to the wrong
"current" head from one of the two writers' point of view.

Fixing B2 (atomic conditional update on engagement.version) also
closes this. Leaving B2 unfixed makes B3 a soft corruption.

### B4. Read-only auditor can read any engagement's audit log

**`src/engagement_routes.py:441-462`** (`audit-log` + `verify`)

These routes have `@bp.before_request _auth_guard` so they require
*any* authenticated user, and they call `_store().list_audit_events(eng_id)`
**without** a `can(user, "engagement.read")` check and **without**
any tenancy ACL on `engagement_id`. A `read_only_auditor` (or any
token-bearing user) can walk the URL-space by guessing UUIDs to
read every engagement's audit log.

SYSTEM_SPEC §3.2 contract:
- *"read-only auditor: scoped to a single engagement via magic-link token."*
- *"Cross-engagement read attempt → HTTP 403 with code `tenancy-violation`."*

The `show` route at `:174` and `bundle` route at `:464` do gate on
`can(user, "engagement.read")` — but the permission table at
`src/identity.py:88-93` grants `engagement.read` to
`read_only_auditor` globally, so even that check does not enforce
tenancy. The note at `:166-169` acknowledges
*"Tokens-to-engagement mapping is a future GAP-39 enhancement; for
now, no engagement visible"* — but only `list_engagements` is
filtered. Every detail route remains open.

Net: B4 is both a missing `can()` check on `/audit-log` and
`/verify` **and** a missing tenancy scope on every detail / upload
/ memo / bundle route. The spec calls this out explicitly; the
implementation does not enforce it. Fix at least the symptomatic
gap: add `can(user, "engagement.read")` on every detail route
(parity with `show`), and add a tracked GAP for the engagement-
level ACL.

### B5. OCR fallback never runs for user-uploaded PDFs

**`src/pdf_intake.py:68-91`** + **`app.py:520-562` `upload_side_letter`**

The OCR fallback is gated on `isinstance(blob_or_path, (str, Path))`
(line 71). The Flask route at `app.py:537` passes raw `bytes`
(`blob = file.read()`), so the branch at `:89-91` runs instead, which
only appends `"pdf-no-text-recovered: image PDF + non-path input"`.

SYSTEM_SPEC §4.3 pipeline: *"If yield < 100 characters or < 5%
page-area coverage, fall back to OCR via a vendor-abstracted
backend."* The user-facing path silently does NOT fall back. The
docstring of `extract_text` even acknowledges *"in-memory bytes
would need to be spilled to a tempfile first"* — but does not do
so. Spec drift on §4.3 in the only production code path.

Fix: spill bytes to a `tempfile.NamedTemporaryFile(suffix=".pdf")`
before invoking the OCR backend, then `unlink`.

---

## 2. Majors (fix in wave 3 or sooner)

### M1. Rate-limit sliding window is up to 2× too wide

**`src/rate_limit.py:71-121` `consume`**

`window_seconds = 3600`, `_bucket = floor(ts/3600)`, and the count
query is `WHERE hour_bucket >= ? AND` against `bucket - 1`. So the
counter sums the current bucket AND the prior bucket.

Repro (`soft_limit=5`, `now_fn` controlled):

| step | bucket | count returned | allowed |
|---|---|---|---|
| 5 consumes at t=360000 | N | 5 | True |
| 1 consume at t=363600 (next hour) | N+1 | 6 | **False** |
| 1 consume at t=367200 | N+2 | 2 | True |

The docstring at `:90-94` even concedes this:
*"the count then represents the strict trailing-hour view rather
than the calendar-hour view."* But for the user immediately after
the boundary the effective window is **2 hours**, not 1. Spec §8.17:
*"Soft limit: 30 exports per hour per user."* — exactly one hour, not
"up to two."

The dead-code window calculation at `:86-88` confirms the author
meant to keep it strict but punted. Fix: parameterise the bucket
size smaller (e.g. 5-minute buckets) and `SUM` the last
`window_seconds/bucket_size` rows; or store full timestamps and
prune.

### M2. `triggered_hard_alert` fires once *per request* past the hard limit

**`src/rate_limit.py:110`** + **`src/engagement_routes.py:356-368`**

`triggered_hard = current >= self.hard_limit`. Once a user crosses
100/hr they get an `audit_event` of type `bulk_export_alert` on
**every** subsequent export call. Spec §8.17 says: *"Hard alert:
100 exports per hour per user triggers an `audit_event` of type
`bulk_export_alert` and an internal notification to the Risk
role."* — singular, not "per-call thereafter."

Worse: the `bundle.zip` route at `src/engagement_routes.py:464-493`
reads the limiter and respects `rl.allowed`, but does NOT call the
audit-event hook at all (the route copies the memo route's first
half but drops the alert hook). Inconsistency between two export
routes.

Fix: switch to `triggered_hard = (current == self.hard_limit)`
(edge-trigger) so the alert fires exactly once at the boundary;
and lift the alert hook into a helper used by both routes.

### M3. `pdf-no-reviewer` and `pdf-blockers-outstanding` refusals not enforced by the memo route on read-only auditors

**`src/engagement_routes.py:348-437`**

The memo route at `:348` checks rate limits but does **not** check
`can(user, "engagement.generate_memo_draft")` or
`export.memo_pdf`. The eligibility check inside
`render_pdf_memo` at `src/pdf_memo.py:127-143` does enforce
"named reviewer" — but the route auto-supplies the user's
display_name if their role is reviewer/partner, and otherwise
silently produces None reviewer (which then 400s as
`pdf-no-reviewer`). Two issues:

1. A `read_only_auditor` calling the memo route can trigger memo
generation for any engagement; they will be 400'd by the
"no reviewer" check, but they still **incremented the rate
limiter** before that check. Free DOS vector against legitimate
analyst export budget.
2. The `analyst` role is permitted `export.memo_pdf` but cannot
have their own name used as reviewer (analyst ≠ reviewer).
With no `?reviewer=` query param, every analyst memo request
fails `pdf-no-reviewer`. The route does not surface this
clearly.

Fix: gate the route on `can(user, "export.memo_pdf")` BEFORE
consuming the rate limit; require `?reviewer=` for analyst role
explicitly with a clear error.

### M4. Bundle re-loads rule pack from disk, not the snapshot's bound pack

**`src/engagement_bundle.py:73-77`**

```python
candidate = Path("rule_packs") / f"{eng.pack_version}.json"
if candidate.exists():
    rule_pack = load_pack_from_file(candidate)
```

The bundle promises to be *"portable, offline-verifiable"*. But
the rule pack copy embedded in the zip is whatever happens to be
on local disk under that filename **today**, not the bytes that
existed when the engagement was opened. If `rule_packs/v2026.3.0.json`
is bumped (rule ordering changed, a rule renamed) the bundle's
copy disagrees with what actually ran against the snapshot. Spec
§8.15 protects against engine-skew with an `engine_version`
column; the analogous protection for the *pack file* is missing
(only `pack_version` string is stored).

Also: `Path("rule_packs")` is a relative path. If the bundle is
invoked from any cwd other than the repo root (a cron worker, a
spawned process), `candidate.exists()` returns False and the
bundle silently omits `rule_pack.json` from the zip. The README
inside the bundle then references a file that isn't there.

Fix: store the rule pack JSON bytes alongside the engagement at
bind time (engagement_pack_binding row), and ship those bytes in
the bundle. Or resolve `_PACKS_DIR` from `src.rule_pack` rather
than cwd-relative.

### M5. Bundle determinism — `generated_at` timestamp inside `manifest.json`

**`src/engagement_bundle.py:79-88`**

`manifest["generated_at"] = datetime.now(timezone.utc).isoformat()`.
The manifest's SHA-256 is then implicit in the zip (the manifest
hash isn't stored in any pinned location — the README only
describes how to verify *other* files using the manifest, not how
to verify the manifest itself).

Spec **§8.10** carves out determinism explicitly: *"PDF audit memo
... Bit-for-bit EXCEPT for the cover-sheet timestamp"*. The bundle
is not in the table at all. Until the spec adds a bundle row to
§8.10's table, this is **spec drift**: the contract for the bundle
is undefined, and the implementation embeds a wall-clock timestamp
without acknowledging it. Two consecutive `build_engagement_bundle`
calls produce different `manifest.json` bytes (and therefore
different `manifest.json` SHA-256s, though that hash isn't recorded).

Fix one of two ways:
- Amend §8.10 to add a bundle row (`bit-for-bit EXCEPT manifest.generated_at`),
match impl to it.
- Source `generated_at` from `eng.created_at` or the head event's
`ts`, removing the wall-clock dependency.

### M6. `engagement.upload_cap_table` permission not checked

**`src/engagement_routes.py:202-263` `upload`**

The route accepts an .xlsx upload and calls `_store().add_snapshot(...)`,
which only checks `engagement.add_snapshot`. The spec lists
`engagement.upload_cap_table` as a separate permission (granted to
analyst only) in `src/identity.py:51` — but no route actually
checks it. The distinction in §3.2 between *"may upload Excel"* and
*"may create snapshots via edits"* collapses. Today a reviewer (who
has `engagement.add_snapshot` per `:62`) can upload .xlsx and
create snapshots; spec says reviewer should only create snapshots
via "edits/resolutions."

Fix: add `can(user, "engagement.upload_cap_table")` gate before
calling `add_snapshot` in the upload route. Or amend the spec to
unify the two permissions and remove the unused one.

### M7. Memo route uses only head-snapshot resolutions

**`src/engagement_routes.py:400`** (`resolutions_list = _store().list_resolutions(snap.id)`)

When a new snapshot is appended (e.g., analyst re-uploads after a
fix), resolutions recorded against the prior snapshot are not
carried into the memo. SYSTEM_SPEC §3.4 §06 ("Findings &
resolutions") doesn't explicitly require carry-forward, but a
"signed off" engagement that has had a resolution recorded against
SNAPSHOT_N and is now at SNAPSHOT_N+1 produces a memo that looks
like the resolution never happened. This silently misrepresents
the engagement history.

Fix: either (a) collect resolutions across all snapshots in the
chain when the head changes, or (b) propagate prior resolutions
into the new snapshot as a `source=resolution` snapshot. Option
(b) matches the spec's *"any edit creates a new snapshot with
source=resolution"* phrasing.

### M8. `cap_table_for_waterfall` is not what the AICPA rule says it is

**`src/rules_v2026_3.py:91-125` `_rule_aicpa_lp_overhang`**

```python
total_shares = cap_table.total_fully_diluted_for_waterfall
enterprise_proxy = pps * total_shares
```

`total_fully_diluted_for_waterfall` includes the granted option
pool. Multiplying by latest preferred PPS is an *upper bound* on
enterprise value, not the OPM-implied value the AICPA actually
discusses in §4.18. The rule's own comment concedes this is
*"the checklist-time approximation."* That is fine as a heuristic,
but the rule's `summary` text presents the ratio as authoritative
("is X% of PPS-implied enterprise value") and analysts will copy-
paste it. The wording overpromises what the proxy supports.

Fix: re-word the summary to say "PPS-implied upper-bound EV proxy"
or similar to make the approximation explicit. (Not a code bug;
a copy bug with audit consequence.)

---

## 3. Minors

### m1. Path traversal vector via `pack_version` in bundle

**`src/engagement_bundle.py:75`** —
`Path("rule_packs") / f"{eng.pack_version}.json"`. `pack_version`
flows from `head_pack().version`, which flows from the JSON file's
`version` field via `RulePack.model_validate_json` at
`src/rule_pack.py:189`. Today the version strings are well-formed
(`v2026.3.0`), but the model accepts any string. A pack file with
`"version": "../../etc/passwd\x00"` would let the bundle attempt
to read arbitrary files (and `Path.exists()` swallows OSErrors).

Fix: validate `pack_version` against `^v\d+\.\d+\.\d+$` at the
Pydantic level, OR sanitise before path concat.

### m2. Bundle `download_name` uses `eng_id[:8]`

**`src/engagement_routes.py:492`** and `engagement_bundle.py:158` —
slicing a UUID to 8 chars in user-facing filenames invites the same
hash birthday-collision UX issue as memo PDFs (`:436`). Two
engagements share a download name with probability ≈ 1.5×10⁻⁵ per
pair. Not security; UX. Fix: full UUID or first 12.

### m3. `parse_report_json` round-trip uses `dataclasses.asdict` then `json.dumps`

**`src/engagement_routes.py:239-244`** — the route at upload time
wraps in a try/except that swallows ANY exception to `parse_report_json = None`.
If serialisation ever fails (e.g., a non-JSON-serialisable warning
class is added to `ParseReport`), the warning silently disappears.
A blanket `except Exception` is the wrong tool here; narrow it to
`TypeError, ValueError` and log the unexpected case.

### m4. `triggered_hard_alert` audit-event hook calls a private method

**`src/engagement_routes.py:358`** — `_store()._append_audit_event(...)`.
Routes are supposed to use public store methods; this leaking
abstraction is the only place outside `engagement.py` that pokes
the underscore-prefixed API. Add a public `append_bulk_export_alert(...)`
helper.

### m5. `Engagement.valuation_date` typed as `Optional[str]` not `date`

**`src/engagement.py:138`** — spec §3.2 says `valuation_date: date`.
Storing as string defers validation to ad-hoc parsing later and
lets `"not-a-date"` pass through. Tightens later, not a blocker.

### m6. `_rule_aicpa_lp_overhang` uses `__import__("datetime").date.min`

**`src/rules_v2026_3.py:106`** — ugly, works. Move the import to
module top.

### m7. `NullBackend.is_available()` returns True

**`src/ocr/null_backend.py:18-19`** — the comment admits this is
"always available — but flagged as unhelpful by zero confidence."
Spec §4.3: *"Default backend: Google Document AI ... Fallback
backend: self-hosted Tesseract + LayoutParser."* The Null backend
is not in the spec's vendor list. Today it short-circuits the
"OCR not configured" warning into a confidence=0 result. That is
*technically* the right behaviour (banner appears, analyst falls
back to manual), but the warning text reads
*"ocr-backend-unavailable: no OCR backend installed."* — which
should be a structured error code, not a freeform message.

### m8. `EngagementVersionConflict.http_status` is 409 (correct) but `ImmutableViolation.http_status` is 500

**`src/engagement.py:127`** — never raised anywhere in the codebase
today. Either remove or use; dead code in an audit-sensitive file
is noise.

### m9. `redact_snapshot_pii` does not enforce engagement-level ACL

**`src/engagement.py:650-692`** — partner permission alone is
enough; no check that the partner owns this engagement (mirror of
B4 tenancy gap).

### m10. `_extract_token` accepts `?token=` query param

**`src/engagement_routes.py:68-72`** — passing auth tokens in
query strings logs them in access logs and browser history. The
docstring says *"X-Auth-Token in the query string for tests"* but
no separation between test-only and prod paths. Tighten to
`X-Auth-Token` header only outside `app.testing`.

---

## 4. Spec drift table

| Spec | Reference | Implementation | Drift |
|---|---|---|---|
| §3.2 Cross-engagement reads forbidden | `audit-log`, `verify`, `bundle`, `memo` routes | Only `list_engagements` filters by role | **B4** — every detail route open to any authenticated user |
| §3.2 `analyst` may upload, `reviewer` may NOT | Both pass `engagement.add_snapshot` check | `engagement.upload_cap_table` permission unused | **M6** |
| §3.2 Engagement edits use optimistic concurrency | `expected_version` check is non-atomic | TOCTOU under concurrent writes | **B2** |
| §3.4 Memo carries all resolutions for engagement | Memo carries only head snapshot's resolutions | Prior resolutions invisible | **M7** |
| §4.3 OCR fallback when text < 100 chars | Only fires for path inputs, not bytes | User-facing upload path skips OCR | **B5** |
| §8.5 Confidence < 0.85 triggers banner | Warning string appended | Matches spec | OK |
| §8.10 Determinism carve-outs | Bundle not listed; `generated_at` baked in | New format with undefined determinism contract | **M5** |
| §8.12 Stale-version returns 409 | Implementation always succeeds under race | Race | **B2** |
| §8.14 Hash chain unbroken under writes | Chain forks under concurrent appends | Race | **B1** |
| §8.16 Excel exports treat strings as values not formulas | (Wave 1; unchanged in Wave 2) | OK | OK |
| §8.17 Soft limit = 30 / hr | Window is up to 2 hr depending on phase | Window math too wide | **M1** |
| §8.17 Hard alert fires *at* 100 | Fires on every call >= 100 | Edge vs level trigger | **M2** |

---

## 5. Resource / perf concerns

- **`EngagementStore._connect` opens a new SQLite connection on every
call** (`src/engagement.py:322-325`). Every list/get/append uses 1-2
connections, every snapshot creation uses 3+. SQLite tolerates this,
but a hot `audit_log` route serving a 5000-event engagement opens N
connections to read N rows. Fix: connection-per-thread via
`threading.local`, or accept it and add a comment.

- **Bundle holds the entire zip in memory** (`engagement_bundle.py:154`
`buf.getvalue()`). For an engagement with 100 snapshots × 200-class
cap tables this could be tens of MB. Acceptable for now; flag for
Phase 3 when the operations runbook talks about long-lived
engagements.

- **`_no_cache` after_request is applied to PDF/zip downloads**
(`app.py:59-62`). That's fine for the security stance, but adds
`no-store` to every static asset response — harmless but wasteful
in browser dev tools.

- **`ExportRateLimiter.prune_older_than` is never called** anywhere.
The `export_counter` table grows linearly with (users × hours).
Fix: schedule via the OPERATIONS runbook cron, or call at startup
with `cutoff = now - 7*24*3600`.

- **Tesseract OCR rasterises at 300 DPI** (`tesseract_backend.py:73`).
For a 30-page scanned PDF this materialises ~30 large PIL images in
memory. Acceptable for a side-letter (1-3 pages typical); for an
8MB-uploaded scan it's borderline. Worth a memory cap.

---

## 6. Security review

| Vector | Site | Status |
|---|---|---|
| Auth bypass (missing `can()`) on audit-log / verify | `engagement_routes.py:441,458` | **Open — B4** |
| Tenancy isolation (engagement-id ACL) | every detail route | **Open — B4** (spec calls this out; impl punts to "future GAP-39") |
| Token-in-query-string logging risk | `engagement_routes.py:72` | **m10** |
| Path traversal via `pack_version` → file load | `engagement_bundle.py:75` | **m1** — validate pack_version |
| Path traversal via `download_name` (eng_id slice) | `engagement_routes.py:436,492` | UUIDs are URL-safe; no traversal possible |
| Zip-slip in bundle (writing entries with `..`) | `engagement_bundle.py:107,113,119,136,141,147,152` | All entry names are server-generated (UUIDs + literal strings); no user-controlled path components |
| Injection in bundle filenames (`source_filename` reflected?) | not reflected — bundle uses snapshot UUIDs only | OK |
| XSS in jinja templates (memo route) | uses `templates/memo/base.html` with `select_autoescape(["html","xml"])` | OK per §8.16 |
| SQL injection | all SQL in `engagement.py` / `rate_limit.py` uses `?` placeholders | OK |
| Mass-assignment via JSON body | `create_engagement` reads `standard`, `valuation_date` from JSON without whitelist — but they pass through to the Pydantic model which has `extra="forbid"` | OK |
| Bulk-export DOS (hard limit not edge-triggered → alert flood) | `rate_limit.py:110` | **M2** |
| Memo route rate-limits even unauthorised callers | `engagement_routes.py:351-381` runs limiter before role check | **M3** (DOS against budget) |
| SAFE/warrant filenames in resolutions could contain HTML | rendered via Jinja autoescape | OK |
| OCR temp-file cleanup | OCR doesn't write its own tempfile — uses caller's path; `pdf2image` materialises in memory | OK |

---

## 7. Things checked and CLEAN

- **`src/diff.py` BUG-014 fix** (`:137`) — `left.issue_price != right.issue_price`
correctly distinguishes `None != 0` and `None != 1.0`. The prior
`(None or 0)` pattern is gone. Conversion-ratio comparison at `:145`
similarly distinguishes None from 1.0.
- **`app.py` BUG-010 fix** (`:628-647`) — zero-baseline class with
shares override correctly computes new LP amount from
`shares × issue_price × multiple` and falls back to legacy
multiplicative scaling when `issue_price` is absent. Division by zero
on `mult_ratio` is guarded at `:627`.
- **PDF tempfile cleanup** in `upload` (`engagement_routes.py:219-236`)
— uses `tempfile.NamedTemporaryFile` with `delete=False` and unlinks
in `finally`. Excel parse errors caught explicitly. Matches BUG-006
pattern from `app.py`.
- **Audit-log canonical-payload hash** (`engagement.py:212-230`) —
sort_keys + colon-separators inside payload_json; `\x00` separator
between prev_hash and canonical. Deterministic and matches the
README recipe in `engagement_bundle.py:189-193`. Verify routine
(`:771-796`) checks both per-row hash and head pointer.
- **Hash genesis = `"0"*64`** (`engagement.py:209`) — consistent
between writer and verifier and README.
- **Rule pack v2026.3.0.json rule_ids** (`rule_packs/v2026.3.0.json:13-43`)
match the seven new `@rule(...)` registrations in `rules_v2026_3.py`
and the 23 inherited from v2026.2.0. Count = 30, matches spec §4.6
acceptance criterion (*"Rule-pack count ≥ 30"*).
- **WeasyPrint autoescape** (`pdf_memo.py:283`) — `select_autoescape(["html","xml"])`,
correct per §8.16.
- **`StubSSOProvider` rejects empty tokens** (`identity.py:135-137`) —
prevents accidental anonymous access via empty Authorization headers.
- **`pdf_memo._ensure_eligible` blockers/no-reviewer enforcement**
(`pdf_memo.py:127-143`) — both spec refusals (§3.4) enforced before
PDF generation.
- **`AuditEventType.bulk_export_alert`** registered (`engagement.py:76`);
the memo route emits it correctly (though see M2 for trigger-edge
issue).

---

## 8. Fix-now-vs-defer table

| Finding | Severity | Fix scope | Recommendation |
|---|---|---|---|
| **B1** Hash chain race | Blocker | Single-line `threading.Lock` or `BEGIN IMMEDIATE` | **Fix in W2-AUDIT** |
| **B2** Snapshot version TOCTOU | Blocker | Conditional UPDATE + rowcount check | **Fix in W2-AUDIT** |
| **B3** Supersede chain under B2 race | Blocker (latent) | Closed by B2 fix | Fix with B2 |
| **B4** Cross-engagement read open | Blocker | `can()` on detail routes + tracked GAP for engagement ACL | **Fix `can()` in W2-AUDIT**, defer engagement ACL to W3.2 |
| **B5** OCR skipped for byte inputs | Blocker (spec drift) | 10 lines — spill to tempfile | **Fix in W2-AUDIT** |
| M1 Rate-limit window | Major | Refactor bucket size + sum | **Fix in W3.3** (audit-log query SLO slot already touches the limiter) |
| M2 Hard-alert edge trigger + bundle missing hook | Major | 2 lines + factor helper | **Fix in W2-AUDIT** |
| M3 Memo permission gate | Major | Add `can()` gate; clarify analyst reviewer-arg requirement | **Fix in W2-AUDIT** |
| M4 Bundle re-loads pack from cwd | Major | Use absolute pack dir; persist pack bytes on bind | **Defer to W3.6** (pack persistence belongs with the new pack) |
| M5 Bundle determinism undefined | Major | Spec amendment (preferred) or freeze timestamp | **Spec change in W3-DONE notes; bundle deterministic at W3** |
| M6 `upload_cap_table` perm unused | Major | One-line `can()` | **Fix in W2-AUDIT** |
| M7 Memo loses prior resolutions | Major | Either carry-forward query or auto-snapshot on resolve | **Defer to W3.1** (subsequent-events memo already touches this code path) |
| M8 AICPA rule wording overpromises | Major (copy) | One-line summary edit | **Fix in W2-AUDIT** (one line) |
| m1 pack_version path-traversal | Minor | Pydantic regex on `version` | **Fix in W2-AUDIT** (cheap) |
| m2 8-char UUID filenames | Minor | Lengthen slice | Fix opportunistically |
| m3 Blanket except in parse_report | Minor | Narrow except | Fix opportunistically |
| m4 Private API leak | Minor | Add public helper | Fix with M2 |
| m5 `valuation_date` as str | Minor | Pydantic `date` | **Defer** — touches DB serialisation |
| m6 Inline `__import__` | Minor | Move to top | Fix in W2-AUDIT |
| m7 Null OCR backend availability | Minor | Structured warning code | **Defer to W3** with proper backend registry |
| m8 `ImmutableViolation` dead code | Minor | Remove | Fix in W2-AUDIT |
| m9 Redaction no engagement ACL | Minor | Mirror B4 fix | Fix with B4 |
| m10 Token in query string | Minor | Restrict to test mode | Fix in W2-AUDIT |

**Summary for W2-AUDIT fix batch** (fits in one session, < 200 LOC
total): B1, B2, B3 (auto), B4 (partial — `can()` only), B5, M2, M3,
M6, M8 (one-line), m1, m4, m6, m8, m10.

**Deferred to wave 3**: M1 (W3.3), M4 (W3.6), M5 (spec round 2),
M7 (W3.1), m5, m7, full tenancy ACL.

---

*End of Wave 2 code audit.*
