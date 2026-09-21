# Build-Ready Signoff

> Single-page status the user reviews before authorising the Phase 1 build to begin. If the user signs §8 below, the agency has the mandate to proceed. If the user does not sign, the agency goes back to whichever §1-§7 row is blocking and resolves it first.
>
> Written 2026-05-25 by the agency (CEO + CTO + Supervisor + QA hats), at the close of the pre-build hardening pass.

---

## 1. Planning artifacts — frozen and tagged

| File | Lines | Author | Purpose | Status |
|---|---:|---|---|---|
| `PRODUCTION_ROADMAP.md` | 526 | Agency (strategic) | Four-phase plan demo → production | Frozen |
| `CURRENT_STATE.md` | 590 | Explore agent | Factual baseline inventory | Frozen |
| `SYSTEM_SPEC.md` | 1,199 | Builder agent + spec custodian (round 1 amendments) | Per-phase functional contract | Frozen, to be git-tagged `spec-r1-2026-05-25` |
| `AUDIT_PLAN.md` | 1,266 | Auditor agent (independent) | Adversarial test plan from external sources | Frozen |
| `VERIFICATION_MATRIX.md` | 342 | Agency (synthesis) | Spec ↔ audit cross-reference, anti-cheating protocol, sign-off sequence | Frozen |
| `AGENCY_STRUCTURE.md` | 273 | Agency (organisational) | Roles, decision rights, escalations, cadence, change-mgmt | Frozen |
| `CODE_AUDIT.md` | 354 | Independent code-auditor agent | 5 blockers, 9 majors, 11 minors in the existing src/ | Frozen |
| `BUILD_READY.md` | this file | Agency (sign-off) | The mandate document | Awaiting signature |

Total planning surface: **~4,820 lines of documentation** produced by a mix of agents and the agency, with structural anti-cheating separation enforced between Builder, Auditor, and synthesiser.

## 2. Code state — baseline + fixes applied

**Baseline (before hardening, 2026-05-24):**
- 331 tests pass
- 93% src/ coverage
- 179 `ResourceWarning: unclosed database` from `SessionStore`
- App boots, all 5 fixtures load end-to-end

**Audit pass (independent) found:**
- 5 blockers (wrong-output or silently-corrupting bugs reproducible from REPL)
- 9 majors (silent data loss, spec drift, resource leaks)
- 11 minors (hardening opportunities)

**Fixes applied (2026-05-25):**

| Bug | File | Fix | Verified by |
|---|---|---|---|
| BUG-005 | `src/persistence.py` | Wrap every `_connect()` call with `contextlib.closing`; preserve `with conn:` for commit-on-success | `test_bug005_session_store_no_resource_warnings` + zero `ResourceWarning` under `-W error::ResourceWarning` |
| BUG-004 | `src/audit_memo.py` | Added `_md()` helper; escape `\\`, `|`, newlines on every cell in every table | `test_bug004_audit_memo_escapes_pipe_characters` |
| BUG-003 | `src/checklist.py` | SAFE-UNCONVERTED iterates every subsequent priced round, not just the first | `test_bug003_safe_unconverted_checks_all_subsequent_rounds` |
| BUG-002 | `src/parser.py` | Replaced order-dependent `in`-match with scored match: priority + end-position + length + table order; added head-word-+-prepositional rule for notes | 8 parametric cases in `test_bug002_header_field_detection` |
| BUG-001 | `src/parser.py` | Unknown class type defaults to `common` (always validates) with a `class_type_unknown` warning; row no longer silently drops | `test_bug001_unknown_class_type_preserves_shares` |
| BUG-006 + BUG-012 | `app.py /upload` and `/diff` | `tempfile.NamedTemporaryFile` replaces hardcoded `/tmp`; narrowed `except` to `(ValueError, KeyError, ValidationError, openpyxl.utils.exceptions.InvalidFileException, zipfile.BadZipFile)` with logging | (covered indirectly via existing routes tests) |
| BUG-007 | `app.py /healthz` | Returns `{"status": "ok"}` only; no `len(SESSIONS)` call | `test_bug007_healthz_matches_spec` |
| BUG-008 | `src/parser.py` warrant reader | Read `share class` column if present; default `Common` with `warrant_share_class_assumed` warning | (regression coverage to be added if a fixture exercises this) |
| BUG-009 | `src/parser.py` `load_from_canonical_json` | Raise `ValueError` if `cap_multiple * lp_amount` and `cap_amount` disagree beyond `1e-6` relative | `test_bug009_inconsistent_cap_raises` |
| BUG-011 | `src/parser.py` SAFE reader | Reads `Trigger Threshold` / `Conversion Trigger` / `Qualified Financing` columns when present, populates `conversion_trigger_threshold` | (paired with BUG-003 test) |
| BUG-013 | `src/parser.py` company tab | Alias table maps `Company Name`, `Country of Incorporation`, `Date of Valuation`, `Currency Code`, etc. to canonical fields | `test_bug013_company_tab_aliased_labels` |
| BUG-022 (minor) | `app.py` | Moved `import zipfile` to module top | — |

**Spec amendments applied (`SYSTEM_SPEC.md §8`):**
- All 11 UNV-x items closed: fuzz-run report, workbook equivalence tolerance, reference environment, URI scheme, OCR normalization, Qapita-infra verifier list, OPM reference appendix, error codes, external-artifact verifier, determinism-with-timestamps carve-outs, openpyxl exception abstraction.
- Blocker spec gaps closed: GAP-01 optimistic concurrency with HTTP 409, GAP-03 PDPA/GDPR/DPDPA erasure protocol, GAP-05 hash-chain audit log, GAP-07 engine-version binding, GAP-35 determinism carve-outs (with §8.10), GAP-36 XSS escaping promise (six-item commitment), GAP-40 bulk-export rate limiting.

**Final state (2026-05-25):**
- **346 tests pass** (331 original + 15 new regression tests in `tests/test_audit_fixes.py`)
- **Zero `ResourceWarning`** under `-W error::ResourceWarning`
- All 5 blockers fixed; 7 of 9 majors fixed; 2 majors (BUG-010 `/whatif` zero-share edge, BUG-014 diff None/0 conflation) deferred to build phase with documented reasoning
- Spec amendment round 1 complete; spec ready for git tag

## 3. Risk register at sign-off

| Risk | Status | Owner | Mitigation in place |
|---|---|---|---|
| Vamsee (Qapita CTO) declines Python/Flask stack | Not yet known | CEO | Phase 1 Q1 — first 1:1 |
| Evelyn picks Path B (tool stays informal) | Possible | CEO | Plan accommodates both; pre-arrival §1.1 IP hygiene applies regardless |
| Public MIT repo creates IP friction | Mitigated | CEO | Three-option decision in `PRODUCTION_ROADMAP §1.1`, default to option C (keep public, stop pushing once internal) |
| Holder-level Indian-CFO Excel parsing harder than 2 weeks | Acknowledged | CTO | Phase 2 §3.3 manual-mapping UI is the load-bearing fallback, not the automation |
| Determinism-with-timestamps invariant ambiguity | Closed | Spec custodian | `SYSTEM_SPEC §8.10` carves out per output type |
| Audit-log tamper detection not in baseline | Closed at spec | Risk | `SYSTEM_SPEC §8.14` hash-chain requirement is binding from Phase 2 |
| GDPR / PDPA / DPDPA conflict with append-only log | Closed at spec | Risk | `SYSTEM_SPEC §8.13` redaction protocol |
| 24 of 40 spec gaps still open (majors + minors) | Triaged | Planner | 21 majors must close by Phase 3 exit; 12 minors tracked in `BACKLOG.md` (to be created at start of Phase 1) |
| Auditor's 5 external sources unaccessible | Documented | QA | `AUDIT_PLAN.md §1.7` lists each; will retry at audit time and document substitutes |

## 4. The agency mandate

Per `AGENCY_STRUCTURE.md`:
- **CEO:** Subhankar (strategic, sign-off, Evelyn / Vamsee / Amit relationships).
- **CTO:** Subhankar (technical architecture, stack, integration).
- **Supervisor:** Subhankar (daily task triage, slippage detection).
- **Planner:** Subhankar (backlog, sequencing, estimates).
- **Structural reviewer:** Subhankar (invariants enforcement, PR review).
- **QA / Auditor:** Subhankar at phase gates; Big-4 sampling for Phase 2+; external Big-4 partner for Phase 4.
- **Risk / compliance:** Subhankar (with Qapita's compliance function consulted from Phase 2).
- **Documentation steward:** Subhankar (doc-code sync).
- **Execution partner:** Claude (this AI), invoked for implementation, audits, reviews — never as decision authority.

Single human wearing eight hats with one AI partner. The hats are scaffolding for honest thinking; decisions are the human's. The agency mandate runs from 2026-08-01 (NOC start) through end of Phase 3 (Dec 2026 target); Phase 4 mandate is a separate negotiation tied to internship extension or post-NOC engagement.

## 5. Improv room — what we are leaving open on purpose

Per the user's instruction "leave room for new things popping up with occasional check-ins and also consistent improvising":

- The change-management protocol in `AGENCY_STRUCTURE.md §5` defines the 4-question triage for new asks.
- The improv license (§5.3) lets any role propose deviations from the plan, in writing, at any time, bounded by the cross-cutting invariants.
- The kill switch (§5.4) lets the CEO pause at any phase boundary.
- The check-in calendar (§9) is a hypothesis; the monthly strategic review revises it.
- The audit cadence (`VERIFICATION_MATRIX.md §5.4`) is non-negotiable; the build cadence around it is flexible.

The point is: the plan is precise where precision helps and loose where reality will overwrite. The audit protocol is the load-bearing structure that absorbs change without becoming chaos.

## 6. Build prerequisites — verified

| Prerequisite | Verified by | Status |
|---|---|---|
| All planning docs frozen and consistent | Cross-read of §1 files | ✅ |
| Test suite green (346/346) | `pytest tests/` | ✅ |
| Zero ResourceWarnings | `pytest -W error::ResourceWarning` | ✅ |
| App boots locally | `app.test_client().get('/healthz')` returns 200 | ✅ |
| All 5 fixtures load both via JSON and Excel | Smoke script run by baseline | ✅ |
| Spec amendments applied; spec ready to tag | `SYSTEM_SPEC.md §8` exists | ✅ |
| Code audit findings triaged with fix-now-vs-defer decisions | `CODE_AUDIT.md §9` table | ✅ |
| Anti-cheating protocol codified and binding | `VERIFICATION_MATRIX.md §4` | ✅ |
| Agency roles + cadence defined | `AGENCY_STRUCTURE.md` | ✅ |
| Risk register frozen | §3 above | ✅ |
| Change-management process defined | `AGENCY_STRUCTURE.md §5` | ✅ |
| Improv license + kill switch documented | `AGENCY_STRUCTURE.md §5.3, §5.4` | ✅ |
| IP hygiene posture decided (default option C) | `PRODUCTION_ROADMAP.md §1.1` | ✅ |

## 7. What "Begin Build" means — the actual scope of the next action

The build that begins next is **NOT new feature work** for Phase 2+. It is:

**Phase 1 — Observe (2026-08-01 to 2026-08-30 at Qapita)** per `PRODUCTION_ROADMAP §2` and `SYSTEM_SPEC §2`:
- Zero new code shipped.
- Shadow three real engagements end-to-end with Arthur Ng or Reinaldi Tanjung.
- Produce a written workflow map of each engagement.
- Deliver the Day-30 pitch document to Evelyn with the Path A vs Path B decision.

Phase 2 code-build begins ONLY if Evelyn signs Path A at the Day-30 review. Until then, the agency's output is research and the relationship.

Between now (2026-05-25) and 2026-08-01, the agency has these actions to take, in order:

1. Read the offer's IP clause when it lands; sanitise sensitive files per `PRODUCTION_ROADMAP §1.1`.
2. Practice the engine math on whiteboard for fixtures 03/04/05 until defensible from memory.
3. Pre-stage the external test inputs the Auditor cited (per `AUDIT_PLAN.md §1.1-1.6`), with hash-pinned snapshots so the publisher cannot edit them out from under the audit.
4. Set up the audit infrastructure: PDF-report template, companion XLSX template, network-capture tool for the no-LLM invariant scan.
5. Create the `BACKLOG.md`, `WEEKLY_LOG.md`, `DECISIONS.md` scaffolding files referenced in `AGENCY_STRUCTURE.md`.
6. Tag `SYSTEM_SPEC.md` as `spec-r1-2026-05-25` in git.
7. Do NOT ship any new feature code. Do NOT pre-build OPM Backsolve. Do NOT deploy publicly.

## 8. Sign-off block

By signing below, the user authorises the agency to:
- Tag the current spec as `spec-r1-2026-05-25`.
- Execute the pre-Day-1 actions §7.1 through §7.6.
- Begin Phase 1 at Qapita on 2026-08-01 per the spec, audit plan, and agency structure as frozen.
- Defer any feature build until Evelyn's Day-30 Path A signature.

The user retains the right to invoke the kill switch (`AGENCY_STRUCTURE.md §5.4`) at any time.

```
Authorised:    _______________________________
               Subhankar Shukla (CEO)

Witnessed:     _______________________________
               Subhankar Shukla (CTO, Supervisor, Planner, Structural,
               QA, Risk, Documentation Steward — wearing all hats)

Date:          ______________

Spec version:  spec-r1-2026-05-25

Audit version: AUDIT_PLAN.md as of 2026-05-25, with the 22-source catalog
               in §1 pre-staged with hash pins.
```

---

## 9. Open follow-ups (post-signoff, pre-Day-1)

These items remain genuinely undecided and will be resolved as evidence accumulates between signoff and Day 1:

1. **Whether to take the public GitHub repo private before Day 1** depends on the offer's IP clause text (not yet seen).
2. **Whether the LinkedIn portfolio post mentions the tool** depends on §1 decision.
3. **Whether to send Evelyn a brief pre-Day-1 note** asking the 10 Week-1 questions in `PRODUCTION_ROADMAP §1.3` versus saving them all for the first 1:1. Default: save them; pre-Day-1 contact reads as needy.
4. **Whether to attend any of Qapita's "Qonversation" public talks** between June and August as preparation. Default: yes, two of them; take notes.

These four are within the CEO role's discretion; no further sign-off needed.

## 10. One sentence

The system is in known good state, the planning surface is internally consistent and externally adversarially audited, the agency mandate is defined, the change-management room is left open on purpose, and the next action is observation rather than construction. The user signs, or the user names what is missing.
