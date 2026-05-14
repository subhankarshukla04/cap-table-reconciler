# Cap Table Reconciler

A small, local tool for the part of cap-table work that doesn't belong to the model — cleaning the file before any math runs.

The premise is simple. Most of an analyst's day on a private-company valuation isn't spent on judgment. It's spent reconciling what the client sent: a stale option pool, a SAFE that should have converted at the last round, an MFN side letter with terms nobody transcribed, an anti-dilution column that says "see charter." This tool is the **input layer** to that work — it ingests the messy file, points at every gap, and produces structured output the analyst can hand to an OPM, Backsolve, or DCF.

> **It makes zero valuation judgments.** No 409A. No Backsolve. No fair-value computation. No LLM in the calculation pipeline. Every finding is rule-based and shows its citation.

The phrasing the tool uses internally is: **expert-led, not algorithm-only.** When the file is too messy to defensibly compute on, the tool refuses and writes the punch list. That refusal — and the punch list — is the deliverable.

---

## What you see when you use it

**1. Upload page.** Drop a `.xlsx`. Or pick one of five built-in fixtures, each modelled on a real worked example with citations to the NVCA Model Charter, Singapore VIMA, or published precedent.

**2. Review page.**
- *Parse warnings* — which sheet was detected, which columns mapped, what got skipped (subtotal rows, blank section headers, etc.).
- *Raw upload → cleaned output* — side-by-side panel showing what the parser saw vs. the structured form it produced. Date strings normalized to ISO-8601, instrument-type aliases coerced to the canonical enum, currency symbols stripped from numeric fields.
- *Findings & resolutions* — every gap the checklist found, sorted by severity. Each one has an inline form: pick a variant, paste counsel's answer, attach a citation, recompute. Blockers (e.g. unconverted SAFEs, missing AD variant, side-letter scope unresolved) prevent the waterfall from running until adjudicated.
- *Side-letter intake* — drop a PDF; it's extracted, any open questions are surfaced, and the analyst records counsel's answers in-session.

**3. Waterfall page.**
- *Cumulative payout chart* — Y-axis is per-class payout, X-axis is exit value, slope changes mark breakpoints. The same data an OPM Backsolve would consume.
- *What-if scenario panel* — sliders for share counts and LP multiples. Edit any input, the chart and breakpoint table redraw within 400ms. In-memory only; the saved cap table doesn't change.
- *Breakpoints, allocation matrix, methodology & provenance* — every breakpoint has an explanation linked to the relevant clause; the allocation matrix shows the fraction of a marginal dollar going to each class within each tranche.

**4. Export.** JSON, static `.xlsx`, or a **live formula workbook** — an 8-sheet `.xlsx` with named ranges and SUMPRODUCT formulas. The analyst can take the workbook home, edit a share count or LP multiple in Excel, and the breakpoints, allocation matrix, and chart update natively. No Python needed after export.

---

## The five fixtures

Every non-vanilla clause traces to a public source. See `fixtures/<name>/provenance.md`.

| Fixture | Company | What it demonstrates |
|---|---|---|
| 01 — clean | Solstice Labs (Singapore) | Three priced rounds, 1× non-participating, broad-based AD. The happy path — seven breakpoints. |
| 02 — typical messy | Pelaut Logistics (SGP + IDN) | Structural mess (merged title row, embedded subtotal, prose in a numeric column) plus five planted gaps (stale pool, two unrecorded SAFE conversions, vendor warrant, MFN scope undefined, blank AD variant). |
| 03 — SEA edge case | Bandhan Ventures (India) | Indian CCPS, participating-with-3×-cap (eight breakpoints), full-ratchet AD on Seed (not triggered), dual-class voting common. |
| 04 — down-round ratchet | Surya Foods (India) | Down-round triggers a Seed full-ratchet (1.0× → 1.667×). Pay-to-play forfeiture with selective waiver. Stress test for the live formula workbook. |
| 05 — Delaware double-cap | Delaware C-corp | Two participating-capped classes at different cap multiples. Tests the senior-above-capped path. |

A sixth example (`sample_uploads/sundar_foods/`) is included as an honest stress test — a fictional Indian D2C Series B-1 file with the kind of CFO-built mess Qapita customers actually send. The engine intentionally degrades on it, and that degradation is the point: the tool produces a 72-warning parse report instead of a fabricated waterfall.

---

## What it explicitly does **not** do

- No OPM Backsolve solver — that judgment belongs to the analyst.
- No fair value, no DLOM, no peer-set construction.
- No auth, no multi-tenancy. Local-only at `http://localhost:5050`.
- No LLM clause extraction — side letters are stored verbatim, scope questions surfaced explicitly, the analyst records the adjudicated answer.

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

Open <http://localhost:5050>. Click any fixture from the sidebar to walk the full flow.

---

## Five-minute demo path

1. **Open `/`.** Look at the sidebar's five fixtures.
2. **Click Pelaut Logistics.** Walk the parser warnings (auto-handled title row + embedded subtotal + footnote-prose column). Walk the raw-vs-clean panel.
3. **Open the findings panel.** SAFE-UNCONVERTED blockers, AD-MISSING, vendor warrant unrecorded, stale pool, MFN scope unresolved. Resolve AD-MISSING in-session: pick *broad-based weighted-average*, attach *Charter §4.3(a)*.
4. **Open the waterfall.** Seven breakpoints, type-aware chart, y=x reference line.
5. **Edit a Series B share count** in the what-if panel. Watch the chart redraw.
6. **Click Export Excel (live formulas).** Open in Excel. Edit a share count from 3M to 4M. Chart updates natively.
7. **Switch to Surya Foods** (fixture 04). The triggered Seed ratchet creates two breakpoints near each other because adjusted Seed PPS (₹30) equals A2 PPS (₹30) — the structural artefact of full-ratchet protection.
8. *(If time)* Drop a side-letter PDF onto the intake. Show the diff page across two snapshots.

---

## Known limits

- **Pari-passu seniority is a checklist blocker, not a computation.** Same-rank classes need a joint-regime walker; the engine refuses to guess.
- **SAFE / convertible note auto-conversion is not built.** Too many opinions (cap vs discount, pre vs post-money, MFN logic) to be implicit — the analyst converts these to structured share classes during the mapping step.
- **Demo-grade surface.** In-memory + SQLite session, single Flask process, no auth. The **engine** is the deliverable; the surrounding app is illustrative.
- **Holder-level cap tables aren't auto-rolled-up.** A common Indian-CFO Excel pattern — one row per shareholder rather than per share class — degrades to a parse-warning report rather than a clean ingest. Roadmap item.

---

## Under the hood (brief)

- `src/parser.py` — Excel → structured CapTable; handles title rows, mixed date formats, alternative tab names, instrument-type aliases (`ccps`, `rcps`, `ordinary`, `founders common`).
- `src/checklist.py` — eight deterministic gap-detection rules. No probabilistic anything.
- `src/waterfall.py` — breakpoints (LP-cleared, conversion thresholds, participation-cap thresholds, pure-conversion thresholds), per-tranche marginal allocation matrix. Non-participating, participating-uncapped, participating-with-cap, including the senior-above-capped case.
- `src/formula_workbook.py` — live-formula `.xlsx` exporter; every breakpoint, allocation, and chart cell is verified against the Python truth using the open-source `formulas` package.
- `src/pdf_intake.py` — `pdfplumber`-based side-letter ingestion; heuristic title detection + open-question extraction.
- `src/diff.py` — fuzzy-matched class-name diff across two snapshots, for the audit memo's *subsequent events* section.

256 unit tests; a 1,500-sample property fuzzer; 40 hand-built edge probes. Every fixture is regression-tested.

---

## License

MIT.
