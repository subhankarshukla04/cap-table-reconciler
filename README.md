# Cap Table Reconciler

A small, local tool for the part of cap-table work that sits **before** the model.

Most of an analyst's hours on a private-company valuation aren't spent on judgment — they're spent reconciling what the client sent. A stale option pool. A SAFE that should have converted at the last round. A side letter with terms nobody transcribed. An anti-dilution column that says *"see charter."* This tool ingests that file, points at every gap, and produces structured output an analyst can hand to an OPM, Backsolve, or DCF.

> **Zero valuation judgments.** No 409A. No Backsolve. No fair-value computation. No LLM in the calculation pipeline. Every finding is rule-based and cites the field it came from.

**The posture is expert-led, not algorithm-only.** When the file is too messy to defensibly compute on, the tool refuses and writes the punch list. That refusal — and the punch list — is the deliverable.

[Walkthrough video and live demo →](https://cap-table-reconciler-site.vercel.app)

---

## In 30 seconds

- **Input:** one `.xlsx` cap table. Optionally text-PDF side letters.
- **Process:** parse → checklist of 8 deterministic gap rules → in-session adjudication → structured waterfall.
- **Output:** JSON, static `.xlsx`, **live-formula `.xlsx`** (edit a share count in Excel, breakpoints and chart redraw natively), audit-memo skeleton, snapshot-diff against an earlier version.
- **Honest limit:** holder-level cap tables (one row per shareholder, common in CFO-built Indian Excel) degrade to a warning report rather than a clean ingest. Documented, not hidden — see [the stress test](#evidence-of-the-honest-limit) below.

---

## What it does

1. **Parse a messy workbook.** Locates the cap-table tab by name pattern, scans the first dozen rows to find headers despite title rows or blanks, skips embedded subtotal rows, normalizes most common date formats to ISO, coerces instrument-type aliases (`CCPS`, `RCPS`, `Ordinary`, etc.) to the canonical enum. Reports everything inferred and everything dropped.
2. **Run the checklist.** Eight hand-authored rules: anti-dilution variant blank, full-ratchet without trigger documentation, unconverted SAFE past trigger, stale option pool, off-table warrant, side-letter scope unresolved, participating-with-cap missing the cap multiple, dual-class voting differential not recorded. Each finding cites the exact field path.
3. **Adjudicate in-session.** Findings with a deterministic resolution (SAFE conversion share count, AD variant picker, warrant inclusion toggle, side-letter scope, pool date refresh) have inline forms. Submit, the cap table updates in memory, the waterfall re-runs.
4. **Compute the waterfall.** Breakpoints (LP-cleared, conversion thresholds, participation-cap thresholds, pure-conversion thresholds), per-tranche marginal allocation matrix. Handles non-participating, participating-uncapped, participating-with-cap including the senior-above-capped case.
5. **Export the bundle.** Structured JSON, a static `.xlsx` with cap-table / convertibles / side-letters / breakpoints / findings tabs, a live-formula `.xlsx` with IF + SUMPRODUCT logic against named input ranges, and a markdown audit-memo skeleton with explicit `[ANALYST]` placeholders for the judgment sections.

---

## What it explicitly does **not** do

- No OPM allocation, no DLOM, no fair-value opinion, no 409A.
- No LLM clause extraction. Side letters stored verbatim; open Q-lines surfaced for adjudication.
- No auto-conversion of SAFEs or convertible notes — too many opinions baked in (cap vs discount, pre vs post-money, MFN). The analyst converts these to share classes during the mapping step.
- No auth, no multi-tenancy. Local-only at `http://localhost:5050`.

---

## Evidence of the honest limit

A sixth fixture (`sample_uploads/sundar_foods/`) is a stress test, not a curated demo. It's a fictional Indian D2C Series B-1 cap table built the way real Qapita customers send them — holder-level rows, mismatched tab names, prose in numeric columns, dates like `14th Feb '25`, and off-charter terms living only in side-letter PDFs.

The engine **intentionally degrades** on it. Only the ESOP rows survive validation; everything else gets dropped at Pydantic's preferred-must-have-LP check. The result is a 72-warning parse report rather than a fabricated waterfall.

**That report is the deliverable** — the audit-defensible record of what an analyst would need to email back to the CFO before any cleanup work can begin. The roadmap fix (holder-level rollup, broader tab-name whitelist, fuller class-type alias map) is real and known.

---

## The five curated fixtures

Every non-vanilla clause traces to a public source. See `fixtures/<name>/provenance.md`.

| Fixture | Company | What it demonstrates |
|---|---|---|
| 01 — clean baseline | Solstice Labs (Singapore) | Three priced rounds, 1× non-participating, broad-based AD. Seven breakpoints. |
| 02 — typical messy | Pelaut Logistics (SGP + IDN) | Structural mess plus five planted gaps. The Act-1 demo file. |
| 03 — SEA edge case | Bandhan Ventures (India) | Indian CCPS, participating-with-3×-cap (eight breakpoints), full-ratchet AD on Seed, dual-class voting common. |
| 04 — down-round ratchet | Surya Foods (India) | Down-round triggers Seed full-ratchet (1.0× → 1.667×). Pay-to-play forfeiture with selective waiver. |
| 05 — Delaware double-cap | Delaware C-corp | Two participating-capped classes at different cap multiples. Tests the senior-above-capped path. |

---

## Run it

```bash
git clone https://github.com/subhankarshukla04/cap-table-reconciler.git
cd cap-table-reconciler
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python app.py
```

Open <http://localhost:5050>. Click any fixture from the left sidebar to walk the full flow without uploading anything.

---

## Five-minute demo path

1. Open `/`. Note the sidebar fixtures and the *zero valuation judgments* banner.
2. Click **Pelaut Logistics**. Walk the Parse Warnings card and the raw-vs-cleaned panel.
3. Scroll to **Findings & resolutions**. Pick one (e.g. AD-MISSING). Open it inline, choose *broad-based weighted-average*, cite *Charter §4.3(a)*, resolve.
4. Open the **Waterfall** tab. Edit a Series B share count in the **What-if** panel. The chart redraws in ~400 ms.
5. Scroll to **Export**. Download the live-formula `.xlsx`. Open in Excel — click any breakpoint cell, the formula bar shows the actual IF/SUMPRODUCT logic referencing named input ranges.

---

## Engine notes

- `src/parser.py` — Excel → structured `CapTable`. Header-row inference, instrument-type alias map, alternative tab names, date-format coercion.
- `src/checklist.py` — eight deterministic gap-detection rules. Nothing probabilistic. Every finding has `fields_referenced` pointing at the source cell.
- `src/waterfall.py` — breakpoint computation across non-participating, participating-uncapped, participating-with-cap (including senior-above-capped).
- `src/formula_workbook.py` — live-formula `.xlsx` exporter; the workbook's chart and breakpoint formulas remain valid for input edits and are verified against the Python truth.
- `src/pdf_intake.py` — text-PDF side-letter ingestion via pdfplumber. Image-only PDFs return a warning, not a hallucination.
- `src/diff.py` — fuzzy-matched class-name diff across two snapshots, for the audit memo's *subsequent events* section.

331 tests collected, every fixture regression-tested. Run with `pytest tests/`.

---

## License

MIT.
