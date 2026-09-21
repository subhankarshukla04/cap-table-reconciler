"""Portable engagement export bundle tests (W2.7 / GAP-08)."""

from __future__ import annotations

import hashlib
import json
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.engagement import EngagementStore, SnapshotSource, _GENESIS_HASH
from src.engagement_bundle import build_engagement_bundle
from src.identity import Role, User
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    s = EngagementStore(db_path=p)
    yield s
    p.unlink(missing_ok=True)


def _ct():
    return CapTable(
        company=Company(name="Bundle Co", currency="USD"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1_000),
            ShareClass(
                name="A",
                type=ShareClassType.preferred,
                shares_outstanding=1_000,
                issue_price=1.0,
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1_000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )


def _make_engagement(store):
    user = User(id="u-1", email="a@x", role=Role.analyst, display_name="A")
    eng = store.create_engagement(
        actor=user, client_id="c-1", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="abcd1234",
    )
    store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=eng.version,
        cap_table=_ct(), source=SnapshotSource.excel_upload,
        source_filename="demo.xlsx", source_hash="cafebabe",
        parse_report_json='{"cap_table_sheet":"Cap Table","warnings":[]}',
    )
    return eng


def test_bundle_contains_required_files(store):
    eng = _make_engagement(store)
    blob = build_engagement_bundle(store, eng.id)
    with ZipFile(BytesIO(blob)) as z:
        names = set(z.namelist())
    assert "manifest.json" in names
    assert "README.md" in names
    assert "engagement.json" in names
    assert "audit_log.jsonl" in names
    assert any(n.startswith("snapshots/") for n in names)
    assert any(n.startswith("parse_reports/") for n in names)


def test_manifest_records_sha256_per_file(store):
    eng = _make_engagement(store)
    blob = build_engagement_bundle(store, eng.id)
    with ZipFile(BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
        for name, expected_sha in manifest["files"].items():
            actual = hashlib.sha256(z.read(name)).hexdigest()
            assert actual == expected_sha, f"{name} hash mismatch"


def test_manifest_head_hash_matches_engagement(store):
    eng = _make_engagement(store)
    blob = build_engagement_bundle(store, eng.id)
    with ZipFile(BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
    fresh = store.get_engagement(eng.id)
    assert manifest["audit_head_hash"] == fresh.audit_head_hash
    assert manifest["audit_head_hash"] != _GENESIS_HASH


def test_audit_log_jsonl_round_trip_verifies_chain(store):
    """Pull the audit_log.jsonl out of the bundle and replay the hash chain
    by hand — that's the auditor's offline verification protocol."""
    eng = _make_engagement(store)
    blob = build_engagement_bundle(store, eng.id)
    with ZipFile(BytesIO(blob)) as z:
        lines = z.read("audit_log.jsonl").decode("utf-8").splitlines()
    prev = _GENESIS_HASH
    for line in lines:
        ev = json.loads(line)
        assert ev["prev_row_hash"] == prev
        # Recompute and compare.
        canonical = f"{ev['event_type']}|{ev['actor']}|{ev['ts']}|{ev['payload']}".encode()
        h = hashlib.sha256()
        h.update(prev.encode())
        h.update(b"\x00")
        h.update(canonical)
        assert h.hexdigest() == ev["row_hash"]
        prev = ev["row_hash"]
    # Compare to manifest.
    with ZipFile(BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["audit_head_hash"] == prev


def test_bundle_with_memo_pdf_includes_memo(store):
    eng = _make_engagement(store)
    fake_pdf = b"%PDF-1.4\n%fake\n"
    blob = build_engagement_bundle(store, eng.id, memo_pdf=fake_pdf)
    with ZipFile(BytesIO(blob)) as z:
        names = set(z.namelist())
        if "memo.pdf" in names:
            assert z.read("memo.pdf") == fake_pdf
    assert "memo.pdf" in names
