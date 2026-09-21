# Qapita Interview #2 — Olesia Sheremeta (Secondaries / Founders Office)

**Date compiled:** 2026-05-11
**Interview:** 30-min Calendly with Olesia Sheremeta (olesia.sheremeta@qapita.com)
**Calendar tag:** "Company: NOC" / "NOC interview for Qapita"
**Likely start:** Aug 2026
**This file is interview #2.** Evelyn Tay prep (Valuations team, Cap Table Reconciler build) is unchanged in `CONTEXT.md` / `PLAN.md` / `app.py`. **Do not conflate.** Different team, different role, different pitch.

---

## TL;DR — what changed vs the Evelyn interview

| | Evelyn Tay (last interview) | Olesia Sheremeta (this interview) |
|---|---|---|
| Team | International Valuations + Financial Reporting | Founders Office / Secondaries (Qapita Marketplace) |
| Base | Singapore | Singapore |
| Hiring track | Full-time analyst seat | **NOC Inbound — NUS Overseas Colleges generalist internship, Aug 2026** |
| Craft they protect | "Expert-led, not algorithm-only" valuation | Issuer-led liquidity programs, India regulatory depth |
| Build resonance | Audit-grade deterministic, zero valuation judgments | Workflow/compliance plumbing, zero pricing judgments |
| Don't pitch | Automated 409A / Backsolve | Hiive-style open marketplace / "AI-priced" secondaries |

The shared rule: **never automate the part the team is paid to do.** Automate the boring scaffolding around it.

---

## Part 1 — Olesia, the person

- **Role:** Founders Office, Qapita Singapore. Generalist / BD-flavored.
- **Background:** Yale-NUS College. Director of Business Affairs, Yale-NUS Global China Connection (2018–2020). Active in Yale-NUS Women in Business. Has done M&A case-comp work and portfolio-company exit analysis (likely a prior VC/PE intern stint).
- **Public footprint:** Contact face at SXSW Sydney + Qapita × Fintech Nation "Superhumans of Fintech 2025" book launch. No own podcasts / panels / Substack — she's operator, not thought leader.
- **Heritage signal:** Ukrainian/Russian-language name; this is irrelevant to the interview but useful context.
- **Why she's interviewing for NOC:** her own Yale-NUS → founders-office path mirrors the NOC inbound profile; she's running the program by being its template.

**Read for the call:** treat as a peer-ish founders-office screen, not a banking superday. Be specific about ops-and-product instincts; don't perform a valuation pitch.

---

## Part 2 — What "NOC" means

**Confirmed: NOC = NUS Overseas Colleges.** NUS's flagship year-abroad entrepreneurship program. Students spend 6–12 months at a partner startup full-time, plus entrepreneurship coursework.

- 3,600+ alumni, 1,000+ startups founded.
- **Jax Liu Jiawei** (now Head of SEA at Qapita) is an NOC NY 2018 alumnus → NOC pipeline produces real responsibility at Qapita.
- **"Inbound NOC"** = non-NUS / overseas students doing the Singapore-side internship leg. The same wording on the Qatalyst (Carbon, SC Ventures) interview confirms this is a shared inbound cohort across NOC-partner startups.

**Implication:** This is a **6–12 month founders-office internship starting Aug 2026**, sitting on or supporting the secondaries / marketplace desk. Frame ambitions accordingly — "what I'd build in 6 months" is the right unit, not "my long-term seat strategy."

---

## Part 3 — Qapita's secondaries product, in one page

**The product surface:**
1. **Tender offers** — company-led, structured liquidity events. Phases: governance → scope/eligibility → comms → acceptance → settlement → compliance. Multi-currency, multi-jurisdiction withholding.
2. **ESOP buybacks & surrenders** — company repurchases vested options/shares; sometimes surrender-then-regrant.
3. **Third-party secondaries** — early-shareholder exits to "a curated network of secondary investors, family offices, and ESOP-focused funds." **Qapita syndicates the buyer side.**
4. **Investor-driven private secondaries** — bilateral or pooled.

**Claimed scale:**
- $250M+ liquidity unlocked, 35+ structured programs, 25,000 participants.
- $185B AUM, $28B employee equity AUM, 500K stakeholders, 2,700 private cos.
- Geo split **70% India / 20% SEA / 10% US** (post-Schwab is the growth bet).
- ~SGD 8.36M annual revenue (FY ending Mar 2025).

**Named issuer clients:** Razorpay, Zepto, Ather, Acko, Boat, Pine Labs, OYO, Physics Wallah, Purplle, Rebel Foods, Spinny, The Souled Store, Urban Company, Zetwerk, Indegene.

**The differentiation, in one breath:**
- **vs Hiive / Forge:** Qapita already owns the cap table. They don't need to ingest — they originate.
- **vs Carta:** India + SEA regulatory depth (SEBI, FEMA, RBI Form FC-TRS, state-by-state stamp duty, NRI pricing-floor rules).
- **vs Trica / EquityList:** Trica explicitly *doesn't* run secondaries on platform; Qapita does.

**Pricing:** SaaS tiers $40 / $125 / Enterprise. Marketplace access is an add-on. Take-rate on secondaries is undisclosed.

---

## Part 4 — Where hours actually sink on a secondaries desk

Stage-by-stage, with the dollar-hour leverage points marked **★**:

| Stage | Hours sink? | Tool surface |
|---|---|---|
| Deal sourcing & buyer/seller match | ★ Manual lists, no canonical buyer-preferences DB | Rules-based match engine |
| Indicative pricing | Light — comp-based, fast | (skip — team's craft) |
| **Eligibility & scope** | **★★ Manual cap-table cross-ref, vesting cutoff, NRI flag** | **Eligibility + waterfall builder** |
| **KYC/AML & accredited verification** | **★★ 80% of Hiive's automation focus** | Doc-collection workflow |
| **Doc assembly (SPA, Deed of Adherence, board resolution)** | **★ Template hell + version control** | Mail-merge generator |
| **ROFR / ROFO clock + notice** | **★★ 15–30 day windows, partial-exercise edge cases** | Deadline tracker |
| Escrow & settlement | Bank-ops, hard to externalize | (skip) |
| **Tax withholding by jurisdiction** | **★ India NRI / SG / US 1099 wrinkles** | Withholding calc baked into waterfall |
| Cap-table register update | Already automated on Qapita stack | (skip) |
| **Participant comms (FAQ, election form, post-close)** | **★★ 25,000 participants — this is the screaming pain point** | Comms + election tracker |

**India-specific moat work (where no US competitor can play):**
- RBI pricing-guideline floors for resident→NRI transfers
- Form FC-TRS filing data
- State-by-state stamp duty (Maharashtra vs Karnataka vs Delhi materially different)
- SEBI's evolving frame on private-secondary transfers
- ESOP vesting + holiday-period rules under Indian SHAs

**Market sizing (the one stat to memorize):**
- Carta: VC secondary value Jul 2024–Jun 2025 = **$61.1B** > VC-backed IPO value **$58.8B**. The exit market shifted underneath public-IPO assumptions. Qapita's bet is the same thesis, India-flavored.
- Jefferies: $240B global secondaries in 2025 (+48% YoY). LP-led 52%, GP-led 48%.

---

## Part 5 — Recent Qapita news, Nov 2025 → May 2026

- **Sept–Oct 2025:** Series B, $26.5M, led by Charles Schwab. Citi + MassMutual Ventures participated. >$80M total raised.
- **Schwab Private Issuer Equity Services** — Schwab white-labels Qapita's cap-table + stock-plan + IPO-prep stack for US private cos. **This is the org's center of gravity right now.**
- **27 Oct 2025: Punch Financial acquisition** — US virtual-CFO + fund admin. Folds into Qapita's new fund-admin line.
- **9 Dec 2025: 13th Annual Conference, Mumbai.** Keynote by **Pramod Rao, former Executive Director, SEBI**, on private-secondary regulation. **Signal: Qapita is courting the regulator to shape India's secondary-transfer frame.**
- New Silicon Valley office; Pune office for 130+ team members. ~300 total HC, 9 global offices.
- No publicly-attributed Qapita-Marketplace tender deals during the window — they don't credit the platform in press, only the issuer.

---

## What's most useful for the 30 minutes, ranked

1. **NOC = 6–12 month founders-office internship, Aug 2026 start.** Frame everything as "what I'd build/own in 6 months," not "my career arc."
2. **Schwab is the center of gravity** — every answer benefits from tying back to the US-expansion thesis.
3. **The pitch is issuer-led liquidity, not Hiive-style marketplace.** Differentiation = "we already own the cap table" + "we understand India's transfer rails."
4. **The numbers:** $250M+ unlocked, 35+ programs, 25K participants, 70/20/10 India/SEA/US, Carta $61.1B > IPO $58.8B.
5. **Pramod Rao keynote signals SEBI engagement** — show you read past the marketing site.

---

# Demo ideas — 5 candidates, ranked

**Selection rules (carried over from Evelyn project):**
- Zero pricing/valuation judgments — pure workflow & hygiene.
- Audit-grade deterministic — no LLM in the calculation pipeline.
- Demo-able in 5 minutes on screen-share.
- Buildable in 4–7 days (single NOC intern's first sprint).
- Must touch a publicly-claimed scale point (25K participants, 35 programs, etc.) so the demo's relevance is obvious.

---

### 🥇 Idea 1 — Tender Offer Eligibility & Waterfall Builder

**One-line:** Upload cap table + tender terms → get a per-holder eligibility decision, max sellable units, pro-rata scaleback if oversubscribed, and withholding-tax estimates by jurisdiction.

**Inputs:**
- Messy cap table .xlsx (reuse the Evelyn fixtures — Solstice / Pelaut / Bandhan)
- Tender terms config: price, eligibility (vesting cutoff date, employee class filter, geography filter), pool size, oversubscription policy

**Outputs:**
- Per-holder: eligible Y/N with structured reason codes, max sellable units, indicative gross proceeds, indicative net-of-withholding, election-form pre-fill
- Pool view: total demand, scaleback factor, post-scaleback allocations
- Export: participant offer-letter pack (mail-merged PDFs) + master CSV for ops

**Why it lands for Olesia:**
- Hits the **25,000-participants** pain point directly.
- Extends the cap-table reconciler from interview #1 — visually proves you carry work forward, you don't restart.
- Zero pricing judgment — the price is an input, not an output.
- The withholding-tax table is the India-moat tell (NRI / resident split → RBI pricing-floor flag).

**Risks / what to watch:**
- The withholding logic is the credibility test. Get the resident-India / NRI / Singapore / US-employee combinations right, or skip the feature.
- Don't model FX conversion — leave it as "convert externally," because banks own the rate.

**Effort:** 4–5 days on top of existing repo. **Demo strength: 9/10.**

---

### 🥈 Idea 2 — FEMA / FC-TRS Pre-Check for Cross-Border Secondary Transfers

**One-line:** Input seller residency + buyer residency + share class + transfer price + valuation date → output: RBI pricing-guideline floor check, pre-filled Form FC-TRS data sheet, stamp-duty estimate by state, required-attachment checklist.

**Inputs:**
- Seller residency status (resident / NRI / foreign)
- Buyer residency status (same)
- Share class + last 409A or DCF valuation date and per-share NAV
- Transfer price per share
- State of issuer (Maharashtra / Karnataka / Delhi / TN / etc.)

**Outputs:**
- **Pricing-floor verdict:** pass / fail vs RBI fair-value floor (for resident→NRI transfers, the floor is "fair value per ICAI-prescribed method"; flag if price is below)
- **FC-TRS data sheet:** pre-filled JSON/PDF with all 30+ fields the bank needs
- **Stamp-duty estimate** by state with citation
- **Attachment checklist:** PAN, FIRC, valuation certificate, board approval, SHA waivers

**Why it lands for Olesia:**
- This is the **single feature no US secondary platform can build.** It's the India moat made tangible.
- Pure compliance plumbing — zero judgment, zero LLM, audit-grade.
- Touches Pramod Rao / SEBI keynote narrative directly.

**Risks / what to watch:**
- RBI rules update annually; cite the rule version date in the output.
- Stamp duty varies per state and per instrument type — keep the matrix narrow (5 states + 2 instrument types) for demo.

**Effort:** 3 days. Standalone Flask page; doesn't need cap-table reconciler. **Demo strength: 9/10 — but only if Olesia's desk does India deals (highly likely given 70% India mix).**

---

### 🥉 Idea 3 — ROFR/ROFO Deadline & Notification Tracker

**One-line:** Track every open Right-of-First-Refusal clock across all live secondary transactions, generate notice packets, alert on expiry, handle partial-exercise mechanics.

**Inputs:**
- Per-transaction: SHA ROFR-clause text (or structured fields: notice-period days, partial-exercise allowed Y/N, board approval required Y/N), notice-sent date, transferring shareholder, transferee, share count, price
- Per-issuer: list of ROFR-holders (typically the company + existing preferred holders)

**Outputs:**
- Dashboard: all open ROFR clocks with days-remaining, sorted by deadline
- Per-transaction: auto-generated ROFR notice (PDF), board-resolution template, post-expiry confirmation
- Partial-exercise calculator: if a ROFR-holder takes 40% of the offered lot, the remaining 60% mechanics — does the original buyer get pro-rated, or does the lot fail?
- Email/calendar export for deadline reminders

**Why it lands for Olesia:**
- Genuinely operational. An intern using this tool on day 1 saves the desk hours per week.
- Demonstrates legal/operational literacy without claiming legal authority.
- Visually thin but **functionally deep** — Olesia (founders-office, ops-flavored) will respect the leverage.

**Risks / what to watch:**
- ROFR clauses vary wildly in language; the structured-fields version is honest, the NLP-parse-the-SHA version is *not* (don't use LLM here).
- Demo will be less photogenic than #1 — fewer numbers on screen.

**Effort:** 3–4 days. **Demo strength: 7/10.**

---

### Idea 4 — Participant Comms & Election-State Tracker

**One-line:** Once a tender launches, automate the 25,000-participant comms loop: personalized offer letters → election forms → reminder cadence → post-close confirmation + tax-doc bundle.

**Inputs:**
- Eligibility output from Idea 1 (or standalone participant list)
- Comms templates (FAQ, offer letter, reminder, confirmation, tax form cover)
- Election deadline + reminder cadence

**Outputs:**
- Mail-merged offer letters per participant (PDF)
- Election portal (HTMX form per participant token, no login)
- State machine per participant: invited → opened → elected (Y/N/partial) → counter-signed → settled
- Real-time dashboard: participation rate, total tendered, breakdown by employee class / geography
- Post-close: tax-doc cover letter + (placeholder for) Form 16 / 1099 attachment

**Why it lands for Olesia:**
- The **25,000-participants** number is literally the demo's volume case.
- Founders-office / BD person sees the comms surface as the "interesting" half of a tender.
- Election-state dashboard is the most photogenic screen of any idea here.

**Risks / what to watch:**
- Without real email-send, this is a mock — the demo has to be clear about "fixture data, deterministic state machine, real SMTP swap is a 1-line change."
- Don't overshoot into building a CRM.

**Effort:** 5–6 days (the dashboard is the hard part). **Demo strength: 8/10.**

---

### Idea 5 — Buyer-Demand Match Engine (Deterministic)

**One-line:** Given a secondary lot (issuer, share class, indicative price band, size, geography), produce a ranked shortlist of buyers from a curated preferences CSV — pure rules-based scoring, no ML.

**Inputs:**
- Lot: issuer name, sector, geography, share class, indicative price band, lot size
- Buyer DB (CSV): each row = fund/family-office with ticket-size min/max, sector tags, geo tags, share-class preferences, eligibility constraints (accredited Y/N, jurisdictions allowed)

**Outputs:**
- Ranked shortlist (top 10) with explicit match scores: sector +20, geo +15, ticket fit +25, etc.
- Per-buyer outreach packet: pre-filled email template, NDA-required flag, prior-deal-count with this issuer
- Filter view: show all near-misses with the rule they failed (so the analyst can override)

**Why it lands for Olesia:**
- Codifies what an analyst already does in a spreadsheet. Operational empathy.
- Rules-based, explainable, zero black-box — fits the "expert-led" culture.

**Risks / what to watch:**
- Buyer-preferences data is private — the demo must use fully fictional buyers. Don't scrape real fund LinkedIns.
- This is the idea most easily mis-read as "the AI picks the buyer." Lead the demo with "the analyst picks; this just pre-sorts the spreadsheet."

**Effort:** 3 days. **Demo strength: 7/10 — strongest if Olesia herself does buyer-side BD (likely given founders-office role).**

---

## Recommendation — which one to build

| Idea | Demo strength | India-moat tell | Reuse Evelyn build | Effort | Pick? |
|---|---|---|---|---|---|
| 1 — Eligibility & Waterfall | 9/10 | Partial (withholding) | ★★★ | 4–5d | **Primary** |
| 2 — FEMA / FC-TRS Pre-Check | 9/10 | ★★★ | None | 3d | **Secondary — bolt-on or standalone** |
| 3 — ROFR Tracker | 7/10 | Light | Light | 3–4d | Skip for this interview |
| 4 — Comms & Election | 8/10 | Light | Partial | 5–6d | Skip — too much scope |
| 5 — Buyer Match | 7/10 | None | None | 3d | Skip — risk of "AI picks buyer" misread |

**Strongest 7-day build:** **Idea 1 as the spine + Idea 2 bolted on as a single "Cross-Border" tab.** Together they tell the full story: "I can run the participant-side mechanics of a tender, *and* I understand why India's transfer rails make Qapita uncopiable from California." That sentence is the interview.

**Opening line for the demo:**
> "This tool produces structured tender-offer mechanics and India-compliance pre-checks. It makes zero pricing judgments — the price is your input, never my output."

That mirrors the Evelyn disarming line and proves you carry the same discipline across both teams' interviews.
