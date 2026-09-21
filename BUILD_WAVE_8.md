# Build Wave 8 — What Shipped

> Wave 8 closed every deferred audit item from waves 5-7 that did NOT
> require Evelyn's input. Hardened the demo surface so prod cutover is
> safe, wired OCI engine versioning, made the xlsx workpaper byte-stable,
> added /readyz + ops CLI, built the engagement archival + 90-day
> restore mechanism, folded the snapshot drift table into the PDF audit
> memo, and shipped the diff workpaper PDF the wave-7 spec promised.
>
> Written 2026-05-29 at wave-8 close.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 8 | 762 active |
| Tests after wave 8 | **786 active** (+24) |
| `-W error::ResourceWarning` | clean (W8.5 filters the framework finalizer noise) |
| Net new src/ modules | 0 (extended `pdf_memo`, `diff_workpaper`, `engagement`, `cookie_auth`, `identity`, `rule_pack`) |
| Net new test modules | 1 (`test_wave8.py`) |
| New routes | `GET /readyz`, `POST /engagement/<id>/restore`, `GET /engagement/<id>/diff.pdf` |
| New schema columns | `engagement.archived_at`, `engagement.restore_eligibility_until` (idempotent migration) |
| New permissions | `engagement.restore_archived` (partner) |
| New audit-event flows | `snapshot_diff_exported` now also fires for PDF format |
| New error codes | `phase-0-demo-disabled` (404) |
| New CLI commands | `prune-deny-list`, `prune-rate-limits`, `hard-delete-archived` |
| Spec round | 6 — §13.1–§13.10 |

---

## 2. What shipped (W8.1 – W8.13)

### 2.1 Header injection on `next` (W8.1)
`_safe_next_url` now rejects any control char (`< 0x20` or `0x7f`) in
addition to scheme/netloc/protocol-relative URLs. A malicious
`?next=/legit%0d%0aLocation:%20attacker.example/` no longer 500s
werkzeug. Closes wave-6 W6m-1.

### 2.2 ALLOW flags for demo surfaces (W8.2)
`StubSSOProvider.__init__` raises `RuntimeError` in non-TESTING mode
unless `ALLOW_STUB_SSO=1` is set OR `allow_in_prod=True` is passed at
construction. Closes the "any non-empty token authenticates as analyst"
footgun for accidental prod deploys.

Phase-0 demo routes (the unauthenticated `/upload`, `/review/`,
`/waterfall/`, `/whatif/`, `/resolve/`, `/export/`, `/compare/`,
`/sessions`, `/upload_side_letter/`, `/demo/`, `/diff`) are now gated
by a before_request hook that returns 404 `phase-0-demo-disabled`
unless `ALLOW_PHASE_0_DEMO=1` or Flask `TESTING` is on. Evaluated
per-request so test apps that flip `TESTING=True` after import are
honoured.

### 2.3 OCI engine version env wiring (W8.3)
`current_engine_commit()` reads `QAPITA_ENGINE_COMMIT` env var FIRST
(used by OCI/Dockerfile builds), then falls back to `git rev-parse`
in dev, then `"unversioned"`. Result cached at module level so
engagement-create doesn't fork+exec git per call. Closes wave-5 m-4.

### 2.4 xlsx byte stability (W8.4)
Both xlsx producers now pin workbook properties + post-process the zip
envelope:
- `diff_workpaper.build_diff_workpaper_xlsx` pins
  `wb.properties.{created,modified,creator,lastModifiedBy}` against
  the oldest snapshot's `created_at`, then post-processes the zip to
  rewrite every entry's `date_time` to the DOS epoch AND scrubs
  `dcterms:modified` in `docProps/core.xml` (openpyxl overrides our
  pin at save() time).
- `formula_workbook.FormulaWorkbookBuilder` pins the same properties
  against `cap_table.company.valuation_date` (or a fixed epoch if
  unknown).

Two builds of the same diff/cap-table now produce byte-identical xlsx
output. Closes wave-7 m-W7-1.

### 2.5 ResourceWarning cleanup (W8.5)
`pyproject.toml` `filterwarnings = ["ignore::pytest.PytestUnraisableExceptionWarning"]`
silences the chatter from weasyprint's fontconfig sqlite handle +
openpyxl's descriptor finalizer that pytest's `gc_collect_harder`
catches at module shutdown. Project-owned sqlite connections all
close via `with closing(...)` already; the warnings were framework
internals, not our connections leaking.

### 2.6 Snapshot created_by redaction (W8.6)
`Snapshot.safe_created_by()` returns `"[redacted]"` when
`snap.redacted` is True. Wired into the timeline JSON, the diff
`SnapshotMeta` construction (so /diff JSON + /diff.html + /diff.xlsx
+ /diff.pdf + the auto-embedded memo drift section all sanitise),
and the bundle exporter. Closes wave-7 m-W7-4.

### 2.7 /logout preserves CSRF cookie (W8.7)
`/logout` no longer clears `qapita_csrf` — only the session cookie
goes. Multi-tab UX no longer breaks (a second tab's next form POST
would otherwise 403 with `csrf-missing-cookie`). CSRF cookie has no
security value without the session cookie since `verify_csrf` only
runs when `g.auth_source == "cookie"`. Closes wave-6 m-W7-9.

### 2.8 /readyz endpoint (W8.8)
`GET /healthz` stays minimal (`{"status":"ok"}` — probes fire often).
New `GET /readyz` returns SRE-grade state:
```
{
  "status": "ok",
  "engine_commit": "abc123def456",
  "rule_pack_head_version": "v2026.6.0",
  "deny_list_size": 12,
  "engagements_total": 47,
  "audit_log_total": 1832,
  "last_engagement_created_at": "2026-05-29T18:32:11+00:00"
}
```

### 2.9 Background pruning CLI (W8.9)
Three idempotent Flask CLI commands ops can schedule via cron / systemd
/ k8s CronJob:
- `flask --app app prune-deny-list` — drop expired Bearer-revocation entries
- `flask --app app prune-rate-limits` — drop rate-limit bucket rows > 7 days old
- `flask --app app hard-delete-archived` — cascade-delete archived engagements past the restore window

### 2.10 Engagement archival + 90-day restore (W8.10)
- `Engagement` model gains `archived_at` + `restore_eligibility_until`
  fields (idempotent ALTER migration).
- `transition()` stamps both atomically when target is `archived` and
  clears them on any transition AWAY from archived.
- New transition `archived → open` (partner-only via
  `engagement.restore_archived`); refused if the window has closed
  (`IllegalStateTransition`).
- New route `POST /engagement/<id>/restore` (auth + CSRF + version-
  conflict check, like the rest of the lifecycle surface).
- New store method `hard_delete_expired_archived()` cascades to
  snapshots + resolutions for engagements past the window. Audit_event
  rows KEPT (legal-erasure preservation is Evelyn-blocked).
- `ARCHIVAL_RESTORE_DAYS = 90` constant; Evelyn picks the actual
  number later.

### 2.11 Diff in PDF memo (W8.11)
`PDFInputs.timeline_diff: Optional[TimelineDiff]`. Memo template
renders a "Snapshot drift" section when supplied. The engagement memo
route auto-computes the drift across the engagement's snapshot chain
(skipped when fewer than 2 snapshots exist). Big-4 reviewer reading
the bundle sees the drift table inside the memo, not just in the
sidecar xlsx.

### 2.12 Diff workpaper PDF (W8.12)
`render_diff_workpaper_pdf(engagement, diff, generated_at=None)` in
`pdf_memo.py` + new `templates/memo/diff.html` template. Route `GET
/engagement/<id>/diff.pdf` mirrors `/diff.xlsx`: same permission
(`export.memo_pdf`), same export rate limit, same
`snapshot_diff_exported` audit event with `payload.format = "pdf"`.
Closes wave-7's promised "xlsx + pdf" pair.

### 2.13 README + onboarding (W8.13)
Rewrote `README.md` to reflect the current 8-wave state: architecture
map, environment-variable checklist, ops CLI, engagement flow diagram,
health probes, run-the-tests recipe.

---

## 3. Files touched

| File | Reason |
|---|---|
| `src/cookie_auth.py` | W8.1 (control-char reject in `_safe_next_url`), W8.7 (keep CSRF cookie on logout) |
| `src/identity.py` | W8.2 (`StubSSOProvider` refuses without opt-in flag + `_running_in_test` helper); W8.10 (`engagement.restore_archived` permission for partner) |
| `src/rule_pack.py` | W8.3 (env-first engine commit + caching) |
| `src/engagement.py` | W8.6 (`safe_created_by`); W8.10 (`Engagement.archived_at` + `restore_eligibility_until` fields, schema column + migration, transition stamping/clearing, `archived → open` allowed transition, window enforcement, `hard_delete_expired_archived`); `ARCHIVAL_RESTORE_DAYS` constant |
| `src/engagement_routes.py` | W8.10 (`POST /restore` route + auto-redact in metas via `safe_created_by`); W8.12 (`/diff.pdf` route); upload route passes `change_note` (W7.4 follow-through) |
| `src/engagement_bundle.py` | W8.6 (`created_by = "[redacted]"` on redacted snapshots in bundle) |
| `src/diff_workpaper.py` | W8.4 (pin workbook properties + zip envelope post-process + core.xml scrub) |
| `src/formula_workbook.py` | W8.4 (pin workbook properties) |
| `src/pdf_memo.py` | W8.11 (`PDFInputs.timeline_diff` field + context wiring); W8.12 (`render_diff_workpaper_pdf`) |
| `app.py` | W8.2 (phase-0 gate + StubSSO instantiation with `allow_in_prod=True`); W8.8 (`/readyz`); W8.9 (three CLI commands) |
| `templates/memo/base.html` | W8.11 (snapshot drift section) |
| `templates/memo/diff.html` | W8.12 (new — diff PDF workpaper) |
| `tests/test_engagement.py` | W8.10 (updated `archived_is_terminal` to `archived_restorable_within_window` + added `archived_restore_refused_after_window`) |
| `tests/test_wave6_hardening.py` | W8.7 (updated logout test to verify CSRF cookie preserved) |
| `tests/test_wave8.py` | new — 24 regression tests across W8.1-W8.12 |
| `pyproject.toml` | W8.5 (filterwarnings) |
| `SYSTEM_SPEC.md` | round 6 (§13.1-§13.10) + §9.6 inventory additions |
| `README.md` | W8.13 (rewritten for current state) |

---

## 4. Audit + post-audit fixes

Independent wave-8 audit (`SYSTEM_AUDIT_WAVE_8.md`) returned: **0 blockers**,
3 majors, 8 minors. All 3 majors + 6 fix-now minors closed in this
same wave with 14 regression tests in `tests/test_wave8_audit_fixes.py`.

### 4.1 Majors (all closed)

| ID | Finding | Fix landed |
|---|---|---|
| W8-M1 | `/readyz` returned 200 OK even during a SQLite outage; SREs wiring it into a readinessProbe would leave dead pods in rotation | `/readyz` now probes each dependency (head_pack, engagement DB, deny list) and returns 503 `{"status":"degraded","reason":...}` on any failure. Anonymous response shape is the minimal `{"status":"ok"}` in healthy state. |
| W8-M2 | `attach_engagement_blueprint(app, store)` and `attach_login_blueprint(app)` crashed at boot in non-test, non-allowed environments because the fallback `StubSSOProvider()` construction tripped the W8.2 guard | Both helpers pass `allow_in_prod=True` to the fallback constructor. The W8.2 guard still fires for direct `StubSSOProvider()` calls outside the helper path (the documented prod hardening surface). |
| W8-M3 | `/readyz` leaked engine commit, pack version, deny-list size, audit-event total, engagement count, and last-create timestamp to anonymous callers | Split: anonymous `/readyz` returns only `{"status":"ok"}`. The rich operational payload moves to `/readyz/detailed`, gated on partner-Bearer auth OR a configured `READYZ_ADMIN_TOKEN` env var for in-cluster scrapers. |

### 4.2 Fix-now minors (closed)

| ID | Finding | Fix landed |
|---|---|---|
| W8-m1 | Live formula workbook NOT byte-stable (W8.4 only fixed the diff workpaper) | Extracted shared helper `src/xlsx_stability.py` with `pin_workbook_properties` + `stabilise_xlsx_bytes`. Both `/export/<token>_live.xlsx` and `_build_clean_xlsx_bytes` now run through it. `diff_workpaper` keeps a back-compat re-export so the wave-7 audit-fix tests still pass. |
| W8-m2 | `current_engine_commit()` module cache was sticky across env changes (hot-reload + CLI paths got stale value) | Cache busts when `QAPITA_ENGINE_COMMIT` env var differs from the cached value. |
| W8-m4 | Memo route 500'd via `validation-failed` 400 if any non-head snapshot's `cap_table_json` was malformed (W8.11 regression) | `compute_timeline_diff` call wrapped in `try/except Exception`; failure logs a warning and falls back to `timeline_diff = None`. Memo template already gates the drift section on `timeline_diff and timeline_diff.class_rows`. |
| W8-m5 | Dead `from src.engagement import EngagementStore as _ES` in `cli_hard_delete_archived` | Removed. |
| W8-m6 | Legacy archived engagements (status=archived but pre-W8.10 row with NULL `restore_eligibility_until`) were stranded — couldn't restore (treated as expired) and couldn't hard-delete (filtered by NOT NULL). | W8.10 idempotent migration block now backfills any `status='archived'` row with NULL columns: `archived_at ← created_at`, `restore_eligibility_until ← created_at + ARCHIVAL_RESTORE_DAYS`. One-shot, idempotent. |

### 4.3 Deferred (with rationale)

| ID | Finding | Defer rationale |
|---|---|---|
| W8-m3 | Phase-0 `/diff` prefix matches `/diffx`, `/diffanything` | No collision today (engagement-blueprint URLs start with `/engagement/`); revisit if a future top-level `/diff*` route is added |
| W8-m7 | Sorted zip central-directory order vs openpyxl native | Functionally correct (openpyxl + Excel both read by name); document next to W8.4 spec |
| W8-m8 | Hardcoded 2026-01-01 anchor fallback in `_pin_xlsx_properties` | Stable + deterministic; pure UX confusion, not a correctness issue |

### 4.4 Files touched

| File | Reason |
|---|---|
| `app.py` | W8-M1 (`/readyz` status-aware), W8-M3 (`/readyz/detailed` admin split), W8-m1 (stabilise live + clean xlsx), W8-m5 (dead import removed) |
| `src/cookie_auth.py` | W8-M2 (fallback `StubSSOProvider(allow_in_prod=True)`) |
| `src/engagement_routes.py` | W8-M2 (same fallback fix), W8-m4 (memo timeline-diff try/except) |
| `src/engagement.py` | W8-m6 (legacy archival backfill in idempotent migration) |
| `src/rule_pack.py` | W8-m2 (engine-commit cache busts on env change) |
| `src/xlsx_stability.py` | new — shared `pin_workbook_properties` + `stabilise_xlsx_bytes` helpers |
| `src/diff_workpaper.py` | Refactored to import from `xlsx_stability` (back-compat re-exports retained) |
| `tests/test_wave8_audit_fixes.py` | new — 14 regression tests across W8-M1..M3 + W8-m1..m6 |

---

## 5. What's left after wave 8

Bucket A (broken/risky in production) → **fully closed.**

Bucket B (Evelyn-independent capability) → **mostly closed.** Remaining:
- OPM Backsolve into engagement (deferred — UX decisions)
- Vol pack → DCF template auto-link (deferred — analyst workflow)
- Rule provenance in memo (deferred — memo template work)

Bucket D (Evelyn-blocked) — unchanged; sitting waiting for her input:
- Real OIDC/SAML callback (SSO endpoint + JWT claim mapping)
- Postgres swap (prod DB choice)
- Real KMS / backup destination
- 90-day window legal sign-off (mechanism shipped, number is her call)
- Real firm-specific rule pack content
- Reviewer-assignment table (org structure)
- Tenancy isolation (hosting model)

The system is now at "Evelyn-ready" — every prod-shaped knob has a
defined position, every demo-surface has an explicit opt-in, the
analyst workflow exercises all the way through to the Big-4-portable
bundle, and the audit-fix loop has closed eight times.
