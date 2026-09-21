# Build Wave 1 — What Shipped, What Is Stubbed for Evelyn

> Wave 1 took the system from a Phase-0 demo to a production-shaped
> implementation that is testable, deterministic, and audit-defensible
> end to end. The pieces that genuinely require Qapita / Evelyn input
> (real SSO endpoints, the Qapita cap-table data adapter, Qapita's
> house PDF style, real engagement data) are stubbed with clear
> abstraction points so they can be filled in without rewriting.
>
> Written 2026-05-25 at the close of the build wave.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave | 346 pass |
| Tests after wave  | 428 pass (+82 new regression tests) |
| Net new src/ modules | 9 |
| Net new test modules | 10 |
| Rule packs shipped | 2 (`v2026.1.0` baseline 8 rules, `v2026.2.0` expansion 23 rules) |
| Total registered rules | 23 (was 8) |
| Spec-gap blockers closed at code | GAP-01 concurrency, GAP-03 redaction, GAP-05 hash chain, GAP-07 engine binding, GAP-20/21/22 pari-passu, GAP-36 XSS escaping |
| Cross-cutting invariants enforced | refusal beats fabrication, snapshots immutable, audit log append-only, determinism, no LLM in calc |

## 2. What shipped

### 2.1 Foundation

**Pari-passu seniority** (`src/models.py`, `src/waterfall.py`, `tests/test_pari_passu.py`)
- New `seniority_sub_rank: int = 0` field on `ShareClass`.
- Validator rejects duplicate `(rank, sub_rank)` tuples; allows shared rank if sub-rank differs.
- Validator refuses mixed LP types within a pari-passu group (GAP-21).
- New `CapTable.preferred_seniority_groups` property: list of pari-passu groups, most-senior first.
- Waterfall regime walker now iterates groups; combined-LP breakpoint per group with proportional within-group allocation.
- Backward compatible: legacy fixtures (sub_rank=0 default) behave identically.

**Rule-pack versioning** (`src/rule_pack.py`, `rule_packs/*.json`)
- `RulePack` model with semver version, effective_from/to, jurisdictions, standards, rule_ids.
- `@rule(...)` decorator registers Python rule functions with metadata (severity, category, citation, jurisdictions, standards, introduced_in_pack).
- `EngagementPackBinding` records pack version + engine git short-SHA at bind time (GAP-07).
- `head_pack()` returns pack effective on a given date.
- `run_pack(cap_table, pack, engagement_jurisdiction)` enforces per-rule jurisdiction predicates (GAP-26).
- `META-RULE-MISSING-<id>` finding surfaces when a pack references a rule the engine doesn't have.
- Baseline pack `v2026.1.0` (8 rules) and expansion pack `v2026.2.0` (23 rules) shipped as JSON artifacts.

**Engagement / snapshot / audit-event model** (`src/engagement.py`, `src/identity.py`)
- `Engagement` headers with status (open/review/signed/archived), version counter, audit_head_hash, pack/engine bindings.
- `Snapshot` immutable rows linked via `superseded_by`; only the linkage pointer is ever updated, never the data fields.
- `Resolution` append-only with required non-empty citation.
- `audit_event` append-only with SHA-256 hash chain per engagement (GAP-05).
- `verify_audit_log(engagement_id)` recomputes the chain and reports the first integrity break.
- Optimistic concurrency: every mutation takes `expected_version` and raises `EngagementVersionConflict` (HTTP 409, code `engagement-version-conflict`) on mismatch (GAP-01).
- PDPA/GDPR/DPDPA redaction (GAP-03): partner-only operation, replaces snapshot payload with sentinel, logs the redaction itself as an audit event.
- Lifecycle transitions enforce permission table; partner can reopen signed → review (GAP-29 / SYSTEM_SPEC §3.2).
- Identity layer: `Role` enum, `_PERMISSIONS` matrix, `IdentityProvider` ABC with `StubSSOProvider` (Evelyn-blocked) and `StaticUserProvider` (tests).

### 2.2 Parsing

**Holder-level Indian-CFO Excel rollup** (`src/rollup.py`, `tests/test_rollup.py`)
- `is_holder_level_workbook(path)` detects holder-level vs class-level via header hints + name-shape heuristics.
- `aggregate_holders(path)` runs three priority heuristics: explicit class column → date+price cluster → name-pattern cluster.
- Confidence score per rolled-up group; `requires_manual_mapping=True` if any group < 0.80 (refusal beats fabrication).
- Every grouping decision recorded in `ParseReport` warnings with heuristic name, group label, sample holders.
- `synthesised_class_level_workbook(result)` materialises a class-level workbook the standard parser accepts. Defaults to `common` (preserves shares; analyst re-tags preferred in manual mapping).
- Holder-detail sidecar preserved separately for ESOP grant-level work.

### 2.3 Outputs

**Big-4 PDF audit memo** (`src/pdf_memo.py`, `templates/memo/base.html`)
- WeasyPrint generates a paginated A4 PDF with cover sheet, header/footer, page numbers, capital-structure table, findings table, breakpoints table, methodology disclosures, analyst-judgment blocks, signature block, provenance appendix.
- Citation provenance: each finding's rule ID maps to its registered citation (cross-cutting with rule-pack metadata).
- Refusal: `PDFBlockersOutstanding` (HTTP 409, code `pdf-blockers-outstanding`) if unresolved blocker findings.
- Refusal: `PDFNoReviewer` (HTTP 400, code `pdf-no-reviewer`) if no named reviewer.
- XSS escaping verified by `test_xss_escaping_in_rendered_html` (covers GAP-36 / SYSTEM_SPEC §8.16).
- HTML-render and PDF-bytes paths exposed separately so tests don't need native WeasyPrint deps if not available.

**Structured snapshot diff** (`src/structured_diff.py`, `tests/test_structured_diff.py`)
- Replaces fuzzy class-name diff with field-level `FieldDiff` (path, change_type, old_value, new_value, source_snapshot, rule_implications).
- Path syntax: `share_classes[<class_name>].liquidation_preference.cap_multiple`, etc. Lists keyed by `name`/`id` so reordering doesn't produce false diffs.
- Conservative rename detection: exactly-one-name-each-side + identical other attributes → `renamed` diff.
- Optional rule-pack run on both sides fills `rule_implications` with the set of finding codes whose firing differs.
- Determinism verified (same inputs → identical diff list).

### 2.4 Siblings (Phase 4)

**OPM Backsolve** (`src/opm/backsolve.py`, `src/opm/bsm.py`, `references/opm_backsolve_reference.md`)
- BSM call valuation (no scipy required for the pricing kernel — uses `math.erf`).
- Per-tranche value = `C(S, K_low) - C(S, K_high)`; allocated via tranche's marginal-allocation matrix.
- `scipy.optimize.brentq` solver on bounds `[1.0, 1e12]` per SYSTEM_SPEC §5.1.
- Sensitivity tables: vol (±10%), time (±1 yr), rf (±25 bps).
- DLOM applied to common via `(1 - dlom)` post-solve.
- Refusal: `BacksolveBlockersOutstanding` if cap table has unresolved blocker findings.
- Refusal: `BacksolveAnchorMissing` if the named anchor class doesn't exist.
- Reference computation appendix shipped (closes UNV-007 / SYSTEM_SPEC §8.7).

**BSM / IFRS 2 ESOP** (`src/opm/bsm_esop.py`, `tests/test_bsm_esop.py`)
- Per-grant `value_grant()` returns per-option fair value via BSM.
- `amortise_grant()` with cliff (straight-line) and graded (per-tranche straight-line per IFRS 2) vesting.
- Annual and monthly period-boundary support.
- Sum of period expenses equals aggregate FV; cumulative monotone-non-decreasing.
- Graded-vesting front-loading verified.

**DCF input sidecar** (`src/dcf_sidecar.py`, `tests/test_dcf_sidecar.py`)
- Excel workbook with one defined name per class for `share_count`, `lp_amount`, `conv_ratio` plus scalars `total_fully_diluted` and `lp_total`.
- Excel-defined-name sanitisation: invalid chars → `_`, leading digit prefixed, reserved tokens (`C`, `R`, `TRUE`, `FALSE`) prefixed.
- "Named Range Map" sheet preserves the human-readable class name alongside its slug.
- "Read me" sheet explains the contract to the DCF builder.
- Yellow-shaded input cells, deterministic sheet order.

### 2.5 Jurisdictions / rule expansion

**Rule pack v2026.2.0** (`src/rules_v2026_2.py`, `tests/test_rules_expansion.py`)

15 new rules across 7 categories:

| ID | Category | Trigger |
|---|---|---|
| `G-AD-003` | AD narrow-based | Narrow-based WA AD detected → memo flag |
| `G-AD-004` | AD triggered | `conversion_ratio > 1.0` → triggered ratchet info |
| `G-AD-005` | AD pari-passu inconsistent | Same-rank classes with differing AD variants |
| `G-LP-002` | LP cap-below-LP | Defence in depth on cap_multiple < 1 |
| `G-LP-003` | LP multiple > 1× | Auditor scrutiny |
| `G-SAFE-002` | MFN-only SAFE | No cap, no discount, no threshold but priced round after (GAP-19) |
| `G-SAFE-003` | Convertible threshold missing | qualified_financing_threshold not set |
| `G-POOL-002` | Pool > 25% | Atypical pool-size flag |
| `G-POOL-003` | Reserved without granted | Pool hygiene |
| `G-VOTE-002` | Voting ratio > 10:1 | Snap/Pinterest precedent |
| `G-ROUND-001` | Down round | Later PPS < prior max |
| `G-ROUND-002` | Same-date rounds different ranks | Likely pari-passu but not modelled as such |
| `G-SL-002` | Side-letter MFN keyword | Body mentions MFN |
| `G-IN-001` | India jurisdiction overlay | Jurisdiction-filtered to IN/INDIA only |
| `G-CURR-001` | Currency mismatch | Jurisdiction-currency mismatch (e.g. India + USD) |

## 3. What is STUBBED for Evelyn

Each stub has a clear seam where the real Qapita implementation slots in, with no other code change required.

### 3.1 Qapita SSO

**Where:** `src/identity.py`, `IdentityProvider` ABC + `StubSSOProvider`.
**What is stubbed:** `StubSSOProvider.authenticate(token)` returns a fixed dev analyst for any non-empty token.
**What Evelyn needs to deliver:** Qapita's SSO endpoint (probably OIDC/OAuth2), the token format, the role-claim mapping (Qapita's internal role names → our `Role` enum).
**What changes when she does:** new class `QapitaSSOProvider(IdentityProvider)`; wiring point is the production `app.py` constructor.
**Tests that prove the stub:** `tests/test_engagement.py` uses `StaticUserProvider` to inject specific role permutations.

### 3.2 Qapita cap-table data adapter

**Where:** `src/parser.py` (Excel ingest exists; Qapita adapter does NOT).
**What is stubbed:** Nothing in code — the ingestion architecture in `PRODUCTION_ROADMAP §3.1` calls for an `ingestion/qapita_api.py` adapter that produces the same canonical `CapTable` model. The data model is ready (and now supports pari-passu, conversion_ratio, side letters, SAFEs, warrants, convertibles); only the adapter is missing.
**What Evelyn needs to deliver:** read access to Qapita's cap-table data source (API or read-only DB), field mappings showing which Qapita field maps to which of our pydantic fields, and an exemplar engagement's data to validate end-to-end.
**Where it slots in:** new module `src/ingestion/qapita.py` returning `tuple[CapTable, ParseReport]`; downstream engine code is unchanged.

### 3.3 Qapita house PDF style

**Where:** `templates/memo/base.html` (CSS at top of file).
**What is stubbed:** Generic Big-4-defensible serif typography, neutral palette, A4 layout.
**What Evelyn needs to deliver:** Qapita's existing audit-memo template (Word or PDF), house typography spec, color palette, cover-page layout requirements.
**Where it slots in:** rewrite the `<style>` block and the cover-sheet markup. The data binding (Jinja2 variables) does not change.

### 3.4 Real engagement workflow integration

**Where:** `src/engagement.py` data model + `app.py` (HTTP layer not yet rewired to use it).
**What is stubbed:** The engagement model is fully implemented (tables, transitions, hash chain, redaction). The Flask app `app.py` still uses the Phase-0 `SessionStore` for backwards compatibility with the existing 5-fixture demo.
**What Evelyn needs to deliver:** confirmation that the engagement workflow shape (open → review → signed → archived; partner reopen capability) matches her team's real handoff process, and any modifications she wants.
**Where it slots in:** new Flask routes under `/engagement/...` that delegate to `EngagementStore`; the old `SessionStore`-backed routes remain for the demo. Migration is route-by-route, not big-bang.

### 3.5 Big-4 auditor sample for sign-off

**Where:** `VERIFICATION_MATRIX.md §5.2` audit cadence calls for a real Big-4 auditor reviewing one memo for Phase 2/3 sign-off.
**What Evelyn needs to identify:** one friendly Big-4 reviewer currently on a Qapita engagement willing to review one tool-generated PDF memo.
**What this validates:** that the PDF format, the citation-to-cell mechanism, and the analyst-judgment-section layout all survive an actual review without substantive pushback.

### 3.6 Real client cap-table corpus

**Where:** `fixtures/` currently has 5 curated fictional examples + 1 honest-limit stress test.
**What Evelyn needs to provide (or grant access to):** anonymised real engagement cap tables across the SEA + India + Delaware + Singapore deal shapes the team actually sees. Used to regression-test the rule packs against the long tail.
**What this enables:** the audit `AUDIT_PLAN.md §1` test plan (real DRHPs, real S-1s, real charter language) can be supplemented with real client engagements once de-identified.

### 3.7 Production infrastructure

**Where:** Phase 3 acceptance criterion `SYSTEM_SPEC §4.6`: "tool runs on Qapita infra, not laptop."
**What Evelyn / Vamsee need to deliver:** deployment target (Kubernetes? ECS? serverless?), SSO endpoint, managed Postgres (current SQLite is a dev placeholder for `SessionStore` + `EngagementStore`), monitoring stack, backup configuration with RPO ≤ 1h and RTO ≤ 4h (per SYSTEM_SPEC §8.6).
**What changes:** swap SQLite for Postgres in `SessionStore` and `EngagementStore` (both already abstracted via `db_path` parameter; needs DSN parameter instead). Add a thin `src/infra/postgres.py` wrapper. Deployment manifest under `infra/`.

## 4. Wave-1 architectural diagram (ASCII)

```
┌──────────────────────────────────────────────────────────────────────┐
│                            INGESTION                                 │
│  ┌─────────────┐    ┌────────────────┐    ┌─────────────────────┐   │
│  │ Excel       │    │ Holder-level   │    │ Qapita data adapter │   │
│  │ parser      │    │ rollup         │    │ (STUB — Evelyn)     │   │
│  └─────────────┘    └────────────────┘    └─────────────────────┘   │
│                  ↓ all emit canonical CapTable ↓                     │
└──────────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       CANONICAL MODELS                               │
│  CapTable + ShareClass (+ seniority_sub_rank, conversion_ratio,      │
│  LP variants, side letters, SAFEs, warrants, convertibles)           │
└──────────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       ENGINE                                         │
│  ┌─────────────┐    ┌────────────────┐    ┌─────────────────────┐   │
│  │ Waterfall   │    │ Checklist via  │    │ Structured diff     │   │
│  │ (pari-passu)│    │ RulePack       │    │ (field-level)       │   │
│  └─────────────┘    └────────────────┘    └─────────────────────┘   │
│      ↓                       ↓                      ↓                │
│  Breakpoints           Findings + rule         FieldDiff with        │
│  + Tranches            implications            provenance            │
└──────────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       PRODUCTION DATA LAYER                          │
│  Engagement / Snapshot (immutable) / Resolution (append-only)        │
│  Audit log (append-only, SHA-256 hash chain per engagement)          │
│  Identity (Role + StubSSO / Evelyn-blocked QapitaSSO)                │
└──────────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       OUTPUTS                                        │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │ JSON / XLSX  │ │ PDF memo     │ │ DCF        │ │ OPM Backsolve│  │
│  │ export       │ │ (WeasyPrint) │ │ sidecar    │ │ + BSM ESOP   │  │
│  └──────────────┘ └──────────────┘ └────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## 5. Test coverage of the wave

```
tests/test_pari_passu.py          6 tests   pari-passu + GAP-20/21/22
tests/test_rule_pack.py           9 tests   rule pack + engagement binding
tests/test_engagement.py         16 tests   engagement + snapshot + audit chain
tests/test_rollup.py              8 tests   holder rollup
tests/test_pdf_memo.py            5 tests   PDF memo + XSS + refusals
tests/test_structured_diff.py     7 tests   structured diff + rename detection
tests/test_opm_backsolve.py      12 tests   OPM Backsolve + BSM
tests/test_bsm_esop.py            6 tests   IFRS 2 ESOP amortisation
tests/test_dcf_sidecar.py         4 tests   DCF named-range sidecar
tests/test_rules_expansion.py     9 tests   v2026.2.0 expansion rules
                                 ──
                                 82 new regression tests
```

Plus the original 346: **428 total tests, all green, zero `ResourceWarning`** under `-W error::ResourceWarning`.

## 6. Wave-2 scope (the next things to build, in order)

When the next build wave starts, the order will be:

1. **Engagement-aware Flask routes** that exercise `EngagementStore` end to end (replacing the Phase-0 `SessionStore`-based routes). Needs the SSO stub to be wired into Flask's request lifecycle. Without this, the engagement model is library-only.
2. **OCR for image-PDF side letters** (SYSTEM_SPEC §4.3). Pdfplumber + Tesseract fallback with confidence normalisation per §8.5. Real fixture corpus required.
3. **Bulk-export rate limiting** (GAP-40 / SYSTEM_SPEC §8.17). Trivial once SSO is wired; per-user counters + HTTP 429.
4. **Backup / DR runbook** (SYSTEM_SPEC §8.6). Doc + scripts, not code.
5. **Postgres-backed `SessionStore` and `EngagementStore`** (Phase 3 infra). Needs Qapita / Vamsee's managed-DB choice.
6. **Further rule-pack expansion** to ~50 rules per `PRODUCTION_ROADMAP §4.1`. Incremental.
7. **`/whatif` zero-share fallback fix** (BUG-010 deferred). Recompute LP from override price when baseline shares == 0.
8. **`diff.py` None/0 conflation fix** (BUG-014 deferred). Reasonable now that the structured diff exists; old diff can be deprecated.
9. **NVCA alias coverage + Delaware-specific rules** (Phase 4 §5.4).

Wave-2 needs ~3 of the 7 Evelyn-blocked items (SSO, Qapita adapter, real data corpus) before it can start in earnest. The other items in §3 above are needed for production polish, not Wave-2 unblocking.

## 7. One sentence

The engine and the data layer are production-shaped; the integration points where Qapita's specific reality lives (SSO endpoints, cap-table source schema, house PDF style, real engagement workflow) are stubbed at clearly-named seams so that when Evelyn returns the answers to the Week-1 questions in `PRODUCTION_ROADMAP §1.3`, the work to wire her answers in is days, not weeks.
