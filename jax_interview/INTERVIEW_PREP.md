# Jax Interview — Talking Points, Q-list, Pitfalls, Pre-Call Checklist

## 0. The 30-second positioning

**Who you are, in one breath:**
> "Final-year NUS-adjacent track, NOC inbound for Aug 2026. I've been prepping the Qapita interview track for the last two weeks — built a Flask cap-table reconciler against the Valuations team's hygiene problem, scoped a tender-readiness intelligence tool against the secondaries desk's morning workflow. For Founders' Office I want to ship a SEA Pipeline Radar — a Monday digest that scores every SEA funding announcement against a Qapita-fit rubric. I have a live `localhost` demo. Can I screen-share for three minutes after we cover the basics?"

That sentence does five things at once: (1) signals you treated each interview as its own problem; (2) shows you ship, not just talk; (3) names SEA explicitly because that's his mandate; (4) preempts the "show me what you can do" beat; (5) puts you in driver's seat for the technical chunk.

## 1. Three things to lead with (in this order)

1. **NOC ↔ NOC.** Acknowledge the symmetry without flattery. "You ran NOC NY 2018; I'm inbound for Aug 2026. The arc is the reason I'm here." Done. Don't dwell.
2. **The SEA-mandate read.** Show you know Qapita's geo split, that SEA is 20% and the growth lever, and that Indonesia is the live edge. He will relax 90 seconds into the call once he hears you know what business he's running.
3. **A buildable demo, not a deck.** Screen-share within the first 10 minutes if he'll let you.

## 2. Things to absolutely avoid

| Avoid | Why |
|---|---|
| Repeating "Schwab is the growth bet" back to him | He lives it. You're not informing him; you're sounding like the marketing site. |
| Pitching AI-priced anything | Same rule as Olesia and Evelyn — never automate the craft. |
| Performing valuation knowledge | He is ACVA. Stay descriptive. |
| Calling Qapita "a Carta competitor" | Internal narrative is "we already own the cap table; Carta is the US footprint comparison, not the wedge." Use "the SEA-native, full-stack equity rail" instead. |
| Asking about salary, intern stipend, conversion to FT | NOC inbound is a fixed-shape program; salary is set by the NOC contract, not by him. Wrong forum. |
| Telling him the Punch acquisition was "interesting" | Use it as evidence of an inference — "Punch tells me corp-dev is a real funnel in FO; here's the M&A scanner idea I sketched against it." |
| Claiming you "know the SEA market" | You don't yet. Claim instead: "Here are the five SEA-startup news sources I read every morning, and here's a tool I built to digest them." |
| Saying you want to learn — and stopping there | Every NOC candidate says this. Differentiate: name the *thing you want to ship* in the first six months. |
| Recapping his LinkedIn at him | He knows his own bio. Cite one detail (ACVA, NOC NY, Indonesia hiring) only if it's load-bearing for your point. |

## 3. The five questions to ask him (last 5 minutes of the call)

Order matters. Ask top-down; if he runs short on time, the top two are the only must-asks.

1. **"What does the Founders' Office actually look like in the SEA office vs the India office? Where does Singapore-FO end and the India team begin on a project like Punch?"**
   — Signals you understand FO is a function, not a team, and that the SEA / India split has real seams. His answer tells you whether he runs corp-dev solo or via the India bench.

2. **"After Punch, where's the next acquisition lens pointing — more US fund-admin, or SEA corp-sec / virtual-CFO?"**
   — High-stakes question, intentionally. If he answers, you've learned where to point Idea 2. If he deflects, you've signaled M&A literacy without forcing him to share anything he can't.

3. **"What's the biggest hole in Qapita's SEA GTM right now — is it the brand, the regulatory rails (Indonesia OJK, Vietnam), or the customer-acquisition cost in markets without Schwab-equivalent distribution?"**
   — Hard, real question. Answer signals where a hire would actually leverage. His answer points you at where the SEA Pipeline Radar's rubric weights should sit.

4. **"How does FO prioritize the standing-investor-update cadence vs ad-hoc strategic projects? Is there a formal calendar or is it CEO-pull?"**
   — Tests the FO operating model. Tells you whether the Investor-Update Skeleton (Idea 3) is even relevant.

5. **"For an inbound NOC who proves out in the first three months — what does month 4 onward look like? Is there a defined 'second project' or is it situational?"**
   — Says you're thinking about the 6-month arc, not the 30-min interview.

## 4. Questions to skip (even though they're obvious)

- "What's the company culture like?" — generic, low-signal, his job is not to sell you the culture.
- "What does success look like in this role?" — same problem; ask instead about *what gets shipped*.
- "Why did Qapita acquire Punch?" — readable from the press release; asking exposes you didn't read it.
- "Who's the biggest competitor?" — he'll say Carta, you'll learn nothing.

## 5. Pre-call checklist (24 hours before)

- [ ] **Demo runs cold on `localhost`.** Cold-start with `python app.py` (or whichever entrypoint), see the digest render, walk through one drilldown — within 60 seconds. If it takes longer, fix it the night before.
- [ ] **Three worked-example fixtures loaded.** Each fixture is a different SEA country so the demo visually proves the geo-coverage claim. (If you can only ship one fixture: make it Indonesia.)
- [ ] **Backup screenshot deck.** A 6-slide PDF of the demo screens. Not for the call — for the email you send after, so the artifact survives if the live demo flakes.
- [ ] **One-page resume re-tailored.** Lead with the Qapita interview-track work and the cap-table reconciler build. Bury anything off-thesis.
- [ ] **Calendar joined, Calendly link archived.** Confirm the timezone (SGT vs IST vs America). The reschedule link is the screenshot — keep that thread.
- [ ] **Phone on silent, laptop charged, second screen for notes** with the four files: `JAX_RESEARCH.md`, `AUTOMATION_5.md`, this file, and the `OLESIA_RESEARCH.md` (so you can answer "how is this different from what you'd build for Olesia" if it comes up).
- [ ] **The 30-second positioning rehearsed once aloud.** Once. Don't over-rehearse it into stiffness.
- [ ] **One closing line drafted** ("If you've got 60 seconds left I'd love to show you the Monday digest the tool would have generated for you this week — three of the top five hits are companies in your roster's adjacency."). Use only if there's time.

## 6. Day-of cadence (30 min)

| Minute | What's happening |
|---|---|
| 0–3 | Pleasantries, NOC reciprocity beat, you reframe as "I want to walk you through what I've been building" |
| 3–13 | Demo + scaling story (Phase 1/2/3 from `AUTOMATION_5.md` recommendation) |
| 13–22 | His questions — Q1 (why Qapita), Q2 (why FO), Q3 (what would you build), Q4 (biggest risk), Q5 (Python/SQL) — anticipated answers in `JAX_RESEARCH.md` Part 6 |
| 22–28 | Your questions (top 2 from §3 above are must-ask; 3–5 if time) |
| 28–30 | Next steps, follow-up artifact promise (the screenshot deck + repo link), thank-you, end |

## 7. The post-call email (send within 4 hours)

Subject: **NOC inbound — SEA Pipeline Radar repo + screenshots**

> Jax —
>
> Thanks for the 30 minutes. As promised: the repo for the SEA Pipeline Radar demo lives at [link or attachment], and the six screens are attached as a PDF for skim-reading. The Monday digest output (synthetic but realistically shaped — five real announcements from last week scored against the rubric) is the third PDF.
>
> Two things I want to flag from our conversation:
> 1. [One specific takeaway from his answer to your Q3 about SEA-GTM hole]
> 2. [One specific extension you'll add — e.g., "I'll wire the Indonesia OJK rule check into the per-company drilldown by end of week as a stretch."]
>
> Happy to walk through the code with anyone on the SEA team when convenient. NOC start window is Aug 2026; happy to send my coursework / timing detail separately if that's useful.
>
> — [user]

The email is a contract: it says you do what you said, plus one stretch you decided on after the call. That's the kind of post-call follow-through Jax's own NOC supervisor likely got from him in NY 2018.

## 8. If something goes wrong

| Scenario | Response |
|---|---|
| Demo crashes on screen-share | "Let me cut to the screenshot deck — same content, less drama." Move on. Recover speed beats heroics. |
| He says "we already have something like this internally" | Pivot: "What does yours optimize for that public sources miss?" Genuine curiosity; you might learn the actual gap. |
| He says "this isn't what FO does, FO is more X" | "Got it. Two of my five sketches lean X — [name them]; want me to walk those instead?" Idea 2 / 3 / 5 are the pivot options. |
| He asks something you don't know (an Indonesia OJK rule, a specific named SEA fund's portfolio) | "I don't know; let me write that down and send you the answer in the follow-up." Don't bluff. |
| Time runs short and you don't get the demo in | The post-call email is the demo. Make the screenshot deck do the work. |
| He's distracted / clearly multitasking | Cut to the most concrete claim you have, fast: "Here are the three companies on this week's Monday digest that fit Qapita's wedge but aren't customers yet." Concrete > clever. |

## 9. After the call

- Add a `JAX_DEBRIEF.md` in this folder within 24h: what he asked, what surprised you, what to update in the rubric / `AUTOMATION_5.md` based on his answers.
- Update `~/.claude/projects/-Users-subhankarshukla/memory/project_qapita_interview.md` with the Jax interview line so future sessions know this happened.
- If invited to a second round: re-read his answer to Q3 (SEA GTM hole) before scoping the round-two build.

## 10. The thing to remember when nervous

Two prior Qapita interviewers (Evelyn, Olesia) have already validated the *shape* of your approach: a workflow tool built to a specific desk's morning rhythm, no automation of the craft. Jax is the third instance of the same conversation in a different seat. **You have already had this conversation twice, in writing, with two of his colleagues.** Walk in with that confidence.
