# Independent Audit Plan — Cap Table Reconciler

> Written by an auditor with NO access to the builder's tests, fixtures, precedent, or source code. Every test scenario sources its input from public, citable references. The point of this document is to verify the builder's spec without inheriting the builder's blind spots.

---

## 0. Auditor's stance

### (a) What I have read

I have read exactly two artifacts produced by the builder:
1. `SYSTEM_SPEC.md` (1,046 lines) — the per-phase functional contract. This is the contract I am testing against.
2. `PRODUCTION_ROADMAP.md` — the strategic narrative around how the spec maps to Phases 0 through 4 and what "Phase N done" means in business terms.

Beyond those two files, all input material for this audit comes from external, citable public sources. I have done at least 15 distinct WebSearch queries against primary regulatory, legal, and accounting sources to ground the test inputs. The source catalog is enumerated in §1. Where a public source is paywalled or behind login, I say so rather than substitute a press summary for the primary doc.

### (b) What I have NOT read

I have deliberately NOT opened any of the following files, even when curiosity made it tempting:

- `/tests/*` — the builder's test suite. Re-running someone's own tests is not an audit.
- `/fixtures/*` — the five curated cap tables (Solstice Labs, Pelaut Logistics, Bandhan Ventures, Surya Foods, Sundar Foods). Designing my tests around the same shapes would defeat the point.
- `/stress_test/*` — the fuzz-audit work.
- `/precedent/*` — the builder's harvested charter precedent.
- `/src/*` — the implementation. I am testing what the spec promises, not what the code happens to do today.
- `CURRENT_STATE.md`, `BUG_REPORT.md`, `PIVOT_AUDIT.md`, `ELIMINATION.md`, `OLESIA_RESEARCH.md`, `PLAN.md`, `PLAN_OLESIA.md`, `RADAR_README.md`, `README.md`, `SPEC_OLESIA.md`.
- Anything in `/jax_interview/` or `/radar/`.

Where this audit would benefit from knowledge those files hold, I write down the unresolved question in §5 (Things I Cannot Independently Verify) rather than peek. The visible gap is the deliverable.

### (c) The anti-cheating rules I am bound by (restated)

- **No fixture mimicry.** Every test input is sourced from a public document I cite by URL. None of my scenarios use Solstice Labs, Pelaut Logistics, Bandhan Ventures, Surya Foods, Sundar Foods, or any near-name variant. If the builder ships a new fixture that mirrors one of my external sources after I publish this plan, that's a flag (see §8).
- **No G-code testing.** The spec uses internal rule codes like `G-CAP-001`. Those are the builder's implementation labels. I test the BEHAVIOR the spec promises (a participating-capped class with cap < 1.0× must normalize to non-participating per §1.5; that's behavior, not a G-code), not the code names.
- **No implementation guessing.** I test the spec's promises. If a promise is silent on something a real engagement will hit, I record that silence as a spec gap (§6).
- **Adversarial > comfortable.** Wherever the spec underspecifies, my test forces the question. Wherever the spec is precise, my test verifies the bounds, not the comfortable middle.
- **Honest when I don't know.** Searches that returned only press coverage rather than primary documents are flagged as such. Sources I could not access (paywalled, login-walled) are noted, not substituted.

---

## 1. External source catalog

Below are the sources I will draw test inputs from. Accessed dates are May 2026 unless noted.

### 1.1 Charter-language / model-document sources

**S1 — NVCA Model Certificate of Incorporation (Updated Oct 2025).** https://nvca.org/document/nvca-model-certificate-of-incorporation-updated-oct-2025/ . Provides the canonical US-Delaware preferred-stock charter language: seniority articles, liquidation preference, conversion, anti-dilution (broad-based weighted average), protective provisions, voting. Authoritative because the NVCA model is the de-facto US VC standard cited by virtually every US deal lawyer. Source for: anti-dilution clause language, LP language, dual-class voting language, redemption rights, drag-along scope.

**S2 — NVCA Model Stock Purchase Agreement (Oct 2025).** https://nvca.org/wp-content/uploads/2025/10/NVCA-Model-SPA-10-1-2025.docx . Source for: representations and warranties on capitalization (the rep that auditors lean on), capitalization schedule format, side-letter precedence vs charter clauses.

**S3 — Singapore VIMA 2.0 Long-Form Term Sheet.** https://www.svca.org.sg/sites/default/files/2022-09/VIMA%202.0%20Model%20Term%20Sheet%20(Long%20Form).doc . Published by Singapore Venture & Private Capital Association + Singapore Academy of Law. Source for: SEA-flavored liquidation preference language (1x non-participating dominant, pari-passu provisions, pro-rata-on-as-converted-basis when proceeds insufficient — this is a VIMA 2.0 update specifically). Authoritative for: Singapore-jurisdiction deals.

**S4 — Cooley GO YC SAFE Document Generator (Singapore variant).** https://www.cooleygo.com/documents/y-combinator-safe-financing-document-generator-singapore/ . Source for: SAFE template variants (pre-money, post-money, with cap, with discount, with MFN only). Critical because the spec says it stores SAFEs with `valuation_cap`, `discount_rate`, `conversion_trigger_threshold` — but YC ships multiple SAFE templates that differ in conversion mechanics.

**S5 — Cooley GO Post-$ Pro Forma Capitalization spreadsheet.** https://www.cooleygo.com/wp-content/uploads/2014/06/Sample-Pre-and-Post-Cap-Table-w-Pricing-Worksheet-2.xls . A worked Excel cap table from a top US firm. Source for: a real holder-level + class-level hybrid layout. Useful because it shows what "well-formed" looks like from a firm that publishes it as a template.

**S6 — Y Combinator Standard Deal page.** https://www.ycombinator.com/deal . Source for: the YC $125k + $375k MFN-uncapped SAFE structure currently in market. Important because hundreds of YC companies have this exact instrument on cap tables and the spec must store both halves.

### 1.2 Real SEC filings (S-1 / S-1/A)

**S7 — Reddit, Inc. Form S-1, Feb 2024.** https://www.sec.gov/Archives/edgar/data/0001713445/000162828024006294/reddits-1q423.htm . Reddit's pre-IPO cap structure included Series A through Series F-1 preferred, each with 1× liquidation preference and explicit conversion mechanics. Source for: a real multi-series cap table with 8+ preferred classes and Class A/B dual-class common stock. Useful for stress-testing how the system handles a cap table at the higher end of class count.

**S8 — Klaviyo Inc. Form S-1, Aug 2023.** https://www.sec.gov/Archives/edgar/data/0001835830/000162828023030618/klaviyoincs-1.htm . Klaviyo had complex preferred structure that converted at IPO. Source for: as-converted basis conversion timing, Class A/B common designations.

**S9 — Astera Labs, Inc. Form S-1, Feb 2024.** https://www.sec.gov/Archives/edgar/data/0001736297/000119312524040419/d285484ds1.htm . Source for: a more recent semiconductor S-1 with preferred conversion mechanics, used as a counter-example to Reddit so we test on at least two distinct US filings.

### 1.3 Real SEBI DRHP filings (India)

**S10 — Swiggy Limited Updated DRHP-I, Sep 2024.** https://www.sebi.gov.in/filings/public-issues/sep-2024/swiggy-limited-updated-drhp-i_87047.html . Source for: real Indian capitalisation-table format, CCPS-to-equity conversion provisions, multiple-round preferred share structure. India is the spec's volume-base jurisdiction (§3.3 holder-level rollup is justified by "70% of Qapita's 2,700 companies"). The DRHP is the publicly filed prospectus that auditors must reconcile against.

**S11 — Lenskart Solutions Limited DRHP, Aug 2025.** https://www.sebi.gov.in/filings/public-issues/aug-2025/lenskart-solutions-limited-drhp_95763.html . Source for: a 2025-filed Indian DRHP with multi-round preferred structure including international institutional investors (FEMA-relevant). Useful for testing the parser against a current rather than legacy DRHP format.

**S12 — Tata Capital Limited UDRHP-I, Aug 2025.** https://www.sebi.gov.in/filings/public-issues/aug-2025/tata-capital-limited-udrhp-i_95828.html . Source for: a large-company capital structure with multiple share classes. Tests scale.

### 1.4 Accounting standards (primary text)

**S13 — IFRS 13 Fair Value Measurement (IASB).** https://www.ifrs.org/issued-standards/list-of-standards/ifrs-13-fair-value-measurement/ . The international fair-value standard. Source for: what "fair value" means in the spec's `standard_of_value` enum, what "exit price" requires, the three-level fair-value hierarchy. Authoritative because IASB-issued.

**S14 — IFRS 13 full standard PDF.** https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ifrs-13-fair-value-measurement.pdf?bypass=on . The primary text. Source for: exact citations in audit memos under the IFRS 13 standard of value.

**S15 — FASB ASC 820 Fair Value Measurement, ASU 2022-03.** https://storage.fasb.org/ASU%202022-03.pdf . The US equivalent of IFRS 13. Source for: contractual sale restrictions on equity securities — directly relevant because preferred-stock charter restrictions on transfer are part of what a fair-value engagement must address.

**S16 — AICPA Accounting & Valuation Guide: Privately-Held-Company Equity Securities (a.k.a. "Cheap Stock Guide") — 2024 working draft of updated chapters 8, 9.** https://www.aicpa-cima.com/advocacy/download/working-draft-of-the-updated-valuation-of-privately-held-company-equity-unpublished . Source for: the canonical methodology for 409A / IFRS 2 valuations the spec's Phase 4 sibling consumers will produce. Particularly: chapter 6 (allocation among classes), chapter 8 (secondary market transactions), chapter 9 (calibration). 2024 draft, not yet final.

**S17 — PCAOB AS 1105 Audit Evidence (effective Dec 15, 2025).** https://pcaobus.org/oversight/standards/auditing-standards/details/as-1105--audit-evidence-(effective-for-fiscal-years-beginning-on-or-after-12-15-2025) . Source for: what an auditor expects to see in workpapers, what "sufficient appropriate audit evidence" means. Drives the audit-log + immutability invariants tests.

### 1.5 Jurisdiction-specific primary sources

**S18 — Delaware General Corporation Law Title 8 §251 (2025 codification).** https://law.justia.com/codes/delaware/title-8/chapter-1/subchapter-ix/section-251/ . Primary text of the merger statute. Source for: conversion mechanics on merger; preferred-stock conversion-on-deemed-liquidation language; cross-references in NVCA charter.

**S19 — California Corporations Code §25102(f) (DFPI page).** https://dfpi.ca.gov/rules-enforcement/laws-and-regulations/law-and-regulations-corporate-securities-law/corporations-code-section-25102f/ . Primary regulatory text. Source for: the California 35-purchaser limited-offering exemption referenced in the spec §5.4. Cap table must record that the financing relied on this exemption (auditor concern).

**S20 — RBI/FEMA Foreign Exchange Management (Transfer or Issue of Security by a Person Resident Outside India) Regulations.** https://incometaxindia.gov.in/Documents/Provisions%20for%20NR/FEM-Transfer-or-Issue-of-Security-by-a-Person-Resident-Outside-India-Regulations-2017.htm . Primary text. Source for: India CCPS pricing-at-issue requirement, OCPS classification as debt (not equity), Form FC-GPR filing deadline. The spec §4.1 enumerates "India FEMA pricing-floor for foreign holders" as a category. Testing requires the primary regulation.

**S21 — ACRA "Different Types of Shares" guidance.** https://www.acra.gov.sg/how-to-guides/shares-and-updating-share-information/different-types-of-shares . Singapore regulator on preference shares: rights must be set out in the constitution per Section 75 of the Companies Act. Source for: what a parsed Singapore preference share must record vs. what the spec actually fields.

**S22 — Indonesia OJK Regulation 35/POJK.05/2015 (venture capital company business).** Referenced via Conventus Law summary (https://conventuslaw.com/featured-content/indonesia-revamping-rules-for-finance-company-and-venture-capital/) and Global Legal Insights Indonesia IPO chapter (https://www.globallegalinsights.com/practice-areas/initial-public-offerings-laws-and-regulations/indonesia/). I could NOT find the OJK regulation in English on the OJK site; relying on practitioner summaries. Source for: Indonesian preferred-share rights structure, OJK 2024 dual-class regulation (relevant to `voting_differential` field). **HONEST GAP: I lack the OJK regulation in primary text. A formal audit should commission a translation.**

### 1.6 Worked-example / practitioner references

**S23 — Eqvista Backsolve Method guide.** https://eqvista.com/company-valuation/backsolve-valuation-method/ . Source for: a published OPM Backsolve worked example I can lift inputs from to test the Phase 4 §5.1 sibling consumer.

**S24 — Marko Djukic "Cap Table Waterfall: Working Example" (Medium).** https://mdjukic.medium.com/cap-table-waterfall-working-example-e6d8fde785d9 . Source for: a single fully-worked waterfall I can compare against the spec's WaterfallResult output. NOTE: Medium post, not regulatory; used only as a sanity-check, not a citation in an audit memo.

**S25 — Damodaran 2025 Equity Risk Premium dataset.** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5168609 . Source for: the volatility / ERP input the analyst would source for the OPM Backsolve sibling consumer. Tests that the spec correctly refuses to compute its own volatility (per §5.1 refusal).

**S26 — Qapita's own waterfall analysis blog post.** https://www.qapita.com/blog/how-to-model-exit-scenarios-with-waterfall-analysis-a-founders-guide . NOT used as test input (would be biased — it's the builder's company's blog). Listed for §8 cheating watch: if the tool's outputs mirror this blog's worked example exactly, that's worth flagging.

### 1.7 Sources I attempted and could not get clean access to

**Failed-S1 — Wilson Sonsini-authored anti-dilution article.** Searched directly; results returned secondary practitioner summaries (VC Beast, FauriLaw) but no WSGR-authored primary article. I am not substituting a Cornell-CMU classnote (which appeared in search) for a WSGR primary source. The NVCA charter (S1) carries the load instead.

**Failed-S2 — Reliance Jio DRHP (Oct 2024).** Located the SEBI URL (https://www.sebi.gov.in/sebi_data/attachdocs/oct-2024/1727955078450_532.pdf) but did not fetch the document. Listing as available source; not relied on for specific text in this plan because I have not read it.

**Failed-S3 — IOSCO / global IFRS 2 application notes.** Did not search exhaustively. IFRS 13 (S13/S14) covers the fair-value layer the spec touches; IFRS 2 share-based payment is the BSM sibling (§5.2). The AICPA Cheap Stock Guide (S16) is the closest cross-jurisdiction practitioner doc.

**Failed-S4 — OJK Indonesia primary regulation in English.** See S22. Practitioner summaries only.

**Failed-S5 — Wilson Sonsini/Cooley anonymized deal data trend reports.** I could verify market-stat claims (98.2% 1× LP, 96.4% non-participating) from a single citation; deeper trend-data would require Cooley's quarterly venture financing report. The single citation appeared in search results from cooleygo.com/data ; I did not fetch the underlying PDF.

---

## 2. Per-phase test plan

> Note: Test IDs follow the pattern `AUDIT-P<phase>-<POS|NEG|ADV|E2E|PERF>-<NNN>`. All tests are objective and binary — they pass or fail on a defined output value or refusal signal.

---

### 2.1 Phase 0 — Current State (Baseline contract)

**Spec contract being tested:** SYSTEM_SPEC.md §1 (sub-sections 1.1 through 1.11). The Phase 0 contract is the most surface-rich because it freezes existing behavior, so Phase 0 carries the most tests.

#### Positive tests (Phase 0)

**AUDIT-P0-POS-001 — Vanilla US 1× non-participating Series A parses.**
- Source: NVCA Model Certificate of Incorporation (S1). Construct an Excel where columns are `Class | Shares | PPS | Issue Date | Seniority | LP Mult | LP Type | Anti-Dilution`. Row 1: "Common", 8,000,000 shares, $0.0001 PPS, common. Row 2: "Series A Preferred", 2,000,000, $1.00 PPS, 1× non-participating, broad-based weighted average, seniority 1.
- Expected output: `(CapTable, ParseReport)` tuple. CapTable contains exactly 2 share classes, Series A has `liquidation_preference.type == non_participating`, `liquidation_preference.multiple == 1.0`, `liquidation_preference.amount == 2_000_000`, `anti_dilution.variant == broad_based_weighted_average`, `seniority_rank == 1`. ParseReport.warnings empty. ParseReport.cap_table_sheet set.
- Pass criterion: exact field-value match on the constructed Pydantic model.
- Spec section: §1.1, §1.3.

**AUDIT-P0-POS-002 — Header row at row 4 (not row 1) still detected.**
- Source: NVCA — derive same structure but place the cap table starting at row 4 with rows 1–3 holding cover text "Capitalization Table as of [Date]" / blank / "[Effective]".
- Expected: parser scans rows 1–12, picks row 4 as header, parses 2 classes successfully.
- Pass criterion: ParseReport.cap_table_sheet set and 2 classes parsed.
- Spec section: §1.1 ("Header-row detection scans the first 12 rows").

**AUDIT-P0-POS-003 — Tab named "Capitalization" recognized by whitelist.**
- Source: NVCA layout; sheet name = `Capitalization`.
- Expected: parse succeeds. Spec §1.1 says `CAP_TABLE_TAB_NAMES` whitelist includes "Capitalization".
- Pass criterion: parse succeeds without ValueError.

**AUDIT-P0-POS-004 — Singapore VIMA 1× non-participating Series A with pari-passu Series A1.**
- Source: VIMA 2.0 Long-Form Term Sheet (S3). NOTE: pari-passu is NOT supported in Phase 0 per §1.5; this test verifies the REFUSAL behavior. Moved to AUDIT-P0-NEG-005.
- This test ID retired in favor of: **AUDIT-P0-POS-004 — Singapore VIMA single-class Series A.** Series A, 1× non-participating, broad-based weighted average. Parse succeeds. Pass: model validates.
- Spec section: §1.1, §1.3.

**AUDIT-P0-POS-005 — Indian CCPS class parses with `CCPS` alias mapping to preferred.**
- Source: Swiggy DRHP (S10). CCPS row with `CCPS` in the class-type column. Per §1.1, "CCPS, RCPS, Ordinary, Equity Shares" alias to canonical `ShareClassType`.
- Expected: ShareClass with `type == preferred`. (LP must be present since type=preferred; supply 1× non-participating.)
- Pass criterion: type == preferred AND LP is non-null.
- Spec section: §1.1 enum coercion paragraph.

**AUDIT-P0-POS-006 — Date format `14th Feb '25` parses.**
- Source: §1.1 explicitly lists "ordinal-suffixed (`14th Feb '25`)" as a supported format.
- Expected: issue_date parses to 2025-02-14.
- Pass criterion: issue_date == date(2025, 2, 14).
- Spec section: §1.1.

**AUDIT-P0-POS-007 — Currency-symbol stripping handles Indian Rupee `₹`.**
- Source: §1.1 lists "₹" among stripped symbols. Use a Swiggy-style cap table with ₹100.50 PPS.
- Expected: issue_price == 100.50.
- Pass criterion: float value matches without symbol artifacts.

**AUDIT-P0-POS-008 — Subtotal row "Subtotal Preferred" silently skipped.**
- Source: NVCA layout with row labeled `Subtotal Preferred`. Per §1.1 subtotal rows detected by `_SUBTOTAL_PREFIXES` prefix match.
- Expected: subtotal row not in CapTable.share_classes; no warning emitted on it.
- Pass criterion: share_classes count matches non-subtotal rows.

**AUDIT-P0-POS-009 — Live-formula Excel exporter round-trip integrity.**
- Source: Cooley GO pro forma cap table (S5). Export to live-formula workbook per §1.6, open it (no edits), verify that Breakpoints sheet's computed values equal Python's WaterfallResult breakpoints.
- Expected: every breakpoint value matches within 1e-6 relative tolerance.
- Pass criterion: numeric equality at floating-point tolerance per §1.5 dedup tolerance.
- Spec section: §1.6.

**AUDIT-P0-POS-010 — Waterfall on participating-capped at 3× preferred.**
- Source: Aranca / Eqvista worked-example math (S24, S23). Single Series A with 1× participating capped at 3× LP. Compute waterfall.
- Expected: cap_reach_thresholds[Series A] = 3 × LP_amount + senior overhang (none for single class). pure_conversion_thresholds[Series A] exists. Breakpoints contain "Series A participation cap reached".
- Pass criterion: cap_reach_threshold equals 3× LP exactly within tolerance.
- Spec section: §1.5.

**AUDIT-P0-POS-011 — Non-participating preferred conversion threshold equals LP/proportion.**
- Source: Marko Djukic worked example (S24). Single non-participating Series A with 2M shares at $1 LP. With 8M common, conversion threshold V_conv solves V_conv × (2M / (2M+8M)) = $2M → V_conv = $10M.
- Expected: conversion_thresholds[Series A] == 10_000_000 within tolerance.
- Pass criterion: numeric equality.
- Spec section: §1.5.

**AUDIT-P0-POS-012 — Marginal allocation percentages sum to 1.0 per tranche.**
- Source: Cooley GO cap table (S5). Run waterfall, sum `marginal_allocation_pct` across classes in each tranche.
- Expected: per-tranche sum within float tolerance of 1.0.
- Pass criterion: |sum − 1.0| < 1e-9 per tranche.
- Spec section: §1.5 ("sum to 1.0 within float tolerance per tranche").

**AUDIT-P0-POS-013 — Snapshot diff identifies a renamed class.**
- Source: Construct two snapshots; in snapshot B rename "Series A Preferred" to "Series A-1 Preferred", everything else identical.
- Expected: ClassMatch status == "renamed", similarity > 0.6.
- Pass criterion: exactly one ClassMatch with status=="renamed" present.
- Spec section: §1.7 ("greedy best-match by Levenshtein similarity > 0.6").

**AUDIT-P0-POS-014 — Markdown audit memo contains all 8 required sections.**
- Source: Any valid cap table. Generate memo.
- Expected: Markdown contains section headers matching §1.8's 8 required sections in declared order. Each `[ANALYST: ...]` placeholder present where spec lists `[J]`.
- Pass criterion: regex match for every named section.

**AUDIT-P0-POS-015 — Session token is 8 URL-safe characters.**
- Source: §1.10 contract. Trigger a session creation (e.g., POST /upload of a valid file).
- Expected: redirect URL contains token matching `[A-Za-z0-9_-]{8}`.
- Pass criterion: regex match.

**AUDIT-P0-POS-016 — `/healthz` returns `{"status": "ok"}` with 200.**
- Source: §1.10.
- Pass criterion: exact JSON body match and HTTP 200.

**AUDIT-P0-POS-017 — Export bundle ZIP includes all four artifact types.**
- Source: §1.10 `/export/<token>.zip` row. Bundle includes JSON + static xlsx + live xlsx + memo.
- Expected: ZIP entries include exactly those four files (or supersets).
- Pass criterion: file list match.

**AUDIT-P0-POS-018 — `Cache-Control: no-store` on every response.**
- Source: §1.10 "All responses receive `Cache-Control: no-store` via after-request hook."
- Expected: header present on `/`, `/healthz`, any export, any review page.
- Pass criterion: header exact match on each of N sampled routes.

**AUDIT-P0-POS-019 — POOL-STALE finding triggers at 271 days.**
- Source: §1.4 rule 4 specifies "more than 270 days before the most recent preferred round's issue_date." Construct: most recent preferred issued 2025-01-01; granted pool issued 2024-04-05 (271 days earlier).
- Expected: finding with code `POOL-STALE`, severity warning.
- Pass criterion: finding present in output list.

**AUDIT-P0-POS-020 — Findings sorted blocker → warning → info, then by code.**
- Source: §1.4 output contract.
- Construct: cap table that triggers AD-MISSING (blocker), WARRANT (warning), VOTING-DIFF (info), AD-RATCHET (info).
- Expected: list order is AD-MISSING, WARRANT, AD-RATCHET, VOTING-DIFF.
- Pass criterion: exact code sequence.

**AUDIT-P0-POS-021 — Determinism: same input twice → byte-identical CapTable JSON.**
- Source: §6 invariant 6. Parse the NVCA-derived workbook twice, serialize with `model_dump_json()`.
- Expected: byte-identical strings.
- Pass criterion: SHA-256 equality.

#### Negative tests (Phase 0)

**AUDIT-P0-NEG-001 — Refusal claim: "no sheet name matches `CAP_TABLE_TAB_NAMES` → `ValueError("no cap-table tab found")`" (§1.1).**
- Input: Workbook with single sheet named "Sheet1" (no whitelist match).
- Expected: ValueError raised with exact message "no cap-table tab found". HTTP layer returns 400.
- Pass criterion: exception type + message exact match; HTTP status 400.

**AUDIT-P0-NEG-002 — Refusal claim: "If a row constructs a ShareClass that fails Pydantic validation ... row is skipped; a warning is appended; parsing continues" (§1.1).**
- Input: Workbook with one valid common row + one preferred row with no LP fields populated.
- Expected: preferred row skipped, ParseReport.warnings contains a warning citing the bad row. CapTable contains only the common row.
- Pass criterion: cap_table.share_classes length == 1, warnings non-empty.

**AUDIT-P0-NEG-003 — Refusal claim: "if the resulting CapTable itself fails model validation (e.g., zero share classes survived) → Pydantic `ValidationError`" (§1.1).**
- Input: Workbook where every row fails validation.
- Expected: ValidationError propagates; HTTP 400.
- Pass criterion: exception type match.

**AUDIT-P0-NEG-004 — Refusal claim: "Duplicate preferred seniority ranks → `ValueError("duplicate seniority ranks among preferred classes: [...]")`" (§1.3).**
- Input: Two preferred classes both with `seniority_rank == 1`.
- Expected: ValidationError with that exact message prefix.
- Pass criterion: error message starts with "duplicate seniority ranks among preferred classes".

**AUDIT-P0-NEG-005 — Refusal claim: pari-passu rejected (§1.5, §1.11 item 11).**
- Source: VIMA 2.0 (S3) — Singapore deals often have pari-passu Series A + A1.
- Input: Series A (seniority 1) + Series A1 (seniority 1), both preferred.
- Expected: same ValidationError as AUDIT-P0-NEG-004.
- Pass criterion: exception raised at model construction.

**AUDIT-P0-NEG-006 — Refusal claim: "File size > 8 MB → Flask returns HTTP 413" (§1.1).**
- Input: 8.5 MB xlsx upload to `/upload`.
- Pass criterion: HTTP 413.

**AUDIT-P0-NEG-007 — Refusal claim: "Image-only PDFs return `("", ["pdf-no-text-recovered"])`" (§1.2).**
- Source: Convert any scanned image to PDF. Or use a known image-only public PDF.
- Expected: extract_text returns empty body and exactly that warning code.
- Pass criterion: warning list contains `pdf-no-text-recovered`.

**AUDIT-P0-NEG-008 — Refusal claim: "Non-PDF uploads are rejected by the route layer with HTTP 400" (§1.2 / §1.10).**
- Input: Upload a .txt to `/upload_side_letter/<token>`.
- Pass criterion: HTTP 400.

**AUDIT-P0-NEG-009 — Refusal claim: "Pydantic `ConfigDict(extra='forbid')` — Unknown keys raise `ValidationError`" (§1.3).**
- Input: CapTable JSON with extra key `fancy_field`.
- Pass criterion: ValidationError on deserialization.

**AUDIT-P0-NEG-010 — Refusal claim: "If `type == participating_capped`: exactly one of `cap_multiple` or `cap_amount` must be set (not zero, not both)" (§1.3).**
- Input 1: participating_capped LP with neither set.
- Input 2: participating_capped LP with both set.
- Expected: both raise ValidationError.
- Pass criterion: 2-of-2 raises.

**AUDIT-P0-NEG-011 — Refusal claim: LP `cap_amount` set must be `≥ amount` (§1.3).**
- Input: LP amount=1_000_000, cap_amount=500_000.
- Expected: ValidationError.
- Pass criterion: exception raised.

**AUDIT-P0-NEG-012 — Refusal claim: "preferred must have LP" (§1.3 `preferred_must_have_lp` validator).**
- Input: preferred class with `liquidation_preference == None`.
- Pass criterion: ValidationError.

#### Adversarial tests (Phase 0) — probing spec gaps

**AUDIT-P0-ADV-001 — Mixed-language cap table (Bahasa + English).**
- Source: A real Indonesian startup might have columns like `Nama Kelas | Saham | Harga`. The spec's synonym map is documented as English-only ("class_name", "shares").
- Spec says: §1.1 lists synonyms but does not enumerate non-English ones.
- Expected behavior under cross-cutting invariants: parser should refuse with a clear ValueError citing missing required column ("class_name and/or shares not found"), not fabricate.
- **SPEC GAP: §1.1 does not address multilingual headers.** A real Indonesian engagement WILL hit this. Suggested spec addition: enumerate non-English synonyms or document that non-English headers require the `manual_column_mapping` parameter.

**AUDIT-P0-ADV-002 — Multi-currency cap table (USD common + SGD preferred).**
- Source: VIMA (S3) — a Singapore startup may issue founders' common in one currency and the round LP in another, especially if the round is denominated in USD but Singapore-resident.
- Spec says: §1.11 item 9 — "No multi-currency FX conversion. All amounts assumed to be in the company's home currency." §1.3 — "Currency mismatch within a single CapTable: not enforced."
- Expected: spec explicitly allows the analyst to mismatch currencies; the system does NOT catch it.
- **SPEC GAP: NO finding is emitted to flag the analyst that they have mixed currencies.** A determinated auditor would catch this; the spec relies on the analyst noticing. Suggested spec addition: §1.4 should add a rule `CURRENCY-MISMATCH` of severity warning when issue_price values across classes vary by >50% in raw magnitude AND `Company.currency_symbol` differs between rows in the source workbook. (Detection from source workbook, not from CapTable, since CapTable doesn't store per-class currency.)

**AUDIT-P0-ADV-003 — A YC MFN-only post-money SAFE with no cap.**
- Source: YC standard deal (S6); Y Combinator's post-money MFN SAFE has NO valuation cap and NO discount. The §1.3 SAFE model has `valuation_cap: Optional`, `discount_rate: Optional`, `conversion_trigger_threshold: Optional`.
- Expected: the SAFE record can be constructed with all three Optional fields = None and `principal` set. It will pass validation.
- **SPEC GAP: §1.4 SAFE-UNCONVERTED rule fires only when `conversion_trigger_threshold` is set. An MFN-only SAFE will silently linger in `safes_outstanding` with no checklist flag.** Suggested spec addition: emit a warning when a SAFE is missing both cap and discount (true MFN-only) AND a preferred round has been issued after the SAFE's issue_date.

**AUDIT-P0-ADV-004 — Pre-money SAFE (older YC template) outstanding alongside post-money SAFEs.**
- Source: Cooley GO YC SAFE generator (S4) — both pre- and post-money templates downloadable. A real cap table may have both.
- Spec says: §1.3 SAFE model has no `template_variant` field. Pre vs post-money math differs in dilution.
- **SPEC GAP: §1.3 SAFE model does not record whether the SAFE is pre-money or post-money.** The downstream analyst (per §1.11 item 7) computes conversion manually, so this is arguably out of system scope — but the audit memo can't cite a fact the model didn't store. Suggested spec addition: SAFE.template_variant ∈ {pre_money, post_money, mfn_only, custom}.

**AUDIT-P0-ADV-005 — Charter clause: "Senior Preferred have right of first refusal on all future preferred issuances within 30 days."**
- Source: NVCA Model Cert (S1) Section on protective provisions / preemptive rights. This is a side-letter-like protective provision usually in the charter itself.
- Spec says: §1.3 ShareClass has no field for protective provisions; §1.4 only flags `VOTING-DIFF` from a free-text `voting_differential` string.
- **SPEC GAP: §1.3 has no structured field for protective provisions / preemptive rights / drag-along / ROFR.** These are standard NVCA terms. Spec §4.1 enumerates the Phase 3 expansion to 50 rules including "ROFR/co-sale" — but the data model gap means even in Phase 3, those rules will have to mine a free-text `note` field. Suggested spec addition: `ShareClass.protective_provisions: list[str]` or a side_letter-style attachment with structured tags.

**AUDIT-P0-ADV-006 — Cap table with negative-shares correction row.**
- Source: Real-world: CFO Excels often include reconciliation rows like "[Adjustment for buyback]: -50,000 shares".
- Spec says: §1.3 `shares_outstanding: int, must be ≥ 0`.
- Expected: row rejected with a Pydantic validation error; per §1.1 the row is skipped with a warning.
- **SPEC GAP: The spec does not document how the parser should handle an explicit negative-correction row.** Real workbooks use them as accounting adjustments. The system silently drops them, potentially over-reporting share counts. Suggested spec addition: §1.1 should warn explicitly when a numeric value is non-finite or negative, with code `numeric-negative-row-dropped`.

**AUDIT-P0-ADV-007 — Encrypted PDF side letter.**
- Source: Real side letters from law firms are often password-protected.
- Spec says: §1.2 only addresses image-only PDFs.
- **SPEC GAP: §1.2 does not address encrypted PDFs.** Expected behavior under invariants: refuse with structured error, not silent failure. Suggested spec addition: extract_text returns ("", ["pdf-encrypted"]) — same shape as `pdf-no-text-recovered`.

**AUDIT-P0-ADV-008 — Excel file with 10,000 holder rows (Indian-style).**
- Source: Lenskart DRHP (S11) — large companies routinely have thousands of equity holders.
- Spec says: §1.1 has no row-count limit, only 8 MB size limit.
- Expected behavior: parser runs successfully but if every row attempts to be its own ShareClass, duplicate-name validation would explode.
- **PHASE-MISALIGNMENT: this is what §3.3 (holder-level rollup, Phase 2) is for. Phase 0 explicitly does not support it.** Test pass = parser fails or produces a useless output. Confirms the Phase 2 gap is real and grounded.

**AUDIT-P0-ADV-009 — Right-to-left language in `Company.name` (Arabic or Hebrew startup).**
- Spec says: §1.3 `name: str (required)`; no character-set restriction.
- Expected: stored verbatim, displayed in HTMX UI.
- **SPEC GAP: §1.10 templates don't promise RTL rendering.** Suggested spec addition: explicit promise that the UI renders Unicode including RTL, or explicit refusal documented.

**AUDIT-P0-ADV-010 — Date in Excel cell stored as Excel serial (e.g., 44927 for 2023-01-01).**
- Source: openpyxl reads serial numbers as `datetime` automatically. So this should "just work" — but if the cell is formatted as text and contains "44927", the parser will try to coerce to a date via the 13-format list and fail.
- Spec says: §1.1 lists 13 documented date formats; serial-number-as-text is not among them.
- Expected: issue_date becomes None with no warning emitted (per §1.1: "Unparseable dates become `None` with no warning emitted on that row").
- **SPEC GAP: §1.1 explicitly chooses NOT to warn on unparseable dates. This means a typo in a date silently produces a missing date that downstream rules (e.g., POOL-STALE) cannot evaluate — and they don't fire a "missing date" warning either.** Suggested spec addition: emit a `date-unparseable` warning when issue_date is required for any rule the row would otherwise satisfy.

#### End-to-end scenarios (Phase 0)

**AUDIT-P0-E2E-001 — NVCA Series A: upload → resolve a SAFE → export memo.**
1. Source: NVCA Cert (S1) + a single YC post-money SAFE (S4) with $500k principal, $10M cap.
2. POST `/upload` with cap table containing common + Series A preferred + a SAFE row in `Convertibles` tab.
3. GET `/review/<token>` — verify SAFE-UNCONVERTED finding present (assuming the SAFE's `conversion_trigger_threshold` was set and the round meets it; if SAFE has no trigger, finding does NOT fire — see ADV-003).
4. POST `/resolve/<token>/safe/<safe_id>` with target class = "Series A Preferred", shares = 50_000 (derived by analyst).
5. GET `/export/<token>.md` — verify memo's "Convertibles" section now shows resolved-SAFE entry.
6. Pass criterion: each step returns expected HTTP status per §1.10; final memo Markdown contains the resolution citation.

**AUDIT-P0-E2E-002 — Indian CCPS cap table: upload → diff against prior snapshot.**
1. Source: Swiggy-style DRHP cap table (S10). Construct snapshot A with Series A CCPS.
2. POST `/upload` with snapshot A.
3. Construct snapshot B (analyst's revised version): same Series A but with corrected conversion_ratio.
4. POST `/diff` with both files.
5. Expected: `compare.html` rendered with diff showing modified conversion_ratio under Series A.
6. Pass criterion: diff result lists exactly one FieldDelta on the Series A class for `conversion_ratio`.

#### Performance / load tests (Phase 0)

Phase 0 makes no performance promises (§1.1 "No latency or throughput SLO promised"). Therefore there are no performance assertions; the only check is: parser does not crash on a documented-input-size workbook. **AUDIT-P0-PERF-001** — Parse an 8 MB workbook with 200 classes. Pass = no crash, no timeout under 60s. (60s is auditor's reasonable upper bound, not a spec promise.)

---

### 2.2 Phase 1 — Observe (Days 1–30)

**Spec contract being tested:** §2 (sub-sections 2.1, 2.2, 2.3, 2.4).

Phase 1 produces artifacts, not code. Auditing is documentary, not technical.

#### Positive tests (Phase 1)

**AUDIT-P1-POS-001 — Workflow map exists and has 6 pages.**
- Spec §2.1 requires "at least 6 pages, one per workflow phase."
- Pass criterion: the map's PDF/Doc has ≥ 6 distinct one-page sections matching the named phases.

**AUDIT-P1-POS-002 — Each workflow-map phase has all 6 fields.**
- Spec §2.1 lists: Engagement column header, Observed activities, Time tally (hours, decimal), Tool intersection (would-have-helped / would-have-hurt / irrelevant), Data format observed, Owner.
- Pass criterion: per-page presence check for all 6.

**AUDIT-P1-POS-003 — Time tallies have a contemporaneous shadow-note source.**
- Spec §2.1 "Evidence rule: every time tally must be backed by a contemporaneous shadow note (timestamp + free-text observation)."
- Auditor procedure: spot-check 10% of time-tally cells; for each, request the shadow note. Pass = each spot-checked cell has a note dated within 48h of the observed activity.

**AUDIT-P1-POS-004 — Day-30 pitch is delivered and ≤ 2 pages.**
- Spec §2.2 "one page recommended, up to two pages."
- Pass criterion: file exists, page count ≤ 2.

**AUDIT-P1-POS-005 — Pitch has all three sections.**
- Spec §2.2 sections: "What I observed", "What would have changed with the tool", "The proposal".
- Pass: each section header present.

**AUDIT-P1-POS-006 — Pitch contains at least one explicit `would-have-saved-nothing` line.**
- Spec §2.2 "Must include at least one explicit `would-have-saved-nothing` line where applicable."
- Pass: search regex for "saved-nothing" or equivalent honest-zero phrasing returns ≥ 1 hit.

**AUDIT-P1-POS-007 — Hours saved/lost expressed with directionality.**
- Spec §2.2 "Hours saved / lost must be expressed as a per-engagement number with a directionality (+ for time saved, − for time added by tool friction)."
- Pass: numeric values have explicit + or − prefix.

**AUDIT-P1-POS-008 — Evelyn's decision recorded verbatim.**
- Spec §2.3 "Evelyn's decision is recorded verbatim in the pitch document after the meeting."
- Pass: a section in the pitch document contains a quoted statement attributed to Evelyn with timestamp.

#### Negative tests (Phase 1)

**AUDIT-P1-NEG-001 — Refusal claim: "No anonymized aggregate ('teams typically take 6 hours') in place of concrete per-engagement observation" (§2.1).**
- Auditor scan: search workflow map for phrases like "typically", "usually", "teams tend to".
- Pass = 0 hits; or each hit accompanied by per-engagement number alongside.

**AUDIT-P1-NEG-002 — Refusal claim: "No tool advocacy phrasing in the map itself" (§2.1).**
- Scan for: "the tool would help", "the tool is great", marketing phrasing.
- Pass = 0 hits.

**AUDIT-P1-NEG-003 — Refusal claim: "No revenue figures. No headcount-savings claims. No timeline commitments embedded in the pitch" (§2.2).**
- Scan pitch for dollar signs, FTE counts, week/month commitments.
- Pass = 0 hits, OR each hit has a footnote marking it as observation only.

**AUDIT-P1-NEG-004 — Refusal claim: "Zero new production code is shipped in Phase 1" (§2.4).**
- Auditor procedure: `git log` on main branch between Day 1 and Day 30; any commit touching `src/` or `app.py` is a violation UNLESS it's a "personal-laptop fix that has zero observable effect on the public artifact" (which is ambiguous and a §5 gap).
- Pass = no commits to production paths.

#### Adversarial tests (Phase 1)

**AUDIT-P1-ADV-001 — Evelyn picks Path B; does the auditor recognize that as a successful outcome?**
- Spec §2.3 "Path B is chosen iff any of the above three conditions fails, OR Evelyn explicitly prefers focus on engagement work."
- Auditor: Path B chosen is NOT a Phase 1 failure. Phase 1 succeeded if the pitch was delivered honestly and Evelyn made a clean decision.
- Pass criterion: the audit report flags Path-B-chosen as a CORRECT Phase 1 outcome, not a failure. (Tests the auditor's own discipline.)

**AUDIT-P1-ADV-002 — Pitch quantification arithmetic is internally consistent.**
- Auditor: re-add the "hours saved" deltas; verify total weekly impact arithmetic matches stated hours/week.
- **SPEC GAP: §2.2 says "Total weekly time impact must be expressed in hours/week based on observed engagement volume" but doesn't define "engagement volume" measurement window.** Suggested spec addition: define the observation window explicitly (e.g., "engagement volume measured over the 30-day observation period").

**AUDIT-P1-ADV-003 — "Personal-laptop fix" loophole in §2.4.**
- §2.4 carve-out "except for personal-laptop fixes that have zero observable effect on the public artifact" is undefined. A clever builder could push a commit there and claim no effect.
- **SPEC GAP: §2.4 carve-out has no enforcement mechanism.** Suggested spec addition: any code commit during Phase 1 to any tracked file is a violation; "personal-laptop" must mean files not under version control.

#### End-to-end scenarios (Phase 1)

**AUDIT-P1-E2E-001 — Full Phase 1 documentary chain.**
1. Verify three shadow-note bundles exist for three named engagements.
2. Verify the workflow map references all three.
3. Verify the pitch's "What I observed" cites time tallies that map to specific cells in the workflow map.
4. Verify Evelyn's decision is recorded.
5. Pass = chain of evidence reads cleanly from raw notes → map → pitch → decision.

**AUDIT-P1-E2E-002 — Path-B-chosen scenario.**
- Simulate the case where Evelyn picks Path B. Verify §2.3 criteria are correctly applied; the pitch document records the failing condition (e.g., "Engineering greenlight unreachable"); subsequent phases (2+) do NOT begin.
- Pass = audit report cleanly closes the engagement after Phase 1.

#### Performance / load (Phase 1)
None — no performance promises in Phase 1.

---

### 2.3 Phase 2 — Internal Pilot (Months 2–3)

**Spec contract:** §3 (sub-sections 3.1, 3.2, 3.3, 3.4, 3.5).

#### Positive tests (Phase 2)

**AUDIT-P2-POS-001 — Qapita adapter returns a canonical `CapTable` matching §1.3 schema.**
- Source: §3.1 contract — output is "A validated `CapTable` matching the Phase 0 Pydantic schema in §1.3 exactly."
- Test: call `ingestion/qapita_api.py` with a mocked Qapita source returning a Series A preferred. Verify returned CapTable validates against Phase 0 schema (no extra keys, all required fields present or marked unknown).
- Pass: CapTable validates; ParseReport has field-level provenance.

**AUDIT-P2-POS-002 — Qapita pull completes in < 5s for 50-class cap table.**
- Source: §3.1 "Cold-start pull for a 50-class cap table: under 5 seconds wall-clock."
- Construct 50-class fixture using mixed NVCA/VIMA/SEBI-derived shapes (S1, S3, S10).
- Pass: wall-clock < 5s on Qapita's reference environment (definition required from spec — see §5).

**AUDIT-P2-POS-003 — Snapshot is immutable after creation.**
- Source: §3.2 "snapshots table has NO UPDATE statement in any production code path."
- Test: attempt to UPDATE a snapshot row directly through the application API. Expected: `SnapshotImmutableError`.
- Pass: exception type match.

**AUDIT-P2-POS-004 — Engagement lifecycle transition `open → review → signed` works.**
- Source: §3.2 lifecycle. Analyst transitions open→review; partner transitions review→signed (after resolving all blockers).
- Pass: status field updates correctly; audit event recorded for each.

**AUDIT-P2-POS-005 — Partner cannot sign with unresolved blocker.**
- Source: §3.2 "review → signed ... Refused if any blocker finding is unresolved."
- Construct: engagement with one AD-MISSING (blocker) finding unresolved.
- Pass: HTTP 409 `engagement-invalid-transition`.

**AUDIT-P2-POS-006 — Read-only auditor magic-link token expires after configured TTL.**
- Source: §3.2 "Read-only auditor role uses a scoped magic-link token issued by a partner; expires after configurable TTL (default 30 days)."
- Test: issue token, fast-forward clock 31 days, attempt access.
- Pass: HTTP 403 with `read-only-token` code (or token-expired equivalent — spec doesn't name the exact expired-code; this is a §6 gap).

**AUDIT-P2-POS-007 — Holder-level rollup heuristic 1: explicit class column groups correctly.**
- Source: §3.3 detection heuristic 1. Construct: 30 holders, each row has an explicit `Class` column with values from {Series A, Series B}.
- Pass: rollup produces 2 ShareClasses; HolderDetail sidecar has 30 rows.

**AUDIT-P2-POS-008 — Holder-level rollup heuristic 2: issue-date + price clustering.**
- Source: §3.3 heuristic 2. Construct: 47 holders, all with identical (issue_date=2024-04-15, issue_price=$5.20, instrument=CCPS). No explicit class column.
- Pass: rollup produces 1 ShareClass; ParseReport contains `rollup-applied` warning with message citing "Grouped 47 holders" + date.

**AUDIT-P2-POS-009 — Holder-level rollup confidence < 0.80 surfaces UI fallback.**
- Source: §3.3 heuristic 4. Construct ambiguous data (e.g., 5 holders with 5 different issue dates).
- Pass: response is `HolderRollupAmbiguous` error with proposed groupings; UI banner text exactly `"Automated grouping confidence is below 80%. Please confirm or remap the proposed share classes."`.

**AUDIT-P2-POS-010 — Big-4 PDF memo contains all 11 required sections in order.**
- Source: §3.4 list of sections 1–11 plus Appendix A and B.
- Generate memo; extract section headers from PDF.
- Pass: exact section name + order match.

**AUDIT-P2-POS-011 — PDF memo contains version stamp footer on every page.**
- Source: §3.4 "Footer with version stamp `vYYYY-MM-DD-HHMMSS-shortcommit`."
- Extract every page footer; regex match.
- Pass: regex matches on every page.

**AUDIT-P2-POS-012 — PDF memo signature block names reviewer and partner.**
- Source: §3.4 "Reviewer name + role + date. Partner name + role + date."
- Pass: last page contains both blocks with all four fields each.

**AUDIT-P2-POS-013 — Two real engagements run end-to-end with analyst sign-off in audit log.**
- Source: §3.5 acceptance criterion 1. Audit log query for `event_type == "engagement.signed"` with `actor.role == analyst`.
- Pass: ≥ 2 such events exist by end of Month 3.

#### Negative tests (Phase 2)

**AUDIT-P2-NEG-001 — Refusal: Qapita adapter NEVER writes back to Qapita.**
- Source: §3.1 "The Qapita adapter NEVER writes back to Qapita's source. Read-only."
- Test: code-path inspection — verify only `SELECT` (no `UPDATE`/`INSERT`) issued against Qapita's data source. Network-traffic capture during a Qapita-pull operation; assert no write methods used.
- Pass: traffic analysis confirms read-only.

**AUDIT-P2-NEG-002 — Refusal: Qapita adapter does not fabricate missing fields.**
- Source: §3.1 "Does NOT fabricate a default value."
- Construct: Qapita source missing `anti_dilution.variant` field.
- Pass: returned CapTable has `anti_dilution.variant == None` AND ParseWarning code `qapita-source-missing-anti_dilution.variant` present.

**AUDIT-P2-NEG-003 — Refusal: cross-engagement read returns 403 `tenancy-violation`.**
- Source: §3.2.
- As user A on engagement X, attempt to GET engagement Y owned by user B.
- Pass: HTTP 403 with code `tenancy-violation`.

**AUDIT-P2-NEG-004 — Refusal: query without `engagement_id` raises `TenancyError`.**
- Source: §3.2 "every query takes `engagement_id` as a required argument; queries without it raise."
- Test: call any data-access method without engagement_id.
- Pass: `TenancyError` raised.

**AUDIT-P2-NEG-005 — Refusal: UPDATE on `resolution` raises `ResolutionImmutableError`.**
- Pass: exception type match.

**AUDIT-P2-NEG-006 — Refusal: DELETE on `audit_event` raises `AuditLogImmutableError`.**
- Pass: exception type match.

**AUDIT-P2-NEG-007 — Refusal: Analyst cannot transition to signed.**
- Source: §3.2 role table.
- Pass: HTTP 403 `role-not-permitted`.

**AUDIT-P2-NEG-008 — Refusal: PDF generation blocked when blockers unresolved.**
- Source: §3.4 "Cannot be generated if engagement has any unresolved blocker findings. Error code: `pdf-blockers-outstanding`."
- Pass: HTTP error with that code; UI banner exactly `"Cannot generate audit memo — N blocker findings unresolved. Resolve or document each before generating."` where N is correctly substituted.

**AUDIT-P2-NEG-009 — Refusal: PDF generation blocked when no reviewer assigned.**
- Source: §3.4. Error code `pdf-no-reviewer`. UI banner exact-match.
- Pass: HTTP error + banner match.

**AUDIT-P2-NEG-010 — Refusal: rollup never silently guesses below 0.80 confidence.**
- Source: §3.3. Construct: ambiguous data with confidence 0.50.
- Pass: `HolderRollupAmbiguous` returned; no CapTable produced; payload contains proposed groupings.

#### Adversarial tests (Phase 2) — probing spec gaps

**AUDIT-P2-ADV-001 — Concurrency: two analysts edit the same engagement simultaneously.**
- Scenario: Analyst A and Analyst B both have `engagement.status == open`; both POST a resolution simultaneously. The spec §3.2 says "Two analysts open the same engagement → race conditions" is a Phase 0 problem the Phase 2 model solves.
- Spec on Phase 2 concurrency: silent.
- Expected: both POSTs succeed; both create separate snapshots; the `superseded_by` chain reflects both edits (snapshot order is deterministic by timestamp).
- **SPEC GAP: §3.2 does not define ordering for concurrent writes.** What if both POSTs arrive within 1ms? Spec is silent. Suggested addition: spec must define either pessimistic lock (analyst must "claim" engagement) or optimistic concurrency (POSTs include the parent snapshot id; server rejects if not the head).

**AUDIT-P2-ADV-002 — A YC MFN-only SAFE pulled from Qapita's source.**
- Source: YC standard deal (S6); Qapita's data model may or may not capture MFN-only SAFEs.
- Spec says §3.1: if source missing a required field, mark unknown.
- **SPEC GAP: §3.1 doesn't specify how the adapter detects "required" vs "optional" Qapita-source fields. The mapping table is undefined.** Suggested addition: an explicit field-mapping document checked into the repo, versioned alongside the rule pack.

**AUDIT-P2-ADV-003 — Right of erasure (GDPR/PDPA) vs. audit-log immutability.**
- A data-subject (employee with vested options) invokes their right to erasure. The spec §3.2 audit log is append-only and stores actor user_ids. Singapore PDPA and EU GDPR both grant erasure rights.
- **SPEC GAP: §3.2 has no mechanism for PII redaction within the immutable audit log.** Suggested addition: per Big 4 norms, retain the audit log but allow redaction of PII fields (replace user names with internal ID + redaction note) under documented legal authority. This must be itself an audit event.

**AUDIT-P2-ADV-004 — Holder-level rollup confidence is in (0.80, 0.81) — boundary fuzz.**
- Source: §3.3 threshold is 0.80; what happens at exactly 0.80?
- Spec: "< 0.80" triggers fallback. So 0.80 exactly does NOT trigger.
- Pass = at 0.80 the rollup proceeds silently; at 0.7999 the fallback fires. (Tests boundary correctness.)

**AUDIT-P2-ADV-005 — Holder name contains injection: `'; DROP TABLE holders;--`.**
- Spec §3.3 doesn't address injection.
- Expected: stored verbatim (per the "store, don't infer" register); rendered safely in UI.
- **SPEC GAP: §3.4 PDF memo cites `snapshot://<snapshot_id>/<sheet>/<cell_ref>` hyperlinks; spec doesn't address URL injection / template escaping.** Suggested addition: explicit promise that all rendered cells use safe HTML/PDF escaping.

**AUDIT-P2-ADV-006 — Engagement signed, then a snapshot must be added later (subsequent event).**
- Source: §3.2 lifecycle `signed → archived` only allowed by system cron. Spec is silent on whether new snapshots can attach to a signed engagement.
- **SPEC GAP: A real "subsequent events" memo addendum is sometimes needed after sign-off (e.g., a down-round happens between signing and report delivery).** Suggested addition: a `reopen` transition `signed → review` with partner authorization, generating an audit event.

**AUDIT-P2-ADV-007 — A Lenskart-DRHP-style cap table with FII (foreign institutional investor) holders.**
- Source: Lenskart DRHP (S11). Foreign holders trigger FEMA pricing rules — but the spec's Phase 2 doesn't have FEMA rules yet (those come in Phase 3 per §4.1).
- Expected: rollup ingests as normal class structure; no FEMA-specific check.
- **PHASE-LIMIT ACKNOWLEDGED: not a spec gap; rolls forward to Phase 3 test set.**

**AUDIT-P2-ADV-008 — PDF generation while engagement is being edited.**
- A partner triggers PDF generation; mid-render, an analyst creates a new snapshot. Which snapshot does the PDF cite?
- **SPEC GAP: §3.4 PDF "cites every cell to snapshot_id" — but doesn't specify which snapshot is used when multiple exist mid-render.** Suggested addition: PDF generation must be atomic against a frozen snapshot id, supplied as a generation parameter.

#### End-to-end scenarios (Phase 2)

**AUDIT-P2-E2E-001 — Full pilot engagement on a real Indian DRHP-shaped cap table.**
1. Source: Swiggy-style cap table (S10) re-shaped as holder-level Excel with 87 holders.
2. Analyst uploads via `/upload` (Phase 0 Excel path; spec doesn't say holder-level upload uses a new route in Phase 2, but functionally the parser must detect holder-level and trigger §3.3 rollup).
3. System detects holder-level → applies heuristic 2 (issue-date clustering) → produces class-level CapTable + HolderDetail sidecar.
4. ParseReport contains `rollup-applied` warnings.
5. Analyst confirms grouping in UI.
6. Snapshot created (immutable). Audit event `snapshot.created` recorded.
7. Checklist runs; AD-MISSING blocker raised on one class.
8. Analyst resolves via `/resolve/.../anti_dilution/...`; new snapshot created; resolution recorded.
9. Engagement transitions open → review (analyst), review → signed (partner).
10. Partner generates PDF memo — succeeds because no blockers remain.
11. PDF contains all 11 sections; cover sheet names client + valuation date + reviewer.
12. Pass criterion: each step produces the spec-documented outputs and audit events.

**AUDIT-P2-E2E-002 — Auditor (read-only) read flow.**
1. Partner issues magic-link token to a Big 4 auditor (TTL default 30 days).
2. Auditor uses token to GET engagement: snapshots, resolutions, audit events, exports.
3. Auditor attempts to POST a resolution — HTTP 403 `read-only-token`.
4. Auditor exports PDF memo — succeeds (read).
5. PDF artifact read is logged in `audit_event` per §3.4 persistence contract.
6. Pass: token grants read on all artifacts of the engagement, writes refused, all reads logged.

#### Performance / load tests (Phase 2)

**AUDIT-P2-PERF-001 — Qapita cold-start pull < 5s for 50-class cap table.**
- Source: §3.1.
- 50 classes spanning NVCA/VIMA/CCPS shapes.
- Pass: wall-clock < 5.0s.

**AUDIT-P2-PERF-002 — Concurrent read load on engagement listing.**
- Spec is silent on concurrent-read SLO. Auditor measures baseline, reports as info, no pass/fail.
- **SPEC GAP: no concurrent-load SLO documented.** Suggested addition.

---

### 2.4 Phase 3 — Hardening (Months 4–6)

**Spec contract:** §4 (sub-sections 4.1, 4.2, 4.3, 4.4, 4.5, 4.6).

#### Positive tests (Phase 3)

**AUDIT-P3-POS-001 — Rule pack version is semver and frozen at engagement open.**
- Source: §4.1.
- Create an engagement; verify `engagement_pack_binding` row exists with `bound_at` timestamp and a semver-formatted version (regex `^\d{4}\.\d+\.\d+$`).
- Pass: regex + presence.

**AUDIT-P3-POS-002 — Adding a rule creates a new pack version.**
- Source: §4.1 rule add/remove process.
- Add a rule (any); query pack table.
- Pass: new pack row with incremented version; previous head's `effective_to` set to new pack's `effective_from − 1 day`.

**AUDIT-P3-POS-003 — Re-running a historical engagement uses the bound pack.**
- Source: §4.1 binding behavior.
- Engagement bound to pack 2026.1.0; new pack 2026.2.0 published; re-run checklist on the historical engagement.
- Pass: findings produced match pack 2026.1.0's rule set, NOT 2026.2.0.

**AUDIT-P3-POS-004 — Pari-passu seniority (1, 1) and (1, 2) accepted.**
- Source: §4.2 + VIMA 2.0 (S3) Singapore Series A + A1 pari-passu.
- Construct Series A with `seniority_tier=(1, 1)`, Series A1 with `seniority_tier=(1, 2)`.
- Pass: CapTable validates.

**AUDIT-P3-POS-005 — Pari-passu LP shared proportionally.**
- Source: §4.2 "Within the group, the LP pool is allocated proportionally to each class's LP_amount share of the group's total LP."
- Construct: Series A LP_amount=$2M, Series A1 LP_amount=$1M; waterfall computes LP-cleared breakpoint at $3M total, with allocation 2/3 and 1/3 within the group.
- Pass: tranche marginal allocation reflects 0.667 / 0.333 within the LP regime for the pari-passu group.

**AUDIT-P3-POS-006 — Backwards-compat migration: legacy `seniority_rank: 1` → `seniority_tier: (1, 0)`.**
- Source: §4.2 backwards compatibility.
- Load a Phase 0 CapTable JSON; verify it parses with the new schema using default tier mapping.
- Pass: legacy JSON loads without error; serialized form emits `seniority_rank` for Phase 0 consumers.

**AUDIT-P3-POS-007 — OCR fallback engaged when pdfplumber yields < 100 chars.**
- Source: §4.3 pipeline step 2.
- Use an image-only PDF (constructed; per S1 NVCA charter rendered as image).
- Pass: OCR backend called; text returned; confidence float in [0, 1].

**AUDIT-P3-POS-008 — OCR confidence < 0.85 surfaces banner.**
- Source: §4.3.
- Use a low-quality scan that yields confidence ~0.7.
- Pass: UI banner copy exactly `"OCR confidence below 0.85. Recommend manual review of the original PDF before relying on extracted text."`.

**AUDIT-P3-POS-009 — Structured snapshot diff identifies field-level changes with rule_implications.**
- Source: §4.4. Two snapshots differ in `share_classes[Series B-1].liquidation_preference.cap_multiple` (3.0 → None).
- Pass: FieldDiff with that path, `change_type == "removed"`, `rule_implications` contains a reference to whichever bound-pack rule applied to capped LPs.

**AUDIT-P3-POS-010 — Diff of two 50-class cap tables < 500ms.**
- Source: §4.4 performance contract.
- Pass: wall-clock < 0.5s on reference environment.

**AUDIT-P3-POS-011 — ≥ 30 rules in head pack.**
- Source: §4.6 acceptance criterion 2.
- Pass: rule count ≥ 30 across categories matching §4.1 (anti-dilution 6, participation 4, SAFE 6, option pool 5, voting 5, round 6, side-letter 5, jurisdiction ~12).

**AUDIT-P3-POS-012 — Every rule has a citation field.**
- Source: §4.1 coverage requirement.
- Inspect rules_json; for each rule, verify non-empty `citation` field.
- Pass: 100% have citations.

#### Negative tests (Phase 3)

**AUDIT-P3-NEG-001 — Refusal: expired rule pack cannot be set as head.**
- Source: §4.1 "Error: `rule-pack-expired`."
- Test: attempt to publish a new pack with `effective_to` in the past.
- Pass: error code match.

**AUDIT-P3-NEG-002 — Refusal: rule pack mutate after creation.**
- Source: §4.1 "Error on UPDATE: `rule-pack-immutable`."
- Pass: error code match.

**AUDIT-P3-NEG-003 — Refusal: duplicate `(rank, sub_rank)` tier pairs.**
- Source: §4.2 `ValueError("duplicate seniority tier (rank, sub_rank): ...")`.
- Pass: error message starts with "duplicate seniority tier".

**AUDIT-P3-NEG-004 — Refusal: NO LLM extraction of structured fields from OCR text.**
- Source: §4.3 "NEVER any LLM extraction of structured fields from OCR text."
- Test: instrument the OCR pipeline; verify no outbound network calls to any LLM endpoint.
- Pass: network capture shows zero calls to *.openai.com / *.anthropic.com / *.googleapis.com/generativelanguage.

#### Adversarial tests (Phase 3)

**AUDIT-P3-ADV-001 — Three-way pari-passu (1, 1), (1, 2), (1, 3).**
- Source: §4.2 examples only show two-way pari-passu. Real Indian round structures occasionally have 3+ tranches pari-passu within a Series (e.g., Series B led by VC with strategic co-investors all pari-passu).
- Expected: model accepts all three; waterfall allocates LP proportionally across three.
- **SPEC GAP: §4.2 doesn't explicitly state N-way pari-passu is supported; only 2-way examples given.** Suggested addition: state "any cardinality" explicitly.

**AUDIT-P3-ADV-002 — Pari-passu but different LP types within a group (1× non-part + 1× participating).**
- Spec §4.2 says pari-passu classes share the LP-paying group; silent on whether they can have different LP types.
- Real-world: a co-investor side letter could grant participating LP to one party in a pari-passu round.
- **SPEC GAP: undefined.** Suggested addition: spec must specify either "all pari-passu must share the same LP type" (refusal) or define semantics for mixed.

**AUDIT-P3-ADV-003 — Pari-passu and full-ratchet anti-dilution triggers simultaneously.**
- Real scenario: down-round triggers full ratchet on one of two pari-passu classes (per side letter); other doesn't have AD.
- Spec is silent on the interaction.
- **SPEC GAP.** Suggested addition: define interaction between §4.2 pari-passu allocation and §1.5 conversion-ratio handling for AD-adjusted classes.

**AUDIT-P3-ADV-004 — OCR on a multi-page PDF with mixed text-PDF + image pages.**
- Spec §4.3 pipeline triggers OCR when pdfplumber yield < 100 chars TOTAL.
- A 20-page side letter with 1 text page + 19 image pages might exceed 100-char threshold, never triggering OCR — but most of the content is unread.
- **SPEC GAP: §4.3 threshold is total-document, not per-page.** Suggested addition: per-page threshold OR per-page-area coverage check.

**AUDIT-P3-ADV-005 — OCR backend swap mid-engagement (data-residency policy change).**
- Spec §4.3 "OCR backend swappable via config." If a re-run later uses a different backend, results may differ.
- Determinism invariant (§6.6): "same input → same output."
- **SPEC GAP: OCR is inherently non-deterministic and backend-dependent. Determinism invariant doesn't carve OCR out.** Suggested addition: explicit carve-out for OCR with persistence of backend used per side letter.

**AUDIT-P3-ADV-006 — Schema evolution: a rule pack adds a new severity tier "critical".**
- Spec §4.1 doesn't constrain rule pack schema to existing severity values {blocker, warning, info}.
- Engagement bound to old pack consumes new severity → undefined.
- **SPEC GAP.** Suggested addition: severity enum is part of engine code, not rule pack JSON; rule pack JSON validated against engine version at bind time.

**AUDIT-P3-ADV-007 — California 25102(f) exemption rule fires when no California nexus exists.**
- Source: California Corporations Code §25102(f) (S19). Spec §5.4 lists this as Phase 4; here in Phase 3 test it for spec gap.
- **SPEC GAP: jurisdiction tagging on §4.1 rule pack is on the pack, not on individual rules.** A "US-CA" tagged pack would fire 25102(f) on engagements that aren't California-resident. Suggested addition: per-rule jurisdiction predicate.

**AUDIT-P3-ADV-008 — Indonesian dual-class share (OJK 2024 reg) — `voting_differential` field.**
- Source: OJK regulation summary (S22) + Dealstreetasia coverage of the dual-class rule.
- Spec §1.3 `voting_differential: Optional[str]` is free-text only.
- Construct: Indonesian PT with founder class 10:1 voting; CapTable records "10:1 voting" as string.
- Pass: VOTING-DIFF info finding fires.
- **SPEC GAP: the free-text is uncomputable. Rules can't query "voting ratio > 5".** Suggested addition: structured `voting_multiplier: Optional[float]` alongside the free-text.

#### End-to-end scenarios (Phase 3)

**AUDIT-P3-E2E-001 — Re-run an engagement 18 months later, against the bound rule pack.**
1. Engagement opened Month 4 bound to pack 2026.1.0.
2. Snapshot S1 captured; checklist run; resolutions recorded; engagement signed.
3. 18 months pass; new packs published up to 2027.6.0.
4. Auditor requests re-run.
5. System loads engagement → loads bound pack 2026.1.0 → re-runs checklist on S1 → emits identical findings.
6. Pass: findings byte-identical to original (determinism invariant).

**AUDIT-P3-E2E-002 — Image-PDF side letter ingested via OCR.**
1. Source: a scanned NVCA-style charter (constructed from S1 NVCA Cert rendered to image).
2. Analyst uploads via `/upload_side_letter/<token>`.
3. Pipeline tries pdfplumber → yields < 100 chars → OCR backend invoked.
4. Confidence returned; if < 0.85, banner shown.
5. Raw text stored verbatim in side letter body; analyst still enters structured fields.
6. Pass: side letter exists with body == raw OCR text + structured fields entered by analyst, NOT by LLM.

#### Performance / load (Phase 3)

**AUDIT-P3-PERF-001 — Diff of two 50-class cap tables < 500 ms (§4.4).**

**AUDIT-P3-PERF-002 — Checklist run on 50-class cap table with 30 rules — no SLO documented.**
- Auditor measures, reports as info.
- **SPEC GAP: no SLO on checklist run time.**

---

### 2.5 Phase 4 — Platform Play (Months 7–12)

**Spec contract:** §5 (sub-sections 5.1, 5.2, 5.3, 5.4, 5.5).

#### Positive tests (Phase 4)

**AUDIT-P4-POS-001 — OPM Backsolve solves for implied total equity value.**
- Source: §5.1 + Eqvista BioStart worked example (S23): Series A at $2.00 per share, pre-money $18M, raise $5M.
- Provide a MarketInputPack: vol=0.6, time=4.0 years, rf=0.04, dlom=0.30.
- Expected: solver converges; implied_total_equity_value > 0 (specific value depends on full cap table; Eqvista publishes a worked example we can pin against).
- Pass: convergence achieved; implied value within ±5% of Eqvista's published reference.

**AUDIT-P4-POS-002 — Sensitivity table on volatility ±10%.**
- Source: §5.1.
- Pass: result includes `sensitivity_tables.volatility` with at least two rows at vol−10% and vol+10%.

**AUDIT-P4-POS-003 — BSM per-grant fair value with vesting amortization.**
- Source: §5.2 + standard BSM formula.
- Input: 1000 shares granted, strike $10, FMV $5, vol=0.5, T=4, rf=0.04, 4-year cliff vesting.
- Expected: per-grant fair value computed; amortization schedule with 4 annual periods.
- Pass: schedule sums equal total fair value.

**AUDIT-P4-POS-004 — DCF sidecar workbook contains all named ranges.**
- Source: §5.3.
- Pass: `share_count_total`, `share_count_<class>`, `lp_total`, `lp_<class>`, `conversion_ratio_<class>`, `valuation_date` all present.

**AUDIT-P4-POS-005 — NVCA Model alias coverage for US deal.**
- Source: §5.4 + NVCA Cert (S1).
- Upload a cap table using NVCA-standard class names (e.g., "Series A Preferred Stock"); verify parser correctly handles NVCA-specific terminology.
- Pass: parse succeeds; class types correctly identified.

**AUDIT-P4-POS-006 — ≥ 3 US ASC 820 / 409A engagements run through tool by Month 12.**
- Source: §5.5 acceptance criterion 2.
- Audit query: count engagements with `standard_of_value ∈ {asc820, sec409a}`.
- Pass: ≥ 3.

**AUDIT-P4-POS-007 — Three siblings live on real engagements.**
- Source: §5.5 acceptance criterion 1.
- Audit query: OPM Backsolve sibling invoked ≥ 1 real engagement; BSM ≥ 1; DCF sidecar ≥ 1.
- Pass: each sibling has at least one production invocation.

#### Negative tests (Phase 4)

**AUDIT-P4-NEG-001 — Refusal: OPM Backsolve refused when CapTable has unresolved blocker.**
- Source: §5.1. Error: `backsolve-blockers-outstanding`.
- Pass: error code match.

**AUDIT-P4-NEG-002 — Refusal: OPM Backsolve refused when `last_round_class` not in cap table.**
- Source: §5.1. Error: `backsolve-unknown-anchor-class`.
- Pass: error code match.

**AUDIT-P4-NEG-003 — Refusal: OPM Backsolve never computes its own volatility.**
- Source: §5.1 "Both are required inputs sourced by the analyst."
- Test: omit volatility input.
- Pass: input validation error; no LLM/heuristic auto-fill.

**AUDIT-P4-NEG-004 — Refusal: DCF sidecar does NOT produce DCF / WACC / terminal value.**
- Source: §5.3.
- Pass: tool output is only an Excel sidecar with named ranges; no computed DCF values.

**AUDIT-P4-NEG-005 — Refusal: solver fails to converge raises `BacksolveNoConvergence`.**
- Source: §5.1.
- Construct degenerate input that won't converge (e.g., negative LP).
- Pass: exception type match.

**AUDIT-P4-NEG-006 — Refusal: BSM consumes CapTable + grant schedule but does NOT duplicate Qapita ESOP admin.**
- Source: §5.2 integration contract.
- Pass: code-path inspection confirms output handed off to existing ESOP product, not duplicating tracking.

#### Adversarial tests (Phase 4)

**AUDIT-P4-ADV-001 — Backsolve with a cap table containing a SAFE that hasn't converted yet.**
- Source: §5.1 input contract requires "validated CapTable". A SAFE outstanding is valid; but the SAFE will dilute on next round, affecting BSM and Backsolve.
- Spec is silent on how Backsolve treats outstanding SAFEs in the share count.
- **SPEC GAP: §5.1 doesn't specify whether outstanding SAFEs are pro-forma-converted for Backsolve purposes.** Suggested addition: explicit declaration that Backsolve uses the cap table as-is, and analyst is responsible for entering converted SAFEs prior to running.

**AUDIT-P4-ADV-002 — OPM Backsolve on a cap table where the anchor class is participating-capped.**
- Source: §5.1 + AICPA Cheap Stock Guide (S16). OPM Black-Scholes math assumes a contingent claim payoff — participating-capped has a piecewise payoff with kink at the cap.
- Spec §5.1 doesn't specify how the solver handles the kink.
- **SPEC GAP: §5.1 implicitly assumes the OPM allocator handles all LP types correctly; the math for participating-capped requires care.** Suggested addition: explicit citation to AICPA Chapter 6 methodology for capped-participating.

**AUDIT-P4-ADV-003 — DCF sidecar value drift if cap table changes mid-engagement.**
- Source: §5.3. Sidecar has named ranges; DCF model in Excel links to them. If a new snapshot supersedes the one the sidecar was built from, the DCF Excel still links to the old sidecar bytes.
- Spec is silent on sidecar regeneration / versioning.
- **SPEC GAP: §5.3 doesn't address sidecar version management.** Suggested addition: every sidecar export records the snapshot_id it was generated from; UI warning when newer snapshot exists.

**AUDIT-P4-ADV-004 — A backsolve on a Reddit-S-1-shape cap table with 8 preferred classes.**
- Source: Reddit S-1 (S7).
- Spec §5.1 doesn't bound class count.
- Pass: solver completes; no degenerate behavior.
- **SPEC GAP: no SLO on solver wall-clock vs. class count.** Suggested addition.

**AUDIT-P4-ADV-005 — Tool's marketing reference includes "AI-assisted".**
- Source: §7 out-of-scope refusals: "No 'AI-assisted' anything in the marketing."
- Audit: scan any Qapita external artifact citing the tool (per §5.5 acceptance criterion 3).
- Pass: zero hits on "AI-assisted", "ML-powered", etc.

#### End-to-end scenarios (Phase 4)

**AUDIT-P4-E2E-001 — Full Backsolve on a real S-1-derived cap table.**
1. Source: Astera Labs S-1 (S9) — extract their pre-IPO preferred structure manually (legal, public).
2. Construct CapTable matching that structure.
3. Provide MarketInputPack with vol from Damodaran 2025 (S25), DLOM from analyst (sourced manually per §5.1 refusal).
4. Run Backsolve.
5. Memo cites AICPA Chapter 6 + IFRS 13.
6. Pass: solver converges; outputs match published reference within ±5%; audit memo cites real published precedents.

**AUDIT-P4-E2E-002 — Sibling integration: cap table → BSM → ESOP product handoff.**
1. CapTable with ESOP grant schedule.
2. BSM computes per-grant fair value.
3. Output handed to Qapita's ESOP product (mocked endpoint).
4. Audit event records handoff.
5. Pass: ESOP product receives correctly-shaped payload; no duplicate tracking created.

#### Performance / load (Phase 4)

**AUDIT-P4-PERF-001 — Backsolve convergence < 30s for 10-class cap table.**
- Spec is silent on solver SLO.
- Auditor measures, reports as info.
- **SPEC GAP: no Backsolve SLO.** Suggested addition.

---

## 3. Cross-phase invariant tests

The spec §6 lists 8 cross-cutting invariants. Each gets an explicit test.

**AUDIT-INV-001 — Invariant 1: NO LLM in the calculation pipeline.**
- Method: network-traffic capture (e.g., mitmproxy) during a full engagement run from Phase 0 upload through Phase 4 Backsolve.
- Assert: zero outbound calls to any known LLM endpoint (*.openai.com, *.anthropic.com, *.googleapis.com/generativelanguage, *.cohere.ai, ollama or self-hosted equivalents).
- Pass: zero hits.

**AUDIT-INV-002 — Invariant 2: every finding cites the field/cell it came from.**
- Method: enumerate all findings produced across a representative engagement run.
- For each finding: assert `fields_referenced` non-empty (Phase 0) OR hyperlink target exists (Phase 2+).
- Pass: 100% have citations.

**AUDIT-INV-003 — Invariant 3: refusal beats fabrication.**
- Method: construct 10 deliberately-ambiguous inputs (low parse confidence, low OCR confidence, low holder-rollup confidence).
- For each: assert system returns structured refusal (error class + punch list), not a guessed output.
- Pass: 10-of-10 refuse.

**AUDIT-INV-004 — Invariant 4: snapshot immutability (Phase 2+).**
- Method: DB-level inspection. Issue `SELECT pg_stat_user_tables WHERE relname='snapshot'` (or SQLite equivalent); inspect application code for any UPDATE statements on snapshot table.
- Pass: zero UPDATE statements; runtime test of attempted UPDATE raises `SnapshotImmutableError`.

**AUDIT-INV-005 — Invariant 5: audit log append-only.**
- Method: same as INV-004 for `audit_event` table.
- Pass: zero UPDATE or DELETE statements.

**AUDIT-INV-006 — Invariant 6: determinism.**
- Method: run a full pipeline (parse → checklist → waterfall → memo → exports) twice on the same input on the same bound rule pack.
- Assert: byte-identical CapTable JSON; byte-identical findings list (order matters, sorted by code); byte-identical Waterfall breakpoint values within documented dedup tolerance; memo body identical (modulo analyst judgment blocks which are placeholders, hence stable).
- Pass: SHA-256 equality on every comparable artifact.
- NOTE: must control for any timestamp fields in output. If timestamps are present in deterministic-output paths, those are themselves a determinism violation per the invariant.

**AUDIT-INV-007 — Invariant 7: currency is metadata; no FX engine.**
- Method: scan all source for FX-related modules, currency-conversion calls. Construct a multi-currency cap table; assert no conversion occurs.
- Pass: assertion holds.

**AUDIT-INV-008 — Invariant 8: Pydantic forbids extra fields.**
- Method: construct CapTable JSON with extra key on every nested model (Company, ShareClass, LP, AntiDilution, Participation, SAFE, Warrant, ConvertibleNote, SideLetter, CapTable).
- For each: assert `ValidationError`.
- Pass: 10-of-10 raise.

---

## 4. Adoption / business-outcome audits (Phases 2–4)

These are not unit tests; they are audit procedures.

### 4.1 Phase 2 adoption metric

**Metric:** Number of real engagements run end-to-end in the tool.
- **Numerator:** Count of `engagement` rows with `status ∈ {review, signed, archived}` AND `created_at` between Month 1 start and Month 3 end.
- **Denominator:** N/A (absolute count).
- **Time window:** 8 weeks (Months 2–3).
- **Threshold for pass:** ≥ 2 (per §3.5 acceptance criterion 1).
- **Data source:** Production database `engagement` table; signed-off by tool maintainer + Evelyn.

### 4.2 Phase 3 adoption metric

**Metric:** % of new International Valuations engagements using the tool for intake.
- **Numerator:** Engagements created in tool in Months 4–6 where `source ∈ {excel_upload, qapita_pull}`.
- **Denominator:** Total International Valuations engagements opened by the team in Months 4–6 (from Qapita's engagement management system, not tool's local DB).
- **Time window:** 12 weeks.
- **Threshold for pass:** ≥ 50% (per §4.6 acceptance criterion 1).
- **Data source:** Qapita engagement management system + tool DB; signed-off by Amit Majumder (SEA head) + Evelyn.

### 4.3 Phase 3 auditor sign-off metric

**Metric:** ≥ 1 Big 4 auditor signed off on a tool-produced PDF memo without substantive pushback.
- **Threshold:** binary (yes/no).
- **Data source:** Email trail / Slack screenshot of auditor confirmation, attached as evidence to the audit report.
- **Interview protocol** (qualitative, since "without substantive pushback" is judgment):
  - Auditor interviewee: the Big 4 senior who reviewed the memo.
  - Question 1: "Did the memo provide sufficient appropriate audit evidence per AS 1105 for the cap table assertions you tested?"
  - Question 2: "Were the cell-level citations (snapshot://...) usable in your workpaper review?"
  - Question 3: "What single change to the memo would make it more useful for your review?"
  - **Positive answer to Q1 and Q2 = pass.** Q3 is captured as improvement backlog, not a pass/fail gate.

### 4.4 Phase 4 outcome metrics

**Metric:** Tool referenced in ≥ 1 Qapita external artifact (Qonversation talk, blog, sales deck).
- Threshold: binary.
- Data source: Qapita marketing / events team confirmation; artifact URL captured.

**Metric:** ≥ 3 US ASC 820 / 409A engagements run.
- See Phase 4 POS-006.

**Metric:** Engine spun out as Qapita-internal service consumed by ≥ 2 other product teams.
- Numerator: distinct internal product teams calling the engine's API.
- Threshold: ≥ 2.
- Data source: API call logs by consuming team's service account.

---

## 5. Things the spec promises that I CANNOT independently verify

Each entry: claim → why I can't verify → suggested resolution.

**UNV-001 — "Fuzz-tested across 23,300+ random cap tables with zero invariant violations" (PRODUCTION_ROADMAP.md §0.1 row Waterfall engine).**
- Why I can't verify: I cannot read `/stress_test/*` or `/tests/*`. I can re-run fuzz only by writing my own (out of scope for this audit plan). I can spot-check by constructing my own random cap tables and checking invariants, but I cannot validate the "23,300+" claim.
- Suggested resolution: builder publishes a fuzz-run report with seed, parameters, and pass-count summary as a separate spec artifact.

**UNV-002 — Live-formula Excel "verified against Python truth" (PRODUCTION_ROADMAP.md §0.1).**
- Why I can't verify: same — would require reading the test suite.
- Suggested resolution: spec adds a contract: "for any CapTable in the regression suite, exporting then opening the live workbook produces breakpoint values equal to Python's WaterfallResult within X tolerance." Then I can spot-check.

**UNV-003 — Phase 2 §3.1 "Cold-start pull for a 50-class cap table: under 5 seconds wall-clock" — reference environment not defined.**
- Why I can't verify: "under 5 seconds" on what hardware? Local laptop? Production EC2 box? Spec doesn't say.
- Suggested resolution: spec adds reference environment spec (CPU, memory, network latency to Qapita data source).

**UNV-004 — Phase 2 §3.4 PDF citation hyperlink format `snapshot://<snapshot_id>/<sheet>/<cell_ref>`.**
- Why I can't verify (now): the URL scheme `snapshot://` is custom; no resolver behavior is described. Does the auditor's PDF viewer follow it? Is there a tool registering the scheme?
- Suggested resolution: spec describes resolver (e.g., "in-tool web UI registers `snapshot://` handler" OR "hyperlink resolves via HTTPS deep-link to engagement viewer").

**UNV-005 — Phase 3 §4.3 OCR confidence semantics.**
- Why I can't verify: "confidence: float ∈ [0, 1]" — but which OCR backend's confidence? Google Document AI and Tesseract produce confidence on different scales. The mapping is not described.
- Suggested resolution: spec defines normalization (e.g., "all backends emit confidence as token-level average normalized to [0,1]").

**UNV-006 — Phase 3 §4.6 "Tool runs on Qapita infrastructure (not the maintainer's laptop)."**
- Why I can't verify: "Qapita infrastructure" is undefined externally.
- Suggested resolution: spec lists the artifacts that prove this (deployment URL, monitoring dashboard, infra-as-code repo path).

**UNV-007 — Phase 4 §5.1 OPM Backsolve solver math.**
- Why I can't verify: math correctness is auditable (compare to a published worked example like Eqvista S23), but the spec doesn't pin a specific reference. I can compare to Eqvista's BioStart example as an external sanity check but the spec doesn't guarantee equivalence.
- Suggested resolution: spec adds a "reference computation" appendix — a fully worked example with all inputs and the expected Backsolve output.

**UNV-008 — Phase 2 §3.2 "Read-only auditor magic-link token expires after configurable TTL."**
- Why I can't verify: error code for expired token not named. §3.2 lists `read-only-token` for a write attempt but doesn't name the code for an expired-token read attempt.
- Suggested resolution: spec adds `token-expired` error code.

**UNV-009 — Phase 4 §5.5 "Tool referenced in at least one Qapita external artifact."**
- Why I can't verify: relies on Qapita's marketing team's calendar. External auditor cannot verify timing pre-launch.
- Suggested resolution: spec adds verification source (e.g., Qapita marketing publication log).

**UNV-010 — Cross-cutting "determinism" invariant: does it include timestamps?**
- Why I can't verify: §6.6 says "same input → same output bit-for-bit." But snapshots have `created_at`. If an export embeds a timestamp ("memo generated at 2026-08-15 10:23:45"), the export is not bit-for-bit deterministic across runs.
- Suggested resolution: spec explicitly carves out which outputs are deterministic in content (data, findings, breakpoints) vs which have a deterministic-modulo-timestamp guarantee (memos, exports). This is a real production concern and the spec is ambiguous.

**UNV-011 — §1.1 "openpyxl.InvalidFileException propagates; route returns HTTP 400."**
- Why I can't verify: spec couples a third-party library's exception type to its HTTP behavior. If openpyxl version changes the exception class, contract may silently break.
- Suggested resolution: spec abstracts to "if openpyxl rejects the file, the route returns HTTP 400 with error banner."

---

## 6. SPEC GAPS — things the spec doesn't address that production reality will demand

Numbered for cross-reference. Repeats some gaps surfaced in §2 with consolidated framing.

**GAP-01 — Concurrency on engagement edits.** Where: §3.2. Scenario: two analysts edit same engagement simultaneously. Risk: lost updates, race conditions, audit-log race. Suggested addition: define optimistic or pessimistic concurrency model with explicit error code.

**GAP-02 — Data retention and deletion.** Where: §3.2 lifecycle has `signed → archived` but not `archived → deleted`. Real-world: GDPR/PDPA + client request to delete. Risk: regulatory non-compliance. Suggested addition: explicit retention policy + deletion procedure compatible with audit-log immutability (e.g., crypto-shredding).

**GAP-03 — GDPR/PDPA right of erasure vs immutable audit log.** Where: §3.2 invariant clash. Risk: legal non-compliance. Suggested addition: PII redaction protocol that itself logs the redaction.

**GAP-04 — Backup, disaster recovery, restore semantics.** Where: §3.2, §4.6. Spec promises "Qapita infra policy" but doesn't define RPO/RTO. Risk: data loss on incident; auditor reproducibility lost. Suggested addition: explicit RPO ≤ 1h, RTO ≤ 4h target for production.

**GAP-05 — Key rotation and signed audit-log integrity.** Where: §3.2 audit log is append-only at table level; spec doesn't address tampering at DB-admin level. Risk: an internal actor with DB access could insert rogue rows. Suggested addition: signed hashes per row + Merkle-chain over the audit log; published verification procedure for auditors.

**GAP-06 — Schema evolution: rule pack JSON validated against engine version.** Where: §4.1. Risk: an engine upgrade that adds a new severity enum value reads an old rule pack JSON containing that severity — undefined behavior. Suggested addition: engine_version field on rule pack; validation at bind time.

**GAP-07 — Rule-pack vs engine-code version skew.** Where: §4.1. Engine code is versioned in git; rule packs are semver-versioned in DB. Skew possible. Risk: deterministic re-runs of historical engagements depend on engine code AND rule pack. Suggested addition: bound engagement also records engine commit hash; re-runs require matching engine + pack OR generate "approximate re-run" warning.

**GAP-08 — Import/export portability.** Where: spec covers internal persistence but not export-for-handoff to another firm. Risk: if Big 4 auditor wants to take the engagement offline, no standard export format defined. Suggested addition: a "portable engagement bundle" zip spec (snapshots + audit log + rule pack snapshot).

**GAP-09 — Internationalization: non-ASCII names, RTL languages, locale dates.** Where: §1.1, §1.10. Spec says "any character openpyxl accepts" but doesn't promise UI rendering. Risk: Indonesian/Arabic/Tamil holder names display garbled. Suggested addition: explicit i18n promise OR documented limitation.

**GAP-10 — Accessibility (WCAG / Singapore IMDA).** Where: §1.10 / §3.4 PDF. Risk: read-only auditor with visual impairment cannot use deliverable. Suggested addition: WCAG 2.1 AA target for UI; tagged PDF (PDF/UA) for memo.

**GAP-11 — Locale-specific currency parsing.** Where: §1.1 lists `$, ₹, S$, Rs.` but not `€, £, ¥, ₩, ₦, ₱`. Risk: Korean / Japanese / European deals fail parsing. Suggested addition: explicit currency symbol list OR generic Unicode currency-category stripping.

**GAP-12 — Multilingual column headers.** Where: §1.1 synonyms are English. Risk: Indonesian / Tamil / Hindi headers reject. Suggested addition: per-locale synonym packs; `locale` parameter to parser.

**GAP-13 — SAFE template variant.** Where: §1.3 SAFE model. Risk: pre vs post-money SAFEs computed identically downstream; analyst cannot disambiguate. Suggested addition: `template_variant` enum on SAFE.

**GAP-14 — Protective provisions / preemptive rights / ROFR / drag-along.** Where: §1.3. Risk: standard NVCA terms cannot be checked by rule pack because no structured field. Suggested addition: structured protective_provisions list.

**GAP-15 — Negative-correction rows in source workbook.** Where: §1.1. Risk: silent over-reporting of shares. Suggested addition: warn on negative-numeric row, document handling.

**GAP-16 — Encrypted PDF.** Where: §1.2. Risk: silent fail. Suggested addition: warning code `pdf-encrypted`.

**GAP-17 — Unparseable-date silence.** Where: §1.1 explicitly chooses no warning. Risk: downstream rules can't fire; auditor doesn't notice. Suggested addition: emit warning when date required for rule evaluation.

**GAP-18 — Multi-currency mismatch detection.** Where: §1.4. Risk: analyst silently mixes USD and SGD. Suggested addition: CURRENCY-MISMATCH info finding.

**GAP-19 — MFN-only SAFE checklist.** Where: §1.4 SAFE-UNCONVERTED. Risk: YC-style MFN-only SAFE never flagged. Suggested addition: warning when SAFE has no cap AND no discount AND a preferred round has been issued.

**GAP-20 — N-way pari-passu cardinality.** Where: §4.2. Risk: 3-way pari-passu not explicitly supported. Suggested addition: "any cardinality" explicit.

**GAP-21 — Pari-passu with mixed LP types.** Where: §4.2. Risk: undefined semantics. Suggested addition: explicit refusal OR defined math.

**GAP-22 — Pari-passu interaction with full-ratchet AD.** Where: §4.2 + §1.5. Risk: undefined. Suggested addition: define interaction.

**GAP-23 — OCR per-page vs total threshold.** Where: §4.3. Risk: mixed-page PDF under-OCR'd. Suggested addition: per-page check.

**GAP-24 — OCR backend swap breaks determinism.** Where: §4.3 + §6.6. Risk: re-run produces different OCR output. Suggested addition: OCR result + backend persisted with side letter; determinism invariant carve-out.

**GAP-25 — Severity enum schema evolution.** Where: §4.1. Suggested addition: severity in engine code, validated at bind.

**GAP-26 — Per-rule jurisdiction predicate.** Where: §4.1. Risk: jurisdiction tagging on pack fires rules in wrong jurisdictions. Suggested addition: per-rule jurisdiction predicate evaluated against engagement metadata.

**GAP-27 — Structured voting_multiplier.** Where: §1.3. Risk: rules can't query "voting ratio > X". Suggested addition: structured field.

**GAP-28 — Concurrent PDF generation during edits.** Where: §3.4. Risk: PDF cites wrong snapshot. Suggested addition: atomic generation against frozen snapshot id parameter.

**GAP-29 — Subsequent-events memo after signing.** Where: §3.2. Risk: legitimate late update has no path. Suggested addition: `signed → review` reopen with partner authorization + audit event.

**GAP-30 — Backsolve treatment of outstanding SAFEs.** Where: §5.1. Risk: ambiguous share count. Suggested addition: explicit pre-conversion requirement.

**GAP-31 — Backsolve solver behavior on participating-capped anchor.** Where: §5.1. Risk: piecewise payoff kink. Suggested addition: AICPA Chapter 6 citation + explicit handling.

**GAP-32 — DCF sidecar versioning.** Where: §5.3. Risk: stale sidecar links. Suggested addition: snapshot_id stamping + UI warning on newer snapshot.

**GAP-33 — Token-expired error code.** Where: §3.2. Suggested addition: `token-expired` code.

**GAP-34 — Reference environment for performance contracts.** Where: §3.1, §4.4. Risk: SLO is unverifiable. Suggested addition: reference env spec.

**GAP-35 — Determinism with timestamps.** Where: §6.6. Risk: exports with embedded timestamps fail invariant. Suggested addition: explicit carve-out per output type.

**GAP-36 — XSS / injection in cell content.** Where: §1.10, §3.4. Risk: malicious holder name renders as script in UI / memo. Suggested addition: explicit escaping promise.

**GAP-37 — Pari-passu data-model migration round-trip safety.** Where: §4.2. Risk: legacy Phase 0 export from new schema must round-trip; spec says "the migration is reversible" but doesn't cover lossy cases (3-way pari-passu has no legacy representation). Suggested addition: explicit lossy-case warning on export.

**GAP-38 — Audit log query SLO.** Where: §3.2 says queryable, no SLO. Risk: audit-time query times out for 7-year-old engagement. Suggested addition: query SLO ≤ 5s.

**GAP-39 — Read-only auditor token revocation pre-expiry.** Where: §3.2. Risk: a partner discovers the auditor relationship is terminated mid-TTL but cannot revoke. Suggested addition: revoke endpoint with audit event.

**GAP-40 — Bulk-export rate limiting.** Where: §1.10 no rate limits. Phase 2+ should have them. Risk: data exfiltration by compromised analyst. Suggested addition: per-user export rate limit + alert threshold.

---

## 7. The deliverable for each phase audit

What does the auditor hand to Evelyn at the end of each phase audit?

### 7.1 Format
- **Primary:** a single PDF report (typeset, paginated, version-stamped). Generated from a structured Markdown source.
- **Companion:** a spreadsheet (XLSX) with the full per-test pass/fail matrix, one row per test ID, columns: ID, name, phase, category, source URL, expected, actual, pass/fail, severity (blocker/major/minor), notes.

### 7.2 Required sections of the PDF report
1. **Cover sheet** — audit version, auditor name, dates, scope (which phase).
2. **Executive summary** — one-page pass/fail roll-up. Total tests, count passed, count failed, count blocked. Top 5 findings.
3. **Pass / fail summary by phase** — table by phase + category (POS/NEG/ADV/E2E/PERF).
4. **Failures (one section per failure)** — ID, name, severity, repro steps, spec section violated, suggested fix routing (engineering / spec / product). Each failure links to the companion spreadsheet row.
5. **Spec gaps surfaced** — list from §6 reformatted with severity ranking.
6. **Cannot-verify list** — list from §5.
7. **Cheating watch findings** — outputs of §8 scans.
8. **Appendix A — source catalog used (§1 of this plan).**
9. **Appendix B — full test matrix (XLSX attached).**
10. **Appendix C — environmental config of audit run** (OS, Python version, network capture tool versions).

### 7.3 Severity definitions
- **Blocker:** spec contract is violated; tool MUST be fixed before this phase is signed off. Example: a refusal claim doesn't fire.
- **Major:** spec is ambiguous and the implementation chose a behavior that contradicts cross-cutting invariants. Example: a determinism invariant fails because of an embedded timestamp.
- **Minor:** spec is silent on a real-world scenario but the implementation degrades gracefully. Example: a multilingual header rejects with a clean error.

### 7.4 Fix routing
- **Engineering** — code change required (e.g., bug fix).
- **Spec** — spec change required (e.g., clarify behavior).
- **Product** — UX or workflow change required (e.g., add banner copy).
- Each failure is routed to exactly one of the three.

---

## 8. The cheating watch-list

Restated concrete behaviors to watch for, with detection method and response.

**CHEAT-01 — Fixture mirrors my external source.**
- Behavior: a new fixture appears in `/fixtures/` that mirrors an S-1 / DRHP I named in §1.
- Detection: scan commit history for new fixture files dated AFTER this plan was published. Compare cap-table shape (class names, class counts, share counts) to my source list.
- Response: flag as `CHEAT-FIXTURE-MIRROR`; reject tests run against that fixture; re-run tests with a fresh re-derived input from the same external source.

**CHEAT-02 — Hard-coded answer for my exact input.**
- Behavior: the engine returns a structurally-different output if I change one share count by 1.
- Detection: for each positive test, run a second variant with one numeric input perturbed by +1 share. Verify output changes by a small, predictable amount (not by a structural change like a new breakpoint disappearing).
- Response: flag as `CHEAT-LOOKUP`; investigate the code path.

**CHEAT-03 — Special "audit mode" code path.**
- Behavior: behavior differs between two semantically-equivalent inputs (e.g., the same CapTable serialized two ways).
- Detection: serialize the same CapTable as (a) Excel upload and (b) JSON import; compare findings, waterfall, memo. Differences indicate divergent paths.
- Response: flag `CHEAT-AUDIT-MODE`.

**CHEAT-04 — LLM only invoked for my inputs.**
- Behavior: LLM call appears only when input contains a name from my external source list.
- Detection: continuous network capture during all audit test runs; assert no outbound LLM calls regardless of input.
- Response: flag `CHEAT-LLM`; this is also a violation of §6 invariant 1.

**CHEAT-05 — Spec amended to retroactively cover a gap I named.**
- Behavior: spec file updated between this plan's publication and the audit run, weakening a refusal claim to make it pass.
- Detection: git log on `SYSTEM_SPEC.md`; compare diff against the version this plan was written against.
- Response: flag `CHEAT-SPEC-RETRO`. The audit runs against the version of the spec at the time of this plan, not the latest.

**CHEAT-06 — Test added that mirrors my test ID's intent.**
- Behavior: builder's test suite gains a test mirroring `AUDIT-P0-NEG-005` (pari-passu rejection) AFTER publication. Doesn't invalidate the audit but proves the gap was real.
- Detection: review `/tests/*` git history for additions after publication. (Auditor may inspect git log without reading file contents.)
- Response: note as `CHEAT-OBSERVATION` (not a fail, but evidence).

**CHEAT-07 — Builder pre-loads cache for my inputs.**
- Behavior: my test inputs return faster than equivalent novel inputs.
- Detection: time 10 audit-test inputs vs 10 same-shape but novel-numerics inputs. Suspicious if my inputs are >2× faster.
- Response: flag `CHEAT-CACHE`.

**CHEAT-08 — Builder rewrites a fixture name to match my source.**
- Behavior: existing fixture renamed to e.g. "Lenskart-style" after this plan publishes.
- Detection: git log on fixture filenames.
- Response: flag `CHEAT-FIXTURE-RENAME`.

**CHEAT-09 — Builder ships a new G-code rule mirroring an adversarial test.**
- Behavior: adversarial test in §2 surfaces a missing rule; builder ships the rule before audit runs.
- Response: this is allowed and good IF the rule is added to the rule pack via the documented Phase 3 process (semver bump, citation, fixture). It is `CHEAT-RUSH-ADD` if the rule is ad-hoc without process.

**CHEAT-10 — Builder routes audit's IP address to a special server.**
- Behavior: requests from the auditor's IP get different responses.
- Detection: run identical request from two distinct IPs; compare responses.
- Response: flag `CHEAT-IP-ROUTING`.

---

## End of plan

This plan defines 100+ tests across 5 phases plus 8 invariant tests plus 4 adoption metrics. It surfaces 40 spec gaps and 11 cannot-verify items. It catalogs 22 usable external sources and is honest about 5 sources I could not access cleanly.

The audit run on this plan will produce a binary go/no-go per phase. The §6 spec gaps are themselves the most valuable output, regardless of whether tests pass.
