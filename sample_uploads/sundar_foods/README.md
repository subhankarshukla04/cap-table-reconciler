# Sundar Foods Pvt. Ltd. — sample upload set

Fictional Indian D2C health-foods company, Series B-1 just closed (Mar 2026). These files are designed to be **uploaded into the Cap Table Reconciler at http://127.0.0.1:5050/** and behave like a real client hand-off — not a fixture tuned to the parser.

## Files

- `Sundar_CapTable_v7_FINAL_v3.xlsx` — the cap table (upload this on the home page).
- `01_Mira_Capital_Side_Letter_2025-02-14.pdf` — 2x LP override, MFN, no AD for Mira.
- `02_TigerLion_SHA_Excerpt_Section_4-6_2026-03-15.pdf` — full-ratchet override for lead.
- `03_Veritas_Industries_Strategic_Investment_Letter_2026-03-29.pdf` — 7-yr redemption, IPO veto.
- `04_SAFE_500_Global_2024-01-11.pdf` — YC post-money SAFE, conversion pending.
- `05_Surya_Capital_AD_Reset_Notice_SCAN.pdf` — letter formatted to mimic a scan.

## What the tool should flag (without being told)

- Holder-level cap-table instead of class-level — same class name appears across many rows.
- Two **Equity Common** rows for Karthik / Priya (duplicate class name → Pydantic).
- Mehta Family Trust (8,50,000 sh.) — type marked 'Equity Common' but flagged TBC in READ ME.
- Series A2 row for Surya has blank anti-dilution column.
- Mira Series A3-Ext. row — LP, AD, seniority all say 'See side letter'.
- Series B-1 LP type '1x non-cum, non-part w/ catch-up' — engine won't recognise the alias.
- Veritas Industries row — no price, no LP, no class type, just 2,00,000 shares + a note.
- `Conv. Instruments` tab name doesn't match the parser's whitelist → SAFEs / CCDs / warrants invisible.
- `Co. Info` tab name doesn't match → company defaults to 'Unnamed Company'.
- `ESOP` tab is per-employee with a 'Lapsed' row — not the granted/reserved split the engine expects.
- Date formats: `15-Mar-2026`, `15/03/2026`, `14th Feb '25` (last one will not parse).
- Mira side letter (PDF 01) — 2x LP overrides charter 1x.
- TigerLion SHA (PDF 02) — full-ratchet override for the lead but BB-WA for everyone else.
- Veritas (PDF 03) — redemption + IPO veto, neither modelled by engine; class designation in dispute.
- 500 Global SAFE (PDF 04) — Series B-1 satisfied the trigger, but conversion paperwork pending.
- Surya AD reset (PDF 05) — laid out as a scan with Courier body; pdfplumber will return text but the   parser's heuristic title detection will pick the wrong line.

## Constraints respected (engine limits)

- Share class types limited to: common, preferred, option_pool_granted, option_pool_reserved
- LP types: non-participating, participating-uncapped, participating-capped
- AD variants: BB-WA, NB-WA, full-ratchet
- Currency: INR (₹), engine maps `INR` → `₹` automatically
- No off-engine instruments (the redemption right and IPO veto are mentioned in PDFs only, not in xlsx)
