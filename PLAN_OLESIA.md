# Tender Radar — Plan, Audits, and Go/No-Go

This document chains the four things the user asked for, in order:
1. **Audit of `SPEC_OLESIA.md`** — what's missing or wrong before we plan
2. **The execution plan** — day-by-day, file-by-file, with acceptance gates
3. **Audit of the plan** — risks, ordering issues, slippage scenarios
4. **Why hasn't this been built already** — market scan + go/no-go call

The plan in `SPEC_OLESIA.md` Section 10 was high-level. This is the operational plan.

---

## 1. Spec audit — 10 problems with `SPEC_OLESIA.md`

| # | Finding | Severity | Fix |
|---|---|---|---|
| S1 | Spec claims "mechanics engine reused from Evelyn build" but Evelyn is a **cap-table reconciler** (data hygiene), not a tender mechanics engine. The reuse claim is wrong. | **High** | Treat mechanics as a fresh build in `radar/mechanics.py`. Only reuse Evelyn's `pydantic` model conventions and `openpyxl` helpers, not its calc code. Update SPEC §4.4 mentally; don't edit the frozen spec. |
| S2 | The "RBI fair-value floor" check in compliance requires a per-issuer fair-value number. We don't have a DCF/409A for arbitrary issuers. | **High** | Use **last-round price-per-share as a fair-value proxy**, with an explicit on-screen disclaimer: *"Fair-value proxy: last round price. Real RBI floor requires ICAI-method valuation."* This keeps the engine honest. |
| S3 | Spec doesn't define the **cap-table holder fixture shape**. Without ~500 synthetic holders per issuer, the mechanics engine has nothing to compute. | **High** | Add Phase 0 task: hand-curate a holder generator that produces realistic distributions (founder concentration + 5–10% ESOP pool + ~400 employees + 20 angels) parameterized per issuer. |
| S4 | Issuer-name matching across scrapers is unspecified. "Razorpay" on the roster vs "Razorpay Software Private Limited" in SEBI EDIFAR will not match a string equality. | **Medium** | Add a `radar/matching.py` module with hand-curated alias map + fuzzy match (rapidfuzz). 15 issuers × ~4 known aliases each = 60-entry map, manageable. |
| S5 | The `/history` route assumes 3+ prior digests exist. Day-1 user has zero. | **Medium** | Add Phase 6 sub-task: generate 3 backdated digests with realistic synthetic signals so the history view is populated on demo day. |
| S6 | "<50ms HTMX recompute target" is asserted but unverified. | **Low–medium** | Add Phase 4 acceptance gate: a pytest benchmark that fails the build if `preview_tender()` exceeds 50ms on the 500-holder fixture. |
| S7 | Demo script over-indexes on the walkthrough. Real call = ~5 min demo + ~22 min Q&A. | **Medium** | Add to plan: a Q&A prep deliverable in Phase 7 — top 10 likely questions with prepared 1–2 sentence answers. |
| S8 | Port collision: Evelyn app on 5000, Radar on 5001. SPEC mentions this but no `make` target enforces it. | **Low** | Add `make radar-up` target that hardcodes `FLASK_RUN_PORT=5001`. |
| S9 | Bark config sharing with finance-digest is asserted but not specified. | **Low** | Phase 0: read `~/Desktop/finance-digest/.env` → confirm `BARK_DEVICE_KEY` is the variable name → copy that exact name into `~/Desktop/qapita/.env`. |
| S10 | Definition of done has 10 items but no rollback plan if a Phase fails. | **Medium** | Add to plan: each Phase has a **rollback target** — what to skip if it slips. E.g., if mechanics slips, ship a static screenshot table for the slider section. |

**Spec verdict:** Solid skeleton; **S1, S2, S3 are blockers** that the execution plan must resolve before Day 4. The rest are tightening, not rebuilding.

---

## 2. The execution plan

### 2.1 Flow diagram

```
Day 0 ──────► Day 1 ──────► Day 2 ──────► Day 3 ──────► Day 4 ──────► Day 5 ──────► Day 6 ──────► Day 7
PRE-FLIGHT   FOUNDATIONS   SCRAPERS      SCORING       MECHANICS     COMPLIANCE    DIGEST+BARK   POLISH+DRY-RUN
fixtures     scaffold      5 sources     10 rules      slider UI     5 states      cron+history  Q&A prep
holders gen  models+db     cached JSON   tested        <50ms tested  RBI proxy     3 backdates   2 dry runs
                                                                                   bark live
       ▲                          ▲                          ▲                          ▲
       │                          │                          │                          │
   GATE 0                     GATE 1                     GATE 2                     GATE 3
   fixtures real?             scrapers ship?             mechanics                  end-to-end
                                                         + compliance               5-min demo
                                                         render correctly?          glitch-free?
```

### 2.2 Phase 0 — Pre-flight (Day 0, ~3 hours)

**Why this exists:** The spec audit flagged 3 blockers (S1, S2, S3). Phase 0 unblocks them before Day 1 starts.

**Deliverables:**
- [ ] `data/fixtures/issuers.json` — 15 hand-curated issuer records (legal name, state, last round, sector). Sources: TechCrunch, Inc42 archives, public LinkedIn employee counts.
- [ ] `data/fixtures/holders/` — Python generator `scripts/gen_holders.py` that produces a realistic cap-table per issuer:
  - 2–3 founders (each 5–20% holding)
  - 5–10% ESOP pool spread across 300–500 employees with realistic vesting curves (4-year vest, 1-year cliff, hire dates back-dated 6mo to 4yr)
  - 5–8 institutional Pref holders (Series A through latest)
  - 10–20 angels
- [ ] `radar/matching.py` — 60-entry alias map for the 15 issuers (e.g., `"razorpay"` → `["razorpay", "razorpay software", "razorpay software private limited"]`)
- [ ] Confirm `BARK_DEVICE_KEY` in `~/Desktop/qapita/.env` matches finance-digest
- [ ] Confirm `~/Desktop/qapita/.venv/` works with new deps (`httpx`, `selectolax`, `feedparser`, `apscheduler`)

**Gate 0 pass criterion:** `python scripts/gen_holders.py razorpay` writes a 500-holder JSON file; `python -c "import httpx, selectolax, feedparser, apscheduler"` succeeds.

### 2.3 Phase 1 — Foundations (Day 1, ~6 hours)

**Hour-by-hour:**

| Hour | Task | Output |
|---|---|---|
| 1 | Create `radar/` subtree per `SPEC_OLESIA.md` §7 layout | empty modules with docstrings |
| 2 | `radar/models.py` — all pydantic v2 classes | `Issuer`, `Signal`, `TenderReadinessScore`, `ScoreComponent`, `DigestRun`, `Holder`, `ShareClass` |
| 3 | `radar/db.py` — SQLite schema + connection helpers; raw SQL migrations (no Alembic) | `radar.db` schema with 4 tables |
| 4 | Fixture loader: `scripts/seed.py` reads `issuers.json` + holder files into `radar.db` | `make seed` populates DB |
| 5 | `radar/app.py` minimal Flask + 3 stub routes returning placeholder Jinja | `localhost:5001` shows base layout |
| 6 | Basic test: `pytest tests/test_models.py` — pydantic validation of fixture records | green test |

**Commit:** `feat(radar): scaffold + 15-issuer fixture roster`

**Gate 1 pass:** `make seed && make radar-up` → browser shows `/` with empty digest, `/issuer/razorpay` with placeholder, `/history` empty. One green test.

### 2.4 Phase 2 — Scrapers (Day 2, ~7 hours)

| Hour | Scraper | Strategy |
|---|---|---|
| 1 | `radar/scrapers/base.py` | `BaseScraper` with rate-limit (sleep), cache (`data/scraper_cache/<source>/<date>.json`), retry (3x with backoff), `MAX_RUNTIME_S=120` |
| 2 | `inc42_rss.py` + `sebi_rbi_press.py` + `googlenews_employee.py` | All 3 are `feedparser`-based; share parsing logic |
| 3 | `unlistedkart_html.py` | `httpx` + `selectolax`; respectful 10s delay; 15 issuer slugs |
| 4 | `sebi_edifar_drhp.py` | `httpx` + `selectolax`; hardest one; HTML table parse; fuzzy match against roster via `radar/matching.py` |
| 5 | Capture one live snapshot of each into `data/scraper_cache/` | demo can run offline |
| 6 | `tests/test_scrapers.py` — snapshot tests using captured JSON as input | green |
| 7 | Wire all 5 into `radar/orchestrator.py` skeleton | `python -m radar.orchestrator` runs all 5, prints signal counts |

**Commit:** `feat(radar): 5 scrapers shipping signals (cached for offline demo)`

**Gate 2a pass:** Orchestrator prints ≥10 signals across all 5 sources from cached fixtures. All scrapers also produce ≥1 fresh signal on a live run.

### 2.5 Phase 3 — Scoring (Day 3, ~5 hours)

| Hour | Task |
|---|---|
| 1 | `radar/scoring_config.py` — rule weights table (the 10 rules from SPEC §4.3) + `BARK_THRESHOLD=80` |
| 2 | `radar/scoring.py` — one pure function per rule family, returning `list[ScoreComponent]`. Wire them into `score_issuer()`. |
| 3 | `radar/scoring.py` continued — `score_all(issuers, signals, today)` |
| 4 | `tests/test_scoring.py` — golden-file fixture: fixed signals + fixed today date → fixed score breakdown. One test per rule. Test that Razorpay/Urban Company/Pine Labs score >80 with the demo-day signal mix. |
| 5 | Hook scoring into orchestrator; persist scores to DB; render top-10 in `/` route as a basic table | digest view stops being a placeholder |

**Commit:** `feat(radar): scoring engine with 10 rules + provenance`

**Gate 2b pass:** `/` shows a real ranked table. 3 designed-high issuers score >80, 3 designed-low score <30.

### 2.6 Phase 4 — Mechanics engine (Day 4, ~8 hours — heaviest day)

| Hour | Task |
|---|---|
| 1 | `radar/mechanics.py` — `TenderParams`, `EligibilityFilter`, `WaterfallPreview` pydantic models |
| 2 | `radar/mechanics.py` — `is_eligible(holder, filter)` pure function + tests |
| 3 | `radar/mechanics.py` — `preview_tender(issuer, holders, params) -> WaterfallPreview`. Returns eligible count, pool, USD value, scaleback factor, top-10 concentration. |
| 4 | `tests/test_mechanics.py` — golden-file tests on Razorpay holder fixture. **Includes benchmark test asserting <50ms.** |
| 5 | `radar/templates/issuer.html.j2` — score breakdown section + mechanics section with HTMX `hx-post` slider |
| 6 | `radar/templates/_preview.html.j2` — partial returned by `POST /issuer/<id>/preview` |
| 7 | `radar/app.py` — wire the POST route. Validate inputs, call `preview_tender`, return partial. |
| 8 | Manual UX pass — slider feels live; numbers update with no flash. Buffer hour for slippage. |

**Commit:** `feat(radar): mechanics engine + live HTMX waterfall preview`

**Gate 3a pass:** Drag slider on `/issuer/razorpay`, waterfall numbers update <100ms perceived, benchmark test green.

**Rollback target:** if Hour 8 still has bugs, ship a *static* mechanics table (no slider) showing a single $20M tender — demo line becomes "live recompute is on the roadmap; today the preview is precomputed."

### 2.7 Phase 5 — Compliance engine (Day 5, ~5 hours)

| Hour | Task |
|---|---|
| 1 | `radar/stamp_duty.py` — 5-state matrix as a dict, each with rate + citation string (state stamp act + section) |
| 2 | `radar/compliance.py` — `preview_compliance(issuer, seller_mix, share_class, price_inr, fair_value_proxy_inr)`. RBI floor verdict logic (using last-round price as proxy with disclaimer). FC-TRS volume estimator. Stamp duty lookup. Required-attachments static list. |
| 3 | `tests/test_compliance.py` — golden-file tests: 5 states × 3 seller-mix combos × 2 share classes = 30 cases |
| 4 | `radar/templates/issuer.html.j2` — compliance section appended; auto-fills from issuer record + sensible defaults for seller mix |
| 5 | Disclaimer footer: *"Tender Radar publishes no opinions on legality. Fair-value proxy is last-round price. Counsel sign-off required."* Manual verify on every page. |

**Commit:** `feat(radar): compliance engine + 5-state stamp duty matrix`

**Gate 3b pass:** All 30 golden-file cases green. Razorpay page shows full compliance section with RBI verdict + FC-TRS estimate + stamp duty.

### 2.8 Phase 6 — Digest, history, Bark (Day 6, ~6 hours)

| Hour | Task |
|---|---|
| 1 | `radar/digest.py` — render the digest HTML from scores + reg-delta signals; persist to `data/digests/<date>.html` |
| 2 | `radar/templates/digest.html.j2` — final layout: header, top-10 table, reg-delta strip, fresh-signals strip, footer |
| 3 | **Generate 3 backdated digests** (May 14, 15, 17) with hand-crafted scenarios so `/history` is populated. Script: `scripts/seed_history.py` |
| 4 | `radar/templates/history.html.j2` — directory listing of `data/digests/*.html` with date + top-3 + alert summary |
| 5 | `radar/bark.py` — reuse finance-digest's Bark client; fire on `score >= 80` with dedup logic (don't refire if same issuer alerted in last 24h) |
| 6 | `make demo-day` — single command: clear today's digest, run orchestrator, render digest, fire Bark, open browser at `/`. |

**Commit:** `feat(radar): digest renderer + history + bark integration`

**Gate 4 pass:** `make demo-day` end-to-end <30s. Bark push arrives on phone. `/history` shows 4 dates (3 backdated + today).

### 2.9 Phase 7 — Polish + dry runs (Day 7, ~6 hours)

| Hour | Task |
|---|---|
| 1 | `radar/static/styles.css` — ~80 lines; muted blue-grey palette; JetBrains Mono numerics via CDN; audit-firm aesthetic |
| 2 | Provenance link audit — every numeric on every page has a `<sup>` link to the source signal URL |
| 3 | README.md — single page: what it is, how to run, demo script, screenshots |
| 4 | **Q&A prep doc** — `QA_PREP.md` with top 10 questions Olesia is likely to ask, with 1–2 sentence answers each (see §3.4 below for the list) |
| 5 | Dry run #1 — full 5-min walkthrough on actual screen-share setup; record yourself; note glitches |
| 6 | Fix glitches; dry run #2; freeze build |

**Commit:** `chore(radar): demo-ready (frozen)`

**Gate 5 (Definition of Done):** All 10 items from SPEC §13 green. Plus: 2 consecutive dry runs without glitches.

---

## 3. Plan audit — what could still go wrong

### 3.1 Risk-weighted by phase

| Phase | Slip probability | Impact if slips | Mitigation |
|---|---|---|---|
| Phase 0 | Low | Cascades into Day 4 | Do it the day before kickoff, not the morning of |
| Phase 1 | Low | Low | Standard scaffolding |
| Phase 2 | **Medium** | High — no scrapers = no demo | All work cached as JSON; if a live source breaks demo day, we use cache silently |
| Phase 3 | Low | Medium — but if it slips, the digest looks wrong | Rule logic is simple arithmetic; primary risk is fixture data not producing the score distribution we want — tunable in `scoring_config.py` |
| **Phase 4** | **High** | **High** — mechanics engine is the demo's centerpiece | Rollback to static mechanics table. Buffer hour built in. |
| Phase 5 | Medium | Medium — partial compliance is OK | If RBI floor logic blows up, ship stamp-duty + FC-TRS only |
| Phase 6 | Low | Low–medium — Bark failure is recoverable | Pre-record a Bark screenshot as fallback |
| Phase 7 | Low | High if skipped — unrehearsed demo fails | Non-negotiable: 2 dry runs |

### 3.2 Critical path

**Phase 0 → Phase 4 is the critical path.** Holder fixtures (Phase 0) feed mechanics (Phase 4). If holders aren't realistic, mechanics output looks fake. If mechanics doesn't recompute live, the demo's most impressive moment is dead.

**Buffer:** Day 7 has 4 hours of pure slack (Hours 5–6 of Phase 7 are dry runs; if dry run #1 is glitch-free, Hour 6 is free time).

### 3.3 Hidden assumptions worth testing now

1. **Bark works on Indian carrier.** Test before Day 6 — fire a manual push from a one-line script. If it doesn't deliver in <30s, find out now.
2. **UnlistedKart's HTML hasn't changed since I last looked.** Spot-check the page structure on Day 0 before committing to the selector strategy.
3. **SEBI EDIFAR allows scraping without rate-limiting an IP.** Check robots.txt and run 1 page on Day 0; if blocked, fall back to **SEBI's DRHP press releases via RSS** which is easier but less timely.
4. **Olesia's machine can open `localhost:5001`.** No — the demo is on *my* screen via Zoom share. This is fine, but confirm Zoom's screen-share doesn't lag the HTMX slider visibly.

### 3.4 Top-10 questions Olesia is likely to ask (Q&A prep deliverable)

| # | Question | Prepared answer (1–2 sentences) |
|---|---|---|
| 1 | "Do we have something like this internally?" | "I assumed you might — the goal was to show how I'd approach the desk's recurring work. If there's an internal version, I'd want to learn what gaps it has and build into those." |
| 2 | "How does this differ from Hiive's pre-IPO data?" | "Hiive prices what buyers are willing to pay. This predicts which issuers should run a structured tender next. Different question, different data shape. Hiive can't do this because they don't have the cap-table relationship." |
| 3 | "Where does the buyer side come in?" | "Out of scope by design. Buyer-side data is confidential, and a buyer matcher on synthetic data wouldn't be credible. Phase 2 inside Qapita uses your internal Rolodex." |
| 4 | "How accurate is the India compliance logic?" | "Stamp duty and FC-TRS are auditable against state acts and RBI master directions — cited inline. The RBI floor uses last-round price as a fair-value proxy with a clear disclaimer; real transactions need ICAI-method valuation." |
| 5 | "What if a scraper breaks?" | "All five run on a 120-second budget and write to a JSON cache. If one fails, the digest still ships with the others and shows a stale-source banner. The demo's cached for offline runs." |
| 6 | "Why are the rules weighted the way they are?" | "Honest answer: best-guess starting weights. Backtesting against the 35 tenders Qapita has run is on the roadmap and is the first thing I'd do post-hire to calibrate." |
| 7 | "Why not use ML?" | "Explainability. Every score component has to justify itself to a regulator-facing team. An ML model can't say 'I gave Razorpay 30 points because Series F is 22 months old.' A rule can." |
| 8 | "What would you do first if I hired you?" | "Swap the scrapers for Qapita's internal data feeds. The digest shape stays — the inputs upgrade. By month 3, the mechanics engine handles SEA waterfall types from the Bandhan-style fixtures." |
| 9 | "Did you talk to anyone on the desk while building?" | "No — this was built on public information end-to-end to keep the conversation honest. Some of what I built will be wrong about how you actually work. That's expected." |
| 10 | "Can I see the code?" | Yes. The repo is structured per the spec; key modules are `mechanics.py`, `compliance.py`, `scoring.py`. Walk through `preview_tender` if she wants depth. |

---

## 4. Why hasn't this been built already? — market scan

The right question. If it's a good idea and easy, someone has done it. Let me reason about why it hasn't.

### 4.1 Could Qapita already have this internally?

**Probably some version, no.** Reasoning:

- **Secondaries desk is small.** Qapita's total HC is ~300, distributed across 9 offices and multiple product lines (cap table, ESOP, valuations, fund admin post-Punch, US/Schwab). The secondaries desk is plausibly 5–10 people including SG + India coverage. Small teams ship spreadsheets, not internal tools.
- **Their product team builds for customers, not for the desk.** Engineering investment goes into platform features that monetize (tender admin module, ESOP grant accounting, etc.), not into desk-internal intelligence.
- **The Punch + Schwab integrations are eating engineering bandwidth right now.** Series B closed Oct 2025; integration sprints are still active. Internal tooling for a small SEA desk isn't the priority.
- **The roster + signal mix is novel.** Even if Qapita's product team built a "tender candidates" report, they'd build it from internal data (cap table aging + ESOP cliff dates). They wouldn't bother adding UnlistedKart price drift, DRHP filings, and Google News employee-pressure proxies — those are *external market signals* the desk currently reads manually.
- **Olesia's role is founders-office + BD-flavored.** If a polished internal version existed, she wouldn't be inbound-screening interns to build market-facing things — she'd be screening for ops support.

**Confidence: ~70% that nothing like Tender Radar exists internally. ~30% chance something adjacent exists (a static "deal pipeline" sheet, an ESOP-vesting-cliff alert, etc.) — and that's the right answer to question #1 in the Q&A prep.**

### 4.2 Why don't Hiive, Forge, EquityZen have this?

**Architectural reason:** their business model is *the opposite*. They are buyer-driven, deal-by-deal marketplaces. They price what's available; they don't predict what should become available.

- **No cap-table relationship.** Hiive et al. aggregate bid/ask data from accredited investors. They don't have a roster of issuers they advise.
- **No regulatory motivation for India signals.** They're US-focused. UnlistedKart, SEBI EDIFAR, FC-TRS volume — none of this enters their workflow.
- **No issuer-side analyst desk to serve.** Their customers are buyers and sellers, not advisors.

**This is structural, not opportunity.** They literally can't ship this product without being a different company.

### 4.3 Why doesn't Carta have this?

Carta has the cap-table relationship — they're the closest analog. Why isn't this a Carta feature?

- **Privacy-model collision.** Each Carta customer's cap table is private from every other customer. A "rank the 50 issuers most likely to tender" report requires *cross-roster* analysis. Carta's contracts likely prevent that.
- **Tender admin is reactive at Carta.** They ship the tooling once a customer launches; they don't suggest that a customer should.
- **US-first.** No India regulatory engine, no UnlistedKart access.
- **Qapita is the cap-table provider that *originated* in a market (India + SEA) where issuer-side advisory is core to the relationship.** That's the wedge.

### 4.4 Why doesn't a secondary fund (Industry Ventures, Setter, Lexington) build this?

- They're buyers, not platforms. They want to *find* deals, not predict them at the company level.
- Their tooling exists for buyer-side sourcing — Pitchbook screens, LinkedIn sourcing, banker intros. Different shape.
- Building an issuer-side tender-readiness product would compete with the bankers who source them. Bad relationship play.

### 4.5 Why doesn't a banker (Lazard, Jefferies, Greenhill) build this?

- They serve a few enterprise mandates, not a 2,700-issuer roster.
- Their "data" is relationship-driven — calls, dinners, board seats. Not RSS scraping.
- They'd never build software that's giveaway-able; their margin is in the relationship.

### 4.6 So what's the actual gap?

The gap is: **"who has the cap-table relationship to a roster of 2,700 private companies in markets where issuer-side liquidity advice is core, *and* the technical org to build internal tooling?"**

The answer is **Qapita and almost nobody else**. EquityList in India is too small. Trica explicitly doesn't run secondaries. Eqvista and Hissa don't have the roster scale.

So Tender Radar is a thing that **Qapita could build but hasn't, because their bandwidth is on platform features, not desk-internal intelligence.** An NOC intern arriving with a working demo is *exactly* what should plug this gap, because:

1. The work is high-leverage but not platform-blocking
2. It serves a specific desk, not the whole customer base
3. It can be built in 7 days as a prototype and matured over a 6-month internship
4. It doesn't compete with any in-flight product investment

### 4.7 What's the failure mode of the pitch?

The risks, ranked:

1. **"We already have this."** (~25%) — answered by Q&A #1; pivot to "show me what's missing."
2. **"This is too presumptuous."** (~10%) — framing matters. Open with "I built this on public data to show how I think about the desk's work, not to claim you don't have it."
3. **"Secondaries isn't actually her team."** (~15%) — Olesia is Founders Office, which is generalist. If her desk is actually adjacent (e.g., partnerships, content, ESOP advisory), the demo still proves analytical chops but lands less directly. Manageable.
4. **"The mechanics + compliance look off."** (~10%) — possible because I built on public sources; the on-stage answer is "tell me what's wrong; that's the calibration loop I'd do month 1."
5. **"The scrapers are fragile / unprofessional."** (~10%) — caching mitigates; framing matters ("disposable layer; internal data replaces this in week 2").
6. **None of the above; demo lands.** (~30%) — best case.

### 4.8 Build / no-build decision

**Build. Conditionally.**

- **Build** because: nobody else can plausibly have built this (§4.1–4.5), the demo shape pattern-matches Olesia's daily reading (per `OLESIA_RESEARCH.md`), and the engines underneath have a 6-month internship trajectory (per `ELIMINATION.md` Scaling Audit).
- **Conditionally** because: the 25% "already have it" probability is non-trivial, and the response must be **rehearsed** (Q&A #1). If the answer is wobbled in the interview, the demo's value evaporates.
- **Don't build** if any of these become true before kickoff:
  - You find a public Qapita blog post / press release describing an internal tool of this shape (search SEBI India + Qapita blog before Day 0)
  - Olesia's actual role turns out to be HR-flavored, not desk-flavored (LinkedIn re-check on Day 0)
  - Bark fails to deliver on Indian carrier in the Phase 0 test

Run those three checks at the start of Phase 0. If all clear → green light.

---

## 5. Pre-build checklist (do these on Day 0 morning)

- [ ] Re-read `OLESIA_RESEARCH.md`, `ELIMINATION.md`, `SPEC_OLESIA.md`, this file end-to-end one more time
- [ ] Search "Qapita tender readiness" / "Qapita secondaries dashboard" / "Qapita issuer scoring" — confirm no public artifact exists
- [ ] Re-check Olesia's LinkedIn for any title change in last 7 days
- [ ] Fire a test Bark push from `~/Desktop/qapita/scripts/test_bark.py`; confirm <30s delivery
- [ ] Confirm `~/Desktop/qapita/.venv/` activates and `pip install httpx selectolax feedparser apscheduler rapidfuzz` succeeds
- [ ] Spot-check UnlistedKart and SEBI EDIFAR — make sure the HTML I'm planning to parse hasn't changed
- [ ] If all 6 pass: start Phase 0. If any fails: revisit this plan.

---

## 6. Decision

**GO. Start Phase 0 immediately. Begin Phase 1 once Gate 0 passes.**

The plan above replaces `SPEC_OLESIA.md` §10 as the operational source of truth. The spec remains the architectural contract; this plan is the execution path.
