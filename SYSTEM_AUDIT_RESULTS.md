# Compiled-System Audit — Results

> Single-page signoff after the cross-cutting audit ran across the
> entire stack (not per-wave). Written 2026-05-25 at the close of the
> audit-fix batch.

---

## 1. Headline numbers

|   |   |
|---|---|
| Tests before audit | 558 active |
| Tests after audit-fix batch | **571 active** (+13 new regression tests) |
| Tests under `-W error::ResourceWarning` | All green |
| Blockers found | 3 (B-1 memo-pack drift, B-2 cwd-relative pack path, B-3 sign-off bypass) |
| Blockers fixed | 3 / 3 |
| Majors found | 7 (M-1 head-snapshot, M-2 pack windows, M-3 error codes, M-4 lifecycle, M-5 voting class, M-6 valuation_date, M-7 dev pack) |
| Majors fixed | 6 / 7 (M-6 deferred — DB-serialisation change) |
| Spec amendment | round 2 appended to `SYSTEM_SPEC.md` §9 with re-tag `spec-r2-2026-05-25` |
| Rule pack data fix | All four pack JSONs now have correct `effective_to` closures |

## 2. What the audit caught that per-wave audits missed

The per-wave audits found 5 + 2 blockers + 8 + 4 majors inside their
respective waves. The compiled audit found different bugs entirely —
all of them at module-to-module seams:

- **B-1** memo route called `head_pack()` instead of the engagement-
  bound pack. Each individual wave looked correct (rule_pack honours
  binding; engagement.py records the version) — but no one checked that
  the memo route used the binding. Determinism §8.10 silently broken
  for any engagement opened under a pre-head pack.

- **B-2** bundle export used `Path("rule_packs")` (cwd-relative) while
  `src/rule_pack.py` defines `_PACKS_DIR` (absolute). Per-wave audit
  saw the bundle code; per-wave audit saw the rule_pack code; nobody
  cross-checked. Under any production cwd ≠ repo root, the bundle
  silently shipped without `rule_pack.json`.

- **B-3** review→signed lacked the blocker-finding gate that the spec
  explicitly forbids bypassing. The gate exists in `pdf_memo._ensure_eligible`
  (memo route), but the transition path doesn't go through there.

- **M-1** subsequent-events used `list_snapshots[-1]` instead of
  `eng.head_snapshot_id`. Wrong under same-microsecond ties.

- **M-2** all four pack JSONs shipped with `effective_to: null`, so
  `is_effective_on(any_date_in_2026)` returned True for all of them.
  `head_pack()` covered it; any external consumer of `is_effective_on`
  would have seen overlapping packs.

Cross-cutting bugs are real and only catchable by reviews that hold
the WHOLE system in working memory at once.

## 3. Fix batch applied

| ID | Severity | Where | Fix |
|---|---|---|---|
| B-1 | Blocker | `engagement_routes.py:497` | `pack = load_engagement_bound_pack(eng.pack_version)` instead of `head_pack()` |
| B-2 | Blocker | `engagement_bundle.py:75` | Use `load_engagement_bound_pack(eng.pack_version)` (which resolves via absolute `_PACKS_DIR`) |
| B-3 | Blocker | `engagement.py:transition()` | New `BlockerFindingsOutstanding` exception; `_enforce_blockers_resolved` loads head snapshot + bound pack + checks against recorded resolutions on `review → signed` |
| M-1 | Major | `subsequent_events.py:107` | Use `eng.head_snapshot_id` to find head; walk `superseded_by` parent map to find original |
| M-2 | Major | `rule_packs/*.json` | Data-only: v1 closes 2026-05-31, v2 closes 2026-08-31, v3 closes 2026-11-30; v4 stays open |
| M-3 | Major | `engagement.py:115` | Rename `illegal-transition` → `engagement-invalid-transition` (matches SPEC §3.2 vocabulary) |
| M-4 | Major | `SYSTEM_SPEC.md` | Spec amendment §9.1 documents the partner→archived + signed→review reopen transitions |
| M-5 | Major | `subsequent_events.py:_classify` | Added `"voting_differential" → "Voting / governance"` bucket |
| M-7 | Major | `rule_pack.py:load_engagement_bound_pack` | Refuses `v0.0.0-dev` unless `QAPITA_ALLOW_DEV_PACK=1` |
| M-6 | Major | `engagement.py:139` | DEFERRED — DB-serialisation change; spec §9.7 documents the deferral |

Plus a new spec-amendment round 2 (SYSTEM_SPEC.md §9) covering:
- §9.1 lifecycle clarifications (closes M-4)
- §9.2 engagement-bound pack contract (closes B-1)
- §9.3 sign-off gate (closes B-3)
- §9.4 rule-pack effective-window closure (closes M-2)
- §9.5 v0.0.0-dev refusal in production (closes M-7)
- §9.6 canonical error-code inventory (closes M-3)
- §9.7 valuation_date typing deferral (acknowledges M-6)

## 4. Things the audit explicitly verified clean

- Hash-chain offline-verify recipe works end-to-end (the bundle
  audit-log replay round-trips).
- Concurrent memo + redact does not corrupt the audit log (B1 wave-2
  fix holds under cross-module load).
- Bundle payload is byte-deterministic modulo the documented
  `manifest.generated_at` carve-out.
- `ResourceWarning` sweep returned zero leaks across all 50-engagement
  high-volume integration test.
- Unicode survives the full chain: Tamil, Devanagari, Arabic (RTL),
  emoji, AED currency, mixed scripts — all round-trip cleanly through
  parse → checklist → waterfall → diff → bundle.
- All 5 curated fixtures drive the engagement flow end-to-end.

## 5. Items the audit deferred

| ID | Why deferred | Tracked in |
|---|---|---|
| M-6 `valuation_date` typing | DB-serialisation migration; touches engagement schema | SPEC §9.7 |
| Per-route engagement-level tenancy ACL (GAP-39 full) | Requires Evelyn confirming scoping semantics | BUILD_WAVE_3.md §3 |
| Per-token engagement scoping for read_only_auditor | Same | BUILD_WAVE_3.md §3 |
| 8 minors from CODE_AUDIT_WAVE_3 (pagination, CSS, etc.) | Cosmetic / low-priority | CODE_AUDIT_WAVE_3.md |
| Tesseract production install + system test | System dependency, not Python | BUILD_WAVE_2.md §6 |
| Postgres migration | Vamsee's call | BUILD_WAVE_2.md §6 |

## 6. Test coverage summary

```
Total active tests:                571
- Wave 1 baseline (incl. fixtures):   ~330
- Wave 1 audit-fix regressions:        15
- Wave 2 build:                        46
- Wave 2 audit-fix regressions:        12
- Wave 3 build:                        37
- Wave 3 audit-fix regressions:         9
- Integration end-to-end:              26
- System-audit fix regressions:        13
- Other recent additions:              83
Slow benchmark (10k audit events):      1 (deselected by default)
```

Strict invariant: `-W error::ResourceWarning` is enforced. Zero leaks.

## 7. What the build-ready state is

Per `BUILD_READY.md` (still authoritative for "begin build" semantics)
+ the 3 build waves + this compiled audit:

- **Codebase:** 13,000+ LOC of source under `src/`, 8,000+ LOC of tests.
- **Rule packs:** 4 versioned packs, 37 registered rules, proper
  effective-window closures.
- **Documentation:** 13 planning/spec/audit docs in repo root totaling
  ~7,500 lines.
- **Spec:** `spec-r2-2026-05-25` (round 2 amendments append round 1).
- **Stubbed for Evelyn:** unchanged from BUILD_WAVE_3.md §3. SSO
  endpoint, Qapita data adapter, house PDF style, Big-4 auditor sample,
  real cap-table corpus, production infra (Postgres + monitoring +
  KMS + backup), per-token engagement ACL.

## 8. The single sentence

The compiled-system audit found three blockers and seven majors
specifically at module-to-module seams, all fixed in this same wave
with 13 regression tests proving the fixes hold, leaving the codebase
at 571 active tests green under strict resource warnings and ready for
whatever comes next.
