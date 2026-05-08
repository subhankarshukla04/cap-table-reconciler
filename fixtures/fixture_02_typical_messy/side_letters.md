# Side Letters and Off-Charter Documents — Pelaut Logistics Pte. Ltd.

The following documents accompany the cap table upload. They are pasted by the analyst into the side-letter memo panel of the tool, where they are stored verbatim and displayed alongside the cap table for reference. The tool does NOT auto-extract structured fields from these documents. The analyst is expected to read them and either enter overrides via the structured form or flag the relevant gap in the checklist for client follow-up.

---

## Document 1 — MFN Side Letter

**Counterparty:** [Strategic Investor — Series B participant, $5,000,000 of $16,000,000 round]
**Effective:** Series B closing, 2026-03-15

> Most Favored Nation. If the Company at any time grants to any other holder of preferred stock terms that are more favorable in the aggregate than those granted to the Investor in connection with the Series B Preferred financing, the Company shall promptly notify the Investor and the Investor shall be entitled to elect, by written notice within thirty (30) days, to have such more favorable terms apply retroactively to its Series B Preferred holdings. "More favorable terms" includes, without limitation, liquidation preference multiples, anti-dilution adjustments, and conversion ratios.

> *(Tool note: this clause is referenced in the cap table input but no specific trigger terms have been entered for parsing. The checklist should flag this. — Planted gap G02-04.)*

---

## Document 2 — SAFE Outstanding Disclosure (Bridge 2024-A)

**Counterparty:** [Existing seed investor, accelerated bridge participant]
**Original issuance:** 2024-08-12

> Simple Agreement for Future Equity. Principal: USD 500,000. Valuation cap: USD 4,500,000. No discount. Conversion trigger: next preferred equity financing of at least USD 5,000,000. Conversion: into shares of the Company's preferred stock issued in such financing, at the lower of (i) the price per share in such financing or (ii) the price per share implied by dividing the valuation cap by the company capitalization on a fully-diluted basis immediately prior to such financing.

> *(Tool note: the Series B closing on 2026-03-15 satisfies the conversion trigger ($16M round > $5M threshold). This SAFE should have converted into Series B Preferred (or "Series B Shadow") at closing. The cap table tab does not reflect the conversion. — Planted gap G02-02a.)*

---

## Document 3 — SAFE Outstanding Disclosure (Bridge 2024-B)

**Counterparty:** [New angel investor, bridge participant]
**Original issuance:** 2024-09-04

> Simple Agreement for Future Equity. Principal: USD 500,000. Valuation cap: USD 4,500,000. No discount. Conversion trigger and mechanics identical to Bridge 2024-A.

> *(Tool note: same condition as Bridge 2024-A — should have converted at Series B closing, not reflected on cap table tab. — Planted gap G02-02b.)*

---

## Document 4 — Marketing Vendor Warrant

**Counterparty:** Northstar Marketing Pte. Ltd.
**Issued:** 2025-06-15
**Expires:** 2030-06-15

> In consideration of marketing services rendered, the Company hereby grants the Vendor a warrant to purchase 50,000 shares of Common Stock at a strike price of USD 0.10 per share, exercisable in whole or in part at any time prior to the expiry date.

> *(Tool note: warrant not recorded on the cap table tab. Should appear under fully-diluted common share count and affect breakpoint calculations. — Planted gap G02-03.)*

---

## Note for the analyst

Of these four documents, two are blockers (the SAFEs that should have converted) and two are warnings (the MFN with no terms entered, and the unrecorded vendor warrant). The tool flags all four. The analyst's next step is to either (a) confirm these terms with the client and re-upload a corrected cap table, or (b) enter the missing data through the tool's structured-form override. The tool does not assume what the correct values should be. It points and asks.
