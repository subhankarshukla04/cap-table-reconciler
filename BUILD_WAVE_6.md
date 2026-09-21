# Build Wave 6 — What Shipped

> Wave 6 was the hardening wave: close every deferred item the wave-5
> stitched audit punted on, and build the cross-wave integration test
> surface that audit explicitly asked for. No new features; production
> readiness only.
>
> Written 2026-05-26 at wave-6 close.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 6 | 682 active |
| Tests after wave 6 | **700 active** (+18) |
| `-W error::ResourceWarning` | clean (2 pre-existing weasyprint/openpyxl GC warnings) |
| Net new src/ modules | 1 (`token_deny`) |
| Net new test modules | 2 (`test_wave6_integration`, `test_wave6_hardening`) |
| Spec rounds | round 4 — §11.1 CSRF, §11.2 Bearer revocation, §11.3 collision guard, §11.4 integration harness |
| New OPERATIONS.md sections | §10.1–§10.7 (env vars, CSRF, Bearer revocation, startup checks, proxy config, integration harness, smoke tests) |

---

## 2. What shipped (W6.1 – W6.6)

### 2.1 CSRF on every cookie-authenticated POST (W6.1)
Double-submit cookie pattern (no Flask-WTF dep). `/login` issues a
`qapita_csrf` cookie alongside the session; HTMX forms render the value
as a hidden input + `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'`.
Engagement blueprint's `before_request` calls `verify_csrf()` only when
`g.auth_source == "cookie"` — Bearer-authenticated requests are exempt
because the credential is explicit (matches the SD-AUD-B5 model).
Mismatch returns 403 `csrf-mismatch`; missing cookie returns 403
`csrf-missing-cookie`. `/logout` clears both cookies.

Closed wave-5 deferred item M-6.

### 2.2 Startup finding-code collision check (W6.2)
`src/rule_pack.py` gains `assert_no_collisions_at_startup(strict=True)`.
App boot runs every registered rule against a programmatic
representative cap table (common + ESOP pool + 2 preferred classes with
mixed LP variants and AD) and refuses to start if any two rules emit
the same `Finding.code`. TESTING mode soft-fails to log so test apps
override the probe table safely.

Closed wave-5 deferred item M-10.

### 2.3 Cross-wave integration test harness (W6.3)
`tests/test_wave6_integration.py` drives one engagement through every
wave's surface end-to-end — the audit's #1 ask after the stitched audit
caught six blockers no unit test could find. 8 tests cover:

| Flow | Auth | Wave seams |
|---|---|---|
| login → create → upload → resolve → review → signed | cookie + CSRF | W5.7, W6.1, W4 HTMX, W2, W3 |
| Bundle byte stability across two regenerations | Bearer | SD-AUD-B2, W3 |
| Bearer revocation via /logout | Bearer | W6.4 |
| Stale `expected_version` upload → 409 | Bearer | W2, SD-AUD-B6 |
| Compute hard-limit alert in audit log | Bearer | W5.5, SD-AUD-M2 |
| CSRF mismatch on form POST → 403 | cookie | W6.1 |
| CSRF missing cookie on cookie auth → 403 | cookie | W6.1 |
| Unresolved blocker prevents signed transition | Bearer | §9.3 gate |

### 2.4 Bearer revocation + deny list (W6.4)
New `src/token_deny.py` exposes `TokenDenyList` (SQLite, SHA-256 hash
storage — never raw tokens). `/logout` with `Authorization: Bearer
<tok>` adds the hash to the deny list. `_require_user` consults the
deny list before identity resolution; a revoked token authenticates
as nobody and falls through to the cookie or 401 path. Operators
prune the table periodically using the SSO max token lifetime as
cutoff.

Closed wave-5 deferred item SD-AUD-B5 (second half).

### 2.5 `load_workbook` close on exception (W6.5)
`src/parser.py::parse_excel` wraps the body in `try/finally` so the
workbook handle releases even when parse fails. Closes wave-5 deferred
item m-6.

### 2.6 OPERATIONS.md prod checklist + spec sweep (W6.6)
`OPERATIONS.md §10` — required env vars table (SESSION_SECRET_KEY,
QAPITA_ALLOW_DEV_PACK, QAPITA_ENGINE_COMMIT), CSRF deploy notes, Bearer
revocation deploy notes, startup-check deploy notes, ProxyFix recipe for
TLS-terminating reverse proxies, smoke test commands.

`SYSTEM_SPEC.md` — §9.6 error inventory gains `compute-rate-limit`,
`csrf-missing-cookie`, `csrf-mismatch`; clarifies `token-revoked` is
now implemented via W6.4. Round-4 amendments §11.1–§11.4 document
the four wave-6 surfaces formally.

---

## 3. Files touched

| File | Reason |
|---|---|
| `src/cookie_auth.py` | W6.1 (`CSRF_*` constants, `_safe_next_url`, `issue_csrf_token`, `verify_csrf`, login sets CSRF cookie, logout clears both); W6.4 (logout revokes Bearer via deny list) |
| `src/engagement_routes.py` | W6.1 (`_auth_guard` calls `verify_csrf` when `g.auth_source == "cookie"`; `_inject_csrf` context processor); W6.4 (`_require_user` consults deny list before authenticate) |
| `src/rule_pack.py` | W6.2 (`_representative_cap_table_for_collision_check`, `assert_no_collisions_at_startup`) |
| `src/parser.py` | W6.5 (try/finally around workbook body) |
| `src/token_deny.py` | new — `TokenDenyList` SQLite-backed Bearer deny list |
| `app.py` | W6.2 (boot-time collision check), W6.4 (instantiate + register `TOKEN_DENY_LIST`) |
| `templates/engagement/list.html` | W6.1 (hidden csrf_token input on create-engagement form) |
| `templates/engagement/detail.html` | W6.1 (hidden csrf_token input on upload + transition forms; hx-headers + form input on resolve + whatif HTMX forms) |
| `SYSTEM_SPEC.md` | §9.6 error inventory; round-4 §11.1-§11.4 amendments |
| `OPERATIONS.md` | §10 prod-deploy checklist |
| `tests/test_wave6_hardening.py` | new — 10 unit tests for CSRF, collision guard, deny list, parser close |
| `tests/test_wave6_integration.py` | new — 8 end-to-end integration tests across all wave seams |
| `tests/test_system_audit_stitched_fixes.py` | updated `test_b5_cookie_used_when_no_bearer_present` to send CSRF token (cookie POSTs now require it) |

---

## 4. Deferred backlog status

Wave-5 punted these to wave-6 or later. Status after wave 6:

| ID | Wave 5 status | Wave 6 action |
|---|---|---|
| M-6 CSRF tokens | deferred | **closed (W6.1)** |
| M-10 startup collision check | deferred | **closed (W6.2)** |
| SD-AUD-B5 /logout Bearer revocation | doc-only | **closed (W6.4)** |
| m-6 load_workbook close on exception | deferred | **closed (W6.5)** |
| m-1 Cache-Control relaxation | deferred | still deferred (demo UX fine) |
| m-3 Secure cookie behind plaintext proxy | deferred | partly addressed in OPERATIONS §10.5 (ProxyFix recipe) |
| m-4 OCI engine-version build-arg | deferred | doc'd in OPERATIONS §10.1 (env var) |
| m-8 cookie payload separator | deferred | still deferred (uuid users today) |
| m-12 subprocess per head_pack | deferred | still deferred (not in hot path) |

---

## 5. Audit + post-audit fixes

The independent wave-6 audit (`SYSTEM_AUDIT_WAVE_6.md`) found 2 blockers
and 6 majors at the seam between W6.1 (CSRF), W6.3 (integration tests),
and W6.4 (Bearer revocation). All blockers + all fix-now majors closed
in the same wave, with regression tests in
`tests/test_wave6_audit_fixes.py`.

### 5.1 Blockers (closed)

| ID | Finding | Fix landed |
|---|---|---|
| W6B-1 | `/logout` was unauthenticated; ANY caller could revoke ANY Bearer token they knew or guessed (the integration test even encoded this as "intentional") | `/logout` now resolves caller identity first (Bearer or cookie). Anonymous /logout returns 401. Only the caller's OWN Bearer is revoked — never an arbitrary token planted in the Authorization header. |
| W6B-2 | Pre-W6 cookie sessions held a valid session cookie but no CSRF cookie — every POST returned 403 with no recovery path | `_inject_csrf` mints a fresh token for cookie-authed safe-method renders; `_heal_csrf_cookie` after_request attaches the SAME token as the cookie so the next form POST succeeds. Double-submit security preserved (cross-site GET can't read the just-issued cookie). |

### 5.2 Fix-now majors (closed)

| ID | Finding | Fix landed |
|---|---|---|
| W6M-1 | Collision probe exercised only 10/60 rules — boot guard was mostly theatre | Probe table enriched (60→24 rules emit findings); 3 jurisdictional probe variants added (Delaware/India/Singapore); static-analysis pass added that scans `Finding(code=...)` literals across rule source files (catches the rules the probes don't fire) |
| W6M-2 | `TokenDenyList` never pruned, opens+closes sqlite per request, no WAL — unbounded growth + per-request I/O | Cached connection per process; `journal_mode=WAL` + `synchronous=NORMAL`; `prune_expired()` + `prune_older_than()` + `size()` exposed for ops; `close()` for tests |
| W6M-3 | Login blueprint `/logout` had no CSRF guard — cross-site POST could nuke the session | `/logout` now calls `verify_csrf()` on the cookie-auth path; Bearer callers exempt (explicit credential) |
| W6M-4 | Deny list entries had no TTL — revoked tokens bricked forever | `expires_at` column added with default 30-day TTL; `revoke(token, ttl_seconds=...)` accepts explicit hint; migration backfills legacy rows |
| W6M-5 | CSRF 403 returned JSON to the HTMX swap target (raw `{error: ...}` in the form panel) | `_auth_guard` branches on `_wants_html()` and renders `engagement/error.html` for HTML clients; JSON only for API clients |
| W6m-7 | No adversarial /logout test — the unsafe behaviour shipped 700-green | 3 new adversarial tests cover: anonymous /logout with victim's Bearer → 401, no-auth /logout → 401, only-own-token revocation |

### 5.3 Deferred (post-wave-6 backlog)

| ID | Finding | Defer rationale |
|---|---|---|
| W6M-6 | CSRF token never rotates within 7-day session | XSS surface already closed (wave-5 B-3); paired with the cookie cleanup the next session boundary rotates anyway |
| W6m-1 | Header-injection via `next` → 500 | cosmetic; tighten `_safe_next_url` to reject `\r`/`\n` in a future patch |
| W6m-2 | Boot crash on collision has no recovery doc | OPERATIONS §10.4 documents the strict-mode failure; add recovery playbook when prod first hits one |
| W6m-4 | sqlite per-call overhead | mitigated by W6M-2 (cached connection + WAL) |
| W6m-5 | Probe cap-table date drifts | non-issue today; revisit when a rule actually anchors against now-vs-valuation_date |
| W6m-6 | verify_csrf force-parses multipart | mitigated by header-first precedence (already in place) |
| W6m-8 | csrf_token empty-string rendering | not exploitable; verify_csrf rejects empty supplied tokens |
| W6m-9 | /logout clears CSRF cookie unconditionally (multi-tab UX) | revisit when multi-tab analyst flows become common |
| W6m-10 | Probe imports inside function | hot path is once-per-boot; not worth top-level pollution |

---

## 6. Files touched (post-audit fix batch)

| File | Reason |
|---|---|
| `src/cookie_auth.py` | W6B-1 (gate /logout; revoke only caller's Bearer); W6M-3 (CSRF on /logout cookie path) |
| `src/engagement_routes.py` | W6B-2 (`_inject_csrf` mints token + `_heal_csrf_cookie` after_request attaches matching cookie); W6M-5 (HTML 403 when `_wants_html()`) |
| `src/token_deny.py` | W6M-2 (cached connection + WAL); W6M-4 (`expires_at` + `prune_expired` + `size`); legacy-schema migration |
| `src/rule_pack.py` | W6M-1 (richer probe table + jurisdictional probe union + static source scan) |
| `templates/engagement/error.html` | new — HTML error page used by W6M-5 |
| `tests/test_wave6_audit_fixes.py` | new — 15 regression tests (3 blocker + 8 major + 4 minor) |
| `tests/test_wave6_integration.py` | added explicit HTML-path CSRF mismatch test; close deny_list in fixture |
| `tests/test_wave6_hardening.py` | updated logout test to send CSRF; updated collision-monkeypatch test to patch `_collisions_across_probes` |
| `tests/test_system_audit_stitched_fixes.py` | updated B-4 logout test to authenticate caller first |

---

## 6. What's next

After this wave, the cap-table reconciler ships with:
- A defensible Big-4-audit-evidence surface (engagement + hash chain +
  byte-stable bundle + pinned memo timestamp + 60-rule pack).
- A browser-usable HTMX UI gated by cookie auth + CSRF, with explicit
  Bearer precedence and server-side Bearer revocation.
- An integration test surface that walks every wave seam end-to-end.
- A documented prod-deploy checklist.

Possible wave-7 directions, in rough priority order:

1. **Replace `StubSSOProvider` with a real OIDC/SAML callback.**
   The single remaining "any non-empty token authenticates as analyst"
   surface. Lands when Evelyn supplies the SSO endpoint URL + JWT
   claim mapping.
2. **Postgres swap.** SQLite abstracts cleanly behind `EngagementStore`;
   wave 7 wires the connection pool and migration story.
3. **Engagement archival with restore window.** Spec §3.2 lists
   `archived` as terminal; partner needs a 30-day restore window before
   hard delete.
4. **Multi-snapshot N-way diff UI.** Today's diff is pairwise; analysts
   often want chronological browse + 3+ snapshot comparison.
5. **Rule pack v2026.7.0** — deeper firm-specific rules once the
   collision guard is in steady state.
