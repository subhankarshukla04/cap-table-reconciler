# Jax / Qapita Demo — 5 Automation Recommendations, Ranked

**Context:** 30-min NOC-inbound interview with Jax LIU Jiawei (Founders' Office + Head of SEA). The user will demo something on screen-share and pitch the post-hire 6-month scaling path. See `./JAX_RESEARCH.md` for the persona and `../OLESIA_RESEARCH.md` for the sister-interview rules.

## Selection rules (carried from Evelyn + Olesia tracks)

- **Zero strategic / valuation / pricing judgments.** No "AI picks the target," "AI prices the secondary," "AI writes the investor update."
- **Audit-grade deterministic.** No LLM inside the calculation or scoring pipeline. (LLM may render copy at the surface; never decide.)
- **Demo-able in 5 minutes** on `localhost:5000` over screen-share.
- **Buildable in 4–7 days** by a single NOC intern using the existing stack (Flask + HTMX + pydantic + openpyxl + requests/feedparser + Bark for push).
- **Must hit a publicly-claimed scale point** so the demo's relevance to Qapita is obvious from the first slide.
- **Must pattern-match validated precedents:** Wego Earnings Digest and Qatalyst Sentinel — recurring intelligence the team reads every morning, not a one-shot transactional tool. (Tender Radar in the Olesia track is the most-recent example of this shape.)

Five candidates below. Each has: one-liner, inputs, outputs, why-it-lands-for-Jax, risks, build effort, scaling ceiling.

---

## 🥇 Idea 1 — SEA Pipeline Radar (recommended winner)

**One-line:** A daily intelligence feed that reads every SEA startup funding announcement (e27, DealStreetAsia, KrAsia, Tech in Asia, Bain SEA, regional RSS) and scores each newly-funded company for **Qapita-fit** — surfacing a ranked Monday-morning lead list for SEA BD and Founders' Office.

**Inputs (all public, all scrape-able locally):**
- RSS / page scrapes: e27, DealStreetAsia (free tier), KrAsia, Tech in Asia, Tech Collective, Cento Ventures SEA Tech Investment reports, Bain–Google–Temasek e-Conomy SEA annual deck (annual but referenceable).
- A static "Qapita-fit" rubric YAML: jurisdiction weights (SG / ID / VN / TH / PH / MY), round-stage band (Series A through Series D where ESOP complexity blooms), sector tags, lead-investor tags (some funds correlate with sophisticated ESOP design), employee-count proxy from LinkedIn (optional, no auth).
- The existing Qapita customer logo list (publicly visible on the website) as a "do-not-surface, already a customer" mask.

**Outputs:**
- **Monday morning HTML digest:** top 20 newly-funded SEA companies ranked by fit score, each with the funding announcement link, the score breakdown (jurisdiction +X, stage +X, lead-investor +X, sector +X, HC-proxy +X), and a one-sentence "why this is a Qapita lead" generated from the rubric (deterministic — template + score, not LLM prose).
- **Per-company drilldown page:** the announcement, the fit-score breakdown, a "first-touch BD note" template (pre-filled with the company's name, lead investor, round size, sector), and a "skip / save / hand to CSM" button (mock — just a state toggle).
- **Sentinel-style alert via Bark** (mirrors the user's finance-digest at 9:30 PM IST) when a company crosses score > 90 *and* is not already in a customer list — pings Jax's phone the moment a hot lead lands.

**Why it lands for Jax specifically:**
- **SEA is his mandate.** Demoing a tool that reads SEA fundraising news every morning is demoing his own job's morning ritual.
- **Direct precedent fit:** same shape as Wego Earnings Digest + Qatalyst Sentinel + Tender Radar — the team-reads-it-every-morning workflow he can picture without you explaining.
- **Hits a public scale point:** the 70/20/10 geo split — 20% SEA is the part he's paid to grow, and a tool that systematically catches every SEA lead before BD does is the most natural thing he could possibly want.
- **Zero strategic judgment:** the score is rule-based and fully explainable; the human still decides whether to call.
- **Maps cleanly to his own arc.** He ran NOC NY → SEA ops; he will recognize this as the kind of leverage tool a generalist would build before being given a real BD seat.

**Risks / what to watch:**
- RSS schemas drift — keep scrapers modular, one file per source, fail-soft. The demo only needs them green on demo day.
- Don't claim the score "predicts" anything. It's a ranking heuristic. Be explicit.
- Don't include a "lead temperature" or "likely-to-close" output — that's a sales judgment, not a workflow output.

**Build effort:** 5–7 days.
- Day 1–2: scraper foundations (5 sources, feedparser + requests + BeautifulSoup, fixtures for offline demo).
- Day 3: scoring rubric YAML + scoring engine + tests.
- Day 4: digest renderer (Jinja templates, polished HTML/email-grade).
- Day 5: per-company drilldown page (HTMX-driven, no SPA).
- Day 6: Bark integration + cron + scheduling polish.
- Day 7: 3 worked-example fixture digests (one each: SG / ID / VN) for a fully-loaded screen-share.

**Reuse from existing repo:**
- `app.py` Flask scaffolding, openpyxl helpers (for CSV export), templates folder, fixtures pattern.
- Bark push pattern from the finance-digest project.
- Tender Radar's scoring-engine + digest-renderer modules (if shipped by then).

**Scaling ceiling: High — durable.** This is *not* a throwaway. As Qapita's internal data (lead history, conversion data) plugs in, the scrapers retire one by one and the score adapts from "public-only" to "public + internal," but the digest shape stays. Eventually becomes Qapita's SEA BD operating dashboard. Then mirrors itself for India (already an Inc42/VCCircle scrape away) and for the US (Crunchbase / PitchBook free signals). Three-region SaaS-internal-tool footprint within 12 months of hire.

**Demo strength: 9.5/10.**

---

## 🥈 Idea 2 — M&A Target Scanner (Punch-style funnel)

**One-line:** Score US + SEA micro-firms in fund-admin, virtual-CFO, ESOP consulting, 409A boutiques, and corp-sec for acquireability — generating a weekly ranked deal-flow memo for Founders' Office.

**Inputs (all public):**
- Crunchbase Pro free pages (or scrape of free profile pages where allowed), LinkedIn company-page HC counts (no auth needed for public counts), G2 / Capterra customer ratings as a quality proxy, US SOS filings for ownership signals (where searchable), founder LinkedIn tenure.
- A "Punch-pattern" rubric: HC band 5–30, founder-led (founder still listed as CEO with no intermediate CXO), no institutional funding (or only friends-and-family), service category match, geographic match (US / SEA priority).
- An exclusion list — already-acquired firms, firms with >$10M raised (likely too expensive), firms inside larger groups.

**Outputs:**
- **Weekly Friday memo:** top 15 candidates ranked by acquireability score with breakdown (HC fit, founder-led signal, category fit, no-VC signal, geo fit).
- **Per-target diligence page:** assembled desktop research — founder bio, HC timeline, customer-mention signals from G2/Capterra, public news mentions, contact email guess via Hunter-pattern (display only, don't send).
- Export-to-PDF deal-flow memo (mail-merge style) ready to hand to Ravi.

**Why it lands for Jax:**
- **Founders' Office runs corp-dev.** Punch was the first; there will be more. A tool that pre-stages the desktop research saves the FO analyst (likely *you*, post-hire) days per acquisition cycle.
- **Reads the room:** signals you noticed the Punch acquisition and inferred the next-12-month acquisition cadence.

**Risks:**
- Acquireability is partly judgment. The tool must rank, not "recommend." Frame the score as a triage filter, not a pick.
- Founder-LinkedIn scraping is a politeness line — don't show the email-guess pattern feature in the demo, just say it's a stretch goal.

**Build effort:** 4–5 days. Lighter than Idea 1 because fewer live feeds — more static-list-of-companies + enrichment.

**Scaling ceiling: Moderate–high.** Becomes Qapita's corp-dev pipeline tracker. Caveat: deal flow is intrinsically sparse — the tool runs weekly, not daily, and once the Punch wave is over (~2–4 more deals over 12 months) it goes quiet. Less recurring than Idea 1.

**Demo strength: 8/10.**

---

## 🥉 Idea 3 — Investor-Update / Board-Pack Skeleton Builder

**One-line:** Given a CSV of monthly KPIs (ARR, customer count, equity AUM, programs run, NPS, headcount, cash runway) and the prior month's commentary, generate a draft board-pack skeleton — data tables formatted, charts pre-rendered, narrative bullets blanked for the founder to fill in.

**Inputs:**
- Monthly KPI CSV (synthetic for demo — invent 12 months of plausible Qapita-shape KPIs).
- A "board pack template" YAML — section ordering, chart specs, narrative-bullet prompts (deterministic — "vs last month, customer count moved by X — please comment").
- Prior-month free-text commentary (so the new month's draft can cross-reference).

**Outputs:**
- Single PDF / HTML deck: cover, KPI tables, trend charts (matplotlib or chart.js), section-by-section bullets with the data filled in and the *commentary lines blank*, ready for the founder/Jax to write the narrative.
- Excel export of the underlying numbers (lookup-grade, for the CFO).

**Why it lands for Jax:**
- This is the single most repetitive piece of FO work — happens every 30 days, takes 8–12 hours of formatting + chart-pasting, and the format barely changes. Automating the scaffolding (not the narrative) is the textbook example of the discipline rule.
- Signals you know what FO actually does day-to-day.

**Risks:**
- Demo without real data feels academic — has to be visually polished to land.
- Don't let the LLM write the narrative bullets. The narrative is the craft. The tool only assembles the structure.

**Build effort:** 4–5 days. Pure rendering + chart prep + template assembly. No live data ingest.

**Scaling ceiling: Moderate.** Universally useful inside the org but doesn't generate competitive advantage — pure internal-productivity tool. Plateaus once the format is locked in. Won't spin out as a product.

**Demo strength: 7.5/10** — visually photogenic but a bit "intern-shaped" (it's exactly the kind of thing a junior would build to save themselves time, which is fine but unambitious for Jax).

---

## Idea 4 — Competitor Pulse Memo

**One-line:** A Friday-afternoon HTML memo summarizing the week's moves by Carta, Pulley, Hiive, Forge, Globacap, Trica, EquityList, AngelList — product-page changes (sitemap diff), funding news, hiring velocity (LinkedIn HC delta + job-post counts by team), executive moves.

**Inputs (all public):**
- Competitor sitemap.xml weekly diffs (detects new product pages / pricing changes).
- LinkedIn public HC counters + job-post pages (no auth, no scraping ToS-violation — just the public counts).
- Funding/news RSS for the names (TechCrunch, PitchBook free, Inc42, Tech in Asia).
- A static config file mapping competitor → their product taxonomy (so a "/secondaries" page going live on Pulley becomes a flagged event).

**Outputs:**
- Friday 4 PM SGT HTML memo: per-competitor pulse, week-over-week deltas, the 3 most-flag-worthy moves, and a "why this matters for Qapita" template-driven note.
- Optional alert via Bark when a competitor crosses a threshold (e.g., posts >5 SEA-region jobs in a week = signals regional move).

**Why it lands for Jax:**
- Regional GM persona — competitive intel is a standing ask he doesn't have time to run.
- Maps the Schwab-as-distribution thesis: a tool that watches Carta's hiring + product moves week over week tells him whether the partnership is durable.

**Risks:**
- "Competitor watch" risks tipping into surveillance theatre if the rubric is shallow.
- LinkedIn HC counts can be noisy week to week — smooth over 4-week windows.

**Build effort:** 4–5 days. Sitemap diffing is one day; LinkedIn HC scraping is one day (public counts only); RSS aggregation is half a day; memo rendering is one day.

**Scaling ceiling: Moderate.** Doesn't deepen much — just adds competitors. But the memo shape lasts and the alert layer scales. Less ambitious than Idea 1 because it doesn't produce customer leads.

**Demo strength: 7/10** — useful, but Jax can build the mental model himself in 30 min of Twitter scrolling. Less differentiated.

---

## Idea 5 — Customer-Health Radar (read-only public signals)

**One-line:** For Qapita's existing customer roster (publicly listed logos), monitor public-signal churn risk — funding-round news (especially down rounds), layoff announcements, CFO/HR-head departures, IPO filings (graduation, not churn but exit-the-platform risk), Glassdoor/Blind sentiment swings — and surface a weekly health pulse for the CSM team.

**Inputs:**
- Public customer logo list from qapita.com (or stated externally — Razorpay, Zepto, Ather, Acko, Boat, Pine Labs, OYO, Physics Wallah, etc.).
- Inc42 / VCCircle / TechCrunch / e27 RSS for the named-company watchlist.
- Layoffs.fyi for layoff signals (public dataset).
- SEBI EDIFAR / SEC EDGAR for filings.
- Glassdoor RSS where available (rate-limited public; use sparingly).

**Outputs:**
- **Weekly CSM dashboard:** per-customer health bands (green / amber / red), recent signals, "why amber" template-driven explanation.
- Alert when any customer crosses to red (Bark / Slack).

**Why it lands for Jax:**
- Founders' Office cares about customer retention because logo churn shows up in board packs. A tool that gives CSM 14 days of head start on a churn risk has unambiguous board-level ROI.
- The customer roster is one of Qapita's strongest assets — a tool that protects it signals you understand commercial leverage.

**Risks:**
- "Health score" sounds like AI judgment — it isn't, but you have to be vocal about the deterministic rubric.
- Don't show competitor logo movement (Carta-poaching signals) — that's gossip-shaped, not workflow-shaped.

**Build effort:** 5 days. Similar to Idea 1's architecture but watchlist-locked rather than open-funnel.

**Scaling ceiling: Moderate–high.** Plugs neatly into Qapita's existing CSM workflow as a feed, not a system. Doesn't replace the CSM call cadence; informs it. Durable, useful, but quieter than Idea 1 because it operates on a fixed roster instead of an open SEA funnel.

**Demo strength: 7.5/10** — strong commercial logic, but the demo is harder to make photogenic (mostly amber/green tiles).

---

## Recommendation summary table

| # | Idea | Effort | Demo | Scaling | Fit-for-Jax |
|---|---|---|---|---|---|
| **1** | **SEA Pipeline Radar** | 5–7d | **9.5/10** | **High — durable** | **★★★ Direct mandate hit** |
| 2 | M&A Target Scanner | 4–5d | 8/10 | Moderate–high | ★★ Hits Punch precedent |
| 3 | Investor-Update Skeleton | 4–5d | 7.5/10 | Moderate | ★★ Hits FO repetition |
| 4 | Competitor Pulse Memo | 4–5d | 7/10 | Moderate | ★ Useful but commodity |
| 5 | Customer-Health Radar | 5d | 7.5/10 | Moderate–high | ★★ Board-level ROI |

## Highest-ROI pick — Idea 1 (SEA Pipeline Radar)

**Why this specifically over the other 4:**
1. **Direct precedent fit** with Wego Earnings Digest / Qatalyst Sentinel / Tender Radar — the user has *already* validated this shape with three prior interviewers. The fourth instance lands without re-explaining the precedent.
2. **Direct mandate fit** — SEA is Jax's job. No tool is more obviously useful to him every Monday morning than this one.
3. **Scaling story writes itself** — Phase 1 (public scrapers) → Phase 2 (internal lead-history adds signal) → Phase 3 (mirror for India + US) → SEA BD's operating dashboard. Tellable in two sentences.
4. **Zero judgment surface** — the score is rule-based and fully explainable. No "AI decides" risk.
5. **Cheapest path to a polished demo** because the existing finance-digest project (Bark, scheduling, HTML email rendering) and the Tender Radar (scoring engine + digest renderer) are direct ancestors.

**What to demo (the opening line, drafted):**
> "Every Monday morning, your SEA BD desk needs to know which startups raised in SEA last week, which of them fit Qapita's wedge, and which one to call first. This tool reads five public feeds, scores every newly-funded SEA company against a transparent rubric — jurisdiction, stage, sector, lead investor — and gives you a ranked Monday digest. The score is rule-based; no judgment is made. You still decide who to call. The tool decides who to surface."

That sentence carries the discipline (no judgment), proves SEA-mandate awareness (the right region), and tells Jax the build is the same shape as the precedents he could reach for if you mentioned them.

## Next step

Run a one-pass elimination round (analogous to `../ELIMINATION.md`) **before** starting the build. Confirm Idea 1 survives against the 5 criteria with Jax-flavored weights. Then scope a `PLAN_JAX.md` with the 5 scrapers, the rubric YAML, and the digest schedule. Reuse as much of `~/Desktop/qapita/` (templates, fixtures, openpyxl helpers, Bark integration) as possible.
