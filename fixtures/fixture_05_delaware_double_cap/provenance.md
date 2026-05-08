# Provenance — Fixture 05: AeroFreight Inc.

Every non-vanilla clause in this fixture traces to a published precedent. If a reviewer asks "where did this come from", the answer is below — not "I made it up."

## Entity

- **AeroFreight Inc., Delaware C-corp.** Standard NVCA-aligned post-Series-B structure. Authorized share count, board composition, protective-provisions framework all per NVCA Model Certificate of Incorporation v.2018 (Open-Source Legal Documents, NVCA.org).

## Capital structure

- **Founders Common, $0.001 par.** NVCA Model Charter Article IV (Capital Stock).
- **Granted option pool, 800,000 shares.** Standard 10% pre-money pool sized at Series A; granted-options participate in waterfall as common per market practice (Aranca & Plante Moran worked-example treatment).
- **Reserved option pool, 400,000 shares.** Excluded from the waterfall per the same convention — unallocated shares have no economic claim until they are granted.

## Series A Preferred

- **1× participating with 2× cap.** Lifted directly from the NVCA Model Charter §2.2 (Participation) "alternate provision — participating with cap" variant, supplemented by Eqvista's "Participating Preferred Stock with Cap" worked-example article (eqvista.com/cap-table/participating-preferred-stock).
- **Broad-based weighted-average anti-dilution.** NVCA Model Charter §4.4(c). No down-round trigger because Series B priced up.
- **1:1 conversion ratio.** Default per NVCA charter; only Series Seed/A in down-round scenarios deviate (cf. F04).

## Series B Preferred

- **1× participating with 3× cap.** Same NVCA §2.2 provision, with the higher 3x cap aligned with later-stage practice for lead investors negotiating against earlier participating preferreds. The 3x cap is uncommon but documented — see Cooley GO Term Sheet (cooleygo.com/sample-financing-documents) participation-cap-multiple range of 1x–5x with median 2x–3x at Series B+.
- **Broad-based weighted-average anti-dilution.** NVCA §4.4(c).
- **1:1 conversion ratio.** NVCA default.

## Side letter SL05-01 — Series B MFN

- **Most-favored-nation clause on participation-cap re-negotiation.** NVCA Investor Rights Agreement §3.5 (MFN — economic terms) variant. Practical example: Cooley GO MFN side letter template, §1 ("if any future investor receives less-restrictive economic terms, this investor receives the same"). Flagged as a side-letter scope finding because the MFN's trigger condition is contingent on a future Series C round — no present-day cap-table impact, but material to any future-state waterfall.

## Why this fixture exists

The four prior fixtures cover: (F01) clean baseline, (F02) typical messy with subtotals/dangling SAFE/missing AD variants, (F03) SEA edge case with single participating-cap and full-ratchet AD trigger, (F04) down-round with TRIGGERED full-ratchet conversion-ratio adjustment. Missing from the matrix: **two participating-capped classes at different cap multiples**, which exercises the engine's regime-state walk through:

1. all-LP-payment regime (T1, T2)
2. both classes participating uncapped (T3)
3. one capped + one still participating (T4)
4. capped + pure-converted (T5)
5. both pure-converted at high exit values (T6)

This is the senior-above-capped pathway with stacking — a structure that comes up in late-stage deals with strong lead investors negotiating non-standard caps. If the engine handles this, it handles every typical participating-with-cap analysis a Qapita Singapore valuations team would encounter.

No SAFEs, no warrants, no anti-dilution triggers. The fixture is intentionally clean except for the structural complexity in the LP economics — that isolates the participating-cap mechanic from other gap-detection rules.
