# Build Wave 9 — What Shipped

> Wave 9 closed three Evelyn-independent deferred items from prior
> audits (W6M-6 CSRF rotation, W7m-3 NaN guard, W8-m3 phase-0
> anchoring) and shipped three analyst-facing capabilities that didn't
> need Evelyn's input: rule provenance in the PDF memo, engagement-
> bound OPM Backsolve, and a vol-pack → DCF sidecar suggestion plumb.
> Plus snapshot pagination, a rule-coverage CLI, and spec round 7.
>
> Written 2026-05-30 at wave-9 close.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 9 | 800 active |
| Tests after wave 9 | **819 active** (+19) |
| Net new src/ modules | 0 (extended `pdf_memo`, `dcf_sidecar`, `rule_pack`, `cookie_auth`, `engagement_routes`, `app`) |
| Net new test modules | 1 (`test_wave9.py`) |
| New routes | `POST /engagement/<id>/opm` |
| New audit-event types | `opm_backsolve_run` |
| New error codes | `opm-bad-inputs` (400), `bad-pagination` (400) |
| New CLI commands | `rule-coverage` |
| Spec round | 7 — §14.1-§14.9 |

---

## 2. What shipped (W9.1 – W9.8)

### 2.1 Rule provenance in the PDF memo (W9.1)
`rule_pack.finding_provenance_map(cap_table, pack=None)` returns
`{finding.code: {"rule_id", "citation", "pack_version"}}` by replaying
the pack and tracking emission. The PDF memo's findings table gains
a "Rule provenance" column showing `rule_id (pack_version)` + the
rule's citation. Big-4 reviewers reading the memo no longer have to
cross-reference `rule_packs/*.json` to find the legal basis for each
finding.

### 2.2 Engagement-bound OPM Backsolve (W9.2)
New route `POST /engagement/<id>/opm`. Wraps `opm.backsolve` against
the head snapshot's cap table. The analyst supplies every input
(volatility, TTL, risk-free, DLOM, anchor class + PPS — the tool does
NOT pick these). Permission `engagement.read`, compute-rate-limited
via COMPUTE_LIMITER, writes `opm_backsolve_run` audit event with
inputs + solved equity value so the chain captures the calibration
moment. Refuses on no-snapshot, redacted snapshot, missing inputs,
unresolved blockers (via `BacksolveBlockersOutstanding`), and solver
failure.

### 2.3 Vol pack → DCF sidecar suggestion (W9.3)
`build_dcf_sidecar(cap_table, vol_pack_readback=None)` accepts an
optional `VolPackReadback`. When supplied, the "Read me" sheet
surfaces volatility / TTL / risk-free / DLOM as analyst-readable
text — explicitly NOT as defined names the DCF model auto-pulls.
Preserves the "expert-led, not algorithm-only" register (§10.1 intent).
The analyst still types the final number into their WACC cell.

### 2.4 Phase-0 prefix anchoring (W9.4 / closes W8-m3)
`_PHASE_0_PREFIXES` split into `_PHASE_0_EXACT` (frozenset of exact
paths: `/upload`, `/diff`, `/sessions`) plus true prefixes with
trailing slash (`/diff/`, `/sessions/`, etc.). A future top-level
`/diffx` or `/sessions-list` route would no longer be silently 404'd.

### 2.5 CSRF token rotation (W9.5 / closes W6M-6)
Tokens now carry an issuance-time prefix: `<unix_seconds>.<random>`.
The engagement blueprint's `after_request` hook rotates the cookie
when its age exceeds `CSRF_ROTATION_SECONDS = 3600`. Pre-W9.5 opaque
tokens are treated as stale and rotated immediately — deploy upgrade
heals itself. A leaked token's blast radius drops from 7 days to 1 hour.

### 2.6 NaN guard in `_classify_pct` (W9.6 / closes W7m-3)
`snapshot_timeline._classify_pct` raises `ValueError` if either prior
or current is NaN — surfaces a corrupt CapTable at the diff layer
instead of silently classifying as 'major'.

### 2.7 Snapshots pagination (W9.7)
`GET /engagement/<id>/snapshots?limit=N&offset=M`. Default `limit=50`
(max 100), `offset=0` so the existing JSON API stays compatible. HTML
view renders `showing N of TOTAL` + prev/next links. Bad pagination
returns 400 `bad-pagination`.

### 2.8 Rule coverage CLI (W9.8)
`flask --app app rule-coverage` runs every registered rule against
every fixture and reports `rule_id → fixtures-where-it-fires`. Surfaces
rules with zero coverage (dead-code review prompt) without running the
test suite.

---

## 3. Files touched

| File | Reason |
|---|---|
| `src/rule_pack.py` | W9.1 (`finding_provenance_map`) |
| `src/pdf_memo.py` | W9.1 (import + per-finding provenance lookup in `_build_context`) |
| `templates/memo/base.html` | W9.1 (new Rule provenance column) |
| `src/engagement_routes.py` | W9.2 (`/opm` route); W9.5 (rotation in `_heal_csrf_cookie`); W9.7 (pagination) |
| `src/engagement.py` | W9.2 (`AuditEventType.opm_backsolve_run`) |
| `src/dcf_sidecar.py` | W9.3 (`vol_pack_readback` parameter) |
| `src/cookie_auth.py` | W9.5 (`issue_csrf_token` + `csrf_token_age_seconds` + `CSRF_ROTATION_SECONDS`) |
| `src/snapshot_timeline.py` | W9.6 (NaN guard) |
| `templates/engagement/snapshots.html` | W9.7 (pagination chrome) |
| `app.py` | W9.4 (phase-0 prefix split); W9.8 (`rule-coverage` CLI) |
| `tests/test_wave9.py` | new — 19 regression tests |
| `tests/test_wave6_hardening.py` | W9.5 (updated csrf token format test) |
| `SYSTEM_SPEC.md` | round 7 (§14.1-§14.9) + §9.6 inventory additions |

---

## 4. Audit + post-audit fixes

Independent wave-9 audit (`SYSTEM_AUDIT_WAVE_9.md`) returned **1
blocker**, 4 majors, 7 minors. All closed except 2 minors that the
audit itself flagged as defer-acceptable. 23 regression tests in
`tests/test_wave9_audit_fixes.py`.

### 4.1 Blocker (closed)

| ID | Finding | Fix landed |
|---|---|---|
| W9-B1 | CSRF rotation race: `_inject_csrf` rendered the OLD token into the form body, then `_heal_csrf_cookie` rotated the cookie to NEW. The very next form POST 403'd `csrf-mismatch`. The W9.5 "closes W6M-6" claim was strictly worse than the original. | The single decision point for rotation now lives in `_inject_csrf`: it picks the chosen token (auto-heal / rotate / pass-through), stashes on `g._minted_csrf`, and returns it as the template variable. `_heal_csrf_cookie` attaches whatever `g._minted_csrf` says. Template body and response cookie now agree on the same token regardless of rotation timing. |

### 4.2 Majors (all closed)

| ID | Finding | Fix landed |
|---|---|---|
| W9-M1 | Snapshots pagination was render-side only — `list_snapshots` still `SELECT *` loaded every snapshot (with `cap_table_json` blobs) before slicing. `?limit=1` paginated the response but not the DB read. | `list_snapshots(engagement_id, *, limit=None, offset=0)` now pushes LIMIT/OFFSET into SQL. New `count_snapshots(engagement_id)` for the total. Default behaviour (no kwargs) preserves backward compat for memo / bundle / timeline-diff callers. |
| W9-M2 | OPM route accepted negative volatility, NaN, Inf, out-of-range rfr/dlom — Black-Scholes squares σ, so a sign typo produced a "defendable" 200 response. Violated the "expert-led, not algorithm-only" register. | `MarketInputs.__post_init__` rejects NaN/Inf, negative volatility, out-of-range TTL/rfr/dlom/dividend_yield with `BacksolveError`. The /opm route catches and returns 400 `opm-bad-inputs` before the audit event lands. |
| W9-M3 | `finding_provenance_map` called without `engagement_jurisdiction` from the memo path. For cross-jurisdiction code reuse (two rules sharing a code template across regions), last-write-wins on the dict → memo rendered the wrong rule_id + citation. | `_build_context` reads `ct.company.jurisdiction` and passes it through to `finding_provenance_map(..., engagement_jurisdiction=...)`. |
| W9-M4 | OPM route consumed COMPUTE_LIMITER but never emitted `compute_burst_alert` at the hard-limit boundary — abuse stayed out of the audit chain. | Lifted the four-line block from `/whatif`; payload carries `"route": "opm"`. |

### 4.3 Fix-now minors (closed)

| ID | Finding | Fix landed |
|---|---|---|
| W9-m2 | `csrf_token_age_seconds` returned negative ages for future-dated tokens; the rotation check `age > 3600` never fired. | Rotation predicate now `age is None or age > CSRF_ROTATION_SECONDS or age < 0`. |
| W9-m5 | DCF sidecar's vol-pack block used hard-coded rows A9..A16; future Read-me additions would silently overwrite. | Rows computed dynamically off `rm.max_row`. |
| W9-m6 | OPM error_codes derived from `type(exc).__name__.lower()` produced `backsolveanchormissing`, `backsolvesolverfailed` — brittle to future renames, not stable kebab-case. | `_OPM_ERROR_CODES` explicit map → `backsolve-anchor-missing`, `backsolve-solver-failed`, `backsolve-blockers-outstanding`. |
| W9-m7 | `VolPackReadback.sourcing` dict captured at parse time but never surfaced — defeated the defensibility intent. | "Sourcing notes (analyst-supplied)" sub-block in the sidecar Read-me renders the dict verbatim. |

### 4.4 Deferred (audit-flagged as acceptable)

| ID | Finding | Defer rationale |
|---|---|---|
| W9-m1 | `_heal_csrf_cookie` + `_inject_csrf` can mint two distinct tokens per request if a view skips template render | Now closed in practice: the `_inject_csrf` refactor for B-1 made it the only place that mints. Edge case where a route returns `jsonify` without invoking the context_processor — the after_request hook reads `g._minted_csrf` which is None → no cookie write. Benign. |
| W9-m3 | `rule-coverage` CLI silently skips fixtures missing `cap_table.xlsx` | Cosmetic; print a warning when convenient |
| W9-m4 | `rule-coverage` CLI crashes if `fixtures/` is absent | Rare ops scenario (minimal Docker image); add try/except later |

### 4.5 Files touched (post-audit fix batch)

| File | Reason |
|---|---|
| `src/engagement_routes.py` | W9-B1 (`_inject_csrf` owns rotation decision); W9-M1 (route uses new SQL pagination); W9-M2 + m-6 (kebab-case error code map); W9-M4 (compute_burst_alert for /opm) |
| `src/engagement.py` | W9-M1 (`list_snapshots(*, limit, offset)` + `count_snapshots`) |
| `src/opm/backsolve.py` | W9-M2 (`MarketInputs.__post_init__` domain checks) |
| `src/pdf_memo.py` | W9-M3 (threads `ct.company.jurisdiction` through to provenance map) |
| `src/dcf_sidecar.py` | W9-m5 (dynamic rows); W9-m7 (sourcing surface) |
| `tests/test_wave9_audit_fixes.py` | new — 23 regression tests |

---

## 5. What's left after wave 9

Deferred audit minors that didn't close:
- W7m-1 (xlsx byte stability — closed in wave 8)
- W7m-4 created_by redaction (closed in wave 8 as W8.6)
- W7m-7 diff HTML link order (comment-only)
- W8-m7 sorted zip central directory (documented)
- W8-m8 hardcoded 2026-01-01 anchor (UX-only)

Remaining Evelyn-blocked work (unchanged):
- Real OIDC/SAML callback
- Postgres swap
- Real KMS / backup destination
- 90-day window legal sign-off
- Real firm-specific rule pack content
- Reviewer-assignment table
- Tenancy isolation

After 9 waves the system has:
- 819 tests across 8 audit cycles
- Every audit fix encoded as a regression test (one test per finding code)
- Spec consolidated across 7 amendment rounds
- Architecture documented in `README.md`, `SYSTEM_SPEC.md` (1700+ lines),
  `OPERATIONS.md`, and 9 per-wave build notes
- Every operational footgun has an ops CLI hook
- Every prod-shaped knob has a defined opt-in flag
- Every analyst flow runs end-to-end to the Big-4 bundle, with the
  drift table both in the memo and as a stand-alone xlsx + pdf workpaper
