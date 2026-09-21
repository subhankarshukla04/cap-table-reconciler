# Jax / Qapita Demo — Elimination Audit

**Purpose:** Reduce the 5 candidates in `AUTOMATION_5.md` to a single buildable demo by eliminating one per round against four fixed criteria. Same shape as `../ELIMINATION.md` ran for Olesia.

**Audit criteria (applied identically every round):**
1. **Scalability to a full-size product** — can the demo grow into a 6-month internship build, then into a durable internal platform or external SaaS? Or does it plateau after the first ship?
2. **Problem severity** — is this a real, recurring pain point with measurable hours-per-week consumed? Or is it a "nice to have" that nobody is currently bleeding over?
3. **Demo quality** — can it be shown in 5 minutes with concrete, photogenic output that lands without you talking? Does the demo prove the build is real and the data is real?
4. **Value to Jax + the SEA team** — does *he*, in his specific seat (Head of SEA + Founders' Office), see the value within 60 seconds? Does the SEA team actually use this every week, or does it sit on a shared drive?

**The 5 starting candidates** (from `AUTOMATION_5.md`):
1. SEA Pipeline Radar — daily digest of newly-funded SEA startups scored on Qapita-fit
2. M&A Target Scanner — score adjacent micro-firms for Punch-style acquireability
3. Investor-Update / Board-Pack Skeleton Builder
4. Competitor Pulse Memo (Carta, Pulley, Hiive, Forge, Globacap, Trica, EquityList)
5. Customer-Health Radar — public-signal churn risk on existing customer roster

---

## Round 1 — eliminate Idea 4 (Competitor Pulse Memo)

| Criterion | Verdict |
|---|---|
| Scalability | **Low.** Adds competitors over time, but the architecture caps out at "weekly memo + alerts." No path to a product. Not infrastructure anyone else inside Qapita reuses. |
| Problem severity | **Moderate-low.** Jax can scroll TechCrunch, Inc42, e27 + Twitter for 20 minutes once a week and reconstruct 80% of the signal himself. There is no team bleeding on this. |
| Demo quality | **Low-moderate.** Output is a text-heavy memo with HC deltas and product-page diffs. Not visually concrete. Hard to land in 5 min — feels like a glorified Google Alerts. |
| Value to Jax | **Low.** Useful background, but no decision changes when he reads it. Doesn't generate a lead, doesn't unblock a deal, doesn't surface a target. He notes it and moves on. |

**Cut reason:** Lowest unique value of the five. It is the only candidate where Jax could plausibly replicate the output himself in under an hour every Friday — which means the tool doesn't earn its space. The other four all surface signal Jax can't easily reproduce by hand.

**Remaining: 1, 2, 3, 5.**

---

## Round 2 — eliminate Idea 3 (Investor-Update / Board-Pack Skeleton Builder)

| Criterion | Verdict |
|---|---|
| Scalability | **Low-moderate.** Plateaus once the board-pack template is locked. No moat — every Series-B startup has someone wiring KPIs into a board template. Won't spin out, won't generalize to other teams. |
| Problem severity | **Moderate.** Real recurring 8–12 hours per month of formatting work, but the people bleeding on it are the **FO analyst (you, post-hire) and a Finance team member** — not Jax himself. He reviews, he doesn't assemble. |
| Demo quality | **Moderate-high (7.5/10).** Photogenic — a finished-looking deck with KPI tables and trend charts demos well. But the synthetic data shows; Jax will mentally discount the polish because the numbers aren't his. |
| Value to Jax | **Low-moderate.** He is the *audience* for the polished version, not the builder. Saves a junior 8h/month, but Jax doesn't feel that 8h directly — and "automating the intern's worst grunt work" is a strange thing to volunteer when interviewing for the intern seat. |

**Cut reason:** This is the tool that helps the person *holding the role* save themselves time. That's the wrong direction in an interview. You want to show value to **the team and the company,** not value to your own day. It also reads as low-ambition relative to the SEA-mandate hits (Ideas 1, 2, 5). The investor-update problem is real but it isn't the problem that buys you a seat.

**Remaining: 1, 2, 5.**

---

## Round 3 — eliminate Idea 5 (Customer-Health Radar)

| Criterion | Verdict |
|---|---|
| Scalability | **Moderate-high.** Plugs into CSM workflow as a public-signal feed. Doesn't replace the CSM call cadence; informs it. Durable, but narrow — it operates on a fixed customer roster, so it can't expand by opening new funnels. |
| Problem severity | **Moderate.** Logo churn shows up in board packs, so there's executive interest, but churn risk is best detected through usage signals (which Qapita already owns internally) — public signals (layoffs, down rounds, CFO departures) are noisy lagging indicators. CSM teams typically already have a watch process. |
| Demo quality | **Moderate (7.5/10).** Mostly amber/green status tiles. Hard to make visually exciting. The "alert when red" mock is the strongest screen, but it's a single event. Five minutes of dashboard = dashboard fatigue. |
| Value to Jax | **Moderate.** Jax cares about the SEA logos specifically; the public signals on SEA private companies are *weaker* than on Indian unicorns (less public news, less Glassdoor, less press). So the SEA cut — the one that matters to him — is the data-thinnest cut of the tool. |

**Cut reason:** The two structural problems are (a) Qapita's own internal product usage signals are a stronger churn predictor than any public scrape, which makes the tool look like a worse version of what their data team should already be building; and (b) CSM is not Jax's team. Jax sells in, the CSM team retains. Demoing a CSM-team tool to a Head-of-SEA / Founders'-Office leader puts the value in someone else's mouth. He nods politely, he doesn't lean in.

**Remaining: 1, 2.**

---

## Round 4 — the final pair, head-to-head

Now between **Idea 1 (SEA Pipeline Radar)** and **Idea 2 (M&A Target Scanner)**. Both pass each prior round; both have real Jax-shaped value.

| Criterion | Idea 1 — SEA Pipeline Radar | Idea 2 — M&A Target Scanner |
|---|---|---|
| **Scalability** | **High — durable.** Phase 1 public scrapers, Phase 2 internal-data plug-in, Phase 3 mirrors to India and US. Becomes SEA BD's operating dashboard, then three-region BD infra inside Qapita. Direct path to "Qapita's internal lead engine." | **Moderate–high.** Becomes the corp-dev pipeline tracker. Useful but sparse — Qapita does ~4 acquisitions/year max. The tool runs weekly but produces meaningful output a handful of times per year. Plateaus as "FO deal-memo generator." |
| **Problem severity** | **High and recurring.** SEA is 20% of revenue today and growing toward 30-40%. Every newly-funded SEA startup is a potential customer; Qapita's SEA BD currently reads e27/DealStreetAsia ad-hoc and misses meaningful leads. The pain is **every week, in Jax's actual P&L.** | **High per instance, sparse in frequency.** Each M&A diligence cycle eats 2-3 weeks of desktop research; the tool could save half of that. But the cycle fires 4× a year, not 4× a month. Real pain, infrequent pain. |
| **Demo quality** | **Excellent (9.5/10).** Monday-morning HTML digest with 20 ranked leads on real news from real SEA startups + per-company drilldown + Bark alert mock. Five minutes tells a complete story: "this is what your desk wakes up to every Monday." Visually concrete. | **Strong (8/10).** Ranked target list + per-target desktop-research page + exportable deal memo. Photogenic but heavier — the demo has to explain "you don't run M&A every Monday" before the value lands. Mentally taxes the room. |
| **Value to Jax personally** | **Direct.** SEA lead gen is **his revenue line**. The tool surfaces deals he himself would close or hand to his BD team. The morning-digest shape is the operating rhythm of his actual job. | **Indirect.** Founders' Office runs corp-dev, but the M&A decisions are CEO-driven. Jax is a stakeholder on M&A; he is the **owner** on SEA pipeline. The tool's value lives in someone else's calendar. |

**Honest tiebreaker:** Recurrence vs sparseness.
- **#1 generates output every Monday morning.** The demo says "every Monday for the rest of your career, this is the first thing you read." That sentence buys a hire.
- **#2 generates output every 8-12 weeks.** The demo says "when we do the next Punch, this saves you two weeks." Powerful, but episodic. The demo has to do the imaginative work of projecting forward to an event that hasn't been scheduled.

Recurrence wins. The Wego Earnings Digest / Qatalyst Sentinel / Tender Radar precedent shape Jax can picture without you explaining is the **daily intelligence feed**, not the **periodic deal-memo assembler**.

---

## Round 5 — should we combine?

The Olesia track combined two ideas because *neither one alone* matched the morning-digest precedent. Here, **Idea 1 already matches it perfectly.** Bolting Idea 2 onto Idea 1 has costs:

**Pros of combination:**
- Doubles the surface area — one tool covers both lead-gen and corp-dev.
- Reuses the same scoring engine + digest renderer + Bark integration; the marginal build cost is small (~1.5 extra days).
- Hedges if Jax pushes on M&A in the interview — you have a second drawer to open.

**Cons of combination:**
- **Dilutes the punchline.** "This is the SEA leads tool" is a sharper sentence than "this is the SEA intelligence brief covering leads and acquisitions."
- Sparse output from the M&A module (a few candidates per quarter) sitting next to dense output from the leads module (10–20 candidates per week) makes the M&A side look thin in the live demo.
- Adds a second rubric and a second data-source set during the 5–7 day build window. The scope risk is real even if the marginal code is small.
- Risks signalling that you don't trust Idea 1 alone — adding M&A reads as compensating for a weak core.

**Verdict on combination:** **Don't bundle them in v1.** Build Idea 1 clean. Mention Idea 2 verbally as a Phase-2 extension — "the same scoring engine runs against an acquireability rubric for corp-dev when M&A cadence picks up." That sentence preserves the optionality without paying the cost.

There is one exception: if the elimination round surfaces that Jax's strongest current pain is M&A (e.g., if you learn through pre-call research that he is mid-funnel on a 2026 acquisition right now), then flip — build Idea 2 as the core, mention Idea 1 as the Phase-2 extension. Default to Idea 1 unless you have that signal.

---

## Decision

**Build: SEA Pipeline Radar (Idea 1).** Same morning-digest shape that won the Olesia interview prep — proven precedent fit. Direct hit on Jax's mandate. Recurring output. Durable scaling path. Photogenic demo.

**Discarded:**
- Round 1: #4 Competitor Pulse Memo (commodity, replicable manually)
- Round 2: #3 Investor-Update Skeleton (helps you not Jax; low ambition)
- Round 3: #5 Customer-Health Radar (wrong team, weaker signal in SEA)
- Round 4: #2 M&A Target Scanner (right value, wrong frequency)

**M&A Target Scanner survives only as a Phase-2 verbal extension** — same engine, second rubric, deferred build.

---

## Scaling Audit — does this survive if he hires me?

The question on the table: if the interview goes well and the build becomes a real 6–12 month NOC-internship project, where does SEA Pipeline Radar actually go?

### Phase 1 — Days 1–7 (pre-interview demo)

- 5 public scrapers (e27, DealStreetAsia free, KrAsia, Tech in Asia, Tech Collective)
- Rubric YAML — jurisdiction × stage × sector × lead-investor weighting
- Monday digest renderer (HTML email + HTMX drilldown pages)
- 3 fully-worked fixture entries (one each: SG / ID / VN), one Bark alert mock
- Localhost demo, polished for screen-share

### Phase 2 — Months 1–3 (early internship)

- Plug in Qapita's internal lead history → rubric weights adapt from "public-fit guess" to "patterns that have closed before"
- Replace 1–2 scrapers as Qapita's internal data sources come online (subscription to PitchBook private datasets, internal CRM hook)
- Per-lead "first-touch BD note" graduates from template to actual handoff into the CRM
- Add 2 more SEA jurisdictions to the rubric (Thailand, Vietnam) based on Indonesia's data confirming the model

### Phase 3 — Months 4–8 (scope expansion)

- **Mirror to India.** Inc42, VCCircle, YourStory feeds; India rubric; same digest shape. India is 70% of Qapita's business and this layer immediately becomes the most-read tool in the office.
- **Mirror to US.** Crunchbase free signals, Series-B-and-up funding, Schwab-program-eligible filtering. This is the Schwab-partnership growth bet given a daily operating rhythm.
- The M&A Target Scanner (Idea 2) plugs in as a second rubric on the same scoring engine — same code, second output, fires on Fridays instead of Mondays.

### Phase 4 — Months 9+ (becomes infrastructure)

- The scoring engine retires as a "lead radar" front-end and emerges as **internal scoring infrastructure** consumed by:
  - BD (the original lead digest)
  - Corp-dev (M&A target memo)
  - Marketing (which segments are converting; which content lands)
  - Strategic finance (which sectors / jurisdictions to invest sales headcount in)
- Tender Radar (from the Olesia track, if it ships) reads from the same source-of-truth list of "active issuers worth watching."

**The durable asset across phases:** the **scoring engine + digest renderer**, not the scrapers. The scrapers are throwaways and Phase 2 retires them one by one. Budget the 7-day build accordingly — under-engineer the scrapers, over-engineer the scoring engine and the rendering pipeline.

### The honest scaling note

Three months in, the tool's bottleneck will not be the data feeds — it will be the **rubric weights.** Whoever owns the rubric owns the tool's accuracy. If Jax hires you, the early-internship work isn't "build more scrapers"; it's **calibrate the rubric against the lead history.** That's the conversation to have in the post-call email, not in the live demo.

### The fork — if scaling matters MORE than demo-shape

If the priority were "build the most defensible long-term product" instead of "win the 30-min interview":

- **Drop the SEA-only framing. Build a three-region rubric engine from day one** with SEA as the lead instance, India and US as scaffolded-but-not-shipped modules.
- You lose some of the SEA-mandate punchline that lands the interview, but you gain a faster Phase 2 because the multi-region architecture is already there.
- This is the **wrong call for the 30-min interview** (over-scoped, dilutes the SEA story) but worth re-evaluating in week 2 of the actual internship.

### Verdict — same pick, with an explicit build budget

**Build SEA Pipeline Radar.** Single-region for the demo. Multi-region architecture only as comments + roadmap, not implemented.

**Build-budget recalibration for the 7 days:**
- ~25% on the scrapers (just enough for a live demo — they're disposable)
- ~50% on the scoring engine, the rubric YAML structure, and the unit tests around scoring (these are the durable assets)
- ~20% on the digest renderer + drilldown pages (visual polish that sells the demo)
- ~5% on the Bark integration (one push, mocked; not the headline)

**One thing to add to the post-interview email (if not raised live):**

> "Phase 2 swaps the scrapers for your internal lead history; same digest, sharper rubric. Phase 3 mirrors the engine to India and US — Schwab pipeline is the obvious third tab. The scoring engine is the durable asset; the scrapers are scaffolding."

That sentence is the bridge from 30-min demo to 6-month internship project, and it's the one Jax needs to hear to justify the hire on his SEA roadmap.
