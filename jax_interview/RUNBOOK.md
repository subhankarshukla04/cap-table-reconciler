# ESOP Atlas — Cold Start + Demo Runbook

**Purpose:** everything you need to run the demo from a cold laptop, plus the minute-by-minute call script.

---

## Cold start (1 minute)

```bash
cd ~/Desktop/qapita/jax_interview
source ../.venv/bin/activate         # reuses parent project's venv
python app.py
```

Open `http://127.0.0.1:5151/` in a browser. The console will print `corpus_size = 25` if rules loaded cleanly.

**If port 5151 is occupied** (another Flask process — happens with hot-reload):

```bash
pkill -9 -f "app.py"
sleep 1
python app.py
```

**If the venv path is wrong:** the project assumes `../.venv/bin/activate` exists (carried over from the Cap Table Reconciler). If not, create one:

```bash
cd ~/Desktop/qapita/jax_interview
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

**Test the cold start before the call:**

```bash
curl -s http://127.0.0.1:5151/healthz
# expect: {"corpus_size": 25, "status": "ok"}
```

---

## Demo URLs (memorize these — they map to the demo script)

| URL | What it shows |
|---|---|
| `/` | Empty form. Use to demonstrate live input. |
| `/verdict/praxis` | **SG-parent → IN-engineer exercise.** The headline cross-border case. |
| `/verdict/pelaut` | **IN-parent → SG-employee exercise.** Reverse cross-border, IRAS overseas-parent rule. |
| `/verdict/solstice` | **SG deemed-exercise on cessation.** The screen that makes Jax sit up. |
| `/sources` | The full rule corpus with citations + retrieval dates. |
| `/print/praxis` | Print-friendly view. Cmd+P → Save as PDF for the deliverable. |
| `/export/xlsx/praxis` | Direct .xlsx download of the Praxis verdict. |

---

## The 5-minute demo script

**Open:** Browser on `/` (empty form). Speak this opening line verbatim:

> "On every SEA sales call your team takes, a founder asks one specific question: when my engineer in Bangalore exercises her option on my Singapore parent, what does she owe and what do I file? Today the answer takes a 1–2 week tax-counsel ping. Carta wrote a 4000-word blog post about this. Loeb & Loeb wrote a comparative guide. Your own Singapore blog has the answer in static content. Nobody has a tool the BD can open during the call. This is that tool."

**0:00–0:30 — Live input.** Type into the form: SG parent, IN employee, exercise, resident, FMV 0.50, exercise price 0.10, options 4000. Click Answer.

**0:30–1:30 — Praxis verdict walks through itself.**
- Top: **PERQUISITE** treatment, FIRM confidence badge.
- Rate description: §17(2)(vi) + Rule 3(8) + ITA 2025 §17(5)(h).
- Withholding: yes, TDS by Indian subsidiary under §192.
- Filing: Form 12BA + Form 16, deadlines listed.
- Documents: SEBI Cat-I merchant banker valuation, cross-charge invoice (transfer-pricing trail).
- Secondary rule below: SG perspective = **NO_TAX** (employee never in SG, territorial nexus).
- Computed amount: **1,600.00** = (0.50 - 0.10) × 4000.

**1:30–2:30 — Click Demo · Pelaut in the top nav.**
- Reverse cross-border. IN parent, SG employee.
- Primary: **EMPLOYMENT_INCOME** in Singapore — explain the IRAS overseas-parent rule: SG taxes the gain regardless of where the parent sits, because the grant attaches to SG employment.
- Secondary: IN no-tax via DTAA Article 15 (Dependent Personal Services).
- Computed amount: **40,000.00** = (4 - 2) × 20000.

**2:30–3:30 — Click Demo · Solstice (the headline).**
- SG-SG, non-resident, **deemed exercise**.
- Primary rule fires the SG deemed-exercise rule.
- Walk through: Indian-national EP holder resigns. Employer files Form IR21 *one month before cessation*. IRAS imputes exercise the day before last-day. Employer withholds final-pay until Tax Clearance Directive.
- Caveat: Tracking Option (qualified ESOP) defers the charge to actual exercise — needs IRAS upfront approval.
- This is the slide that lands the moat thesis: "this is the kind of edge case that requires a tool, not a blog post."

**3:30–4:00 — Click Sources.**
- Show the full corpus: 25 rules, every one with statutory citation, source URL, and retrieved-on date.
- Make the point: "zero rules in this corpus are guesses. Anything we couldn't cite is flagged requires-counsel and the engine surfaces that flag in the verdict UI."

**4:00–4:30 — Click Export Excel on the Solstice verdict.**
- Verdict sheet: query inputs + treatment + filing requirements.
- Citations sheet: every source URL, every retrieval date, ready to hand to legal.

**4:30–5:00 — Close.** Land the scaling story:

> "What you're looking at is two jurisdictions × four events × four pair-combinations. Phase 2 adds Indonesia and Vietnam — the Jakarta office's next sales market. Phase 3 wires this into the cap-table product as a tab on every event. Phase 4 it becomes an external API: SEA law firms and Big 4 audit consume Qapita's compliance verdicts as a licensed SKU. The scoring engine is the moat. Carta cannot replicate it in SEA without five years of local work."

---

## If something goes wrong

| Scenario | Recovery |
|---|---|
| Browser shows "corpus_size: 0" | Stale Flask process. `pkill -9 -f app.py`, restart. |
| /verdict/praxis returns 404 | tests/fixtures/praxis.json is missing or malformed. Run `python -m pytest tests/test_fixtures.py` to diagnose. |
| HTMX swap returns the full page instead of fragment | Browser cache; reload with Cmd+Shift+R. |
| Verdict shows "requires-counsel" | The (parent, employee, event, status) tuple isn't in the corpus. Check via `/sources`. |
| Excel download is 207 bytes / fails | `io` import or path issue. Run `pytest tests/test_export.py` first. |
| Jax asks about Vietnam/Indonesia/Thailand | Honest answer: "Phase 2. The architecture supports it; the rule corpus needs the source research. Two days of work per jurisdiction with verified citations." |
| Jax asks "is this really IRAS / ITA exact?" | Click /sources. Every rule has a source URL with retrieved-on date. Be ready to load the IRAS or ITA page in an adjacent tab. |
| Jax asks about RSUs / SARs | "Phase 2. Same engine, separate rule schema for non-option instruments. The pydantic schema already supports the extension — see `src/models.py`." |

---

## Backup screenshot deck

If the live demo flakes, you have 6 pre-rendered HTML files to fall back on. Generate them with:

```bash
python app.py &
sleep 2
for view in / sources verdict/praxis verdict/pelaut verdict/solstice print/solstice; do
  fname=$(echo "$view" | tr '/' '_' | sed 's/^_//')
  curl -s "http://127.0.0.1:5151/$view" -o "screenshots/$fname.html"
done
```

Or simpler — use the browser's "Save Page As" on each demo URL into a `screenshots/` folder before the call, and attach them as a 6-page PDF to the follow-up email.

---

## Test sweep before the call

```bash
cd ~/Desktop/qapita/jax_interview
source ../.venv/bin/activate
python -m pytest tests/ -v
# expect: 33 passed
```

If any test fails, FIX it before the call. Untested code on screen-share is a credibility risk.

---

## What's in the demo deliverable (post-call email attachment)

1. The repo path: `~/Desktop/qapita/jax_interview/`
2. A 6-page PDF: index page + 3 verdict screens + sources page + print view
3. Three `.xlsx` exports — Praxis, Pelaut, Solstice
4. This RUNBOOK.md
5. PLAN_JAX.md (the build plan + scaling map)
