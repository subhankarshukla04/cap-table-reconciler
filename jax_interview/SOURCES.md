# ESOP Atlas — Source Map (the citation constraint)

**Purpose:** This file defines the **only** sources I will cite when adding rules. No rule may ship in the corpus unless every fact in it is traceable to at least one source listed here. Anything I cannot verify against this list gets `confidence: requires_counsel` and a `note` explaining the gap.

**The discipline:**
- **Primary source** = the regulator's own publication (statute, circular, e-Tax guide, IRS publication, HMRC manual).
- **Secondary source** = Big-4 firm or major law firm publication (PwC Worldwide Tax Summaries, Deloitte country guides, EY tax guides, Baker McKenzie Global Equity Matrix, KPMG country tax profile).
- **Every rule must have ≥ 1 primary source.** Secondary sources cross-check, they don't replace primary.
- **Anything uncited or unverifiable** → `confidence: requires_counsel`, never silently guessed.

---

## Singapore (SG) — locked in v1 (already in `src/rules/sg.json`)

**Primary:**
- Income Tax Act 1947 (Singapore) — `https://sso.agc.gov.sg/Act/ITA1947`
- IRAS — Gains from the exercise of stock options — `https://www.iras.gov.sg/taxes/individual-income-tax/basics-of-individual-income-tax/what-is-taxable-what-is-not/employment-income/gains-from-the-exercise-of-stock-options`
- IRAS e-Tax Guide on Tax Treatment of ESOP and Other Forms of ESOW Plans (rev. 30 Jan 2026) — `https://www.iras.gov.sg/media/docs/default-source/e-tax/etaxguides_iit_esop_2026-01-30.pdf`
- IRAS — Form IR21 guidance (tax clearance for foreign / non-resident employees) — `https://www.iras.gov.sg/taxes/individual-income-tax/employers/tax-clearance-for-foreign-non-resident-employees-form-ir21`
- IRAS — Capital gains tax page — `https://www.iras.gov.sg/taxes/individual-income-tax/basics-of-individual-income-tax/what-is-taxable-what-is-not/capital-gains`

**Secondary cross-checks (informally — not in citation chain since primary is sufficient):**
- PwC Worldwide Tax Summaries — Singapore
- RSM Singapore — ESOP tax treatment article
- Loeb & Loeb — Understanding ESOPs Across Key Asia Jurisdictions

## India (IN) — locked in v1 (already in `src/rules/in.json`)

**Primary:**
- Income-tax Act 1961 — `https://incometaxindia.gov.in/Pages/acts/income-tax-act.aspx`
  - §17(2)(vi) — perquisite from share allotment
  - §111A — STCG on listed equity
  - §112 — LTCG on unlisted shares
  - §112A — LTCG on listed equity
  - §192 — TDS on salary at average rate
  - §192(1C) — DPIIT-startup ESOP deferral
  - §48 — cost basis for capital gains
  - §9(1)(i), §9(1)(ii) — Indian-source income for non-residents
  - §195 — TDS on payments to non-residents
- Income-tax Rules 1962 — `https://incometaxindia.gov.in/Pages/rules/income-tax-rules-1962.aspx`
  - Rule 3(8) — FMV computation for ESOP perquisite
- Income-tax Act 2025 — successor provisions §17(5)(h), §392(1)
- India–Singapore DTAA — `https://incometaxindia.gov.in/Pages/international-taxation/dtaa.aspx`
  - Article 13(4) — capital gains on Indian-company shares
  - Article 15 — Dependent Personal Services

**Secondary:**
- ITA tutorial PDF — `https://incometaxindia.gov.in/Tutorials/50.Taxation-of-ESOPs.pdf` (403's via WebFetch but referenced via search results)
- PwC Worldwide Tax Summaries — India
- TaxBuddy / Hissa / Inkle / EquityList ESOP guides (used only for cross-check, never as sole source)

---

## Indonesia (ID) — adding in batch 1

**Primary (committed; will cite directly in rule JSON):**
- DGT (Direktorat Jenderal Pajak) — `https://www.pajak.go.id/en/`
  - Withholding Article 21 Tax (PPh 21) page — `https://www.pajak.go.id/en/withholding-article-21-tax`
  - Tax Treaty Rates page — `https://www.pajak.go.id/en/tax-treaty-rates`
- UU PPh — Income Tax Law (Law No. 7/1983 as amended by Law No. 36/2008 and most recently by UU HPP, Law No. 7/2021)
- PMK 168/PMK.03/2023 — current technical regulation on Article 21 income tax withholding (effective 1 Jan 2024). **Supersedes PMK 252/2008** (which is what my earlier draft text incorrectly cited).
- PP No. 41/1994 — final tax on listed-share sales (0.1% on transaction value)

**Secondary (cross-check; cited alongside primary where useful):**
- PwC Indonesian Pocket Tax Book 2025 — `https://www.pwc.com/id/en/pocket-tax-book/english/pocket-tax-book-2025.pdf`
- PwC Worldwide Tax Summaries Indonesia — `https://taxsummaries.pwc.com/indonesia/`
  - `/corporate/withholding-taxes`
  - `/corporate/income-determination`
- Acclime Indonesia withholding-tax guide — `https://indonesia.acclime.com/guides/withholding-tax/`
- KPMG Indonesia Tax Profile

**Honest scope note:** Indonesia does NOT have a dedicated ESOP/stock-option tax circular at the level of SG's e-Tax Guide or India's Rule 3(8). The rules are derived by applying general PPh 21 employment-income provisions (under UU PPh + PMK 168/2023) to share-grant fact patterns. PwC and Acclime both confirm this. Where Indonesia practice is settled, confidence = `firm`; where it requires interpretation (e.g., FMV determination for unlisted overseas parent shares), confidence = `conditional` with a written caveat.

---

## United States (US) — planned for batch 2 (not in v1 yet)

**Primary (verified, citable):**
- IRS — Topic 427 (Stock options) — `https://www.irs.gov/taxtopics/tc427`
- 26 U.S. Code (Internal Revenue Code) via Cornell LII — `https://www.law.cornell.edu/uscode/text/26/`
  - §83 — property transferred in connection with services (NSO governing section)
  - §83(b) — election to include in gross income at grant
  - §422 — Incentive Stock Options (ISO)
  - §423 — Employee Stock Purchase Plans (ESPP)
  - §3121 — FICA wage base
  - §3402 — federal income tax withholding
  - §409A — deferred comp (penalty on discounted options)
- IRS Form 3921 — ISO exercise reporting — `https://www.irs.gov/forms-pubs/about-form-3921`
- IRS Form 3922 — ESPP transfer reporting
- IRS Form W-2 instructions (Box 12 code V for NQSO compensation, Box 14 ISO disqualifying disposition)
- IRS Publication 525 — Taxable and Nontaxable Income (stock options section)

**Secondary cross-check:**
- Carta — "Taxation on Employee Stock Ownership Plans (ESOPs) in Southeast Asia" + US ESOP guides
- Foley & Lardner / Cooley alerts on §422 ISO mechanics
- NASPP (National Association of Stock Plan Professionals) — Early Exercise + 83(b)
- Schwab "Non-qualified Stock Option (NQSO) Taxes" guide
- VestingStrategy / Cornell LII as cross-validation

**Notable US-specific facts I'll encode:**
- ISO at exercise: no regular income tax, but AMT adjustment for spread (§55, §56)
- ISO holding requirements: 2 years from grant, 1 year from exercise → LTCG on disposition
- NSO at exercise: ordinary income on spread, FICA + FIT withholding, W-2 Box 12 code V
- US-India DTAA Article 16 (Dependent Personal Services)
- **US-Singapore: no comprehensive income tax treaty.** Only FATCA + limited information exchange. Foreign tax credit (§901) is the relief mechanism, not treaty.

---

## Vietnam, Thailand, Philippines, Malaysia, UK, HK — NOT in scope

These will only be added when I can verify primary source citations in English with the same discipline.

For each, before adding, I will:
1. Identify the primary regulator (e.g., Vietnam General Department of Taxation, Thai Revenue Department).
2. Locate the specific statute / circular addressing ESOP / share-based remuneration.
3. Cross-check against PwC / Deloitte / EY / KPMG country guide.
4. If primary source not available in English with verifiable section refs, **defer the jurisdiction** — do not ship guessed rules.

---

## Acceptance gate (per-rule)

Before any new rule lands in the corpus:

- [ ] At least one **primary source** is cited with its URL (or, for statute, the statute reference + version year).
- [ ] At least one **secondary cross-check** is mentioned (in `note` field of a citation, or in caveats).
- [ ] `confidence` is set honestly: `firm` only if both primary and secondary agree without ambiguity; `conditional` if interpretation is involved; `requires_counsel` if I cannot verify.
- [ ] `retrieved_on` is set to the actual verification date.
- [ ] Caveats list at least one nuance that a tax practitioner would flag.

This file is the constraint. The next rule I write will cite only what is mapped above.
