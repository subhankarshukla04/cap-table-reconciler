# Jax / Qapita NOC Interview #3 — Folder Index

**Interviewer:** Jax LIU Jiawei, ACVA — Founders' Office and Head of Operations, SEA / Head of Southeast Asia, Qapita
**Email:** jax@qapita.com
**Type:** NOC inbound, Aug 2026 start (6–12 month founders'-office internship)
**Compiled:** 2026-05-11

This folder is **only for the Jax interview.** It does not touch any files in the parent `~/Desktop/qapita/` directory — those belong to the prior Evelyn (Valuations) and Olesia (Secondaries) tracks.

## Files in this folder

| File | What's in it |
|---|---|
| [JAX_RESEARCH.md](./JAX_RESEARCH.md) | The person, his team, the SEA-and-FO vantage on Qapita, what he likely asks, and what to memorize before walking in. |
| [AUTOMATION_5.md](./AUTOMATION_5.md) | Five ranked automation recommendations (Pipeline Radar, M&A Scanner, Investor-Update Skeleton, Competitor Pulse, Customer-Health Radar) with build effort + scaling ceiling for each, and a clear pick for the demo. |
| [INTERVIEW_PREP.md](./INTERVIEW_PREP.md) | Opening positioning, talking points, five questions to ask him, pre-call checklist, day-of cadence, post-call email template, failure-mode recovery. |
| [ELIMINATION_JAX.md](./ELIMINATION_JAX.md) | Five rounds of audit against scaling / problem severity / demo quality / value-to-Jax. Eliminates 4, lands on SEA Pipeline Radar (single build, M&A Scanner deferred as Phase-2 verbal extension). Includes the post-hire Phase 1–4 scaling map. |
| [PLAN_JAX.md](./PLAN_JAX.md) | **Final build plan.** Pivoted from SEA Pipeline Radar to **SEA-India ESOP Cross-Border Compliance Atlas**. Audit + scope trim. 7-day schedule, architecture, risks, scaling map. |
| [RUNBOOK.md](./RUNBOOK.md) | **Cold-start + 5-minute demo script + failure recovery.** Read this 24 hours before the interview. |

## The build (shipped)

**Run it:**

```bash
cd ~/Desktop/qapita/jax_interview
source ../.venv/bin/activate
python app.py
# open http://127.0.0.1:5151/
```

**Test it:**

```bash
python -m pytest tests/ -v
# expect: 192 passed
```

**Demo URLs:**
- `/` — query form (any 7-jurisdiction combination)
- `/batch` — upload a CSV of N employees, download one Excel with N verdicts
- `/sources` — full corpus, 87 rules, every one cited to primary source
- `/verdict/praxis` — SG↔IN exercise (headline)
- `/verdict/pelaut` — IN↔SG exercise (reverse, IRAS overseas-parent rule)
- `/verdict/solstice` — SG deemed-exercise on cessation
- `/verdict/atlas_corp` — US↔IN (Schwab-pipeline case)
- `/verdict/avalon_uk` — UK↔IN (EMI cross-border)
- `/verdict/horizon_hk` — HK↔IN (IRO s.9 / DIPN 38)
- `/verdict/zenith_ae` — AE↔IN (Dubai-flip founders, India incidence)
- `/export/xlsx/<scenario>` — audit-grade Excel
- `/pdf/<scenario>` — audit-firm PDF advisory memo (reportlab letterhead + numbered citation footer)
- `/batch/sample` — CSV template
- `/healthz` — rich status (corpus size + jurisdictions + fixtures)

**Stack:** Flask 3, pydantic 2, HTMX, openpyxl, reportlab. No DB, no auth, no LLM in the engine. **192 tests, all green.**

**Architecture:**
- `app.py` — Flask routes (single + batch + Excel + PDF + sources + healthz + error pages)
- `src/models.py` — pydantic Rule / Query / Verdict schemas with citation enforcement
- `src/corpus.py` — JSON loader + (parent, employee, event, status) index
- `src/engine.py` — cross-product resolution, employee-perspective-as-primary ordering, requires-counsel fallback
- `src/export.py` — openpyxl Excel exporter (Verdict + Citations sheets)
- `src/batch.py` — CSV parser + bulk runner + 3-sheet batch Excel (Summary + Citations + Inputs)
- `src/pdf.py` — reportlab advisory memo with audit-firm letterhead
- `src/rules/*.json` — 7 jurisdiction files, 87 rules total, every rule primary-source cited
- `tests/` — 192 tests across engine, rule corpora, fixtures, exports, batch, PDF, routes

**Scope (v0.2):**
- Jurisdictions: SG, IN, ID, US, UK, HK, AE (7)
- Events: Grant, Vest, Exercise, Sale, Deemed Exercise (5)
- Instrument: stock options (RSUs / SARs deferred to Phase 2)
- Outputs: web verdict, Excel workbook, batch Excel, PDF advisory memo
- Discipline: every rule has primary statutory citation; uncited combinations return `requires-counsel`; no LLM in the calculation pipeline.

## TL;DR (read this if nothing else)

1. **The pick:** Build **SEA Pipeline Radar** — a Monday digest of every newly-funded SEA startup, scored on Qapita-fit. Same shape as Wego Earnings Digest / Qatalyst Sentinel / Tender Radar — a precedent already validated across three prior interviews. 5–7 days to demo-ready.
2. **The frame:** SEA is Jax's mandate. Lead with what you'd ship in 6 months, not your career arc. He ran NOC NY 2018 himself — same arc you're on.
3. **The discipline:** zero strategic / valuation / pricing automation. He's ACVA; he protects the craft. Automate scaffolding only.
4. **The post-call:** repo + screenshot deck within 4 hours of the call. Sent.

## What to do next (in order)

1. **Read all three files in order**: `JAX_RESEARCH.md` → `AUTOMATION_5.md` → `INTERVIEW_PREP.md` (15–20 min total).
2. **Run a single-pass elimination round** like `../ELIMINATION.md` did for Olesia — confirm Idea 1 survives the criteria against Jax's specific weights, or pivot to Idea 2/3/5.
3. **Scope `PLAN_JAX.md`** in this folder once the elimination is settled: 5 scrapers, rubric YAML, digest schedule, fixture set, Bark wiring. Reuse the finance-digest project's scheduling + push, and any Tender Radar modules that exist by then.
4. **Build for 5–7 days.** Two days before the call, freeze. The night before: cold-start the demo, confirm the screenshot deck, rehearse the 30-second opener.
5. **Day of call:** follow the §6 cadence in `INTERVIEW_PREP.md`. Lead with the demo. Ask the top two questions. Send the email within 4 hours.

## Do not touch

- `../app.py`, `../CONTEXT.md`, `../PLAN.md`, `../TEACH.html`, `../INTERVIEW.html` — Evelyn track.
- `../OLESIA_RESEARCH.md`, `../ELIMINATION.md` — Olesia track (read-only reference).
- Anything in `../src/`, `../tests/`, `../fixtures/`, `../precedent/`, `../data/`, `../stress_test/`, `../templates/`, `../static/`, `../scripts/`.

New files for the Jax build (once started) all land inside this `jax_interview/` subfolder. If shared modules (scoring, digest renderer, Bark integration) need to be promoted out to the parent app to avoid duplication, do that as a separate commit *after* the demo lands — not before.
