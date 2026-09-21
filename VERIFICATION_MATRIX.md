# Verification Matrix — Spec ↔ Audit Cross-Reference

> Written 2026-05-24, after the Builder agent wrote `SYSTEM_SPEC.md` (1,046 lines) and the Auditor agent wrote `AUDIT_PLAN.md` (1,266 lines) independently. Synthesizes the two: which spec claims are tested, which aren't, which audit tests have no spec basis, and the binding anti-cheating protocol the user wants enforced.
>
> If the spec and the audit drift apart, this file is where the drift gets named.

---

## 0. The four documents and how they relate

```
PRODUCTION_ROADMAP.md   ← strategic plan and phase definition
        ↓
CURRENT_STATE.md        ← factual inventory of the system today
        ↓
SYSTEM_SPEC.md          ← per-phase functional contract (Builder POV)
                            ↓ (independently, no access to tests/fixtures/src)
                          AUDIT_PLAN.md   ← adversarial test plan (Auditor POV)
                            ↓
                          VERIFICATION_MATRIX.md  ← this file
```

The Builder and Auditor never talked to each other. The Auditor was forbidden from reading the existing `/tests/`, `/fixtures/`, `/stress_test/`, `/precedent/`, `/src/`, `CURRENT_STATE.md`, or any of the builder's planning docs. Test scenarios in `AUDIT_PLAN.md` cite only external public sources (NVCA, SEBI EDIFAR, SEC EDGAR, ACRA, IFRS Foundation, AICPA, etc.). This is the structural guarantee that no test was designed to fit the engine and no fixture was designed to fit the test.

---

## 1. Coverage matrix — spec sections to audit test ranges

The audit plan has 5 phases × {Positive, Negative, Adversarial, End-to-end, Performance} = 25 test buckets, plus 8 cross-cutting invariant tests, plus 4 adoption metrics. Mapping:

| SYSTEM_SPEC § | What it promises | AUDIT_PLAN tests covering | Coverage |
|---|---|---|---|
| §1.1 Excel ingestion | Header inference, alias map, date coercion, parse warnings | P0-POS-001..006, P0-NEG-001..004, P0-ADV-001..005 | Strong |
| §1.2 PDF intake | pdfplumber text-only, image-only returns warning | P0-POS-007..008, P0-NEG-005, P0-ADV-006 | Adequate |
| §1.3 Data model contract | Pydantic constraints, all field bounds | P0-POS-009..012, P0-NEG-006..010 | Strong |
| §1.4 Checklist (8 rules) | Each rule's trigger, severity, fields_referenced | P0-POS-013..020 (one positive per rule), P0-NEG-011..014 | Strong |
| §1.5 Waterfall engine | Non-participating, participating-uncapped, participating-with-cap, senior-above-capped | P0-POS-021..028, P0-NEG-015..016, P0-ADV-007..010, P0-E2E-001 | Strong |
| §1.6 Live-formula Excel | Workbook with IF + SUMPRODUCT, Python-truth-equivalent | P0-POS-029..031, P0-PERF-001 | **Partial** — equivalence to Python truth marked UNV-002 |
| §1.7 Snapshot diff | Fuzzy class-name match across versions | P0-POS-032..033 | Adequate |
| §1.8 Markdown audit memo | Skeleton with [ANALYST] placeholders | P0-POS-034..035 | Adequate |
| §1.9 Persistence | SQLite token-keyed, no auth, survives restart | P0-POS-036..037, P0-ADV-011 | Adequate |
| §1.10 Flask routes (24 routes) | Per-route contract | P0-POS-001 through P0-E2E-002 cover most; explicit per-route smoke not enumerated | **Gap** — needs per-route smoke test |
| §1.11 Phase 0 refusals (17 items) | Things system promises NOT to do | P0-NEG-001..014, INV-001..008 | Strong |
| §2 Phase 1 Observe | Zero new code, workflow map, Day-30 pitch | P1-POS-001..004, P1-NEG-001..002, P1-ADV-001..003, P1-E2E-001..002 | Adequate |
| §3.1 Qapita data ingestion | Adapter contract, 5s cold-start | P2-POS-001..007, P2-NEG-001..004, P2-PERF-001 | Strong |
| §3.2 Multi-tenancy, auth, audit log | Engagement lifecycle, role-based access, append-only audit | P2-POS-008..020, P2-NEG-005..012, P2-ADV-001..005, P2-E2E-001 | Strong |
| §3.3 Holder-level rollup | Heuristics, 0.80 confidence threshold, manual fallback | P2-POS-021..025, P2-NEG-013..014, P2-ADV-006..008 | Strong |
| §3.4 Big-4 PDF memo | WeasyPrint, cited cells, named reviewer | P2-POS-026..030, P2-NEG-015..017 | Adequate |
| §3.5 Phase 2 acceptance | 2 real engagements end-to-end | P2-E2E-002, §4.1 adoption metric | Adequate |
| §4.1 Rule-pack versioning | semver, effective_from, engagement binding | P3-POS-001..008, P3-NEG-001..004 | Strong |
| §4.2 Pari-passu seniority | seniority_tier tuple, proportional allocation | P3-POS-009..012, P3-NEG-005..006, P3-ADV-001..003 | Strong (gaps surfaced: GAP-20/21/22) |
| §4.3 OCR for image PDFs | pdfplumber → OCR fallback, 0.85 confidence | P3-POS-013..016, P3-NEG-007..009, P3-ADV-004 | Adequate (gap: GAP-23/24) |
| §4.4 Structured snapshot diff | Field-level, provenance, 500ms SLO | P3-POS-017..019, P3-PERF-001 | Adequate |
| §4.5 Wider-team onboarding | Docs, jurisdiction quick-ref | P3-POS-020..021 | Adequate |
| §4.6 Phase 3 acceptance | 50%+ adoption, 1+ Big 4 sign-off | §4.2, §4.3 adoption metrics | Adequate |
| §5.1 OPM Backsolve | brentq solver, sensitivity tables | P4-POS-001..006, P4-NEG-001..003, P4-ADV-001..003 | Adequate (gap: GAP-30/31, UNV-007) |
| §5.2 BSM / IFRS 2 ESOP | Per-grant FV, amortization | P4-POS-007..011, P4-NEG-004..006 | Adequate |
| §5.3 DCF input sidecar | Named ranges, no DCF model | P4-POS-012..014 | Adequate |
| §5.4 US / ASC 820 | NVCA aliases, Delaware rules, AICPA citations | P4-POS-015..018, P4-ADV-004..006 | Adequate |
| §5.5 Phase 4 acceptance | 3 siblings live, external reference | §4.4 outcome metrics | Adequate |
| §6 Cross-cutting invariants (8) | No LLM, citations, refusal, immutability, determinism | INV-001..008 | Strong (one ambiguity: UNV-010 / GAP-35) |
| §7 Out-of-scope refusals (16) | Promises NEVER to do X | Sampled in P0/P4 negative tests | Adequate |

**Headline coverage:** of ~28 distinct spec section claims, all are touched by at least one audit test. **One real gap** — §1.10 (Flask route exhaustiveness): the spec enumerates 24 routes with contracts; the audit covers most via end-to-end but doesn't smoke-test every route individually. Adding 24 per-route smoke tests to the audit closes it.

---

## 2. Spec claims with WEAK or NO audit coverage

These are promises the builder is making that the auditor cannot independently verify with what they have today. From `AUDIT_PLAN.md §5`:

| ID | Spec claim | Why not verifiable | Action required |
|---|---|---|---|
| UNV-001 | "23,300+ fuzz cap tables, zero invariant violations" | Auditor can't read `/stress_test/` or `/tests/` | Builder publishes a separate fuzz-run report artifact (seed, params, pass-count) so the auditor can spot-check |
| UNV-002 | Live-formula Excel "verified against Python truth" | Same — would require reading test suite | Spec adds the equivalence contract explicitly: "for any CapTable, exporting then opening produces breakpoint values equal to `compute_waterfall()` output within tolerance ε" |
| UNV-003 | "Cold-start Qapita pull < 5s for 50-class cap table" | Reference environment undefined | Spec adds: CPU class, RAM floor, network latency budget to Qapita data source |
| UNV-004 | PDF citation hyperlink format `snapshot://<id>/<sheet>/<cell>` | Custom URI scheme — no resolver behavior described | Spec describes resolver (in-tool web UI registers handler OR HTTPS deep-link to engagement viewer) |
| UNV-005 | OCR confidence ∈ [0,1] | Different OCR backends emit different scales | Spec defines normalization across backends |
| UNV-006 | "Tool runs on Qapita infrastructure not laptop" | "Qapita infrastructure" undefined externally | Spec lists artifacts that prove it: deployment URL, monitoring dashboard, infra-as-code repo |
| UNV-007 | OPM Backsolve math correctness | No reference computation pinned in spec | Spec adds appendix with a worked example: all inputs + expected outputs (cite AICPA Cheap Stock Guide Ch.6 worked example) |
| UNV-008 | Read-only auditor magic-link token expires | Error code for expired-token read not named | Spec adds `token-expired` error code (also GAP-33) |
| UNV-009 | "Tool referenced in Qapita external artifact" | Relies on Qapita marketing timing | Spec adds verification source: Qapita marketing publication log entry |
| UNV-010 | Determinism: "same input → same output bit-for-bit" | Snapshots have `created_at`; exports may embed timestamps | **Material ambiguity.** Spec must carve out per-output-type: data outputs deterministic in content; memos/exports deterministic-modulo-timestamp |
| UNV-011 | "openpyxl.InvalidFileException → HTTP 400" | Couples 3rd-party exception type to HTTP behavior | Spec abstracts: "if openpyxl rejects file, route returns HTTP 400 with error banner" |

**Action: Builder updates SYSTEM_SPEC.md to address all 11 UNV items before Phase 1 starts.** Without that, the audit cannot sign Phase 1 cleanly because the spec has unverifiable promises.

---

## 3. Audit tests with no spec basis — these are SPEC GAPS

From `AUDIT_PLAN.md §6`, the Auditor surfaced 40 gaps where the spec is silent on a real-world scenario. Ranked by risk to production:

### 3.1 Blockers (must fix before Phase 2 starts)

| GAP | What | Risk |
|---|---|---|
| GAP-01 | Concurrency on engagement edits — two analysts simultaneously | Lost updates, audit-log race |
| GAP-03 | GDPR/PDPA right of erasure vs immutable audit log | Legal non-compliance (Singapore PDPA, India DPDPA Aug 2023, EU GDPR for any EU-domiciled cap-table participants) |
| GAP-05 | Audit-log integrity at DB-admin level — no signed hashes | Internal actor with DB access can inject rogue rows undetected; defeats Big 4 sign-off |
| GAP-07 | Rule-pack vs engine-code version skew | Re-runs of historical engagements not actually deterministic |
| GAP-35 | Determinism with timestamps (same as UNV-010) | Cross-cutting invariant ambiguous |
| GAP-36 | XSS / injection in cell content (holder names rendered in UI/memo) | Security vulnerability; named-PII PDF goes to Big 4 |
| GAP-40 | Bulk-export rate limiting | Data exfiltration by compromised analyst account |

### 3.2 Majors (must fix before Phase 3 ends)

| GAP | What |
|---|---|
| GAP-02 | Data retention/deletion policy beyond `archived` |
| GAP-04 | Backup/DR — RPO/RTO undefined |
| GAP-06 | Schema evolution on rule pack JSON |
| GAP-08 | Import/export portability (handoff to another firm's auditor) |
| GAP-13 | SAFE template variant (pre vs post-money) — Y Combinator standard not disambiguated |
| GAP-14 | Protective provisions / ROFR / drag-along — no data model field at all |
| GAP-19 | YC-style MFN-only SAFE never flagged by current checklist |
| GAP-20 | N-way pari-passu cardinality (3-way at same rank not explicit) |
| GAP-21 | Pari-passu with mixed LP types — undefined semantics |
| GAP-22 | Pari-passu interaction with full-ratchet AD — undefined |
| GAP-23 | OCR per-page vs total threshold |
| GAP-26 | Per-rule jurisdiction predicate |
| GAP-28 | Concurrent PDF generation during edits — PDF may cite stale snapshot |
| GAP-29 | Subsequent-events memo path after engagement signed |
| GAP-30 | Backsolve treatment of outstanding SAFEs |
| GAP-31 | Backsolve solver behavior on participating-capped anchor class |
| GAP-32 | DCF sidecar versioning (stale link detection) |
| GAP-34 | Reference environment for every performance contract |
| GAP-37 | Pari-passu data-model migration: lossy cases on round-trip |
| GAP-38 | Audit log query SLO (7-year-old engagement, may time out) |
| GAP-39 | Read-only auditor token: pre-expiry revocation |

### 3.3 Minors (track, address opportunistically)

GAP-09 (i18n names), GAP-10 (accessibility), GAP-11 (locale currency parsing), GAP-12 (multilingual headers), GAP-15 (negative-correction rows), GAP-16 (encrypted PDF warning code), GAP-17 (unparseable-date silence), GAP-18 (multi-currency mismatch warning), GAP-24 (OCR backend swap breaks determinism — also touched by GAP-35), GAP-25 (severity enum evolution), GAP-27 (structured voting_multiplier field), GAP-33 (`token-expired` code — also UNV-008).

**Action: Builder triages all 40 gaps. Blockers (7) must be addressed in SPEC + implementation before Phase 2 begins. Majors (21) must be closed by Phase 3 exit. Minors (12) tracked in a backlog with explicit deferral notes.**

---

## 4. The anti-cheating protocol — binding

The user has been emphatic: "I will not accept any form of cheating." This section codifies what cheating means here and what enforcement looks like. This is not a list — it's a contract between the builder (you, post-Aug 2026) and the auditor (whoever Evelyn assigns, possibly yourself wearing a different hat, possibly a Qapita engineer outside Valuations, possibly an external Big 4 reviewer for sign-off).

### 4.1 Definition of cheating

Cheating, in this project, means any of the following:

1. **Fixture-to-source mirroring.** Building a new fixture (test input) that mimics an external source the auditor has already cited in `AUDIT_PLAN.md §1`. The fixture passes because it's the curated answer to the audit's exact question, not because the engine generalized.
2. **Spec retroactive weakening.** Editing `SYSTEM_SPEC.md` between audit publication and audit run to remove or soften a refusal claim the audit would have caught. The "version of the spec at the time of audit" is the version the audit runs against.
3. **Hard-coded answer lookup.** Implementing a code path that returns a pre-computed answer for a specific input (e.g., a recognized hash of the auditor's test CapTable). Detected by perturbing one share count by ±1 and confirming structural output behavior continues to make sense.
4. **Special "audit mode" code path.** Behavior differs between semantically equivalent inputs (e.g., the same CapTable serialized as Excel vs JSON produces different findings). Equivalent inputs must produce equivalent outputs.
5. **LLM-conditional invocation.** LLM calls fire only for inputs matching the auditor's source list. The cross-cutting invariant (§6.1: no LLM in calc pipeline, ever) is violated regardless.
6. **IP-conditional response.** The server returns different responses based on the requester's IP address. Detected by running identical requests from two distinct IPs.
7. **Cache pre-warming for auditor inputs.** Audit-test inputs return measurably faster than equivalent novel inputs of the same shape. Detected via timing comparison.
8. **Test-suite mirroring.** The builder's `/tests/` gains a test that mirrors the auditor's test ID's intent AFTER the audit plan is published. This is allowed (improving test coverage is good) — but it must be flagged as "added in response to AUDIT-Pn-XXX-NNN" in the commit message. Hiding the origin is cheating.
9. **Rule-pack rush-add.** A new G-prefix rule appears in the engine ad-hoc in response to an adversarial test, without the Phase 3 documented process (semver bump, citation, fixture, regression). The rule itself may be correct, but the bypass of process is cheating.
10. **Fixture rename to look unrelated.** Existing fixture renamed to disguise that the audit triggered its creation. Detected by git-log on fixture filenames.

### 4.2 Detection procedures (run by the auditor at the start of every phase audit)

Before running any test, the auditor runs these scans:

| # | Scan | Command (illustrative) | Triggers |
|---|---|---|---|
| 1 | New fixtures since audit publication | `git log --since="<audit-publication-date>" -- fixtures/` | Any new fixture file → manual review against §1 source catalog |
| 2 | Spec retroactive edits | `git log --since="<audit-publication-date>" -- SYSTEM_SPEC.md` | Any commit → diff against audit's snapshot; flag weakened refusals |
| 3 | New tests citing audit IDs | `git grep "AUDIT-P[0-9]-" tests/` | Any match → check commit messages for transparency |
| 4 | Fixture renames | `git log --diff-filter=R -- fixtures/` | Any rename → manual review |
| 5 | New G-codes since audit publication | `git log --since=... -- src/checklist.py` plus rule-pack history | Any new rule → must trace to a Phase 3 process commit |
| 6 | Outbound network activity during test runs | network capture (e.g., `mitmproxy` recording) | Any outbound to LLM endpoints (api.openai.com, api.anthropic.com, openrouter.ai, etc.) — instant fail of invariant 1 |
| 7 | Cache pre-warming | Run 10 audit inputs, then 10 same-shape novel inputs, compare timings | Audit inputs >2× faster → flag for code review |
| 8 | IP-conditional response | Run identical request from two distinct IPs (VPN + direct) | Any divergence → instant fail |
| 9 | Audit-mode divergence | Serialize same CapTable as Excel + JSON, compare outputs | Any divergence beyond known serialization metadata → flag |
| 10 | Hard-coded answer | For each positive test, run a `+1 share` variant | Output must change predictably; if structurally identical, flag |

The audit deliverable PDF (per `AUDIT_PLAN.md §7`) includes a "Cheating Watch Findings" section listing the output of each scan with timestamps.

### 4.3 What happens if cheating is detected

The user wants zero tolerance. Operationally:

- **Hard cheats (1, 4, 5, 6, 9 — i.e., LLM invocation, audit-mode divergence, IP gating, hard-coded answers, fixture mirroring):** the phase audit is immediately failed. The phase is not signed off until the cheat is removed AND the affected scope is re-audited with fresh tests from the auditor (auditor publishes a delta test plan).
- **Soft cheats (2, 7, 8, 10 — spec retro-weakening, fixture rename, rush-add rule, cache warming):** the cheat is documented in the audit report as a `CHEAT-OBSERVATION`, the phase may still pass on its own merits, but the cheat appears in the report Evelyn / Vamsee read at sign-off, and recurrence triggers the hard-cheat protocol.
- **All cheats are reported regardless of severity.** Hiding them is itself a cheat (recursion intended).

### 4.4 What is explicitly NOT cheating

To avoid paralysis, the following are explicitly allowed:

- Improving the existing test suite, in any way, at any time, with transparent commit messages.
- Adding new rules to the rule pack via the documented Phase 3 process (semver bump, citation to published precedent, regression fixture, audit log entry). The rule may originate from an adversarial audit finding; the origin must be cited in the commit.
- Refactoring code that does not change behavior. (Detected by determinism scan — if behavior is unchanged, the refactor is fine.)
- Adding fixtures from PUBLIC sources that the auditor did not cite. This grows defensive coverage without mirroring the audit.
- Asking the auditor to clarify an ambiguous spec section. The auditor's response is logged as part of the audit; the spec may be amended to incorporate the clarification BEFORE the audit runs.
- Disagreeing with an audit finding and writing a documented rebuttal. The audit deliverable preserves both the finding and the rebuttal. Evelyn arbitrates.

---

## 5. Per-phase sign-off procedure

The audit is not a one-shot. It's a gated workflow. Each phase has a defined sign-off sequence.

### 5.1 Roles in the workflow

- **Builder** — you, post-Aug 2026. Implements per the spec.
- **Spec custodian** — also you initially; transitions to Vamsee's engineering team once internalized. Authority to amend `SYSTEM_SPEC.md`. All amendments versioned, dated, signed.
- **Auditor** — for Phase 1 and Phase 2 pilot: Evelyn directly OR Arthur Ng under her instruction. For Phase 3 onward: a Qapita engineer outside Valuations (independence) plus at least one Big 4 auditor sample (real audit firm reviewing one engagement). For Phase 4: external review by a named Big 4 partner is the gold standard.
- **Approver** — Evelyn (for Valuations practice scope) and Vamsee (for engineering / infra). Both signatures required to advance phases.

### 5.2 Sign-off sequence per phase

1. **Spec freeze.** Builder declares spec frozen for this phase. Spec custodian timestamps and signs a Git tag (e.g., `spec-phase-2-v1.0`). No further edits to spec sections in scope without re-freeze.
2. **Audit run.** Auditor executes `AUDIT_PLAN.md` Phase N tests against the tagged spec. Generates the deliverable PDF + companion XLSX per `AUDIT_PLAN.md §7`.
3. **Cheating-watch scans.** All 10 scans from §4.2 above run before the test pass-rate is reported. Any hard-cheat triggers protocol §4.3.
4. **Findings review.** Builder reviews findings. For each: accept and fix, dispute with written rebuttal, or request spec clarification. No phase advances with open blockers.
5. **Approval signature.** Evelyn and Vamsee sign the audit PDF. Phase declared complete; next phase work may begin.
6. **Audit retention.** PDF + XLSX + raw test artifacts archived to Qapita's document store with retention matching the engagement-data retention policy (typically 7 years for Big-4-relevant artifacts).

### 5.3 Re-audit triggers

A signed-off phase audit can be invalidated, requiring re-audit, by any of:

- A new blocker finding from a subsequent phase audit that traces to a previous phase's scope.
- A production incident affecting a phase-scope feature (e.g., a Phase 2 audit-log integrity bug → Phase 2 re-audit).
- An external regulator (Big 4 partner reviewing a real engagement, SEBI/RBI/IRAS, etc.) raising a concern about a phase-scope feature.
- A material change to `SYSTEM_SPEC.md` post-sign-off (any change ≥ minor severity per `AUDIT_PLAN.md §7.3`).
- Discovery of a cheat (any of §4.1) in retrospective review.

### 5.4 The audit-cadence calendar

| Phase | Audit cadence | Auditor |
|---|---|---|
| Phase 1 (Observe, Days 1–30) | Single audit at Day 30 (pitch document review) | Evelyn |
| Phase 2 (Pilot, Months 2–3) | Mid-phase smoke audit at Month 2.5, full audit at Month 3 | Arthur Ng + 1 Big-4 sample |
| Phase 3 (Hardening, Months 4–6) | Monthly mini-audits, full audit at Month 6 | Qapita engineer outside Valuations + 1 Big-4 partner sample |
| Phase 4 (Platform, Months 7–12) | Quarterly audits | External Big-4 named partner |

Each audit produces a fresh deliverable PDF and the matrix's coverage table is refreshed.

---

## 6. The end-to-end functional vision — what the system DOES at each phase exit

For grounding, here is what an outside observer (an analyst on Evelyn's team, a Big 4 reviewer, a Qapita engineer) would see and be able to do at each phase boundary. This is the functional-vision equivalent of the spec.

### 6.1 End of Phase 0 (today)

An analyst can:
- Open `http://localhost:5050` on their laptop, see five curated fixtures + an upload box.
- Click any fixture, walk parse-warnings → findings → waterfall → export.
- Upload their own `.xlsx`, get the same flow IF the file matches one of the parser's supported header layouts. If not, see a degraded parse-report.
- Adjudicate eight specific finding types inline.
- Edit a share count in the live-formula Excel; breakpoints redraw in Excel.
- Export JSON, static `.xlsx`, live `.xlsx`, Markdown memo skeleton.
- Diff two cap-table snapshots (fuzzy class-name match).

Cannot: log in, share, collaborate, persist beyond a local SQLite token, run anywhere except their laptop, get a PDF memo, run a Backsolve.

### 6.2 End of Phase 1 (Day 30 at Qapita)

Same as Phase 0 functionally — zero new code shipped. Plus: a written workflow map of three real engagements and a Day-30 pitch document delivered to Evelyn, with an explicit Path A vs Path B decision.

### 6.3 End of Phase 2 (Month 3 at Qapita)

An analyst can:
- Log into the tool via Qapita SSO.
- Open an engagement scoped to a client. See only the engagements they have access to.
- Pull cap-table data directly from Qapita's platform (for on-platform clients) OR upload Excel (for off-platform clients).
- Excel ingestion handles holder-level Indian-CFO formats automatically; falls back to a manual mapping UI when heuristics fall below 0.80 confidence.
- Every state change creates an immutable snapshot.
- Resolve findings; each resolution is logged with citation, actor, timestamp.
- Generate a PDF audit memo (WeasyPrint) with cover sheet, version stamp, named reviewer, signature block, citations to source cells.
- See the engagement audit log: who did what when.
- Have a read-only auditor magic-link role that lets an external Big 4 reviewer browse the engagement without editing.

Cannot: run Backsolve, run BSM, choose between rule packs (one pack is current), recover a deleted engagement (because nothing is deleted), use it without Qapita SSO.

### 6.4 End of Phase 3 (Month 6 at Qapita)

Adds:
- Rule packs: engagements freeze a rule pack at open. Auditor can re-run an engagement against the frozen pack two years later and get identical output.
- ~30 rules covering anti-dilution variants, participation/cap mechanics, SAFE/convertible templates, option pool mechanics, voting/governance, round mechanics, side-letter integrity, jurisdiction-specifics (India FEMA, Singapore VIMA, Delaware §251, AICPA Cheap Stock).
- Pari-passu seniority supported at the data model and waterfall levels.
- Image-PDF side letters OCR'd via Google Document AI (or Tesseract fallback); confidence < 0.85 surfaces a banner.
- Structured field-level snapshot diff feeds the memo's "subsequent events" section automatically.
- Tool runs on Qapita-managed infrastructure with monitoring, backups, and SOC-2-relevant logging.
- 50%+ of new International Valuations engagements use it for intake.
- At least one Big 4 auditor has signed off on a tool-produced PDF memo without substantive pushback.

### 6.5 End of Phase 4 (Month 12 at Qapita)

Adds three sibling consumers, each reading the same canonical CapTable:
- **OPM Backsolve sibling** — given the clean cap table + market inputs (vol, time, rf, DLOM), runs `scipy.optimize.brentq` to find implied total equity value, outputs per-class fair value + common FMV + sensitivity tables. No fair-value-from-scratch OPM, no PWERM.
- **BSM/IFRS 2 sibling** — per-ESOP-grant fair value, vesting amortization, P&L impact per period. Integrates with Qapita's ESOP product.
- **DCF sidecar** — Excel workbook with named ranges (share counts, LPs, conversion ratios); the analyst's DCF model in Excel links to it. Tool does not produce a DCF.

Plus: NVCA alias coverage, Delaware-specific rules, AICPA Cheap Stock Guide citations in memos. ≥3 US engagements processed under ASC 820 / 409A. The cap-table engine has spun out as an internal Qapita calculator service consumed by ≥2 other product teams.

### 6.6 The single sentence at Phase 4 done

A Qapita International Valuations analyst opens any engagement — whether the cap table comes from an Indian CFO's holder-level Excel, Qapita's own platform, or a Delaware NVCA-templated charter — and walks intake → findings → waterfall → OPM Backsolve → BSM/ESOP → audit memo PDF, with every output deterministic against a frozen rule pack, every finding cited to its source field, every action logged immutably, and the resulting PDF survives a Big 4 partner's review.

If that sentence isn't true at Phase 4 sign-off, Phase 4 isn't done.

---

## 7. Open items routed back to Builder

Action list, ordered by urgency:

1. **Update SYSTEM_SPEC.md** to address all 11 UNV-x items (§2 above) — without this, the Phase 1 audit cannot sign cleanly because the spec has unverifiable promises. Target: before any work in Phase 2 begins.
2. **Triage all 40 GAP-x items** (§3 above) — 7 blockers must be in spec + implementation before Phase 2 starts; 21 majors before Phase 3 exit; 12 minors tracked in backlog with deferral notes.
3. **Publish the fuzz-run report** as a standalone artifact (per UNV-001). Format: seed, parameters, sample CapTables tested, invariants checked, pass count.
4. **Add per-route smoke tests** to AUDIT_PLAN (§1.10 spec lists 24 routes; audit covers most via E2E but not exhaustively per-route).
5. **Define reference environment** for every performance contract (UNV-003, GAP-34).
6. **Resolve the determinism-with-timestamps ambiguity** (UNV-010, GAP-35) — material, blocks invariant testing.
7. **Add reference computation appendix** to spec §5.1 (OPM Backsolve) with worked example for auditor sanity-check.

---

## 8. Open items routed back to Auditor

If the auditor (you in a different hat, or whoever takes the role) is going to actually run this audit:

1. **Acquire the WebFetch-failed sources** — the audit notes 5 sources couldn't be cleanly accessed (OJK Indonesia regulation in English, Wilson Sonsini-authored primary article, Reliance Jio DRHP body text, Cooley deal-data PDF, one other). Either pay for access, find equivalent free sources, or document the gap in the deliverable.
2. **Pre-stage external test inputs** — for each AUDIT-Pn-* test, download the source document NOW and store hashes. Otherwise the source can be edited by the publisher between plan-write and audit-run.
3. **Stand up the network-capture tooling** for the no-LLM invariant scan (mitmproxy or equivalent). This is non-trivial — do it before the audit, not during.
4. **Identify the Big 4 auditor sample** for Phase 3 — one real auditor willing to review one engagement memo as part of an existing Qapita engagement. Don't fabricate; use a real workflow.
5. **Set up the deliverable template** (PDF + XLSX) per AUDIT_PLAN.md §7 — generate a Phase 0 dry run today, with the system as-is, to validate the deliverable format works.

---

## 9. The bottom-line summary

- The system today is a strong Phase 0 demo with a substantial engine room. The roadmap takes it to genuine production through four phases over ~12 months.
- The Builder spec covers each phase functionally; the Auditor plan covers each phase adversarially. They were written independently and they cover each other's spec sections within reasonable tolerance.
- The audit surfaced **11 unverifiable claims, 40 spec gaps, and 10 cheating watch-list items**. The 7 blockers and 11 UNVs are the action list before Phase 2 begins.
- The anti-cheating protocol (§4) is binding. Detection runs at every audit. Hard cheats fail the phase; soft cheats are reported even if the phase otherwise passes.
- The sign-off sequence (§5) ensures Evelyn + Vamsee both sign each phase, on a tagged spec, with a deliverable PDF that includes the cheating-watch scan output.
- At Phase 4 exit, the test is the one-sentence vision (§6.6). If it doesn't hold, the phase isn't done.

The reason this works is not that the documents are bulletproof — they're not, and the audit found that. It works because the documents were generated by parties with no communication, and they cover each other's blind spots better than a single author could.
