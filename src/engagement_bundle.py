"""Portable engagement export bundle (W2.7 / GAP-08).

Produces a zip containing every artefact a Big 4 auditor would need to
re-audit an engagement offline:

  bundle.zip
    ├── manifest.json                — bundle version, engagement id,
    │                                  generation timestamp, hash chain head,
    │                                  packed file list with SHA-256 each
    ├── README.md                    — what's in the bundle and how to
    │                                  verify the audit-log hash chain
    │                                  offline
    ├── engagement.json              — Engagement headers (status, pack,
    │                                  engine, version, head_snapshot_id)
    ├── rule_pack.json               — frozen rule pack effective at
    │                                  engagement open
    ├── snapshots/
    │     ├── <snapshot_id>.json     — full Snapshot record + cap_table_json
    │     └── ...
    ├── resolutions/
    │     ├── <resolution_id>.json
    │     └── ...
    ├── audit_log.jsonl              — one line per event with
    │                                  prev_row_hash + row_hash
    ├── memo.pdf                     — generated memo (if provided)
    └── parse_reports/
          ├── <snapshot_id>.json
          └── ...

Auditor offline verification recipe:
  1. Recompute audit_log SHA-256 hash chain.
  2. Confirm manifest hash-chain-head matches the tail of the recomputed
     chain.
  3. For each snapshot, compute SHA-256(cap_table_json) and check the
     manifest entry.
  4. Re-run the rule pack against the head cap_table and compare to
     the findings in memo.pdf or in the bundle's audit log entries.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .engagement import EngagementStore
from .rule_pack import RulePack, load_pack_from_file, load_engagement_bound_pack


BUNDLE_VERSION = "1.0"

# SD-AUD-B2: every zip entry mtime is pinned to the DOS epoch so the bundle
# is bit-for-bit reproducible across regenerations. Auditors recompute
# SHA-256 against the bundle file; wall-clock mtimes would break that.
_BUNDLE_EPOCH = (1980, 1, 1, 0, 0, 0)


def _zip_write(z: ZipFile, name: str, data: bytes) -> None:
    info = ZipInfo(filename=name, date_time=_BUNDLE_EPOCH)
    info.compress_type = ZIP_DEFLATED
    z.writestr(info, data)


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_engagement_bundle(
    store: EngagementStore,
    engagement_id: str,
    memo_pdf: Optional[bytes] = None,
    rule_pack: Optional[RulePack] = None,
) -> bytes:
    """Materialise the bundle as zip bytes. Caller decides what to do
    with the result (HTTP send_file, write to disk, push to S3)."""
    eng = store.get_engagement(engagement_id)
    snapshots = store.list_snapshots(engagement_id)
    audit_events = store.list_audit_events(engagement_id)

    if rule_pack is None:
        # W4.2: prefer the engagement-pinned bytes (set at create time).
        # Disk lookup is the fallback for legacy engagements created
        # before bound_pack_json existed.
        if eng.bound_pack_json:
            try:
                rule_pack = RulePack.model_validate_json(eng.bound_pack_json)
            except Exception:
                rule_pack = None
        if rule_pack is None:
            try:
                rule_pack = load_engagement_bound_pack(eng.pack_version)
            except (FileNotFoundError, ValueError):
                rule_pack = None

    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "engagement_id": engagement_id,
        # SD-AUD-B2: pin to engagement.created_at (stored, immutable)
        # instead of wall-clock so the bundle is bit-stable.
        "generated_at": eng.created_at.astimezone(timezone.utc).isoformat(),
        "audit_head_hash": eng.audit_head_hash,
        "engagement_version": eng.version,
        "pack_version": eng.pack_version,
        "engine_version": eng.engine_version,
        "files": {},
    }

    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        eng_bytes = eng.model_dump_json(indent=2).encode("utf-8")
        _zip_write(z, "engagement.json", eng_bytes)
        manifest["files"]["engagement.json"] = _sha256_hex(eng_bytes)

        if rule_pack is not None:
            rp_bytes = rule_pack.model_dump_json(indent=2).encode("utf-8")
            _zip_write(z, "rule_pack.json", rp_bytes)
            manifest["files"]["rule_pack.json"] = _sha256_hex(rp_bytes)

        for snap in snapshots:
            # SD-AUD-W7-M4 (sub-finding of W7-B1): redacted snapshots must
            # ship into the bundle with PII-bearing fields zeroed. The DB
            # UPDATE now does this on redaction, but the bundle is the
            # artifact a Big-4 auditor stores OUTSIDE the system — every
            # consumer applies the safe accessors as defence in depth.
            if snap.redacted:
                snap = snap.model_copy(update={
                    "change_note": None,
                    "source_filename": None,
                    "created_by": "[redacted]",  # W8.6
                })
            blob = snap.model_dump_json(indent=2).encode("utf-8")
            name = f"snapshots/{snap.id}.json"
            _zip_write(z, name, blob)
            manifest["files"][name] = _sha256_hex(blob)
            if snap.parse_report_json:
                pr_name = f"parse_reports/{snap.id}.json"
                pr_bytes = snap.parse_report_json.encode("utf-8")
                _zip_write(z, pr_name, pr_bytes)
                manifest["files"][pr_name] = _sha256_hex(pr_bytes)
            for res in store.list_resolutions(snap.id):
                res_name = f"resolutions/{res.id}.json"
                res_bytes = res.model_dump_json(indent=2).encode("utf-8")
                _zip_write(z, res_name, res_bytes)
                manifest["files"][res_name] = _sha256_hex(res_bytes)

        log_lines = []
        for ev in audit_events:
            log_lines.append(json.dumps({
                "id": ev.id,
                "engagement_id": ev.engagement_id,
                "event_type": ev.event_type.value,
                "actor": ev.actor,
                "ts": ev.ts.isoformat(),
                "payload": ev.payload_json,
                "prev_row_hash": ev.prev_row_hash,
                "row_hash": ev.row_hash,
            }, sort_keys=True))
        log_blob = ("\n".join(log_lines) + ("\n" if log_lines else "")).encode("utf-8")
        _zip_write(z, "audit_log.jsonl", log_blob)
        manifest["files"]["audit_log.jsonl"] = _sha256_hex(log_blob)

        if memo_pdf is not None:
            _zip_write(z, "memo.pdf", memo_pdf)
            manifest["files"]["memo.pdf"] = _sha256_hex(memo_pdf)

        readme = _readme_text(engagement_id)
        readme_bytes = readme.encode("utf-8")
        _zip_write(z, "README.md", readme_bytes)
        manifest["files"]["README.md"] = _sha256_hex(readme_bytes)

        manifest_blob = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        _zip_write(z, "manifest.json", manifest_blob)

    return buf.getvalue()


def _readme_text(engagement_id: str) -> str:
    return f"""# Engagement Bundle — {engagement_id[:8]}

This is a portable, offline-verifiable snapshot of a Cap Table Reconciler
engagement. Big 4 auditors can re-verify the work without access to the
live system.

## Contents

  engagement.json      — engagement headers, status, version, hash-chain head
  rule_pack.json       — frozen rule pack at engagement open
  snapshots/<id>.json  — every cap-table snapshot, immutable
  resolutions/<id>.json — every analyst resolution with citation
  parse_reports/<id>.json — parse-time warnings + column mapping
  audit_log.jsonl      — one line per audit event with hash chain
  memo.pdf             — generated audit memo (if generated before export)
  manifest.json        — SHA-256 of every file above for tamper detection

## Verifying the hash chain (offline)

The audit log is hash-chained per row using SHA-256:

    row_hash = SHA256(prev_row_hash || canonical_payload)

where canonical_payload = event_type|actor|ts_iso|payload_json (payload_json
is itself canonical: sort_keys=True, separators=(',', ':')).

Genesis hash: 64 zero hex chars.

Recipe:
  1. Read `audit_log.jsonl` line by line.
  2. Start `prev = "00" * 32`.
  3. For each event, recompute SHA-256(prev || "\\x00" || canonical) and
     verify it equals the stored row_hash. (The "\\x00" separator between
     prev_hash and canonical payload mirrors the engine's `_compute_row_hash`
     implementation in src/engagement.py.)
  4. Set `prev = stored row_hash` and move to the next event.
  5. The final event's row_hash MUST equal `manifest.audit_head_hash`.

If any step fails, the engagement has been tampered with after generation.

## Re-running the rule pack offline

  1. Load `rule_pack.json` and `snapshots/<head>.json`.
  2. Parse the snapshot's `cap_table_json` into a CapTable model.
  3. Run the pack's rules in the listed order.
  4. Compare findings to `audit_log.jsonl` entries of type
     `resolution_recorded` and the included memo.

## Re-running the engine

The bundle does NOT contain the engine source. Pin the engine to
`engagement.json::engine_version` (a git short SHA from this repo) to
guarantee bit-equivalent re-runs per SYSTEM_SPEC §8.10 determinism
carve-outs.
"""


def write_engagement_bundle_to_disk(
    store: EngagementStore,
    engagement_id: str,
    output_path: Path,
    memo_pdf: Optional[bytes] = None,
    rule_pack: Optional[RulePack] = None,
) -> Path:
    blob = build_engagement_bundle(store, engagement_id, memo_pdf, rule_pack)
    output_path.write_bytes(blob)
    return output_path
