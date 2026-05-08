# Cap Table Reconciler

A local-first tool that ingests messy client cap-table `.xlsx` files, runs a deterministic gap-detection checklist, and produces a clean structured liquidation waterfall with breakpoints. The output is the **input layer** to your existing OPM, Backsolve, or DCF workflow — the tool itself makes zero valuation judgments.

Built around the practitioner observation that cap-table cleanup is the single largest hour drain on a small valuations team, and a top reason audit memos are sent back. The fix is structural: catch missing fields *before* any math runs, refuse to compute when a blocker is open, and produce output that's defensible under audit.

> **Scope discipline.** No 409A. No Backsolve solver. No fair-value computation. No LLM in the calculation pipeline. Every finding is rule-based and deterministic.

## What it does

1. **Ingest** — accepts a `.xlsx` cap table (clean or structurally messy: title rows, mid-data subtotals, footnote-prose columns, mixed date formats are all handled).
2. **Detect gaps** — runs eight rules covering anti-dilution variant, full-ratchet trigger documentation, participating-with-cap presence, stale option pool dates, unrecorded SAFE conversions, vendor warrants, side-letter scope questions, and dual-class voting differentials.
3. **Resolve in-session** — each blocker has an inline form: pick a variant, attach a citation, recompute. Resolutions are logged and persist with the session.
4. **Compute the waterfall** — breakpoints (LP-cleared, conversion thresholds, participation-cap thresholds, pure-conversion thresholds), per-tranche marginal allocation matrix, conversion thresholds. Handles non-participating, participating-uncapped, participating-with-cap (including the senior-above-capped case from the NVCA worked examples).
5. **Export** — clean structured output as JSON, static `.xlsx`, **or a live formula workbook** where the analyst can edit Inputs in Excel and watch breakpoints, allocations, and the chart update natively.

## Headline features

| Feature | What it is | Why it matters |
|---------|------------|----------------|
| **Live formula workbook** | 8-sheet `.xlsx` with named ranges, States matrix, IF/SUMPRODUCT formulas. Edit a share count, watch the chart update. | Analyst takes the workbook home and iterates without re-running the tool. |
| **Side-letter PDF intake** | `pdfplumber` extracts text from a side-letter PDF; attached as a `SideLetter` on the cap table. Heuristic title detection + open-question extraction. | Common ingestion path; replaces manual transcription. |
| **Cap-table snapshot diff** | Upload two `.xlsx`, fuzzy-match share classes (Levenshtein), get a structured class-by-class delta. | Fills the audit memo's *subsequent events* section deterministically. |
| **SQLite session persistence** | Sessions survive server restart; analyst can come back to the tab tomorrow. | No "I have to re-upload" friction during multi-day reviews. |
| **In-session resolutions** | Each finding has an inline form (anti-dilution variant picker, warrant treasury-method toggle, side-letter scope adjudication, pool-date refresh). | Closes the blocker → recompute loop without a roundtrip to Python. |

## What it explicitly does **not** do

- No OPM Backsolve solver — judgment work belongs to the analyst, not the tool.
- No fair-value output, no DLOM, no volatility peer-set.
- No auth, no multi-tenancy, no anonymizer.
- No deployment to any cloud — local-only via `http://localhost:5050`.
- No LLM-based clause extraction — side letters are stored verbatim, the analyst transcribes any structured overrides.

## Architecture

```
cap-table-reconciler/
├── app.py                       Flask routes
├── src/
│   ├── models.py                pydantic v2 (CapTable, ShareClass, ...)
│   ├── parser.py                Excel → CapTable, structural-mess handling
│   ├── pdf_intake.py            pdfplumber → SideLetter
│   ├── checklist.py             8 gap-detection rules
│   ├── waterfall.py             breakpoint + allocation computation
│   ├── formula_workbook.py      Live formula workbook builder (8 sheets)
│   ├── diff.py                  Cap-table snapshot diff
│   └── persistence.py           SQLite SessionStore
├── templates/                   Jinja2 templates (audit-firm aesthetic)
├── static/css/main.css          slate/blue palette, monospace numbers
├── fixtures/                    Fixtures with provenance
├── scripts/                     Fixture xlsx generators
├── tests/                       Pytest regression suite
└── data/sessions.db             SQLite session store (gitignored)
```

## Fixtures

Every non-vanilla clause traces to NVCA Model Charter, Singapore VIMA, or a published worked example. See `fixtures/<name>/provenance.md` for citations.

| Fixture | Company | What it demonstrates |
|---------|---------|----------------------|
| `fixture_01_clean` | Solstice Labs (Singapore) | Clean baseline. 3 priced rounds, 1× non-participating, broad-based AD. 7 breakpoints. |
| `fixture_02_typical_messy` | Pelaut Logistics (SGP+IDN) | Structural mess + 5 planted gaps (stale pool, 2 SAFEs, vendor warrant, MFN scope, blank AD). |
| `fixture_03_edge_case` | Bandhan Ventures (India) | Indian CCPS, participating-with-3× cap (8 breakpoints), full-ratchet AD on Seed (not triggered), dual-class voting. |
| `fixture_04_down_round_ratchet` | Surya Foods (India) | Down-round triggers Seed full-ratchet (1.0× → 1.667×). Pay-to-play forfeiture with Seed waiver. Stress test for the live formula workbook. |
| `fixture_05_delaware_double_cap` | Delaware C-corp | Two participating-capped classes at different cap multiples. Tests the senior-above-capped formula path. |

## Run locally

```bash
git clone https://github.com/subhankarshukla04/cap-table-reconciler.git
cd cap-table-reconciler
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
flask --app app run --port 5050
```

Open <http://localhost:5050>.

## Tests

```bash
pytest tests/ -v
```

Coverage spans: parser (50+ tests), checklist (10), waterfall regressions across all fixtures (40+), Flask routes (25+), persistence (8), live formula workbook (24, with formula evaluation via `formulas` package), PDF intake (6), diff (8), integration (10).

## Reliability scaffolding

- **256 unit tests** across the modules listed above.
- **Property-based fuzzer** (`stress_test/fuzzer.py`) — 1,000 normal + 500 pathological cap tables per run. Runs cleanly.
- **40 hand-built edge probes** (`stress_test/edge_20.py`, `edge_20_v2.py`) covering conv_ratio extremes, currency variants, deep stacks, validator boundaries, and dedup tolerance. Found three engine bugs during construction; all fixed.
- **Live workbook formula verification** — every breakpoint, allocation, and cumulative-payout cell in the exported `.xlsx` is verified against the Python `compute_waterfall` truth using the open-source `formulas` package (a real spreadsheet engine). See `tests/test_formula_workbook.py`.

## Known limits

- **Pari-passu seniority is currently a checklist blocker, not a computation.** Same-rank classes need a joint regime walker (NVCA §2.1(b) treatment); engine refuses to compute rather than guess. The fix is the next outstanding engine-level item.
- **SAFE / convertible note auto-conversion is not built.** The parser ingests them as a flat list; the analyst converts to structured share classes during the mapping confirmation step. SAFE conversion math has too many opinions baked in (cap vs discount, pre/post-money) for it to be implicit.
- **Demo-grade application surface.** In-memory + SQLite session, no auth, single Flask process. The engine is the deliverable; the surrounding app is illustrative.

## Demo flow (5 minutes)

1. Open `/`. Show the fixtures.
2. Click *Pelaut Logistics*. Walk the parser warnings card (auto-handled merged title row, two embedded subtotals, a footnote-prose column). Walk the raw-vs-clean panel.
3. Show the findings card — SAFE-UNCONVERTED blockers, AD-MISSING, vendor warrant, stale pool, side-letter scope. Resolve AD-MISSING in-session: pick *broad-based weighted-average*, attach *Charter §4.3(a)*.
4. View waterfall — 7 breakpoints, type-aware chart, y=x reference line.
5. Click *Export Excel (live formulas)*. Open in Excel. Edit a Series B share count from 3M to 4M. Chart updates live. Walk the audit-defensibility caveat (preserves threshold ordering — structural changes require re-export).
6. Switch to *Surya Foods* (fixture 04). Walk the triggered ratchet story. Two breakpoints near each other because adjusted Seed PPS (₹30) equals A2 PPS (₹30) — the structural artefact of full-ratchet protection.
7. *(If time)* drop a PDF onto the side-letter intake; show the diff page across two snapshots.

Anchor every claim to provenance. The tool stops at structured output — fair-value judgment stays with the analyst.

## License

MIT.
