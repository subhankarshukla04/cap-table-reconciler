"""Engagement / snapshot / audit-event tests (SYSTEM_SPEC §3.2, §8.12, §8.13, §8.14).

Covers:
- Engagement creation + state machine transitions
- Snapshot immutability and superseded_by chain
- Resolution append-only behavior with required citation
- Audit-log hash chain integrity (GAP-05)
- Optimistic concurrency / version conflict (GAP-01)
- Role-based permission denials
- PDPA/GDPR redaction (GAP-03)
- Partner reopen of signed engagement (GAP-29)
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.engagement import (
    EngagementNotFound,
    EngagementStatus,
    EngagementStore,
    EngagementVersionConflict,
    IllegalStateTransition,
    PermissionDenied,
    SnapshotSource,
    _GENESIS_HASH,
)
from src.identity import Role, StaticUserProvider, User
from src.models import (
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


@pytest.fixture
def users():
    return {
        "analyst": User(id="u-1", email="a@x", role=Role.analyst, display_name="A"),
        "reviewer": User(id="u-2", email="r@x", role=Role.reviewer, display_name="R"),
        "partner": User(id="u-3", email="p@x", role=Role.partner, display_name="P"),
        "ro": User(id="u-4", email="ro@x", role=Role.read_only_auditor, display_name="RO"),
    }


def _ct() -> CapTable:
    return CapTable(
        company=Company(name="Demo Co"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
            ShareClass(
                name="A",
                type=ShareClassType.preferred,
                shares_outstanding=1000,
                issue_price=1.0,
                issue_date=date(2024, 1, 1),
                seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating
                ),
            ),
        ],
    )


# ---- Create + read ----------------------------------------------------------


def test_create_engagement_initial_state(store, users):
    eng = store.create_engagement(
        actor=users["analyst"],
        client_id="client-001",
        standard_of_value="ifrs13",
        pack_version="v2026.1.0",
        engine_version="abcd123",
    )
    assert eng.status == EngagementStatus.open
    assert eng.head_snapshot_id is None
    assert eng.version == 0
    assert eng.audit_head_hash != _GENESIS_HASH  # genesis audit_event already written


def test_read_only_auditor_cannot_create(store, users):
    with pytest.raises(PermissionDenied):
        store.create_engagement(
            actor=users["ro"],
            client_id="c",
            standard_of_value="ifrs13",
            pack_version="v2026.1.0",
            engine_version="x",
        )


def test_engagement_not_found(store):
    with pytest.raises(EngagementNotFound):
        store.get_engagement("nope")


# ---- Snapshots --------------------------------------------------------------


def test_add_snapshot_advances_version_and_head(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=users["analyst"],
        engagement_id=eng.id,
        expected_version=eng.version,
        cap_table=_ct(),
        source=SnapshotSource.excel_upload,
        source_filename="demo.xlsx",
        source_hash="deadbeef",
    )
    refreshed = store.get_engagement(eng.id)
    assert refreshed.head_snapshot_id == snap.id
    assert refreshed.version == eng.version + 1
    # CapTable round-trips.
    assert snap.load_cap_table().company.name == "Demo Co"


def test_multiple_snapshots_chain_via_superseded_by(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    s1 = store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    eng = store.get_engagement(eng.id)
    s2 = store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=eng.version, cap_table=_ct(), source=SnapshotSource.manual_edit,
    )
    s1_refreshed = store.get_snapshot(s1.id)
    assert s1_refreshed.superseded_by == s2.id
    assert s2.superseded_by is None


def test_snapshot_version_conflict_raises(store, users):
    """Two attempted snapshots with the same expected_version → second fails."""
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    with pytest.raises(EngagementVersionConflict) as excinfo:
        store.add_snapshot(
            actor=users["analyst"], engagement_id=eng.id,
            expected_version=0, cap_table=_ct(), source=SnapshotSource.manual_edit,
        )
    assert excinfo.value.error_code == "engagement-version-conflict"
    assert excinfo.value.http_status == 409


# ---- Resolutions ------------------------------------------------------------


def test_resolution_requires_citation(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    with pytest.raises(Exception, match="citation"):
        store.record_resolution(
            actor=users["analyst"], snapshot_id=snap.id,
            finding_code="G-AD-001-A", decision={}, citation="",
        )


def test_resolution_appears_in_list(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    res = store.record_resolution(
        actor=users["analyst"], snapshot_id=snap.id,
        finding_code="G-AD-001-A",
        decision={"variant": "broad_based_weighted_average"},
        citation="Charter §4.3(a)",
    )
    assert store.list_resolutions(snap.id) == [res]


# ---- Transitions ------------------------------------------------------------


def test_open_to_review_by_analyst(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    moved = store.transition(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=eng.version, new_status=EngagementStatus.review,
    )
    assert moved.status == EngagementStatus.review


def test_review_to_signed_requires_reviewer_or_partner(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    eng = store.transition(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=eng.version, new_status=EngagementStatus.review,
    )
    with pytest.raises(PermissionDenied):
        store.transition(
            actor=users["analyst"], engagement_id=eng.id,
            expected_version=eng.version, new_status=EngagementStatus.signed,
        )
    signed = store.transition(
        actor=users["reviewer"], engagement_id=eng.id,
        expected_version=eng.version, new_status=EngagementStatus.signed,
    )
    assert signed.status == EngagementStatus.signed


def test_partner_can_reopen_signed_to_review(store, users):  # GAP-29
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    eng = store.transition(actor=users["analyst"], engagement_id=eng.id,
                           expected_version=eng.version, new_status=EngagementStatus.review)
    eng = store.transition(actor=users["partner"], engagement_id=eng.id,
                           expected_version=eng.version, new_status=EngagementStatus.signed)
    reopened = store.transition(actor=users["partner"], engagement_id=eng.id,
                                 expected_version=eng.version,
                                 new_status=EngagementStatus.review)
    assert reopened.status == EngagementStatus.review


def test_archived_restorable_within_window(store, users):
    """W8.10: archived → open is now a partner-restore path within the
    90-day window. Originally the spec called `archived` terminal; the
    restore mechanism is a controlled exception with audit-log capture."""
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    eng = store.transition(actor=users["partner"], engagement_id=eng.id,
                           expected_version=eng.version, new_status=EngagementStatus.archived)
    assert eng.archived_at is not None
    assert eng.restore_eligibility_until is not None
    # Within window → restore succeeds.
    eng2 = store.transition(actor=users["partner"], engagement_id=eng.id,
                            expected_version=eng.version,
                            new_status=EngagementStatus.open)
    assert eng2.status == EngagementStatus.open
    # Archival metadata cleared by the transition.
    assert eng2.archived_at is None
    assert eng2.restore_eligibility_until is None


def test_archived_restore_refused_after_window(store, users):
    """W8.10: outside the restore window the transition raises."""
    from datetime import datetime, timedelta, timezone
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    eng = store.transition(actor=users["partner"], engagement_id=eng.id,
                           expected_version=eng.version, new_status=EngagementStatus.archived)
    # Manually backdate restore_eligibility_until to simulate window close.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store._connect() as conn:
        conn.execute(
            "UPDATE engagement SET restore_eligibility_until = ? WHERE id = ?",
            (past, eng.id),
        )
        conn.commit()
    with pytest.raises(IllegalStateTransition):
        store.transition(actor=users["partner"], engagement_id=eng.id,
                         expected_version=eng.version,
                         new_status=EngagementStatus.open)


# ---- Audit log + hash chain (GAP-05) ----------------------------------------


def test_audit_chain_verifies_on_clean_history(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    eng = store.transition(actor=users["analyst"], engagement_id=eng.id,
                           expected_version=1, new_status=EngagementStatus.review)
    ok, problem = store.verify_audit_log(eng.id)
    assert ok, problem


def test_audit_chain_detects_tampering(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    # Tamper: open a connection directly and modify a payload.
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE audit_event SET payload_json = '{\"tampered\":true}' "
            "WHERE engagement_id = ?",
            (eng.id,),
        )
    ok, problem = store.verify_audit_log(eng.id)
    assert not ok
    assert "row_hash mismatch" in problem


def test_audit_head_hash_advances_with_each_event(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    hash_1 = eng.audit_head_hash
    store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    hash_2 = store.get_engagement(eng.id).audit_head_hash
    assert hash_1 != hash_2 != _GENESIS_HASH


# ---- PDPA / GDPR redaction (GAP-03) ----------------------------------------


def test_only_partner_can_redact_pii(store, users):
    eng = store.create_engagement(
        actor=users["analyst"], client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=users["analyst"], engagement_id=eng.id,
        expected_version=0, cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    with pytest.raises(PermissionDenied):
        store.redact_snapshot_pii(
            actor=users["analyst"], snapshot_id=snap.id,
            request_reference="LEG-001", legal_basis="PDPA s.20",
        )
    redacted = store.redact_snapshot_pii(
        actor=users["partner"], snapshot_id=snap.id,
        request_reference="LEG-001", legal_basis="PDPA s.20",
    )
    assert redacted.redacted
    assert redacted.load_cap_table() is None
    ok, _ = store.verify_audit_log(eng.id)
    assert ok  # audit log integrity preserved despite the redaction
