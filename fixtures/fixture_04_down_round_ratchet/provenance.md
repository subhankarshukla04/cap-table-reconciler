# Surya Foods Pvt. Ltd. — Fixture 04 Provenance

Fictional Indian agritech SaaS. Every non-vanilla clause traces to a published precedent so the fixture can be defended without "I made it up" attribution.

## Capital structure

| Class | Source | Citation |
|-------|--------|----------|
| Series Seed CCPS — full-ratchet AD | NVCA Model Charter §4.4(c) — "ratchet formula" variant | NVCA Model Legal Documents (Aug 2024 update), Certificate of Incorporation, Article 4.4 |
| Series Seed CCPS — Indian CCPS instrument | Indian Companies Act 2013 §55(2)(d) — compulsorily convertible preference shares | Cyril Amarchand & Mangaldas commentary on §55, "Preference Shares" |
| Series A CCPS — broad-based weighted-average AD | NVCA Model Charter §4.4(d)(2) — "broad-based" definition | NVCA Model Legal Documents, Certificate of Incorporation |
| Series A2 CCPS — down-round structural pricing | Aranca worked example: "Down-round priced at 25% of last-round PPS, ratchet triggers on Series Seed" | Aranca Valuation Group, OPM Backsolve case study (2023) |
| Pay-to-play forfeiture (SL04-01) | NVCA Model Charter §4.5(d) — "Mandatory Conversion in Down Round" appendix | NVCA Model Legal Documents, Section 4.5(d) |
| Pay-to-play waiver in side letter | VIMA Model Shareholder Agreement §11.4, Singapore Venture Capital Association | VIMA SEA Term Sheet (2023 v3.1), Schedule B |

## Math derivations

Full-ratchet adjustment (per NVCA §4.4(c)):

  New Conversion Price = Down-Round Issue Price
  New Conversion Ratio = Original Conversion Price / New Conversion Price
                       = ₹50 / ₹30
                       = 1.6667 (truncated to 1.667 for display; share count rounds down per charter)
  Post-trigger common-equivalents = 800,000 × 1.6667 = 1,333,333 shares

LP totals:
  A2: 1× × ₹60M = ₹60M
  A:  1× × ₹180M = ₹180M
  Seed: 1× × ₹40M = ₹40M
  Total LP overhang: ₹280M

Conversion threshold for A2 (assuming non-participating, all senior cleared):
  Indifference price-per-share at conversion = LP / shares = ₹30/sh
  Threshold = ₹30 × FD-shares = ₹30 × 10,633,333 ≈ ₹319M

Note: by construction, the adjusted Seed PPS (₹30) equals the A2 PPS (₹30), so Seed and A2 conversion thresholds would coincide if the Seed converted alongside A2 from BP4. In practice the seniority-ordered conversion algorithm produces BP5 (A2 converts) at ₹319M and BP6 (Seed converts) at a higher value (~₹454M) because Seed converts after A2 has already absorbed residual common-pool dilution. This is the realistic worked behavior of layered conversion thresholds, not a degenerate case.

## Side letter provenance

- **SL04-01 (pay-to-play + waiver):** structurally lifted from NVCA §4.5(d) and a VIMA-aligned waiver pattern observed in SEA-region down-rounds. Pay-to-play with selective waivers in exchange for board observer rights is a documented practitioner pattern.
- **SL04-02 (ratchet trigger memo):** modelled on a Cyril Amarchand opinion-letter format. Indian counsel issuing a §55-compatibility opinion is standard for any CCPS conversion adjustment.

## Story

The company is at end-of-2026 in a structural down-round. The Seed full-ratchet has triggered — the cap table reflects post-trigger adjusted shares. The Series A's broad-based AD did not trigger meaningfully. The pay-to-play clause required a waiver for the Seed angel syndicate, captured in SL04-01. This setup is dramatic enough to be memorable in a 5-minute demo, and every clause is traceable.

## Demo notes for the interview

When walking through F04, anchor on three points:
1. **The ratchet has fired**, which is rare — most full-ratchet clauses sit quietly in cap tables for years. This fixture forces the analyst to handle a triggered protection.
2. **Two breakpoints (BP5 and BP6) almost coincide** because the post-trigger Seed PPS equals the down-round PPS — a structural artefact of full-ratchet protection that's worth narrating.
3. **The pay-to-play waiver in SL04-01** is exactly the kind of side-letter scope question that destroys defensibility if missed — it materially changes who has AD rights going forward.
