# Cap Table Reconciler

A small, local tool for the part of cap-table work that sits **before** the model.

Most of an analyst's hours on a private-company valuation aren't spent on judgment — they're spent reconciling what the client sent. A stale option pool. A SAFE that should have converted at the last round. A side letter with terms nobody transcribed. An anti-dilution column that says *"see charter."* This tool ingests that file, points at every gap, and produces structured output an analyst can hand to an OPM, Backsolve, or DCF.

> **Zero valuation judgments.** No 409A. No Backsolve. No fair-value computation. No LLM in the calculation pipeline. Every finding is rule-based and cites the field it came from.

**The posture is expert-led, not algorithm-only.** When the file is too messy to defensibly compute on, the tool refuses and writes the punch list. That refusal — and the punch list — is the deliverable.

---

## In 30 seconds

- **Input:** one `.xlsx` cap table per snapshot. Optionally text-PDF side letters.
- **Process:** parse → 60-rule checklist (jurisdictional + structural) → in-session adjudication with citations → engagement-bound persistence → hash-chained audit log → byte-stable bundle.
- **Output:** structured JSON, static `.xlsx`, **live-formula `.xlsx`** (edit a share count in Excel, breakpoints recompute natively), DCF sidecar + cross-workbook template, PDF audit memo with `[ANALYST]` placeholders, snapshot timeline + N-way diff, Big-4-portable `bundle.zip` with auditor-recompute recipe.
- **Workflow:** browser HTMX UI (cookie auth + CSRF + Bearer revocation) drives the analyst flow; API surface for programmatic clients.

---

## What it does

1. **Parse a messy workbook.** Locates the cap-table tab by name pattern, scans for headers despite title rows, skips embedded subtotals, normalizes date formats, coerces instrument-type aliases (`CCPS`, `RCPS`, `Ordinary`) to the canonical enum. Reports everything inferred and everything dropped.
2. **Run the rule pack.** 60 deterministic rules across 6 chronologically-pinned packs (`v2026.1.0` → `v2026.6.0`). Anti-dilution coverage, SAFE conversion checks, side-letter open-questions, FEMA/§409A/IRAS jurisdictional flags, pari-passu seniority, full-ratchet trigger documentation, etc. Each finding cites the rule id + the field path.
3. **Adjudicate inline.** Browser form per finding. Decision + citation (required) lands as an immutable `Resolution` linked to the snapshot id. The hash chain records who resolved what with what citation.
4. **Compute the waterfall.** Breakpoints, per-tranche allocation matrix. Handles non-participating, participating-uncapped, participating-with-cap including senior-above-capped.
5. **Persist the engagement.** Status lifecycle (open → review → signed → archived) with role-gated transitions, optimistic concurrency, pack-bytes pinned at create-time, append-only hash-chained audit log per engagement.
6. **Snapshot timeline + N-way diff.** Chronological browse of every snapshot; select 2+ → magnitude-tiered drift table (none / minor / material / major) per (class, field); export as xlsx workpaper or PDF.
7. **Export the workpaper.** Static `.xlsx`, live-formula `.xlsx`, DCF sidecar + cross-workbook template with external-link refs, PDF audit memo with auto-embedded snapshot drift section, portable `bundle.zip` containing every artefact a Big-4 auditor would need to re-verify offline.

---

## Architecture map (where things live)

```
src/
  parser.py              — Excel → CapTable (header inference, alias map, date coercion)
  models.py              — Pydantic v2 schema (CapTable, ShareClass, LP, SAFE, …)
  checklist.py           — 60-rule registry + @rule decorator
  rules_v2026_{1..6}.py  — six chronologically-pinned rule packs
  rule_pack.py           — pack loading, head_pack(today), startup collision guard
  waterfall.py           — breakpoint + allocation engine
  diff.py                — pairwise cap-table diff
  snapshot_timeline.py   — N-way diff primitive (magnitude tiers)
  diff_workpaper.py      — xlsx workpaper builder
  formula_workbook.py    — live-formula xlsx exporter
  dcf_sidecar.py         — DCF input sidecar (named ranges, defined-names)
  dcf_template.py        — DCF template with external-link refs to sidecar
  audit_memo.py          — markdown memo skeleton
  pdf_memo.py            — PDF memo + diff workpaper PDF (WeasyPrint)
  engagement.py          — EngagementStore (SQLite), hash chain, redaction
  engagement_routes.py   — Flask blueprint (engagement REST surface + HTMX UI)
  engagement_bundle.py   — Big-4-portable bundle.zip builder
  cookie_auth.py         — HMAC-signed session cookies + CSRF double-submit
  token_deny.py          — Bearer revocation deny list (SQLite, WAL)
  identity.py            — IdentityProvider abstraction + StubSSOProvider
  rate_limit.py          — per-user calendar-hour rate limiter
  subsequent_events.py   — rollup of resolved findings across snapshots
  vol_pack.py            — vol assumptions for OPM tail-vol flags

templates/
  engagement/            — HTMX UI (base, list, detail, snapshots, diff, login, error)
  memo/                  — PDF memo (base.html, diff.html)
  waterfall.html         — phase-0 demo waterfall page
  _whatif_panel.html     — phase-0 demo whatif HTMX panel

rule_packs/              — six packs v1..v6, plus v0.0.0-dev for fixtures
fixtures/                — 5 curated + 1 stress-test fixture
tests/                   — 760+ tests (every wave, every audit fix)
SYSTEM_SPEC.md           — full spec, rounds 1-5
OPERATIONS.md            — prod deploy checklist
BUILD_WAVE_{1..8}.md     — per-wave build notes
SYSTEM_AUDIT_*.md        — independent audit reports
```

---

## What it explicitly does **not** do

- No OPM allocation, no DLOM, no fair-value opinion, no 409A.
- No LLM clause extraction. Side letters stored verbatim; open Q-lines surfaced for adjudication.
- No auto-conversion of SAFEs or convertible notes — too many opinions baked in.
- No real SSO. `StubSSOProvider` is the dev/demo IdP — refuses to mount in non-TESTING unless `ALLOW_STUB_SSO=1` is set explicitly.
- No production database choice. SQLite abstracts cleanly behind `EngagementStore(db_path=...)` for a Postgres swap.

---

## Run it (dev)

```bash
git clone <repo>
cd qapita
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python app.py
```

Open <http://localhost:5050>. The phase-0 demo flow (upload → waterfall → what-if) is available for screen-share; the engagement flow lives under `/engagement/?html=1`.

For prod-shaped deploys, the phase-0 demo routes refuse to serve unless `ALLOW_PHASE_0_DEMO=1` is set. See `OPERATIONS.md §10` for the full env-var checklist (`SESSION_SECRET_KEY`, `QAPITA_ENGINE_COMMIT`, `ALLOW_STUB_SSO`, `ALLOW_PHASE_0_DEMO`).

---

## Run the tests

```bash
pytest                                    # full suite
pytest tests/test_wave7_diff.py -v         # one wave's tests
pytest -W error::ResourceWarning           # promote framework finalizer noise
pytest -k "B-W7-1 or W6B"                  # tests by audit finding id
```

760+ tests, every audit-fix encoded as a regression. Suite runs in ~60s.

---

## Operational CLI

```bash
flask --app app prune-deny-list          # drop expired Bearer-revocation entries
flask --app app prune-rate-limits        # drop rate-limit buckets > 7 days old
flask --app app hard-delete-archived     # cascade-delete archived engagements past restore window
```

Schedule these in cron / systemd-timer / k8s CronJob. None of them run automatically; absence is correctness-safe but disk-usage degrades.

---

## Health probes

```
GET /healthz   → {"status": "ok"}          (liveness)
GET /readyz    → {status, engine_commit, rule_pack_head_version,
                  deny_list_size, engagements_total, audit_log_total,
                  last_engagement_created_at}                  (readiness + SRE)
```

---

## Engagement flow at a glance

```
analyst                      partner / reviewer            big-4
   │                                  │                      │
   ▼                                  │                      │
 /login (cookie + CSRF)               │                      │
   │                                  │                      │
 POST /engagement/                    │                      │
   │ (create + bind rule pack)        │                      │
   │                                  │                      │
 POST /upload (+ change_note)         │                      │
   │ (snapshot, 60 rules run)         │                      │
   │                                  │                      │
 POST /resolve (per finding)          │                      │
   │ (decision + citation)            │                      │
   │                                  │                      │
 POST /transition (review)            │                      │
   │ ────────────────────────────────►│                      │
   │                                  │                      │
   │                       POST /transition (signed)         │
   │                       (blocker gate fires)              │
   │                                  │                      │
 GET /memo.pdf                        │                      │
 GET /diff.xlsx, /diff.pdf            │                      │
 GET /bundle.zip ─────────────────────────────────────────►  │
                                                             │
                                            offline recompute:
                                            audit_log SHA-256
                                            chain verification
                                            + per-file SHA-256
```

---

## License

MIT.
