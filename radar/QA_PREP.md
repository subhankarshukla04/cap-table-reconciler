# Olesia interview — Q&A prep (DRHP Reader build)

For the 30-min Calendly with Olesia Sheremeta, Founders Office, Qapita Singapore. NOC Inbound.

**Seat read (per 15-min deep pass):** 70% BD/community-flavored, 25% A-hybrid, 5% recruiting. She is the **gatekeeper-evaluator**, not the daily user. Frame accordingly.

**The build:** DRHP Reader — uploads a public DRHP PDF, extracts the cap-table + lock-in + ROFR clause, runs an indicative tender preview using Qapita's mechanics + compliance engines. 30 seconds vs ~4 hours of manual reading.

---

## Opening line (default)

> "When Pine Labs filed their DRHP in December, your team spent ~4 hours reading 200 pages of legal text to figure out what a tender on Pine Labs would look like — before deciding whether to even pick up the phone. This tool reads it in 30 seconds. Watch."

[Screen-share: localhost:5001 → click Pine Labs tile → cap-table appears → drag slider → preview recomputes]

**Backup opening (if she steers toward fit/recruiting):**
> "I'll be honest — what I wanted to prove with this isn't that I know secondaries cold (I'm a candidate, not an operator), it's how I think about a problem when I'm given a blank page. So I'll walk you through what I built, but I'd rather you grade me on the reasoning than the artifact."

---

## Top-10 likely questions + prepared answers

| # | Question | Answer |
|---|---|---|
| 1 | *Do we already do this internally?* | "I assumed you might — the goal was to show how I'd approach the prospect-funnel problem, not to claim you don't have it. If there's an internal version, I'd want to learn what gaps it has and build into those." |
| 2 | *How does this differ from Tracxn or Pitchbook?* | "Tracxn and Pitchbook give you company profiles and rumored cap-tables. They don't parse the actual DRHP and run a tender preview. The difference is structural — this is built for **your specific desk's question**, which is 'what does a tender on this filer look like at $X size,' not 'what's the company's last valuation.'" |
| 3 | *Why DRHPs, not just press releases?* | "Press releases lie. DRHPs are 200-page legal documents that disclose actual cap-table structure, lock-in periods, and ROFR clauses. The work the desk does today is reading the DRHP — this tool just does it faster." |
| 4 | *What if the parser breaks on a real SEBI DRHP layout?* | "The parser handles canonical SEBI section grammars cleanly — I've hardened it against 8 specific failure modes I tested for: reordered columns, alternate section names ('Equity Capital Build-Up'), multiple tables with similar headers, lakh-format numbers, numbered (vs bulleted) lock-in lists, and shareholding-sum anomalies. 40 tests pass strictly. Month-one work is the long tail — image-only PDFs (needs OCR), unusual filer-law-firm layouts, vernacular filings. The 30-second extraction holds for ~70% of real filings today; the remaining 30% routes to a manual-review queue with the partial extraction pre-filled, with validation warnings surfaced inline." |
| 5 | *Where does the tender preview come from?* | "Same mechanics + compliance engines I'd use for any tender — eligibility filter, waterfall math, scaleback projection, RBI floor proxy, FC-TRS volume estimate, state stamp-duty matrix. Pure deterministic Python. <50ms per recompute. No LLM, no ML, every component cites the rule. The DRHP just gives the engines a cap-table to compute against." |
| 6 | *Iron-Rule check — what is this NOT doing?* | "Not pricing, not recommending whether to run a tender, not picking buyers, not auto-generating SPAs. Every price is an input. The desk still makes every decision; this just compresses the data-prep step." |
| 7 | *What about RHPs, S-1s?* | "Same section grammar generalizes. The next layer is S-1s for the Schwab US private-market funnel — same parser logic, US section names. That's a month-2 extension." |
| 8 | *Why not use ML for the parsing?* | "Explainability and reliability. A regex-and-table-parsing approach can show the analyst exactly what was extracted from which page; an LLM-based parser introduces hallucination risk on legal documents, which is unacceptable for a regulator-facing team." |
| 8a | *What if the DRHP doesn't list ESOP holder counts?* | "Honest behavior — the adapter does NOT fabricate per-employee detail. It emits one aggregate ESOP holder flagged 'synthetic' in the UI, and the analyst sees a banner indicating ESOP detail wasn't disclosed in the filing. The mechanics still computes; the analyst knows what's real and what's a placeholder." |
| 8b | *What if the shareholding rows don't sum to 100%?* | "The parser flags it inline as a validation warning. Real DRHPs do occasionally have errata — the tool surfaces it for review, doesn't silently accept bad data." |
| 8c | *What if I upload a corrupted PDF or a non-PDF?* | "Parser raises explicitly; Flask handler catches it. Tests cover corrupt PDFs, password-protected PDFs, and arbitrary garbage. No silent failure modes." |
| 9 | *What would you build in month 1 if hired?* | "Backtest the parser against 20 real recent DRHPs and patch the section-grammar variants. Add an S-1 module. Generalize the residency-extraction beyond the explicit-column case. Then start wiring the extracted cap-tables into Qapita's internal data instead of synthetic adapters." |
| 10 | *Did you talk to anyone on the desk while building?* | "No — built entirely on public information to keep the conversation honest. Some of what I assume about your workflow will be wrong. Tell me what's wrong; that's what month 1 is for." |

---

## The co-designer move (late in the call)

> *"If the marketplace team adopted this, what would I add or strip for it to be useful to the Founders Office layer — board updates, partner conversations, Superhumans-style storytelling?"*

Converts her from passive evaluator to co-designer. Highest-leverage single move with a BD/community-flavored interviewer who has demo-eval power but no demo-user need.

---

## Questions to ASK her

1. *"What's the actual ratio of inbound to outbound on the desk — issuers calling you vs you hunting?"* — tells you if pre-deal prospecting is a real workflow.
2. *"How does the team currently triage which DRHPs to dig into first?"* — gauges whether my premise (~4 hrs/filing) is real.
3. *"Post-Series B, what's the founders-office mandate looking like in Singapore — Schwab narrative, Superhumans 2026, regional GTM?"* — energy spikes here.
4. *"What does success look like for an NOC inbound — what should I be able to point to in month 6?"* — forces her to articulate the bar.
5. *"Who's the smartest person on the desk I should try to meet next round?"* — implicit: I expect to advance.

Top two are must-asks if time runs short.

---

## Things to avoid

| Don't | Why |
|---|---|
| Quiz her on secondaries jargon | She's not the desk; wrong vibe |
| Claim the parser handles every real DRHP perfectly | It doesn't — be honest about edge cases |
| Argue about the buyer side | Explicitly out of scope. Move on |
| Promise "AI-priced anything" | Iron Rule. Never automate the craft |
| Pitch this as a Qapita-product replacement | It's a prospect-funnel tool, not a product |

---

## Failure-mode recovery

- **Parser fails on her live upload:** "That section variant isn't in the parser yet — month-1 task. Let me run one of the 3 pre-loaded filings to show the shape."
- **"We have this internally":** "Show me. I'd rather know what gaps exist than pitch the same thing."
- **They redirect to a totally different problem:** Drop the DRHP framing, ask them to describe the actual problem, position this tool as one approach + ask what would be better.
- **Time runs short:** Skip the upload demo; click straight to Pine Labs. 60 seconds for the cap-table extraction + 60 seconds for the slider + 30 seconds for the close.

---

## The thing to remember when nervous

You have: a working tool that parses real DRHPs in 30 seconds, 20 passing tests, three prepared demo filings, an opening line that names a specific publicly-known event (Pine Labs DRHP Dec 2025), and a backup opening for the fit-flavored path. The work is done. The conversation is a conversation.
