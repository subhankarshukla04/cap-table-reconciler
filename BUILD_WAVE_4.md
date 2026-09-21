# Build Wave 4 — What Shipped

> Wave 4 turned the engagement model into a browser-usable application:
> HTMX UI pages alongside the JSON API, pack-bytes pinned at engagement
> create so the bundle is fully self-contained, a full DCF model
> template, the rule pack expanded to 50 rules, the deferred
> `valuation_date` typing fix, and a what-if scenarios HTMX panel.
>
> Written 2026-05-25 at wave-4 close. Next step is the user's
> compiled audit pass; no per-wave audit ran in-build per user direction
> ("go through everything, then we'll do an audit").

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 4 | 571 active |
| Tests after wave 4 | **603 active** (+32 new) |
| `-W error::ResourceWarning` | clean |
| Net new src/ modules | 3 (`dcf_template`, `rules_v2026_5`, vol_pack additions) |
| Net new test modules | 4 (engagement_html, whatif_htmx, dcf_template, rules_v2026_5) |
| Rule packs total | 5 (v1 → v5) |
| Total registered rules | **50** (was 37) |
| New Flask blueprint surface | HTMX content-negotiation on every existing route + new POST `/whatif` |
| Spec amendments since wave 3 | none in wave 4 itself (round 2 already covered the design) |
| Deferred audit items closed | M-6 (`valuation_date` typing), M-4 (audit M4 pack-bytes persistence) |

## 2. What shipped

### 2.1 HTMX UI surface (W4.1)

`templates/engagement/` (3 new templates) + content-negotiation in
`engagement_routes.py`. The same routes now serve:
- JSON to API clients (no behaviour change — every wave 2/3 test still passes)
- HTML when `?html=1` query param OR `Accept: text/html` header

Pages:
- `engagement/base.html` — shell with nav + flash messages, HTMX CDN
- `engagement/list.html` — paginated list with all wave 3 filters as form inputs
- `engagement/detail.html` — engagement view, snapshot table, transition
  buttons (computed per role), exports panel, what-if scratchpad
- `engagement/_whatif.html` — partial template returned by /whatif

Form handling supports both JSON and form-encoded payloads on every
mutating route (create, upload, transition). HTML success paths
redirect via 302; JSON paths still return the same dict shapes.

Templates use Jinja2 autoescape (XSS-safe by default; covered by
`test_xss_safe_in_html_render`).

### 2.2 Pack-bytes-at-bind persistence (W4.2 — closes wave-2-audit M4)

Engagement schema gains `bound_pack_json` column; idempotent migration
on store init. `create_engagement` now loads the rule-pack JSON at
create time and stores the bytes alongside the engagement. The bundle
exporter prefers these pinned bytes over disk lookup, so:
- A rule_packs/*.json that gets pruned post-create doesn't break bundles
- Bundle is fully self-contained — no external dependency on the repo's
  pack files
- The version-skew failure mode from CODE_AUDIT_WAVE_2 M4 is impossible

Backward compat: legacy engagements created before the migration still
load (bound_pack_json defaults to None; bundle falls back to disk).

### 2.3 DCF model template (W4.3)

`src/dcf_template.py` + `build_dcf_template(cap_table)`. Six-sheet
Excel workbook with:
- "Read Me" — usage notes
- "Assumptions" — yellow input cells for Revenue growth, EBITDA margin,
  Capex %, NWC %, WACC, terminal growth, tax rate, net debt, cash
- "Projection" — 5-year FCFF rollout with explicit formulas
- "Terminal Value" — Gordon-growth TV + PV
- "Equity Bridge" — EV → equity value with debt/cash adjustments
- "Per-Class FV" — per-class allocation via `=share_count_<Slug>`
  references to the W1 DCF sidecar's named ranges

Pairs with the wave-1 `dcf_sidecar.py` (named ranges for share counts +
LP amounts + conversion ratios) and the wave-3 `vol_pack.py` (sourcing
fields for vol/time/rfr). Tool fills STRUCTURE only — every assumption
is a yellow cell the analyst defends.

### 2.4 Rule pack v2026.5.0 (W4.4) — total 50 rules

`src/rules_v2026_5.py` + `rule_packs/v2026.5.0.json`. 13 new rules:

| ID | Triggers on |
|---|---|
| `G-ESOP-001` | Reserved ESOP exists but no granted ESOP shares |
| `G-ESOP-002` | Granted ESOP exceeds total preferred share count |
| `G-ESOP-003` | Granted ESOP exists with no §83(b) / early-exercise mention |
| `G-VIMA-001` | Singapore jurisdiction → VIMA founder-vesting reminder |
| `G-VIMA-002` | Convertible note with both cap AND discount (double-dip risk) |
| `G-OJK-001` | Indonesia jurisdiction → DNI / POJK foreign-ownership reminder |
| `G-AUDIT-001` | Valuation date > 12 months after most recent priced round |
| `G-AUDIT-002` | Valuation date is in the future |
| `G-PRF-001` | Preferred class notes mention "dividend" or "cumulative" |
| `G-PRF-002` | Preferred class notes mention "redemption" / "put right" |
| `G-CAP-001` | Preferred class with conversion_ratio < 1.0 |
| `G-CAP-002` | Share class with zero outstanding shares |
| `G-WAR-002` | Warrant expiry date has passed |

`rule_packs/v2026.4.0.json` closed at 2027-02-28 to make room for v5.

### 2.5 `valuation_date` typing fix (W4.5 — closes audit M-6)

`Engagement.valuation_date` changed from `Optional[str]` to
`Optional[date]` with a Pydantic `field_validator(mode="before")` that
accepts ISO strings, date objects, or datetimes. Garbage like
`"not-a-date"` is refused at construction time with a clear error.

`engagement_routes.list_engagements` updated to parse `date_from` /
`date_to` query params with `date.fromisoformat()` and return HTTP 400
`bad-date-filter` on malformed inputs. Date arithmetic is now real
date math, not string comparison.

DB serialisation: stores ISO strings on write, parses via the validator
on read. Backward compat with existing rows preserved.

### 2.6 What-if HTMX panel (W4.6)

New `POST /engagement/<id>/whatif` route returns the rendered
`_whatif.html` partial. Accepts `shares_<ClassName>` and
`lp_mult_<ClassName>` form fields; recomputes the waterfall under the
override and shows a side-by-side breakpoints table plus a
human-readable changed-inputs list. Reuses the BUG-010 zero-share
fallback fix from wave 2.

## 3. Architectural deltas (wave 3 → wave 4)

```
[Identity + Engagement]
    ↓ (unchanged)
[Engagement Store]
    + bound_pack_json column (W4.2)
    + valuation_date typed as `date` (W4.5)
    ↓
[Blueprint /engagement/*]
    + HTML content-negotiation on every route (W4.1)
    + POST /whatif scenarios endpoint (W4.6)
    + valuation_date filter parses ISO strings (W4.5)
    ↓
[Templates engagement/*.html]                   ← NEW
    base.html — shell with HTMX CDN
    list.html — filter form + paginated table
    detail.html — snapshot table, transition buttons, what-if scratchpad
    _whatif.html — partial returned by /whatif
                                            ↓
[Exporters]
    + dcf_template.py — 6-sheet DCF workbook (W4.3)
    + dcf_sidecar.py (W1) — named ranges
    + vol_pack.py (W3.4) — sourcing fields
    + formula_workbook + snapshot stamp (W3.5)

[Rule packs]
    50 rules across 5 packs
    v2026.5.0 includes ESOP / VIMA / OJK / audit-trail / preferred /
    capital / warrant edge cases
```

## 4. Test coverage of the wave

```
tests/test_engagement_html.py     9 tests   HTMX UI surface + XSS
tests/test_whatif_htmx.py         4 tests   /whatif partial + overrides
tests/test_dcf_template.py        5 tests   DCF template structure + bytes
tests/test_rules_v2026_5.py      14 tests   v2026.5.0 expansion
                                 ──
                                 32 new wave-4 regression tests
```

Plus 571 from waves 0–3 + the compiled-system audit fixes:
**603 active tests, all green** (1 slow benchmark deselected by default),
**zero `ResourceWarning`** under `-W error::ResourceWarning`.

## 5. What is stubbed for Evelyn (cumulative)

Unchanged from BUILD_WAVE_3.md §3 except:
- **#8 GAP-39 engagement-level tenancy ACL** — wave 4 didn't ship anything
  new; reviewer/partner still scope by `?client_id=`. The per-token
  scoping for `read_only_auditor` still pending.
- **#4 engagement workflow integration** — now usable from a browser
  via the HTMX UI; reviewer can transition, generate memo, download
  bundle without curl.

No new items added this wave.

## 6. Wave 5 candidates (when next requested)

Order if the next wave starts:
1. Postgres-backed `EngagementStore` (needs Vamsee's call on production DB)
2. Per-token engagement ACL (GAP-39 full) — needs Evelyn's scoping semantics
3. Wider rule pack expansion + jurisdiction depth (India FEMA depth, Singapore tax)
4. Inline finding-resolution form in the HTMX detail page
5. Snapshot diff visualization in the HTMX UI (uses W3.1 subsequent_events)
6. Real Tesseract install + system-test pipeline (system dep — needs IT)
7. Auto-generate per-class share-count form fields on the what-if panel
   (currently W4.6 ships an empty form; analyst types field names by hand)

Wave 5 needs at least the SSO + DB choice items from §5 unlocked, or
it'll keep building against stubs that get rewritten when Evelyn's
answers land.

## 7. One sentence

Wave 4 took the engagement model from "library-complete with HTTP
JSON" to "browser-usable HTMX app with self-contained bundles, a real
DCF template, 50 versioned rules, and tightened type discipline" —
603 tests green, zero resource leaks, ready for the next audit
cycle when you call it.
