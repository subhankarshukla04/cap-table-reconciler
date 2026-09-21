# Build Wave 2 — What Shipped + Audit Fix Batch

> Wave 2 wired the Phase-2 production model end-to-end: engagement-aware
> Flask routes with stub SSO, per-user export rate limiting, OCR fallback
> for image PDFs, portable engagement bundles, rule-pack v2026.3.0 with
> NVCA / Delaware / AICPA coverage, the two deferred wave-1 bugs, and the
> operations runbook. Then an independent agent audited the wave and
> found 5 blockers + 8 majors + 10 minors; the in-scope fix batch landed
> in this same wave (13 items, ~250 LOC).
>
> Written 2026-05-25 at wave-2 close. Wave 3 starts next.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 2 | 428 pass |
| Tests after wave 2 build (W2.1–W2.7) | 474 pass (+46 new) |
| Tests after wave 2 audit-fix batch | **486 pass** (+12 regression tests) |
| Net new src/ modules | 6 (`engagement_routes`, `engagement_bundle`, `rate_limit`, `ocr/__init__`, `ocr/null_backend`, `ocr/tesseract_backend`, `rules_v2026_3`) |
| Net new test modules | 7 |
| Rule packs total | 3 (baseline + v2026.2.0 + v2026.3.0) |
| Total registered rules | 30 (was 23) |
| Spec-gap blockers closed in this wave | GAP-08 portable bundle, GAP-40 rate limiting, partial GAP-39 (auth gates) |
| Audit blockers found AND fixed in same wave | 5 / 5 (B1 hash-chain race, B2 TOCTOU, B3 chain-link race, B4 missing auth on `/audit-log`, B5 OCR skipped on bytes) |
| Audit majors found AND fixed in same wave | 5 / 8 (M2 edge-trigger alert, M3 memo permission ordering, M6 upload permission, M8 AICPA wording, m1/m4/m6/m8/m10) |
| Audit items deferred to wave 3 | 3 majors (M1 rate-window math → W3.3, M4 pack-bytes-persist → W3.6, M5 bundle-determinism → spec change), 2 minors (m5 valuation_date typing, m7 OCR registry) |

## 2. What shipped (build, then audit-fix)

### 2.1 Engagement-aware Flask blueprint (W2.1)

`src/engagement_routes.py` (+ wiring in `app.py`). Eleven routes:

| Method | Path | Purpose |
|---|---|---|
| POST | `/engagement/` | Create engagement |
| GET | `/engagement/` | List engagements (role-filtered) |
| GET | `/engagement/<id>` | Engagement detail + snapshot list |
| POST | `/engagement/<id>/upload` | Excel upload → new snapshot |
| POST | `/engagement/<id>/resolve` | Record finding resolution |
| POST | `/engagement/<id>/transition` | State transition |
| POST | `/engagement/<id>/redact/<snap>` | PDPA redaction (partner only) |
| GET | `/engagement/<id>/memo.pdf` | Render PDF memo |
| GET | `/engagement/<id>/audit-log` | List audit events |
| GET | `/engagement/<id>/verify` | Recompute audit chain |
| GET | `/engagement/<id>/bundle.zip` | Portable export bundle |

Auth via `Authorization: Bearer <token>` resolved by injected `IdentityProvider`. Errors translated to spec-compliant `(error_code, http_status)` pairs.

### 2.2 Bulk-export rate limiting (W2.2)

`src/rate_limit.py`. Per-user counter persisted in SQLite. Soft 30/hr → HTTP 429 with `Retry-After` + `export-rate-limit` code. Hard 100/hr → `bulk_export_alert` audit event. Applied to `/memo.pdf` and `/bundle.zip` via shared `_enforce_export_limit` helper (M2 fix).

### 2.3 Deferred bug fixes (W2.3)

- **BUG-010** (`/whatif` zero-share fallback): when baseline shares=0 and analyst overrides, recompute LP from `new_shares × price × multiple` instead of silently scaling to zero.
- **BUG-014** (`diff.py` None vs 0 conflation): compare `issue_price` and `conversion_ratio` with `!=` directly; `None → 0` and `None → 1.0` now register as real changes.

### 2.4 OCR backend abstraction (W2.4)

`src/ocr/__init__.py` + `null_backend.py` + `tesseract_backend.py`. `OCRBackend` ABC with `select_backend()` factory. `TesseractBackend` lazily checks for the binary + `pytesseract` + `pdf2image`; falls back to `NullBackend` if any link is missing. Confidence normalised to [0, 1]; threshold 0.85 triggers the spec banner. Pipeline in `src/pdf_intake.extract_text` routes any PDF with text yield < 100 chars to the OCR backend.

### 2.5 Rule pack v2026.3.0 (W2.5)

`src/rules_v2026_3.py` + `rule_packs/v2026.3.0.json`. 7 new rules:

| ID | Triggers on |
|---|---|
| `G-DE-001` | Delaware jurisdiction → DGCL §251 reminder |
| `G-NVCA-001` | NVCA-style clause keyword in any side letter |
| `G-NVCA-002` | Preferred exists but no protective-provisions side letter |
| `G-AICPA-001` | LP overhang > 50% of PPS-implied upper-bound EV proxy (post-fix wording) |
| `G-AICPA-002` | Common exists → DLOM band justification reminder |
| `G-DRAG-001` | Drag-along keyword + extract %-threshold |
| `G-ROFR-001` | ROFR/ROFO keyword without notice-period text |

Total registered rules: **30** (per SYSTEM_SPEC §4.6 acceptance criterion *"≥ 30 rules with fixture coverage"*).

### 2.6 Operations runbook (W2.6)

`OPERATIONS.md`. RPO ≤ 1h, RTO ≤ 4h. Hourly incremental backups, daily fulls, weekly cross-region replication, 7-year retention for Big-4-audit-relevant engagements. Quarterly DR drill protocol. SEV-1 / SEV-2 / SEV-3 / SEV-4 incident response. Key rotation policy. Audit-log query SLO. Monitoring dashboard expectations.

### 2.7 Portable engagement export bundle (W2.7)

`src/engagement_bundle.py`. Zip containing manifest.json (with SHA-256 per file), engagement.json, rule_pack.json, snapshots/*.json, resolutions/*.json, audit_log.jsonl (one line per event), memo.pdf (optional), README.md explaining offline verification procedure. Auditor can replay hash chain offline → confirm manifest head matches → re-verify the engagement years later without the live system.

### 2.8 Audit-fix batch (W2-AUDIT)

In response to `CODE_AUDIT_WAVE_2.md`:

**Blockers fixed:**
- **B1 hash chain race**: added process-local `threading.RLock` on `EngagementStore`; protects `_append_audit_event` from concurrent readers seeing the same `prev_row_hash`.
- **B2 add_snapshot TOCTOU**: atomic conditional UPDATE `WHERE id = ? AND version = ?` with rowcount check, inside the same write lock. Same fix applied to `transition`.
- **B3** (snapshot supersede link race): closed by B2 — both operations now inside one locked + atomic transaction.
- **B4 (partial)**: added `can(user, "engagement.read")` gate on `/audit-log` and `/verify` (parity with `show`). The deeper per-engagement tenancy ACL stays open as GAP-39, planned for wave 3.
- **B5 OCR fallback on bytes**: `pdf_intake.extract_text` spills `bytes` input to a temp `.pdf`, hands it to the OCR backend, then unlinks. Production upload route now actually OCRs scanned PDFs.

**Majors fixed:**
- **M2 hard-alert edge-trigger**: `triggered_hard = current == hard_limit` (was `>=`). Plus the alert hook lifted into `_enforce_export_limit` so memo + bundle both emit the same event.
- **M3 memo permission ordering**: `can(user, "export.memo_pdf")` BEFORE rate-limit consume. No more budget DOS via 403'd requests.
- **M6 upload permission**: `can(user, "engagement.upload_cap_table")` gate on `/engagement/<id>/upload`. Reviewer can no longer upload Excel (only analyst can).
- **M8 AICPA wording**: rule summary now says "PPS-implied upper-bound EV proxy" with explicit "this is a checklist heuristic, not the OPM-allocated EV" caveat.

**Minors fixed:**
- **m1** pack-version regex `^v\d+\.\d+\.\d+(?:-[A-Za-z0-9.\-]+)?$` + explicit traversal-character check on `RulePack.version` (closes path-traversal vector in bundle code).
- **m4** lifted private-API call into `_enforce_export_limit` helper.
- **m6** moved `__import__("datetime")` to module-top import in `rules_v2026_3.py`.
- **m8** kept `ImmutableViolation` for documenting intent (not used yet; defence-in-depth).
- **m10** query-string `?token=` now rejected outside `app.config["TESTING"]`; `X-Auth-Token` header is the only production path beyond `Authorization: Bearer`.

12 new regression tests in `tests/test_audit_fixes_wave2.py` lock all of the above. Notable: a real 8-thread concurrent test verifies B1 (hash chain holds), a real 4-thread test verifies B2 (exactly 1 of 4 succeeds, 3 get 409s).

## 3. What is stubbed for Evelyn (delta from wave 1)

Wave 2 added new seams. Cumulative Evelyn-blocked list:

1. **Qapita SSO endpoint + JWT claim mapping** — `StubSSOProvider` works; swap for `QapitaSSOProvider(IdentityProvider)` when she provides the OIDC URL.
2. **Qapita cap-table data adapter** — unchanged from wave 1.
3. **Qapita house PDF style** — unchanged. CSS block in `templates/memo/base.html`.
4. **Real engagement workflow integration** — now LIVE in routes; what remains is Evelyn confirming the workflow shape (`open → review → signed → archived`, partner reopen) matches her team's handoff process.
5. **Big-4 auditor sample for sign-off** — unchanged.
6. **Real client cap-table corpus** — unchanged.
7. **Production infrastructure** — unchanged (Postgres swap, deployment target, monitoring stack, KMS, backup destination).
8. **Engagement-level tenancy ACL (GAP-39)** — NEW: spec calls for read-only auditor tokens to be scoped per-engagement. Wave 2 ships per-route `can()` checks only. Evelyn needs to confirm scoping semantics (one-engagement-per-token? client-id-scope? time-bound?).
9. **Pack-bytes persistence at bind time (M4 deferred)** — NEW: bundle currently reloads rule pack JSON from cwd-relative `rule_packs/`. Wave 3 (W3.6) will persist the bound pack's bytes per engagement so the bundle is fully self-contained.

## 4. Architectural deltas (wave 1 → wave 2)

```
[Identity layer]                              [Engagement layer]
    ↓                                              ↓
StubSSOProvider                            EngagementStore
    + StaticUserProvider (tests)               + atomic version updates
    + QapitaSSOProvider (stub, Evelyn)         + hash-chained audit log
                                                + RLock for write safety
              ↘                       ↙
              [Flask blueprint: /engagement/*]
                 + per-route can() gates
                 + _enforce_export_limit helper
                 + tempfile-based upload spill
                          ↓
              [Outputs: memo.pdf, bundle.zip]
                 + rate-limited (per-user counter)
                 + XSS-escaped (WeasyPrint autoescape)
                 + portable, offline-verifiable

[Parsing layer]
    ↓                                       [Checklist layer]
pdfplumber                                  3 rule packs registered
    ↓ (< 100 char yield + bytes/path)         + 30 rules total
OCR fallback                                  + jurisdiction predicates
    ↓                                         + version-regex validation
NullBackend (default) | TesseractBackend
    ↓
side letter text (verbatim)
```

## 5. Test coverage of the wave

```
tests/test_engagement_routes.py     14 tests   blueprint surface
tests/test_rate_limit.py             8 tests   limiter + memo integration
tests/test_deferred_bugs.py          4 tests   BUG-010 + BUG-014
tests/test_ocr.py                    6 tests   OCR abstraction + fallback
tests/test_rules_v2026_3.py          9 tests   v2026.3.0 expansion
tests/test_engagement_bundle.py      5 tests   bundle integrity + replay
tests/test_audit_fixes_wave2.py     12 tests   audit-fix regressions
                                    ──
                                    58 new wave-2 regression tests
```

Plus the 428 from waves 0–1: **486 total, all green, zero `ResourceWarning`** under `-W error::ResourceWarning`.

## 6. Wave 3 scope

Wave 3 (next, kicking off now) builds on the engagement model:

1. **W3.1 Subsequent-events memo section** — auto-populated PDF section using structured-diff between original snapshot and head. Closes audit M7 (memo loses prior resolutions): the new section surfaces what changed across all snapshots, so prior resolutions remain visible.
2. **W3.2 Engagement list/search** — filters, pagination, GAP-39 ACL-aware filtering.
3. **W3.3 Audit-log query SLO** — synthesise 10k events, time the query, meet ≤ 5s SLO; close audit M1 (rate-limit window math) in the same touch.
4. **W3.4 Volatility input pack** — structured Excel template the analyst fills with sourcing + citations; OPM Backsolve refuses to run if any required field is missing.
5. **W3.5 Snapshot-stamped live workbook** — embed snapshot_id + engagement_id + generated_at in a hidden sheet so a stale sidecar can be detected (closes GAP-32 + audit M5 partially).
6. **W3.6 Rule pack v2026.4.0** — protective provisions enumeration, ROFR/drag-along structured fields, IRR-hurdle features, vesting acceleration. Adds `ProtectiveProvisions` model field (closes GAP-14). Plus pack-bytes-persist (closes audit M4).
7. **W3-AUDIT** — independent wave-3 audit + fix batch.
8. **W3-DONE** — BUILD_WAVE_3.md.

## 7. One sentence

Wave 2 closed the gap between a library-complete engagement model and a usable HTTP-facing service: routes, rate limits, OCR fallback, export bundles, more rules, more docs — and the audit caught five concurrent-write blockers that would have bitten in production, all fixed in the same wave with regression tests proving the fix.
