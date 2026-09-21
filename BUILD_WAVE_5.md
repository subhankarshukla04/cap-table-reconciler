# Build Wave 5 — What Shipped

> Wave 5 closed the cross-wave surface: the analyst can now run the full
> engagement loop in a real browser (cookie auth, inline resolution form,
> snapshot-aware what-if, snapshot diff), the rule pack grew to 60, the
> DCF trio cross-workbooks correctly, and /whatif gained its own compute
> budget. The stitched whole-system audit caught six blockers and ten
> majors at the seams between waves — all six blockers and all fix-now
> majors are closed.
>
> Written 2026-05-26 at wave-5 close.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 5 | 603 active |
| Tests after wave 5 build (pre-audit) | 659 active (+56) |
| Tests after stitched-audit fixes | **682 active** (+79 wave-5 total) |
| `-W error::ResourceWarning` | clean (2 pre-existing weasyprint/openpyxl GC warnings, not failures) |
| Net new src/ modules | 2 (`cookie_auth`, `rules_v2026_6`) |
| Net new test modules | 3 (`test_wave5_ui`, `test_rules_v2026_6`, `test_system_audit_stitched_fixes`) |
| Rule packs total | 6 (v1 → v6) |
| Total registered rules | **60** (was 50) |
| New routes | `POST /engagement/<id>/whatif`, `GET /login`, `POST /login`, `POST /logout` |
| Spec amendments since wave 4 | §10.5 chronology refresh (v2026.6.0 added, v2026.5.0 closed) |

---

## 2. What shipped (W5.1 – W5.7)

### 2.1 Snapshot-aware /whatif form (W5.1)
`templates/engagement/detail.html` now reads the head snapshot and emits
one override row per preferred class — `shares_<name>` + `lp_mult_<name>`
inputs wired to `POST /engagement/<id>/whatif`. Empty-snapshot pages show
the explicit "no preferred classes on the head snapshot yet" message.
Replaces the wave-4 dev-text-area workaround.

### 2.2 Inline finding-resolution form (W5.2)
Each finding row on the detail page expands into a `<details>` block with
a form that `hx-post`s to `/engagement/<id>/resolve` and swaps in
`_resolution_ok.html` on success. Form-encoded payload is accepted in
addition to JSON; decision JSON is parsed out of the form field.

### 2.3 Subsequent events + snapshot diff panel (W5.3)
Detail page now shows a categorized rollup of subsequent events from the
engagement's snapshot chain, plus a historical resolutions table so prior
work stays visible across snapshot uploads.

### 2.4 DCF cross-workbook external-link references (W5.4)
`dcf_template.py` switched from same-workbook named ranges to Excel
external-link syntax — `='[dcf_sidecar.xlsx]Cap Inputs'!share_count_X`.
When the analyst opens both workbooks side-by-side, the template pulls
live values from the sidecar instead of showing `#NAME?`.

### 2.5 /whatif compute budget (W5.5)
A second `ExportRateLimiter` instance (`compute_limits.db`, soft 300/hr,
hard 600/hr) gates the engagement-bound `/whatif`. Closes wave-4 audit
m-6 (compute path was unrate-limited so a runaway HTMX page could melt
the box).

### 2.6 Rule pack v2026.6.0 — 60 rules (W5.6)
Ten new rules in `rules_v2026_6.py`:
G-IN-002 FEMA FCY price floor, G-IN-003 FEMA downround, G-IN-004 CCPS
conversion window, G-SG-001 IRAS deemed consideration, G-SG-002 FY
boundary, G-US-001 §409A presumption lapsed, G-US-002 §409A material
event, G-AICPA-003 common near zero, G-AICPA-004 junior OTM, G-CONV-002
convertible maturity past. All anchor against `valuation_date`, never
`date.today()`.

### 2.7 Browser session-cookie auth shim (W5.7)
`cookie_auth.py` — HMAC-SHA256 signed cookies (`qapita_session`), TTL
7 days, `httponly`/`SameSite=Strict`/`secure` in non-TESTING. `/login`
GET+POST + `/logout` POST blueprint. The engagement-blueprint guard
falls back to the cookie when no explicit Bearer is presented, so real
browsers can drive the HTMX UI without scripting Authorization headers.

---

## 3. Stitched whole-system audit

After the build closed, an independent Opus-level audit walked the
entire stack as a single deployable (~16k LOC, 60 rules across 6 packs,
659 active tests). Severity ladder: blocker (ship-stop), major
(pre-prod), minor (pre-external-audit). Findings filed at
`SYSTEM_AUDIT_STITCHED.md`.

### 3.1 Blockers (all closed)

| ID | Finding | Fix landed |
|---|---|---|
| B-1 | DCF sidecar + template emitted divergent slugs when an excluded class collided with an included class — per-class FV silently pointed at the wrong class | sidecar enumerates non-excluded classes only for slug counter + defined-names; excluded classes still appear in the Cap Inputs sheet but receive no named range |
| B-2 | Bundle `.zip` byte-unstable across regenerations (`datetime.now` in manifest + wall-clock entry mtimes) — broke the auditor recompute promise | every `writestr` uses `ZipInfo(date_time=(1980,1,1,0,0,0))`; `generated_at` pinned to `engagement.created_at` (stored) |
| B-3 | Stored XSS via class name in `{{ chart_json\|safe }}` — uploaded `</script>` payload broke out of `<script>...</script>` | both templates now pass the chart dict to `\|tojson`; literal `</script>` becomes `</script>` |
| B-4 | Open redirect on `/login` + `/logout` via unvalidated `next` param | `_safe_next_url()` rejects any URL with a scheme/netloc or that starts with `//`; falls back to `/engagement/?html=1` or `/login` |
| B-5 | Cookie silently overrode Bearer when both present — partner cookie + analyst Bearer acted as partner | explicit Bearer beats ambient cookie; cookie path only fires when no Authorization/X-Auth-Token is supplied |
| B-6 | `/upload` defaulted `expected_version` to the current version when missing, defeating the optimistic-concurrency contract (GAP-01 / §8.12) | route now returns 400 `missing-expected-version` like `/transition` does |

### 3.2 Fix-now majors (closed)

| ID | Finding | Fix landed |
|---|---|---|
| M-1 | Memo cover timestamp was wall-clock; spec carve-out allowed it but byte-stability was lost | `PDFInputs.generated_at` + `build_audit_memo(generated_at=)` accept a pinned `datetime`; engagement memo route passes `eng.created_at` |
| M-2 | Compute rate-limit alert was silent — no audit-log trace when a script DOSes `/whatif` | new `AuditEventType.compute_burst_alert`, edge-triggered when `current_count == hard_limit` |
| M-3 | `review → open` transition existed in `_ALLOWED_TRANSITIONS` but no role had the permission — dead branch | `engagement.transition_review_to_open` granted to partner |
| M-4 | Legacy `/whatif/<token>` in `app.py` bypassed the wave-5 compute budget | kept (still drives the phase-0 demo flow) but now consumes the compute limiter against the session token; comment cites SD-AUD-M4 |
| M-5 | `attach_login_blueprint` ordering invariant was unstated and load-bearing | accepts an explicit `identity_provider` arg; raises in non-TESTING if `SESSION_SECRET_KEY` is missing from env/config |
| M-7 | `_enforce_export_limit` took a raw `eng_id` string and could have written audit events against unvalidated ids | takes a validated `Engagement` object; both callers fetch the engagement first |
| M-8 | Rate-limit window was a 2-bucket sum (effective window between 1h and 2h depending on position) — soft limit could be doubled at boundary | single-bucket calendar-hour policy (`hour_bucket = ?` not `>= ? - 1`) |
| M-9 | Spec §10.5 listed only 5 packs; v2026.6.0 shipped but was undocumented | §10.5 now lists all 6 packs, documents v2026.5.0's 1-day window explicitly |
| m-2 | `SESSION_SECRET_KEY` doc was misleading + missing in prod was a silent footgun | covered by M-5 (explicit raise) + app.py-level dev-key fallback for the demo runtime |
| m-9 | `_row_to_engagement` swallowed `ValidationError` silently when valuation_date couldn't be parsed | now logs `WARNING` with the engagement id + offending value before falling back to `None` |

### 3.3 Deferred (post-wave-5 backlog)

| ID | Finding | Defer rationale |
|---|---|---|
| M-6 | No CSRF tokens on POST routes | `SameSite=Strict` + the B-3 XSS fix close the realistic vectors; Flask-WTF wiring is 2h of work that's better landed alongside a real prod cutover |
| M-10 | Finding-code collision check is CI-only, not a startup check | nothing fires it today; add when the rule pack passes 75 rules |
| m-1 | Global `Cache-Control: no-store` blocks browser back-button | demo UX is fine; relax when the prod nav pattern is fixed |
| m-3 | Cookie `Secure` flag may bite local-HTTPS-off prod | tie to the prod-proxy config decision |
| m-4 | `current_engine_commit()` returns `unversioned` in OCI deploys | document in OPERATIONS; build-time env var in the deploy story |
| m-6 | `load_workbook` not closed on upload exception path | GC handles it; revisit if upload volume warrants |
| m-8 | Cookie payload `|` separator | uuid user_ids today; harden when SSO assigns free-form ids |
| m-12 | `subprocess` per `head_pack` invocation | move to module-level cache if we ever start calling `head_pack` per-request |

---

## 4. Things checked clean by the stitched audit

- Hash chain construction + recomputation
- Optimistic concurrency on transition + add_snapshot (atomic conditional UPDATE + rowcount check)
- Pydantic v2 sort-keys serialisation
- `_engagement_errors` HTML/JSON content negotiation with q-values
- `_extract_token` refusing query-string tokens in non-TESTING
- Parameterised SQL throughout
- Path-traversal validation in pack version (`_PACK_VERSION_RE`)
- PDPA redaction sentinel + immutability
- Subsequent events anchored on `head_snapshot_id`
- Rule-pack `effective_from`/`effective_to` non-overlapping windows
- 60 rules collision-free against the rich fixture
- No `date.today()` in any `rules_v2026_*.py`
- Audit-log immutability (append-only, hash-chained)
- Permission table coverage (post-M-3) — every transition has at least one role

---

## 5. Files touched (post-audit fix batch)

| File | Reason |
|---|---|
| `src/engagement_routes.py` | B-6 (upload expected_version), B-5 (Bearer-over-cookie), M-2 (compute alert), M-7 (engagement object) |
| `src/cookie_auth.py` | B-4 (`_safe_next_url`), B-5 (logout scope doc), M-5 (identity_provider arg + prod-secret raise) |
| `src/engagement_bundle.py` | B-2 (ZipInfo epoch + pinned generated_at) |
| `src/engagement.py` | M-2 (compute_burst_alert enum), m-9 (warn log on valuation_date fallback) |
| `src/dcf_sidecar.py` | B-1 (filtered slug counter + skip defined-names on excluded) |
| `src/rate_limit.py` | M-8 (single-bucket calendar hour) |
| `src/identity.py` | M-3 (`transition_review_to_open` grant to partner) |
| `src/audit_memo.py` | M-1 (`generated_at` param) |
| `src/pdf_memo.py` | M-1 (`PDFInputs.generated_at` field + context wiring) |
| `app.py` | B-3 (drop `chart_json`/`scenario_chart_json` args), M-4 (compute-limit the legacy route), m-2 (env-secret resolution) |
| `templates/waterfall.html` | B-3 (`\|tojson`) |
| `templates/_whatif_panel.html` | B-3 (`\|tojson`) |
| `SYSTEM_SPEC.md` | M-9 (§10.5 chronology v2026.6.0) |
| `tests/test_system_audit_stitched_fixes.py` | new — 22 regression tests, one per blocker + each fix-now major |

---

## 6. What's next

Wave 5 closes the cross-wave seams. The engagement + audit half of the
system is now Big-4-defensible end-to-end; the browser half is XSS-clean,
open-redirect-safe, byte-stable on the bundle, and explicit on
authentication precedence. Outstanding spec work for any future wave:

1. Land CSRF tokens (M-6) when the production cutover plan settles.
2. Wire the startup collision check (M-10) once the rule pack passes
   ~75 rules and the manual fixture coverage stops being credible.
3. Document the Bearer-revocation contract in §10.x (the /logout-Bearer
   carve-out from B-5).
4. Build a cross-wave integration test surface so the next stitched audit
   has fewer first-week-of-prod surprises to catch (the unit suite couldn't
   have found any of the six blockers — they all lived at the seams).
