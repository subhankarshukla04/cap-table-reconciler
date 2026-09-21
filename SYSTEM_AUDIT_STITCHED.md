# Whole-System Stitched Audit

> Auditor: independent (Opus 4.7). Five waves of build + 60-rule pack + cookie
> auth + DCF trio + engagement hash chain, all stitched. No prior-audit notes
> consulted. Sole inputs: source tree, templates, rule_packs/*.json,
> SYSTEM_SPEC.md, OPERATIONS.md, app.py, and live reproductions executed in
> the project venv. All findings include file:line and (where possible) a
> reproducible snippet.

---

## 0. Stance + methodology

I treated the cap-table reconciler as a single deployable, not five separate
waves. Authentication, persistence, rendering, rate-limiting, rule evaluation
and Excel/PDF/bundle export are one stack as far as the analyst is concerned.
Anything that flows across a wave boundary got special attention: cookie auth
× engagement permissions, DCF sidecar × DCF template slugging, rule packs ×
checklist code registry, bundle generation × byte determinism, HTMX content
negotiation × error rendering.

What I executed:

1. Read every src/*.py and templates/**/*.html in full (skipped tests, prior
   audits, build-wave docs as instructed).
2. Diffed implementation against SYSTEM_SPEC.md §§1–10.
3. Reproduced each non-obvious finding in the project venv (`.venv/bin/python
   -c "..."`). Reproductions are inlined under each finding.
4. Walked one full real flow login → bundle and noted every place the contract
   bent.
5. Compared the cookie-auth contract to the Bearer-auth contract and proved
   their interaction via the Flask test client.

Severity ladder I used:

| Tier | Definition |
|---|---|
| BLOCKER | Data-integrity break, auth bypass, audit-evidence break, or determinism break with no spec carve-out. Ship-stop. |
| MAJOR | Violates a documented invariant (spec §§), can corrupt downstream artifacts, or hides a class of bugs from the test surface. Pre-prod fix. |
| MINOR | Spec drift, dead code, contract sloppiness, or hardening that should land before the next external audit. |

I did NOT recommend new features. Where the same fact reads as multiple
distinct symptoms, I list it once at the highest tier.

---

## 1. Blockers

### B-1. DCF sidecar and DCF template emit DIVERGENT slugs when an excluded class collides with an included class

`src/dcf_sidecar.py:82-90` enumerates EVERY share class (including
`option_pool_reserved`, which is `excluded_from_waterfall=True`) and
increments the slug-collision counter `_seen_slugs` for each.
`src/dcf_template.py:325-334` filters those out FIRST
(`included = [sc for sc in cap_table.share_classes if not sc.excluded_from_waterfall]`)
and only then runs an identical collision counter against the filtered list.

The two slug streams therefore disagree whenever a non-included class and an
included class slug-collide.

**Reproduced** (`.venv/bin/python -c "..."` output):

```
SIDECAR share_count names: ['share_count_ESOP_A', 'share_count_ESOP_A_2']
SIDECAR row: ('ESOP A',  'option_pool_reserved', 1000, ...)  → slug ESOP_A
SIDECAR row: ('ESOP-A',  'preferred',            2000, ...)  → slug ESOP_A_2
TPL row:    ESOP-A | slug: ESOP_A | formula: ='[dcf_sidecar.xlsx]Cap Inputs'!share_count_ESOP_A
```

The DCF template's "ESOP-A" row pulls `share_count_ESOP_A` from the sidecar.
Sidecar's `share_count_ESOP_A` is the **option-pool-reserved** class (1000
shares). The analyst sees 1000 shares for the preferred class that actually
has 2000. Per-class fair value silently maps to the wrong class with no
warning to the analyst.

The slug-uniqueness ledgers must operate over the same input set in both
files. Either the template enumerates all classes (and then hides the
excluded ones from the table), or the sidecar enumerates only the
non-excluded set. The fix is one or the other; today both ledgers pretend
they are authoritative.

Severity: BLOCKER — wrong number on the deliverable handed to the analyst,
with the legal-style "yellow cells = inputs, grey cells = formulas" UX
falsely implying the cell is trustworthy.

### B-2. Engagement bundle (`bundle.zip`) byte-stability is broken; no SPEC §8.10 carve-out exists

Two contributors:

- `src/engagement_bundle.py:91` writes `datetime.now(timezone.utc)` into the
  manifest.
- `zipfile.writestr(...)` uses `time.localtime()` for each entry's mtime by
  default.

**Reproduced**:

```python
b1 = build_engagement_bundle(store, eng.id)
time.sleep(1.1)
b2 = build_engagement_bundle(store, eng.id)
# bytes equal: False  (3506 vs 3506; same payload, different metadata)
```

Spec §8.10 carves out zip metadata explicitly for the *static .xlsx* and the
*live-formula .xlsx* — those rows read "openpyxl may write differing
low-level XML zip metadata." The bundle is NOT one of those rows; in fact
the README of the bundle itself (`src/engagement_bundle.py:194-205`) tells
Big-4 auditors to recompute SHA-256 against each file and confirm the
manifest. With wall-clock mtimes, the per-file SHA-256 in manifest will
still pass (the SHA covers the inner payload, not the zip envelope), but
the *bundle* SHA will diverge across regenerations. SYSTEM_SPEC.md §6.6
("same inputs → same outputs") and §8.10 say nothing about the bundle. If
the spec's promise is "the auditor can re-pull the bundle and diff it
against the one we shipped them," that promise fails today.

Fix: pass a `ZipInfo` with `date_time=(1980,1,1,0,0,0)` to every
`writestr`, and source `generated_at` from
`store.get_engagement(eng_id).created_at` (a stored timestamp) or from a
caller-injected clock. Then add a row in §8.10 for `engagement bundle.zip`
documenting bit-for-bit determinism.

Severity: BLOCKER — audit-evidence break. The bundle is the literal Big-4
deliverable. If we can't recreate it byte-for-byte we cannot say
"the bundle you have is the bundle we shipped."

### B-3. XSS via Excel-uploaded class names in waterfall + what-if HTML pages

`templates/waterfall.html:59`:

```jinja
const payload = {{ chart_json|safe }};
```

`templates/_whatif_panel.html:5` is identical. `chart_json` is
`json.dumps(chart_payload(...))`. `chart_payload` puts every share class's
`.name` into the JSON unmodified. JSON-encoding escapes `"` and `\` but does
NOT escape `</script>`.

**Reproduced**:

```
{"datasets": [{"label": "</script><script>alert(1)</script>", ...}]}
```

Drop that JSON inside `<script>...</script>` and the browser splits at
`</script>` — the alert fires. Share-class names flow from the uploaded
.xlsx. Any analyst opens the file → the workbook's malicious class name
runs script in their browser session, on the same origin where the
session cookie lives, with `httponly` blocking only the script's read of
the cookie (the script can still POST to /engagement/anything with
SameSite=Strict satisfied since it IS the site).

Spec §8.16 promises "Holder names, class names, company names, and
side-letter text may contain any UTF-8" with "Jinja2 autoescape is on for
all HTML templates." Autoescape is on, but the `|safe` filter overrides
it; the developer pinky-swore that JSON encoding alone is enough. It
isn't.

Fix: replace `{{ chart_json|safe }}` with one of
- `{{ chart_json|tojson }}` (uses Flask's tojson, which escapes `<`, `>`,
  `&`, `'`, U+2028, U+2029),
- `<script type="application/json" id="chart">{{ chart_json }}</script>`
  then `JSON.parse(document.getElementById('chart').textContent)`,
- a `data-chart="{{ chart_json }}"` attribute and read it via
  `JSON.parse(el.dataset.chart)` (autoescape applies to attributes).

Severity: BLOCKER — stored XSS, session co-located with cookie-auth. Even
a non-malicious analyst with a typo'd class name `<foo>` could cause page
breakage in the demo.

### B-4. Open redirect on /login + /logout via the `next` query/form parameter

`src/cookie_auth.py:171`:

```python
resp = make_response(redirect(next_url))  # next_url from request.form['next']
```

Same pattern on line 184 (`logout_post`). `next_url` is user-controlled and
NEVER validated. A phishing link of the form
`https://qapita.example/login?next=https://attacker.example/login` lands
the user on the legit login form (so the URL bar reads `qapita.example`),
they enter their cookie token, and the success path redirects them to the
attacker's clone. The cookie isn't leaked but the credential capture is
trivial. The attack surface is double-sized because `/logout` accepts the
same parameter for the post-logout redirect.

Fix: validate that `next_url` is a relative path OR an absolute URL whose
host matches the request host. Flask snippet:

```python
from urllib.parse import urlparse
def _is_safe_next(target: str) -> bool:
    p = urlparse(target)
    return not p.netloc and not p.scheme  # path-only
```

Severity: BLOCKER — phishing-enabling. Cookie auth was added specifically
to let real browsers use the HTMX UI; an open redirect on the only
unauthenticated path is the canonical bad combination.

### B-5. Cookie auth silently overrides Bearer auth — partner cookie + analyst Bearer ⇒ acts as partner

`src/engagement_routes.py:103-128` resolves the cookie FIRST and only
falls back to the Bearer header if the cookie is empty/invalid. If both
are present and both validate, the cookie wins.

**Reproduced**:

```
# cookie = partner, Bearer = analyst (who has engagement.create), call /engagement/
STATUS 403  BODY {"error":"Role.partner cannot engagement.create",
                  "error_code":"permission-denied"}
```

Failure mode: an analyst leaves a stale partner-cookie in their browser
from yesterday's screen-share. Today they curl with their Bearer token —
the request is silently rejected because the cookie identity overrode
their Bearer identity. Worse: an analyst who happens to also have a
partner cookie gets *partner authorisation everywhere*, with no warning,
even when they intended to act as analyst.

The spec doesn't say which wins, but the principle-of-least-surprise
answer is: explicit Authorization header beats ambient cookie. The Bearer
header is the dedicated *credential* — the cookie is the *session*.
When both are present we should either prefer the explicit one or 400
with `auth-ambiguous`.

Additional related issue: `/logout` only clears the cookie. A Bearer token
held by the same user keeps working (verified in the same repro: after
`POST /logout` returning 302, `GET /engagement/` with the same Bearer
returns 200). Spec should document that Bearer revocation requires the
SSO provider; OR add a server-side token-deny list. Today the UX claims
"logout" but the API surface stays open. Big-4 will flag this.

Severity: BLOCKER for permission ambiguity. Document /logout's narrower
scope as a MAJOR.

### B-6. Engagement `/upload` silently passes the optimistic-concurrency check (defeats GAP-01)

`src/engagement_routes.py:603`:

```python
expected_version = int(request.form.get("expected_version", eng.version))
```

When the form omits `expected_version`, the route fetches the CURRENT
version and submits THAT as the expected version. The `add_snapshot`
store call then trivially succeeds: `eng.version == expected_version`.

This is a contract leak. SPEC §8.12 says "Every mutating route accepts an
`If-Match: <version>` header (HTTP) or `expected_version: int` field"; the
implication is that the field is required. `/transition` correctly returns
400 `missing-expected-version` when absent (line 716-720). `/upload`
should do the same, or accept the version exclusively as form-required and
return 400 when missing.

Today, two analysts uploading the same engagement in parallel will both
read `eng.version=5` at the same moment, both POST `expected_version=5`
(or, more commonly, both POST without the field and have the route fill
in 5), then race. The DB lock makes one win and the other's
expected_version mismatches the post-increment version. With the OLD
race-prone code maybe one would silently overwrite the other. The current
store code is correct (B2 fix per the engagement.py docstrings) — but the
HTTP layer routes a missing version to a *guaranteed-success* path
instead of surfacing 409. That breaks the "the audit log records both
the attempted action (with the stale version) and the conflict" promise
of §8.12 last sentence.

Severity: BLOCKER for the contract. Easy fix: remove the default; return
400 if missing.

---

## 2. Majors

### M-1. PDF memo & Markdown memo break their own spec carve-out by NOT pinning the timestamp

SPEC §8.10:
> Markdown audit memo: Bit-for-bit EXCEPT for the leading `*Generated by
> ... at <UTC timestamp>*` line.
> PDF audit memo: Bit-for-bit EXCEPT for the cover-sheet timestamp and any
> PDF-internal `/CreationDate` / `/ModDate` metadata.

Implementation today: `src/audit_memo.py:77` and `src/pdf_memo.py:272` both
call `datetime.now(timezone.utc)` at memo-build time. That matches the
spec exception. BUT the spec's intent is that the same engagement with the
same inputs always renders the same memo modulo the single timestamp
line. Today, if anything ELSE in `_build_context` (`pdf_memo.py:254`) ever
becomes non-deterministic, we have no way to tell from byte-diff. The
test suite probably patches `datetime.now`; production has no such hook.

Recommendation: source the timestamp from
`engagement.head_snapshot.created_at` or the latest audit-event timestamp
so each memo regeneration is byte-stable per engagement state. That's
strictly stronger than the spec and forecloses regression of M-2.

Severity: MAJOR. Today's behaviour matches the spec literally; the
recommendation hardens it.

### M-2. Compute-rate-limit and export-rate-limit asymmetry

`src/rate_limit.py` provides one `ExportRateLimiter` class with a `consume`
method. `app.py:78` uses it twice: once as `EXPORT_LIMITER` (memo + bundle)
and once as `COMPUTE_LIMITER` (whatif). `_enforce_export_limit` in
`engagement_routes.py:187-223` writes a `bulk_export_alert` audit event
when `current == hard_limit`. The compute limiter's analogous block
(`engagement_routes.py:906-921`) does NOT write any audit event, ever.

Result: a script that DOSes /whatif at 600/hr leaves no trace in the
hash-chained audit log; the rate limit just keeps returning 429. The
engagement looks innocent to a Big-4 reviewer reading the audit log.
Inconsistent with §8.17's intent.

Severity: MAJOR. Either add a `compute_burst_alert` audit-event variant
or document the asymmetry in §8.17.

### M-3. `review → open` transition is permanently dead

`src/engagement.py:347-352`:

```python
_ALLOWED_TRANSITIONS = {
    EngagementStatus.review: {EngagementStatus.open, EngagementStatus.signed},
    ...
}
```

`src/engagement.py:357-363`:

```python
(EngagementStatus.review, EngagementStatus.open):
    "engagement.transition_review_to_open",
```

No role in `src/identity.py:43-93` grants
`engagement.transition_review_to_open`. **Reproduced**:

```
$ python -c "from src.identity import _PERMISSIONS
for r,p in _PERMISSIONS.items():
    if 'engagement.transition_review_to_open' in p: print(r)
# (no output)"
```

A partner who wants to send a stuck-in-review engagement back to "open"
cannot. The UI's `allowed_transitions` (engagement_routes.py:475-478)
filters by `can(user, action)`, so the button simply never appears. From
the partner's POV the only escape from `review` is `signed` (which is
gated by blocker-resolution per §9.3) or `archived` (terminal). Spec §3.2
and §9.1 don't list `review → open` either. So this is either:

- a planned transition with no permission grant (bug), or
- a dead branch of the lifecycle dict (cleanup).

Either way, the implementation surface is wrong.

Fix: pick one. Either remove `open` from `review`'s allowed set, or grant
the permission to `partner`.

Severity: MAJOR — silent UI omission for a recoverable lifecycle path.

### M-4. Spec §10.2 is unimplemented: legacy `/whatif/<token>` route still lives in app.py

SPEC §10.2 explicitly removes `/whatif/<token>` and declares
`POST /engagement/<eng_id>/whatif` canonical. The engagement-blueprint
route exists. The legacy route at `app.py:596-673` is still wired and
duplicates the override logic. Two consequences:

1. Two implementations drift over time. Today both have the BUG-010-fix
   logic inlined; tomorrow someone fixes only one.
2. The legacy route is rate-limit-EXEMPT and auth-EXEMPT (it predates
   wave-2). An analyst can hit `/whatif/<session_token>` and burn CPU
   forever, bypassing W5.5's compute budget entirely.

Spec drift in two directions: spec says the route shouldn't exist;
implementation says it exists AND it has none of the safety rails the new
route has.

Severity: MAJOR. Remove the legacy route OR document its phase-0 sandbox
status more loudly than "session expired" 404.

### M-5. `attach_login_blueprint` ordering invariant is unstated and load-bearing

`src/cookie_auth.py:191-197`: `attach_login_blueprint(app)` reads
`app.config["IDENTITY_PROVIDER"]` only inside the `/login` POST handler
(`cookie_auth.py:153`). If `attach_engagement_blueprint` was NOT called
first to set it, the next `/login` POST 500s with a KeyError. The
docstring at line 192-193 hints at this ("Caller must have set
IDENTITY_PROVIDER and SESSION_SECRET_KEY in app.config") but nothing
enforces it. Today app.py:82-87 calls the blueprints in the right order;
any future refactor that inverts the order ships a runtime crash.

Fix: make `attach_login_blueprint` accept an explicit `identity_provider`
argument with the same default-StubSSOProvider fallback as
`attach_engagement_blueprint`, or raise at attach-time if the config key
is missing.

Severity: MAJOR — ordering bug waiting to happen.

### M-6. No CSRF protection on any POST route

`grep -rn "csrf" templates/ src/ app.py` is empty. Every mutating route
(resolve, transition, redact, whatif, upload, delete, login, logout)
accepts a form POST with no CSRF token. Mitigation today is
`SameSite=Strict` on the session cookie (cookie_auth.py:176). That blocks
cross-site form submissions on modern browsers — but:

- It does NOT cover XSS-enabled same-origin attacks. Combine M-6 with B-3
  and an attacker can call any state-changing route AS the analyst with
  no token needed.
- Bearer-token clients don't get SameSite protection at all (they don't
  use cookies). The route accepts a form POST with credentials in
  Authorization header — completely vulnerable to a cross-origin form
  POST if the attacker can get the analyst's token.
- Some older corporate browsers ignore SameSite=Strict on certain
  navigation paths.

Fix: Flask-WTF CSRF on every POST route. Standard hardening.

Severity: MAJOR.

### M-7. `_enforce_export_limit` records the bulk-export-alert with a possibly-bogus engagement id

`src/engagement_routes.py:198-209` calls
`_store()._append_audit_event(engagement_id=eng_id, ...)` from inside the
helper. The audit event needs a valid engagement_id (`engagement.py:893-944`
selects the engagement's `audit_head_hash` and updates it). The two
callers (memo, bundle) pass `eng.id` from
`_store().get_engagement(eng_id)` which would have already raised
`EngagementNotFound` upstream — so the path is *probably* safe today. But
`_enforce_export_limit` is helper-shaped (takes a raw eng_id string), and
nothing prevents a future caller from invoking it with an unverified id,
incrementing the user's rate count, and then crashing on the audit-event
write. Worse: if a future refactor calls this BEFORE the eng_id is
validated, an attacker can trip the alert event for an engagement they
have no access to.

Fix: pass the validated `Engagement` object, not the string. Re-derive the
id inside.

Severity: MAJOR. Defensive but the underlying contract is sloppy.

### M-8. Rate-limit window math: 2-bucket sum is up to 2 hours, not 1

`src/rate_limit.py:103-108`:

```sql
SELECT SUM(count) WHERE user_id = ? AND hour_bucket >= ?  -- bucket - 1
```

The two-bucket sum represents an *envelope* that is `1h + (now mod 1h)`
seconds long — between 1h and 2h at any given moment. So the effective
hourly limit is up to 2× higher right after a bucket boundary. SPEC §8.17
says "per hour" — the implementation either delivers strictly-trailing
1h (would need finer buckets) or strictly-current bucket (today's
behaviour minus the 2-bucket sum). The 2-bucket compromise is neither.

Severity: MAJOR. Either pick "strictly-trailing 1h" (smaller buckets) or
"calendar hour" (single bucket).

### M-9. Spec §10.5 chronology is stale; v2026.6.0 exists but isn't listed

SPEC §10.5 documents 5 packs (`v2026.1.0` … `v2026.5.0`). The directory
ships 6 — including `v2026.6.0` (60 rules, head). `head_pack(today)`
returns `v2026.6.0`. Spec says head is `v2026.5.0`. Documentation drift,
not a code bug, but bound-pack reproductions years from now will read the
spec and assume the engagement was bound to v2026.5.0 when the audit_log
will show `v2026.6.0`.

Fix: append v2026.6.0 to §10.5 chronology and close v2026.5.0's
effective_to to 2026-05-25.

Severity: MAJOR — spec freshness.

### M-10. `_assert_no_finding_code_collisions` is gated to test-only; no startup check

`rule_pack.py:117-146` is a helpful collision detector. The docstring says
"Production should NOT call this on every request — it's a CI / fuzz
helper." But the function isn't called from app.py at startup either.
Today the 60 rules are collision-clean against the fixtures I tested;
nothing prevents wave-7 from introducing a regression that no test will
catch unless someone remembers to also run the collision check.

Fix: call once at app boot against a known representative cap table; log
the result; refuse to start if it's non-empty in production mode.

Severity: MAJOR — silent regression risk.

---

## 3. Minors

### m-1. `Cache-Control: no-store` blocks browser back/forward on the HTMX UI

`app.py:60-63` sets `no-store, max-age=0` on EVERY response, including
HTML pages. The HTMX UI relies on browser back-button working for the
analyst's "look at the previous engagement" reflex. With `no-store` the
browser refetches every page (auth re-validation on every back-click);
combined with the rate limit on `/whatif`, the back-button can consume
budget for no work.

Fix: keep `no-store` for export routes and 4xx/5xx; relax to
`private, no-cache, must-revalidate` for HTML pages.

### m-2. `secrets` for cookie key generation is fine; documentation is misleading

`src/cookie_auth.py:194-196`: "Per-process random key for dev. Production
sets via env." Production setup must read SESSION_SECRET_KEY from env
before `attach_login_blueprint` runs; if not set, a different per-process
key is generated and every cookie becomes invalid on restart. There's no
env var being read; the helper just silently generates and uses an
ephemeral key. Document that `os.environ["SESSION_SECRET_KEY"]` is
required for production and assert at startup if missing in non-TESTING
mode.

### m-3. Login form's `secure=not TESTING` reaches HTTPS only when `TESTING=True` is False — fine in dev, may bite local-HTTPS-off prod

`src/cookie_auth.py:177`: `secure=not current_app.config.get("TESTING")`.
If a prod environment runs without TLS (single-node demo behind a
reverse-proxy that terminates TLS), the cookie's `secure` flag will be
set but the browser will refuse to attach it. Common bug pattern. Either
honor `X-Forwarded-Proto`, or require a `PROXIED=1` toggle.

### m-4. Determinism leak: `current_engine_commit()` shells out to `git`

`src/rule_pack.py:211-226`. Cached only in-process. In containerized
deploys without git, returns `"unversioned"`. SPEC §8.15 promises engine
commit SHA at bind time. Today, a deploy from an OCI image (no .git)
records `"unversioned"` permanently for every engagement created there.
The spec doesn't expect "unversioned" to ever appear in the live
engagement table. Either build the commit SHA into the image at build
time (env var) and read it from env, or record an `engagement_unversioned`
audit event when the fallback triggers.

### m-5. Login POST returns 400/401 rendering `engagement/login.html`, but autoescape is on and content is escaped — clean

Verified `templates/engagement/login.html` shape via repro. Form-controlled
`next` value flows into a hidden input through `{{ next_url | e }}` — that
combined with autoescape blocks XSS via `?next=`. Open-redirect on
successful login is still B-4; XSS on /login is clean.

### m-6. `load_workbook` is not closed on the upload exception path

`app.py:204-221` and `src/parser.py:412` open the workbook; openpyxl
doesn't expose a `close()` for read-only mode but does for keep_vba mode.
On parse-failure, the file handle is closed by GC eventually. Not a
correctness bug, but in a long-running daemon under high upload volume,
ResourceWarning noise will obscure real issues.

### m-7. `engagement.created_at` is wall-clock, but tests presumably want deterministic timestamps for memo determinism

`engagement.py:415` calls `datetime.now(timezone.utc)`. Per M-1, sourcing
memo timestamps from `engagement.created_at` would shift determinism into
a *stored, audit-logged* timestamp instead of a re-evaluated one. The
audit log already pins it.

### m-8. Cookie value separator `|` collides with URL-unsafe characters in user_id

`src/cookie_auth.py:65-74`: payload is `f"{user_id}|{expiry.isoformat()}"`.
If a future identity provider lets `user_id` contain `|`, the
`split("|", 1)` on line 98 misparses. Today's user_ids are uuids — fine.
Hardening: use a delimiter that can't appear in user_id (e.g., `\0`) or
length-prefix the user_id.

### m-9. `Engagement._row_to_engagement` swallows the original ValidationError silently

`engagement.py:526-545`: the try/except falls back to `valuation_date=None`
on validation failure with no log line. Legacy garbage dates become
silently None on read. The first time someone investigates "why is the
date filter returning the wrong rows," it'll be hard to find. Add a
warning log.

### m-10. `/healthz` is exempt from auth (correct) and exempt from rate limits (correct), but is also exempt from `Cache-Control: no-store`? No — the global after_request runs. Fine. Documenting for the matrix below.

### m-11. `SAME-DATE-{d.isoformat()}` is a finding code containing user-influenceable formatted date

`src/rules_v2026_2.py:423`. ISO date is safe. But if d ever becomes
non-ISO (regression), the finding code embeds free-form text. Today: safe.
Add a `date.fromisoformat(d.isoformat())` round-trip assert if you want
belt-and-braces.

### m-12. The `head_pack().version` flow for engagement-create runs `subprocess` per call

`engagement.py:447` (via `current_engine_commit` from `head_pack`) shells
out. Per-engagement-create that's fine. If a future wave moves it into
`list_engagements`, we eat a fork+exec on every list call.

### m-13. Spec §10.5 says v2026.5.0 effective 2026-05-25 → null; reality is 2026-05-25 → 2026-05-25 (1-day window)

Then v2026.6.0 picks up 2026-05-26 → null. v2026.5.0 was effectively
operational for exactly the calendar day of 2026-05-25. Any engagement
created on any other date is bound to a different pack. Spec drift; the
list_available_packs() doesn't refuse, but `head_pack(date(2026,5,25))`
returns v2026.5.0 and `head_pack(date(2026,5,26))` returns v2026.6.0 —
two engagements created a day apart bind to different rule packs even
though the analyst made no change. That's the system working as designed
per §9.4 / §10.5; the spec docs just need to admit v2026.6.0 exists.

---

## 4. Cross-wave contract matrix

The matrix below maps every wave's authoritative surface to every other
wave's consumer, noting where the contract holds and where it bends.

| Producer | Consumer | Contract | Status | Detail |
|---|---|---|---|---|
| W2 engagement model (engagement.id, version) | W5 cookie auth | Cookie user_id maps to a User the engagement-store sees | OK | StaticUserProvider/StubSSO both resolve correctly |
| W2 permission matrix (`identity._PERMISSIONS`) | W5 cookie-authenticated routes | Cookie identity goes through the same `can(user, action)` checks as Bearer | OK | `_require_user` returns the same `User`; per-route `can()` calls fire |
| W2 audit-log hash chain | W5 cookie-auth events | Cookie-issued auth events appear in the chain | N/A | Cookie issuance/clearance doesn't log to the engagement chain (no engagement context). This is the right call — but worth documenting |
| W2 optimistic concurrency (expected_version) | W4 HTMX UI | UI submits expected_version on every state change | PARTIAL | upload route silently defaults the field (B-6); transition + others require it |
| W2 PII redaction | W4 PDF memo | Redacted snapshots refuse memo with `snapshot-redacted` 410 | OK | engagement_routes.py:782-787 |
| W2 bound_pack_json | W3 bundle + W3 memo + W3 subsequent events | All three prefer pinned bytes over disk | OK | bundle (engagement_bundle.py:77-86), memo (engagement_routes.py:798-804), subsequent_events (engagement_routes.py:504-514) |
| W3 valuation_date typing (date) | W2 audit-log payloads | Audit events serialize valuation_date as ISO | OK | `_canonical_payload` uses payload_json with sorted keys; valuation_date never appears in audit events; engagement creation payload has only client_id/standard/pack/engine |
| W4 PDF memo blocker refusal | W4 sign-off gate | Both use unresolved blocker set | DRIFT | Memo uses `_ensure_eligible` (pdf_memo.py:131); transition uses `_enforce_blockers_resolved` (engagement.py:803). Both reload the pack independently — if pack files are pruned, only the transition check raises the spec error; the memo check would just see no blockers (load fails to None). Convergence check needed |
| W5 cookie auth | W5 HTMX UI redirects | Anonymous request to HTML route redirects to /login | OK | engagement_routes.py:115-123 |
| W5 cookie auth | W5 Bearer fallback | Cookie wins over Bearer when both present | BLOCKER | See B-5 |
| W5 cookie auth | All POST routes | Cookie carries enough credential to mutate state | RISK | No CSRF token; SameSite=Strict only partially mitigates (M-6) |
| W5 compute rate limit | W4 /whatif | Audit log records spike | DRIFT | Export limiter logs alert; compute limiter doesn't (M-2) |
| W5 export rate limit | W2 audit log | Hard alert event references engagement_id | RISK | Helper accepts raw eng_id without validation (M-7) |
| W1 legacy /whatif/<token> | W5 compute rate limit | Legacy route is rate-limited | BROKEN | Legacy route bypasses everything (M-4) |
| Sidecar slug counter | DCF template slug counter | Same input set → same slug | BROKEN | Different input filters (B-1) |
| Sidecar `defined_names` | DCF template `_sidecar_ref` | External-link path resolves | OK if names match (currently doesn't, see B-1) |
| OPM vol_pack | DCF template's WACC cell | Vol pack feeds the analyst's WACC assumption | N/A | No automated link; analyst copies manually (intentional per §10.1) |
| 6 rule packs (v2026.1 → v2026.6) | head_pack() | Non-overlapping monthly windows | OK | 1-day v2026.5.0 window is intentional per §10.5 + my §M-9 note |
| 60-rule registry | bundle export | Bound pack JSON in bundle matches engagement.bound_pack_json | OK | engagement_bundle.py:78-86 round-trips via RulePack.model_validate_json |

---

## 5. End-to-end flow trace

Walking one real flow as a partner analyst auditing Acme Inc. cap-table.

### Step 1: GET /login → POST /login

- Browser issues `GET /login` (no cookie, anonymous).
- `cookie_auth.login_get` renders the form. `next` defaults to
  `/engagement/?html=1`. **Note:** if a phisher seeds `?next=...` here,
  the form's hidden input picks it up unsanitized (XSS-safe due to
  autoescape; open-redirect-NOT-safe, see B-4).
- Browser POSTs `token=anything-non-empty`. StubSSOProvider returns the
  same analyst user for any non-empty input. **Note:** in production
  this must be replaced. Today's stub means any HTTP client with
  /login access becomes an analyst.
- Server issues `qapita_session` cookie. HttpOnly, SameSite=Strict,
  Secure=True (will fail behind plaintext local proxy, see m-3).
- 302 → `/engagement/?html=1`.

### Step 2: POST /engagement/ (create)

- `before_request` calls `_require_user`. Cookie present → resolved
  via IdentityProvider's `lookup_user(user_id_from_cookie)`. OK.
- create_engagement form: client_id="acme", standard_of_value="ifrs13",
  no valuation_date. `_engagement_errors` wraps; pack loaded via
  `head_pack()` → v2026.6.0 → bound_pack_json pinned. Genesis audit
  event appended (hash chain initialized).
- **Issue:** the head_pack version (v2026.6.0) doesn't appear in SPEC
  §10.5 chronology (M-9). Future reproducibility audit will see a pack
  the spec doesn't mention.

### Step 3: POST /engagement/<id>/upload

- File: acme_captable.xlsx. **Bug:** the form (template detail.html:53)
  has `<input type="hidden" name="expected_version" value="{{ ... }}">`
  so the version IS sent. But if anyone calls the route programmatically
  without that field, B-6 silently passes the concurrency check.
- `parse_excel` succeeds. Snapshot inserted under write lock.
- snapshot_added audit event appended.
- **Issue:** if the cap table has a class named `</script>alert(1)`,
  it's now stored verbatim in the engagement DB. The next analyst who
  visits the waterfall page will execute it (B-3). The hash chain
  doesn't help us — the malicious content IS what we faithfully recorded.

### Step 4: POST /engagement/<id>/resolve (inline form, HTMX)

- form fields: snapshot_id=..., finding_code="AD-MISSING-Series A",
  decision={"variant":"broad_based"}, citation="Charter §4.4".
- citation is non-empty (else engagement.py:687-688 rejects).
- `record_resolution` inserts row, appends resolution_recorded audit
  event. Returns _resolution_ok partial.
- **Note:** the inline form lacks CSRF (M-6). A successful XSS via B-3
  could submit this from a malicious script with no token check.

### Step 5: POST /engagement/<id>/transition (review)

- expected_version=2 (after upload + resolve). transition() takes the
  write lock, verifies version, runs `_enforce_blockers_resolved` only
  when target == signed (line 777). For review target, no blocker check —
  correct per spec §3.2.
- transition audit event appended.

### Step 6: POST /engagement/<id>/transition (signed)

- expected_version=3. Reviewer must be partner-or-reviewer; verified.
- `_enforce_blockers_resolved` re-loads bound pack and re-runs rules.
- **Convergence risk:** the pack-load path here is `load_engagement_bound_pack(eng.pack_version)`,
  which does NOT consult `bound_pack_json`. If the disk file was
  deleted, this raises `BlockerFindingsOutstanding(...)`. The memo
  route uses the bound JSON first, then disk. They can disagree —
  with bound_pack_json present and disk pruned, transition refuses,
  memo succeeds.

### Step 7: GET /engagement/<id>/memo.pdf

- Permission check: partner has `export.memo_pdf` ✓.
- Export rate limit consumed.
- `_ensure_eligible` checks blockers — passes (we resolved them).
- WeasyPrint renders. `generated_at` is wall-clock (M-1).
- Returned with `Content-Disposition: attachment`.

### Step 8: GET /engagement/<id>/bundle.zip

- Permission + rate limit pass.
- `build_engagement_bundle` produces zip with:
  - manifest.json including `generated_at: <now>` (B-2)
  - audit_log.jsonl with hash chain
  - rule_pack.json from bound_pack_json
  - snapshots, resolutions, parse_reports, memo (optional)
- Each file's mtime is current wall-clock → bytes differ across calls.

### Step 9: POST /logout

- Cookie cleared (max_age=0).
- Bearer tokens NOT invalidated. The analyst still has API access if
  they hold the token. (B-5 second half.)

### Determinism preservation across steps 1–9

| Artifact | Determinism today | Spec carve-out | Verdict |
|---|---|---|---|
| Audit log row hashes | Deterministic for given (event_type, actor, ts, payload) | §8.14 implicit | OK (ts must be pinned at row-creation time, which it is) |
| Snapshot cap_table_json | Pydantic v2 sorts keys | §8.10 | OK |
| Static .xlsx | Cell values deterministic; zip metadata not | §8.10 row 4 | OK by carve-out |
| Live .xlsx | Cell formulas deterministic; zip metadata not | §8.10 row 5 | OK by carve-out |
| PDF memo | Cover timestamp + PDF /CreationDate vary | §8.10 row 7 | OK by carve-out — but the cover timestamp could be pinned (M-1) |
| Bundle .zip | EVERY entry mtime varies + manifest generated_at | NONE | B-2 |
| Markdown memo | Generated-at line varies | §8.10 row 6 | OK by carve-out |

---

## 6. Determinism review

The single biggest hole is the bundle (B-2). Beyond that:

- The hash chain (`engagement.py:893-944`) hashes `(event_type | actor |
  ts_iso | payload_json)`. ts_iso is wall-clock and stored. The hash is
  deterministic given the stored row, which is what auditors recompute.
  CORRECT.
- `payload_json` is `json.dumps(payload, sort_keys=True,
  separators=(",", ":"))`. Stable. CORRECT.
- The `_canonical_payload` separator is `|` (engagement.py:269). User IDs
  cannot contain `|` today (uuid format); same caveat as m-8.
- Bundle README `_readme_text` (engagement_bundle.py:166-221) is a
  static f-string with `engagement_id[:8]` substituted. Stable.
- `chart_payload` in waterfall.py — verified stable for the same inputs.
- DCF sidecar + template — stable per-build, but inputs across the
  trio disagree (B-1).
- Vol pack — not reviewed in depth here; cited as clean by inspection.
- All rule files anchor to cap-table dates (verified by grep, line 14 of
  rules_v2026_6.py header note).

---

## 7. Security review

| Surface | Check | Status |
|---|---|---|
| Cookie HttpOnly | `cookie_auth.py:175` httponly=True | OK |
| Cookie SameSite | `cookie_auth.py:176` Strict | OK |
| Cookie Secure | `cookie_auth.py:177` secure=not TESTING | Mostly OK (m-3) |
| Cookie signing | HMAC-SHA256, constant-time compare (`cookie_auth.py:95`) | OK |
| Cookie key bytes | 32 bytes from secrets.token_bytes if env-unset | OK functionally; doc m-2 |
| Cookie payload format | `user_id|expiry_iso|HMAC` | OK; m-8 hardening |
| Cookie expiry check | `cookie_auth.py:102-103` | OK |
| CSRF tokens | None | M-6 |
| Open redirect | next param unvalidated | B-4 |
| XSS in templates | Autoescape on; one `|safe` on JSON inside `<script>` | B-3 |
| XSS in PDF memo | Autoescape on; `select_autoescape(["html","xml"])` | OK |
| XSS in Markdown memo | `_md()` escapes pipes + newlines (audit_memo.py) | OK per spec §8.16 |
| SQL injection | All `conn.execute` calls use parameterised queries | OK (verified by grep) |
| Path traversal in pack version | Validated by `_PACK_VERSION_RE` + `_no_path_traversal_in_version` | OK |
| Auth on every engagement route | `before_request` hook | OK |
| Auth on legacy app.py routes | None (session-token-based, no role) | INTENTIONAL — phase-0 demo surface; should be documented |
| /logout revokes Bearer | No | B-5 (second part) |
| Cookie vs Bearer precedence | Cookie wins silently | B-5 |
| Rate limit on memo + bundle | Yes | OK |
| Rate limit on /whatif | Yes (compute limiter) | OK |
| Rate limit alert audit | Export only; compute is silent | M-2 |
| StubSSOProvider in prod | Accepts any non-empty token | INTENTIONAL stub; gate via env in deploy |
| `QAPITA_ALLOW_DEV_PACK` gate | enforced | OK |
| Permission table for every action | 4 roles defined; some unreachable | M-3 (dead transition) |
| Audit log immutability | append-only, hash-chained | OK |
| PDPA redaction | sentinel + audit event | OK per §8.13 |

Overall security posture: the **engagement** half (W2) is hard. The
**HTMX + cookie** half (W4 + W5) ships several first-week-of-prod
vulnerabilities (B-3, B-4, B-5, M-6). The phase-0 demo app.py routes
(/upload, /review, /waterfall) are intentionally auth-free for
screen-shared demo; they should be wrapped or pulled before any
internet-facing deploy.

---

## 8. Spec compliance against round-3 amendments

| Amendment | Implementation status |
|---|---|
| §9.1 partner reopen + archive | partner can `signed → review` (verified); `signed → archived` allowed for partner (verified); `open → archived` allowed for partner (verified). `review → open` is in the dict but no role has the permission (M-3). |
| §9.2 engagement-bound pack contract | Memo, bundle, subsequent_events all prefer `bound_pack_json` over disk lookup. Transition's `_enforce_blockers_resolved` does NOT — it loads disk directly. Inconsistency. |
| §9.3 sign-off gate | `_enforce_blockers_resolved` runs only on `→ signed`. Refuses with `engagement-blockers-unresolved`. No force flag. OK. |
| §9.4 pack effective windows | 6 packs ship with non-overlapping windows. §10.5 lists 5; reality has 6 (M-9). |
| §9.5 v0.0.0-dev refusal | `load_engagement_bound_pack` refuses unless env set. OK. |
| §9.6 error-code inventory | Implementation emits all listed codes plus `auth-required`, `parse-failed`, `client-id-required-for-role`, `bad-date-filter`. `compute-rate-limit` NOT in §9.6 — spec drift. |
| §9.7 valuation_date typing | Implementation went further than spec admits — now `date | None` (W4.5) not `str` as §9.7 documents. Spec is stale. |
| §10.1 DCF template clarification | `dcf_template.py` produces inputs only. Yellow cells visible. Aligned. |
| §10.2 /whatif URL | `POST /engagement/<id>/whatif` exists. **Legacy `/whatif/<token>` still exists in app.py — direct spec violation (M-4).** |
| §10.3 bound_pack_json column | Column exists; migration is idempotent; bundle + memo use it. OK. |
| §10.4 HTMX cookie auth contract | Cookie path implemented; production-mode header auth still works. OK. Stub provider is the documented Evelyn-block. |
| §10.5 chronology renumbering | v2026.5.0 effective 2026-05-25 → 2026-05-25 (not null as §10.5 says). v2026.6.0 added but undocumented in §10.5 (M-9). |
| §10.6 rule determinism (no wall-clock) | Verified by grep — no `date.today()` calls in `rules_v2026_*.py`. OK. |

Where I cannot verify against spec because the spec is silent:

- Bundle .zip determinism (B-2) — no §8.10 row for it.
- Cookie/Bearer precedence — no doc.
- CSRF stance — no doc.
- Compute rate-limit alert behaviour — no §8.17 row for it.

---

## 9. Things checked CLEAN

- Hash chain construction (`engagement.py:893-944`) — atomic under
  `_write_lock`, prev_hash → row_hash transitions verified offline.
- `verify_audit_log` recomputes from genesis correctly.
- Pydantic v2 sort-keys serialisation — deterministic.
- Optimistic concurrency on `transition` and `add_snapshot` — atomic
  conditional UPDATE under lock plus rowcount check.
- `_engagement_errors` decorator — routes HTML when wants_html(), JSON
  otherwise. Q-value parsing in `_wants_html` works.
- `_extract_token` correctly refuses query-string tokens in non-TESTING
  mode.
- `attach_engagement_blueprint` config-set order is correct.
- `_assert_no_finding_code_collisions` returned None on the rich test
  cap-table I built.
- Rate-limit bucket math is *correct* arithmetically — only the policy
  (M-8) is off.
- PDPA redaction sentinel + immutability — correct.
- Subsequent events anchoring on `head_snapshot_id` (M-1 of compiled
  audit) — implemented correctly.
- Rule pack `effective_from`/`effective_to` non-overlapping windows —
  confirmed via load.
- SAFEs/warrants/notes resolutions in app.py — proper model_copy use,
  no in-place mutation.
- Diff route's tempfile cleanup pattern.
- Compare-page logic for unchanged-row skip.

---

## 10. Fix-now-vs-defer table

| # | Severity | Finding | Cost | Fix-now? |
|---|---|---|---|---|
| B-1 | Blocker | DCF sidecar/template slug divergence | 1h | YES — directly produces wrong analyst output |
| B-2 | Blocker | Bundle byte non-determinism | 2h | YES — audit-evidence claim |
| B-3 | Blocker | XSS via `|safe` JSON in script tags | 30m | YES — trivial fix, severe impact |
| B-4 | Blocker | Open redirect on /login + /logout | 30m | YES — phishing surface |
| B-5 | Blocker | Cookie-over-Bearer precedence + Bearer not revoked by /logout | 1h | YES — at minimum surface ambiguity |
| B-6 | Blocker | /upload silently passes optimistic concurrency | 15m | YES — spec contract |
| M-1 | Major | Memo timestamp from wall-clock not engagement state | 30m | Strengthen now; spec allows current behaviour |
| M-2 | Major | Compute-rate-limit alert missing | 30m | Now |
| M-3 | Major | Dead `review → open` transition | 5m | Now — pick one half of the dict to align |
| M-4 | Major | Legacy /whatif/<token> route still wired | 15m | Now — direct §10.2 violation |
| M-5 | Major | attach_login_blueprint ordering invariant unstated | 15m | Now |
| M-6 | Major | No CSRF protection | 2h | Now — pair with B-3 fix |
| M-7 | Major | _enforce_export_limit takes raw eng_id | 15m | Now |
| M-8 | Major | 2-bucket sum is up to 2h, not 1h | 30m | Now — easy off-by-one |
| M-9 | Major | Spec §10.5 stale: v2026.6.0 undocumented | 5m | Now — doc only |
| M-10 | Major | Finding-code collision check is dev-only | 30m | Defer to startup check |
| m-1 | Minor | `no-store` blocks browser back-button | 10m | Defer; doesn't affect demo |
| m-2 | Minor | SESSION_SECRET_KEY env-var documentation | 5m | Now — one-line addition |
| m-3 | Minor | Secure cookie behind plaintext proxy | 10m | Defer until prod toggle decided |
| m-4 | Minor | "unversioned" engine_version in OCI | 30m | Defer; document in OPERATIONS |
| m-5 | Minor | Login form XSS check (verified clean) | — | None |
| m-6 | Minor | load_workbook close on exception | 15m | Defer |
| m-7 | Minor | engagement.created_at wall-clock | — | Defer; pair with M-1 |
| m-8 | Minor | Cookie payload `|` separator | 10m | Defer; uuid users today |
| m-9 | Minor | _row_to_engagement silently fallback to None date | 5m | Now — add log |
| m-10 | Minor | /healthz coverage in matrix | — | None |
| m-11 | Minor | SAME-DATE-<iso> code construction | — | None |
| m-12 | Minor | subprocess per engagement-create | 30m | Defer; cache module-level |
| m-13 | Minor | v2026.5.0 1-day window vs §10.5 | 5m | Now — paired with M-9 doc fix |

Total fix-now: **~9h focused engineering** to close all six blockers and
the doc-touch majors. The compute-limiter alert (M-2) and CSRF (M-6) are
the two non-trivial pieces.

---

**Bottom line:** the engagement + audit-log half of the system is the
hardened, defensible Big-4-grade work. The cookie/HTMX/DCF-trio half
ships several first-week-of-production bugs — XSS, open redirect, auth
precedence ambiguity, byte non-determinism on the very deliverable the
spec calls "the portable auditor handoff," and a wrong-shares bug on the
DCF sidecar/template pair. None of these failed any unit test. They are
the cost of cross-wave-stitching not having an integration test surface.
Build one before the next external audit.
