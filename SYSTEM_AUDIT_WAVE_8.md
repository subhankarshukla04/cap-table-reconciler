# SYSTEM AUDIT — Wave 8

Auditor: independent gate
Scope: only the surface introduced or touched by wave 8 (W8.1–W8.13), and
any contract collisions wave 8 creates with W2–W7 consumers.
Method: read W8 files, reproduce non-obvious findings against the
project venv, then probe each item in the wave-8 brief.

Baseline: 786 tests pass under the same harness shipped with the wave.

Severity ladder — BLOCKER (ship-stop), MAJOR (pre-prod), MINOR.

---

## 1. BLOCKERS

None. The wave does not introduce any ship-stop defects.

---

## 2. MAJORS

### W8-M1 — /readyz lies during a database outage
File: `app.py:1344-1392`

`/readyz` always returns `{"status": "ok", ...}` and HTTP 200, even when
the `ENGAGEMENTS._connect()` block raises. The route catches the
exception, sets `engagements_total` and `audit_log_total` to `None`, and
keeps `status: "ok"`. An SRE wiring this into a Kubernetes
readinessProbe / load-balancer health check will leave the pod in
rotation while SQLite is unreachable or corrupt. The probe was sold to
SRE consumers as "the state SREs actually page on" — by definition that
must downgrade `status` on DB failure.

Fix: set `out["status"] = "degraded"` (and return HTTP 503) inside the
two `except Exception` arms (lines 1373-1374, 1389-1391), and also when
`pack_version is None` after the head-pack try/except. A successful
`/readyz` must mean every dependency probed succeeded; mixed-null
payloads with `"ok"` are worse than no probe at all.

### W8-M2 — Phase-0 gate breaks attach-from-other-app callers
File: `src/engagement_routes.py:1619` and `src/cookie_auth.py:332-333`

W8.2 added a constructor-time refusal to `StubSSOProvider`. Two helpers
that previously worked without identity wiring now raise at attach
time:

  - `attach_engagement_blueprint(app, store)` (no `identity_provider`
    kwarg): line 1619 unconditionally evaluates
    `identity_provider or StubSSOProvider()`. The `or` chain ALWAYS
    constructs the stub when the kwarg is `None`, even though it
    might be discarded by the truthy left side — Python evaluates both
    sides. In dev/test that's fine because `_running_in_test()` returns
    True. Outside pytest (e.g. an SRE smoke harness, a vendored
    consumer, or a non-pytest test runner) this raises
    `RuntimeError: StubSSOProvider refused to start`.
  - `attach_login_blueprint(app)` with no `identity_provider` kwarg and
    no `IDENTITY_PROVIDER` already in app.config (line 332-333): same
    construction, same failure mode.

This is a silent contract change. The wave-2..wave-7 fixture apps that
set `app.config["IDENTITY_PROVIDER"]` BEFORE calling these helpers are
unaffected, which is why 786 tests pass. But any consumer who relied on
"helpers default to a working stub" gets a runtime crash on import-time
boot.

Reproduced:
```
$ .venv/bin/python -c "
from flask import Flask; from pathlib import Path
from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
import tempfile
with tempfile.TemporaryDirectory() as td:
    attach_engagement_blueprint(Flask(__name__), EngagementStore(Path(td)/'e.db'))
"
RuntimeError: StubSSOProvider refused to start: set ALLOW_STUB_SSO=1 ...
```

Fix: change line 1619 to
`app.config["IDENTITY_PROVIDER"] = identity_provider or StubSSOProvider(allow_in_prod=True)`,
and line 332-333 in cookie_auth.py to the same. The wrapper helpers are
themselves the explicit dev-path opt-in; if the operator wanted prod
hardening, they'd pass their own provider or set the env var. The
W8.2 guard exists for the boot path (`app.py:93`), which already opts
in via `allow_in_prod=True`. Without this fix, the W8.2 hardening also
silently breaks any well-intentioned consumer that relied on the
defaults documented in the helpers' docstrings.

### W8-M3 — /readyz leaks operational counters without auth
File: `app.py:1344-1392`

`/readyz` exposes — anonymously — engine commit, rule-pack version,
deny-list size, audit log total, engagement count, and the timestamp of
the last engagement creation. The deny-list size pairs with the W6.4
ops doc ("operators page on sudden growth = revocation storm"); leaking
it externally signals revocation tempo to an attacker. The
`engagements_total` and `last_engagement_created_at` fields reveal
business scale and last-user-activity to anyone who curls the endpoint.

This is defensible on an SRE-only ingress, but the route has no auth
gate by design and the brief acknowledges that posture. In any
deployment where the LB exposes `/readyz` to the public internet (the
default for many ingress configurations), the leak is real.

Fix: split the route. Keep a minimal anonymous `/readyz` that returns
`{"status": "ok"}` (or 503 — see W8-M1) and gate the counters behind
either Bearer auth (admin scope) OR a CIDR allow-list configured in
app.config["READYZ_ALLOW_CIDR"]. The richer-probe variant becomes
`/readyz/detailed` for in-cluster scraping.

---

## 3. MINORS

### W8-m1 — Formula workbook is NOT byte-stable despite W8.4 claim
File: `src/formula_workbook.py:98-115`

The W8.4 spec sold byte-stable xlsx for diff workpapers AND the live
formula workbook. `src/formula_workbook.py` pins
`wb.properties.created/modified/creator/lastModifiedBy` but does NOT
post-process the zip envelope. openpyxl's `save()` later overrides
`wb.properties.modified` with wall-clock at write time, and the zip
entry mtimes are wall-clock too. The diff workpaper handles both via
`_rewrite_zip_with_epoch_mtimes` + `_scrub_core_xml_modified`; the
formula workbook does not.

Reproduced:
```
$ .venv/bin/python -c "
from src.formula_workbook import build_formula_workbook
from src.parser import load_from_canonical_json
from src.waterfall import compute_waterfall
from pathlib import Path
import io, time, hashlib
ct = load_from_canonical_json(Path('fixtures/fixture_01_clean/cap_table_input.json'))
wf = compute_waterfall(ct)
b1 = io.BytesIO(); build_formula_workbook(ct, wf).save(b1)
time.sleep(1.1)
b2 = io.BytesIO(); build_formula_workbook(ct, wf).save(b2)
print('same?', b1.getvalue() == b2.getvalue())
"
same? False
```

Fix: in `app.py`'s `export_live_xlsx` (line 1007-1017), after
`wb.save(bio)`, run the bytes through
`src.diff_workpaper._rewrite_zip_with_epoch_mtimes`. Alternatively,
move that helper to a shared module (e.g. `src/xlsx_stability.py`) and
call it from both export paths plus `_build_clean_xlsx_bytes`. The
prod-readiness claim is "every xlsx the engine emits is bit-stable";
shipping with one of the three xlsx producers non-stable is a
half-finished fix.

### W8-m2 — current_engine_commit() cache is sticky across env changes
File: `src/rule_pack.py:462-498`

The module-level `_ENGINE_COMMIT_CACHE` is populated by the first call
and never invalidated. If `QAPITA_ENGINE_COMMIT` is set AFTER the first
call (test isolation, a hot config reload, a CLI command that imports
the engine before reading env from a dotenv file), the cached
"unversioned" / dev-git-SHA value persists for the lifetime of the
process.

Reproduced:
```
$ .venv/bin/python -c "
import os, src.rule_pack as rp
print(rp.current_engine_commit())
os.environ['QAPITA_ENGINE_COMMIT'] = 'abc123def456'
print(rp.current_engine_commit())
"
7675029f2c6a
7675029f2c6a
```

Fix: invalidate when the env var differs from the cache. Two lines:

```
env_commit = os.environ.get("QAPITA_ENGINE_COMMIT", "").strip()
if env_commit and _ENGINE_COMMIT_CACHE != env_commit[:12]:
    _ENGINE_COMMIT_CACHE = None  # bust on env change
```

before the `if _ENGINE_COMMIT_CACHE is not None: return` short-circuit.

### W8-m3 — Phase-0 gate's `/diff` prefix swallows future routes too
File: `app.py:131-159`

`_PHASE_0_PREFIXES` contains the literal string `/diff` (no trailing
slash). `path.startswith("/diff")` matches `/diff`, `/diffx`,
`/diffanything`. Today no engagement-blueprint URL collides (engagement
routes start with `/engagement/`). But any future top-level route named
`/diff*` (e.g. a `/difference-report` admin tool) silently gets 404'd
in any non-phase-0 deploy. Same risk on `/sessions` (matches
`/sessions-list`).

Reproduced — confirmed `/engagement/<id>/diff` does NOT match (it
starts with `/engagement/`):
```
/engagement/abc/diff blocked? False
/diff blocked? True
/diffx blocked? True
```

Fix: anchor each entry. Use `"/diff/"` plus an exact-match check for
`/diff` (a tuple of exact paths + a tuple of prefixes), so future
routes don't trip a silent 404. Same for `/sessions`.

### W8-m4 — Memo route 500s on bad snapshot JSON post-W8.11
File: `src/engagement_routes.py:1024-1039`

W8.11 added auto-compute of `compute_timeline_diff` inside the memo
route. If any snapshot's `cap_table_json` fails `CapTable` validation
(legacy data, partial migration, malformed serialization), the
list-comprehension `[s.load_cap_table() for s in all_snaps]` raises
`ValidationError`. `_engagement_errors` catches `ValidationError` and
returns 400 — so the analyst gets `validation-failed` 400 instead of
the memo they could have generated before W8.11 (the head snapshot is
still valid; only an older one is broken).

Fix: wrap the timeline-diff block in try/except `Exception` and set
`timeline_diff = None` on failure. The memo template already gates the
section on `{% if timeline_diff and timeline_diff.class_rows %}`. Log
the failure for ops visibility. Memo generation should never regress
on a problem with a stale snapshot the analyst isn't even asking
about.

### W8-m5 — hard-delete CLI's dead import
File: `app.py:1329`

`from src.engagement import EngagementStore as _ES` inside
`cli_hard_delete_archived` is unused. Harmless but noisy. Drop it.

### W8-m6 — Legacy archived engagements with NULL restore_until cannot ever restore
File: `src/engagement.py:867-877`

The W8.10 idempotent ALTER migration adds `restore_eligibility_until`
as a NULL column on existing rows. An engagement archived BEFORE
wave-8 deploy has `archived = open + status = archived` but
`restore_eligibility_until IS NULL`. The transition guard at line 869
treats NULL as "expired" and refuses restoration permanently.

That's defensive (no time machine), but the wave-8 hard-delete CLI
also refuses to delete rows with NULL `restore_eligibility_until`
(line 943 `AND restore_eligibility_until IS NOT NULL`). So legacy
archived engagements are now stranded: cannot restore, cannot
hard-delete. They sit forever.

Fix: in the W8.10 idempotent ALTER block (engagement.py:452-459),
backfill: for any row where `status = 'archived'` and
`restore_eligibility_until IS NULL`, set `archived_at = COALESCE(...,
created_at)` and `restore_eligibility_until = archived_at + 90 days`.
This makes the migration retroactively coherent. One-time data move,
idempotent.

### W8-m7 — Sorted zip entries may surprise consumers expecting
openpyxl's native order
File: `src/diff_workpaper.py:201`

`_rewrite_zip_with_epoch_mtimes` writes entries in alphabetical order
(`sorted(n.filename for n in src.infolist())`). Excel + openpyxl both
read by name from the central directory, so this is functionally
correct (verified: the rewritten file round-trips through openpyxl
with all three sheets intact). But the central-directory order is now
NOT what openpyxl produced. Any consumer that diffs xlsx with a tool
that relies on entry order (e.g., a digest of the central directory
itself) will see drift vs. an openpyxl-native build. Minor because no
known consumer cares; flag for completeness so future "why does my
SHA differ from the engine's" tickets have a paper trail.

No fix needed; document in the spec next to the W8.4 stability claim.

### W8-m8 — `_pin_xlsx_properties` hardcoded 2026-01-01 fallback
File: `src/diff_workpaper.py:73-74`, `src/formula_workbook.py:111`

`if anchor is None: anchor = datetime(2026, 1, 1, ...)`. When a diff
has zero snapshots (unreachable today — `/diff` gate refuses <2
snapshots) or a formula workbook is built for a cap table with no
valuation_date, this hardcoded date is embedded in
`docProps/core.xml`. Stable across deploys (same constant everywhere),
so not a stability problem per se. Confusing if someone reads the
metadata and sees Jan 1 2026 on a cap-table valued at Mar 2027 —
they'll think the workbook is misdated. Pure UX; no security/data
correctness issue.

Fix optional: use the project's import-time `datetime.now()` (resolved
once at module load) instead of a literal. Or document the constant
in `SYSTEM_SPEC.md §13` so the next analyst doesn't file a "wrong
date" bug.

---

## 4. CROSS-WAVE CONTRACT MATRIX

| W8 producer                       | Consumer wave / surface                  | Contract OK? | Notes                                                                  |
|-----------------------------------|------------------------------------------|--------------|------------------------------------------------------------------------|
| W8.1 `_safe_next_url`             | `/login`, `/logout` (W5.7/W6.1)          | OK           | Verified `\r\n\x00\x7f` all rejected; redirects fall through to default |
| W8.2 StubSSOProvider refusal      | `attach_engagement_blueprint` (W2.1)     | BROKEN       | See W8-M2: helpers cannot construct fallback in non-test prod          |
| W8.2 StubSSOProvider refusal      | `attach_login_blueprint` (W5.7)          | BROKEN       | Same as above                                                          |
| W8.2 phase-0 demo gate            | `/healthz`, `/readyz`, `/engagement/*`   | OK           | None of these match the prefix list                                    |
| W8.2 phase-0 demo gate            | `/login`, `/logout`                      | OK           | Not in prefix list                                                     |
| W8.3 `current_engine_commit()`    | `/readyz`, `create_engagement`           | MINOR        | Stale cache across env changes — W8-m2                                 |
| W8.4 xlsx byte stability          | diff workpaper xlsx                      | OK           | Verified two consecutive builds produce identical bytes                |
| W8.4 xlsx byte stability          | live formula workbook                    | BROKEN       | Pinning without zip rewrite leaves wall-clock everywhere — W8-m1       |
| W8.4 xlsx byte stability          | static clean workbook (`_build_clean_*`) | NOT WIRED    | Untouched by W8.4 at all; same drift risk                              |
| W8.5 ResourceWarning silence      | full pytest suite                        | OK           | 786 pass under `-W error::ResourceWarning` with the filterwarnings hop  |
| W8.6 `safe_created_by()`          | timeline JSON, SnapshotMeta, bundle      | OK           | Wired at every render site (engagement_routes.py:1140, 1232, 1330, 1404)|
| W8.7 /logout preserves CSRF       | engagement blueprint after_request heal  | OK           | After logout, next GET re-issues CSRF via `_heal_csrf_cookie`           |
| W8.8 /readyz                      | SRE consumers                            | MAJOR x2     | W8-M1 (lies on outage), W8-M3 (anonymous data leak)                    |
| W8.9 prune-deny-list CLI          | TokenDenyList.prune_expired              | OK           | Method exists; safe to schedule daily                                  |
| W8.9 prune-rate-limits CLI        | ExportRateLimiter.prune_older_than       | OK           | Method exists; uses 7-day cutoff bucket                                |
| W8.9 hard-delete-archived CLI     | EngagementStore.hard_delete_expired_*    | OK + W8-m6   | Works for new archives; legacy archives stranded                       |
| W8.10 archival columns            | Pydantic `Engagement` model              | OK           | Both nullable; legacy rows tolerate                                     |
| W8.10 restore window enforcement  | `transition(archived → open)`            | OK           | Verified expired restore raises `IllegalStateTransition`               |
| W8.10 archived → open clears       | `bound_pack_json`                        | UNTOUCHED    | Correct — restore must keep prior pack binding                          |
| W8.10 archived → open clears       | `head_snapshot_id`                       | UNTOUCHED    | Correct — restore must keep prior snapshot                              |
| W8.10 archived → open clears       | `archived_at` + `restore_eligibility_*`  | CLEARED      | Verified to NULL                                                       |
| W8.10 hard-delete cascade          | snapshots, resolutions, audit_event       | OK by design | audit_event PRESERVED (FK off — by design); rest cascaded               |
| W8.11 PDFInputs.timeline_diff      | memo template `base.html`                 | OK + W8-m4   | Gated `≥ 2`, safe with redacted; raises on bad JSON                    |
| W8.12 render_diff_workpaper_pdf    | engagement route `/diff.pdf`              | OK           | Permission, rate limit, audit event all wired                          |
| W8.12 snapshot_diff_exported audit | format="pdf" + format="xlsx"              | OK           | Two writers, same event type, distinguished by `format` payload         |

---

## 5. END-TO-END ARCHIVE → RESTORE → HARD-DELETE FLOW TRACE

Reproduced in the project venv:

```
$ .venv/bin/python <smoke.py>

Step 1 (analyst): create_engagement → version=0
Step 2 (analyst): add_snapshot       → version=1
Step 3 (partner): transition open → archived
                  archived_at=2026-05-29 ...
                  restore_eligibility_until=2026-08-27 ... (+90 days)
                  version=2
Step 4 (partner): transition archived → open  (within window)
                  archived_at=None
                  restore_eligibility_until=None
                  version=3
                  (head_snapshot_id, bound_pack_json preserved)
Step 5 (partner): transition open → archived again → version=4
Step 6 (force-expire restore_until via UPDATE)
Step 7 (partner): transition archived → open
                  → IllegalStateTransition: restore window has expired
Step 8 (cron): hard_delete_expired_archived() → 1 engagement deleted
Step 9 (audit chain): 5 audit_event rows preserved
                      0 engagement rows
                      0 snapshot rows
```

Findings:
- The W8.10 contract holds end-to-end.
- Audit chain rows are retained as documented (legal-erasure decision
  deferred to Evelyn).
- The CSRF gate on `/restore` works because the route is registered on
  the engagement blueprint, which runs `_auth_guard` (engagement_routes.py:383)
  on every request — that helper invokes `verify_csrf()` whenever
  `auth_source == "cookie"`.
- Concurrent reads during hard-delete are safe: SQLite's default
  journal mode serializes write transactions; readers either see the
  pre-delete or post-delete state, never partial. Process-local
  `_write_lock` only protects against in-process races, but the
  conditional UPDATE pattern across the wave-2..wave-8 store
  guarantees correctness even under multi-process load. The relevant
  race here is "user is reading the engagement detail page while cron
  hard-deletes it": user gets a stale view, next refresh 404s. No
  corruption.

---

## 6. THINGS CHECKED CLEAN

- `_safe_next_url` rejects `\r\n\x00\x7f` and every other control char;
  rejects scheme/netloc; rejects protocol-relative `//evil`.
- Phase-0 gate does NOT shadow `/engagement/<id>/diff` (different
  prefix family). Verified.
- StubSSOProvider refusal triggers as designed in non-test, non-allowed
  environments; allows test and `allow_in_prod=True` paths.
- archived → open clears archival columns (verified) without touching
  `bound_pack_json` or `head_snapshot_id` (correct — restore must not
  lose state).
- hard-delete cascade leaves no orphan FK on snapshot or resolution;
  audit_event preservation is by design (legal-trail).
- xlsx byte stability of the DIFF WORKPAPER is real (verified across
  two builds 1.1s apart). openpyxl reads the rewritten zip correctly,
  sheet names + cells intact. (Live workbook stability is NOT — see
  W8-m1.)
- `safe_created_by()` is plumbed at every rendering boundary
  (`/snapshots` JSON, `/diff` JSON/HTML, diff.xlsx, diff.pdf, memo
  drift section). Defence-in-depth holds.
- `/logout` preserves CSRF cookie (`resp.set_cookie(COOKIE_NAME, "", ...)`
  but not the CSRF cookie). Comments at cookie_auth.py:303-309 are
  accurate.
- `compute_timeline_diff` handles all-redacted (returns empty rows;
  template silently omits) and partially-redacted (column blanks;
  no PII leak via `safe_*` accessors at the route layer).
- Restore route enforces CSRF (inherits from engagement blueprint
  `_auth_guard`).
- Pyproject `filterwarnings = ["ignore::pytest.PytestUnraisableExceptionWarning"]`
  silences the weasyprint/openpyxl finalizer noise; 786 tests pass
  cleanly under the wave-8 suite.
- `hard_delete_expired_archived` is idempotent (re-running after
  deletion finds no eligible rows).

---

## 7. FIX-NOW VS DEFER

| ID     | Severity | Surface                                                | Fix now? | Notes                                                                            |
|--------|----------|--------------------------------------------------------|----------|----------------------------------------------------------------------------------|
| W8-M1  | MAJOR    | /readyz returns 200 OK during DB outage                | YES      | One-line fix: set status=degraded + return 503 from the except arms              |
| W8-M2  | MAJOR    | attach_* helpers crash without identity kwarg          | YES      | Two-line fix: pass `allow_in_prod=True` to the fallback constructions            |
| W8-M3  | MAJOR    | /readyz leaks counters without auth                    | YES      | Split into anonymous + admin-gated routes, or gate by CIDR                       |
| W8-m1  | MINOR    | Live formula workbook not byte-stable                  | YES      | Shared helper + apply to all xlsx producers (live, clean, diff)                  |
| W8-m2  | MINOR    | engine_commit cache is sticky                          | YES      | Two-line invalidator; cheap insurance for hot-reload paths                       |
| W8-m3  | MINOR    | /diff prefix matches /diffx etc.                       | DEFER    | No collision today; document in code comment to prevent regression               |
| W8-m4  | MINOR    | Memo 500s if a non-head snapshot has bad JSON          | YES      | Wrap timeline-diff block in try/except; never regress generation on stale data   |
| W8-m5  | MINOR    | Dead import in cli_hard_delete_archived                | YES      | Trivial cleanup                                                                  |
| W8-m6  | MINOR    | Legacy archived rows have NULL restore_until — stranded| YES      | Add backfill SQL to the W8.10 idempotent migration block                         |
| W8-m7  | MINOR    | Sorted zip entries vs openpyxl native order            | DEFER    | Functionally correct; document next to W8.4 spec                                 |
| W8-m8  | MINOR    | Hardcoded 2026-01-01 anchor fallback                   | DEFER    | Stable + deterministic; UX-only confusion potential                              |
