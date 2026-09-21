# Olesia / Qapita Demo — Elimination Audit

**Purpose:** Reduce the 5 candidates in `OLESIA_RESEARCH.md` to a single buildable demo by eliminating one per round against five fixed criteria.

**Audit criteria (applied identically every round):**
1. **Build** — feasibility in 4–7 days with the stack we have (Flask + HTMX + pydantic + openpyxl).
2. **Achievable** — what the final demo actually shows on screen.
3. **Useful for them** — does it touch the real recurring work of the secondaries desk?
4. **Resources & local hosting** — can we get the inputs without paid APIs, run it on `localhost` for screen-share?
5. **Precedent fit** — does it pattern-match **Wego Earnings Digest** and **Qatalyst Sentinel**? Both are recurring intelligence feeds the team reads every morning — *not* one-shot workflow tools.

**The 5 starting candidates** (from `OLESIA_RESEARCH.md`):
1. Tender Offer Eligibility & Waterfall Builder
2. FEMA / FC-TRS Cross-Border Pre-Check
3. ROFR / ROFO Deadline & Notification Tracker
4. Participant Comms & Election-State Tracker
5. Buyer-Demand Match Engine

---

## Round 1 — eliminate Idea 5 (Buyer-Demand Match Engine)

| Criterion | Verdict |
|---|---|
| Build | Easy, 3d. |
| Achievable | A scored shortlist UI with "why" annotations. |
| Useful for them | **Low novelty.** Olesia's desk already has a buyer Rolodex in an internal sheet; codifying it offers no signal they don't have. |
| Resources / local | Buyer-preference data is **confidential and not publicly available**. The demo has to use fully fictional buyers, which kills credibility. |
| Precedent fit | None. Reads as a CRM tab, not a Sentinel/Digest. |

**Cut reason:** It looks the most like AI-picks-the-buyer, the exact misread we cannot risk with a "don't automate the craft" team. And the input data simply isn't accessible locally without confidentiality problems.

**Remaining: 1, 2, 3, 4.**

---

## Round 2 — eliminate Idea 3 (ROFR / ROFO Deadline Tracker)

| Criterion | Verdict |
|---|---|
| Build | 3–4d. State machine + deadline math + PDF generation. |
| Achievable | Dashboard of open clocks + per-deal notice generator. |
| Useful for them | Real pain, but the tool's value depends on **already having a live pipeline of deals fed into it.** Without that, the demo is empty boilerplate. |
| Resources / local | Possible, but the only realistic demo dataset is fully synthetic (we don't have Qapita's deal pipeline). Fictional ROFR notices look like a law-firm template, not a market signal. |
| Precedent fit | Reads as a Jira board. Zero alignment with Sentinel / Digest. |

**Cut reason:** Visually thin, demo-empty without real pipeline data, and the value proposition is internal project management — exactly the kind of tool an intern *could* build in week 3 of the actual job, but not the right thing to *open with*.

**Remaining: 1, 2, 4.**

---

## Round 3 — eliminate Idea 4 (Participant Comms & Election-State Tracker)

| Criterion | Verdict |
|---|---|
| Build | 5–6d. The heaviest of the four. Most of the build is plumbing (mail-merge, state machine, dashboard) that isn't secondary-specific. |
| Achievable | Photogenic dashboard + per-participant election portal. Strongest visual of any candidate. |
| Useful for them | Yes, but **commodity.** Qapita is already a software company; they have engineers who can build this. The intern-shaped value-add isn't here. |
| Resources / local | Local works for the dashboard. Email-send (the most "alive" part of the demo) breaks locally — has to be mocked. |
| Precedent fit | Operational tool. Wego Earnings Digest and Qatalyst Sentinel both deliver **a signal you read every morning**. A comms tracker doesn't fit that mold. |

**Cut reason:** Scope-heavy, most of it isn't unique to secondaries, and the team has the engineering bench to build it themselves whenever they want. Spending 6 days here proves we can ship a Mailchimp clone, not that we understand their market.

**Remaining: 1, 2.**

---

## Round 4 — the final pair, and the reframe

Now between **Idea 1 (Eligibility & Waterfall)** and **Idea 2 (FEMA / FC-TRS Pre-Check)**.

| | Idea 1 | Idea 2 |
|---|---|---|
| Build | 4–5d | 3d |
| Achievable | Waterfall table + offer-letter pack | Compliance verdict + pre-filled FC-TRS sheet + stamp-duty table |
| Useful | Runs *after* a tender is decided | Runs *once per deal* at structuring time |
| Local resources | Fixtures we already have from Evelyn work | Public RBI / SEBI / state stamp-duty rules — all scrape-able |
| Precedent fit | Workflow tool, not a recurring signal | Workflow tool, not a recurring signal |

**Honest finding:** **Neither one pattern-matches Sentinel or Digest.** Both are one-shot transactional tools. If we ship either one alone, we're proving the wrong reflex — that we want to build *features* for the platform, not *intelligence* for the desk.

This is the moment the user's instruction matters: **"or combine 2 to make a new one."**

---

## The combination — "Tender Radar"

**One-line:** A daily / weekly intelligence feed for the secondaries desk that scores every issuer on Qapita's roster for **tender-readiness** — combining the Idea-1 mechanics engine (eligible-pool sizing, waterfall, scaleback math) and the Idea-2 compliance engine (FEMA / RBI pricing-floor, FC-TRS readiness, stamp-duty exposure) as its computation core, fed by **public signals** that pattern-match the Sentinel + Digest precedents.

### How it pattern-matches the precedents

| Tool | What it does daily | Output |
|---|---|---|
| **Wego Earnings Digest** | Scans earnings transcripts for travel-segment signal | A morning digest |
| **Qatalyst Sentinel** | Monitors carbon-credit-issuer feeds for due-diligence risk | An alert when a flag trips |
| **Tender Radar (this)** | Monitors public signals to score the Qapita issuer roster for "due for a tender" | A morning digest + a flag when an issuer crosses the threshold |

Same shape. Same morning-coffee reading rhythm. Same "the analyst reads it before opening their inbox" workflow integration.

### What it ingests (all locally scrape-able, no paid APIs)

1. **Primary fundraise aging** — VCCircle / Inc42 / YourStory RSS for "raised Series C/D/E" announcements. Issuers crossing 18+ months since last primary become tender candidates (employees nearing 4-year cliff = liquidity pressure).
2. **Unlisted-share price drift** — scrape UnlistedKart (now Qapita-owned) + Stockify + IPV for the issuer roster. Spreads widening = secondary demand building.
3. **DRHP / IPO-filing watch** — SEBI EDIFAR public filings index. A DRHP file = a 60–90 day pre-IPO secondary window opening.
4. **Regulatory delta** — SEBI press release RSS, RBI press release RSS, Ministry of Corporate Affairs circulars. Any change touching private-share transfer rules.
5. **Employee-pressure proxies** — Glassdoor / Blind / news scrape for "layoff" / "ESOP cliff" / "RSU repricing" mentions on the issuer roster.

### What it outputs

- **Morning HTML digest** (7 AM SGT, mirrors the finance-digest project the user already runs at 9:30 PM IST): top 10 issuers ranked by tender-readiness score with the signal that moved them.
- **Per-issuer detail page**: tender-readiness score breakdown + an **instant mechanics preview** using the Idea-1 engine (if a $20M tender ran at last-round-price, how many holders eligible, indicative waterfall, scaleback if 2x oversubscribed) + an **instant compliance preview** using the Idea-2 engine (cross-border seller mix, stamp-duty exposure by issuer state, FC-TRS volume estimate).
- **Sentinel-style alert** when an issuer crosses a threshold (e.g., score > 80 *and* not on any active engagement) — could pipe to Bark for parity with the finance-digest.

### Audit on the combination (running the same 5 criteria one more time)

| Criterion | Verdict |
|---|---|
| Build | 5–7d. Day 1: scraper foundations (5 sources). Day 2: scoring rules. Day 3–4: digest renderer + per-issuer page. Day 5: mechanics preview (port from Idea 1). Day 6: compliance preview (port from Idea 2). Day 7: Bark integration + polish. |
| Achievable | Live HTML digest with real data on real Indian unicorns + 2–3 fully-worked per-issuer pages. Demo-able end-to-end in 4 minutes. |
| Useful | **Yes — and it's the exact-shaped useful.** Olesia's desk's #1 job is "which issuer do we call next month." This is a screen that answers that question every morning. |
| Resources / local | All inputs are public RSS or public-page scrapes. Runs on `localhost:5000` with a 5-min cron. Nothing paid. |
| Precedent fit | **Direct.** A morning digest plus a threshold alert is exactly the Wego/Qatalyst shape. |

**Demo opening line:**
> "This tool reads five public feeds every morning and ranks the 50 most-likely-next-tender issuers on your roster. Click any one and you see the mechanics and India-compliance picture for a hypothetical $X tender on that company. It makes zero pricing judgments — every score is rule-based and explainable."

That sentence carries the discipline from the Evelyn interview (no valuation judgments), proves we understand the desk's *recurring* work (not just transactional), and tells Olesia that we shaped the build to look like the intelligence tools that have worked for similar interviews before.

---

## Decision

**Build: Tender Radar** — a recurring tender-readiness digest + per-issuer mechanics & compliance preview, combining the calc cores of Ideas 1 + 2, shaped like Wego Earnings Digest / Qatalyst Sentinel.

**Discarded:** Ideas 3, 4, 5 in rounds 2/3/1 respectively. Ideas 1 and 2 survive only as **calculation modules inside** the new tool, not as standalone demos.

**Next step (when ready to build):** scope a `PLAN_OLESIA.md` covering the 5 scrapers, the scoring rule-set, and the digest schedule. Re-use as much of the existing `~/Desktop/qapita/` Flask app as possible (templating, fixtures, openpyxl helpers) — different file tree, same engineering grammar.

---

# Scaling Audit — does this survive if she hires me?

The question on the table: assume the interview goes well and the build becomes a real 6–12 month NOC-internship project (or longer). Which of the candidates has a **durable scaling trajectory** vs which only survives the 30-min demo?

## Each candidate's ceiling

| Candidate | Scaling ceiling | Why |
|---|---|---|
| **#1 Eligibility & Waterfall** | **High — standalone SaaS path.** | A tender-administration calculator that handles SEA-flavored share classes (CCPS, RCPS, dual-class, participating-with-cap) has paying customers beyond Qapita: smaller PE firms, law firms running buybacks, secondary funds. Carta-competitive at the calc layer. Engine deepens forever — every share class, every breakpoint, every scaleback rule. |
| **#2 FEMA / FC-TRS** | **High — narrow but durable.** | India-private-transfer compliance as an API. Banks, secondary funds, law firms, and Big-4 audit all want this. Moat = staying current with RBI / SEBI / MCA circulars. Naturally evolves into a regulatory-data SaaS. |
| #3 ROFR Tracker | Low. Already commoditized (Datasite, iDeals own the deal-room layer). |
| #4 Participant Comms | Low. Carta already ships this; you'd be re-building Mailchimp-for-tenders. |
| #5 Buyer Match | Moderate but slow. Network-effects play, requires capturing private buyer data, hard to bootstrap. |
| **Tender Radar (combo)** | **Moderate–high, but with a known cliff.** | The morning-digest shape is exactly the desk's operating rhythm. But the **scrapers are throwaway** — once Qapita's internal data is plugged in, the scraper layer becomes redundant. The durable scaling parts are the **mechanics engine (from #1)** and the **compliance engine (from #2)** underneath. |

## How Tender Radar scales over time

| Phase | Window | What changes | What stays |
|---|---|---|---|
| **Demo phase** | Days 1–7, pre-interview | 5 public scrapers feed the digest; 3 worked-example issuers | The two engines are real |
| **Post-hire Phase 1** | Months 1–3 of internship | Scrapers retire one-by-one as Qapita's internal data (cap tables, deal pipeline, buyer Rolodex) replaces them; digest stays | Digest shape, both engines |
| **Post-hire Phase 2** | Months 4–8 | Mechanics engine deepens — adds SEA-specific waterfall types (CCPS-with-3x-cap, RCPS, dual-class breakpoints from the Bandhan / Pelaut fixtures); compliance engine adds more Indian states + Singapore + UAE rails | Same architecture, more depth |
| **Post-hire Phase 3** | Months 9+ | The engines spin out as **internal calculator services** the whole secondaries desk uses, not just the digest. Tender Radar becomes one consumer of those services, not the whole product | The engines become Qapita-internal infra |

**The honest scaling note:** what's durable is **the two calc engines, not the scrapers.** Budget the 7-day demo build accordingly — don't sink time into hardening scrapers against schema drift; they're disposable. Sink time into making the mechanics + compliance engines **modular and testable**, because those are what survive.

## The fork — if scaling matters MORE than demo-shape

If the priority were "build the most defensible long-term product" instead of "win the 30-min interview":

- **Drop the scrapers and the digest. Build #1 alone as a multi-tenant tender-administration calc.** Cleanest standalone product trajectory of any candidate. Carta-competitive, sellable beyond Qapita, deeper engine room over time.
- But you lose the Sentinel/Digest precedent shape, which is the thing that lands the interview.

## Verdict — same pick, with an updated build budget

**Build Tender Radar.** The morning-digest shape wins the demo *and* matches the desk's recurring operating rhythm long-term. The two engines underneath have an independent scaling path even if the scraper layer eventually retires.

**Build-budget recalibration for the 7 days:**
- ~30% on the scrapers (just enough for a live demo — don't overengineer)
- ~50% on the mechanics + compliance engines (these are the durable assets — make them clean modules with proper tests)
- ~20% on the digest renderer + Bark integration (visual polish)

**One thing to add to the post-interview roadmap (if she asks):**
A clear "Phase 2" pitch — "swap the scrapers for your internal data feeds, and the same digest becomes the desk's daily operating dashboard." That sentence is the bridge from 30-min demo to 6-month internship project, and it's the one Olesia needs to hear to justify the hire.
