# Provenance — Fixture 03 (SEA Edge Case)

Every clause traces to a published, freely available legal precedent. The fixture is fictional but every non-vanilla mechanic is sourced.

## Company

- **Bandhan Ventures Pvt. Ltd.** — fictional Indian e-commerce SaaS, Pvt. Ltd. (Indian private-limited) structure. "Bandhan" (Hindi: bond/connection) is a generic name with no real-world referent.

## Capital structure — SEA-specific elements

### CCPS (Compulsorily Convertible Preference Shares)

All three preferred classes (Seed, A, B) are CCPS rather than US-style Preferred Stock. CCPS is the dominant Indian venture instrument, used in place of US-style preferred for two reasons:

1. **FEMA / FDI treatment.** Per Ministry of Finance guidance dated April 30, 2007, CCPS issued to a foreign investor is treated as equity for FDI sectoral cap purposes. Non-convertible or optionally-convertible preference shares are treated as debt under External Commercial Borrowings (ECB) rules. CCPS lets foreign investors hold preferred-style economics under the equity FDI regime.
2. **Section 47(xb) tax treatment.** The Income-Tax Act 1961 explicitly excludes CCPS-to-equity conversion from capital gains tax, preserving the conversion's tax-neutrality.

For waterfall purposes CCPS behaves like preferred — sits ahead of common, takes liquidation preference at exit. The mandatory-conversion mechanic only matters at IPO or on specific contractual triggers; for a present-date waterfall valuation, CCPS is preferred.

**Sources:** Cyril Amarchand Mangaldas blog, "CCPS as instrument for startups and M&A structuring." Companies Act 2013, Section 55. Income-Tax Act 1961, Section 47(xb).

### Series A 1x Participating with 3x Cap

Participating-with-cap is a real, NVCA-sanctioned variant of the standard liquidation preference. Per NVCA Model Certificate of Incorporation, Article IV, Section 2.2, the three liquidation preference variants are non-participating, participating without cap, and participating with cap. The 3x cap is a typical bound in pro-investor or strategic-led rounds; 2x and 5x caps are also seen.

In the modern venture market, participating-with-cap appears most often in:
- Down rounds, where investor pressure justifies stronger preferences.
- Strategic-led rounds, where the strategic investor wants protection against their target's underperformance.
- Bridge rounds with a "preferred stock junior" attached.

The clause produces three additional breakpoints in any OPM/Backsolve waterfall, which is exactly the audit-memo-walkthrough complexity Evelyn's team handles regularly.

**Sources:** NVCA Model Certificate of Incorporation, Article IV, Section 2.2(c); AICPA Practice Guide chapter on liquidation waterfalls; Aranca Backsolve whitepaper worked examples; Plante Moran 2015 worked example.

### Series Seed Full-Ratchet Anti-Dilution

Full ratchet is the most aggressive of the three NVCA-recognized anti-dilution mechanics. Under NVCA Model Certificate of Incorporation, Article IV, Section 2.4(d), three variants are recognized: broad-based weighted average (modern market default), narrow-based weighted average (mid-aggressive), and full ratchet (most aggressive — adjusts conversion ratio to make the original investor whole at any subsequent down-round price).

In real practice, full ratchet survives in:
- Bridge rounds where the bridge investor demands maximum protection.
- Distressed financings where the company has weak BATNA.
- Side-letter overrides on otherwise-vanilla weighted-average rounds, granted to specific strategic holders.

For this fixture, the full-ratchet survives from a 2022 distressed bridge that was eventually resolved without a down-round. The clause has not been triggered. Including it documents that real Indian cap tables sometimes carry inherited odd clauses from earlier financings, and that an analyst building a 409A or fair-value memo needs to capture them as audit-memo footnotes even when they don't currently affect the waterfall.

**Sources:** NVCA Model Certificate of Incorporation, Article IV, Section 2.4(d); Cyril Amarchand and Khaitan & Co commentary on Indian anti-dilution practice; AICPA Cheap Stock Guide chapter on anti-dilution interaction with backsolve.

### Founders' Class A Dual-Class Voting Common

Per Cyril Amarchand commentary on Indian dual-class structures, founder dual-class shares with differential voting (typically 5x to 10x) but identical economic rights are increasingly common in Indian venture-backed companies. SEBI's framework permitting DVR (differential voting rights) for listed companies has normalized the structure for unlisted private cos via contractual arrangement.

Treatment in waterfall: per VIMA Long Form Term Sheet annotation and Cyril Amarchand commentary, "Indian dual-class structures usually have identical economic rights with voting differentials only — model as one economic class." So Bandhan's Class A is one economic class for waterfall purposes; the voting differential lives in disclosures.

**Sources:** Cyril Amarchand blog on Indian dual-class structures; SEBI DVR framework reference; VIMA 2.0 Long Form Term Sheet (March 2025).

### Super Pro-Rata Side Letter

Super pro-rata rights granting an investor more than 1.0x their proportional share in the next round are a standard NVCA-side-letter mechanism. They appear in two contexts: (a) lead-investor anchor protection, and (b) strategic-investor concentration commitments. Bandhan's side letter grants 1.5x super pro-rata to a strategic Series B investor who put in roughly half of the round.

Forward-looking right; does not affect present-date waterfall but affects pro-forma cap table modeling for any contemplated next round.

**Sources:** NVCA Model Investors' Rights Agreement, Section 4 (Pre-Emptive Rights); standard side-letter convention.

## Numerical realism

Round economics:
- Seed: 1M shares at ₹50 = ₹50M raised. Realistic 2022-vintage Indian seed.
- Series A: 2.5M shares at ₹100 = ₹250M raised. 2x step-up from Seed; realistic 2024 Series A.
- Series B: 3.5M shares at ₹250 = ₹875M raised. 2.5x step-up from A; realistic 2026 Series B for a growing e-commerce SaaS.

Total raised: ₹1,175M ≈ USD 14M at ₹85/USD. Within the realistic envelope for a 4-year-old Indian e-commerce SaaS at Series B per Cento Ventures and Tracxn Indian VC trend reports.

## What is intentionally NOT in this fixture

- No outstanding SAFEs or CCDs at the present valuation date. (Fixture 02 covers SAFE conversion gaps.)
- No vendor warrants. (Fixture 02 covers warrants.)
- No MFN side letter. (Fixture 02 covers MFN.)
- No PMA / Indonesian FDI structure. (Per precedent research, Indonesian fixtures don't materially diverge from Singapore for waterfall purposes; we don't add a separate Indonesian fixture.)
- No 2x liquidation preference (red-flag in all SEA markets per VIMA + Cyril Amarchand commentary).

## References

- NVCA Model Legal Documents — current edition. https://nvca.org/model-legal-documents/
- AICPA Practice Guide, "Valuation of Privately-Held-Company Equity Securities Issued as Compensation," 2013/2019 edition.
- Cyril Amarchand Mangaldas, "CCPS as instrument for startups and M&A structuring," 2026.
- Companies Act 2013, Section 55 (preference shares).
- Income-Tax Act 1961, Section 47(xb).
- VIMA 2.0 (Singapore Venture & Private Capital Association) — March 2025 Shareholders' Agreement and CARE updates.
- Cento Ventures, SEA Tech Investment annual reports.
- Aranca Backsolve whitepaper.
- Plante Moran (2015), "Equity compensation in venture capital and private equity."
