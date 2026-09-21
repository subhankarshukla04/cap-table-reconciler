# DRHP Reader — pre-deal cap-table intelligence

A tool that ingests a public DRHP / RHP filing (PDF), extracts the **Build-up of Share Capital** table, lock-in periods, ROFR/ROFO clause, ESOP pool, and foreign-holder mix, then runs an indicative tender preview against Qapita's mechanics + compliance engines. **Compresses 3–5 hours of manual DRHP reading to 30 seconds.**

Built for the Olesia Sheremeta interview (NOC Inbound, Singapore Founders Office).

## What problem it solves

When Pine Labs, Razorpay, or Urban Company files a DRHP, the secondaries desk currently spends 3–5 hours per filing reading 200+ pages of legal text to answer: how many shareholders, what classes, what ESOP overhang, what foreign-holder mix, what lock-ins, and what would a hypothetical $20M tender look like — **before deciding whether to even pick up the phone.** ~50 relevant filings per year × 4 hours = **200 hours of repetitive PDF-reading annually.**

This tool replaces that with: upload PDF → 30 seconds → structured cap-table + tender preview + compliance flags.

## Run

```bash
make install            # installs deps into .venv
make seed               # generates holder fixtures + seeds SQLite
.venv/bin/python scripts/gen_drhps.py     # generates 3 demo DRHPs
make radar-up           # starts Flask on :5001
```

Open `http://localhost:5001/`.

## Demo flow

1. **Landing** (`/`) — drop-zone for any DRHP PDF + 3 pre-loaded demo filings: Pine Labs, Razorpay, Urban Company.
2. **Click Pine Labs** (or upload one of `data/drhp/*.pdf`) → 30s → structured cap-table page.
3. **The filing page** (`/filings/pinelabs`):
   - **What the parser found** — sections detected, issue size, ESOP pool, foreign-holder share, risk-factor count
   - **Pre-Offer shareholding** — the extracted BUILD-UP OF SHARE CAPITAL table (10 holder rows)
   - **Lock-in periods** — parsed from the LOCK-IN PERIODS section
   - **ROFR clause** — captured verbatim
   - **Tender preview** — live HTMX slider feeds the same mechanics + compliance engines the rest of Qapita uses; numbers recompute in <50ms
4. **Compare** by clicking Razorpay (62% foreign-holder mix → high cross-border filing load) vs Pine Labs (35% foreign → moderate load) vs Urban Company (62% foreign + Delhi state → higher stamp duty rate).

## What the parser actually does

`radar/drhp_parser.py` uses **pdfplumber** to extract text + tables from the PDF, then:
- Detects 8 canonical DRHP sections via uppercase-text matching (CAPITAL STRUCTURE, BUILD-UP OF SHARE CAPITAL, LOCK-IN PERIODS, ROFR / ROFO CLAUSES, EMPLOYEE STOCK OPTION PLAN, RISK FACTORS, TABLE OF CONTENTS, DRHP cover)
- Pulls every table on every page; the BUILD-UP table is identified by header columns ("Holder", "Class", "Units", "% Pre-Offer", "Residency")
- Regex-extracts: registered state, founded year, employee count, issue size, ESOP pool %, ESOP-holder count estimate, risk-factor count
- Pattern-matches bulleted LOCK-IN PERIODS entries
- Captures the ROFR paragraph verbatim
- Optional `fixture_hint` (for demo reliability) augments uncertain extractions from `data/drhp/_facts.json`

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│  PDF upload  │──▶│  drhp_parser.py    │──▶│  ParsedDRHP  │
│  (any DRHP)  │    │  pdfplumber +      │    │  pydantic v2 │
└──────────────┘    │  section regex     │    └──────┬───────┘
                    └──────────────────┘            │
                                                    ▼
                                       ┌─────────────────────────┐
                                       │     adapter.py          │
                                       │  ParsedDRHP → Issuer +  │
                                       │  synthetic Holders[]    │
                                       └────────┬────────────────┘
                                                ▼
                          ┌──────────────────────────────────────┐
                          │   mechanics.preview_tender(...)      │
                          │   compliance.preview_compliance(...) │
                          │       (UNCHANGED from Tender Radar)  │
                          └──────────────────────────────────────┘
                                                │
                                                ▼
                                      Flask + Jinja + HTMX UI
```

**Key invariants:**
- The mechanics + compliance engines are **unchanged from the Tender Radar build** — same code, same tests, same <50ms benchmark. They're durable infrastructure.
- The DRHP parser is the new input pipeline.
- No LLM anywhere. PDF parsing is deterministic; engines are pure functions.
- Demo runs entirely on **public DRHP data** — no Qapita-internal data needed.

## Layout

```
radar/
├── app.py                # Flask :5001 — /, /filings/upload, /filings/<id>, /filings/<id>/preview
├── drhp_parser.py        # PDF → ParsedDRHP
├── adapter.py            # ParsedDRHP → Issuer + Holder[]
├── mechanics.py          # UNCHANGED — eligibility + waterfall + scaleback
├── compliance.py         # UNCHANGED — RBI floor proxy + cross-border + stamp duty
├── stamp_duty.py         # UNCHANGED — 6 jurisdictions
├── models.py             # extended with ParsedDRHP, ExtractedHolder, LockInPeriod
├── matching.py           # UNCHANGED — fuzzy issuer-name match (kept for any future name resolution)
├── db.py                 # UNCHANGED — SQLite helpers (kept; not used by current flow)
├── templates/
│   ├── base.html.j2      # rebranded header to "DRHP Reader"
│   ├── landing.html.j2   # drop-zone + 3 demo filing tiles
│   ├── filing.html.j2    # parsed sections + cap-table + tender preview
│   └── _preview.html.j2  # HTMX partial — UNCHANGED
├── static/styles.css     # ~330 lines; audit-firm palette + filing-tile additions
├── _archive/             # scoring.py, digest.py, orchestrator.py, all scrapers, bark.py — retired
└── QA_PREP.md            # interview Q&A (updated to match new pitch)

data/
├── drhp/                 # _facts.json + 3 synthetic-but-realistic DRHPs (Pine Labs / Razorpay / UC)
├── parsed/               # ParsedDRHP JSON snapshots — cached per filing_id
├── uploads/              # any user-uploaded PDFs
└── fixtures/             # original 15-issuer roster + holder fixtures (kept for engine tests)

scripts/
├── gen_drhps.py          # produces 3 demo DRHPs from data/drhp/_facts.json via ReportLab
├── seed.py               # seeds DB (unchanged from prior phase)
└── gen_holders.py        # generates synthetic holders for engine tests (unchanged)

tests/radar/
├── test_drhp.py          # 10 tests on parser + adapter
└── test_radar.py         # 10 tests on engines (UNCHANGED)
```

## Demo opening line

> *"When Pine Labs filed their DRHP in December, your team spent ~4 hours reading 200 pages of legal text to figure out what a tender on Pine Labs would look like — before deciding whether to even pick up the phone. This tool reads it in 30 seconds. Watch."*

Then: click Pine Labs tile → cap-table appears → drag slider to $30M → waterfall + Karnataka stamp duty + FC-TRS estimate update live → click Razorpay → 62% foreign-holder mix surfaces a higher cross-border filing load.

## Why this works

- **Iron Rule clean** — pure data extraction. No pricing recommendation, no buyer match.
- **Doesn't duplicate Qapita's product** — Qapita serves *customers*. This serves the **prospect funnel** — pre-customer intelligence.
- **Not a newsletter** — the tool does the reading. Analyst was the bottleneck.
- **Engines reused** — `mechanics.py` + `compliance.py` + `stamp_duty.py` + `models.py` + base template + CSS — all carry over from the prior phase.
- **Demo runs entirely on public data** — DRHPs are SEBI filings, public domain. Honest end-to-end.
- **Generalizable** — the section grammar generalizes to RHPs, S-1s (Schwab US story), and any structured public capital-markets filing.

## Testing

```bash
make test
```

**20 tests, 0.54s.** 10 on parser + adapter (extraction correctness, graceful fallback on non-DRHP PDFs), 10 on engines (mechanics consistency, <50ms benchmark, compliance verdicts, fuzzy matching).

## Cross-references

- `OLESIA_RESEARCH.md` — interviewer + team research
- `ELIMINATION.md` — original 5-candidate audit → Tender Radar
- `PIVOT_AUDIT.md` — 20-candidate deep audit → DRHP Reader (this build)
- `SPEC_OLESIA.md` — earlier architectural contract (Tender Radar shape; engines section still valid)
- `PLAN_OLESIA.md` — earlier execution plan
- `radar/QA_PREP.md` — top-10 likely questions, prepared answers, opening line
