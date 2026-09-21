# Wave-6 Hardening Audit

> Auditor: independent (Opus 4.7). Scope: ONLY the surface changed by wave 6
> (CSRF — W6.1, startup collision probe — W6.2, integration tests — W6.3,
> Bearer revocation deny list — W6.4, parser close-on-exception — W6.5, spec
> sweep — W6.6) and cross-contract regressions those changes introduce against
> the wave-2…wave-5 surface. The wave-5 stitched audit
> (`SYSTEM_AUDIT_STITCHED.md`) governs everything else. Reproductions inlined
> from `.venv/bin/python -c "..."`. Severity ladder identical to the wave-5
> audit (BLOCKER / MAJOR / MINOR).

---

## 0. Stance + methodology

I read the six surfaces wave 6 touched
(`src/cookie_auth.py`, `src/engagement_routes.py:103-142, 322-341`,
`src/token_deny.py`, `src/rule_pack.py:117-223`, `src/parser.py:405-503`,
`app.py:82-113`, `tests/test_wave6_integration.py`), reproduced behaviour
end-to-end through the Flask test client against the real
`EngagementStore` + `TokenDenyList` + `StaticUserProvider` + both rate
limiters, and asked one question of each W6 change:

  - Does the new behaviour break a W2-W5 contract?
  - Does the new behaviour close the SD-AUD finding it claims to close?
  - Does the new code introduce its own attack surface or operational
    footgun?

Tests passing is necessary, not sufficient — every BLOCKER below ships
green under the 700-test suite.

---

## 1. Blockers

### W6B-1. `/logout` is unauthenticated; ANY caller can revoke ANY Bearer token

`src/cookie_auth.py:250-268` (`logout_post`). The handler reads
`Authorization: Bearer <token>` (and `X-Auth-Token`), hashes it, and
appends the hash to `TOKEN_DENY_LIST`. No identity check; the login
blueprint has no `before_request` guard. An attacker who learns ANY
Bearer token (browser-extension leak, server log, stolen client) — or
who simply guesses one (the `StubSSOProvider` accepts any non-empty
string!) — can POST `/logout` with that token in the Authorization
header and permanently revoke it. The legitimate holder is then locked
out of the API surface for the lifetime of the deny entry.

**Reproduced**:

```
Before, deny size: False
Logout status: 302
After, victim revoked: True
Victim create after attacker logout: 401
```

Two compounding factors make this worse than a single-user DOS:

  1. `TokenDenyList` has no expiry. `prune_older_than` exists but
     **`app.py` never calls it** (`grep prune app.py` empty). The deny
     list is a one-way, append-only "permanent revocation" map.
  2. With `StubSSOProvider` in dev (which accepts any non-empty token),
     a bored client can sweep `tok-aaaa` → `tok-zzzz` in a single
     curl-loop and permanently brick every future stub login.

Fix (file:line — `src/cookie_auth.py:250`): wrap `logout_post` so it
ONLY revokes the Bearer/X-Auth-Token actually belonging to the
caller's currently-authenticated identity. Concretely: resolve the
caller via `_require_user`-equivalent first; if no identity, 401; if
identity is cookie-only, no Bearer to revoke (just clear the cookie);
if Bearer came in, verify it resolves to the SAME user as any cookie
also presented, then revoke. Alternatively: gate `/logout` behind
`_require_user` from the engagement blueprint and revoke only the
header that matches the user the request authenticated as.

Severity: **BLOCKER**. Pre-auth permanent revocation of arbitrary
credentials is a textbook auth-DOS. The wave-5 audit accepted
"Bearer not revoked by /logout" as a MAJOR; wave 6 fixed that with a
new BLOCKER.

### W6B-2. Cookie sessions issued before W6.1 cannot make ANY POST — server-side healing absent

`src/cookie_auth.py:74-106` issues the CSRF cookie ONLY from
`/login` POST (`login_post`, line 247: `attach_csrf_cookie(resp,
issue_csrf_token())`). `_auth_guard` in
`src/engagement_routes.py:322-334` enforces `verify_csrf()` on every
cookie-authenticated mutating request and returns
`csrf-missing-cookie` 403 when the cookie isn't present.

Any browser session that existed before the wave-6 deploy holds a
valid 7-day session cookie but no CSRF cookie. On the next POST, the
server 403s with `csrf-missing-cookie`. The user has no recovery path
in-app: no auto-re-issue on GET, no documented "log out, log in,
re-try" surface, no graceful fallback. The HTMX UI just renders the
JSON 403 as raw text.

**Reproduced** (simulating a pre-W6 cookie):

```
GET status: 200
CSRF cookie set after GET? False
POST status: 403 {'error': 'CSRF check failed', 'error_code': 'csrf-missing-cookie'}
```

For a Big-4 demo where the analyst logged in yesterday, walked away,
came back today to a shipped-overnight W6, every form click is now a
silent 403. This is the kind of regression that ships green
(`test_csrf_missing_cookie_on_cookie_auth_returns_403` explicitly
PROVES the failure mode is "intentional") but reads as outage in prod.

Fix (file:line — `src/cookie_auth.py:74` + new before_request hook in
the engagement blueprint): when the request authenticates via cookie
AND no `qapita_csrf` cookie is present, AUTO-ISSUE a fresh CSRF
cookie on the response of the next GET (or 200 from the safe-methods
branch). The double-submit pattern stays sound because the attacker
on a cross-site GET still can't read the just-issued cookie. Pair
with an `OPERATIONS.md §10` note: "rolling W6 over an existing
cookie session is seamless; the first GET re-heals the CSRF cookie."

Severity: **BLOCKER** for production rollout. Every live browser
session breaks on deploy with no in-app remediation.

---

## 2. Majors

### W6M-1. Startup collision probe exercises only ~10 of 60 rules

`src/rule_pack.py:154-198` defines
`_representative_cap_table_for_collision_check()` — a synthetic cap
table with one common class, one ESOP pool, and two preferred
classes with LP + AD. `assert_no_collisions_at_startup` runs every
registered rule against this table and looks for duplicate finding
codes.

The probe table has no SAFEs, no warrants, no convertible notes, no
side letters, no jurisdictional triggers, no down-round, no
double-cap, no stale-pool-grant date, no missing-conversion-ratio,
no participating-uncapped, no full-ratchet trigger fired against an
actual prior price.

**Reproduced**:

```
total rules: 60
rules emitting 0 findings on probe table: 50
first 10: ['G-AD-001', 'G-POOL-001', 'G-SAFE-001', 'G-WAR-001',
          'G-SL-001', 'G-VOTE-001', 'G-AD-003', 'G-AD-004',
          'G-AD-005', 'G-LP-002']
```

50 of 60 rules emit zero findings on the probe table → 50 of 60 rules
contribute zero codes to the duplicate-finding-code check. The boot
guard's promise — "two rules can't silently overwrite each other's
findings" — only covers the 10 rule paths that the probe table
actually fires. The wave-5 audit's M-10 ("`_assert_no_finding_code_collisions`
is gated to test-only; no startup check") is now formally closed
in `app.py:113`, but the closure is mostly theatre.

Fix (`src/rule_pack.py:154`): extend the probe cap table to fire every
rule's emission path at least once. Cheapest path: union the cap
tables from `fixtures/fixture_0[1-5]/cap_table_input.json` (already
shipped, already known-clean) and run the probe against the union.
Even cheaper: harvest the cap tables the test suite already uses.
Alternative: change the collision check from "run rules on a probe
table" to "static analysis of every rule's `Finding(code=...)`
literal", which catches the collision regardless of code path.

Severity: **MAJOR** — the audit claim doesn't match the runtime
guarantee.

### W6M-2. `TokenDenyList` grows unbounded; never pruned, never bounded, never observable

`src/token_deny.py:70-79` provides `prune_older_than(ts)` but
`app.py:84-88` instantiates `TokenDenyList` and **never calls
`prune_older_than`**. `grep prune app.py` returns empty.

Each `/logout` writes one row. Each W6B-1-style attack writes one
row. Each `is_revoked(token)` does a sqlite SELECT on every
engagement-blueprint request (`engagement_routes.py:116`). Over 6
months of production, the table is unbounded; lookup latency
gradually walks up; the deny db never reports its size.

Compounding: there is no `WAL` mode, no `synchronous=NORMAL`, no
shared-connection pool. Every revoke + every check opens a fresh
sqlite connection (`token_deny.py:45-47`). On a per-request hot
path this is one fopen + one fclose + one fsync (default sqlite
sync=FULL) per HTTP call. Not catastrophic today; will be
catastrophic the first time someone benchmarks the engagement
blueprint under load.

Fix (`src/token_deny.py:36` + `app.py:88`):
  1. Add a periodic prune scheduled at app boot for entries older
     than the SSO max token lifetime (e.g., 30 days).
  2. Cache the sqlite connection per-process (or expose a single
     `Engine`-like pool).
  3. Switch journal_mode=WAL on init.
  4. Add a `deny_list_size()` helper and expose at `/healthz` so an
     operator can spot DOS attacks.

Severity: **MAJOR** — operational footgun + an unbounded resource
sink that pairs with W6B-1 to become a real outage.

### W6M-3. Login blueprint `/logout` and `/login` have no CSRF protection

W6.1 added CSRF to the engagement blueprint's `before_request`
hook (`engagement_routes.py:322-334`). The login blueprint
(`cookie_auth.py:208-268`) has NO `before_request` and NO
`verify_csrf` call on either `/login` POST or `/logout` POST.

Consequences:

  - `/logout`: a cross-site form POST to `/logout` (autosubmitted
    via JS on an attacker page) ends the user's session. SameSite=Strict
    mitigates the cookie path, but combined with W6B-1's missing
    auth check, any caller can also revoke the user's Bearer if the
    attacker knows the token.
  - `/login`: session-fixation. An attacker submits a cross-origin
    form POST to /login with the attacker's own stub token; the
    victim's browser (if same-site context exists) gets a session
    cookie under the attacker's identity. The next action the victim
    takes ("save" their work) saves it under the attacker's account.
    SameSite=Strict on the response cookie partially mitigates, but
    the attack window exists when the user navigates same-site after
    the POST.

The wave-5 SD-AUD-M6 fix landed only on the engagement blueprint;
wave-6's intent ("CSRF on every cookie-authenticated POST") is
documented but not delivered for the auth blueprint.

Fix (`src/cookie_auth.py:208`): add a `bp.before_request` that
runs `verify_csrf()` for non-safe methods, except on `/login` POST
which by design has no prior session. For `/logout`, require either
a CSRF token (cookie-auth path) or an explicit Bearer auth
(API-client path), gated by W6B-1's fix.

Severity: **MAJOR**.

### W6M-4. Bearer-revocation deny list keys on raw token hash — survives token reissue

`src/token_deny.py:32-33`: `_hash(token) = sha256(token).hexdigest()`.
Revoking is by token hash, irrevocably. If the SSO provider re-issues
the same token string to the same user (e.g., long-lived service
tokens, rotated keys), the new issuance is born revoked.

More subtle: with the dev `StubSSOProvider`, the token IS the user-id
input. Once revoked, that input string is forever unusable. There is
no admin endpoint to un-revoke. There is no per-token TTL. The
contract a deny list usually has — "revoked until expiry" — is broken
here because there's no expiry concept.

Fix (`src/token_deny.py:25-30`): add an `expires_at REAL NOT NULL`
column, default `revoked_at + 30 days` (configurable). `is_revoked`
checks `expires_at > now`. `/logout` accepts an explicit expiry
hint. Adds operational sanity AND closes the regression where
`prune_older_than` exists but is dead code.

Severity: **MAJOR** — contract drift between "revoke" (temporary,
matches token lifetime) and the implementation (permanent).

### W6M-5. CSRF check returns JSON 403; the HTMX UI renders it as raw text

`engagement_routes.py:332-334`: on CSRF failure the `before_request`
hook builds a `jsonify(...)` 403 and `abort(resp)`. The
`_engagement_errors` decorator (which contains the
`_wants_html()` branch that would render `engagement/base.html`
with an error banner) is NEVER REACHED because `before_request`
short-circuits.

For an HTMX form post that hits the wrong CSRF token (e.g., a stale
cookie, a forged DOM state), the browser swap target is replaced
with the JSON error body — the analyst sees
`{"error":"CSRF check failed","error_code":"csrf-mismatch"}` jammed
into their cap-table form panel.

Fix (`engagement_routes.py:332`): branch on `_wants_html()` and
render `engagement/base.html` with the spec error code instead of
jsonify when the request wanted HTML. Matches the rest of the
4xx handling discipline elsewhere in the same module.

Severity: **MAJOR** — UX break visible on the very first CSRF
failure, which an analyst WILL hit (multi-tab use, browser
back-button, form auto-fill replaying stale tokens).

### W6M-6. CSRF token never rotates — exfiltrated token replayable for 7 days

`cookie_auth.py:57` `COOKIE_TTL_DAYS = 7`. `attach_csrf_cookie`
sets the CSRF cookie's `max_age = COOKIE_TTL_DAYS * 86400`. The
token is issued ONCE at `/login` POST and is the same value for
the full 7-day session. There is no rotation on privilege change,
no rotation on partial-failure recovery, no rotation on
session-impersonation hop. If the token leaks via an LLM-summarised
log, a screen-share, or a third-party browser extension, the
attacker has a 7-day window to forge state-changing requests under
the victim's identity.

Standard hardening: rotate on every authenticated session boundary
(login, role escalation, sensitive-action), or rotate every N
minutes by re-issuing the cookie when stale.

Fix: in the engagement blueprint's `after_request`, if the
csrf cookie is older than 1 hour (encode `issued_at` into the
token, HMAC-signed), re-issue it.

Severity: **MAJOR** — defense-in-depth gap, pairs with the
unmitigated XSS surface from the wave-5 stitched audit's B-3
(template `|safe` on JSON in script tags, which I did NOT
re-audit; if B-3 was closed in W6, demote this to MINOR).

---

## 3. Minors

### W6m-1. Header injection via `next` parameter returns 500 instead of 400

`/login` POST with a `next` form value containing `\r\n` passes
`_safe_next_url` (the helper only checks scheme/netloc/leading `/`),
flows into `redirect(next_url)`, and werkzeug 3.x raises
`ValueError: Header values must not contain newline characters`.
The Flask error handler returns 500.

```
ValueError: Header values must not contain newline characters.
```

A malicious link can trigger 500s reliably (small noise in monitoring,
free DOS amplifier). Fix: tighten `_safe_next_url` to reject any
`\r`, `\n`, control char.

### W6m-2. `assert_no_collisions_at_startup` runs in `strict=True` mode in prod but the failure mode is "refuse to boot" with no recovery doc

`app.py:113`: `_assert_no_collisions(strict=not app.config.get("TESTING", False))`.
A future rule that silently emits a colliding finding code crashes
the whole app at boot. No graceful fallback ("disable colliding
rule and warn"), no SRE-friendly toggle. Pair with W6M-1: the probe
table misses most rules → false confidence; if it ever DOES catch a
collision, prod crashes hard.

Fix: emit a `compute_burst_alert`-style audit event into a startup
log AND raise. Document the recovery path in OPERATIONS.md.

### W6m-3. `_inject_csrf` context processor only fires for engagement blueprint

`engagement_routes.py:336-341`. Login blueprint templates (login.html
in particular) don't get the csrf_token context variable. If
W6M-3's fix lands (CSRF on /login + /logout), the login template
needs a hidden input populated by csrf_token; today the context
processor doesn't reach there.

### W6m-4. `TokenDenyList.__init__` opens + closes sqlite per call; `is_revoked` does the same

`token_deny.py:42-47`. Cheap but not free. At engagement-blueprint
request rate (memo, bundle, whatif), this is per-request sqlite
fopen+fclose. Bench it under 100 RPS; if it shows up, switch to a
per-process cached connection.

### W6m-5. The collision-probe cap table embeds wall-clock-stable but unusual dates (e.g. 2020-01-01)

`rule_pack.py:166`: `valuation_date=date(2025, 6, 1)`. Today is
2026-05-26. The probe table is in the past relative to "today" —
any future rule that checks `valuation_date <= today` will trigger
or skip differently than expected. Won't cause silent failure, but
the probe should pin a future-stable date (e.g.,
`date.today() - timedelta(days=180)`).

### W6m-6. `verify_csrf` consumes `request.form` on a multipart upload — burns memory eagerly

`cookie_auth.py:102`. For 8MB-cap uploads
(`app.MAX_CONTENT_LENGTH = 8 * 1024 * 1024`), the entire body is
parsed into memory before the route handler runs, even when the
header-based CSRF token would have sufficed. Cheapest fix: check
the header first, only fall back to `request.form` if header is
absent — which is what the code already does, so this is actually
fine when HTMX sends X-CSRF-Token. Document the precedence
explicitly so a future refactor doesn't invert it.

### W6m-7. Wave-6 test suite has no test for the unauthenticated `/logout` revocation surface

`tests/test_wave6_integration.py:230-247` proves logout revokes the
caller's token. It does NOT prove that an arbitrary caller cannot
revoke an arbitrary OTHER user's token (which is W6B-1 above). Add a
test: `client_attacker.post("/logout", headers=_bearer("tok-victim"))`
should NOT revoke `tok-victim` if the attacker has no identity.

### W6m-8. `csrf_token_for_request` returns `None` for anonymous requests but `_inject_csrf` renders empty string

`engagement_routes.py:341`: `return {"csrf_token": csrf_token_for_request() or ""}`. Templates
render `value=""` for the hidden input, which a careless form
re-submitter might confuse with "valid empty token." Today's
verify_csrf rejects empty supplied tokens (`if not supplied`), so
this is safe — note for future hardening.

### W6m-9. `/logout` clears CSRF cookie unconditionally

`cookie_auth.py:267`. Even on cookie-only logout (no Bearer involved),
the CSRF cookie is cleared. If the user has multiple tabs open and
hits logout in one, the other tabs' next POST fails with
`csrf-missing-cookie` 403 — same UX regression as W6B-2.

### W6m-10. `_representative_cap_table_for_collision_check` is imported at module-load AND at every boot call

`rule_pack.py:154-198`: every call constructs the cap table fresh.
That's fine semantically, but `assert_no_collisions_at_startup`
imports `from .models import ...` inside the function body — adds
import-graph noise to the cold-start path. Move imports to module
top.

---

## 4. Cross-wave contract matrix (W6 producers × W2-W5 consumers)

| Producer | Consumer | Contract | Status | Detail |
|---|---|---|---|---|
| W6.1 CSRF guard on engagement blueprint | W4 HTMX UI forms | Every cookie-auth POST carries a matching CSRF token | OK | All 4 form templates (`detail.html` lines 51/69/108/187) include both hidden input AND `hx-headers` X-CSRF-Token |
| W6.1 CSRF guard | W5 cookie-auth precedence | CSRF gated on `g.auth_source == "cookie"` | OK | `_auth_guard` correctly tags `bearer` vs `cookie`; Bearer requests bypass CSRF |
| W6.1 CSRF guard | W2 engagement mutating routes | All POST routes enforced via `before_request` | OK | Single chokepoint, no per-route opt-out |
| W6.1 CSRF guard | Pre-W6 browser sessions | Existing session cookies continue working | BROKEN | W6B-2: existing sessions get permanent 403 csrf-missing-cookie |
| W6.1 CSRF guard | W4 HTMX error UX | 4xx renders the engagement base template with error banner | BROKEN | W6M-5: CSRF 403 returns raw JSON, breaking HTMX swap target |
| W6.1 CSRF cookie | Login blueprint /login POST | CSRF check before session issuance | BROKEN | W6M-3: login blueprint has no CSRF check; session-fixation possible |
| W6.1 CSRF cookie | Login blueprint /logout POST | CSRF check before cookie clearance | BROKEN | W6M-3 + W6B-1 — /logout has no auth AND no CSRF |
| W6.2 startup collision check | W2 rule registry | 60-rule registry stays collision-clean | PARTIAL | W6M-1: only 10/60 rules exercised by probe table |
| W6.2 startup collision check | W3 bundle pack pinning | Bundle's `rule_pack.json` references valid pack | OK | No interaction; the boot guard runs at app start, before any request |
| W6.3 integration tests | W5 cookie auth path | Cookie flow login→bundle covered | OK | `test_browser_flow_login_create_upload_resolve_transition_signed` covers the full flow |
| W6.3 integration tests | SD-AUD-B5 Bearer-beats-cookie | Bearer precedence covered | PARTIAL | Tested in `test_bearer_token_revoked_by_logout_stops_authenticating`, but no explicit "cookie + bearer both present → bearer wins" test |
| W6.3 integration tests | W6B-1 unauth /logout DOS | Adversarial /logout coverage | MISSING | W6m-7: no test that prevents arbitrary token revocation |
| W6.4 deny list | W2 audit chain | Revocation events recorded in engagement audit log | RISK | `/logout` writes deny-list row but writes NO audit event — Big-4 sees a token "stop working" with no audit trail to explain why |
| W6.4 deny list | W5 Bearer auth | `is_revoked` checked before identity resolution | OK | `_require_user:115-117` checks deny BEFORE `provider.authenticate` |
| W6.4 deny list | W2 engagement integrity | Revoked token can still write past audit chain | OK | Revocation deny applied at AUTH layer; never reaches mutating store calls |
| W6.4 deny list | Operational lifecycle | Deny entries expire, get pruned | BROKEN | W6M-2 + W6M-4: no TTL, no pruning, grows unbounded |
| W6.5 parser close on exception | W2 upload route | No ResourceWarning under load | OK | Reproduced clean: try/finally closes `wb` on every exit path |
| W6.5 parser close on exception | W4 phase-0 demo upload | Same close on exception | N/A | `app.py:140-160` `_read_xlsx_raw_excerpt` still doesn't close on its own except path — pre-existing wave-5 issue, not regressed by W6 |
| W6.6 spec sweep | All wave consumers | Spec docs match implementation | OK | §9.6 + §11 amendments mirror the code; OPERATIONS.md §10 lists the prod checklist |

---

## 5. End-to-end CSRF + Bearer-revoke flow trace

Two flows that exercise wave-6 surface:

### Flow A — Browser cookie POST with CSRF

1. `GET /login` → 200 HTML form. No cookies set yet.
2. `POST /login token=tok-analyst` → 302 to `/engagement/?html=1`.
   Response sets `qapita_session` (HttpOnly, SameSite=Strict, Secure)
   AND `qapita_csrf` (NOT HttpOnly, same SameSite/Secure).
3. Browser follows redirect → `GET /engagement/?html=1`.
   `_auth_guard` resolves cookie → `g.auth_source = "cookie"`. Method
   is GET → CSRF check skipped (allow_methods includes GET).
   `_inject_csrf` makes `csrf_token` available to the template.
4. Browser HTMX form on `detail.html` POSTs `/engagement/<id>/resolve`
   with `hx-headers='{"X-CSRF-Token": "<token>"}'` AND hidden input
   `csrf_token=<token>`. `_auth_guard` sees cookie → CSRF check
   runs. Header read first, matches cookie via `hmac.compare_digest`.
   Pass.
5. Route handler runs. State mutated.

Reproduced via `test_browser_flow_login_create_upload_resolve_transition_signed`.

**Crack #1 (W6M-5)**: if the token in the hidden input drifts (stale
tab), the 403 response body is JSON — HTMX renders the raw JSON into
the swap target.

**Crack #2 (W6B-2)**: between steps 2 and 3, if the user closes the
browser and re-opens with the session cookie restored but the CSRF
cookie cleared by extension cleanup, step 4 fails with
csrf-missing-cookie. No auto-heal.

### Flow B — Bearer revocation via /logout

1. API client makes `POST /engagement/ -H "Authorization: Bearer tok-analyst"
   -d '{"client_id":"c"}'`. `_extract_token` finds the Bearer; deny list
   check passes (not revoked); `provider.authenticate` resolves the
   user; `g.auth_source = "bearer"`. CSRF skipped (Bearer path).
   Engagement created.
2. Client decides to log out: `POST /logout -H "Authorization: Bearer tok-analyst"`.
   No auth check fires (no before_request on login blueprint).
   Handler reads the Authorization header, hashes
   `tok-analyst`, inserts into `token_deny`. Clears session cookie
   (none was set; no-op). Returns 302 to `/login`.
3. Same client tries `POST /engagement/` again with the same Bearer.
   `_extract_token` finds it. `deny_list.is_revoked(token)` → True.
   `token = None`. `provider.authenticate("")` → None. No cookie
   fallback. `_require_user` returns 401.

Reproduced via `test_bearer_token_revoked_by_logout_stops_authenticating`.

**Crack #1 (W6B-1)**: step 2 had NO IDENTITY CHECK. The deny list
accepts the token whoever sent the request. An anonymous attacker
can do step 2 against ANY token they know or guess.

**Crack #2 (W6M-2 + W6M-4)**: the deny entry has no expiry. Tomorrow,
yesterday, never — `tok-analyst` is revoked forever. Even if the
SSO provider re-issues the same token, the new issuance is born
revoked.

**Crack #3 (W6.4 ↔ W2)**: the deny event is not in the engagement
audit chain. A Big-4 reviewer pulling the audit log six months from
now will see `tok-analyst` make 12 calls, then nothing — with no
record of why. They'd have to compare against the deny-list db, which
isn't in the bundle and has no signature.

---

## 6. Things checked CLEAN

- `src/parser.py:412-502` — `wb.close()` in `finally` closes the handle
  on every exception path including `ValueError("Could not find a
  Cap Table tab...")`. ResourceWarning reproduction clean.
- `verify_session_cookie` — constant-time HMAC compare, expiry check
  after signature check, exception-swallowing path returns None
  rather than crashing. No regression from W5.7.
- CSRF token entropy — `secrets.token_urlsafe(32)` → 256-bit random,
  URL-safe character set. Compatible with form values and headers.
- `verify_csrf` header-first, form-second precedence. HMAC compare via
  `hmac.compare_digest`.
- `_auth_guard` sets `g.auth_source` correctly under all four
  combinations: bearer-only, cookie-only, both-present-bearer-wins,
  bearer-revoked-cookie-fallback. Verified against
  `test_browser_flow_*` and `test_bearer_token_revoked_by_logout_*`.
- `attach_login_blueprint` raises `RuntimeError` if SESSION_SECRET_KEY
  is missing in non-TESTING mode (closes wave-5 m-2).
- `_safe_next_url` blocks `//evil.example`, `https://evil`, empty
  string. Backslash variants are URL-encoded by Flask before reaching
  the Location header (verified via reproduction; result was
  `/%5Cevil.example.com/...`).
- `assert_no_collisions_at_startup` import order — app.py's
  `from src.checklist import run_checklist` (line 43) triggers
  `src/__init__.py` which registers all rules_v2026_*; by the time
  line 113 runs the boot probe, all 60 rules are in
  `_REGISTRY`.
- 60-rule registry collision-clean on the probe table (10 rules
  active) — no false-positive collision blocks boot.
- W6.3 8 integration tests pass against the full stack with no
  mocks at the seams.
- Bearer + cookie precedence preserved from SD-AUD-B5 fix.

---

## 7. Fix-now-vs-defer table

| # | Severity | Finding | Cost | Fix-now? |
|---|---|---|---|---|
| W6B-1 | Blocker | Unauth `/logout` can revoke any Bearer | 30m | YES — pre-auth credential DOS |
| W6B-2 | Blocker | Pre-W6 sessions can't recover (CSRF cookie absent) | 30m | YES — deploy-day outage |
| W6M-1 | Major | Collision probe exercises 10/60 rules | 30m | YES — invalidates W6.2's audit claim |
| W6M-2 | Major | Deny list never pruned, sqlite hot-path noise | 1h | YES — pair with W6B-1 fix |
| W6M-3 | Major | Login blueprint /login + /logout have no CSRF | 30m | YES — pair with W6B-1 fix |
| W6M-4 | Major | Deny list entries have no TTL | 30m | YES — pair with W6M-2 |
| W6M-5 | Major | CSRF 403 returns JSON to HTMX UI | 15m | YES — first-failure UX break |
| W6M-6 | Major | CSRF token never rotates for 7 days | 1h | Defer unless XSS surface remains open |
| W6m-1 | Minor | Header-injection `next` → 500 | 10m | Defer; cosmetic |
| W6m-2 | Minor | Boot crash on collision has no recovery doc | 10m | Defer |
| W6m-3 | Minor | csrf_token absent in login template ctx | 5m | Defer until W6M-3 lands |
| W6m-4 | Minor | sqlite per-call overhead in deny list | 30m | Defer; bench first |
| W6m-5 | Minor | Probe cap-table date drifts vs "today" | 5m | Defer |
| W6m-6 | Minor | verify_csrf force-parses multipart form | — | Document precedence; no fix needed |
| W6m-7 | Minor | No adversarial /logout test | 10m | YES — pair with W6B-1 fix |
| W6m-8 | Minor | csrf_token empty-string rendering | — | Defer; not exploitable |
| W6m-9 | Minor | /logout clears CSRF cookie unconditionally | 5m | Defer until multi-tab UX matters |
| W6m-10 | Minor | Probe imports lazy inside function | 5m | Defer |

Total fix-now budget: **~3.5h focused engineering** to close W6B-1, W6B-2,
W6M-1, W6M-2, W6M-3, W6M-4, W6M-5, plus the W6m-7 test. Everything else
is post-prod hardening.

---

**Bottom line.** Wave 6 closes four wave-5 audit findings (CSRF / collision
check / integration tests / parser handle / Bearer revocation) and
introduces two NEW BLOCKERS (unauth `/logout` revocation, CSRF-cookie
unhealable session) plus six majors (mostly around the new deny-list
operational surface and the auth-blueprint CSRF gap). The integration
test harness W6.3 is the most valuable wave-6 artifact — it covers the
seams the wave-5 audit explicitly called out as untested — but it
encodes the unsafe `/logout` behaviour as INTENTIONAL (line 240-242 of
the test file passes a Bearer header to `/logout` and asserts the
revocation succeeds without verifying caller identity), which is how
this BLOCKER shipped green. Fix the two blockers + the four
operational majors before the next external audit and W6 lands cleanly.
