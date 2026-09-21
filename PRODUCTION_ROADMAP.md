# Cap Table Reconciler — Demo to Production Roadmap

> Frozen planning doc. Written 2026-05-24, after the Qapita offer landed (NOC Aug 2026 → Dec 2026). The intent of this file: take a 5,400-LOC demo with five curated fixtures, 256 passing tests, and one honest-limit stress test — and walk it, eyes open, into being an internal tool the International Valuations practice actually runs engagements on.
>
> Not a wish list. A sequence. With the hard tradeoffs spelled out, because the failure mode for this project is not "the engine breaks" — it's "Evelyn nods politely, says thank you, and you spend six months building four other things while this never gets adopted." Adoption is the only success metric that matters.

---

## 0. The Strategic Read

### 0.1 What was actually built

| Layer | State | Honest grade |
|---|---|---|
| Pydantic data model (`src/models.py`, 262 LOC) | Locks 7 instrument types: ShareClass, LiqPref, AntiDilution, Participation, SAFE, Warrant, ConvertibleNote. Hard rules on preferred-must-have-LP, capped-LP must have one cap, seniority uniqueness | **A-** — one hard limit: pari-passu seniority rejected at the model layer |
| Excel parser (`src/parser.py`, 827 LOC) | Header-row inference, instrument-type alias map, tab-name pattern matching, date coercion, raw-vs-cleaned excerpt for the UI | **B+** — works on the five curated fixtures, degrades to a 72-warning report on the Sundar Foods holder-level stress test |
| 8-rule checklist (`src/checklist.py`, 336 LOC) | Deterministic, every finding cites `fields_referenced`, severity tiers (blocker/warning/info), stable G-codes | **B** — 8 rules is a demo; the real surface area is ~50 |
| Waterfall engine (`src/waterfall.py`, 760 LOC) | Non-participating, participating-uncapped, participating-with-cap including senior-above-capped. Regime walker, breakpoint dedupe with relative tolerance, conversion + cap-reach + pure-conversion thresholds | **A** — fuzz-tested across 23,300+ random cap tables and 10 SEA archetypes, zero invariant violations after E1/E2/E3 fixes |
| Live-formula Excel exporter (`src/formula_workbook.py`, 1,025 LOC) | IF + SUMPRODUCT against named input ranges; edit a share count in Excel, breakpoints redraw natively; verified against Python truth | **A** — this is the demo's "wow" artifact and it survives scrutiny |
| PDF intake (`src/pdf_intake.py`, 107 LOC) | pdfplumber text-PDF only; image-only returns a warning | **C** — half the Indian-deal side letters are scanned, this fails them |
| Snapshot diff (`src/diff.py`, 207 LOC) | Fuzzy class-name match across two cap-table versions | **C+** — works, but isn't yet field-level structured for auditor-grade subsequent-events memos |
| Audit memo (`src/audit_memo.py`, 252 LOC) | Markdown skeleton with `[ANALYST: ...]` judgment placeholders | **D** — Big 4 doesn't accept Markdown. Needs PDF with citations to source cells |
| Persistence (`src/persistence.py`, 262 LOC) | SQLite-backed session store, idempotent migration on startup | **C** — works for local screen-share; no auth, no tenancy, no immutability |
| Flask app (`app.py`, 1,178 LOC) | HTMX, no-cache headers, in-memory + SQLite session model | **C+** — the routing surface is fine; the app boundary is not production-shaped |
| Test suite | 256 pytest cases including fixtures, fuzz, regression | **A-** — coverage is real; production-grade CI/CD is not yet wired |

**Bottom line:** the engine room is genuine. The boat is a demo dinghy. The roadmap is about replacing the boat without breaking the engines.

### 0.2 What "production" means here — five gates

This is the load-bearing definition. Without it, "production-ready" devolves into "deploy to a server, add login," and the tool fails its real test.

1. **Data gate.** The tool must accept cap-table input from (a) client-uploaded Excel, AND (b) Qapita's own cap-table database for clients already on the platform. Without (b), the tool is permanently second-class — engagements that already have data in Qapita won't touch it.
2. **Identity gate.** Multi-tenant, multi-user, role-based (analyst / reviewer / partner / read-only auditor). Every action attributable. Session != engagement.
3. **Audit gate.** Every output traceable to a versioned rule-pack, a frozen cap-table snapshot, and a named human reviewer. Re-runnable two years later with the rule-pack and data effective on the original valuation date. This is the moat over Carta and the reason Big 4 will sign.
4. **Scale gate.** Holder-level Indian-CFO Excel (rolling up 200+ individual holders into share classes) must parse without degrading. This is 70% of Qapita's customer base.
5. **Defense gate.** Every weird clause in the output cites a published precedent (NVCA, VIMA, charter §). Every degraded parse generates a punch list, not a fabrication. No LLM in the calculation pipeline, ever.

A feature that doesn't move one of these gates is a distraction.

### 0.3 The positioning that must survive — "expert-led, not algorithm-only"

The tool's entire register is built on this sentence, lifted from Evelyn's public 409A page. Production decisions that erode it kill the tool's adoption faster than any bug:

- The tool **refuses** when input is too messy. It does not guess. The refusal is the deliverable.
- The tool **cites** every finding to a field or source cell. No floating opinions.
- The tool **does not** produce a fair-value number, an OPM output, a Backsolve, or a DLOM. It hands clean structured data to a model the analyst still drives.
- The audit memo has `[ANALYST: ...]` placeholders **on purpose**. The tool fills facts; the human fills judgment.

Any production feature that violates this register is rejected on sight, no matter how clever. This is non-negotiable.

---

## 1. Pre-Arrival (now → 2026-08-01)

The build is done. The interview is won. The danger window is *between now and starting* — bad decisions here make the rest of the roadmap impossible.

### 1.1 IP and licensing — fix before joining

- **Current state:** MIT license, public GitHub repo `subhankarshukla04/cap-table-reconciler`, fixtures and engine fully open.
- **Threats:**
  - Qapita IP assignment clauses (standard in most fintech offers) may sweep anything you build during employment, even on personal time, if the work touches the employer's domain. Cap-table tooling is squarely in the domain.
  - A public repo with "Qapita" in the README (currently mentioned in `CONTEXT.md`, `PLAN.md`, etc.) is a discoverable artifact. If the tool becomes internal, that public history complicates the IP story.
- **Actions before Day 1 at Qapita:**
  1. **Read the offer's IP clause carefully** the moment it lands. If pre-employment work is excluded from assignment (typical for prior inventions), keep the public repo as a *demonstrable prior invention* and list it in the schedule of pre-existing IP attached to the offer letter. This protects you from later disputes.
  2. **If pre-employment work is NOT excluded**, take the repo private before Day 1 and request explicit written carve-out for "Cap Table Reconciler, GitHub commit `7675029` and prior, MIT-licensed, prior-art." Most fintech employers accept this when raised cleanly.
  3. **Remove Evelyn's name and any Qapita-internal details** (team headcount, internal email addresses, specific engagement references) from public-facing files. Specifically `CONTEXT.md`, `PLAN.md`, `BUG_REPORT.md`, `ELIMINATION.md`, `OLESIA_RESEARCH.md`, `PIVOT_AUDIT.md`. Move sensitive notes into a `notes_private/` folder gitignored locally, or wipe.
  4. **Strip the `Recent Engagements` section** of `CONTEXT.md` (Avant Meats, Campana Group, ABB Vietnamese portfolio) from anything public. Those engagements are public-facing for Qapita's PR, but listing them in a tool's prep doc looks like you scraped client work for marketing.
  5. **Decide the license posture for after you join.** Three options, ranked:
     - **(A) Take repo private, transfer to Qapita on Day 30 after pilot proposal accepted.** Best alignment. Loses public portfolio asset.
     - **(B) Keep MIT + public, build internal fork at Qapita with explicit license-back.** Best portfolio outcome. Requires Vamsee (CTO) and legal alignment.
     - **(C) Keep MIT + public, but stop pushing changes once internal work begins.** Cleanest, lowest-friction. You lose the ability to credit yourself with post-join improvements in the public artifact, but the public version stays as a portfolio piece frozen at the pre-join state.
     - **Default to (C) unless explicit reason to do (A) or (B).** Doing (A) gives Qapita free engineering and may not get reciprocity. (B) opens a licensing-policy debate you do not want to initiate as an intern.

### 1.2 Defensive scope discipline — what to NOT do before Aug 1

- **Do not ship new fixtures.** Five is enough. The sixth (Sundar Foods stress test) is the honest-limit demo. Adding more dilutes the demo's argument.
- **Do not pre-build OPM Backsolve.** Tempting because the CONTEXT.md was originally about that. But the *expert-led* register is the reason you got the offer. An unsolicited OPM Backsolve before Day 1 reads as "I want to do your team's judgment work."
- **Do not deploy publicly.** Once it's at `something.com`, you owe operational hygiene (uptime, security disclosure, abuse handling) you don't want to own. The Vercel marketing site (`cap-table-reconciler-site`) is fine; the actual tool stays local.
- **Do not announce the offer or the tool on LinkedIn in a way that names Qapita or the team.** "Joining a Singapore fintech" is enough until you're in.
- **Do practice the engine math.** Re-derive the participating-cap waterfall on paper for fixture 03 (Bandhan Ventures), 04 (Surya Foods full ratchet trigger), 05 (Delaware double cap). If a Big 4 auditor asked you to defend any output, you must be able to do it on a whiteboard. This is the credential that makes everything else possible.

### 1.3 Pre-arrival research — the questions to bring to Day 1

You don't have answers to these yet. Write them down. The first week is about getting them.

1. **What is Qapita's actual stack?** (Vamsee is CTO, 20+ yrs eng. If it's TypeScript/Node + Postgres, your Python/Flask tool needs a strategy: either rewrite or expose-as-service.)
2. **How does the Valuations team currently move data?** (Email attachments? Shared drive? Internal app? If Qapita already has a workpaper system, this is your integration target, not your replacement target.)
3. **What % of International Valuations engagements involve non-Qapita-platform clients?** (If 90%+ are already on the platform, the "Excel ingest" wedge is small. If 50% or more come from outside, the wedge is enormous.)
4. **Who is the actual decision-maker on internal tool adoption?** (Evelyn for her practice; Amit Majumder for SEA & ANZ; Vamsee for engineering greenlight. Three signoffs, sequenced.)
5. **What's the audit retention requirement?** (Big 4 typically wants 7 years immutable. Singapore/India regulations vary. This sets the data architecture.)
6. **What's the SOC 2 / ISO 27001 / data-residency posture?** (Qapita serves regulated clients. India data may need to stay in India. Singapore data may need to stay in Singapore. Determines hosting strategy.)
7. **Does Qapita already have a 409A / IFRS 13 output template?** (If yes, your audit memo template must match it, not invent its own.)
8. **How does the team handle SAFE conversion today?** (The tool punts to the analyst by design. Maybe the team has a worksheet that does this. Maybe Punch Financial's acquisition brought one. Find out before reinventing.)

---

## 2. Phase 1 — Observe, Days 1–30

The single highest-leverage thing you can do in your first month is **not write code**. Watch three real engagements end-to-end. Map every step. Note where the existing tool would have helped, where it would have gotten in the way, and where it's irrelevant. Bring that map to Evelyn at Day 30. That conversation determines whether the tool gets internalized.

### 2.1 Three engagements, shadowed

For each: sit with Arthur Ng (Singapore) or Reinaldi Tanjung (Indonesia) through the entire workflow.

| Phase | What to watch for |
|---|---|
| Client kickoff | What format is the cap-table data delivered in? Excel? Qapita platform? PDF charter? Email attachments? Who chases the CFO when terms are missing? |
| Data intake | How long does cap-table cleanup take? How is the cleanup recorded? Is there a punch list today, or is it tribal knowledge? |
| Model build | OPM Backsolve? DCF? BSM for ESOP? Which inputs are the hardest to source? Which inputs cause the most auditor pushback? |
| Memo drafting | What template? Who reviews? Where are the time sinks — narrative writing, sensitivity tables, citation-checking, version control? |
| Auditor handoff | What does Big 4 send back? Which questions recur? How long is the review cycle? |
| Re-engagement | When does the same client need an updated 409A six months later — how much is reusable vs from-scratch? |

**Deliverable to yourself at Day 30:** a written workflow map (one page per phase, one engagement per column, mark in red the points where the demo tool would have helped). This is the single most important artifact of Phase 1.

### 2.2 The Day-30 pitch

Walk into Evelyn's 1:1 with a one-page document. Three sections:

1. **What I observed.** Concrete time tallies from the three engagements. e.g., *"Avant Meats follow-up Q2 took 14 hours of analyst time, of which 6.5 hours was cap-table cleanup, 4 hours model rebuild, 3.5 hours memo drafting and citation checking."* (Fabricate nothing. Numbers come from your shadow notes.)
2. **What would have changed with the tool.** Honestly. Maybe 2 of 6.5 hours of cleanup go to zero. Maybe the memo draft saves 1.5 of 3.5 hours via auto-populated structured sections. Maybe the model rebuild saves nothing because the team uses internal Excel. **Quantify, don't sell.**
3. **The proposal.** Two paths:
   - **Path A — internalize.** Migrate the tool into Qapita infrastructure. You spend Months 2–4 on the integration and the missing features (multi-tenancy, holder-level rollup, Big 4 PDF, Qapita data wiring). Target: by Month 4, every new engagement starts in the tool. Concrete success metric: by Month 6, 50%+ of new International Valuations engagements use the tool for intake.
   - **Path B — keep external.** The tool stays a personal artifact, gets used informally by Arthur/Reinaldi for cleanup, but never becomes Qapita IP. This is the fallback if Vamsee won't greenlight a new Python service in the stack, or if Evelyn's preference is "I want you on engagement work, not engineering."

**Whichever path Evelyn picks is the right path.** Do not argue for A if she picks B. Adoption you don't own is still adoption.

### 2.3 What you do NOT do in Phase 1

- **Do not write a single line of production code for the tool.** Touching the engine to "make it more enterprise" before you understand the workflow is the most common failure mode.
- **Do not pitch Evelyn the tool in Week 1.** She knows. The interview was the pitch. Re-pitching looks needy. Earn the right to bring it up by being useful on engagement work first.
- **Do not show the tool to anyone outside her direct team without permission.** Especially not Amit Majumder, Vamsee, or the founders. Premature visibility creates premature stakeholders.
- **Do not promise timelines.** Internal-tool builds at small companies always take 2-3x longer than expected because the engagement work has priority.

---

## 3. Phase 2 — Internal Pilot, Months 2–3

Assumes Path A from §2.2 (greenlight to internalize). Months 2–3 are about closing the four production gaps that, until closed, make the tool unusable on a real engagement. The order is non-negotiable; each blocks the next.

### 3.1 Gap 1 — The Qapita data wiring (Weeks 5–7)

**The problem.** Right now the tool only ingests Excel. Half (or more) of International Valuations engagements involve clients already on Qapita's platform. For those clients, the canonical cap-table is in Qapita's database, not in a CFO's Excel. Forcing analysts to export Excel from Qapita to re-import to the tool is a hostile workflow.

**The fix.** Add a third input mode to the parser: read directly from Qapita's cap-table data source. Architecture:

```
ingestion/
  excel.py        (existing parser, unchanged)
  qapita_api.py   (NEW — adapter that reads Qapita's internal cap-table API)
  pdf.py          (existing pdf_intake, unchanged)
canonical/
  models.py       (existing — the pydantic CapTable stays canonical)
```

The Qapita adapter outputs the same canonical `CapTable` object. Everything downstream (checklist, waterfall, exporters) is unchanged. This is the load-bearing architectural choice that keeps the engine portable.

**Open questions to resolve Week 5:**
- Does Qapita's cap-table data model include the SEA-specific clauses the engine needs? (Anti-dilution variant, participation cap multiple, voting differential, conversion ratio post-ratchet.) If yes, easy mapping. If no, two options: (a) extend Qapita's data model — political, requires Vamsee buy-in; (b) ingest from Qapita + supplement with a lightweight "valuations annotations" overlay table in your service.
- Is there an internal API or do you read the DB directly? Read-only DB access is faster but couples you to schema. API is cleaner but may not exist yet.
- What identity scheme — Qapita SSO or your own auth? Almost certainly SSO. Don't roll your own.

**Risk.** If the Qapita data model is missing fields the engine needs, this gap is bigger than 3 weeks. Plan for that contingency: keep the Excel path as the primary, treat Qapita data as a "starter" that the analyst still augments via the existing UI.

### 3.2 Gap 2 — Multi-tenancy, auth, and the immutable audit log (Weeks 7–9)

**The problem.** `SessionStore` (SQLite, token-keyed, no auth) is fine for a screen-share demo. It is not okay for a tool that touches real client cap-tables. The instant a real engagement starts:
- Two analysts open the same engagement → race conditions.
- The CFO sends a revised Excel mid-engagement → the prior version must be preserved exactly.
- The auditor asks "what did the cap-table look like on the valuation date" → you must produce it byte-for-byte.

**The fix.** Three pieces, sequenced.

**(a) Engagement model.** Replace `session` (transient, token) with `engagement` (durable, named):

```
engagement
  id (uuid)
  client_id (FK to Qapita client)
  valuation_date
  standard_of_value (ENUM: ifrs13 | asc820 | sec409a | ifrs2)
  created_by (user)
  created_at
  status (open | review | signed | archived)

snapshot
  id (uuid)
  engagement_id (FK)
  source (ENUM: excel_upload | qapita_pull | manual_edit | resolution)
  source_filename
  source_hash (SHA-256 of the original bytes)
  cap_table_json (canonical, immutable)
  parse_report_json
  created_by (user)
  created_at
  superseded_by (FK to next snapshot, NULL if current)

resolution
  id (uuid)
  snapshot_id (FK)
  finding_code (G-prefix)
  decision_json (what the analyst chose)
  citation (free-text, required)
  resolved_by (user)
  resolved_at

audit_event (append-only)
  id (uuid)
  engagement_id
  event_type
  payload_json
  actor (user)
  ts
```

Critically: **snapshots are immutable.** An "edit" creates a new snapshot and links the old one via `superseded_by`. Resolutions are append-only. The audit log is append-only. There is no UPDATE statement on any of these tables in production code. This is what makes the tool defensible to a Big 4 auditor two years after the engagement closes.

**(b) Authentication.** Qapita SSO. Period. No custom user table. Roles via Qapita's existing role system. Read-only auditor role gets a magic-link-style scoped read token that expires.

**(c) Tenancy.** Single-tenant per engagement (each engagement scoped to one client). Cross-engagement reads gated by client_id + user role. This is enforced at the query layer, not the application layer — every query takes `client_id` as a required parameter; queries without it raise.

**Risk.** This is six weeks of work compressed into two. It will overrun. Mitigation: scope the MVP to engagement + snapshot + audit_event only. Defer the resolution-versioning subtlety to Month 4 if needed.

### 3.3 Gap 3 — Holder-level Indian-CFO Excel rollup (Weeks 9–10)

**The problem.** The Sundar Foods stress test is honest about this: real Indian CFO Excels are *holder-level*, not *class-level*. One row per individual shareholder. The class structure is implied by repeated columns or shared issue-date patterns. The parser today drops 72 rows of holder data because they fail the preferred-must-have-LP validator. India is 70% of Qapita's 2,700 companies. This must work.

**The fix.** A new pre-parser layer: `rollup.py`. Given a holder-level workbook, detect and aggregate into class-level rows before the existing parser runs.

Detection heuristics, in order of priority:
1. **Explicit class column.** If a `Class` or `Security Type` or `Instrument` column exists, group by it.
2. **Issue-date clustering.** Holders with identical issue dates and identical issue prices are nearly always the same round. Group by (issue_date, issue_price, instrument_type_alias).
3. **Name-pattern clustering.** "Series A Investor Mr. X", "Series A Investor Ms. Y" → "Series A" class. Pattern-mine the holder column for class hints.
4. **Manual mapping fallback.** If automated heuristics produce <80% confident grouping, surface a UI step: show the analyst the proposed grouping with a sample of holders per group, let them confirm or remap.

The rollup produces a class-level cap-table with a *holder-detail* sidecar (kept separately, used for ESOP grant-level work later but never feeding the waterfall). The downstream engine is unchanged.

**Critical:** the rollup must record every aggregation decision in the parse report. "Grouped 47 holders → Series A based on issue-date cluster 2023-04-15." Auditor must be able to verify.

**Risk.** This is genuinely hard. The fallback to manual mapping is not optional — automated heuristics will be wrong sometimes and the analyst needs an escape hatch. Design the UI for the manual path first; automation is the fast lane on top.

### 3.4 Gap 4 — The Big-4 PDF memo (Weeks 10–12)

**The problem.** Today the audit memo is Markdown with `[ANALYST: ...]` placeholders. Markdown is not an audit deliverable. Big 4 wants PDF with: cover sheet, version stamp, page numbers, named reviewer, citations to source cells with hyperlinks back to the snapshot, signature block.

**The fix.** WeasyPrint (already in your global stack — `libpangoft2-1.0-0` is the system dep). Template structure:

```
templates/memo/
  base.html          (cover + header + footer with version stamp + page numbers)
  section_01_engagement.html
  section_02_scope.html       (Standard of Value: IFRS 13 / ASC 820 / 409A / IFRS 2)
  section_03_methodology.html (the tool's role: data integrity, not valuation)
  section_04_cap_table.html   (auto-populated, every cell cites snapshot ID + cell ref)
  section_05_findings.html    (auto-populated from checklist + resolutions)
  section_06_waterfall.html   (auto-populated breakpoints + tranche table)
  section_07_assumptions.html ([ANALYST: ...] judgment block — explicit)
  section_08_conclusion.html  ([ANALYST: ...] judgment block — explicit)
  appendix_a_provenance.html  (every non-vanilla clause → citation)
  appendix_b_changelog.html   (snapshot history, who changed what when)
```

Two passes:
- **Pass 1 (Weeks 10–11):** auto-populated sections work. Analyst's judgment sections are still explicit placeholders. Output is a real PDF; cover sheet, footer, citations all present.
- **Pass 2 (Week 12):** review with Evelyn against her current Word/PDF template. Adjust typography, table styling, citation format to match Qapita's house style. This is taste work, not engineering — sit next to her for an afternoon.

**Risk.** The biggest miss here is *not matching the existing template*. If Evelyn's team has a 30-page Word doc they've been refining since 2022, your PDF must look like it could slot into that workflow without retraining auditors. Get the template first.

### 3.5 Phase 2 acceptance criteria

By end of Month 3:
- Two real engagements have been run end-to-end in the tool, with analyst sign-off that the tool produced a usable workpaper.
- All four gaps closed at "good enough for pilot" level — not perfect. Production-grade hardening is Phase 3.
- A written go/no-go from Evelyn: does the tool get used on every new International Valuations engagement starting Month 4, yes or no?

If no, regroup. Don't sunk-cost into Phase 3.

---

## 4. Phase 3 — Hardening, Months 4–6

Assumes Phase 2 go: tool is now the default intake path for new engagements. Phase 3 is about making the tool defensible in three regimes that demo work doesn't touch.

### 4.1 Rule-pack versioning and the path to 50 rules (Month 4)

**Why this is the moat.** Carta has cap-table software. Pulley has cap-table software. Eqvista has cap-table software. None of them have *rule-pack versioned* cap-table integrity checks where the auditor can re-run an engagement two years later against the rules effective on the valuation date. This is the difference between a productivity tool and a regulated workflow tool.

**The model.**

```
rule_pack
  id (uuid)
  version (semver: 2026.1.0)
  effective_from (date)
  effective_to (date, nullable for current)
  jurisdictions (array: ["IN", "SG", "US-DE", "ID"])
  standards (array: ["ifrs13", "asc820", "sec409a"])
  rules_json (the full ordered list of G-codes with logic + severity + citations)

engagement_pack_binding
  engagement_id (FK)
  rule_pack_id (FK, frozen at engagement open)
```

When an engagement is opened, the rule pack is frozen against it. Re-runs use the frozen pack. The current "head" pack is what new engagements use. Auditor request for re-run: load the snapshot, load the bound pack, recompute.

**Scaling from 8 to ~50 rules.** Real-world rule categories the demo doesn't yet cover:

- **Anti-dilution mechanics (currently 1 rule → expand to 6):** narrow-based vs broad-based denominator drift; full-ratchet trigger with founder-friendly exceptions; pay-to-play forfeiture with selective waiver; weighted-average pre-money basket definition; AD waiver letter detection; AD precedent over multiple rounds.
- **Participation/cap mechanics (currently 1 → 4):** cap multiple-of-LP vs absolute; cap on pre-money vs total return; double-cap stacking; pay-to-play interaction with participation.
- **SAFE/convertible mechanics (currently 1 → 6):** MFN clause unresolved; cap vs discount conflicting at trigger; pre-money vs post-money SAFE detection; YC vs Cooley vs custom template; qualified financing threshold below current raise; SAFE-on-SAFE conversion ordering.
- **Option pool mechanics (currently 1 → 5):** pre-money vs post-money pool sizing; granted vs reserved split; refresh threshold; cliff/vesting schedule integrity; ISO/NQO classification (US engagements).
- **Voting / governance (currently 1 → 5):** dual-class supermajority detection; protective provisions enumeration; founder vesting and acceleration; drag-along scope; ROFR/co-sale.
- **Round mechanics (currently 1 → 6):** down-round detection (full-ratchet trigger); side-by-side preferred (pari-passu); convertible bridge round detection; non-cash consideration; secondary purchase in primary round; insider-only round flags.
- **Side-letter integrity (currently 1 → 5):** MFN scope unresolved; super-pro-rata rights; information rights asymmetry; consent-right enumeration; side-letter precedence vs charter conflicts.
- **Jurisdiction-specific (currently 0 → ~12):** India FEMA pricing-floor for foreign holders; India CCPS/RCPS structure validation; Singapore VIMA model-doc drift; Delaware Section 251 conversion mechanics; California 25102(f) exemption; AICPA Cheap Stock Guide cross-references.

**Pace.** ~5 rules/month. Don't rush. Each rule needs a fixture, a regression test, a citation to a published precedent, and (ideally) a real engagement that exercised it.

### 4.2 Pari-passu seniority (Month 4)

The hard data-model limit. Real Singapore deals have it. The fix:

- Replace `seniority_rank: int` with `seniority_tier: tuple[int, int]` where `(1, 0)` means rank 1 standalone, `(1, 1)` and `(1, 2)` are pari-passu within rank 1.
- The waterfall engine's regime walker treats pari-passu classes as a single LP-paying group with proportional allocation within the group.
- Existing fixtures and tests migrate via a default `(rank, 0)` mapping — backward compatible.

This is ~1 week of focused work, not a month. Schedule it early in Month 4 so it's done before any pari-passu real engagement hits.

### 4.3 OCR for image-PDF side letters (Month 5)

**Why.** Half the Indian deal side letters are scanned. The current pdfplumber-only intake silently fails them.

**The fix.** A two-stage pipeline:
1. `pdfplumber` extraction first (works for text PDFs).
2. If pdfplumber yields <100 characters or <5% page-area coverage, fall back to OCR (Tesseract or, more reliably, a managed OCR service like AWS Textract or Google Document AI).
3. Either way, the output is text + a confidence score. Side letters with confidence <0.85 surface a UI banner: "OCR confidence low, recommend manual review of original."

**Critical constraint:** the OCR output is *raw text stored verbatim*. No LLM extraction. The analyst still reads it and enters structured side-letter fields manually. This preserves the expert-led register.

**Vendor decision.** Probably Google Document AI for Indian-script support and table-aware extraction. Cost is real but trivial vs analyst hours saved. If data-residency forbids cloud OCR, fall back to a self-hosted Tesseract + LayoutParser stack — worse accuracy, higher ops burden, but compliant.

### 4.4 Structured snapshot diff (Month 5)

Current `diff.py` does fuzzy class-name matching. Production needs field-level diff with provenance:

```
diff(snapshot_a, snapshot_b) → list[FieldDiff]
  FieldDiff:
    path: "share_classes[Series B-1].liquidation_preference.cap_multiple"
    old_value: 3.0
    new_value: None
    change_type: "removed"
    source_snapshot: snapshot_b.id
    rule_implications: ["G-CAP-001 was applied to old; rule not applicable to new"]
```

This feeds the audit memo's *subsequent events* section automatically. Auditor reading the memo can hyperlink from "the option pool grew by 1.2% between valuation date and signing" directly to the exact field on both snapshots.

### 4.5 Onboarding the wider team (Month 6)

By Month 6, the tool is being used by Arthur, Reinaldi, and you. Time to widen:

- **Amit Majumder's India team** (Head of SEA & ANZ). India is the volume base. Onboarding 2–3 India analysts is the test of whether the tool generalizes beyond your direct working relationship.
- **Punch Financial integration scout.** Punch was acquired Oct 2025. They do US fund admin. If their workflow touches portfolio-company valuations (typical for fund admins), the tool may be relevant. Don't push; find out via low-key conversation.
- **A read-only auditor role.** Pick one friendly Big 4 auditor on a current engagement. Give them a read-only login. Get a 30-minute walkthrough of their workpaper. Their feedback on the PDF memo is the single most valuable signal you'll get all year.

### 4.6 Phase 3 acceptance criteria

By end of Month 6:
- 50%+ of new International Valuations engagements use the tool for intake (matches your Day-30 pitch number).
- At least one Big 4 auditor has signed off on a tool-produced PDF memo without substantive pushback.
- Rule-pack count: 30+, each with fixture coverage.
- Holder-level Excel parses cleanly on 5+ real engagements without manual remapping.
- The tool runs in Qapita infrastructure (not on your laptop). Identity via Qapita SSO. Persistence in Qapita's managed DB. Backups + retention policy enforced.

---

## 5. Phase 4 — Platform Play, Months 7–12

This is where the tool stops being a tool and becomes a platform. The bet: the *clean structured cap-table output* is the right contract for a family of downstream consumers, each of which is a separate workflow today doing its own ad-hoc cleanup.

### 5.1 Sibling 1 — OPM Backsolve consumer (Months 7–8)

The original CONTEXT.md target. Now defensible because the input layer is solid.

- **Contract.** OPM Backsolve consumes the clean CapTable + a market-input pack (volatility, time, risk-free, DLOM). Outputs implied total equity value + per-class fair value + per-share common FMV.
- **Scope discipline.** This is *Backsolve only*. No fair-value-from-scratch OPM. No DCF. The Backsolve is the workhorse and the auditor-defensible path.
- **Build pattern.** Same canonical-model approach. New module `src/opm/backsolve.py` with `scipy.optimize.brentq` solver. Outputs feed a new memo section.
- **Critical:** market inputs (vol, time, rf) are *defensible per Qapita house methodology*. The tool surfaces the input, the analyst sources and defends it. No "auto-pick vol from comps." Expert-led.

### 5.2 Sibling 2 — BSM for ESOPs / IFRS 2 (Months 8–9)

ESOP fair value under IFRS 2 / ASC 718. Per-grant BSM, amortized over vesting, journal-entry summary.

- **Contract.** Consumes CapTable + ESOP grant schedule + market inputs. Outputs per-grant fair value, amortization schedule, P&L impact per period.
- **Why this one matters.** Every Qapita customer with an ESOP needs this for IFRS-compliant financial reporting. High volume, repetitive, exactly the kind of work the JD said "automate financial models."
- **Risk.** Qapita's ESOP product team already does some of this. Coordinate with them; the goal is to *feed* their reporting pipeline, not duplicate it.

### 5.3 Sibling 3 — DCF input contract (Months 9–10)

For full-DCF engagements (Avant Meats was one, per Qapita's own marketing). The cap-table reconciler delivers a structured per-class equity contract that the DCF model consumes when allocating enterprise value back to share classes.

- **Contract.** Same clean CapTable. The DCF runs in Excel (where the team builds it today). Tool produces a clean Excel sidecar with named ranges for share counts, LPs, conversion ratios. DCF model links to the sidecar.
- **Why a sidecar, not a DCF.** The DCF is judgment work — comps, terminal value, WACC. Expert-led. The tool's role is to make the cap-table layer beneath the DCF clean and version-stable.

### 5.4 Schwab + US expansion (Months 10–12)

The strategic context: Schwab Series B Oct 2025, Punch acquired Oct 2025, US market expansion the explicit thesis of the round. Internationally Valuations team scope is growing US-ward.

**The tool's path to US relevance:**
- **NVCA Model Legal Documents v2 alias coverage.** US deals use NVCA charter language. The instrument-type alias map and the rule-pack need NVCA-specific coverage. Most of this is already partially present from the demo fixtures; tighten it.
- **ASC 820 + Section 409A + AICPA Cheap Stock Guide alignment in the memo template.** Every section explicitly cites the standard it's compliant with. US auditors want the citations explicit.
- **Delaware-specific rules.** Section 251 conversion, dual-class share classes, redemption rights, preferred drag-along scope. Adds ~6 jurisdiction-specific rules.
- **S-1 read pipeline (stretch).** Per the OLESIA_RESEARCH pivot doc, DRHP reading generalizes to S-1 reading. If the Schwab cross-sell pipeline matters, the tool extends to ingesting filed S-1s for pre-IPO secondary work. This is a separate project that *reuses* the cap-table engine.

### 5.5 Phase 4 acceptance criteria

By end of Month 12:
- Three sibling consumers (OPM Backsolve, BSM/ESOP, DCF sidecar) live and used.
- US deal coverage: ≥3 ASC 820 / 409A engagements run through the tool.
- Tool is referenced in at least one Qapita external artifact (Qonversation talk, blog post, sales deck). Acknowledged as house infrastructure, not a side project.
- The engine has spun out as a Qapita-internal calculator service consumed by ≥2 other product teams (likely ESOP admin + Liquidity).

---

## 6. Hard Tradeoffs — What Not To Build

For each, the reason it's seductive and why it's a trap.

### 6.1 No LLM in the calculation pipeline. Ever.

- Seductive: "ChatGPT can extract terms from charters and side letters in 30 seconds."
- Trap: a single hallucinated anti-dilution variant in an audit memo is the kind of thing that ends Big 4 sign-off and creates legal liability. The "expert-led, not algorithm-only" register dies the moment an LLM is in the calc path.
- Allowed: LLMs in the *editor's* path (drafting the analyst's judgment paragraphs in the memo). Never in the data path.

### 6.2 No PWERM or hybrid-OPM/PWERM.

- Seductive: late-stage clients with visible IPO paths. PWERM is what they need.
- Trap: PWERM is 80% judgment (scenario weighting, IPO timing, illiquidity discount). The tool's role ends at clean cap-table. PWERM lives in Excel where Evelyn's team drives it.

### 6.3 No founder-facing cap-table editor.

- Seductive: it's natural for a "cap-table tool" to let founders edit their cap-tables.
- Trap: Qapita already has that product. Building it again is internal competition. The tool's audience is the Valuations team and the auditor, not the founder.

### 6.4 No tender administration, no secondary market, no buyer matching.

- Seductive: the OLESIA pivot explored exactly this surface and concluded "tender admin duplicates Qapita's tender product."
- Trap: same conclusion still holds. Stay in the Valuations lane.

### 6.5 No public deployment with multi-tenant SaaS pricing.

- Seductive: VC-friendly framing. Cap-table cleanup as a horizontal SaaS.
- Trap: you're not a founder, you're an intern. The expected outcome is "internal tool that becomes infra," not "Qapita is incubating a startup inside Qapita." If the spin-out conversation happens, it happens 18+ months in and only if Qapita drives it. Don't pitch it from inside.

### 6.6 No DLOM library, no volatility peer-set engine.

- Seductive: every OPM Backsolve needs a vol and a DLOM. Building a defensible vol library is a real product.
- Trap: vol and DLOM are *judgment inputs*. The tool surfaces them; the analyst sources them from Damodaran, Bloomberg, AICPA practice aids. If a vol library gets built, it's a separate research project, not bolted onto the cap-table tool.

### 6.7 No "AI-assisted" anything in the marketing.

- Seductive: AI is in everyone's deck.
- Trap: Evelyn's team is defined by *not* being algorithm-only. If the tool ever gets external visibility, the marketing register is "deterministic, audit-grade, rule-based." That's the differentiator.

---

## 7. Risk Register

Ranked by probability × impact, top 10.

| # | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Vamsee won't greenlight a new Python service in the stack | Medium | High | Phase 1 §2.3 Q1. If stack is Node/TS, port the engine to TS (4-6 week project). If stack is Python, no change. If stack is heterogeneous (likely), build as a sidecar service with a thin HTTP API. |
| 2 | Evelyn prefers you on engagement work, not engineering | High | Medium | Path B in §2.2. Tool stays informal, used by analysts. Slower growth but still valuable. Your visibility becomes engagement-quality, which is fine. |
| 3 | Qapita's existing cap-table data model is missing engine-required fields | Medium | High | Phase 2 §3.1 mitigation. Excel-first remains the primary path; Qapita data is enrichment, not replacement. |
| 4 | Holder-level rollup is harder than 2 weeks | Medium | Medium | Drop the auto-grouping ambition; ship manual-mapping UI first, automate later. |
| 5 | OCR vendor data-residency conflicts with Qapita's posture | Low | High | Self-hosted Tesseract fallback documented in §4.3. Worse output but ships. |
| 6 | Pari-passu data-model change breaks existing fixtures | Low | Low | Default-tier migration in §4.2; regression suite catches it. |
| 7 | Big 4 PDF memo doesn't match Qapita's house style | High | Low | Spend the afternoon with Evelyn in §3.4 Pass 2. Taste, not engineering. |
| 8 | Public MIT repo creates IP friction | Low if §1.1 done | High if not | Option (C) default. Don't push public commits once internal work starts. |
| 9 | The tool is "too good" and Qapita wants to commercialize it as a product | Low | Medium | Let them. Spin-out is their decision, not yours. Negotiate equity-back-to-builder if it happens (this is what your lawyer earns their fee on). |
| 10 | You burn out on the tool because engagement work is more interesting | Medium | High | Be honest. If by Month 4 you're not energized by tool work, hand it off to a Qapita engineer and stay on engagements. The tool's value to your career is the *transition* it represents (built it → ship it → it gets adopted), not the maintenance grind. |

---

## 8. Definition of Done — by Phase

| Phase | Done when |
|---|---|
| Pre-arrival (Aug 2026) | IP posture clean, public repo decision made, sensitive files sanitized, math defensible on whiteboard from memory |
| Phase 1 — Observe (Sep 2026) | 3 shadowed engagements documented, 1-page pitch delivered to Evelyn, go/no-go decision on internalization |
| Phase 2 — Internal Pilot (Sep–Nov 2026) | 4 production gaps closed (Qapita data, multi-tenant + audit log, holder-level rollup, Big 4 PDF), 2 real engagements run end-to-end |
| Phase 3 — Hardening (Dec 2026) | 50%+ of new International Valuations engagements use the tool, 30+ versioned rules, 1+ Big 4 auditor signed off on a memo, runs on Qapita infra not your laptop |
| Phase 4 — Platform Play (post-internship) | 3 sibling consumers live, US/ASC 820 coverage, tool referenced externally as Qapita infrastructure |

The internship is Aug–Dec 2026. Phases 1–2 and the start of Phase 3 fit. Phases 3 completion and Phase 4 only happen if Qapita extends, hires you back post-NOC, or contracts you. That's a separate negotiation. Don't optimize for it.

---

## 9. Open Questions for Week 1

These need answers before any code:

1. What's Qapita's primary engineering stack? (Vamsee 1:1 in Week 1.)
2. How does the Valuations team move cap-table data today? (Shadow Arthur, Day 2.)
3. What % of International Valuations engagements involve clients already on Qapita's platform? (Evelyn 1:1 Week 1.)
4. Who owns greenlight on a new internal service — Vamsee solo, or a CTO-CPO joint? Does Amit Majumder get a vote on SEA-team tooling?
5. What's the audit retention requirement (Singapore + India + Indonesia + Delaware engagements all differ)?
6. SOC 2 / data residency posture? Which cloud, which region for cap-table data?
7. Is there an existing 409A / IFRS 13 memo template, and can I see it?
8. How does the team handle SAFE conversion today — manual worksheet, internal tool, or punt-to-Excel?
9. What's the Punch Financial integration roadmap and does any of it touch portfolio-co valuations?
10. What's the realistic engagement volume Sep–Dec 2026? (Determines how many engagements you can shadow vs work on.)

Bring these to Evelyn's Week-1 1:1. Don't ask all ten at once; sequence them. Q1 and Q3 are the most important — they determine the entire architecture.

---

## 10. The One-Sentence Strategy

Internalize the Cap Table Reconciler as Qapita's audit-grade intake layer for International Valuations, by shadowing three engagements, closing four production gaps in 90 days, and extending the engine into OPM/BSM/DCF siblings only after the intake layer is the default path for new engagements — preserving "expert-led, not algorithm-only" as the non-negotiable register at every step.

If that sentence stops being true at any point, stop and rethink the phase.
