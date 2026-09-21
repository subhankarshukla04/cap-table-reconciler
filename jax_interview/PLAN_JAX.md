# Jax / Qapita Demo — Build Plan (audited)

**Status:** Plan locked. Build starts immediately.
**Build dir:** `~/Desktop/qapita/jax_interview/`
**Supersedes:** the pick in `AUTOMATION_5.md` and `ELIMINATION_JAX.md` (SEA Pipeline Radar). Those files preserved as reasoning trail.

---

## Audit findings on the prior plan + the fixes applied

| Audit issue | Fix |
|---|---|
| Rule accuracy was the single biggest existential risk — citing Indonesian PMK / DGT or Vietnamese rules without English-language source authorities the user can defend | **Trimmed to 2 jurisdictions: Singapore (SG) + India (IN).** Both have English-language statute + regulator guides; the user has native domain familiarity in both. ID/VN move to Phase 2. |
| 4 jurisdictions × 6 events = 96 cells. Unbuildable accurately in 7 days. | **2 jurisdictions × 4 events** (Grant, Vest, Exercise, Sale). 16 cells. Tractable. |
| Schedule misaligned with budget (45% research but Day 1 promised "SG corpus done") | Schedule rewritten — Day 1 = schema only, Day 2–3 = corpus research. |
| "2-day legal-check delay" claim was unsupported | Softened: replaced with the observable claim — "Carta wrote a 4000-word blog post about this; Loeb & Loeb wrote a comparative guide; Qapita itself has the answer in static blog content. Nobody has it as a tool the BD can pull in a meeting." |
| Demo fixtures not named | **Three named demo scenarios committed below.** |
| Architecture didn't match existing project layout | Rebuilt to mirror parent: `app.py` at root of `jax_interview/`, `src/` sibling, `templates/`, `static/`, `tests/`, `fixtures/`. CSS reused from `../static/css/main.css`. |
| Plan mentioned Bark + scheduler | **Dropped.** This is a live workflow tool, not a digest. No notifications, no cron, no scheduler. |
| "Cessation" as event name | Renamed to **"Deemed Exercise"** (IRAS's term). |
| Opening line a touch aggressive | Softened. Final draft below. |
| No fallback if rule research runs over | **Graceful-degrade rule built in:** demo can run on SG-IN exercise + sale only (4 cells) if the full 16 doesn't land in time. |

---

## The pick: SEA-India ESOP Compliance Atlas

**One-line:** A workflow tool the Qapita BD/FO team opens during a sales call to answer — instantly and with statutory citations — the cross-border ESOP question a SEA founder asks about their India team (or a SEA holding co asks about Singapore employees). Specifically: *"What does my employee in [X] owe in tax when they hit a vesting / exercise / sale event, and what do I file?"*

**Today without the tool:** the BD says *"let me confirm with our tax counsel and circle back."* The deal goes cold for 1–2 weeks.

**With the tool:** open it on screen during the call, input *parent jurisdiction + employee jurisdiction + event + residency status + dates*, show the founder a fully-cited compliance verdict in <30 seconds.

**Why SG + IN specifically (and not Indonesia for v1):**
- Both have **English-language statute texts and regulator e-Tax Guides** with section-level citations the user can defend in a room with an ACVA interviewer.
- **SG-IN is Qapita's single highest-volume cross-border ESOP pair.** Almost every SEA-headquartered Series A+ company has an India engineering team. Solve this one pair flawlessly and the moat story writes itself.
- IN is Qapita's home turf (70% of revenue) — credible authority.
- SG is Jax's seat — direct SEA-mandate hit.
- Indonesia + Vietnam + Thailand land in Phase 2 once the rule-acquisition process is proven on the SG-IN pair.

---

## Scope (v1, 7-day demo build)

**Parent × Employee jurisdiction pairs (4 pairs):**
1. SG parent × SG employee (baseline)
2. SG parent × IN employee (the headline cross-border case)
3. IN parent × IN employee (Qapita's home turf, included for credibility)
4. IN parent × SG employee (the reverse cross-border case)

**Events (4):**
1. **Grant** — option awarded
2. **Vest** — vesting cliff hit (no tax in SG/IN, but recorded for audit)
3. **Exercise** — option exercised, FMV vs exercise price spread realized
4. **Sale** — underlying share sold post-exercise

**Plus 1 jurisdiction-specific edge case:**
- **SG "Deemed Exercise"** — non-citizen employee ceases SG employment with unvested or unexercised options. IRAS triggers tax as if all options were exercised on the day before cessation.

**Per cell return:**
- Tax treatment (employment income / capital gain / no tax)
- Rate or rate band
- Withholding obligation (yes / no / conditional)
- Filing requirement (form, deadline)
- Documentation checklist
- Statutory citation (act + section number)
- Confidence flag (**firm** / **conditional** / **requires-counsel**)
- Source URL + retrieval date

**Out of scope (Phase 2):**
- Indonesia, Vietnam, Thailand, Philippines, Malaysia jurisdictions
- RSUs, SARs, phantom stock, ESOW
- Capital-gain treatment for listed-share sales
- Tax-equalization for globally-mobile employees
- US 1099 / NQSO treatment (separate problem)

---

## The three named demo fixtures

These are written upfront so the demo script is locked from Day 1. All three are illustrative and **not** based on a real Qapita client.

**Fixture A — "Praxis Labs"** (the headline pair)
- SG-incorporated parent, 35-person team
- Engineer based in Bengaluru, India, employed by Praxis India Pvt Ltd subsidiary
- Granted 10,000 options at $0.10, FMV $0.50 at exercise, exercises 4,000 vested options
- Demo answer: India perquisite tax on (FMV − exercise) × 4,000 at marginal rate; TDS by employer under ITA §192 / 2025 §392(1); filed via Form 12BA + Form 16. **Singapore: no tax (employee never worked in SG).**

**Fixture B — "Pelaut Maritime"** (the reverse cross-border)
- IN-incorporated parent, Mumbai HQ
- Operations Head based in Singapore, SG tax resident
- Granted 50,000 options, FMV step-up of $2.00 at exercise, exercises 20,000
- Demo answer: SG taxes the gain because the grant was made during SG employment (IRAS guidance — overseas-parent grants are taxed equally); rate per progressive PIT bands; no SG withholding (employee files via Form B); **India: no Indian tax for the SG-resident employee.**

**Fixture C — "Solstice Holdings"** (the deemed-exercise edge case)
- SG-incorporated parent, Indian-national employee
- Employee resigns and leaves SG after 18 months, with 8,000 vested-but-unexercised options
- Demo answer: **SG "deemed exercise" rule triggers** — IRAS imputes exercise on the day before cessation; tax on (FMV at imputed exercise − exercise price) × 8,000; tax clearance via Form IR21 by the SG employer before the employee's last day. This is the single specific edge case the demo opens with — it's the screen that makes Jax sit up.

---

## Architecture (matches parent project conventions)

```
~/Desktop/qapita/jax_interview/
  app.py                       # Flask routes
  pyproject.toml               # Python 3.11, Flask 3, pydantic 2, openpyxl
  README.md
  PLAN_JAX.md                  # this file
  JAX_RESEARCH.md              # (already written)
  AUTOMATION_5.md              # (already written, reasoning trail)
  ELIMINATION_JAX.md           # (already written, reasoning trail)
  INTERVIEW_PREP.md            # (already written)
  src/
    __init__.py
    models.py                  # pydantic: Event, Verdict, Citation, RuleRef
    engine.py                  # core query: (parent, employee, event, status) -> Verdict
    corpus.py                  # loads JSON rule files, validates, indexes
    export.py                  # Excel + PDF export
    rules/
      sg.json                  # Singapore rules + citations
      in.json                  # India rules + citations
  templates/
    base.html
    index.html                 # input form
    verdict.html               # HTMX swap target — the answer page
    sources.html               # "where these rules come from"
  static/
    css/
      atlas.css                # tiny override on top of parent's main.css
  tests/
    __init__.py
    test_engine.py
    test_rules_sg.py
    test_rules_in.py
    test_app_routes.py
    fixtures/
      praxis.json
      pelaut.json
      solstice.json
```

**Tech:**
- Flask 3, pydantic 2 (matches `../pyproject.toml`)
- HTMX (no SPA, no JS framework)
- JSON rule corpus loaded at app startup, validated against pydantic schema
- No DB, no persistence, no session store — this tool is stateless
- CSS: `<link>` to `../static/css/main.css` reused; `atlas.css` only for tool-specific additions

**Discipline (non-negotiable):**
- No LLM in the engine. Rules are pure pydantic + dict lookup.
- Every rule has a `citation` field. Anything uncited is `confidence: requires-counsel`.
- Confidence flag visible in the verdict UI. We never bluff.
- Same inputs → same outputs forever. Rule changes are git-tracked.

---

## 7-day schedule (revised, aligned with budget)

| Day | Build | Done-when |
|---|---|---|
| **1** | Project skeleton: pyproject, `app.py` stub, `src/models.py` (pydantic Event/Verdict/Citation), `src/engine.py` skeleton, base test scaffold, `templates/base.html` reusing parent CSS. | `pytest` green on empty engine. Browser loads `/` and shows a heading. |
| **2** | **SG rule corpus.** Read IRAS e-Tax Guide on ESOP/ESOW + IRAS web pages. Author `src/rules/sg.json` with grant/vest/exercise/sale + deemed-exercise rules. Confidence + citations on every rule. | `pytest tests/test_rules_sg.py` validates the corpus loads + every rule has a non-empty citation. |
| **3** | **IN rule corpus.** Author `src/rules/in.json` from ITA §17(2)(vi) / Rule 3(8) + ITA 2025 §17(5)(h) / §392(1) + Form 12BA / Form 16 requirements. | `pytest tests/test_rules_in.py` green. |
| **4** | **Engine cross-product logic.** Implement the 4 pair × 4 event matrix in `src/engine.py`. Handle the deemed-exercise SG edge case. Three fixture files (Praxis, Pelaut, Solstice) committed. | All three fixtures resolve to fully-cited verdicts. `pytest tests/test_engine.py` green. |
| **5** | **UI.** `index.html` input form, `verdict.html` HTMX swap target, `sources.html`. Audit-firm aesthetic carried from `main.css`. | Browser end-to-end: input form → verdict page renders for all three fixtures. |
| **6** | **Exports + sources page + polish.** Excel export of a verdict (openpyxl, like parent project). PDF export (weasyprint or print-to-PDF). Sources page lists every rule with URL + retrieval date. | One-click export of any verdict to .xlsx + .pdf. Sources page enumerates all rules. |
| **7** | **Demo rehearsal + screenshot deck + README.** Cold-start sequence documented. 3 demo scenarios scripted minute-by-minute. Backup screenshot PDF saved. | Cold-start `python app.py` → 3-scenario demo completes in <4 min. PDF backup attached. |

**Graceful degrade:** if Day 3 IN corpus slips, ship SG-only with the deemed-exercise edge case as the headline. That alone is a complete demo.

**Cut-day:** if Day 6 slips, drop the PDF export — keep Excel. PDF is a stretch.

---

## Opening line for the demo (final draft)

> "On every SEA sales call your team takes, a founder asks one specific question: *'when my engineer in Bangalore exercises her option on my Singapore parent, what does she owe and what do I file?'* Today the answer takes a 1–2 week tax-counsel ping. Carta wrote a 4000-word blog post about this. Loeb & Loeb wrote a comparative guide. Your own Singapore blog has the answer in static content. **Nobody has a tool the BD can open during the call.** This is that tool — four jurisdiction pairs, four events plus the deemed-exercise edge case, every output statutorily cited, audit-grade deterministic. The product is the regulatory layer Qapita's cap table sits on top of. It's the SEA-India moat Carta can't replicate without five years of local work."

What this line does: (1) names a concrete Jax-side pain — sales-call delay; (2) cites the gap in the competitive set with proof; (3) restates the discipline — no judgment, only citations; (4) positions the build as **product moat infrastructure**, not a feature; (5) lands the SEA-India pair as the highest-leverage opening case.

---

## Post-hire scaling map (carried from earlier version, sharpened)

| Phase | Window | What changes | What stays |
|---|---|---|---|
| 1 — Pre-interview demo | Days 1–7 | SG + IN, 4 events + deemed-exercise. 3 fixtures. Local Flask. | Engine + rule schema + citation discipline. |
| 2 — Early internship | Months 1–3 | Add Indonesia + Vietnam jurisdictions (priority: ID because of Jakarta office). Add RSU + SAR event treatments. Wire compliance verdicts into Qapita's existing cap-table product as a tab on every event. | Same engine, same schema, more corpus. |
| 3 — Productization | Months 4–8 | Batch mode (upload SEA cap table → per-employee verdict matrix). Tax-year cutoff handling for mid-year rule changes. PDF deliverable for the founder. Integration with tender-offer settlement. | Engine becomes the live compliance layer across products. |
| 4 — Moat infrastructure | Months 9+ | External API: SEA law firms, fund admins, Big 4 consume Qapita's compliance verdicts as a licensed SKU. M&A integration: every acquired SEA corp-sec firm's rule knowledge gets codified into the engine — acquisitions become permanent platform value rather than headcount. | The engine is the moat. Everything else is consumer of it. |

---

## Build budget (7 days, revised)

- **40%** Rule corpus research + JSON authoring + citations (Days 2–3 dominate)
- **25%** Engine + pydantic models + unit tests (Day 1 + part of Day 4)
- **20%** UI (Flask + HTMX templates + styling) (Day 5)
- **10%** Exports + sources page (Day 6)
- **5%** Polish + rehearsal + screenshot deck (Day 7)

The rule corpus is the durable asset. Over-engineering the engine is wasted time; under-citing the corpus kills the demo. Allocation reflects that asymmetry.

---

## Now executing

Build starts immediately. Day 1 deliverable: pyproject + app.py stub + pydantic models + engine skeleton + base template + first passing test.
