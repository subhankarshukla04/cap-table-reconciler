# Tender Radar — Demo Build Spec

**Project:** Tender Radar
**Target interview:** Olesia Sheremeta (Founders Office, Qapita Singapore), 30-min Calendly, NOC Inbound program
**Build window:** 7 days from kickoff
**Author:** Subhankar Shukla
**Status:** FROZEN — once `app.py` lines start, this file is read-only

This document is the single source of truth for the demo build. `OLESIA_RESEARCH.md` is the research dump. `ELIMINATION.md` is the audit log. **This file** is the contract.

---

## 1. Problem statement

### 1.1 The desk's job, in one sentence

Qapita's Secondaries / Marketplace desk's recurring question is: **"which issuer on our roster should we approach about a tender offer in the next 30–90 days, and how big can that tender realistically be?"**

That decision today is made by an analyst reading:
- VCCircle / Inc42 / YourStory every morning for fundraise news
- UnlistedKart (now Qapita-owned) for unlisted-share price drift
- SEBI EDIFAR for DRHP filings
- SEBI + RBI press releases for regulatory deltas
- Google News for layoff / ESOP-cliff signals on the issuer roster

Then cross-referencing all of it against the internal cap-table data to estimate eligible pool size, expected scaleback, India compliance load, and stamp-duty exposure. **That cross-reference is hours of manual work per issuer, per week.**

### 1.2 The non-goal — what we are *not* automating

Per the same rule that governed the Evelyn build:

> **We do not automate the part the team is paid to do.**

The desk is paid to **decide which issuer to call, at what price, with which buyers.** Tender Radar makes **zero** decisions on:
- Pricing (every price is an input, never an output)
- Buyer selection
- Whether to actually launch a tender
- Valuation methodology

What it automates is the **pre-decision intelligence layer** — the morning reading + the manual cross-reference. The analyst still chooses, still calls, still negotiates. Tender Radar just gives them a sorted starting list.

### 1.3 Why this shape, not a workflow tool

The audit in `ELIMINATION.md` established that workflow tools (eligibility calculator, FEMA pre-check, ROFR tracker, comms tracker, buyer matcher) all read as **one-shot transactional features** — the kind Qapita's product team builds for the platform. They prove engineering, not market understanding.

The Wego Earnings Digest and Qatalyst Sentinel precedents work because they deliver **a signal the team reads every morning**. They integrate into the operating rhythm of the desk, not just the deal pipeline.

Tender Radar is shaped the same way: a daily HTML digest plus threshold-based Bark alerts, with the workflow engines (mechanics + compliance) collapsed into a per-issuer **preview** the analyst can click into from the digest. This is the dominant design.

---

## 2. The demo — what Olesia sees in 5 minutes

This is the script the build serves. Every architectural decision below answers to this script.

### 2.1 Opening line (0:00–0:15)

> "This tool reads five public feeds every morning and ranks the 50 most-likely-next-tender issuers on Qapita's roster. Click any issuer and you see the mechanics and India-compliance picture for a hypothetical tender on that company. It makes zero pricing judgments — every score is rule-based and explainable. The price is your input, never my output."

### 2.2 Screen 1 — the morning digest (0:15–1:30)

URL: `localhost:5000/`

Single-page HTML view. Date stamp at the top: "Tender Radar — Monday 18 May 2026 — 07:00 SGT".

A ranked table of the top 10 issuers (out of ~15 in the fixture roster):

| Rank | Issuer | Score | Trigger | Last update |
|---|---|---|---|---|
| 1 | Razorpay | 87 | +25 DRHP filed Apr 2026; +30 Series F now 22 months old | 06:48 |
| 2 | Acko | 79 | +20 last round 38 months old; +15 unlisted price +24% MoM | 06:42 |
| ... | | | | |

Beneath the table: a strip showing today's **regulatory delta** ("RBI Master Direction on Foreign Investment update — 14 May 2026"), and **5 fresh signals** that didn't move scores enough to crack the top 10 but are still worth a glance.

The visual style: muted blue-grey, monospace numbers, audit-firm aesthetic. No gradients, no animations. Same standard as the Evelyn build.

### 2.3 Screen 2 — per-issuer detail (1:30–4:00)

Click "Razorpay" → `localhost:5000/issuer/razorpay`.

Three stacked sections:

**A. Score breakdown** (full rule-by-rule decomposition)
- `+30` Series F closed 22 months ago — fundraise-age band [18–36mo]
- `+25` DRHP filed 14 Apr 2026 — pre-IPO secondary window opening
- `+15` Unlisted-share price up 24% in 30 days (UnlistedKart)
- `+10` 3 "ESOP cliff" mentions in employee-side news (last 30 days)
- `+7` Employee count > 500 multiplier
- = **87 / max 100**
- *Every component links to the underlying signal URL.*

**B. Mechanics preview** — the Idea-1 engine
- Tender size input: `[ $20M ]` (HTMX slider, 5–100M range)
- Price-per-share input: `[ last round $0.84 ]` (editable)
- Eligibility filter: `[ vested ESOPs + ex-employees < 12mo ]`
- Outputs (recomputed live on slider change):
  - Eligible holder count: 412
  - Eligible unit pool: 31.2M shares ($26.2M at input price)
  - Indicative scaleback if 2× oversubscribed: 0.76
  - Top-10 holder concentration: 38% of pool
- Bottom of section: "Download offer-letter pack (412 PDFs)" link → generates mail-merged sample for 3 holders

**C. Compliance preview** — the Idea-2 engine
- Issuer state: `Karnataka` (auto-filled from issuer record)
- Assumed seller mix: 78% resident India, 14% NRI, 8% foreign (auto-filled, editable)
- Outputs:
  - RBI pricing-floor verdict: **PASS** (input price ₹70 vs RBI floor ₹62, computed from last round + DCF placeholder NAV)
  - Form FC-TRS estimated volume: **57 filings** (14% NRI × 412 holders)
  - Stamp duty exposure (Karnataka, 0.015% on share transfer): **₹2.6 lakh**
  - Required attachments checklist: 7 items

### 2.4 Screen 3 — the history view (4:00–4:30)

URL: `localhost:5000/history`

A simple table: last 7 daily digests, each row showing top-3 issuers and the alert that fired (if any). Demonstrates the recurring-cadence shape without needing 30 days of fixture data.

### 2.5 Bark alert demo (4:30–5:00)

Trigger a synthetic signal that pushes a fixture issuer over the score-80 threshold → live Bark push to the user's phone during the call. Same channel as the finance-digest at 9:30 PM IST. Mirrors the operating rhythm Olesia already lives in if her colleagues use similar tools.

### 2.6 Close

> "The scrapers are deliberately throwaway — once I'm inside Qapita and your internal cap-table and deal-pipeline data is plugged in, the same digest becomes the desk's daily operating dashboard, with no scrapers to maintain. The durable parts are the mechanics and compliance engines underneath — that's what I'd keep building over a 6-month internship."

---

## 3. Architecture overview

```
                  ┌─────────────────────────────┐
                  │   5 SCRAPERS (cron, 06:30)  │
                  │  - inc42_rss                 │
                  │  - unlistedkart_html         │
                  │  - sebi_edifar_drhp          │
                  │  - sebi_rbi_press            │
                  │  - googlenews_employee       │
                  └──────────────┬──────────────┘
                                 │  Signal[]
                                 ▼
                  ┌─────────────────────────────┐
                  │   STORAGE (SQLite, local)   │
                  │  issuers / signals / runs   │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                  ┌─────────────────────────────┐
                  │   SCORING ENGINE             │
                  │  rules.py — pure functions   │
                  └──────────────┬──────────────┘
                                 │  TenderReadinessScore[]
                                 ▼
   ┌────────────────────┐  ┌────────────────────┐  ┌──────────────┐
   │  MECHANICS ENGINE  │  │ COMPLIANCE ENGINE  │  │ BARK PUSH    │
   │  (from Idea #1)    │  │ (from Idea #2)     │  │ on score>80  │
   └─────────┬──────────┘  └─────────┬──────────┘  └──────────────┘
             │                       │
             └────────────┬──────────┘
                          ▼
                  ┌─────────────────────┐
                  │  FLASK + HTMX UI    │
                  │  /, /issuer/<id>,   │
                  │  /history           │
                  └─────────────────────┘
```

**Key invariants:**
- Every engine is a **pure function** of typed pydantic inputs. No global state, no I/O inside the calc path.
- The frontend is **server-rendered Jinja2 + HTMX**. No SPA, no React. Inline `<style>` block in the base template; no Tailwind build.
- **No LLM anywhere in the calc pipeline.** Scrapers use deterministic CSS selectors + regex. Scoring is rule-based. Mechanics + compliance are typed arithmetic.

---

## 4. Backend — deep mapping

### 4.1 Data model

All models live in `src/models.py` as pydantic v2 classes. Persisted via SQLite using SQLModel-compatible mapping; the schema is intentionally small.

```python
# src/models.py (sketch — final code may differ)

class Issuer(BaseModel):
    id: str                    # slug, e.g. "razorpay"
    legal_name: str
    sector: str
    geography: Literal["IN", "SEA", "US", "MENA"]
    state: str | None          # Indian state for stamp duty (e.g., "Karnataka")
    employee_count: int | None
    founded_year: int | None
    last_round_amount_usd: float | None
    last_round_date: date | None
    last_round_price_per_share_usd: float | None
    last_round_price_per_share_local: float | None  # for India: INR
    share_classes: list[ShareClass]
    on_qapita_roster: bool      # all True in demo fixture

class ShareClass(BaseModel):
    name: str                   # "Series F Pref", "Common", "ESOP Pool"
    liquidation_pref_multiple: float = 1.0
    participating: bool = False
    participation_cap: float | None = None
    conversion_ratio: float = 1.0
    units_outstanding: int

class Signal(BaseModel):
    id: str                     # uuid
    issuer_id: str
    source: Literal[
        "inc42_rss", "unlistedkart_html", "sebi_edifar_drhp",
        "sebi_rbi_press", "googlenews_employee"
    ]
    signal_type: Literal[
        "fundraise_age", "price_drift", "drhp_filing",
        "reg_delta", "employee_pressure"
    ]
    value: float | str          # numeric (months, % change) or string (title)
    url: str
    captured_at: datetime
    raw_payload: dict           # full upstream payload, opaque

class TenderReadinessScore(BaseModel):
    issuer_id: str
    score: int                  # 0–100
    components: list[ScoreComponent]
    computed_at: datetime

class ScoreComponent(BaseModel):
    rule_id: str                # "fundraise_age_18_36"
    points: int
    rationale: str              # "Series F closed 22 months ago"
    signal_url: str | None      # link back to upstream

class DigestRun(BaseModel):
    run_date: date
    top_10_issuer_ids: list[str]
    alerts_fired: list[str]     # issuer_ids that crossed the threshold
    fresh_signal_count: int
    started_at: datetime
    finished_at: datetime
```

### 4.2 The scrapers

Each scraper is a module under `src/scrapers/` exposing a single function `fetch() -> list[Signal]`. They share a thin base class for rate-limit + retry + cache logic.

| Module | Source URL | Method | What it produces | Fragility notes |
|---|---|---|---|---|
| `inc42_rss.py` | `https://inc42.com/feed/` (and YourStory + VCCircle equivalents) | `feedparser` RSS | `fundraise_age` signals — parses titles like "Razorpay raises $X in Series F" + the article date | Title regex is brittle; backup is manual fixture cron entry |
| `unlistedkart_html.py` | `https://www.unlistedkart.com/buy-share/<slug>` (Qapita-owned, on-brand demo tell) | `httpx` + `selectolax` CSS selector | `price_drift` signals — compares scraped price to 30-day moving average from local cache | Anti-bot risk; respect robots.txt; 10s rate-limit between calls |
| `sebi_edifar_drhp.py` | `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3` | `httpx` + `selectolax` HTML table parse | `drhp_filing` signals — flags any DRHP filed in last 90 days where filer name fuzzy-matches an issuer on roster | Filer-name fuzzy match needs a hand-curated alias map |
| `sebi_rbi_press.py` | `https://www.sebi.gov.in/sebirss.xml` + `https://www.rbi.org.in/Scripts/Rss_Custom.aspx?Id=70` | RSS | `reg_delta` signals — keyword filter on `["private", "secondary", "FC-TRS", "transfer", "unlisted", "preferential"]` | Low-volume; manual review fine |
| `googlenews_employee.py` | `https://news.google.com/rss/search?q=<issuer>+layoffs+OR+ESOP+OR+attrition&hl=en-IN` | RSS | `employee_pressure` signals — count of articles per issuer per 30-day window | Lots of noise; filter on negative-sentiment keyword list (no LLM — just keyword filter) |

**Operational notes:**
- All scrapers respect a `MAX_RUNTIME_S=120` budget; if a source times out, it's skipped, and a stale-source warning shows in the digest footer.
- Output cached to `data/scraper_cache/<source>/<yyyy-mm-dd>.json` so the demo can run **offline** during the interview if Wi-Fi is bad.
- Each Signal carries the upstream URL so every score component in the UI links back to the source. **Provenance is non-negotiable** — same audit-firm rule from the Evelyn build.

### 4.3 The scoring engine

File: `src/scoring.py`. Pure functions only. **No I/O, no DB calls.**

```python
def score_issuer(issuer: Issuer, signals: list[Signal], today: date) -> TenderReadinessScore:
    components = []
    components += score_fundraise_age(issuer, today)
    components += score_price_drift(issuer, signals)
    components += score_drhp_filing(issuer, signals, today)
    components += score_employee_pressure(issuer, signals, today)
    components += score_employee_count_multiplier(issuer)
    total = min(100, sum(c.points for c in components))
    return TenderReadinessScore(
        issuer_id=issuer.id,
        score=total,
        components=components,
        computed_at=now(),
    )
```

**Rules table (v0):**

| Rule ID | Condition | Points |
|---|---|---|
| `fundraise_age_under_12` | Last round < 12 months ago | 0 |
| `fundraise_age_12_18` | Last round 12–18 months | +15 |
| `fundraise_age_18_36` | Last round 18–36 months | +30 |
| `fundraise_age_over_36` | Last round > 36 months | +20 |
| `price_drift_positive_20` | Unlisted price up >20% MoM | +15 |
| `price_drift_positive_10` | Unlisted price up 10–20% MoM | +8 |
| `drhp_filed_90d` | DRHP filed in last 90 days | +25 |
| `employee_pressure_3plus` | 3+ negative-keyword mentions in 30d | +10 |
| `employee_pressure_1_2` | 1–2 mentions | +4 |
| `employee_count_500plus` | Headcount > 500 | +7 |

**Max raw score: 87.** Cap at 100. Threshold for Bark alert: **80**.

Why 80 and not higher: with the fixture roster, 2–3 issuers should sit above 80 on demo day (DRHP + aged round = automatic 55+, anything else pushes it). Tunable in `src/scoring_config.py`.

**Why rule-based, not ML:** explainability is the entire point. Every component in the UI says "+30 because Series F closed 22 months ago." An ML model can't justify itself that way to a regulator-facing team.

### 4.4 The mechanics engine

File: `src/mechanics.py`. Pure functions. **Tested against golden-file fixtures from the Evelyn build.**

```python
class TenderParams(BaseModel):
    tender_size_usd: float
    price_per_share_usd: float
    eligibility_filter: EligibilityFilter

class EligibilityFilter(BaseModel):
    include_vested_esops: bool = True
    include_ex_employees_within_months: int | None = 12
    include_class_action: list[str] = []  # "Common", "Series A Pref", etc.
    min_vesting_months: int = 12
    exclude_foreign_holders: bool = False

class WaterfallPreview(BaseModel):
    eligible_holder_count: int
    eligible_unit_pool: int
    eligible_pool_usd: float
    scaleback_factor_if_2x: float
    top_10_concentration_pct: float
    per_class_breakdown: list[ClassAllocation]

def preview_tender(
    issuer: Issuer,
    holders: list[Holder],          # synthetic for demo — see fixtures
    params: TenderParams,
) -> WaterfallPreview:
    eligible = [h for h in holders if is_eligible(h, params.eligibility_filter)]
    pool = sum(min(h.sellable_units, h.vested_units) for h in eligible)
    pool_usd = pool * params.price_per_share_usd
    demand_usd = params.tender_size_usd
    scaleback = min(1.0, demand_usd / pool_usd) if pool_usd > 0 else 1.0
    scaleback_2x = min(1.0, demand_usd / (pool_usd * 2)) if pool_usd > 0 else 1.0
    ...
    return WaterfallPreview(...)
```

**Demo waterfall complexity is intentionally narrow:**
- Single-class tenders only (Common + vested ESOP)
- Pro-rata scaleback (no priority tranches)
- No participation-preferred conversion math in the demo

The deeper math (CCPS-with-cap, RCPS, dual-class breakpoints) sits in `src/mechanics_advanced.py` from the Evelyn build but is **not wired into the UI** for the demo. Mention it in the close: "the engine handles full SEA waterfall complexity — the demo just exposes the simple path so we can show the live recompute."

### 4.5 The compliance engine

File: `src/compliance.py`. Pure functions.

```python
class ComplianceParams(BaseModel):
    issuer_state: str           # "Karnataka"
    seller_mix: SellerMix       # % resident / NRI / foreign
    share_class: str
    transfer_price_per_share_inr: float
    rbi_fair_value_per_share_inr: float   # computed elsewhere; not our judgment

class CompliancePreview(BaseModel):
    rbi_floor_verdict: Literal["PASS", "FAIL", "MARGINAL"]
    rbi_floor_delta_pct: float
    fc_trs_filings_estimated: int
    stamp_duty_inr: float
    stamp_duty_rate_used: float
    state_duty_citation: str
    required_attachments: list[str]
```

**Rule-set (v0):**

- **RBI floor check:** if seller is resident and buyer is NRI, transfer price must be ≥ RBI fair value (per ICAI-prescribed method). Output PASS/FAIL/MARGINAL with delta.
- **FC-TRS volume estimate:** `count(NRI sellers) × eligible_holders` ÷ 100. One filing per cross-border transfer leg.
- **Stamp-duty matrix** (`src/stamp_duty.py`): hard-coded 5 states for the demo — Maharashtra (0.005% on duty-stamp share transfer), Karnataka (0.015%), Tamil Nadu (0.005%), Delhi (0.25% capped), Telangana (0.015%). Each cites the relevant state stamp act. **Updated as of FY26**; flag staleness if state-act amended.
- **Required attachments:** static list per transfer type — PAN, FIRC for inward, valuation certificate, board approval, SHA waiver, Form FC-TRS, KYC bundle.

**Crucially: we publish zero opinions on legality.** The output is a *checklist verdict + numeric estimates*. A real transaction still needs counsel sign-off. This sentence appears in the UI footer.

### 4.6 The digest renderer

File: `src/digest.py`.

```python
def render_morning_digest(
    run_date: date,
    scores: list[TenderReadinessScore],
    reg_delta_signals: list[Signal],
) -> str:  # HTML
    top_10 = sorted(scores, key=lambda s: s.score, reverse=True)[:10]
    template = jinja_env.get_template("digest.html.j2")
    return template.render(
        run_date=run_date,
        top_10=top_10,
        reg_delta=reg_delta_signals[:3],
        fresh_signals=fetch_fresh_today(),
    )
```

The digest is **also persisted as a flat HTML file** at `data/digests/<yyyy-mm-dd>.html`, so the `/history` view is just a directory listing. No DB query needed for history. Same pattern as the user's existing finance-digest.

### 4.7 The Bark notifier

File: `src/bark.py`. Reads `BARK_DEVICE_KEY` from `.env`. Same channel as finance-digest.

```python
def send_alert(score: TenderReadinessScore, issuer: Issuer) -> None:
    title = f"Tender Radar: {issuer.legal_name} → {score.score}"
    body = f"Top trigger: {score.components[0].rationale}"
    url = f"http://localhost:5000/issuer/{issuer.id}"
    httpx.post(f"https://api.day.app/{key}/{title}/{body}?url={url}")
```

Fire once per issuer per crossing event — don't spam if score stays above threshold across days.

### 4.8 Orchestration

File: `src/orchestrator.py`. The morning run:

```
06:30 — scrapers run in parallel (asyncio.gather)
06:33 — signals persisted to SQLite
06:34 — scoring engine runs over all issuers
06:35 — digest renderer writes data/digests/<today>.html
06:36 — Bark fires for any newly-crossed issuers
```

In demo mode (`make demo`): all five scrapers replaced with `data/scraper_cache/<source>/2026-05-18.json` fixtures, so the run completes in <2 seconds and the digest is reproducible.

---

## 5. Frontend — deliberately simple

Three routes. Server-rendered Jinja2 templates. HTMX for the per-issuer mechanics slider. No JavaScript framework. Inline `<style>` block in `base.html.j2`. Same visual standard as Evelyn build.

| Route | Template | Purpose |
|---|---|---|
| `GET /` | `digest.html.j2` | Today's digest, top-10 table + reg delta strip |
| `GET /issuer/<id>` | `issuer.html.j2` | Score breakdown + mechanics preview + compliance preview |
| `POST /issuer/<id>/preview` | `_preview.html.j2` partial | HTMX target — recomputes waterfall when user changes tender size or price |
| `GET /history` | `history.html.j2` | List of past digests (directory listing) |
| `GET /static/styles.css` | static | One file, ~80 lines |

**Style rules (carry-over from Evelyn):**
- Muted blue-grey (`#3a4859`, `#e8ecef`), one accent (`#1f4e79` for headers)
- All numerics in `JetBrains Mono` (CDN)
- All non-numeric text in `Inter` (CDN)
- No gradients, no shadows, no rounded corners > 2px
- No emojis, no playful microcopy
- Table-heavy layout — this is a workpaper tool, not a SaaS landing page
- Every cited fact carries a small superscript URL link back to the source

---

## 6. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | Match Evelyn build, virtualenv already configured |
| Web | Flask 3.x | Same as Evelyn |
| Templates | Jinja2 | Same |
| Interactivity | HTMX 1.9 (CDN) | Same |
| Data validation | pydantic v2 | Same |
| HTTP | httpx | async support, modern |
| HTML parsing | selectolax | fast CSS selector parsing |
| RSS | feedparser | well-established |
| DB | SQLite (file-based) | local-only demo; no Postgres needed |
| Cron | `apscheduler` (in-process) | local-first; no system cron config |
| PDF | `weasyprint` | only for offer-letter sample export; reuse from Evelyn |
| Notifications | Bark (HTTP API) | parity with finance-digest |
| Tests | pytest + golden-file fixtures | match Evelyn discipline |

**Dependencies to add to `pyproject.toml`** (incremental over Evelyn's existing list):
```
httpx, selectolax, feedparser, apscheduler
```

---

## 7. Repository layout

```
~/Desktop/qapita/
├── app.py                          # existing Evelyn app — UNCHANGED
├── PLAN.md                         # Evelyn plan — UNCHANGED
├── CONTEXT.md                      # Evelyn context — UNCHANGED
├── OLESIA_RESEARCH.md              # interview #2 research
├── ELIMINATION.md                  # audit log
├── SPEC_OLESIA.md                  # ← this file
├── radar/                          # ← NEW — entire Tender Radar lives here
│   ├── __init__.py
│   ├── app.py                      # Flask app — separate port (5001)
│   ├── models.py                   # pydantic models
│   ├── db.py                       # SQLite helpers
│   ├── scoring.py
│   ├── scoring_config.py           # rule weights + thresholds
│   ├── mechanics.py                # imports from existing Evelyn mechanics
│   ├── compliance.py
│   ├── stamp_duty.py               # 5-state matrix
│   ├── digest.py
│   ├── bark.py
│   ├── orchestrator.py             # the 06:30 daily run
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py                 # rate-limit + cache + retry
│   │   ├── inc42_rss.py
│   │   ├── unlistedkart_html.py
│   │   ├── sebi_edifar_drhp.py
│   │   ├── sebi_rbi_press.py
│   │   └── googlenews_employee.py
│   ├── templates/
│   │   ├── base.html.j2
│   │   ├── digest.html.j2
│   │   ├── issuer.html.j2
│   │   ├── _preview.html.j2        # HTMX partial
│   │   └── history.html.j2
│   └── static/
│       └── styles.css              # ~80 lines, one file
├── data/
│   ├── radar.db                    # SQLite, gitignored
│   ├── scraper_cache/              # gitignored
│   │   └── inc42_rss/2026-05-18.json
│   ├── digests/                    # HTML snapshots, gitignored
│   │   └── 2026-05-18.html
│   └── fixtures/
│       ├── issuers.json            # 15 issuers, hand-curated
│       └── holders/                # synthetic cap-table per issuer
│           └── razorpay.json
└── tests/
    ├── test_scoring.py             # rule-by-rule
    ├── test_mechanics.py           # golden-file
    ├── test_compliance.py          # golden-file
    └── test_scrapers.py            # snapshot tests against captured HTML
```

**Reuse from Evelyn build:**
- `mechanics_advanced.py` (waterfall math for SEA share classes) — imported, not duplicated
- `templates/base.html.j2` styles — copy and adapt
- `weasyprint` PDF generation utilities — imported

---

## 8. Fixture roster — 15 issuers

These are the issuers on Qapita's public client list (per `OLESIA_RESEARCH.md` Part 3). Each gets a hand-curated `Issuer` record + a synthetic `holders/*.json` cap-table.

| ID | Legal name | Sector | State | Last round | Round date | On purpose |
|---|---|---|---|---|---|---|
| razorpay | Razorpay Software Pvt Ltd | Fintech | Karnataka | Series F | 2024-07 | High-score showcase (DRHP + aged round) |
| acko | Acko Technology & Services | Insurance | Karnataka | Series D | 2022-10 | Aged round, mid-score |
| zepto | Kiranakart Technologies | Q-commerce | Maharashtra | Series F | 2024-11 | Too-recent round, low score (control) |
| ather | Ather Energy | EV | Karnataka | IPO 2024 | Listed | Reg-delta only signal |
| pinelabs | Pine Labs | Fintech | Karnataka | Series I | 2022-05 | Aged, DRHP-stage |
| boat | Imagine Marketing | Consumer | Maharashtra | Series B | 2021-01 | Very aged, employee pressure |
| oyo | Oravel Stays | Travel | Delhi | Pre-IPO | 2024 | Reg + DRHP signal |
| physicswallah | PW Edutech | Edtech | Delhi | Series A | 2022-12 | Aged + cliff signal |
| purplle | Manash Lifestyle | Beauty | Maharashtra | Series E | 2022-08 | Aged + price drift |
| rebelfoods | Rebel Foods | F&B | Maharashtra | Series F | 2021-10 | Very aged, distress signal possible |
| spinny | Valerian Corp | Auto | Delhi | Series E | 2022-12 | Aged |
| souledstore | The Souled Store | Apparel | Maharashtra | Series C | 2024-06 | Recent — low score control |
| urbancompany | Urban Company | Services | Delhi | DRHP filed | 2025-12 | Pre-IPO showcase |
| zetwerk | Zetwerk Manufacturing | Industrial | Karnataka | Series F | 2022-08 | Aged + size |
| indegene | Indegene Ltd | Healthtech | Karnataka | IPO 2024 | Listed | Out-of-roster control |

**3 of these are designed to score >80 on demo day:** Razorpay, Urban Company, Pine Labs.
**3 are designed to score <30** so the ranking is visibly meaningful: Zepto, Souled Store, Indegene.

---

## 9. Non-goals (explicit)

Per build discipline — listing what we are deliberately not doing, to keep scope tight.

- **No pricing/valuation output** of any kind, anywhere. Every price is an input.
- **No buyer-side data**. Tender Radar is sell-side/issuer-side only.
- **No LLM in the calc pipeline.** Scrapers, scoring, mechanics, compliance are all deterministic.
- **No multi-tenant**. Single user, single roster, localhost-only.
- **No auth**. Localhost demo. Adding auth burns days for zero demo value.
- **No real email send**. The "download offer-letter pack" link generates PDFs to disk; no SMTP.
- **No live deal pipeline**. The mechanics preview uses synthetic holders fixtures, clearly labeled.
- **No advanced waterfall types in the UI**. The engine handles them; the UI exposes only the simple path.
- **No mobile**. Desktop screen-share only.
- **No production hardening of scrapers**. They're cached; if a source breaks the demo on the day, we fall back to cached JSON without anyone noticing.

---

## 10. Build plan — 7 days

| Day | Output | Acceptance criterion |
|---|---|---|
| **1** | Repo scaffold + `radar/` skeleton; pydantic models; SQLite schema; 15-issuer fixture roster loaded | `make seed` runs; `radar.db` populated; one passing pytest |
| **2** | All 5 scrapers ship a `fetch() -> list[Signal]` function; cached JSON for offline demo | `make scrape-cached` produces signals; integration test green |
| **3** | Scoring engine — all 10 rules wired with rationale strings; threshold logic | `pytest tests/test_scoring.py` — 100% rule coverage, 3 fixture issuers cross 80 |
| **4** | Mechanics engine port from Evelyn + simple-path UI; HTMX recompute | Slider in `/issuer/razorpay` recomputes waterfall in <50ms |
| **5** | Compliance engine + stamp-duty matrix + RBI floor check | 5 states × 3 seller-mix combinations all return sensible verdicts |
| **6** | Digest renderer + `/history` + Bark integration | A `make demo-day` command renders today's digest, fires one Bark, opens browser |
| **7** | Visual polish (styles.css), demo script rehearsal, edge-case fixes, README | Full 5-minute walkthrough runs without a glitch, twice in a row |

**Buffer rule:** Days 6 and 7 also absorb slippage from earlier days. If Day 3 (scoring) slips by half a day, it eats Day 7 polish, not Day 8 (which doesn't exist).

---

## 11. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Scrapers break on demo day (anti-bot, schema change) | Medium | All output cached as JSON in `data/scraper_cache/`. Demo runs offline by default. |
| Bark push doesn't arrive during the call (network, phone DND) | Low–medium | Have a screenshot of a prior push ready as fallback. Demo doesn't depend on the push being live. |
| HTMX slider compute is too slow → demo lag | Low | Mechanics engine is pure Python arithmetic on ~500 holders; tested to <50ms |
| Olesia challenges India compliance accuracy | Medium | Compliance engine cites every rule's source (RBI master direction number, state stamp act section). If she pushes harder than that, agree it needs counsel sign-off — that's the spec's stated position. |
| "Where does the buyer side come in?" | Certain to be asked | Honest answer: out of scope by design. Buyer-side data is confidential; building a buyer matcher on synthetic data wouldn't be credible. Phase-2 inside Qapita uses the internal Rolodex. |
| "How does this scale to non-India geos?" | Likely | Compliance engine is jurisdiction-pluggable; show the directory structure (`src/compliance/{IN,SG,UAE}/`); Singapore and UAE stubs exist with `NotImplementedError` placeholders. |
| She asks for Hiive comparison | Likely | Already framed in research: Qapita owns the cap table, Hiive doesn't. Tender Radar's per-issuer mechanics preview is only possible because the cap-table relationship already exists. Hiive can't replicate it. |
| Time runs out before all 7 days complete | Medium | Day-by-day acceptance criteria. If Day 5 (compliance) is at risk, ship a stub that just shows the stamp-duty matrix — the demo still works. |

---

## 12. What this spec deliberately leaves for "later"

Out-of-scope for the demo, **explicitly on the post-hire roadmap** if Phase 2 happens:

- Internal-data adapters replacing scrapers (Qapita cap-table API → mechanics; Qapita deal-pipeline API → issuer roster; Qapita buyer CRM → buyer matcher)
- SEA + UAE jurisdiction modules in compliance engine
- Full SEA waterfall types in mechanics UI (CCPS-with-cap, RCPS, dual-class) — engine ready, UI to expose
- Multi-user auth + RBAC
- Real-time signal stream (webhooks instead of cron)
- Backtest mode — replay 12 months of signals to validate the scoring rules predicted real tenders
- Production hardening: retry logic, monitoring, schema-drift alarms, scraper SLAs

The closing line of the interview references this roadmap as the 6-month internship plan. Don't volunteer it before she asks.

---

## 13. Definition of done

Tender Radar is ready to demo when, on the morning of the interview:

1. `make demo-day` runs end-to-end in <30 seconds and renders today's digest
2. Three specific issuers (Razorpay, Urban Company, Pine Labs) show score > 80 with full component breakdowns
3. The per-issuer page for Razorpay loads in <500ms with mechanics + compliance previews
4. The HTMX slider recomputes the waterfall live with no visible lag
5. A Bark push fires successfully to the user's phone
6. The history view shows ≥3 prior days of digests
7. Every numeric on screen has a provenance link
8. The footer line "*Tender Radar publishes no opinions on legality. Counsel sign-off required for any real transaction.*" appears on every page
9. Two full dry-runs of the 5-minute demo script have completed without a glitch
10. This spec, `OLESIA_RESEARCH.md`, and `ELIMINATION.md` all still pass a re-read with no contradictions

Once those 10 are green, freeze the build. Don't add features in the 24 hours before the call.
