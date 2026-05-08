# NVCA Model Legal Documents — Reference Summary

> Distilled reference for the Cap Table Reconciler. Every clause we use in fixtures must trace to a source quoted here.

**Primary source:** [NVCA Model Legal Documents](https://nvca.org/model-legal-documents/) — current set updated October 2025.

**Documents in the package:**
- [Certificate of Incorporation (Charter)](https://nvca.org/document/nvca-model-certificate-of-incorporation-updated-oct-2025/) — the share classes, rights, conversion mechanics
- [Stock Purchase Agreement (SPA)](https://nvca.org/document/nvca-model-stock-purchase-agreement-updated-oct-2025/) — the deal contract
- [Investors' Rights Agreement (IRA)](https://nvca.org/document/nvca-model-investors-rights-agreement-updated-oct-2025/) — pro-rata, registration rights, info rights
- [Voting Agreement](https://nvca.org/document/nvca-model-voting-agreement-updated-oct-2025/) — board, drag-along
- [Right of First Refusal and Co-Sale Agreement](https://nvca.org/document/right-of-first-refusal-and-co-sale-agreement-updated-april-6-2026/) — ROFR
- [Model Term Sheet](https://nvca.org/wp-content/uploads/2019/06/NVCA-Model-Term-Sheet-1.doc) — annotated précis with all three alternatives per term

The Term Sheet is the most quotable document because it contains all three alternative formulations of every key term side by side. All language quoted below is from that document unless noted.

---

## 1. Liquidation Preference

Three alternative formulations published as standard market.

### Alternative 1 — Non-Participating (most common, default for "1x non-participating")

> "First pay [one] times the Original Purchase Price [plus accrued dividends] [plus declared and unpaid dividends] on each share of Series A Preferred (or, if greater, the amount that the Series A Preferred would receive on an as-converted basis). The balance of any proceeds shall be distributed pro rata to holders of Common Stock."

**Plain English.** Preferred takes either its money back (with the multiplier) or its as-converted share of the proceeds, whichever is greater. No double-dip. Common takes the rest. This is the dominant structure in 2024-2026 US Series A/B/C term sheets.

### Alternative 2 — Full Participating (the "double-dip")

> "First pay [one] times the Original Purchase Price [plus accrued dividends] [plus declared and unpaid dividends] on each share of Series A Preferred. Thereafter, the Series A Preferred participates with the Common Stock pro rata on an as-converted basis."

**Plain English.** Preferred takes its preference AND keeps its as-converted share of the remainder. Investor-friendly; common-friendly term sheets push back on this.

### Alternative 3 — Capped Participation (the middle ground)

> "First pay [one] times the Original Purchase Price [plus accrued dividends] [plus declared and unpaid dividends] on each share of Series A Preferred. Thereafter, Series A Preferred participates with Common Stock pro rata on an as-converted basis until the holders of Series A Preferred receive an aggregate of [____] times the Original Purchase Price (including the amount paid pursuant to the preceding sentence)."

**Plain English.** Preferred participates up to a stated cap (commonly 2x or 3x of original purchase price), then converts to common. Above the cap, treated as common. Creates an additional breakpoint at the cap level.

### Multiplier conventions

- **1x** is market default in 2024-2026 US venture financings.
- **1.5x** appears in down-round structures and bridge instruments.
- **2x** appears occasionally in down-rounds, distressed financings, or for strategics with leverage.
- **>2x** is highly unusual in venture and a red flag for valuations purposes — Eqvista and Aranca worked examples in the corpus avoid multiples above 1.5x.

### Deemed Liquidation Event (M&A treatment)

> "A merger or consolidation (other than one in which stockholders of the Company own a majority by voting power of the outstanding shares of the surviving or acquiring corporation) and a sale, lease, transfer, exclusive license or other disposition of all or substantially all of the assets of the Company will be treated as a liquidation event (a 'Deemed Liquidation Event'), thereby triggering payment of the liquidation preferences described above."

This is the trigger that makes liquidation preferences relevant in M&A waterfalls — without this clause, preferences would only matter in a literal liquidation/wind-down.

---

## 2. Anti-Dilution Provisions

Three alternative formulations. All three apply only to **down-round** issuances; carve-outs (below) prevent anti-dilution from triggering on routine grants.

### Alternative 1 — Broad-Based Weighted Average (market standard)

> "CP2 = CP1 * (A+B) / (A+C)"

Where:
- **CP2** = Series A Conversion Price immediately after new issue
- **CP1** = Series A Conversion Price immediately prior to new issue
- **A** = Number of shares of Common Stock deemed outstanding immediately prior (includes common, preferred on as-converted basis, and options on as-exercised basis; **excludes** convertible securities converting into the new round)
- **B** = Aggregate consideration received divided by CP1
- **C** = Number of shares issued in the subject transaction

**Plain English.** The conversion price drops, but only proportionally to the size of the down round relative to the existing share base. Most founder-friendly anti-dilution that still gives the investor real protection.

### Alternative 2 — Full Ratchet

> "The conversion price will be reduced to the price at which the new shares are issued."

**Plain English.** If a down round prices at $0.50 and the existing preferred had a $1.00 conversion price, the existing preferred ratchets to $0.50 — i.e., it doubles its as-converted share count. Brutal for founders. Rare in 2024-2026 standard term sheets, occasionally used for strategics or in distressed financings.

### Alternative 3 — None

> "No price-based anti-dilution protection."

Rare except for very early seed rounds.

### Carve-Outs (do not trigger anti-dilution)

> "(i) securities issuable upon conversion of any of the Series A Preferred, or as a dividend or distribution on the Series A Preferred; (ii) securities issued upon the conversion of any debenture, warrant, option, or other convertible security; (iii) Common Stock issuable upon a stock split, stock dividend, or any subdivision of shares of Common Stock; and (iv) shares of Common Stock (or options to purchase such shares of Common Stock) issued or issuable to employees or directors of, or consultants to, the Company pursuant to any plan approved by the Company's Board of Directors"

These four carve-outs are universal across NVCA-flavored documents. Item (iv) is the option-pool carve-out that makes ESOP grants exempt from anti-dilution.

### Narrow-Based Weighted Average

Same formula as Alternative 1 but **A** is narrowed to only the existing preferred class on an as-converted basis (excluding common and options). More investor-favorable than broad-based, less common in market.

---

## 3. Conversion Rights

### Optional Conversion (always 1:1 initially, adjusted by anti-dilution)

> "The Series A Preferred initially converts 1:1 to Common Stock at any time at option of holder, subject to adjustments for stock dividends, splits, combinations and similar events."

The 1:1 initial ratio is the standard. Subsequent down rounds can shift this via anti-dilution.

### Mandatory (Automatic) Conversion

> "Each share of Series A Preferred will automatically be converted into Common Stock at the then applicable conversion rate in the event of the closing of a [firm commitment] underwritten public offering with a price of [____] times the Original Purchase Price (subject to adjustments for stock dividends, splits, combinations and similar events) and [net/gross] proceeds to the Company of not less than $[_____] (a 'QPO'), or (ii) upon the written consent of the holders of [__]% of the Series A Preferred."

**Plain English.** At IPO above a stated price hurdle and proceeds threshold ("Qualified Public Offering" = QPO), preferred converts automatically. Also converts on majority preferred consent. Typical price hurdles are 2-3x of original purchase price; typical proceeds thresholds are $50-100M.

---

## 4. Participation Rights (already covered in Liquidation Preference Alternatives 2 and 3)

The "participation cap" creates an extra breakpoint in the waterfall. Mechanically, capped-participating preferred converts to common when the cap is reached because additional value is allocated as common, not as preferred-plus-participation.

---

## 5. MFN, Pay-to-Play, and Investor Protections

### Pay-to-Play

> "[Unless the holders of [__]% of the Series A elect otherwise,] on any subsequent [down] round all [Major] Investors are required to purchase their pro rata share of the securities set aside by the Board for purchase by the [Major] Investors. All shares of Series A Preferred of any [Major] Investor failing to do so will automatically [lose anti-dilution rights] [lose right to participate in future rounds] [convert to Common Stock and lose the right to a Board seat if applicable]."

**Plain English.** Existing investors must put their share into a down round, or they lose protections. Three menu options for the penalty: lose anti-dilution, lose pro-rata, or auto-convert to common.

### MFN

The NVCA Term Sheet does not include MFN as a default option. MFN clauses appear in side letters and SAFEs. The mechanic: if a later instrument has more favorable terms, the earlier holder gets retroactively bumped up to those terms. Common in seed-stage SAFEs and uncapped notes; less common at Series A+.

### Major Investor Definition

> "A 'Major Investor' means any Investor who purchases at least $[____] of Series A Preferred."

Threshold is negotiated per round; $1-2M is common at Series A, $5-10M+ at later rounds.

---

## 6. Pro-Rata, Super-Pro-Rata, and Registration Rights

### Pro-Rata Participation Right

> "All [Major] Investors shall have a pro rata right, based on their percentage equity ownership in the Company (assuming the conversion of all outstanding Preferred Stock into Common Stock and the exercise of all options outstanding under the Company's stock plans), to participate in subsequent issuances of equity securities of the Company (excluding those issuances listed at the end of the 'Anti-dilution Provisions' section of this Term Sheet). In addition, should any [Major] Investor choose not to purchase its full pro rata share, the remaining [Major] Investors shall have the right to purchase the remaining pro rata shares."

**Plain English.** Major investors can maintain their percentage in future rounds. Carve-outs match the anti-dilution carve-outs. Includes a "gobble-up" clause for unsubscribed pro-rata.

### Super Pro-Rata

Not in the standard NVCA Term Sheet. Negotiated separately via side letter — gives one investor the right to acquire MORE than their pro-rata share, sometimes contractually first-refusal on the entire round. Highly investor-favorable; appears in strategic-led rounds.

### Registration Rights (S-1 demand, S-3 demand, piggyback, lockup)

> "Upon earliest of (i) [three-five] years after the Closing; or (ii) [six] months following an initial public offering ('IPO'), persons holding [__]% of the Registrable Securities may request [one][two] (consummated) registrations by the Company of their shares. The aggregate offering price for such registration may not be less than $[5-15] million."

> "The holders of [10-30]% of the Registrable Securities will have the right to require the Company to register on Form S-3, if available for use by the Company, Registrable Securities for an aggregate offering price of at least $[1-5 million]. There will be no limit on the aggregate number of such Form S-3 registrations, provided that there are no more than [two] per year."

> "Investors shall agree in connection with the IPO, if requested by the managing underwriter, not to sell or transfer any shares of Common Stock of the Company [(including/excluding shares acquired in or following the IPO)] for a period of up to 180 days [plus up to an additional 18 days to the extent necessary to comply with applicable regulatory requirements] following the IPO."

These do not affect waterfall math directly but show up in side-letter inventories that valuations teams reconcile.

---

## 7. Y Combinator SAFE Templates

**Source:** [YC Documents](https://www.ycombinator.com/documents). Three current US SAFE variants:

1. **SAFE: Valuation Cap, no Discount** — converts at the lower of (a) the qualified financing price per share, or (b) the price implied by the valuation cap divided by company capitalization.
2. **SAFE: Discount, no Valuation Cap** — converts at the qualified financing price per share, multiplied by (1 - discount rate).
3. **SAFE: Uncapped MFN (no Cap, no Discount)** — converts at qualified financing price; if any subsequent SAFE/note has better terms, this holder gets bumped to those terms (the MFN trigger).

**Conversion triggers:**
- **Equity Financing** — preferred stock financing for capital-raising purposes. Converts SAFE to "Safe Preferred Stock" at the conversion price (cap-implied or discount-adjusted).
- **Liquidity Event** — change of control or IPO. SAFE holder elects either a return of investment (1x) or conversion to common at a stated cap-implied price.
- **Dissolution Event** — wind-down. SAFE holder receives the purchase amount, after debt and before common equity.

**Post-money vs pre-money distinction.** YC switched the default SAFE from pre-money to post-money in late 2018. Post-money SAFEs cap dilution to founders by treating prior SAFEs as part of the cap-table denominator. This shows up in cap-table reconciliation as: post-money SAFEs need to be modeled with their cap baked into the share count *before* the priced round prices, not after.

**SAFE conversion mechanics for waterfall purposes.** Until conversion, SAFEs are not in the cap table as shares — they're a contingent claim. At the priced round, they convert to a tranche of preferred (or "Safe Preferred Stock") at the cap-implied price. This is one of the most common cap-table cleanup gaps: founders forget to model the SAFE conversion in the round close.

---

## 8. Convertible Notes

NVCA does not publish a standard convertible note template (the SPA + Charter assume a priced round). Cooley GO and YC's SAFE supplant most note usage in venture, but notes still appear. Key terms:

- **Discount** — typical 20% (range 10-25%).
- **Valuation cap** — like SAFE valuation cap; the lower of cap-implied price or financing price applies.
- **Maturity / interest** — typically 18-24 months at 4-8% simple interest. Interest accrues to the principal that converts at the priced round.
- **Qualified Financing trigger** — minimum amount raised in a priced round (typically $1M+) for automatic conversion.

For waterfall purposes, notes that haven't converted are debt — they sit ahead of all equity. Notes that have converted are preferred (or common, depending on the round). Mismatches between "the note has matured but not converted" and "the note converted at the round close" are a chronic cap-table cleanup gap.

---

## Key Takeaways for Fixture Construction

1. **Vanilla baseline = NVCA Term Sheet Alternative 1 across all sections.** 1x non-participating preferred, broad-based weighted average anti-dilution, optional + automatic conversion at QPO, NVCA standard pro-rata, NVCA standard registration rights. Fixture 1 should look like this.
2. **"Typical messy" mess comes from omissions, not exotic terms.** Stale option pool, unrecorded SAFE conversions, advisor warrants outside the cap table, MFN side letters not reflected. Fixture 2.
3. **"Edge case" exotic terms still trace to NVCA alternatives.** Capped participation (Alt 3), full ratchet anti-dilution (Anti-Dilution Alt 2), pay-to-play with auto-convert penalty. Fixture 3.
4. **The carve-outs in anti-dilution are universal.** Any anti-dilution clause we model must respect the four NVCA carve-outs (existing preferred conversions, convertible securities, splits/dividends, ESOP grants).
5. **Multipliers above 2x are red flags.** Stay 1x for vanilla, 1.5x for messy, 2x max for edge case.
