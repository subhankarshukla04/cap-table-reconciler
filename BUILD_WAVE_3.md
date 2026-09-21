# Build Wave 3 — What Shipped + Audit Fix Batch

> Wave 3 stacked Phase-3 hardening on top of the wave-2 engagement
> surface: subsequent-events memo section reuses structured-diff;
> engagement-list pagination with role-aware scoping; audit-log SLO
> benchmark; volatility input pack honoring the §7 no-engine refusal;
> snapshot-stamped live workbooks; rule pack v2026.4.0 with structured
> protective-provisions / ROFR / drag-along fields (closes GAP-14).
>
> Independent agent audit ran post-build; found 2 blockers + 4 majors +
> 8 minors. The fix-now batch (B1, B2, M1, M2, M3, M4) landed in the
> same wave with 9 regression tests proving the fixes hold.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 3 | 486 pass |
| Tests after wave 3 build | 523 pass (+37 new) |
| Tests after wave 3 audit-fix batch | **532 pass** (+9 regression tests) |
| Net new src/ modules | 4 (`subsequent_events`, `opm/vol_pack`, `rules_v2026_4`, structured-diff classifier expansion) |
| Net new test modules | 7 |
| Rule packs total | 4 (baseline + v2026.2.0 + v2026.3.0 + v2026.4.0) |
| Total registered rules | **37** (was 30) |
| Spec-gap blockers closed in this wave | GAP-14 (structured PP/ROFR/drag), GAP-32 (snapshot-stamped sidecar), GAP-38 (audit-log query SLO) |
| Audit blockers found AND fixed in same wave | 2/2 (B1 vol-pack bounds, B2 PDF provenance regex broken for wave-3 rules) |
| Audit majors found AND fixed in same wave | 4/4 (M1 tenancy-leak on list, M2 classifier missing new field paths, M3 non-deterministic ORDER BY, M4 snapshot-stamp wall-clock) |
| Audit items deferred | 8 minors with reasoning in CODE_AUDIT_WAVE_3.md |

## 2. What shipped (build, then audit-fix)

### 2.1 Subsequent-events memo section (W3.1)

`src/subsequent_events.py` + template addition. Walks the engagement's
snapshot chain to find the original and head; diffs them via
`structured_diff.diff_snapshots`; groups FieldDiffs into memo-bucket
categories ("Share count", "Liquidation preference", "Protective
provisions", "Drag-along", etc.). Surfaces ALL resolutions across the
chain (closes audit M7 from wave 2 — prior resolutions no longer lost
when a new snapshot is appended).

PDF memo template now renders a `4a. Subsequent Events` section with
both grouped diff bullets and a full resolution history table.

### 2.2 Engagement list + search (W3.2)

`/engagement/` route is now paginated with filters: `status`,
`standard_of_value`, `client_id`, `date_from`, `date_to`, `q` (substring
on client_id / id / standard), `limit`, `offset`. Response shape:

```json
{
  "total": 17,
  "limit": 50,
  "offset": 0,
  "items": [{...engagement}, ...]
}
```

Role-aware scoping:
- analyst: own-created only
- reviewer / partner: per-`client_id` only (must pass `?client_id=`; otherwise 400 with `client-id-required-for-role`) — partial mitigation of GAP-39 added during the W3-AUDIT fix batch
- read_only_auditor: zero engagements until per-token engagement ACL ships in a later wave

### 2.3 Audit-log query SLO (W3.3)

`tests/test_audit_log_slo.py` runs a 1k-event benchmark in CI (asserts
< 1s) and a `@pytest.mark.slow` 10k-event benchmark for the full
SYSTEM_SPEC §8 OPS ≤ 5s SLO. Also includes the M1 rate-limit window
math fix verification — confirms a counter actually drops to zero past
the 2-hour boundary (closes audit M1 from wave 2).

### 2.4 Volatility input pack (W3.4)

`src/opm/vol_pack.py`. `build_vol_pack_template()` materializes an
Excel form with yellow-shaded inputs + named-cell slugs for: vol,
time-to-liquidity, rfr, dividend_yield, dlom, plus 7 sourcing
fields (peer tickers, observation window, size adjustment bps, citation,
time basis, rfr source, DLOM basis). `read_vol_pack()` reads it back,
**rejects** numeric values outside spec bounds, refuses if any required
sourcing field is empty. Honors §7 *"no volatility peer-set engine"* —
the tool structures the form; the analyst sources and defends.

### 2.5 Snapshot-stamped live workbook (W3.5)

`build_formula_workbook()` accepts an optional `snapshot_stamp` dict
and writes a hidden "Snapshot Stamp" sheet with engagement_id,
snapshot_id, memo_version, engine_version, pack_version,
generated_at, schema_version. **Refuses** if `generated_at` is missing
(W3-AUDIT M4 fix — wall-clock injection would break SYSTEM_SPEC §8.10
determinism). Caller passes `snapshot.created_at` for deterministic
output.

### 2.6 Rule pack v2026.4.0 — structured-field rules (W3.6)

`src/rules_v2026_4.py` + `rule_packs/v2026.4.0.json`. Closes GAP-14
by introducing structured `ProtectiveProvision`, `ROFRTerms`,
`DragAlongTerms` fields on `CapTable`. 7 new rules query them directly
instead of scraping side-letter text:

| ID | Triggers on |
|---|---|
| `G-PP-001` | Preferred exists, protective_provisions list empty |
| `G-PP-002` | Provision with consent_threshold_pct > 66.67% |
| `G-PP-003` | Provision with no consenting_class_names |
| `G-ROFR-002` | ROFR notice_period_days < 15 |
| `G-DRAG-002` | Drag threshold outside 50-75% |
| `G-DRAG-003` | Drag terms exist but drag_classes empty |
| `G-XREF-001` | Drag present but no ROFR terms (uncommon pairing) |

Total registered rules: **37**. Backward compat verified: legacy
CapTable JSON without the new fields still validates.

### 2.7 W3-AUDIT fix batch

In response to `CODE_AUDIT_WAVE_3.md`:

**Blockers fixed:**
- **B1 vol-pack numeric bounds**: `read_vol_pack` now refuses
  vol outside [0, 5], time ≤ 0 or > 50, rfr outside [-0.05, 1], dlom /
  dividend_yield outside [0, 1]. Spec §5.1 numeric contract honored
  with structured rejection rather than silent acceptance.
- **B2 PDF provenance regex**: rewritten to enumerate `pack.rule_ids`
  directly (every rule with metadata gets a row), instead of regex-
  parsing finding codes. Wave-3 rules (PP-EMPTY, DRAG-CLASSES-EMPTY,
  XREF-DRAG-NO-ROFR, etc.) now appear correctly in the appendix.

**Majors fixed:**
- **M1 tenancy enumeration leak**: reviewer/partner must pass
  `?client_id=` or receive HTTP 400 `client-id-required-for-role`. Not
  the full GAP-39 fix (per-token engagement ACL), but a meaningful
  surface-area reduction.
- **M2 subsequent-events classifier**: added buckets for
  `protective_provisions`, `rofr_terms`, `drag_along_terms` paths so
  the new structured fields appear in the right memo section instead
  of "Other".
- **M3 deterministic ordering**: `list_snapshots` and
  `list_resolutions` now use `ORDER BY <ts>, id` so ties resolve
  deterministically. Required for SYSTEM_SPEC §8.10 memo determinism.
- **M4 snapshot-stamp wall-clock**: `build_formula_workbook` raises
  `ValueError` if `snapshot_stamp.generated_at` is missing instead of
  silently injecting `datetime.now()`. Caller must pass a deterministic
  source (typically `snapshot.created_at`).

**Minors deferred** with notes in CODE_AUDIT_WAVE_3.md §3: pagination
edge cases (negative offsets normalised to 0 already in `max(0, ...)`),
duplicate-PP-name produces duplicate codes (cosmetic), date-filter
silent acceptance of garbage (minor — ISO comparison still safe), CSS
brittle interpolation (not exploitable today), historical-resolutions
block omits decision column (UX), vol-pack column-D slug editable
(test fixture surface). All tracked.

## 3. What is stubbed for Evelyn (cumulative)

No new items added this wave. Cumulative list unchanged from wave 2 §3
except for status updates:

1. Qapita SSO endpoint + JWT mapping — unchanged.
2. Qapita cap-table data adapter — unchanged.
3. Qapita house PDF style — unchanged.
4. Real engagement workflow integration — **LIVE and used** in tests; awaiting Evelyn confirmation that workflow shape matches her team's reality.
5. Big-4 auditor sample — unchanged.
6. Real client cap-table corpus — unchanged.
7. Production infrastructure — unchanged.
8. **Per-token engagement ACL (GAP-39)** — partial mitigation landed in W3-AUDIT M1; full implementation still requires Evelyn confirming scoping semantics.
9. **Pack-bytes persistence (M4 from wave 2 audit)** — deferred again; the bundle still loads packs from `rule_packs/*.json` at export time. Adding a `pack_json_bytes` column on `EngagementPackBinding` is a wave-4 task once Postgres ships.

## 4. Test coverage of the wave

```
tests/test_subsequent_events.py       5 tests
tests/test_engagement_list.py         9 tests
tests/test_audit_log_slo.py           4 tests (1 marked slow)
tests/test_vol_pack.py                5 tests
tests/test_snapshot_stamp.py          4 tests
tests/test_rules_v2026_4.py          10 tests
tests/test_audit_fixes_wave3.py       9 tests
                                     ──
                                     46 new wave-3 regression tests
                                     (45 active, 1 slow)
```

Plus the 486 from waves 0–2: **532 total active tests, all green,
zero `ResourceWarning` under `-W error::ResourceWarning`**.

## 5. What's next (wave 4 candidates)

Order of operations if/when a wave 4 starts. None of these is in
scope unless explicitly requested:

1. **Engagement-aware UI templates** — HTMX surface for the
   `/engagement/*` blueprint so analysts use it from a browser, not
   `curl`.
2. **Postgres backing for `EngagementStore` and `ExportRateLimiter`**
   — once Vamsee picks the production DB.
3. **Per-token engagement ACL (GAP-39 full)** — once Evelyn confirms
   scoping semantics for read_only_auditor.
4. **Pack-bytes-at-bind persistence (audit M4 from wave 2)** — store
   the bound pack JSON on each engagement so the bundle is fully
   self-contained.
5. **`/whatif` zero-share fallback exposed in HTMX** — already wired
   in the backend (BUG-010 fix), needs UI affordance.
6. **DCF model template** — pair with the volatility pack and the DCF
   sidecar from wave 1 to give analysts a complete worksheet.
7. **More rule expansion to ~50 rules** — incremental as engagement
   types come up (e.g., wave-4 might cover ASC 718 ESOP edge cases,
   Singapore VIMA-specific clauses, Indonesia OJK).
8. **Real Tesseract install + system-test pipeline** — currently the
   OCR backend stub is the production path; needs `brew install
   tesseract` + integration test to qualify it.

## 6. Two sentences

Wave 3 made the engagement model usable end-to-end through a Flask
surface that supports filtering, pagination, subsequent-events memo
sections, structured protective-provisions / ROFR / drag-along rules,
and a vol input pack that refuses to run OPM Backsolve when sourcing
is missing. The audit caught 2 blockers and 4 majors that would have
shipped silently — vol-pack accepting negative volatility,
PDF provenance missing wave-3 rule IDs entirely, reviewer/partner
enumerating the full engagement table, two non-deterministic ORDER BY
clauses — all fixed and locked with regression tests in the same wave.
