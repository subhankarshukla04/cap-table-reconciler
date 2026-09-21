# SYSTEM AUDIT — Wave 7 (snapshot timeline + N-way diff + xlsx workpaper)

**Auditor:** independent (this session)
**Scope:** changes introduced by W7.1–W7.7 plus cross-wave contracts those changes touch (bundle export, redaction, audit chain, rate limiting, content negotiation).
**Method:** read all new + modified files; reproduced every non-obvious finding with `.venv/bin/python -c "..."` against the project venv.
**Suite at audit time:** 742 passing under `-W error::ResourceWarning`. None of the findings below are caught by the wave-7 test pack.

Severity ladder: **BLOCKER** (ship-stop) → **MAJOR** (pre-prod) → **MINOR**.

---

## 1. BLOCKERS

### B-W7-1 — Redacted snapshot's `change_note` is leaked everywhere it is rendered (PDPA / GAP-03 regression)

**Files:** `src/engagement.py:879-921` (`redact_snapshot_pii`), `src/engagement_routes.py:1009-1020` (timeline JSON), `src/engagement_routes.py:1074-1106` (diff JSON), `src/engagement_routes.py:1147-1156` (xlsx workpaper), `src/engagement_bundle.py:123-124` (bundle snapshot dump), `templates/engagement/diff.html:53-55` (diff HTML).

`redact_snapshot_pii` overwrites only `cap_table_json` and flips `redacted=1`. Pre-W7 that was complete; W7.4 added a new `change_note` column carrying analyst-supplied free-form text that frequently contains exactly the PII that triggered the redaction request (the demo upload form's placeholder even encourages naming people and dollar amounts: `"e.g. Series C closing — added 1.5M shares at $1.50"`). After W7, that text survives redaction and re-surfaces in:

  1. `GET /engagement/<id>/snapshots` (JSON) — reproduced.
  2. `GET /engagement/<id>/diff` (JSON + HTML) — reproduced; the diff HTML template does not gate change_note on `s.redacted` the way `snapshots.html:54-56` does.
  3. `GET /engagement/<id>/diff.xlsx` (Summary tab col F + Snapshots tab col F) — reproduced.
  4. `GET /engagement/<id>/bundle.zip` — reproduced; `snap.model_dump_json(indent=2)` serialises the field unconditionally.

Reproduction: see the bash trace in this session — note `"PII secret: investor mary@example.com paid 1.5M"` survived a partner redaction and was emitted in `snapshots/<id>.json` inside the bundle, in the diff JSON for a redacted middle snapshot, and rendered in the diff HTML (`"contains PII note? True"`).

**Fix:** in `redact_snapshot_pii`, the UPDATE must zero `change_note` (and arguably `source_filename` — same PII risk if filename contains the client's name). Defence in depth: every consumer that reads a snapshot for display (`_row_to_snapshot`, the diff JSON serializer in `engagement_routes.py`, `diff_workpaper.build_diff_workpaper_xlsx`, `snap.model_dump_json` in the bundle) should also coerce `change_note` to `None` (or to a sentinel like `"[redacted]"`) when `snap.redacted` is True. The right shape is a single helper `_redaction_safe_view(snap) -> dict` reused by all four consumers so the next PII-bearing column added is not a third regression.

---

### B-W7-2 — `GET /engagement/<id>/diff.xlsx` crashes (HTTP 500) when any selected snapshot's `change_note` contains a control character

**File:** `src/diff_workpaper.py:79` and `:134` (`ws.cell(... value=s.change_note or "")`).

The DB column is `TEXT` with no character filtering; the upload route in `engagement_routes.py:723` only strips whitespace. SQLite happily round-trips control chars (NUL through 0x1F) and so does the diff JSON path. openpyxl refuses them via `IllegalCharacterError`, which propagates out of `build_diff_workpaper_xlsx` to Flask's default 500 handler. Reproduction in this session: `'pre\x01post'` change_note → `IllegalCharacterError: prepost cannot be used in worksheets` → HTTP 500.

Impact: any analyst (or — more concerning — a hostile party able to upload, e.g. via a future API surface) can permanently brick the xlsx export for an engagement by uploading a single snapshot with `change_note='\x00'`. The error is sticky because the snapshot is immutable; the only remedy is partner redaction, and W7.5 is meant to be the auditor's escape hatch from broken HTML.

**Fix:** the cheap fix is a `_sanitise_for_xlsx(s) -> str` helper that strips/replaces the openpyxl-illegal char set (`re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")`) and is applied at every `ws.cell` site that takes `change_note`, `source_filename`, or `created_by`. The right fix is to validate change_note at the upload-route boundary (reject the upload with `error_code: change-note-illegal-character`) so the bug surfaces at write time, not at every read.

---

## 2. MAJORS

### M-W7-1 — `GET /engagement/<id>/diff` has no rate limit; bypasses the W5.5 compute budget

**File:** `src/engagement_routes.py:1024-1106`.

The /whatif route (line 1197-1225) explicitly consumes a `COMPUTE_LIMITER` token because "each /whatif costs one waterfall recompute; abusive spam would burn CPU without tripping any alert". The wave-7 diff route does strictly more work per request: it calls `s.load_cap_table()` for every snapshot id (each one a JSON deserialise + pydantic re-validate of a CapTable), then runs `compute_timeline_diff` which is O(snapshots × classes). Yet it bypasses both the export and compute limiters entirely. An authenticated analyst (or revoked-but-leaked token before the deny list catches up) can hammer `/diff?snap=…&snap=…&snap=…` with a real engagement's snapshot ids and burn CPU without registering on any audit alert. There is no `compute_burst_alert` recorded for diff abuse.

**Repro:** the session trace shows `qs = '&'.join('snap=...' for _ in range(500))` returning 200 in 123 ms with no rate-limit consumption and no audit event written — pure compute spend with zero observability.

**Fix:** make `snapshots_diff` consume the `COMPUTE_LIMITER` exactly the way `whatif` does (mirror the block at lines 1197-1225), and write a `compute_burst_alert` at the hard boundary. The xlsx export route already gates on the export limiter; the JSON/HTML diff route should gate on compute.

---

### M-W7-2 — Diff route accepts unbounded + duplicate `snap=` parameters; trivial memory amplifier

**File:** `src/engagement_routes.py:1035-1064`.

`request.args.getlist("snap")` returns every value verbatim — no deduplication, no cap. The session repro shows `snap=<same-id>` × 500 produces a 500-column JSON response (or a 500-column xlsx) in 123 ms. With 50 real snapshots × 500 repeats × 6 fields × 1 KB of payload, a single GET produces a multi-MB response from a few-KB query string; with a real snapshot count in the dozens and a malicious client requesting all of them duplicated, this lifts the engagement's RAM ceiling per request.

The xlsx export amplifies it further: each duplicate snapshot adds a column to the "Class Drift" sheet *and* a row to the "Snapshots" tab. There is no cap on column count beyond Excel's intrinsic 16384 limit, which the engine will happily try to reach.

**Fix:** in `snapshots_diff` and `diff_workpaper_xlsx`, after `getlist` enforce
```python
snap_ids = list(dict.fromkeys(request.args.getlist("snap")))  # preserve order, dedupe
if len(snap_ids) > MAX_DIFF_SNAPSHOTS:  # e.g. 20
    return jsonify({"error": "...", "error_code": "diff-too-many-snapshots"}), 400
```
The cap is the natural analyst-workflow cap (a memo never compares more than ~6-10 snapshots); 20 is generous.

---

### M-W7-3 — Diff and diff-xlsx error responses ignore content negotiation (raw JSON in the browser)

**File:** `src/engagement_routes.py:1036-1049`, `1045-1049`, `1121-1135`, plus the snapshot-engagement-mismatch and "snapshot not found" paths.

W4-AUDIT M-3 wrapped the `EngagementError` family in `_engagement_errors` so HTMX form submissions get a styled error page on 4xx. The wave-7 routes return `jsonify({...}), 400` directly for "need at least 2 snapshots", "snapshot does not belong", "permission denied", and the deeper get_snapshot "snapshot ... not found". When the analyst submits the compare form from `snapshots.html` with only one checkbox ticked, the browser receives `application/json` with raw JSON in the viewport — confirmed in this session. Same for the cross-engagement mismatch path.

Additionally the get_snapshot path raises bare `EngagementError(f"snapshot ... not found")` (engagement.py:671) which renders to the wire as `error_code: "engagement-error"` — a generic catch-all that breaks the spec contract that every 4xx ships a stable machine-readable code. The diff and diff-xlsx routes should validate the snapshot ids themselves (return `snapshot-not-found`) instead of inheriting the generic base.

**Fix:** funnel the four manual error returns through `_engagement_errors`-style HTML/JSON branching, and introduce a dedicated `SnapshotNotFound(EngagementError)` subclass with `error_code = "snapshot-not-found", http_status = 404` for `get_snapshot`.

---

### M-W7-4 — Bundle export now leaks redacted change_note (cross-wave regression W7.4 × W2.x)

**File:** `src/engagement_bundle.py:123-124`, `snap.model_dump_json(indent=2)`.

This is a sub-finding of B-W7-1 but called out separately because the bundle is the artifact a Big-4 auditor downloads and stores outside the system; once the bundle ships with the PII inside, every PDPA-erasure remediation downstream of that bundle becomes a separate paper trail. The bundle's `redacted` flag is preserved in the JSON, but the body of the snapshot now carries the analyst's `change_note`. There is no carve-out in `engagement_bundle.py` for the new W7.4 column.

**Fix:** the helper from B-W7-1 must also be applied at line 124 — either model_dump with `exclude={"change_note"}` when redacted, or replace with the redaction-safe view.

---

## 3. MINORS

### m-W7-1 — xlsx workpaper bytes are not stable across two identical calls (docProps/core.xml timestamps)

**File:** `src/diff_workpaper.py:48-140`.

`Workbook()` populates `docProps/core.xml` with `dcterms:created` = wall clock; openpyxl rewrites it on every `.save()`. Reproduction: `build_diff_workpaper_xlsx(diff)` called twice 1.1 s apart produces 7222-byte outputs whose SHA-256s differ; the only diff is in `docProps/core.xml`. The cell payloads are stable (so the audit-relevant content matches), but a workpaper diff hash recorded in the bundle manifest would falsely flip on every regeneration.

Defer status: the same instability exists in `formula_workbook.build_formula_workbook`; wave 7 inherited the platform-level quirk, didn't introduce it. SYSTEM_SPEC §8.10 cares about cell-payload determinism, which is preserved. Flag as MINOR; fix would be to pin `wb.properties.created = wb.properties.modified = eng.created_at` (and `creator = "qapita-engine"`) at the top of `build_diff_workpaper_xlsx`, mirroring SD-AUD-B2's epoch-pinning idea.

### m-W7-2 — `change_note > 32767` chars is silently truncated in the xlsx workpaper

**File:** `src/diff_workpaper.py:79` and `:134`.

Excel's cell-text limit is 32767 chars. openpyxl truncates silently (verified: 50000-char note round-trips through the xlsx as 32767 chars). The DB has no length cap, so a 10 MB change_note round-trips happily there. Pair with B-W7-2's recommended upload-time validator: also cap change_note at 32767 chars (with a clear error code) so analyst expectations match what every consumer can render.

### m-W7-3 — `_classify_pct` numeric edge cases are surprising for negative or near-zero values

**File:** `src/snapshot_timeline.py:48-66`.

Currently:
  - `_classify_pct(-100, 100)` → `"major"` (correct: 200% drift)
  - `_classify_pct(-100, -150)` → `"major"` (correct: 50% drift)
  - `_classify_pct(1e-12, 1.0)` → `"major"` (technically correct; signals huge ratio but the analyst's mental model for "tiny number → unit number" probably wants `"major"` regardless, so this is fine)
  - `_classify_pct(float('nan'), 100)` → `"major"` (silently treats NaN as a value, branches into the `abs(current - prior) / abs(prior)` path which propagates `nan`; `delta < 1e-9` is False, `delta <= MINOR_FRAC` is False, falls through to `"major"`)

None of these are wrong outputs per se, but cap-table numeric fields should never be NaN. Add an assertion `if math.isnan(prior) or math.isnan(current): raise ValueError(...)` so a corrupt CapTable surfaces at the diff layer instead of being mis-classified as drift.

### m-W7-4 — Snapshot timeline JSON exposes `created_by` (user.id) without consideration for the redaction event

**File:** `src/engagement_routes.py:1014`.

The PDPA-erasure path (`GAP-03`) currently does not redact `created_by` either, and the W7.1 timeline now exposes it via JSON to anyone with `engagement.read`. Pre-W7 the same data was visible via the older detail-route snapshot list, so this is not a regression in attack surface — but the consolidated chronology view makes the leak more obvious. Defer to a broader "redaction-safe view" project (paired with B-W7-1's fix).

### m-W7-5 — `_compute_field_tier` categorical branch contains dead code

**File:** `src/snapshot_timeline.py:175-181`.

```python
if prior is None or current is None:
    tiers.append("major")
else:
    tiers.append("major")
```
Both branches append `"major"`. Either the dev meant to distinguish (presence-change vs variant-change with two real values) and the categories collapsed, or the if/else is leftover scaffolding. Either way it should be a single `tiers.append("major")` or the comment should say "any inequality is a major event" with the dead branch removed.

### m-W7-6 — Diff route returns "engagement-error" (generic) for unknown snapshot id

**File:** `src/engagement.py:671` and `src/engagement_routes.py:1044`.

`get_snapshot` raises `EngagementError(f"snapshot {snapshot_id} not found")`. The wave-7 diff route does not pre-validate snap ids, so the unknown-id path turns into `{"error_code": "engagement-error"}` instead of something like `"snapshot-not-found"`. Spec contract is that 4xx responses ship stable error codes (the wave-2 / wave-3 audits enforced this). Add a `SnapshotNotFound` subclass and raise it from `get_snapshot`.

### m-W7-7 — Diff HTML's "Export as workpaper" link does not preserve the snapshot order chosen by the analyst

**File:** `templates/engagement/diff.html:29-32`.

The link uses `{% for s in diff.snapshots %}snap={{ s.id }}{% endfor %}` — and `diff.snapshots` is the server-sorted (chronological) order. That happens to coincide with the route's own sort, so the workpaper is consistent. Minor concern: if a future change adds analyst-controlled re-ordering, this template silently flattens it. Worth a comment, not a fix.

---

## 4. Cross-wave contract matrix (W7 producers × W2–W6 consumers)

| W7 producer                                | Touches W2–W6 surface             | Status |
|---|---|---|
| `Snapshot.change_note` column (W7.4)       | `EngagementStore.add_snapshot` (W2)  | OK — keyword arg, default None, ALTER is idempotent |
| `Snapshot.change_note` column (W7.4)       | `EngagementStore.redact_snapshot_pii` (W2, GAP-03) | **B-W7-1** — redaction does not zero change_note |
| `Snapshot.change_note` column (W7.4)       | `build_engagement_bundle` (W3, byte-stable) | **M-W7-4** — bundle leaks redacted change_note via `model_dump_json` |
| `Snapshot.change_note` column (W7.4)       | Audit chain (W2, GAP-05)         | OK — change_note is not in `snapshot_added` payload; doesn't affect chain |
| `snapshot_diff_exported` audit event (W7.6) | `verify_audit_log` (W2)          | OK — chain verified clean across two diff exports |
| `snapshot_diff_exported` audit event (W7.6) | Bundle's `audit_log.jsonl`        | OK — new event_type flows through |
| `/engagement/<id>/snapshots` (W7.1)         | Permission gate (W3, engagement.read) | OK |
| `/engagement/<id>/diff` (W7.2)              | Permission gate (W3, engagement.read) | OK — read_only_auditor can read JSON; intentional |
| `/engagement/<id>/diff` (W7.2)              | Compute limiter (W5.5)            | **M-W7-1** — bypasses |
| `/engagement/<id>/diff` (W7.2)              | Content negotiation (W4.1)         | **M-W7-3** — error paths return JSON when html=1 |
| `/engagement/<id>/diff.xlsx` (W7.5)         | Export rate limiter (W3)          | OK — consumed |
| `/engagement/<id>/diff.xlsx` (W7.5)         | Permission gate (`export.xlsx`)   | OK — read_only_auditor blocked (403 confirmed) |
| `/engagement/<id>/diff.xlsx` (W7.5)         | Audit chain (W2, hash chain)     | OK — verified |
| `/engagement/<id>/diff.xlsx` (W7.5)         | openpyxl character constraints   | **B-W7-2** — IllegalCharacterError → 500 |
| Multi-line / unicode change_note            | SQLite TEXT round-trip            | OK — newlines, emoji, CJK, NUL all preserved |
| `compute_timeline_diff` (W7.2)              | Redacted snapshot path           | OK at compute layer (renders blank column); leak is downstream (B-W7-1) |

---

## 5. End-to-end timeline → diff → workpaper flow trace

```
User POST /engagement/<id>/upload (multipart file + change_note)
  └─ engagement_routes.upload (line 661)
       ├─ auth + can(upload_cap_table)                              [W2/W3 — OK]
       ├─ parse_excel → CapTable                                    [W1 — OK]
       ├─ store.add_snapshot(change_note=…)                         [W7.4 — OK]
       │    └─ INSERT into snapshot table; audit event snapshot_added
       │       (payload does NOT include change_note — chain stays narrow)
       └─ 201 + redirect / JSON

User GET /engagement/<id>/snapshots?html=1
  └─ engagement_routes.snapshots_timeline (line 988)
       ├─ auth + can(read)                                          [OK]
       ├─ list_snapshots — deterministic ORDER BY created_at, id    [W3-AUDIT M3 — OK]
       └─ render snapshots.html — change_note column hidden if redacted [OK]

User submits compare form (>= 2 checkboxes)
  └─ GET /engagement/<id>/diff?snap=...&snap=...&html=1
       ├─ auth + can(read)                                          [OK]
       ├─ getlist("snap")  — NO dedupe, NO cap                      [M-W7-2]
       ├─ FOR each id: get_snapshot + engagement mismatch check
       │    └─ unknown id → EngagementError "engagement-error"      [m-W7-6]
       │    └─ mismatch  → jsonify (JSON even when html=1)          [M-W7-3]
       ├─ sort chronologically                                      [OK]
       ├─ load_cap_table per snap (None when redacted)              [OK]
       ├─ compute_timeline_diff                                     [OK]
       ├─ NO rate-limit consume                                     [M-W7-1]
       └─ render diff.html OR jsonify
            └─ diff.html ALWAYS prints s.change_note                [B-W7-1]
            └─ JSON ALWAYS includes change_note                     [B-W7-1]

User clicks "Export as workpaper (xlsx)"
  └─ GET /engagement/<id>/diff.xlsx?snap=...&snap=...
       ├─ auth + can(export.xlsx)                                   [OK — read_only_auditor blocked]
       ├─ snap id validation (same flaws as diff)                   [M-W7-2 / M-W7-3]
       ├─ export rate-limit consume                                 [W3 — OK]
       ├─ build_diff_workpaper_xlsx
       │    ├─ ws.cell(value=change_note or "")                     [B-W7-2 — illegal char → 500]
       │    │                                                       [m-W7-2 — truncate at 32767]
       │    │                                                       [B-W7-1 — leaks redacted]
       │    └─ wb.save → core.xml carries wall-clock timestamp       [m-W7-1 — byte instability]
       ├─ audit: snapshot_diff_exported                             [W7.6 — chain OK]
       └─ 200 + xlsx blob
```

---

## 6. Things checked clean

  - W7.4 migration is idempotent: re-running `EngagementStore(...)__post_init__` on a freshly-altered DB is silent, and the legacy `_row_to_snapshot` correctly falls back to `change_note = None` for pre-W7 rows.
  - `change_note` SQLite round-trip preserves multi-line text, emoji, CJK characters, and even NUL bytes — no encoding loss at the DB layer.
  - `snapshot_diff_exported` audit event preserves hash-chain integrity: two exports → two events → `verify_audit_log` returns `(True, None)`.
  - HTML templates correctly escape change_note via `| e`. Even an XSS payload like `<script>alert(1)</script>` renders as text. No JS-injection risk in the diff or timeline HTML.
  - Permission model on `/diff.xlsx` correctly denies `read_only_auditor` (403 confirmed); `/diff` JSON correctly permits the same auditor (200) since they hold `engagement.read`.
  - Cross-engagement snapshot mismatch is caught (`error_code: "snapshot-engagement-mismatch"`) — a token holder for engagement A cannot diff one of A's snapshots against one of B's just by knowing B's snapshot UUID.
  - `compute_timeline_diff` length-mismatch and N=1 guards raise as expected.
  - Diff route is read-only — no CSRF concern even on cookie auth.
  - The form GET on `snapshots.html` with `?html=1` correctly drives the diff route into HTML rendering when 2+ checkboxes ship.

---

## 7. Fix now vs defer

| ID       | Severity | Recommendation                                                                                                                | Effort | Notes |
|---|---|---|---|---|
| B-W7-1   | BLOCKER  | **Fix now.** PDPA carve-out is a binding obligation under the redaction contract; the bundle export is the worst surface.    | M (1 helper + 5 call sites + a regression test) | Ship a hot-fix before pushing wave 7 to any tenant that has used `/redact`. |
| B-W7-2   | BLOCKER  | **Fix now.** A single bad-character upload bricks the workpaper export for the engagement.                                    | S (validator at upload route + tighten `_sanitise_for_xlsx`) | Pair with m-W7-2's 32767 cap. |
| M-W7-1   | MAJOR    | **Fix now.** Compute amplifier is real; mirrors the W5.5 fix exactly.                                                          | S (copy the whatif limiter block) | Two-line config + one audit event type. |
| M-W7-2   | MAJOR    | **Fix now.** Dedupe + cap (`MAX_DIFF_SNAPSHOTS = 20`) at the route boundary.                                                   | S | Same fix lives in two routes. |
| M-W7-3   | MAJOR    | **Fix now-ish.** Routes funnel through `_engagement_errors`-style HTML/JSON branching.                                         | M | Touches 4 manual jsonify sites. |
| M-W7-4   | MAJOR    | **Folds into B-W7-1.** Same redaction-safe-view helper.                                                                        | — | Don't ship the helper without applying it here. |
| m-W7-1   | MINOR    | **Defer.** Pre-existing platform behaviour; track as a separate determinism epic across all xlsx producers.                    | M | Will need a global `_pin_xlsx_properties` helper. |
| m-W7-2   | MINOR    | **Fix now** (cheap, ships with B-W7-2).                                                                                        | S | Add to upload-route validator. |
| m-W7-3   | MINOR    | **Defer.** NaN cap-table values are not currently possible; add assertion when we add an external integration that could emit them. | S | Worth a one-line assert. |
| m-W7-4   | MINOR    | **Defer.** Track under broader redaction-safe view (paired with B-W7-1 v2).                                                    | — | |
| m-W7-5   | MINOR    | **Fix now** (one-line cleanup; reduces "is this intentional" review friction).                                                 | XS | |
| m-W7-6   | MINOR    | **Fix-now-ish.** Introduce `SnapshotNotFound` subclass; small API contract improvement.                                        | S | |
| m-W7-7   | MINOR    | **Defer + comment.** Add a Jinja comment noting the chronological assumption.                                                  | XS | |
