# Build Wave 7 — What Shipped

> Wave 7 is the analyst-facing feature wave: the snapshot timeline +
> N-way diff + xlsx workpaper export. Lands the "expert-led, faster"
> positioning for Evelyn directly — every analyst flow that used to be
> mental glue across pairwise diffs is now one click + one table.
>
> Written 2026-05-26 at wave-7 close.

---

## 1. Headline metrics

|   |   |
|---|---|
| Tests before wave 7 | 716 active |
| Tests after wave 7 | **742 active** (+26) |
| `-W error::ResourceWarning` | clean (6 pre-existing weasyprint/openpyxl GC warnings) |
| Net new src/ modules | 2 (`snapshot_timeline`, `diff_workpaper`) |
| Net new test modules | 1 (`test_wave7_diff`) |
| New routes | `GET /engagement/<id>/snapshots`, `GET /engagement/<id>/diff`, `GET /engagement/<id>/diff.xlsx` |
| New schema columns | `snapshot.change_note` (idempotent ALTER migration) |
| New audit-event types | `snapshot_diff_exported` |
| Spec round | 5 — §12.1-§12.6 |

---

## 2. What shipped (W7.1 – W7.7)

### 2.1 Chronological snapshot timeline (W7.1)
`GET /engagement/<id>/snapshots` lists every snapshot per engagement
with metadata (date, version, who uploaded, source filename, change
note, head/superseded status). HTML view renders a compact table plus
the compare checkbox form (when ≥2 snapshots exist). JSON view returns
the same data for API clients. Navigation added to the detail page
as `Snapshot timeline` button.

### 2.2 N-way snapshot diff (W7.2)
`GET /engagement/<id>/diff?snap=<id>&snap=<id>[&snap=<id>...]` computes
the cross-snapshot drift in one pass. Snapshots are sorted
chronologically; analyst can pick out of order. Refuses fewer than 2
snapshots (`diff-needs-two-snapshots`) and rejects cross-engagement
snapshot ids (`snapshot-engagement-mismatch`). The pure-compute primitive
lives in `src/snapshot_timeline.py` so it's reusable by the workpaper
exporter and any future memo integration.

Per-class table layout: one master row per class name (union across
snapshots), six sub-rows per class (shares_outstanding / issue_price /
seniority_rank / liquidation_preference / conversion_ratio /
anti_dilution). N columns one per snapshot. Reads chronologically left-
to-right.

### 2.3 Per-class drift highlighting + magnitude tiers (W7.3)
Four-tier classification per (class, field) cell:

| Tier | Trigger |
|---|---|
| `none` | identical across all snapshots |
| `minor` | numeric value moves within ±5% |
| `material` | numeric value moves 5–20% |
| `major` | numeric value moves >20% OR presence change OR any categorical change |

Class-level overall tier is `max(field tiers)`. UI renders the tier as
a colour-coded pill (slate / blue / amber / red); xlsx export uses
matching cell fills. Legend rendered on the diff page so the analyst
sees the scale up front.

### 2.4 Snapshot change-note annotation (W7.4)
`Snapshot` gained `change_note: Optional[str]`. Set at upload time via
the form field `change_note=...` (empty/whitespace becomes None). DB
migration is idempotent — `ALTER TABLE snapshot ADD COLUMN change_note
TEXT` runs once on `EngagementStore.__post_init__`, `duplicate column
name` is swallowed. Legacy snapshots read as `change_note=None`. The
note surfaces in the snapshot timeline, in the diff snapshot-headers
section, and in the xlsx workpaper Summary + Snapshots tabs.

### 2.5 Diff workpaper export (W7.5)
`GET /engagement/<id>/diff.xlsx?snap=...&snap=...` renders the same
diff as a 3-tab xlsx: **Summary** (engagement headers, aggregate
counts), **Class Drift** (one row per (class, field) with magnitude
tier + N snapshot value columns + colour-coded fills), **Snapshots**
(raw metadata per snapshot for traceability). Consumes the export
rate limit (shares budget with memo + bundle).

### 2.6 Audit-log integration (W7.6)
New `AuditEventType.snapshot_diff_exported`. Edge-triggered on every
xlsx download with payload `{snapshot_ids: [...], format: "xlsx",
class_count: N}`. Lands in the hash chain → the bundle picks it up
automatically → Big-4 reviewer pulling the bundle six months later
sees every workpaper export with full chain-of-custody.

### 2.7 Test surface + spec round 5 (W7.7)
26 new tests in `tests/test_wave7_diff.py`:
- 9 unit tests on the pure compute primitive
  (`_classify_pct`, `_max_tier`, `compute_timeline_diff` with magnitude
  + presence + redaction + length validation)
- 2 unit tests on the xlsx workpaper builder
- 7 end-to-end tests via the Flask test client
  (timeline JSON shape, diff refuse <2 snapshots, cross-engagement
  rejection, N-way grid, xlsx audit event, HTML compare form,
  change_note round-trip)
- spec round 5: §12.1-§12.6 documents the new surface; §9.6 inventory
  gains `diff-needs-two-snapshots` and `snapshot-engagement-mismatch`.

---

## 3. Files touched

| File | Reason |
|---|---|
| `src/snapshot_timeline.py` | new — N-way diff pure compute + magnitude classifier |
| `src/diff_workpaper.py` | new — xlsx workpaper builder |
| `src/engagement.py` | W7.4 `Snapshot.change_note` field + DB column + idempotent ALTER; `add_snapshot()` parameter; `_row_to_snapshot` legacy-column tolerance |
| `src/engagement.py` (AuditEventType) | W7.6 `snapshot_diff_exported` event |
| `src/engagement_routes.py` | W7.1 `/snapshots` route; W7.2 `/diff` route; W7.5 `/diff.xlsx` route with rate limit + audit-event hook; upload route now plumbs `change_note` |
| `templates/engagement/snapshots.html` | new — chronological timeline + compare checkbox form |
| `templates/engagement/diff.html` | new — N-way side-by-side per-class table with magnitude pills |
| `templates/engagement/detail.html` | added change_note input on upload form; added Snapshot timeline button |
| `SYSTEM_SPEC.md` | round 5 (§12.1-§12.6) + §9.6 inventory additions |
| `tests/test_wave7_diff.py` | new — 26 tests |

---

## 4. Audit + post-audit fixes

The independent wave-7 audit (`SYSTEM_AUDIT_WAVE_7.md`) found 2 blockers,
4 majors, and 7 minors. All blockers + all fix-now majors + 3 fix-now
minors closed in the same wave, with 19 regression tests in
`tests/test_wave7_audit_fixes.py`.

### 4.1 Blockers (closed)

| ID | Finding | Fix landed |
|---|---|---|
| B-W7-1 | Redacted snapshot's `change_note` leaked through timeline JSON, diff JSON+HTML, xlsx workpaper, and the bundle (PDPA / GAP-03 regression) | `redact_snapshot_pii` UPDATE now zeroes `change_note` AND `source_filename` atomically with the cap-table sentinel. Defence-in-depth: `Snapshot.safe_change_note()` + `safe_source_filename()` accessors used at every render boundary; bundle exporter `model_copy(update={...: None})` when `snap.redacted`. |
| B-W7-2 | A snapshot with a control char in `change_note` permanently 500'd the xlsx workpaper export for the engagement | Upload route validator rejects `[\x00-\x08\x0b\x0c\x0e-\x1f]` with `change-note-illegal-character` 400. `_safe_cell()` in `diff_workpaper` strips the same character class as defence in depth for legacy data. |

### 4.2 Fix-now majors (closed)

| ID | Finding | Fix landed |
|---|---|---|
| M-W7-1 | `/diff` did material compute (N JSON loads + class union) with no rate limit | Mirrors the `/whatif` block: consumes `COMPUTE_LIMITER`, writes `compute_burst_alert` at hard boundary with `payload.route = "diff"`. |
| M-W7-2 | `?snap=` accepted unbounded + duplicate ids; 500-column response trivially achievable | New `_parse_diff_snap_ids` helper dedupes via `dict.fromkeys` and caps at `MAX_DIFF_SNAPSHOTS = 20`. New error code `diff-too-many-snapshots`. Applied to `/diff` and `/diff.xlsx`. |
| M-W7-3 | Diff route error responses returned raw JSON when `html=1` (regression of W4-AUDIT M-3 discipline) | `_diff_error()` branches on `_wants_html()` and renders `engagement/error.html` for HTML clients. Used at every manual error site in both routes. |
| M-W7-4 | Bundle exporter leaked redacted `change_note` via `model_dump_json` | Sub-finding of B-W7-1; folded into the same fix (bundle `model_copy(update={...})` for redacted snaps). |

### 4.3 Fix-now minors (closed)

| ID | Finding | Fix landed |
|---|---|---|
| m-W7-2 | `change_note > 32767` chars silently truncated by openpyxl | Upload route caps at 32767 with `change-note-too-long` 400; `_safe_cell` truncates legacy data. |
| m-W7-5 | Dead `if/else` branch in `_compute_field_tier` categorical path | Collapsed to single `tiers.append("major" if prior != current else "none")`. |
| m-W7-6 | Unknown snapshot id returned generic `engagement-error` | New `SnapshotNotFound(EngagementError)` subclass with `error_code = "snapshot-not-found"`, `http_status = 404`. `EngagementStore.get_snapshot` now raises it; diff routes catch and emit the dedicated code. |

### 4.4 Deferred (post-wave-7 backlog)

| ID | Finding | Defer rationale |
|---|---|---|
| m-W7-1 | xlsx workpaper bytes not stable across regenerations | Pre-existing platform behaviour shared with `formula_workbook`; track as a global xlsx-determinism epic when the workpaper enters the bundle |
| m-W7-3 | `_classify_pct` doesn't guard NaN | No upstream source emits NaN today; add assertion when an external integration could |
| m-W7-4 | Timeline JSON exposes `created_by` for redacted snapshots | Pair with a broader "redaction-safe view" sweep; not regressed by W7 |
| m-W7-7 | Diff HTML's xlsx export link silently flattens snapshot order | Comment-only future-concern; analyst-controlled re-ordering not in scope |

---

## 5. What's next

Wave 7 closes the multi-snapshot story. Possible wave-8 directions in
rough priority order:

1. **Real OIDC/SAML callback** to replace `StubSSOProvider` — the single
   remaining "any non-empty token authenticates as analyst" surface.
   Blocked on Evelyn's SSO endpoint + JWT claim mapping.
2. **Engagement archival + 90-day restore window** — closes spec §3.2
   (`archived` is terminal); needed for Big-4 compliance posture.
3. **Postgres swap** — SQLite abstracts cleanly behind `EngagementStore`;
   wave 8 wires connection pool + migration story.
4. **Rule pack v2026.7.0** — Big-4 firm-specific waterfall checks
   (Deloitte 409A drift, EY IFRS 13 disclosure gaps, KPMG OPM tail-vol,
   PwC IRR backsolve sanity).
5. **Diff → memo integration** — embed the magnitude-tiered drift table
   into the PDF audit memo as a new section.
