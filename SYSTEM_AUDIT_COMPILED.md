# Compiled System Audit

## 0. Stance + methodology

This is a cross-cutting integration audit. Per-wave audits already enumerated
intra-module bugs; this pass walks **module-to-module contracts**, **whole-
system flows**, and **spec-vs-implementation drift**, then enumerates the
seams that are at risk of breaking when one side changes.

Scope I read: `src/` (excluding sub-package internals beyond surface),
`app.py`, `templates/memo/base.html`, `rule_packs/*.json`, `references/`,
`OPERATIONS.md`, `SYSTEM_SPEC.md`.

Scope I did NOT read (per the instructions): `tests/`, `fixtures/`,
`BUILD_*.md`, `CODE_AUDIT_*.md`.

Repro strategy: every blocker / major has either a python one-liner under
`.venv/bin/python -c ...` or a `file:line` citation. I wrote zero new test
files; everything below was reproduced inline.

I tried to **avoid restating** anything that's plainly a per-wave concern
(e.g., individual finding bodies, single-rule math). I focused on:

- Where wave-2 and wave-3 modules call each other and one side has drifted.
- Where the spec amendments in §8 were added but downstream consumers
  weren't updated.
- Where the system depends on something not in the spec (engine→spec drift).
- Where a determinism / lifecycle claim quietly fails under a realistic
  edge case (Unicode, time inversion, identical timestamps).

---

## 1. Blockers (anywhere in the system)

### B-1. Engagement-bound rule pack is ignored at memo time

**Files:** `src/engagement_routes.py:497` (and the subsequent-events
call at `:512`).

The engagement model records `pack_version` at engagement-open
(`src/engagement.py:142`, `:351`, `:358`). SYSTEM_SPEC §4.1 binding
behaviour is explicit:

> The engagement runs the checklist using the bound pack for its entire
> lifetime. Re-running the checklist on a historical snapshot uses the
> snapshot's engagement's bound pack.

The `/engagement/<id>/memo.pdf` route does:

```python
# src/engagement_routes.py:497
pack = head_pack()
findings = run_pack(cap_table, pack=pack)
# :512 — same head_pack reused for subsequent-events
rollup = compute_subsequent_events(_store(), eng.id, pack=pack)
```

`head_pack()` returns the **current** head pack, not `eng.pack_version`.
So an engagement bound to `v2026.1.0` (8 rules) that generates a memo
today (head = `v2026.4.0`, 37 rules) silently runs the newer pack.

Repro:

```bash
.venv/bin/python -c "
from src.rule_pack import head_pack, load_pack_from_file
print('head:', head_pack().version, len(head_pack().rule_ids))
print('v1:', load_pack_from_file('rule_packs/v2026.1.0.json').version,
      len(load_pack_from_file('rule_packs/v2026.1.0.json').rule_ids))
"
# head: v2026.4.0 37
# v1: v2026.1.0 8
```

Downstream consequences:

- Memo PDF "findings" section reflects a pack the engagement is not bound
  to. Determinism (§8.10) is violated: same engagement re-generated next
  month produces different findings.
- `compute_subsequent_events`'s `rule_implications` field (the codes whose
  applicability changed across snapshots) is computed under the wrong
  pack — every diff between snapshots looks like rules were added.
- The `engine_version` re-run guarantee (§8.15) becomes useless because
  pack skew silently masks engine skew.

Fix: load the engagement-bound pack:

```python
pack = load_pack_from_file(_PACKS_DIR / f"{eng.pack_version}.json")
```

(and surface `engine-version-skew` per §8.15 if `eng.engine_version !=
current_engine_commit()`).

---

### B-2. Engagement bundle silently drops `rule_pack.json` when cwd ≠ repo root

**Files:** `src/engagement_bundle.py:75`.

```python
candidate = Path("rule_packs") / f"{eng.pack_version}.json"
if candidate.exists():
    rule_pack = load_pack_from_file(candidate)
```

This is a cwd-relative path. `src/rule_pack.py:200` already defines
`_PACKS_DIR = Path(__file__).parent.parent / "rule_packs"` — the
bundle module did not use it.

Reproduced:

```bash
.venv/bin/python -c "
import os, tempfile, pathlib, zipfile, io
from src.engagement import EngagementStore, SnapshotSource
from src.identity import StubSSOProvider
from src.models import CapTable, Company, ShareClass, ShareClassType
from src.engagement_bundle import build_engagement_bundle

tmp = pathlib.Path(tempfile.mkdtemp())
store = EngagementStore(db_path=tmp/'e.db')
user = StubSSOProvider()._STUB_USER
eng = store.create_engagement(actor=user, client_id='c1',
    standard_of_value='ifrs13', pack_version='v2026.1.0', engine_version='abc')
ct = CapTable(company=Company(name='X'), share_classes=[
    ShareClass(name='C', type=ShareClassType.common, shares_outstanding=10)])
store.add_snapshot(actor=user, engagement_id=eng.id, expected_version=0,
    cap_table=ct, source=SnapshotSource.excel_upload, source_filename='x.xlsx')
os.chdir(tmp)
blob = build_engagement_bundle(store, eng.id)
with zipfile.ZipFile(io.BytesIO(blob)) as z:
    print('rule_pack.json in bundle?', 'rule_pack.json' in z.namelist())
"
# rule_pack.json in bundle? False
```

Consequences:

- The README inside the bundle (`engagement_bundle.py:158-212`) tells
  the offline auditor to *"Load `rule_pack.json` and `snapshots/<head>.json`"*.
  When this fails silently, the auditor cannot re-run the checklist.
- `manifest.json::files` will not list `rule_pack.json`, so a tamper-check
  alone does not flag the omission.
- Any deployment that launches Flask from `/var/run/qapita` or under
  `gunicorn --chdir /srv/qapita` ships broken bundles.

Fix: use `_PACKS_DIR` from `src/rule_pack.py`.

---

### B-3. `review → signed` transition skips the blocker-finding gate

**Files:** `src/engagement.py:295-311`, `src/engagement.py:637-684`.
SYSTEM_SPEC §3.2:

> `review → signed` — Triggered by partner sign-off. Allowed actors:
> `partner` only. **Refused if any blocker finding is unresolved.**

And §7.12 (out-of-scope refusals) re-asserts:

> Bypass of the blocker-finding gate on engagement sign-off or PDF memo
> generation. No "force" flag exists.

The implementation's `transition()` only checks the lifecycle table
(`_ALLOWED_TRANSITIONS`) and the permission (`_TRANSITION_PERMISSION`).
It does **not** load the head snapshot, run the bound pack, and refuse
on outstanding blockers. The only blocker-gate in the codebase lives in
`src/pdf_memo.py::_ensure_eligible` (correct for PDF generation but
unrelated to sign-off).

Repro (any engagement with an unresolved-blocker snapshot can be
transitioned to `signed` by a partner with no rejection):

```python
# Walk: open → review (analyst) → signed (partner) succeeds even when
# the head snapshot has an AD-MISSING-A blocker finding.
```

Severity: **blocker** because this is a load-bearing spec invariant
("the engagement is the legal artefact") and the spec explicitly forbids
a bypass mechanism.

Fix: in `transition()`, when `new_status == signed`, load the head
snapshot, run the bound rule pack, and refuse if any unresolved blocker
remains (matching the discard-by-resolution pattern in
`pdf_memo._ensure_eligible`). Use a new spec-aligned error code
`engagement-invalid-transition` with `blockers_unresolved` payload.

---

## 2. Majors

### M-1. `compute_subsequent_events` uses `list_snapshots[-1]` not `head_snapshot_id`

**Files:** `src/subsequent_events.py:107`, `:117`; `src/engagement.py:537-548`.

```python
snapshots = store.list_snapshots(engagement_id)
original = snapshots[0]
head = snapshots[-1]
```

`list_snapshots` orders by `(created_at, id)`. Under sub-second timing
ties, two snapshots can serialize their `created_at` to the same ISO
string; the tiebreaker is then UUID lexicographic — which is **not**
the actual chain order. The chain order is `superseded_by`; the
engagement separately tracks `head_snapshot_id`.

Repro (verified — bypassed `add_snapshot` to inject same `created_at`):

```
inserted A,B = ['1392963e-...', '0c3b5275-...']
list returns:  ['0c3b5275-...', '1392963e-...']
head_snapshot_id = '0c3b5275-...'
list[-1] == head: False
```

Consequence: when two snapshots tie on `created_at`, the memo's
"subsequent events" section diffs from `chain_head` against `original`
in the wrong direction, or picks the wrong "original" entirely. The
resolutions rollup is unaffected (it iterates all snapshots), but
`SubsequentEvent.description` strings will be inverted (`added` instead
of `removed`, etc.).

This is also a determinism-§8.10 violation for engagements that produce
multiple snapshots in a single second (e.g., a bulk-import path that
adds three snapshots in quick succession).

Fix: replace `head = snapshots[-1]` with
`head = store.get_snapshot(store.get_engagement(engagement_id).head_snapshot_id)`
and walk `superseded_by` backward for the original. Use `head_snapshot_id`
as the source of truth.

---

### M-2. Rule-pack effective-window contract violated in `rule_packs/*.json`

**Files:** `rule_packs/v2026.1.0.json`, `…/v2026.2.0.json`,
`…/v2026.3.0.json`, `…/v2026.4.0.json`; SYSTEM_SPEC §4.1.

Spec says:

> Adding or removing any rule creates a NEW rule pack version (semver
> bump per change category). **The previous pack's `effective_to` is set
> to the new pack's `effective_from − 1 day`.** The new pack becomes head.

All four packs ship with `effective_to: null`:

```
v2026.1.0  effective_from=2026-01-01  effective_to=None
v2026.2.0  effective_from=2026-06-01  effective_to=None
v2026.3.0  effective_from=2026-09-01  effective_to=None
v2026.4.0  effective_from=2026-12-01  effective_to=None
```

`is_effective_on(date(2026,12,15))` is `True` for **all four** packs.
`head_pack()` covers the bug by picking the max `effective_from`, but
any external consumer that filters via `is_effective_on` (e.g., a
future "which pack applied on 2026-07-01?" query) will see four
overlapping packs and have no deterministic answer.

Severity: major because the multi-pack-effective overlap is now a
silent ambiguity. The fix is data-only (close out the prior
`effective_to`) plus a load-time validator in `list_available_packs`
that refuses overlapping windows.

---

### M-3. Spec error codes drift across the route surface

**Files:** `src/engagement.py:89-128`, `src/engagement_routes.py` (broadly).

SYSTEM_SPEC §3.2 mandates the following error codes:

| Spec code | Implemented? | Where |
|---|---|---|
| `engagement-invalid-transition` | NO | impl uses `illegal-transition` (`engagement.py:115`) |
| `tenancy-violation` | NO | impl uses `permission-denied` everywhere |
| `role-not-permitted` | NO | impl uses `permission-denied` everywhere |
| `read-only-token` (§8.8) | NO | no magic-link role implemented |
| `token-expired` (§8.8) | NO | not implemented |
| `token-revoked` (§8.8) | NO | not implemented |
| `pdf-signed-immutable` (§3.4) | NO | only `pdf-blockers-outstanding`, `pdf-no-reviewer` |
| `engagement-version-conflict` (§8.12) | YES | `engagement.py:101` |

A Big-4 auditor parsing the error-code namespace will see a different
vocabulary from the spec. Either rename the implementation's codes to
match the spec, or amend §3.2 + §8.8 to record what the engine actually
emits.

---

### M-4. `signed → review` reopen and `partner → archived` lack spec amendments

**Files:** `src/engagement.py:298`, `:307`, `:309-310`; `src/identity.py:78-79`.

Implementation lifecycle table:

```python
_ALLOWED_TRANSITIONS = {
    EngagementStatus.open:     {EngagementStatus.review, EngagementStatus.archived},
    EngagementStatus.review:   {EngagementStatus.open,   EngagementStatus.signed},
    EngagementStatus.signed:   {EngagementStatus.review, EngagementStatus.archived},  # GAP-29
    EngagementStatus.archived: set(),
}
```

vs SYSTEM_SPEC §3.2:

- `open → review`: ✓
- `review → open`: ✓
- `review → signed`: ✓ (partner)
- `signed → archived`: spec says **"Allowed actors: system cron only."**
  Impl grants this to `partner` via `engagement.transition_to_archived`.
- `signed → review`: spec says **"All other transitions are refused with
  HTTP 409 engagement-invalid-transition."** Impl allows this for partner
  via "GAP-29 reopen" (mentioned in code, not in spec §8).
- `open → archived`: spec doesn't mention it. Impl allows it.

The implementation has clearly drifted forward (sensibly — auditors do
need reopen, partners do archive) but spec §8 was not amended with
a `8.18 GAP-29 partner reopen` clause. Two paths:

1. Append §8.18 to SYSTEM_SPEC.md describing the partner-reopen and
   partner-archive contract.
2. Roll back the impl to spec.

Choosing (1) is cheaper and matches operational reality. Either way,
this drift must be closed, not left as a comment.

---

### M-5. `_classify` in `subsequent_events.py` mis-categorises `voting_differential`

**Files:** `src/subsequent_events.py:46-82`.

`voting_differential` diffs land in "Share-class structure" instead of
their own bucket. Per SYSTEM_SPEC §3.4 the memo's per-section bullets
are derived from these categories; voting-rights changes get buried in
the "structure" bucket where reviewers will miss them, even though
"VOTING-DIFF" findings carry their own bucket in the checklist.

Reproduced:

```python
_classify(FieldDiff(path='share_classes[A].voting_differential',
                   change_type='modified', old_value=None, new_value='10x',
                   source_snapshot='RHS'))
# -> 'Share-class structure'  (expected: 'Voting / governance')
```

Cheap fix: insert `if ".voting_differential" in p: return "Voting / governance"`
before the `share_classes[` catch-all.

---

### M-6. `Engagement.valuation_date` accepts any string (incl. "not-a-date" and future)

**Files:** `src/engagement.py:139`.

```python
valuation_date: Optional[str] = None  # ISO date string, kept loose
```

SYSTEM_SPEC §3.2 schema: `valuation_date: date`. Implementation stores
free-form text. Repro:

```
Bogus date accepted: not-a-date
Future valuation_date accepted: 2099-12-31
```

A future date is a legitimate use case (forward-dated valuations exist).
"not-a-date" is not. The filter logic at `engagement_routes.py:254-263`
does string comparison (`>=`, `<=`) on these values, so a bogus string
will sort wherever Python places it and silently corrupt list filtering.

Fix: validate with `date.fromisoformat()` at the boundary (parse in the
route or constrain the field to a `date | None`). Document forward-dated
valuations as legal.

---

### M-7. `head_pack()` dev fallback ships every registered rule with version `v0.0.0-dev`

**Files:** `src/rule_pack.py:223-242`.

When no persisted pack is effective on the requested date (e.g., a
year far in the future, or a fresh checkout without rule_packs/),
`head_pack()` synthesises a pack containing every rule in
`_REGISTRY` and stamps it `v0.0.0-dev`. The version regex (`_PACK_VERSION_RE`)
accepts this string. An engagement created in this state binds to
`pack_version="v0.0.0-dev"` — which then makes the bundle path lookup
(`engagement_bundle.py:75`) fail silently because there's no
`rule_packs/v0.0.0-dev.json` to materialise.

Combined with B-2 above, the bundle ships **no** `rule_pack.json` and
no error fires. The audit deliverable is incomplete.

Fix: in `create_engagement`, refuse to bind to a `v0.0.0-dev` pack
unless an env var (`QAPITA_ALLOW_DEV_PACK=1`) is set. Production should
fail closed.

---

## 3. Minors

### m-1. Dead variable + dead imports

- `src/rate_limit.py:86-88`: `window_start = ...` is computed and never
  read. Looks like a leftover from an aborted sliding-window refactor.
- `src/engagement_routes.py:62`: `EngagementPackBinding` imported, never
  used. `EngagementPackBinding.create` is dead at the call-site level
  (never instantiated anywhere in `src/` or `app.py`).

### m-2. `_describe_lp` in `pdf_memo.py` reads `lp.multiple` as raw float

`src/pdf_memo.py:125` formats `f"{lp.multiple}x ..."`. A multiple of `1.0`
prints as `1.0x`; `2` prints `2x`. Inconsistent rendering depending on
parser input type. Minor presentational consistency.

### m-3. `_classify` order: `protective_provisions` lands inside an LP path

`src/subsequent_events.py:56`: the `"protective_provisions" in p` check
matches *any* path containing the literal substring, including
`share_classes[X].liquidation_preference.protective_provisions`
(hypothetical future field). Substring matching across the path is
fragile. Migrate to a sequence of prefix/regex anchors keyed off the
known schema.

### m-4. Currency symbol fallback table is incomplete

`src/parser.py:553`: fallback symbol map is `{USD, INR, SGD, EUR, GBP}`.
JPY (¥), KRW (₩), CNY (¥), AED (د.إ), NGN (₦), and any custom symbol
fall through to `$`. Number-parsing on line 321 already strips `¥`
and `£`, so the asymmetry is real: a JPY workbook parses correctly
but renders with a `$` sign throughout the memo and exports.

### m-5. DCF sidecar named-range vocabulary drifts from spec §5.3

`src/dcf_sidecar.py:10-19`:
- Spec: `share_count_<class>`, `lp_<class>`, `conversion_ratio_<class>`,
  `valuation_date`.
- Impl: `share_count_<>`, `lp_amount_<>`, `conv_ratio_<>`,
  `total_fully_diluted`. **No `valuation_date` named range exists.**

A DCF model in Excel built against the spec naming will fail to resolve.

### m-6. Module-load side effects in `app.py`

`app.py:66-71` constructs `SessionStore(_DB_PATH)`, `EngagementStore(...)`,
`ExportRateLimiter(...)` at import time, all pointing at `data/sessions.db`,
`data/engagements.db`, `data/export_limits.db`. Any test that imports
`app` (or that uses Flask's test client without overriding `app.config`)
will write to the on-disk production-ish DB. Test-isolation risk;
prefer lazy-construct or a `create_app(db_path=...)` factory.

### m-7. Bundle determinism is conformant but not visibly asserted

The bundle is deterministic in all payload files; only `manifest.json`
varies across runs (carve-out per §8.10). This was reproduced by
generating two bundles 1.1s apart — every payload file hashed equal,
manifest differed only on `generated_at`. Good. No bug here; calling
this out because the property isn't asserted in code anywhere outside
tests I cannot read.

---

## 4. Cross-module contract checks

Status legend: ✅ aligned, ⚠ aligned but fragile, ❌ broken.

| Caller | Callee | Contract | Status |
|---|---|---|---|
| `engagement_routes.memo` | `head_pack` | should be `eng.pack_version` per §4.1 | ❌ (B-1) |
| `engagement_routes.memo` | `compute_subsequent_events(pack=…)` | should be `eng.pack_version` | ❌ (B-1) |
| `engagement_bundle.build_engagement_bundle` | `Path("rule_packs")` | should use `_PACKS_DIR` | ❌ (B-2) |
| `EngagementStore.transition` | `pdf_memo._ensure_eligible` blocker contract | spec §3.2 says transition must enforce same gate | ❌ (B-3) |
| `subsequent_events.compute_subsequent_events` | `list_snapshots[-1]` | should use `head_snapshot_id` | ❌ (M-1) |
| `engagement_routes` | `engagement.EngagementError.error_code` | spec codes | ❌ (M-3) |
| `pdf_memo.render_pdf_memo` | `RulePack.rule_ids → rule_metadata` | provenance enumeration | ✅ |
| `Resolution.finding_code` | `Finding.code` | resolution discards by code | ✅ |
| `engagement.add_snapshot` | `Engagement.version` optimistic CC | atomic UPDATE + write_lock | ✅ |
| `engagement._append_audit_event` | hash-chain prev_hash | held under `_write_lock` | ✅ |
| `redact_snapshot_pii` | `Snapshot.load_cap_table()` | sentinel + redacted flag | ✅ |
| `engagement_routes._enforce_export_limit` | `_store()._append_audit_event` | bulk_export_alert edge-trigger | ✅ |
| `structured_diff.diff_snapshots` | `subsequent_events._classify` | path syntax matches | ⚠ (M-5) |
| `bundle README` recipe | `_compute_row_hash` | hash chain verifiable offline | ✅ (verified) |
| `bundle manifest` | `audit_head_hash` | matches recomputed tail | ✅ (verified) |
| `parser.Company` | `pdf_memo._money` | currency symbol display | ⚠ (m-4) |
| `Engagement.valuation_date` | spec `date` type | string-typed, unvalidated | ❌ (M-6) |
| `dcf_sidecar` named ranges | spec §5.3 vocabulary | drift | ❌ (m-5) |

---

## 5. End-to-end determinism review

I traced one full flow end-to-end and rebuilt the bundle twice 1.1s
apart:

1. `EngagementStore.create_engagement(client_id='c1', pack_version='v2026.1.0', engine_version='abc')`
2. `add_snapshot(cap_table=…, source=excel_upload)`
3. `build_engagement_bundle(store, eng.id)` ×2

Per-file equality of the two bundles:

```
audit_log.jsonl            equal
snapshots/<head>.json      equal
engagement.json            equal
rule_pack.json             equal (only when cwd is repo root; see B-2)
README.md                  equal
manifest.json              NOT equal  (manifest.generated_at differs)
```

This is the **documented** carve-out per §8.10. The README's offline
verification recipe was run end-to-end and validates the hash chain
against `manifest.audit_head_hash` correctly.

Identified determinism leaks:

- **L-1 (B-1):** Memo findings re-run under `head_pack()` not the
  engagement-bound pack. Same engagement → different findings as the
  rule pack evolves.
- **L-2 (M-1):** Snapshot list ordering breaks under same-microsecond
  inserts; `subsequent_events` then picks the wrong head/original.
- **L-3 (M-7):** Engagements bound to the synthesised dev pack ship
  no `rule_pack.json` regardless of cwd.
- **L-4:** `Engagement.valuation_date` accepts non-ISO strings (M-6),
  which sort non-deterministically under `>=` / `<=` filters.

Stripping the documented carve-outs (manifest.generated_at,
cover-sheet timestamp on PDFs, the `*Generated by …*` line in the
Markdown memo), the bundle for a Phase-0/2 engagement is byte-stable
**only when**: (a) the engagement-bound pack equals `head_pack()`, (b)
the cwd is the repo root, (c) no two snapshots share `created_at`.
That's a brittle envelope.

---

## 6. Spec drift table (across waves)

| Spec section | Implementation | Drift |
|---|---|---|
| §3.2 lifecycle transitions | impl adds `signed → review`, `signed/open → archived` for partner | major; spec §8 amendment owed |
| §3.2 error codes | impl uses `illegal-transition`, `permission-denied` blanket | major; rename or amend |
| §3.2 `valuation_date: date` | impl uses `Optional[str]` | minor data-validation gap |
| §3.2 `review→signed` blocker gate | not implemented in `transition()` | blocker |
| §3.4 `pdf-signed-immutable` | not implemented | minor (analyst-role gate for signed engagements) |
| §4.1 pack binding for memo runs | uses `head_pack()` | blocker (B-1) |
| §4.1 pack `effective_to` chain | all four packs `null` | major (M-2) |
| §4.2 `seniority_tier: (rank, sub_rank)` | impl uses two int fields `seniority_rank` + `seniority_sub_rank` | minor naming drift, semantics intact |
| §5.3 DCF sidecar named ranges | naming drift, `valuation_date` missing | minor (m-5) |
| §8.8 `token-*` error codes | not implemented | open gap (no magic-link role) |
| §8.13 redaction sentinel | matches spec | ✅ |
| §8.14 hash chain | matches spec | ✅ |
| §8.15 `engine-version-skew` banner | not implemented | open gap |
| §8.10 determinism carve-outs | conformant for bundle payload | ✅ |
| §8.17 export rate limiting | implemented with edge-trigger alert | ✅ |

---

## 7. Error-code inventory

Implementation-side codes (grepped from `src/engagement.py`,
`src/engagement_routes.py`, `src/pdf_memo.py`):

```
auth-required
bad-pagination
client-id-required
client-id-required-for-role
engagement-error
engagement-not-found
engagement-version-conflict
export-rate-limit
illegal-transition
immutable-violation
missing-expected-version
missing-redaction-fields
missing-resolution-fields
missing-status
no-file
no-snapshot
parse-failed
pdf-blockers-outstanding
pdf-error
pdf-no-reviewer
permission-denied
snapshot-redacted
unknown-status
unsupported-file-type
validation-failed
```

Spec-side codes from SYSTEM_SPEC §3.2, §3.4, §8.8, §8.12, §8.17:

```
auth-required               ← matches
engagement-version-conflict ← matches
export-rate-limit           ← matches
pdf-blockers-outstanding    ← matches
pdf-no-reviewer             ← matches
engagement-invalid-transition  ← MISSING (impl: illegal-transition)
role-not-permitted          ← MISSING
tenancy-violation           ← MISSING
read-only-token             ← MISSING
token-expired               ← MISSING
token-revoked               ← MISSING
pdf-signed-immutable        ← MISSING
rule-pack-expired           ← MISSING (no pack-expiry enforcement)
rule-pack-immutable         ← MISSING (no UPDATE protection on rule_pack)
```

No code is duplicated to mean two different things. The drift is
spec-codes → impl-codes (impl undercounts).

---

## 8. Things checked CLEAN

- **Hash-chain verification recipe in bundle README** — reproduced
  step-by-step; matches `_compute_row_hash` in `src/engagement.py:224-231`.
  Manifest's `audit_head_hash` equals the recomputed tail.
- **Concurrent memo+redact** — no race; redaction is atomic relative to
  `Snapshot.load_cap_table()`; verify_audit_log still passes after
  redaction.
- **Concurrent engagement-store + rate-limiter writes** — independent
  SQLite files, no shared lock contention; 300 concurrent ops produced
  zero errors.
- **ResourceWarning sweep** — 50× bundle build + audit + snapshot list
  with `-W error::ResourceWarning` produced no warnings; the BUG-005
  cursor-close fix holds.
- **Unicode survival** — Tamil class name, Devanagari + emoji class
  name, Arabic RTL company name, AED currency: parser → checklist →
  waterfall → structured_diff all worked. The structured-diff path
  preserves the unicode literally inside `share_classes[…]`.
- **Cross-version pack run** — engagement bound to `v2026.1.0` and
  manually re-run against `v2026.4.0` returned different findings (as
  expected) without breaking the engagement's hash chain. (See B-1
  for the bug: the *automatic* re-run uses the wrong pack.)
- **Zero-snapshot engagement bundle** — generates 2,888 bytes; no
  crash; `compute_subsequent_events` returns an empty rollup.
- **Time inversion** — engagement `created_at` in the future + snapshot
  `created_at` in the past does not break `verify_audit_log` (no
  temporal invariants enforced, which is fine).
- **Pari-passu invariants** — `preferred_seniority_tier_unique` +
  `pari_passu_groups_homogeneous_lp` model validators correctly refuse
  mixed-LP-type pari-passu, matching spec §4.2 + GAP-21.
- **Snapshot chain `superseded_by` linkage** — preserved end-to-end
  into the bundle's `snapshots/<id>.json` files.
- **Determinism of audit_log.jsonl** — bit-identical across two builds.
  `ts` strings are captured once at `_append_audit_event` and never
  recomputed.

---

## 9. Fix-now-vs-defer table

| ID | Severity | Fix complexity | Fix-now? |
|---|---|---|---|
| B-1 pack-binding ignored at memo time | blocker | 4 lines (load `_PACKS_DIR / f"{eng.pack_version}.json"`) | **Now.** Memo determinism is load-bearing. |
| B-2 bundle drops rule_pack.json on cwd≠root | blocker | 1 line (use `_PACKS_DIR`) | **Now.** Trivial. |
| B-3 `review→signed` skips blocker gate | blocker | ~20 lines in `transition()` | **Now.** Spec invariant. |
| M-1 subsequent_events picks wrong head | major | ~10 lines (use `head_snapshot_id`) | Now. |
| M-2 pack `effective_to` chain | major | data fix + 1 load-time validator | Now. Data-only. |
| M-3 error-code drift | major | rename ~6 codes or amend §3.2 | Coordinated with spec custodian; amend §3.2 cheaper. |
| M-4 signed→review reopen unamended | major | amend SYSTEM_SPEC §8.18 | Now (one paragraph). |
| M-5 voting_differential mis-classified | major (memo UX) | 2 lines | Now. |
| M-6 valuation_date unvalidated | major | 5 lines validator | Now. |
| M-7 dev-pack binding silent | major | guard in `create_engagement` | Now. |
| m-1 dead code | minor | delete | Now. |
| m-2 `_describe_lp` rendering | minor | format spec | Defer. |
| m-3 substring matching in `_classify` | minor | refactor | Defer. |
| m-4 currency symbol table | minor | extend dict | Now. |
| m-5 DCF sidecar naming | minor | rename + add `valuation_date` | Now (spec is normative). |
| m-6 `app.py` module-load side effects | minor | `create_app()` factory | Defer to the production-deploy hardening pass. |

**Cumulative fix budget for blockers + majors: ~80 LOC + one spec
amendment paragraph + one rule-pack data fix.** None of these are
re-architectures; they are integration-seam tightenings on top of work
the per-wave audits already validated.

---

*End of compiled system audit.*
