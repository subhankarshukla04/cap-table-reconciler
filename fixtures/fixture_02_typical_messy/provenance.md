# Provenance — Fixture 02 (Typical Messy)

Every clause in this fixture traces to a published, freely available legal precedent. No client data, no NDA-protected material. The "messiness" is plausible because each gap mirrors a documented practitioner gripe.

## Company

- **Pelaut Logistics Pte. Ltd.** — fictional Singapore-incorporated cross-border logistics SaaS. "Pelaut" is Indonesian/Malay for "sailor"; the Pte. Ltd. structure is the standard Singapore private-company suffix. Cross-border SEA logistics is a real and growing SaaS sector; the company profile is plausible without resembling any specific real company.

## Capital structure (vanilla baseline)

The structural skeleton of this cap table is identical to fixture 01 — three preferred rounds, all 1x non-participating, all broad-based weighted-average anti-dilution, all 1:1 conversion. Same NVCA Model Certificate of Incorporation references apply. See `fixtures/fixture_01_clean/provenance.md` for the standard NVCA citations.

What changes here is the introduction of mess.

## Planted gaps and their precedents

### G02-01 — Stale option pool grant date

The option pool's last grant date (2025-03-01) precedes the Series B closing (2026-03-15). This is one of the documented practitioner gripes: option grants made between rounds are issued at the prior 409A FMV, but a new round can trigger a refreshed FMV for any subsequent grants. The pool itself isn't necessarily wrong, but the analyst needs to confirm whether (a) any post-Series-A grants slipped through under the old FMV, and (b) the option pool was expanded at Series B closing as part of the term sheet (it almost always is).

**Source:** Etonvs, "19 Examples of 409A Material Events"; KLR, "What Events Trigger a 409A Stock Re-Evaluation."

### G02-02 — Unrecorded SAFE conversions

The two outstanding SAFEs (Bridge 2024-A and 2024-B) have valuation caps ($4.5M) below the Series B price implied by the round ($16M raised at $4.00/share = $64M post-money equity at face value). Per Y Combinator's standard SAFE conversion mechanics, these SAFEs convert at the lower of the next-round price or the cap-implied price; with a $4.5M cap on a $64M-post-money round, conversion happens at the cap. They should have converted at Series B closing, but the cap table tab does not show them as Series B Preferred (or Series B Shadow) holders.

This gap is the single most common cap-table-cleanup issue identified in the practitioner research dive. Founders forget to update cap tables at closing. The tool's job is to point out the discrepancy.

**Source:** Y Combinator post-money SAFE template; TheStartupLawBlog, "Convertible Notes & SAFEs Complete Guide"; 409A-valuation.com, "Cap Table & 409A — incomplete documents potentially [add] 1-2 weeks of additional back-and-forth."

### G02-03 — Unrecorded vendor warrant

Vendor warrants — issued in lieu of cash payment for services — are common in early-stage SaaS but rarely make it onto the cap table file unless the analyst asks. The 50,000-share warrant to Northstar Marketing Pte. is plausible: a low-cash startup buying marketing services with equity-linked compensation. Warrants struck at $0.10 with the company at $4.00/share are deep in-the-money and effectively count as fully-diluted common.

**Source:** NVCA Model Documents, warrant template variants. Practitioner gripe documented in 409A-valuation.com cap-table cleanup guide.

### G02-04 — MFN side letter, no terms entered

MFN clauses for strategic investors are a standard NVCA-aligned side letter. A strategic investor who put in a meaningful slice of the round (here, $5M of $16M) often negotiates an MFN as protection against a future round granting better terms to other holders. The clause is referenced in the cap table input but no specific trigger terms have been entered, which is exactly what happens when an analyst is given a cap table file without the accompanying side-letter PDF set.

**Source:** NVCA Model Investors' Rights Agreement, Section 6.X (MFN provisions); standard side-letter convention.

### G02-05 — Anti-dilution variant unspecified

Series A Preferred has anti-dilution rights per the charter, but the variant (broad-based vs narrow-based vs full ratchet) is blank in the cap table file. This is a common upload defect: the cap table SaaS stores share counts and prices but not always the anti-dilution variant.

**Source:** NVCA Model Certificate of Incorporation, Article IV, Section 2.4(d). Defect pattern documented in the cap-table cleanup grunt-task ranking from the practitioner research dive.

## What is intentionally NOT in this fixture

- No participating preferred or caps. (Fixture 03 introduces participating-with-cap.)
- No anti-dilution variant other than broad-based weighted-average and the planted blank. (Fixture 03 introduces a full-ratchet slice on Seed.)
- No RCPS or India/Indonesia-flavored instruments at the share-class level. (Fixture 03 introduces RCPS.)
- No dual-class common voting structure.

## References

- NVCA Model Legal Documents — current edition. https://nvca.org/model-legal-documents/
- Y Combinator post-money SAFE — https://www.ycombinator.com/documents
- AICPA Practice Guide, "Valuation of Privately-Held-Company Equity Securities Issued as Compensation," 2013/2019 edition.
- Etonvs, "19 Examples of 409A Material Events." https://etonvs.com/409a-valuation/409a-material-event/
- 409A-valuation.com, "Cap Table and 409A Valuation." https://409a-valuation.com/insights/cap-table-409a-valuation
- TheStartupLawBlog, "Convertible Notes Complete Guide."
