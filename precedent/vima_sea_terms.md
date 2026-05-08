# VIMA + SEA Term Conventions — Reference Summary

> SEA-specific deviations from NVCA standard. Distilled reference for the Cap Table Reconciler. Singapore (VIMA), India (CCPS / Companies Act 2013), Indonesia (PMA structures).

**Primary sources:**
- [SVCA Model Legal Documents (VIMA 2.0)](https://www.svca.org.sg/model-legal-documents) — Singapore Academy of Law + Singapore Venture & Private Capital Association joint publication, current revision 2022 with Shareholders' Agreement and CARE updated March 2025.
- [Cyril Amarchand — CCPS as instrument for startups and M&A structuring](https://corporate.cyrilamarchandblogs.com/2026/02/ccps-an-important-instrument-for-startups-and-ma-structuring/)
- [Companies Act 2013, Section 55 — Issue and redemption of preference shares](https://ca2013.com/issue-and-redemption-of-preference-shares/)
- [ICSI Journal — Legal & Accounting Aspects of Redeemable Preference Shares (Aug 2025)](https://www.icsi.edu/media/webmodules/CSJ/August-2025/13.pdf)
- [Mahwengkwai — Redeemable Convertible Preference Shares (March 2024)](https://mahwengkwai.com/wp-content/uploads/2024/04/2024-03-13-Online-Talk-Redeemable-Convertible-Preference-Shares-Raising-Capital-for-Your-Business.pdf)

---

## VIMA 2.0 Document Suite (Singapore)

### Series A Documents (most relevant for our fixtures)

| Document | Version | Function |
|---|---|---|
| Shareholders' Agreement | March 2025 | Investor rights, governance, share-class rights |
| Term Sheet (Short Form) | 2022 | Streamlined commercial terms |
| Term Sheet (Long Form) | 2022 | Full commercial + legal terms with annotations |
| Subscription Agreement | 2022 | Equity purchase mechanics |
| Convertible Note | 2022 | Bridge instrument |
| Model Constitution | 2022 | Singapore-incorporated company governance |
| ESG Letter Agreements | 2022 | ESG commitments (short and long forms) |

### Pre-Series A Documents

| Document | Version | Function |
|---|---|---|
| CARE (Convertible Agreement Regarding Equity) | March 2025 | Singapore SAFE-equivalent, early-stage convertible |
| Founders' Agreement | 2022 | Co-founder equity allocation |

### Why VIMA matters for Qapita's valuations team

VIMA is the SEA equivalent of NVCA. Singapore-headquartered companies in Qapita's pipeline use VIMA-derived terms. The structure of VIMA is very NVCA-aligned (Singapore borrowed heavily from US and UK conventions when drafting), but several specific deviations matter for waterfall mechanics. CARE in particular is the SEA equivalent of YC's SAFE — same conceptual mechanics, different governing law and statutory backstops.

---

## Material Deviations from NVCA Standard

### 1. CARE (Singapore SAFE-equivalent)

**Source:** VIMA 2.0 Pre-Series A package, [SVCA](https://www.svca.org.sg/model-legal-documents).

**Mechanics (largely mirror YC SAFE):**
- Discount-only, valuation cap-only, or both.
- Converts at the next "Equity Financing" (Series A or later priced round).
- Liquidity Event and Dissolution Event triggers parallel YC's structure.

**Singapore-specific differences vs YC SAFE:**
- Governing law is Singapore (not Delaware), affecting interpretation of dispute clauses.
- "Conversion shares" are technically issued under Singapore Companies Act provisions, not Delaware GCL.
- Currency frequently SGD or USD; conversion mechanics need to handle FX if denominated differently from the priced round.
- Statutory backstop on discount/cap math is similar in effect but worded differently.

**For waterfall purposes:** identical to SAFE — a pre-conversion CARE is a contingent claim, not a cap-table line item; post-conversion it's preferred at the cap-implied price.

### 2. Indian CCPS (Compulsorily Convertible Preference Shares) — the most important SEA-specific instrument

**Source:** [Cyril Amarchand](https://corporate.cyrilamarchandblogs.com/2026/02/ccps-an-important-instrument-for-startups-and-ma-structuring/), [Companies Act 2013 Sec 55](https://ca2013.com/issue-and-redemption-of-preference-shares/).

CCPS is the dominant preferred-equity instrument in Indian venture financings. Most Series A/B/C deals into Indian companies are CCPS-structured rather than equity-preferred.

**Why CCPS rather than RCPS or US-style preferred:**
> Per Ministry of Finance guidance (April 30, 2007), "CCPS issued or transferred to any foreign investor would be treated as equity" for FDI sectoral cap purposes. By contrast, non-convertible or optionally convertible preference shares "issued on or after May 1, 2007, would be regarded as debt" subject to External Commercial Borrowings restrictions.

**Plain English.** CCPS bypass the FEMA debt-instrument rules that would otherwise constrain cross-border investment. RCPS (Redeemable, optionally Convertible) is treated as debt under FEMA. So Indian VC deals overwhelmingly use CCPS.

**Mechanics:**
- **Mandatory conversion**, not optional. Conversion happens on a stated trigger (next round, IPO, or fixed date) at a stated ratio (often performance- or valuation-linked).
- **Conversion non-taxable** under Section 47(xb) of the Income-Tax Act, 1961. CCPS-to-equity conversion is explicitly excluded from capital gains tax.
- **Maximum tenure 20 years** (Section 55, Companies Act 2013) — though most CCPS in venture convert well before that.
- **Dividend voting trigger** — under Section 47, if CCPS holders do not receive dividends for two or more consecutive years, they acquire voting rights on all resolutions, similar to equity shareholders. This is a statutory default, not a contractual term.
- **Dividend mechanics** — "paid only when profits are available, thereby preserving cash for operations and growth" (Section 123 distributable-profits constraint).

**For waterfall purposes:**
- Until conversion, CCPS sits ahead of common in the waterfall (preferred treatment).
- The mandatory conversion is a known event with a known ratio, so for a valuation date *after* the conversion trigger has occurred, model CCPS as already-converted common.
- The dividend voting trigger doesn't directly affect waterfall math but does affect protective-provision modeling — CCPS holders who haven't been paid dividends for 2+ years get a statutory blocking right.

### 3. RCPS (Redeemable Convertible Preference Shares)

**Source:** [ICSI Journal Aug 2025](https://www.icsi.edu/media/webmodules/CSJ/August-2025/13.pdf), [Mahwengkwai](https://mahwengkwai.com/wp-content/uploads/2024/04/2024-03-13-Online-Talk-Redeemable-Convertible-Preference-Shares-Raising-Capital-for-Your-Business.pdf).

RCPS combines redemption right and convertibility. Redemption can be at the company's option, the holder's option, or mandatory.

**Mechanics:**
- **Redemption** — can occur out of profits otherwise available for dividend, or out of fresh issue proceeds raised for redemption purposes (Section 55, Companies Act).
- **Mandatory redemption tenure** — within 20 years of issue (or 30 years for infrastructure cos), with at least 10% redeemed per year from year 21 onward.
- **Conversion** — per agreement; can be optional or mandatory.
- **Why RCPS over CCPS** — typically used for domestic Indian capital (where FEMA is irrelevant) or in Singapore/Malaysia structures where the company prefers preserving the option to redeem rather than dilute.
- **Worth noting** — Malaysian RCPS practice (per Mahwengkwai) closely tracks Indian RCPS practice; both share Companies Act lineage.

**For waterfall purposes:**
- RCPS that has been redeemed is gone from the cap table — it's a debt that's been paid.
- RCPS that is still outstanding sits ahead of common like any preferred class.
- The redemption right doesn't directly affect a sale waterfall (deemed liquidation triggers preferences regardless), but it does affect IPO conversion logic — some RCPS auto-redeem at IPO instead of converting.

### 4. Liquidation Preference Norms in SEA

NVCA standard is 1x non-participating. SEA Series A/B trends similarly:
- **India:** 1x non-participating dominant in 2024-2026 venture; 1x participating with cap appears in down rounds and strategic-led deals.
- **Singapore:** 1x non-participating dominant per VIMA 2.0 Long Form Term Sheet annotations.
- **Indonesia:** 1x non-participating common; participating-with-cap occasionally seen in fintech and consumer rounds where strategic participation is high.

No SEA market materially diverges to 2x as default. A 2x preference in any of these jurisdictions is a red flag for valuations purposes — same as in US — and warrants documentation in the side letter inventory.

### 5. Anti-Dilution

VIMA Long Form Term Sheet (per [Bird & Bird](https://www.twobirds.com/en/insights/2019/singapore/venture-capital-investment-model-agreements) and [Allen & Gledhill](https://www.allenandgledhill.com/perspectives/corporate-social-responsibility/venture-capital-investment-model-agreements/) commentary) offers the same three alternatives as NVCA: broad-based weighted average, narrow-based weighted average, full ratchet. Broad-based weighted average is market default in SEA, matching US convention. Indian venture term sheets also default to broad-based weighted average per Cyril Amarchand and Khaitan & Co commentary.

**For our fixtures:** treat anti-dilution as identical to NVCA across SEA jurisdictions unless the specific deal is documented otherwise.

### 6. Tag-Along, Drag-Along, ROFR

**Tag-Along.** SEA convention closely tracks US — minority shareholders can join a sale on the same terms as the seller, with the threshold typically defined as a sale of >50% of the outstanding shares.

**Drag-Along.** Two material differences from NVCA:
- SEA drag thresholds frequently negotiated higher than US norm (60-67% of preferred + founder consent vs US's typical majority-of-preferred). The VIMA Long Form Term Sheet annotation flags this as a negotiation point.
- Indian Companies Act squeeze-out is statutory (Section 235) at 90% threshold, separate from contractual drag.

**ROFR.** SEA convention is similar to NVCA Right of First Refusal and Co-Sale Agreement structure, with the company first, then investors second.

For waterfall purposes, none of these directly affect breakpoint math — they affect *which* exit transactions trigger the preferences.

### 7. Dual-Class Common Structures (India)

Indian venture-backed companies increasingly issue dual-class common with founder voting shares — particularly where founders are concerned about losing control across multiple rounds. SEBI permitted DVR (differential voting rights) shares for listed companies subject to specific framework; for unlisted companies, contractual dual-class is more common.

**Mechanics:**
- Founder shares typically carry 5-10x voting rights of ordinary common.
- Convert to ordinary common on transfer to non-founders, on IPO, or after a stated period.
- **Affect waterfall math** if economic rights differ — but in most Indian structures, voting rights differ while economic rights are identical (so waterfall math is unchanged).

For our SEA edge-case fixture: include a dual-class structure with identical economic rights but differential voting. Annotate the cap table so the tool flags "voting differential present, economic identical" rather than treating it as two separate share classes for breakpoint purposes.

### 8. Indonesia PMA Structures

**Source:** OJK regulations and practitioner notes from local firms. Indonesia is more constrained than India or Singapore for foreign investment — most VC into Indonesian companies flows through PMA (Penanaman Modal Asing / Foreign Investment Company) structures with sector-specific FDI limits.

**For our fixtures:** Indonesia-specific structures don't materially change waterfall mechanics at the cap-table level — the sector caps affect *which investors can participate*, not how preferences flow. So an Indonesian fixture mirrors a Singapore fixture for our purposes, with a note in the side letter inventory about FDI compliance.

---

## Key Takeaways for SEA Fixture Construction

1. **Singapore fixtures use VIMA 2.0 structure** — borrows from NVCA, no material waterfall-math differences. Use VIMA Term Sheet Long Form annotations for any unusual term to ensure precedent traceability.
2. **Indian fixtures use CCPS instead of US-style preferred.** Treat CCPS as preferred for waterfall purposes, with mandatory conversion as a forward-dated event the analyst can model in or out depending on valuation date.
3. **CCPS has a statutory dividend voting trigger** at 2 years of unpaid dividends. This affects protective-provision modeling but not direct waterfall math.
4. **Conversion is non-taxable in India** (Section 47(xb)). Doesn't affect waterfall math but is a relevant audit-memo footnote when discussing fair value of CCPS.
5. **20-year max tenure on CCPS/RCPS** under Section 55. Affects long-dated valuations but rarely a binding constraint for venture timelines.
6. **Liquidation preference norms are 1x non-participating across SEA**, same as US. 2x is a red flag in all three markets.
7. **Anti-dilution defaults to broad-based weighted average across SEA**, same as US.
8. **Drag thresholds run higher in SEA** (60-67% vs US 50%+1). Affects M&A trigger logic but not breakpoint math.
9. **Indian dual-class structures usually have identical economic rights** with voting differentials only — model as one economic class.

The Cap Table Reconciler treats SEA structures as a layer on top of the NVCA baseline, with the SEA-specific divergences flagged as separate metadata fields rather than re-modeled from scratch.
