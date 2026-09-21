# SYSTEM AUDIT — WAVE 9

Scope: only issues introduced by wave 9 (W9.1–W9.8) or cross-contract
breaks W9 created against the existing W2–W8 surface. Severity:
BLOCKER / MAJOR / MINOR.

Auditor: independent reviewer
Date: 2026-05-30
Tests at audit time: 819 passing (per build note).

---

## 1. BLOCKERS

### B-1 — CSRF rotation creates a template/cookie mismatch on the same GET (W9.5)

**Files**: `src/engagement_routes.py` lines 409–456 (`_heal_csrf_cookie`
after_request + `_inject_csrf` context_processor).

**Root cause**: order of hook execution for a single safe-method GET:

1. `_auth_guard` runs (`before_request`).
2. View handler renders the template. Inside the render,
   `_inject_csrf` context_processor reads the EXISTING cookie value and
   injects it into the template as `csrf_token`. The rendered HTML form
   carries the OLD token.
3. `_heal_csrf_cookie` after_request runs. It checks
   `csrf_token_age_seconds(existing) > CSRF_ROTATION_SECONDS` and, if
   stale, replaces the cookie via `attach_csrf_cookie(response,
   issue_csrf_token())`. The cookie now holds the NEW token.

Result: HTML body has OLD, cookie has NEW. The user's next form POST
sends OLD in `csrf_token` field and NEW in the cookie → `verify_csrf`
returns `csrf-mismatch` → 403.

**Repro** (run in `.venv/bin/python`):

```python
import time, secrets, re, tempfile
from pathlib import Path
from flask import Flask
from src.cookie_auth import CSRF_COOKIE_NAME, attach_login_blueprint
from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User
from src.rate_limit import ExportRateLimiter
from src.token_deny import TokenDenyList

paths = [Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name) for _ in range(4)]
store = EngagementStore(db_path=paths[0])
exl = ExportRateLimiter(db_path=paths[1], soft_limit=50, hard_limit=100)
cpl = ExportRateLimiter(db_path=paths[2], soft_limit=20, hard_limit=40)
dl = TokenDenyList(db_path=paths[3])
app = Flask(__name__); app.config["TESTING"] = True
app.config["SESSION_SECRET_KEY"] = b"x"*32; app.config["TOKEN_DENY_LIST"] = dl
provider = StaticUserProvider({"tok-a": User(id="u-a", email="a@x",
    role=Role.analyst, display_name="A")})
attach_engagement_blueprint(app, store, provider,
    export_limiter=exl, compute_limiter=cpl)
attach_login_blueprint(app, identity_provider=provider)
c = app.test_client()
c.post("/login", data={"token": "tok-a"})
stale = f"{int(time.time()) - 3700}.{secrets.token_urlsafe(32)}"
c.set_cookie(CSRF_COOKIE_NAME, stale, domain="localhost")
r = c.get("/engagement/?html=1")
old = re.search(r"name=['\"]csrf_token['\"] +value=['\"]([^'\"]+)['\"]",
                r.get_data(as_text=True)).group(1)
new_cookie = c.get_cookie(CSRF_COOKIE_NAME).value
# Submit with the form value the page actually showed:
r2 = c.post("/engagement/", data={"csrf_token": old, "client_id": "c",
    "valuation_date": "2025-06-01"})
print(r2.status_code, r2.get_data(as_text=True)[:120])
# → 403 {"error":"CSRF check failed","error_code":"csrf-mismatch"}
```

This also hits the multi-tab case: tab A has a fresh form open with the
old token; the user opens tab B (a GET) which crosses the 3600s
boundary and rotates the cookie. Tab A's next submit now 403s with no
recovery path other than reload.

**Fix sketch**: when after_request rotates the cookie, either (a) skip
rotation for any response whose body is a rendered template that
already contains the old token (track via `g._minted_csrf` /
`g._template_csrf_rendered = True` set in `_inject_csrf`), (b) defer
rotation to the NEXT safe-method GET that does not render a form, or
(c) make `verify_csrf` accept both the current cookie value AND the
predecessor for a short grace window. Option (a) is the cheapest.

**Closes claim**: W9.5 advertises "closes W6M-6" but actually opens a
strictly worse defect (silent 403 race vs the original "tokens never
rotate"). Should NOT ship as-is.

---

## 2. MAJORS

### M-1 — Snapshots pagination is render-side only; O(N) per request (W9.7)

**Files**: `src/engagement_routes.py:1296–1362` calls
`_store().list_snapshots(eng_id)` which `SELECT *` loads every
snapshot row (including `cap_table_json` blob) into memory before the
slice `all_snaps[offset:offset+limit]` runs.

The W9.7 contract advertises pagination with `limit ≤ 100`, but the
DB read is unbounded. An engagement with thousands of snapshots pays
the full memory + JSON-deserialisation cost on every `?limit=1`
request. Hostile or stress-test traffic against `/snapshots?limit=1`
trivially burns RSS and SQLite read amplification.

**Repro by inspection**: `src/engagement.py:756–767` is a plain `SELECT
* FROM snapshot WHERE engagement_id = ? ORDER BY created_at, id` with
no LIMIT.

**Fix sketch**: push limit/offset into a new
`list_snapshots(engagement_id, *, limit, offset)` that emits
`SELECT ... LIMIT ? OFFSET ?` and a separate `count_snapshots(engagement_id)`
for `total`. Pagination UI math stays unchanged.

### M-2 — OPM route accepts negative and otherwise nonsense floats; produces "defendable" output (W9.2)

**Files**: `src/engagement_routes.py:1152–1175` parses `volatility`,
`time_to_liquidity_years`, `risk_free_rate`, `dlom`, `dividend_yield`
through `float(...)` with no domain guards. `MarketInputs`
(`src/opm/backsolve.py:71-78`) is a plain frozen dataclass — also no
validation.

**Repro**: posting `{"volatility": -0.5, "time_to_liquidity_years": 4.0,
"risk_free_rate": 0.045, "anchor_class_name": "Series A",
"anchor_price_per_share": 1.0}` to `/engagement/<id>/opm` returns
`200` with `implied_total_equity_value ≈ 6,000,000.00` (Black–Scholes
squares σ, so negative σ silently behaves like its positive twin).

This violates the "expert-led, not algorithm-only" register the
project explicitly adopted from Evelyn's feedback: a typo on the
sign produces an answer the analyst could paste into a memo with no
clue the model never validated it. NaN and Inf get caught by brentq
downstream (good), but the negative-σ and negative-rfr / negative-TTL
paths slip through.

**Fix sketch**: domain-check `MarketInputs` (`__post_init__` raising
`BacksolveError`): `volatility >= 0`, `0 < time_to_liquidity_years <
100`, `-0.1 <= risk_free_rate <= 1.0`, `0 <= dlom <= 1`,
`0 <= dividend_yield <= 1`, and reject NaN/Inf at the route level
before audit-event write. Mirror the route-side `opm-bad-inputs` 400.

### M-3 — `finding_provenance_map` does not honour jurisdiction filter, mis-attributes findings on cross-jurisdiction code reuse (W9.1)

**Files**: `src/pdf_memo.py:196–197` calls
`finding_provenance_map(ct, pack=inputs.pack)` with no
`engagement_jurisdiction` arg, while the matching `run_pack` for the
memo's findings IS jurisdiction-filtered (per
`src/rule_pack.py:633–637`).

Concretely: two rules in different jurisdictions are allowed to emit
the same `Finding.code` (the W6.2 startup guard runs per-probe and
across-probes, and `_static_collisions_in_rule_sources` flags only
identical literal codes, not jurisdictionally disjoint pairs that
happen to share a template prefix). Result: the memo can render the
WRONG rule_id + citation in the new "Rule provenance" column, because
`finding_provenance_map` walks the FULL pack and last-write-wins on
the dict.

**Fix sketch**: pass `engagement_jurisdiction=eng.jurisdiction` from
the caller (engagement-routes memo path) all the way through
`PDFInputs` into the provenance map call.

### M-4 — OPM route lacks `compute_burst_alert` audit event at hard-limit boundary (W9.2)

**Files**: `src/engagement_routes.py:1132–1146` consumes
`COMPUTE_LIMITER` but only returns 429 on `not rl.allowed`. The two
prior compute-side routes (`/whatif` line 1665 and `/diff` line 1390)
both emit a `compute_burst_alert` audit event when
`rl.current_count == rl.hard_limit` so abuse lands in the engagement's
hash chain. OPM does not. An attacker who knows the soft/hard gap can
calibrate exactly at the hard limit and the audit chain stays silent.

**Fix sketch**: lift the four-line `compute_burst_alert` block from
`/whatif` into `/opm`, with `"route": "opm"` in the payload.

---

## 3. MINORS

### m-1 — `_heal_csrf_cookie` and `_inject_csrf` both call `issue_csrf_token()` independently when no cookie exists, producing two distinct tokens per request

**Files**: `src/engagement_routes.py:430–431` vs `440–456`.
`_inject_csrf` mints `minted` and stashes it on `g._minted_csrf`; the
after_request hook reads `g.get("_minted_csrf") or issue_csrf_token()`.
This works (the `or` falls through), but only because the
context_processor runs first. If a future view path renders without
the context_processor (e.g. `make_response(jsonify(...))` returned
directly with no template render and no `_inject_csrf` invocation),
the after_request hook will mint a SECOND token unrelated to anything
the client saw. Benign today but a latent variant of the B-1 race.

### m-2 — `csrf_token_age_seconds` truncates on overflow and reports negative ages without rotation

**Files**: `src/cookie_auth.py:84–95`. A token whose `<unix_seconds>`
prefix is in the FUTURE (server clock skew, dev test, tampering)
returns a negative age. The rotation check `age > 3600` is false for
negative values, so a future-dated token is never rotated. Low impact
(attacker who can mint a CSRF token can already do worse), but worth
clamping: rotate when `age is None or age > 3600 or age < 0`.

### m-3 — `rule-coverage` CLI swallows "fixture has no `cap_table.xlsx`" silently (W9.8)

**Files**: `app.py:1373–1376`. `if not xlsx.exists(): continue` skips
silently. A fixture dir with a typo'd filename or a half-imported
fixture would produce zero coverage and no warning. Parse failures
are printed (line 1380). Add the same diagnostic for the missing-file
path.

### m-4 — `rule-coverage` CLI crashes if `fixtures/` directory is absent

**Files**: `app.py:1366–1367`. `fixtures_dir.iterdir()` raises
`FileNotFoundError` if `fixtures/` doesn't exist (e.g. minimal Docker
image that strips test fixtures). The CLI should catch and print
"rule-coverage: fixtures directory missing" instead of a stack trace.

### m-5 — `build_dcf_sidecar` Read-me text positioning assumes vol-pack rows do not collide with future Read-me content

**Files**: `src/dcf_sidecar.py:178–199`. Hard-coded cells `A9..A16` for
the vol-pack block. If a future revision adds another paragraph at
`A8/A9`, the vol-pack block silently overwrites. Move to
`rm.append([...])` or compute the next row dynamically (`next_row =
rm.max_row + 2`).

### m-6 — OPM route does not surface `BacksolveAnchorMissing` distinctly from `BacksolveSolverFailed`

**Files**: `src/engagement_routes.py:1201–1207`. All `BacksolveError`
subclasses funnel into `error_code = type(exc).__name__.lower()` —
e.g. `backsolveanchormissing`, `backsolvesolverfailed`. These should
be stable kebab-case for API consumers (e.g. `backsolve-anchor-missing`).
Bare `.__name__.lower()` is brittle to future renames.

### m-7 — Vol-pack block in DCF sidecar interpolates floats with `{:.2%}` which silently rounds e.g. 0.5500001 to 55.00%

**Files**: `src/dcf_sidecar.py:186–192`. Rounding is fine for analyst
display but the sourcing note is dropped entirely. The
`vol_pack_readback.sourcing` dict is captured in the readback but
never surfaced in the Read-me, so the analyst loses the provenance of
each market input. The whole point of the vol pack workflow is
defensibility — showing 55% without citing "peer set Q1 2025" is the
weak link.

---

## 4. Cross-wave contract matrix (W9 producers × W2–W8 consumers)

| W9 producer | W2–W8 consumer | Contract held? | Notes |
|---|---|---|---|
| W9.1 `finding_provenance_map` | W3.x `pdf_memo._build_context` | Partial (M-3) | jurisdiction filter not threaded through |
| W9.1 provenance dict shape | W8.11 `timeline_diff` section in memo | Clean | provenance keyed by finding code; timeline diff doesn't read it |
| W9.2 `opm_backsolve_run` AuditEventType | W4.x `verify_audit_log` (`/engagement/<id>/verify`) | Clean | new enum value parses through `AuditEventType(r["event_type"])` (line 1170) |
| W9.2 OPM audit payload | W7.6 audit-row JSON consumers | Clean | payload contains scalars + class name; no PII; JSON-stable |
| W9.2 OPM compute limiter consumption | W5.5/W7-M1 compute_burst_alert pattern | **Broken (M-4)** | OPM consumes but never emits the boundary alert that /whatif and /diff do |
| W9.3 vol-pack readback in sidecar | W8.x DCF bundle byte stability | Clean | sidecar isn't in the bundle; verified by code reading + test_w93 doesn't roundtrip through bundle |
| W9.4 phase-0 split | W2.x top-level routes `/upload`, `/sessions`, `/diff` | Clean | both legacy paths still blocked; `/diffx`, `/sessionsx` correctly not matched |
| W9.4 phase-0 split | W4+ `/engagement/<id>/diff`, `/engagement/<id>/diff.xlsx` | Clean | engagement routes are under `/engagement/` prefix, not gated |
| W9.5 CSRF rotation | W6.1 cookie-auth POST verify | **BROKEN (B-1)** | template/cookie value diverge in same request |
| W9.5 CSRF rotation | W8.7 multi-tab logout/heal contract | **BROKEN** | new failure mode: open-tab forms 403 when sibling tab triggers rotation |
| W9.6 NaN guard `_classify_pct` | W7.1 timeline diff JSON / W8.11 memo drift table | Clean | only raises on float NaN; ints/None untouched |
| W9.7 snapshots pagination JSON shape | W7.1 existing JSON callers expecting a top-level list | Clean (default `limit=50` preserves full list at small N) | but if total > 50 the old contract silently truncates with no envelope |
| W9.7 pagination DB load | W7.1 `list_snapshots` | **Broken (M-1)** | render-side slice; DB still O(N) per request |
| W9.8 `rule-coverage` CLI | W5+ registered rules | Clean | crashes only if `fixtures/` absent (m-4) |

---

## 5. CSRF rotation flow trace (W9.5)

Trace for a cookie-authed GET on `/engagement/?html=1` whose CSRF
cookie is 3700 s old:

```
HTTP/1.1 GET /engagement/?html=1
Cookie: qapita_session=<valid>; qapita_csrf=1747000000.aaaa…  (age 3700s)

[engagement_routes.py:383 _auth_guard]
  → _require_user() sets g.current_user, g.auth_source="cookie"
  → verify_csrf() in before_request runs for GET? request.method in
    allow_methods=("GET","HEAD","OPTIONS") → returns None. Pass.

[engagement_routes.py view handler renders template]
  Jinja render() triggers context_processor _inject_csrf (line 440).
    existing = request.cookies.get("qapita_csrf") = "1747000000.aaaa…"
    returns {"csrf_token": "1747000000.aaaa…"}  ← OLD
  Template substitutes OLD into <input name="csrf_token" value="OLD">.
  Response body contains OLD.

[engagement_routes.py:409 _heal_csrf_cookie after_request]
  g.auth_source == "cookie" ✓
  request.method in ("GET","HEAD") ✓
  response.status_code 200 < 400 ✓
  existing = "1747000000.aaaa…" (truthy)
  age = csrf_token_age_seconds(existing) = 3700
  3700 > 3600 → attach_csrf_cookie(response, issue_csrf_token())
  Set-Cookie: qapita_csrf=<NEW>; …
  Response body STILL contains OLD.

Browser stores qapita_csrf=NEW.
Browser displays form with hidden csrf_token=OLD.

[Next user click] POST /engagement/<...>
  Cookie sent:        qapita_csrf=NEW
  Form field sent:    csrf_token=OLD

[engagement_routes.py:383 _auth_guard before_request]
  verify_csrf():
    expected = "NEW"; supplied = "OLD"; compare_digest(NEW, OLD) = False
  → returns "csrf-mismatch"
  → 403 response.
```

Mitigation must either (a) make the cookie set by after_request
identical to the one rendered in the body (e.g. context_processor
mints + stashes on `g`, after_request reads `g`), or (b) skip
rotation on responses whose body holds a form (`g._template_csrf =
True`), or (c) implement a two-token grace window so the previous
token validates for one round-trip after rotation.

The minimal fix is (a): have `_inject_csrf` mint the rotated token
itself when the existing one is stale, stash it on `g`, and have
`_heal_csrf_cookie` always reuse `g._minted_csrf` instead of minting
its own.

---

## 6. Things checked clean

- W9.3 vol-pack readback flows ONLY into the sidecar Read-me sheet,
  never into the engagement bundle. Bundle byte stability holds.
- W9.4 phase-0 split: every legacy top-level route still gated
  (`/upload`, `/diff`, `/sessions`, `/sessions/<tok>/delete`,
  `/demo/<id>`, `/review/<tok>`, `/whatif/<tok>`, `/export/<tok>.xlsx`,
  `/compare/<tok>`, `/upload_side_letter/<tok>`,
  `/resolve/<tok>/...`). `/engagement/<id>/diff[.xlsx]` correctly
  not matched (different prefix). `/diffx` etc not matched (W8-m3
  closed cleanly).
- W9.6 NaN guard only raises on real `float('nan')`; ints, `None`,
  and `(0, 0)` paths still classify correctly.
- W9.8 rule-coverage CLI executes end-to-end against the project
  fixtures (60 rules, 23 firing, 37 dead-coded under current fixture
  set) — modulo m-3/m-4.
- W9.1 `finding_provenance_map` exception path: rules that raise are
  silently skipped and absent from the map (PDF row renders blank for
  those codes). Acceptable graceful degradation.
- W9.1 duplicate-code handling: last rule wins. The W6.2 startup
  guard already refuses literal collisions; only the
  jurisdiction-disjoint pseudo-collision path is exposed (M-3).
- W9.2 OPM bypass scan: respects `engagement.read` permission, the
  redacted-snapshot 410 gate, and compute rate limit. Does not bypass
  snapshot-not-found / engagement-not-found. Audit event payload
  contains only scalars + class name + snapshot_id — no PII (no
  source_filename, no created_by, no anchor raise amount in payload
  when None).
- W9.2 OPM NaN/Inf inputs are caught at brentq (returns 400
  `backsolvesolverfailed`) BEFORE audit event write — no NaN smuggled
  into the audit chain.
- W9.5 token shape (`<unix_seconds>.<random>`) is `compare_digest`-safe
  (full-string comparison; prefix doesn't weaken the random suffix).
- W9.7 negative offset / huge offset arithmetic: rejected (`offset <
  0`) or returns empty slice (`offset > total`). No Python int
  overflow (arbitrary precision).
- AuditEventType enum: `opm_backsolve_run` parses through the
  reconstruction path in `list_audit_events` cleanly.

---

## 7. Fix-now-vs-defer

| ID | Severity | Fix now / Defer | Rationale |
|---|---|---|---|
| B-1 | BLOCKER | **Fix now** | Silent 403s in the cookie-auth UI cross the 3600s boundary; multi-tab users see them daily. Cannot ship W9.5 with this race. |
| M-1 | MAJOR | Fix now | Pagination not actually paginating defeats the entire W9.7 contract; trivial DB-side LIMIT/OFFSET patch. |
| M-2 | MAJOR | Fix now | "Expert-led" register is a load-bearing claim; OPM accepting negative σ silently is exactly the failure Evelyn's pivot called out. Cheap dataclass `__post_init__`. |
| M-3 | MAJOR | Fix now | Wrong rule_id + citation in the memo is a deliverable correctness bug. Single arg-threading change. |
| M-4 | MAJOR | Fix now | OPM abuse goes undetected in the audit chain — mirror the existing /whatif pattern, four lines. |
| m-1 | MINOR | Defer | Benign today; revisit if any JSON view starts using `make_response` without a template render. |
| m-2 | MINOR | Defer | Future-dated CSRF tokens require a credentialed attacker who can already do worse. |
| m-3 | MINOR | Fix now (one line) | CLI loudness is cheap and saves a real footgun. |
| m-4 | MINOR | Fix now (one line) | Same; turn FileNotFoundError into a clean message. |
| m-5 | MINOR | Defer | Only bites if someone adds content at A8/A9 in the Read-me — caught by the next Read-me edit reviewer. |
| m-6 | MINOR | Defer | API consumers don't depend on the exact error_code casing today; tighten when bundle docs ship. |
| m-7 | MINOR | Fix now | The sourcing dict is the defensibility artefact; surfacing it is the entire point of the readback. Two `rm.append` calls. |
