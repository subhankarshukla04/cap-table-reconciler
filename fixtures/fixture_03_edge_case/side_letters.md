# Side Letters and Off-Charter Documents — Bandhan Ventures Pvt. Ltd.

These documents accompany the cap table upload. They are pasted by the analyst into the side-letter memo panel of the tool, where they are stored verbatim. The tool does not auto-extract structured fields. The analyst is expected to read them and either enter overrides or flag the relevant gap for client follow-up.

---

## Document 1 — Founders' Class A Voting Differential

**Subject:** Founders Common (Class A)

> The Class A Common Stock shall carry five (5) votes per share on all matters submitted to a vote of shareholders. The economic rights of Class A Common, including liquidation preference, dividend rights, and conversion mechanics, shall be in all respects identical to those of ordinary Common Stock. Upon transfer to any holder other than a Founder or a Founder Affiliate, Class A shares shall convert automatically to ordinary Common Stock on a one-for-one basis.

> *(Tool note: voting differential present, economic rights identical. Modeled as a single economic class for waterfall per VIMA / Cyril Amarchand commentary on Indian dual-class structures. Flagged for audit memo capital-structure disclosure. — Planted finding G03-D.)*

---

## Document 2 — Super Pro-Rata Right (Series B Strategic Investor)

**Counterparty:** [Strategic investor — Series B participant, ₹400,000,000 of ₹875,000,000 round]
**Effective:** Series B closing, 2026-04-15

> Super Pro-Rata Right. Notwithstanding any other provision of the Investors' Rights Agreement, the Investor shall have the right to participate in the Company's next preferred equity financing for up to 1.5x its pro-rata share, calculated as 1.5 multiplied by the ratio of the Investor's holdings of Preferred Stock immediately prior to such next financing to the total Preferred Stock then outstanding. This right shall be exercisable for thirty (30) days following written notice of the financing.

> *(Tool note: forward-looking right. Does not affect the present-date waterfall. Capture in subsequent-events or forward-looking-dilution section of audit memo. — Planted finding G03-C.)*

---

## Document 3 — Series Seed Full-Ratchet Anti-Dilution Provenance

**Subject:** Series Seed CCPS, anti-dilution clause origin

> The Series Seed CCPS subscription documents executed in August 2022 include a full-ratchet anti-dilution adjustment in lieu of the broad-based weighted-average mechanism customary in Indian venture financings. This clause was negotiated under the duress of an imminent cash-out event in mid-2022, when the Company had approximately six months of operating runway remaining. The full-ratchet provision has not been triggered as of the valuation date; no subsequent equity financing has occurred at a price-per-share below ₹50.

> *(Tool note: anti-dilution variant rare but documented. Does not affect waterfall at this date because no triggering event has occurred. Flag for audit memo methodology footnote. If a future down-round were to occur, Seed's conversion ratio would adjust to fully restore Seed's economic position. — Planted finding G03-A.)*

---

## Note for the analyst

This fixture's mathematical complexity comes from the participating-with-cap mechanism on Series A. The waterfall has eight breakpoints rather than the seven seen in the cleaner fixtures, because the cap interaction generates three additional regions:

1. The cap-reach point (BP6) where Series A's combined LP + participation hits 3x and the marginal flow to Series A becomes zero.
2. The point at which Series B finds it advantageous to convert (BP7), given that Series A is no longer in the residual pool.
3. The point at which Series A finds it advantageous to abandon the cap entirely and pure-convert (BP8).

The audit memo should walk through each of these breakpoints explicitly. They are not artifacts of the tool — they are the genuine mathematical structure of a participating-with-cap term. An OPM Backsolve built on this waterfall would treat each breakpoint as a separate option strike.
