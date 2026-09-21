# Tender Radar Pivot — 20-Candidate Deep Audit

**Context:** Surprise prototype for Olesia. No asking allowed. Previous proposals (Tender Radar, Tender Builder) both audited as wrong. This file forces breadth (20 ideas) before shortlisting.

**Five filters every candidate must clear:**
1. **Iron Rule** — does not automate the craft (pricing, deal structuring, buyer selection)
2. **Non-duplication** — does not compete with Qapita's existing product surface
3. **Real recurring pain** — solves something measurable in analyst-hours per week
4. **Not a newsletter** — does WORK, not aggregation
5. **Demo-able in 7 days** on `localhost`, photogenic, end-to-end

Plus one demo-discipline filter:
6. **Olesia-seat fit** — works for BD/Founders-Office gatekeeper-evaluator

---

## The 20 candidates

| # | Name | One-line description |
|---|---|---|
| 1 | Tender Readiness Digest | Daily HTML digest scoring roster by tender-readiness (the current `radar/`) |
| 2 | Pre-Tender Diligence Pack | 5-page internal one-pager — pool size, compliance, comparable history, risk flags, PDF |
| 3 | Tender Builder + Live Cockpit | Setup form → auto-generated offer letters + election portal + ops dashboard |
| 4 | Cap-Table Hygiene Auditor (issuer-side) | Pre-tender data-cleanup tool for issuer's messy Excel; flags inconsistencies before onboarding |
| 5 | ROFR / ROFO Coordinator | Tracks ROFR deadlines across active deals; generates notice packets |
| 6 | Cross-Border Tax Withholding Calculator | Per-holder TDS / FATCA / DTAA pre-calc for any tender |
| 7 | Secondary Pricing Benchmarker | Scrapes unlisted prices + comps; recommends price band |
| 8 | **DRHP-to-Cap-Table Reader + Tender Preview** | Upload public DRHP/RHP PDF → extract cap-table → run mechanics preview |
| 9 | Founder Liquidity Forecaster | Models when founders' lock-ups expire; predicts liquidity demand timing |
| 10 | ESOP Cliff Wave Forecaster | Hire-date distribution → predicts vested-ESOP cliff-event volumes 12mo out |
| 11 | Marketplace Buyer-Sentiment Tracker | Public scrape of secondary funds' announced raises / sector preferences |
| 12 | Tender Outcome Backtester | Backtests scoring rules against Qapita's 35 public tenders to validate prediction logic |
| 13 | Issuer Health Watchlist (Sentinel) | Cross-roster distress signals — down rounds, layoffs, CFO turnover, regulator probes |
| 14 | Acquihire vs Tender Predictor | Scores a stressed issuer's likely outcome path |
| 15 | Schwab Cross-Sell Pipeline Builder | Identifies Qapita issuers with US shareholder mix worth Schwab handoff |
| 16 | SEA Re-Domiciliation Risk Tracker | SEA cos flipping to Singapore for IPO/secondary; cap-table implications |
| 17 | NRI Holder Compliance Heatmap | Issuer geo-holder mix → predicts FC-TRS / FATCA load before launch |
| 18 | Punch Financial Integration Mapper | Maps which Qapita customers benefit from Punch's fund-admin overlay (post-Oct'25 acq) |
| 19 | Tender Window Calendar | Visualizes ideal launch windows — blackouts, vesting cliffs, holidays, filings |
| 20 | Comparable Transaction Database | Searchable structured DB of public secondary deals (Razorpay 2022, Swiggy, etc.) |

---

## Round 1 — kill the obvious failures (8 cuts)

| # | Killed because |
|---|---|
| 1 | **Newsletter.** User just demolished this. |
| 3 | **Duplicates Qapita's tender admin product** (`$250M+ unlocked, 35+ programs` is their own marketing). Iron Rule violation on auto-generated SPAs. |
| 5 | **Already cut in original elimination** — demo is empty without a live deal pipeline. |
| 7 | **Iron Rule violation** — recommends pricing. |
| 11 | **Newsletter-flavored.** Aggregates public statements. No work being done. |
| 12 | **Internal validation tool**, not a product. Not photogenic. Would land as "I QA'd a model nobody has." |
| 14 | **Iron Rule borderline** — predicts strategic outcomes. Plus thin signal density on public data. |
| 20 | **Commodity** — Tracxn / Pitchbook already do this at enterprise scale. Building a worse version doesn't impress. |

**Remaining: 12.**

---

## Round 2 — narrow on Olesia-seat fit + novelty (5 more cuts)

| # | Killed because |
|---|---|
| 4 | **Adjacent to the Evelyn build** (cap-table reconciler). Risk of looking like I built the same thing twice. |
| 6 | **Too narrow.** Tax counsel still has to validate every output, so the time-saving claim doesn't hold. Better as a sub-feature of something bigger. |
| 9 | **Speculative outputs.** Founder lock-up timing is contractual + private; my version would be public-data inference, easy to challenge. |
| 10 | **Narrow.** Single-variable forecaster. Useful but visually thin — a chart per issuer. Hard to demo "wow." |
| 18 | **Punch acquisition is too recent** (Oct 2025). Internal integration mapping requires Qapita's own data we don't have. |

**Remaining: 7.**

---

## Round 3 — final-pair audit (drop 5 more)

Survivors so far: **#2, #8, #13, #15, #16, #17, #19**. Audit each against the 6 filters.

| # | Iron Rule | Non-duplication | Real pain | Not newsletter | Demo-able | Olesia-fit | Net |
|---|---|---|---|---|---|---|---|
| 2 Pre-Tender Diligence | ★★ borderline (risk flags = judgment) | ★★★ | ★★★ analyst time real | ★★★ | ★★ photogenic | ★★ analyst not BD | **strong but compromised** |
| **8 DRHP Reader** | **★★★ pure extraction** | **★★★ no Qapita overlap** | **★★★ ~200 hrs/yr** | **★★★ does the reading** | **★★★ upload→table** | **★★★ sourcing = BD** | **★★★★★** |
| 13 Issuer Health Sentinel | ★★★ | ★★★ | ★★ medium | ★ aggregation-shaped | ★★ dashboard | ★★ | **mid** |
| 15 Schwab Cross-Sell | ★★★ | ★★★ | ★★ medium-strategic | ★★★ | ★★ slide-deck-y | ★★★ Series-B aligned | **strong** |
| 16 SEA Re-Domicile | ★★★ | ★★★ | ★ niche | ★★★ | ★ thin | ★★★ Singapore | **niche** |
| 17 NRI Heatmap | ★★★ | ★★★ | ★★ India-only | ★★ ranking-shaped | ★★ medium | ★★ India-flavored | **mid** |
| 19 Tender Window Calendar | ★★★ | ★★★ | ★★ scheduling | ★★★ | ★ thin | ★★ | **mid** |

**Killed in Round 3:** #2, #13, #16, #17, #19 — each has a single ★ on a critical filter.

**Final pair: #8 vs #15.**

---

## Round 4 — head-to-head

| Dimension | #8 DRHP Reader + Tender Preview | #15 Schwab Cross-Sell Pipeline |
|---|---|---|
| **Source novelty** | DRHPs (60+ page legal PDFs) — **HARD to read manually**, no competitor parses them | Public + Qapita-internal data (we'd fake the Qapita side) |
| **What it produces** | Structured cap-table from public filing + mechanics preview using my existing engine | Ranked list of cross-sell candidates with rationale |
| **The work it saves** | ~200 analyst-hours/year reading new DRHPs | Strategic BD prioritization — episodic, not recurring |
| **Demo strength** | **Upload a real Pine Labs DRHP → 30 sec later → cap-table table + $20M-tender preview**. Live, undeniable. | A ranked dashboard. Less visceral. |
| **Engine reuse** | **Wires straight into existing `mechanics.py` + `compliance.py`** — the strongest part of what I already built survives | Engines barely used |
| **Iron Rule** | Pure extraction, no judgment | Borderline — "who to cross-sell" is a BD judgment |
| **Olesia BD-fit** | Sourcing tool = pre-relationship work = founders-office territory | Founders-office strategic mapping = also founders-office |
| **Schwab narrative** | Generalizes from DRHP (India) to S-1 (US) — Schwab story carries over | Directly Schwab-aligned |
| **Risk** | DRHP layouts vary — fragile parsing | Need fake Qapita-internal data to demo, less honest |
| **Wedge against incumbents** | Hiive/Forge/Carta can't do this (no DRHP context). Tracxn/Pitchbook don't extract cap-tables from DRHPs. **Real gap.** | Closer to standard BD enablement; less defensible wedge |
| **What survives post-hire** | Internalized: DRHP reader becomes a prospect-funnel tool the desk uses ahead of every Indian/SEA IPO filing. **Durable.** | More of a one-time analysis exercise |

**#8 wins on 8 of 10 dimensions.**

---

## Why #8 is the recommendation — the honest sentence

**Today, when Pine Labs, Urban Company, or Razorpay files a DRHP, Qapita's secondaries desk reads 60+ page legal PDFs by hand to estimate whether the issuer is a viable tender target, what their cap-table looks like, and what a hypothetical $20M tender would yield. That's ~3–5 analyst-hours per filing, ~50 relevant filings per year — call it 200+ hours of repetitive PDF-reading. A tool that ingests the DRHP and outputs (a) a structured cap-table, (b) a mechanics preview against my existing engines, and (c) flagged compliance considerations turns 4 hours into 30 seconds.**

### Why this isn't another wrong path

- **Iron Rule clean:** pure extraction + descriptive math. No pricing, no buyer match, no deal structuring.
- **Doesn't duplicate Qapita's product:** Qapita serves *companies that are already customers*. This serves the **prospect funnel** — pre-customer intelligence. Different surface.
- **Not a newsletter:** the tool *does the reading*. The analyst was the bottleneck; the tool removes them.
- **Demo-able in 7 days:** Python has `pdfplumber` for table extraction; section parsing is regex + heuristics. Demo with 3 hand-curated DRHPs (Razorpay, Pine Labs, Urban Company — all already in our fixtures). Graceful fallback for unsupported layouts.
- **Olesia BD-fit:** sourcing tools live in Founders Office. The pitch is *"when a hot DRHP drops on Monday morning, can the desk have a structured view by the 9am SEA call?"* That's exactly what a BD-flavored founders-office associate cares about.
- **Engine survival:** my existing `mechanics.py` + `compliance.py` + `models.py` + `stamp_duty.py` + CSS + base template — **all reused.** The DRHP reader is a NEW input pipeline that feeds the SAME engines.
- **Strategic alignment:** DRHP-extraction generalizes to S-1 extraction. Schwab Series B is about US private-market expansion. The tool's roadmap reads: "today DRHPs, tomorrow S-1s for the Schwab funnel."

### What gets thrown away

From `radar/`:
- `scoring.py`, `scoring_config.py` (the digest scoring concept)
- `digest.py`, `bark.py`, `orchestrator.py` (newsletter mechanics)
- All 5 scrapers under `scrapers/` (no more public-news scraping)
- `templates/digest.html.j2`, `templates/history.html.j2`
- `scripts/bake_cache.py`, `scripts/seed_history.py`

What stays:
- `models.py` (extended with `ParsedDRHP`, `ExtractedCapTable`)
- `db.py` (slightly different schema)
- `matching.py` (still useful for fuzzy-matching issuer names in DRHP filings)
- `mechanics.py`, `compliance.py`, `stamp_duty.py` — the durable engines
- `templates/base.html.j2`, `_preview.html.j2`, `issuer.html.j2` (now becomes `filing.html.j2`)
- `static/styles.css`
- 15-issuer + 6,508-holder fixtures (used to demo "what if we already had the cap table, here's the comparison")
- All 13 tests still pass on the engines

Roughly **60% of code survives**, ~40% replaced.

### Build budget (4-5 days new work)

| Day | Output |
|---|---|
| 1 | Find + hand-curate 3 real DRHPs (Razorpay, Pine Labs, Urban Company), put under `data/drhp/`; build `radar/drhp_parser.py` (pdfplumber + section regex); golden-file tests |
| 2 | Extend `models.py` (`ParsedDRHP`, `ExtractedCapTable`); upload route + DRHP processing pipeline; basic results page |
| 3 | Wire extracted cap table into existing `mechanics.preview_tender` — "if a $20M tender ran on this DRHP-filer's cap table, here's what it would look like" |
| 4 | Compliance preview from extracted geo data + issuer state (auto-detected from DRHP); risk flags surfaced as warnings, not predictions |
| 5 | Visual polish; 3-DRHP demo loop; Q&A update; 2 dry runs |

### Demo opening line

> "When Pine Labs filed their DRHP in December, your team spent — what, three hours? four? — reading 60 pages of legal text to figure out what a tender on Pine Labs would look like, before deciding whether to even pick up the phone. This tool reads it in 30 seconds. Watch."

[Upload Pine Labs DRHP] → [30 seconds of progress UI] → [structured cap table] → [slider: tender size = $20M] → [waterfall + compliance preview, same engines you saw earlier].

That's the demo. It's not a newsletter. It's not a duplicate of their product. It does the work an analyst would otherwise do by hand. And it survives every audit I can throw at it.

---

## Decision

**Build #8 — DRHP-to-Cap-Table Reader + Tender Preview.**

Discard: Tender Radar in current form (scrapers, scoring engine, digest, history, Bark). Keep: mechanics, compliance, stamp duty, models, DB, matching, CSS, base template, fixtures, tests.

This is the recommendation I'd defend across all six filters without rationalizing.
