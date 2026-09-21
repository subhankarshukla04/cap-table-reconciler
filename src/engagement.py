"""Engagement / snapshot / audit-event data model (SYSTEM_SPEC §3.2).

Implements the production data layer:

  - `engagement` (mutable headers + lifecycle state)
  - `snapshot` (immutable cap-table states, linked via `superseded_by`)
  - `resolution` (append-only analyst decisions on findings)
  - `audit_event` (append-only with per-engagement hash chain — GAP-05)

Cross-cutting:
  - GAP-01 optimistic concurrency: every engagement carries a `version`;
    mutations require `expected_version` and raise EngagementVersionConflict
    (HTTP 409) on mismatch.
  - GAP-03 PDPA/GDPR right-of-erasure: snapshots can be redacted (replaces
    payload in place with a sentinel) while the audit log preserves the
    redaction event.
  - GAP-05 hash chain: each audit_event row records SHA-256(prev_hash ||
    canonical_payload). The current head is mirrored on the engagement row
    as `audit_head_hash`.
  - GAP-07 engine-version: every engagement_pack_binding row carries the
    engine commit SHA at bind time.
  - GAP-29 subsequent-events reopen: partners can transition signed -> review
    via `engagement.transition_signed_to_review`.

Architecture choice: a single `EngagementStore` class, dict-of-engagements
in-memory cache backed by SQLite, no auto-UPDATE on snapshots/resolutions/
audit_events. The store is the gate; any direct SQL UPDATE on those tables
from outside this module is a bug and will be caught by the structural
review.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .identity import User, can
from .models import CapTable


# ---- Enums ------------------------------------------------------------------


class EngagementStatus(str, Enum):
    open = "open"
    review = "review"
    signed = "signed"
    archived = "archived"


class SnapshotSource(str, Enum):
    excel_upload = "excel_upload"
    qapita_pull = "qapita_pull"
    manual_edit = "manual_edit"
    resolution = "resolution"
    redaction = "redaction"  # GAP-03


class AuditEventType(str, Enum):
    engagement_created = "engagement_created"
    snapshot_added = "snapshot_added"
    resolution_recorded = "resolution_recorded"
    transition = "transition"
    pii_redacted = "pii_redacted"
    auditor_token_revoked = "auditor_token_revoked"
    bulk_export_alert = "bulk_export_alert"  # GAP-40
    compute_burst_alert = "compute_burst_alert"  # SD-AUD-M2
    snapshot_diff_exported = "snapshot_diff_exported"  # W7.6
    opm_backsolve_run = "opm_backsolve_run"  # W9.2


# ---- Exceptions -------------------------------------------------------------


class EngagementError(Exception):
    """Base for any engagement-store error.

    Subclasses correspond to spec error codes in SYSTEM_SPEC §3.2.
    """

    error_code: str = "engagement-error"
    http_status: int = 400


class EngagementNotFound(EngagementError):
    error_code = "engagement-not-found"
    http_status = 404


class SnapshotNotFound(EngagementError):
    """SD-AUD-W7-m6: dedicated error code so callers don't see the
    generic `engagement-error` 400 catch-all when a snapshot id is bad."""
    error_code = "snapshot-not-found"
    http_status = 404


class EngagementVersionConflict(EngagementError):
    """GAP-01 / SYSTEM_SPEC §8.12. HTTP 409."""

    error_code = "engagement-version-conflict"
    http_status = 409

    def __init__(self, engagement_id: str, expected: int, current: int):
        super().__init__(
            f"engagement {engagement_id}: expected version {expected}, "
            f"current is {current}"
        )
        self.engagement_id = engagement_id
        self.expected = expected
        self.current = current


class IllegalStateTransition(EngagementError):
    # M-3 fix (compiled system audit): rename to match SPEC §3.2 exactly.
    error_code = "engagement-invalid-transition"
    http_status = 409


class BlockerFindingsOutstanding(EngagementError):
    """B-3 fix (compiled system audit): review→signed must refuse
    when the head snapshot has unresolved blocker findings (SPEC §3.2,
    §7.12 — no force-flag allowed).
    """
    error_code = "engagement-blockers-unresolved"
    http_status = 409


class PermissionDenied(EngagementError):
    error_code = "permission-denied"
    http_status = 403


class ImmutableViolation(EngagementError):
    """Raised if anything tries to UPDATE a snapshot or audit_event row."""

    error_code = "immutable-violation"
    http_status = 500


# ---- Pydantic models --------------------------------------------------------


from datetime import date as _date_type  # local alias; module-top `date` not imported


class Engagement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    client_id: str
    # W4.5 (closes audit M-6): typed date instead of free-form string.
    # The boundary validator accepts ISO date strings or `date` objects;
    # garbage like "not-a-date" is refused at construction.
    valuation_date: Optional[_date_type] = None
    standard_of_value: str  # "ifrs13" | "asc820" | "sec409a" | "ifrs2"
    status: EngagementStatus
    pack_version: str
    engine_version: str
    head_snapshot_id: Optional[str] = None
    audit_head_hash: str  # SHA-256 hex, 64 chars, all zeros at genesis
    version: int = Field(default=0, ge=0)
    created_by: str
    created_at: datetime
    # W4.2 (closes W2-AUDIT M4): pack JSON bytes pinned at create time.
    # Lets bundle export ship a self-contained pack copy without needing
    # to find the file on disk. Optional for backward compat with rows
    # created before this column existed.
    bound_pack_json: Optional[str] = None
    # W8.10: archival lifecycle metadata. Both are NULL for engagements
    # that haven't been archived. When status transitions TO `archived`
    # the store stamps `archived_at = now` and
    # `restore_eligibility_until = now + 90 days` atomically with the
    # status change. Partner can restore within the window;
    # hard-delete CLI cleans up after the window passes.
    archived_at: Optional[datetime] = None
    restore_eligibility_until: Optional[datetime] = None

    @field_validator("valuation_date", mode="before")
    @classmethod
    def _parse_iso_date(cls, v):
        """Accept None, date, datetime, or ISO-formatted string.

        Order matters: datetime is a SUBCLASS of date, so the datetime
        check must come first or `isinstance(v, date)` would match it
        and bypass the `.date()` coercion (W4-EDGE finding).
        """
        if v is None:
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, _date_type):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                return _date_type.fromisoformat(s)
            except ValueError as e:
                raise ValueError(
                    f"valuation_date {v!r} is not a valid ISO date: {e}"
                )
        raise TypeError(f"valuation_date must be None, date, or ISO string; got {type(v).__name__}")


class Snapshot(BaseModel):
    """Immutable. Created by the store; never UPDATE-d."""

    model_config = ConfigDict(extra="forbid")

    id: str
    engagement_id: str
    source: SnapshotSource
    source_filename: Optional[str] = None
    source_hash: Optional[str] = None  # SHA-256 of the source bytes
    cap_table_json: str  # serialized CapTable (or {"_redacted": true,...})
    parse_report_json: Optional[str] = None
    superseded_by: Optional[str] = None  # next snapshot's id, or None
    created_by: str
    created_at: datetime
    redacted: bool = False  # GAP-03
    # W7.4: analyst-supplied "why did this change" note. Set at upload time
    # via the form; surfaces in the snapshot timeline and the N-way diff
    # header so the next analyst (or auditor) reads the rationale before
    # the numbers. Optional — legacy snapshots keep working.
    change_note: Optional[str] = None

    def load_cap_table(self) -> Optional[CapTable]:
        """Returns the parsed CapTable, or None if this snapshot is redacted."""
        if self.redacted:
            return None
        data = json.loads(self.cap_table_json)
        if isinstance(data, dict) and data.get("_redacted"):
            return None
        return CapTable.model_validate(data)

    def safe_change_note(self) -> Optional[str]:
        """SD-AUD-W7-B1: defence-in-depth. Even after the redaction
        UPDATE zeroes change_note in the DB, this helper guarantees no
        rendering surface ever shows the field on a redacted snapshot —
        any future regression that misses the UPDATE (e.g. an in-memory
        Snapshot built before redaction landed) still renders blank."""
        return None if self.redacted else self.change_note

    def safe_source_filename(self) -> Optional[str]:
        """Same posture as `safe_change_note` for the filename column."""
        return None if self.redacted else self.source_filename

    def safe_created_by(self) -> str:
        """W8.6 / closes wave-7 m-W7-4. Mask the original uploader's id
        from rendering surfaces of a redacted snapshot. The DB still
        carries the value (audit log needs it); only the user-facing
        view sanitises."""
        return "[redacted]" if self.redacted else self.created_by


class Resolution(BaseModel):
    """Append-only."""

    model_config = ConfigDict(extra="forbid")

    id: str
    snapshot_id: str
    finding_code: str
    decision_json: str
    citation: str  # required, non-empty
    resolved_by: str
    resolved_at: datetime


class AuditEvent(BaseModel):
    """Append-only with per-engagement hash chain (GAP-05)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    engagement_id: str
    event_type: AuditEventType
    payload_json: str  # canonical JSON
    actor: str  # user.id
    ts: datetime
    prev_row_hash: str  # 64-char hex
    row_hash: str  # SHA-256(prev_row_hash || canonical_payload)


# ---- Hash chain helper ------------------------------------------------------


_GENESIS_HASH = "0" * 64


def _canonical_payload(
    event_type: str, payload_json: str, actor: str, ts_iso: str
) -> bytes:
    """Canonical bytes for the per-row hash.

    Field order is fixed; payload_json is assumed already canonical (the
    caller produces it via json.dumps(sort_keys=True)).
    """
    return f"{event_type}|{actor}|{ts_iso}|{payload_json}".encode("utf-8")


def _compute_row_hash(
    prev_row_hash: str, event_type: str, payload_json: str, actor: str, ts_iso: str
) -> str:
    h = hashlib.sha256()
    h.update(prev_row_hash.encode("utf-8"))
    h.update(b"\x00")
    h.update(_canonical_payload(event_type, payload_json, actor, ts_iso))
    return h.hexdigest()


# ---- The engagement store ---------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS engagement (
    id                       TEXT PRIMARY KEY,
    client_id                TEXT NOT NULL,
    valuation_date           TEXT,
    standard_of_value        TEXT NOT NULL,
    status                   TEXT NOT NULL,
    pack_version             TEXT NOT NULL,
    engine_version           TEXT NOT NULL,
    head_snapshot_id         TEXT,
    audit_head_hash          TEXT NOT NULL,
    version                  INTEGER NOT NULL DEFAULT 0,
    created_by               TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    -- W4.2: bound pack JSON bytes pinned at create time. Closes the
    -- "rule_packs/*.json got pruned post-create" failure mode and lets
    -- the bundle ship a self-contained pack copy without disk lookup.
    bound_pack_json          TEXT,
    -- W8.10: archival lifecycle. Both NULL until status moves to archived.
    archived_at              TEXT,
    restore_eligibility_until TEXT
);

CREATE TABLE IF NOT EXISTS snapshot (
    id                       TEXT PRIMARY KEY,
    engagement_id            TEXT NOT NULL REFERENCES engagement(id),
    source                   TEXT NOT NULL,
    source_filename          TEXT,
    source_hash              TEXT,
    cap_table_json           TEXT NOT NULL,
    parse_report_json        TEXT,
    superseded_by            TEXT,
    created_by               TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    redacted                 INTEGER NOT NULL DEFAULT 0,
    -- W7.4: analyst's "why did this change" note. Idempotent ALTER below
    -- migrates legacy DBs (which have all other columns but not this one).
    change_note              TEXT
);

CREATE TABLE IF NOT EXISTS resolution (
    id                       TEXT PRIMARY KEY,
    snapshot_id              TEXT NOT NULL REFERENCES snapshot(id),
    finding_code             TEXT NOT NULL,
    decision_json            TEXT NOT NULL,
    citation                 TEXT NOT NULL,
    resolved_by              TEXT NOT NULL,
    resolved_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_event (
    id                       TEXT PRIMARY KEY,
    engagement_id            TEXT NOT NULL REFERENCES engagement(id),
    event_type               TEXT NOT NULL,
    payload_json             TEXT NOT NULL,
    actor                    TEXT NOT NULL,
    ts                       TEXT NOT NULL,
    prev_row_hash            TEXT NOT NULL,
    row_hash                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_snapshot_engagement ON snapshot(engagement_id);
CREATE INDEX IF NOT EXISTS ix_audit_engagement_ts ON audit_event(engagement_id, ts);
CREATE INDEX IF NOT EXISTS ix_resolution_snapshot ON resolution(snapshot_id);
"""


# W8.10: archival restore window. Engagements transitioned to `archived`
# can be restored by a partner within this many days; afterwards the
# hard-delete CLI cascades them. Hard-coded today; Evelyn picks the
# actual production number.
ARCHIVAL_RESTORE_DAYS = 90


# Allowed lifecycle transitions per SYSTEM_SPEC §3.2.
# W8.10: archived → open is now a partner-only restore path (within the
# restore window — enforced by transition() and the restore route).
_ALLOWED_TRANSITIONS: dict[EngagementStatus, set[EngagementStatus]] = {
    EngagementStatus.open: {EngagementStatus.review, EngagementStatus.archived},
    EngagementStatus.review: {EngagementStatus.open, EngagementStatus.signed},
    EngagementStatus.signed: {EngagementStatus.review, EngagementStatus.archived},  # GAP-29 reopen
    EngagementStatus.archived: {EngagementStatus.open},  # restore
}


# Map transition (from, to) to the permission action required.
_TRANSITION_PERMISSION: dict[tuple[EngagementStatus, EngagementStatus], str] = {
    (EngagementStatus.open, EngagementStatus.review): "engagement.transition_open_to_review",
    (EngagementStatus.review, EngagementStatus.signed): "engagement.transition_review_to_signed",
    (EngagementStatus.signed, EngagementStatus.review): "engagement.transition_signed_to_review",
    (EngagementStatus.review, EngagementStatus.open): "engagement.transition_review_to_open",
    (EngagementStatus.open, EngagementStatus.archived): "engagement.transition_to_archived",
    (EngagementStatus.signed, EngagementStatus.archived): "engagement.transition_to_archived",
    (EngagementStatus.archived, EngagementStatus.open): "engagement.restore_archived",  # W8.10
}


@dataclass
class EngagementStore:
    db_path: Path
    # Process-local lock — protects the engagement-row UPDATE + the
    # audit-event hash-chain append from interleaving (B1, B2, B3 fixes
    # from CODE_AUDIT_WAVE_2). For multi-process / distributed
    # deployments, replace with a row-level DB lock or a distributed
    # primitive. The lock is intentionally process-local because the
    # default SQLite path is single-process anyway.
    _write_lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)
            # W4.2 idempotent migration: ensure bound_pack_json column
            # exists on older DBs. W4-AUDIT m-3: tolerate the race when
            # multiple processes call __post_init__ simultaneously —
            # SQLite serialises ALTER, but only the first wins; the
            # losers get OperationalError "duplicate column name", which
            # is benign here (the column already exists).
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(engagement)")}
            if "bound_pack_json" not in cols:
                try:
                    conn.execute("ALTER TABLE engagement ADD COLUMN bound_pack_json TEXT")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
            # W8.10 idempotent migration: archival lifecycle columns.
            for col_name in ("archived_at", "restore_eligibility_until"):
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE engagement ADD COLUMN {col_name} TEXT")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e).lower():
                            raise
            # SD-AUD-W8-m6: backfill legacy archived engagements that
            # predate the W8.10 columns. Without this, such rows have
            # `status = 'archived'` but `restore_eligibility_until IS
            # NULL` — transition() treats NULL as expired (refuses
            # restore) AND hard_delete_expired_archived skips them
            # (`AND restore_eligibility_until IS NOT NULL`). Stranded
            # forever. Backfill: archived_at ← created_at, restore_until
            # ← created_at + ARCHIVAL_RESTORE_DAYS. One-shot, idempotent
            # (subsequent runs find no rows to update because the
            # columns are now populated).
            rows = conn.execute(
                "SELECT id, created_at FROM engagement "
                "WHERE status = 'archived' AND archived_at IS NULL"
            ).fetchall()
            for row in rows:
                try:
                    base = datetime.fromisoformat(row["created_at"])
                except (TypeError, ValueError):
                    base = datetime.now(timezone.utc)
                restore_until = base + timedelta(days=ARCHIVAL_RESTORE_DAYS)
                conn.execute(
                    "UPDATE engagement SET archived_at = ?, "
                    "restore_eligibility_until = ? WHERE id = ?",
                    (base.isoformat(), restore_until.isoformat(), row["id"]),
                )
            # W7.4 idempotent migration: snapshot.change_note column.
            snap_cols = {row["name"] for row in conn.execute("PRAGMA table_info(snapshot)")}
            if "change_note" not in snap_cols:
                try:
                    conn.execute("ALTER TABLE snapshot ADD COLUMN change_note TEXT")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- Create / read --------------------------------------------------

    def create_engagement(
        self,
        actor: User,
        client_id: str,
        standard_of_value: str,
        pack_version: str,
        engine_version: str,
        valuation_date: Optional[_date_type | str] = None,
    ) -> Engagement:
        if not can(actor, "engagement.create"):
            raise PermissionDenied(f"{actor.role} cannot engagement.create")

        eng_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        # W4.2: load the bound pack JSON bytes at create time. Failure
        # to load is fatal — engagements must always bind to a real
        # persistable pack. Dev-only v0.0.0-dev path is gated by env var.
        from .rule_pack import load_engagement_bound_pack
        try:
            bound_pack = load_engagement_bound_pack(pack_version)
            bound_pack_json = bound_pack.model_dump_json()
        except (FileNotFoundError, ValueError) as e:
            raise EngagementError(
                f"cannot create engagement bound to {pack_version!r}: {e}"
            )
        eng = Engagement(
            id=eng_id,
            client_id=client_id,
            valuation_date=valuation_date,
            standard_of_value=standard_of_value,
            status=EngagementStatus.open,
            pack_version=pack_version,
            engine_version=engine_version,
            head_snapshot_id=None,
            audit_head_hash=_GENESIS_HASH,
            version=0,
            created_by=actor.id,
            created_at=now,
            bound_pack_json=bound_pack_json,
        )
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """INSERT INTO engagement
                   (id, client_id, valuation_date, standard_of_value, status,
                    pack_version, engine_version, head_snapshot_id,
                    audit_head_hash, version, created_by, created_at,
                    bound_pack_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    eng.id,
                    eng.client_id,
                    eng.valuation_date.isoformat() if eng.valuation_date else None,
                    eng.standard_of_value,
                    eng.status.value,
                    eng.pack_version,
                    eng.engine_version,
                    eng.head_snapshot_id,
                    eng.audit_head_hash,
                    eng.version,
                    eng.created_by,
                    eng.created_at.isoformat(),
                    eng.bound_pack_json,
                ),
            )
        # Record genesis audit event.
        self._append_audit_event(
            engagement_id=eng.id,
            event_type=AuditEventType.engagement_created,
            payload={
                "client_id": client_id,
                "standard_of_value": standard_of_value,
                "pack_version": pack_version,
                "engine_version": engine_version,
            },
            actor=actor,
        )
        return self.get_engagement(eng.id)

    def get_engagement(self, engagement_id: str) -> Engagement:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM engagement WHERE id = ?", (engagement_id,)
            ).fetchone()
        if row is None:
            raise EngagementNotFound(engagement_id)
        return self._row_to_engagement(row)

    def list_engagements(self, client_id: Optional[str] = None) -> list[Engagement]:
        sql = "SELECT * FROM engagement"
        params: tuple = ()
        if client_id is not None:
            sql += " WHERE client_id = ?"
            params = (client_id,)
        sql += " ORDER BY created_at DESC"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_engagement(r) for r in rows]

    def _row_to_engagement(self, row: sqlite3.Row) -> Engagement:
        # bound_pack_json may be missing on legacy rows; handle gracefully
        keys = row.keys()
        bound_pack = row["bound_pack_json"] if "bound_pack_json" in keys else None
        # W8.10: archival columns are nullable; legacy rows return None.
        archived_at_str = row["archived_at"] if "archived_at" in keys else None
        restore_until_str = (
            row["restore_eligibility_until"]
            if "restore_eligibility_until" in keys else None
        )
        archived_at = datetime.fromisoformat(archived_at_str) if archived_at_str else None
        restore_until = datetime.fromisoformat(restore_until_str) if restore_until_str else None
        raw_vdate = row["valuation_date"]
        try:
            return Engagement(
                id=row["id"],
                client_id=row["client_id"],
                valuation_date=raw_vdate,
                standard_of_value=row["standard_of_value"],
                status=EngagementStatus(row["status"]),
                pack_version=row["pack_version"],
                engine_version=row["engine_version"],
                head_snapshot_id=row["head_snapshot_id"],
                audit_head_hash=row["audit_head_hash"],
                version=row["version"],
                created_by=row["created_by"],
                created_at=datetime.fromisoformat(row["created_at"]),
                bound_pack_json=bound_pack,
                archived_at=archived_at,
                restore_eligibility_until=restore_until,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "engagement %s has non-ISO valuation_date %r; coerced to None (%s)",
                row["id"], row["valuation_date"], exc,
            )
            return Engagement(
                id=row["id"],
                client_id=row["client_id"],
                valuation_date=None,
                standard_of_value=row["standard_of_value"],
                status=EngagementStatus(row["status"]),
                pack_version=row["pack_version"],
                engine_version=row["engine_version"],
                head_snapshot_id=row["head_snapshot_id"],
                audit_head_hash=row["audit_head_hash"],
                version=row["version"],
                created_by=row["created_by"],
                created_at=datetime.fromisoformat(row["created_at"]),
                bound_pack_json=bound_pack,
                archived_at=archived_at,
                restore_eligibility_until=restore_until,
            )

    # ---- Snapshots (immutable) -----------------------------------------

    def add_snapshot(
        self,
        actor: User,
        engagement_id: str,
        expected_version: int,
        cap_table: CapTable,
        source: SnapshotSource,
        source_filename: Optional[str] = None,
        source_hash: Optional[str] = None,
        parse_report_json: Optional[str] = None,
        change_note: Optional[str] = None,  # W7.4
    ) -> Snapshot:
        if not can(actor, "engagement.add_snapshot"):
            raise PermissionDenied(f"{actor.role} cannot engagement.add_snapshot")

        snap_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        ct_json = cap_table.model_dump_json()

        # B2 fix: hold the write lock across the optimistic-concurrency
        # check + the UPDATE so concurrent callers can't both pass the
        # `expected_version` test. The conditional UPDATE inside the
        # transaction provides defence in depth — even if a future
        # refactor removes the lock, the rowcount check still catches
        # the race.
        with self._write_lock:
            eng = self.get_engagement(engagement_id)
            if eng.version != expected_version:
                raise EngagementVersionConflict(
                    engagement_id, expected_version, eng.version,
                )
            with closing(self._connect()) as conn, conn:
                # Atomic conditional UPDATE: only succeeds if version
                # still matches what we read above. rowcount == 0 means
                # we lost the race despite the lock (which is impossible
                # in a single process — but we check anyway).
                cur = conn.execute(
                    "UPDATE engagement SET head_snapshot_id = ?, "
                    "version = version + 1 "
                    "WHERE id = ? AND version = ?",
                    (snap_id, engagement_id, expected_version),
                )
                if cur.rowcount != 1:
                    raise EngagementVersionConflict(
                        engagement_id, expected_version,
                        self.get_engagement(engagement_id).version,
                    )
                # Insert the new snapshot after the version is reserved.
                conn.execute(
                    """INSERT INTO snapshot
                       (id, engagement_id, source, source_filename, source_hash,
                        cap_table_json, parse_report_json, superseded_by,
                        created_by, created_at, redacted, change_note)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        snap_id,
                        engagement_id,
                        source.value,
                        source_filename,
                        source_hash,
                        ct_json,
                        parse_report_json,
                        None,
                        actor.id,
                        now.isoformat(),
                        0,
                        change_note,
                    ),
                )
                # B3: link prior head's superseded_by. Inside the same
                # locked + atomic-updated transaction this is now safe.
                if eng.head_snapshot_id is not None:
                    conn.execute(
                        "UPDATE snapshot SET superseded_by = ? "
                        "WHERE id = ? AND superseded_by IS NULL",
                        (snap_id, eng.head_snapshot_id),
                    )

            self._append_audit_event(
                engagement_id=engagement_id,
                event_type=AuditEventType.snapshot_added,
                payload={
                    "snapshot_id": snap_id,
                    "source": source.value,
                    "source_filename": source_filename,
                    "source_hash": source_hash,
                },
                actor=actor,
            )
        return self.get_snapshot(snap_id)

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM snapshot WHERE id = ?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise SnapshotNotFound(f"snapshot {snapshot_id} not found")
        return self._row_to_snapshot(row)

    def list_snapshots(
        self,
        engagement_id: str,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[Snapshot]:
        # W3-AUDIT M3: deterministic ordering. Without `, id` tiebreaker,
        # two snapshots with identical created_at sort non-deterministically
        # and break SYSTEM_SPEC §8.10 determinism for downstream memo
        # subsequent-events sections.
        # SD-AUD-W9-M1: optional limit + offset pushed into SQL so a
        # paginated request does not have to load every snapshot's
        # cap_table_json blob into memory. Default behaviour
        # (limit=None) preserves backward compatibility — callers that
        # need the full chain (memo, bundle, timeline diff) still get it.
        sql = (
            "SELECT * FROM snapshot WHERE engagement_id = ? "
            "ORDER BY created_at, id"
        )
        params: list = [engagement_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def count_snapshots(self, engagement_id: str) -> int:
        """SD-AUD-W9-M1: cheap COUNT for pagination chrome."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM snapshot WHERE engagement_id = ?",
                (engagement_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def _row_to_snapshot(self, row: sqlite3.Row) -> Snapshot:
        # W7.4: change_note may be absent on legacy DBs that haven't been
        # touched by the idempotent ALTER yet (e.g. read-only mounts).
        keys = row.keys() if hasattr(row, "keys") else []
        change_note = row["change_note"] if "change_note" in keys else None
        return Snapshot(
            id=row["id"],
            engagement_id=row["engagement_id"],
            source=SnapshotSource(row["source"]),
            source_filename=row["source_filename"],
            source_hash=row["source_hash"],
            cap_table_json=row["cap_table_json"],
            parse_report_json=row["parse_report_json"],
            superseded_by=row["superseded_by"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            redacted=bool(row["redacted"]),
            change_note=change_note,
        )

    # ---- Resolutions (append-only) -------------------------------------

    def record_resolution(
        self,
        actor: User,
        snapshot_id: str,
        finding_code: str,
        decision: dict,
        citation: str,
    ) -> Resolution:
        if not can(actor, "engagement.resolve_finding"):
            raise PermissionDenied(f"{actor.role} cannot engagement.resolve_finding")
        if not citation or not str(citation).strip():
            raise EngagementError("resolution citation is required and must be non-empty")
        snap = self.get_snapshot(snapshot_id)
        res_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        decision_json = json.dumps(decision, sort_keys=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """INSERT INTO resolution
                   (id, snapshot_id, finding_code, decision_json, citation,
                    resolved_by, resolved_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (res_id, snapshot_id, finding_code, decision_json, citation,
                 actor.id, now.isoformat()),
            )
        self._append_audit_event(
            engagement_id=snap.engagement_id,
            event_type=AuditEventType.resolution_recorded,
            payload={
                "resolution_id": res_id,
                "snapshot_id": snapshot_id,
                "finding_code": finding_code,
                "decision": decision,
                "citation": citation,
            },
            actor=actor,
        )
        return Resolution(
            id=res_id,
            snapshot_id=snapshot_id,
            finding_code=finding_code,
            decision_json=decision_json,
            citation=citation,
            resolved_by=actor.id,
            resolved_at=now,
        )

    def list_resolutions(self, snapshot_id: str) -> list[Resolution]:
        # W3-AUDIT M3: same determinism fix as list_snapshots.
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM resolution WHERE snapshot_id = ? "
                "ORDER BY resolved_at, id",
                (snapshot_id,),
            ).fetchall()
        return [
            Resolution(
                id=r["id"],
                snapshot_id=r["snapshot_id"],
                finding_code=r["finding_code"],
                decision_json=r["decision_json"],
                citation=r["citation"],
                resolved_by=r["resolved_by"],
                resolved_at=datetime.fromisoformat(r["resolved_at"]),
            )
            for r in rows
        ]

    # ---- Lifecycle transitions -----------------------------------------

    def transition(
        self,
        actor: User,
        engagement_id: str,
        expected_version: int,
        new_status: EngagementStatus,
        note: Optional[str] = None,
    ) -> Engagement:
        # Same B2-style atomic conditional UPDATE pattern as add_snapshot.
        with self._write_lock:
            eng = self.get_engagement(engagement_id)
            if eng.version != expected_version:
                raise EngagementVersionConflict(
                    engagement_id, expected_version, eng.version,
                )

            if new_status not in _ALLOWED_TRANSITIONS.get(eng.status, set()):
                raise IllegalStateTransition(
                    f"cannot transition engagement {engagement_id} from "
                    f"{eng.status.value} to {new_status.value}"
                )

            action = _TRANSITION_PERMISSION.get((eng.status, new_status))
            if action and not can(actor, action):
                raise PermissionDenied(f"{actor.role} cannot {action}")

            # W8.10: restore-window enforcement. The transition contract
            # already gates the (archived → open) state pair on the
            # `engagement.restore_archived` permission; here we also
            # refuse the restore once the window has closed (the
            # hard-delete CLI would otherwise vaporise the engagement
            # while the partner thinks they have time).
            if (eng.status == EngagementStatus.archived
                    and new_status == EngagementStatus.open):
                if eng.restore_eligibility_until is None or (
                    eng.restore_eligibility_until
                    < datetime.now(timezone.utc)
                ):
                    raise IllegalStateTransition(
                        f"engagement {engagement_id} restore window has "
                        f"expired (eligible until "
                        f"{eng.restore_eligibility_until})"
                    )

            # B-3 fix (compiled system audit): SPEC §3.2 requires
            # review → signed to refuse when blocker findings are unresolved.
            # Load head snapshot, run the engagement's bound pack, surface
            # any blocker codes not yet resolved by a recorded resolution.
            if new_status == EngagementStatus.signed and eng.head_snapshot_id:
                self._enforce_blockers_resolved(eng)

            # W8.10: stamp archival metadata atomically with the status
            # change when target == archived. On any non-archived transition
            # (including restore via the dedicated path) we ALSO clear the
            # archival columns — a partner unarchiving must not leave stale
            # timestamps behind.
            now = datetime.now(timezone.utc)
            with closing(self._connect()) as conn, conn:
                if new_status == EngagementStatus.archived:
                    restore_until = now + timedelta(days=ARCHIVAL_RESTORE_DAYS)
                    cur = conn.execute(
                        "UPDATE engagement SET status = ?, version = version + 1, "
                        "archived_at = ?, restore_eligibility_until = ? "
                        "WHERE id = ? AND version = ?",
                        (new_status.value, now.isoformat(),
                         restore_until.isoformat(),
                         engagement_id, expected_version),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE engagement SET status = ?, version = version + 1, "
                        "archived_at = NULL, restore_eligibility_until = NULL "
                        "WHERE id = ? AND version = ?",
                        (new_status.value, engagement_id, expected_version),
                    )
                if cur.rowcount != 1:
                    raise EngagementVersionConflict(
                        engagement_id, expected_version,
                        self.get_engagement(engagement_id).version,
                    )
            self._append_audit_event(
                engagement_id=engagement_id,
                event_type=AuditEventType.transition,
                payload={
                    "from": eng.status.value,
                    "to": new_status.value,
                    "note": note,
                },
                actor=actor,
            )
        return self.get_engagement(engagement_id)

    def hard_delete_expired_archived(self) -> int:
        """W8.10: drop engagements whose archival restore window has
        closed. Cascades to snapshots + resolutions + parse reports;
        deliberately KEEPS audit_event rows so the chain history remains
        for any Big-4 inquiry. Returns the number of engagements deleted.

        Idempotent and safe to schedule daily. Engagement legal-erasure
        contract (preserve audit metadata vs delete entirely) is Evelyn-
        blocked; current implementation chooses preservation.
        """
        deleted = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            with closing(self._connect()) as conn, conn:
                rows = conn.execute(
                    "SELECT id FROM engagement WHERE status = ? "
                    "AND restore_eligibility_until IS NOT NULL "
                    "AND restore_eligibility_until < ?",
                    (EngagementStatus.archived.value, now_iso),
                ).fetchall()
                for row in rows:
                    eng_id = row["id"]
                    # Cascade: resolutions first (FK on snapshot), then
                    # snapshots (FK on engagement), then engagement.
                    snap_ids = [
                        r["id"] for r in conn.execute(
                            "SELECT id FROM snapshot WHERE engagement_id = ?",
                            (eng_id,),
                        )
                    ]
                    for sid in snap_ids:
                        conn.execute(
                            "DELETE FROM resolution WHERE snapshot_id = ?",
                            (sid,),
                        )
                    conn.execute(
                        "DELETE FROM snapshot WHERE engagement_id = ?",
                        (eng_id,),
                    )
                    conn.execute(
                        "DELETE FROM engagement WHERE id = ?", (eng_id,),
                    )
                    deleted += 1
        return deleted

    def _enforce_blockers_resolved(self, eng: "Engagement") -> None:
        """B-3 fix (compiled system audit). Loads the head snapshot, runs
        the engagement-bound pack, collects every blocker finding code,
        compares against the recorded resolutions on the head snapshot,
        and raises BlockerFindingsOutstanding if any blocker remains
        unresolved. SPEC §3.2 + §7.12: no force-flag bypass.
        """
        if not eng.head_snapshot_id:
            return
        snap = self.get_snapshot(eng.head_snapshot_id)
        cap_table = snap.load_cap_table()
        if cap_table is None:
            # Redacted head — caller already past the data-driven gate;
            # let downstream logic decide. Refuse defensively.
            raise BlockerFindingsOutstanding(
                f"engagement {eng.id} head snapshot is redacted; cannot "
                "evaluate blocker findings."
            )
        # Lazy import to avoid the rule_pack ↔ engagement cycle at module load.
        from .rule_pack import load_engagement_bound_pack, run_pack
        try:
            pack = load_engagement_bound_pack(eng.pack_version)
        except (FileNotFoundError, ValueError) as e:
            raise BlockerFindingsOutstanding(
                f"engagement {eng.id} bound pack {eng.pack_version} cannot "
                f"be loaded: {e}. Refuse the transition until the pack is "
                f"available."
            )
        findings = run_pack(cap_table, pack=pack)
        blocker_codes = {f.code for f in findings if f.severity == "blocker"}
        resolved_codes = {
            r.finding_code for r in self.list_resolutions(snap.id)
        }
        outstanding = blocker_codes - resolved_codes
        if outstanding:
            raise BlockerFindingsOutstanding(
                f"engagement {eng.id} has {len(outstanding)} unresolved "
                f"blocker finding(s): {sorted(outstanding)}. SPEC §3.2 + "
                f"§7.12 forbid signing with outstanding blockers; resolve "
                f"each via /resolve before retrying."
            )

    # ---- PII redaction (GAP-03) ----------------------------------------

    def redact_snapshot_pii(
        self,
        actor: User,
        snapshot_id: str,
        request_reference: str,
        legal_basis: str,
    ) -> Snapshot:
        if not can(actor, "engagement.pii_redact"):
            raise PermissionDenied(f"{actor.role} cannot engagement.pii_redact")
        snap = self.get_snapshot(snapshot_id)
        if snap.redacted:
            return snap
        redaction_event_id = str(uuid.uuid4())
        redacted_at = datetime.now(timezone.utc)
        sentinel = json.dumps(
            {
                "_redacted": True,
                "redaction_event_id": redaction_event_id,
                "redacted_at": redacted_at.isoformat(),
            },
            sort_keys=True,
        )
        with closing(self._connect()) as conn, conn:
            # Redaction is one of two exceptions to snapshot immutability,
            # documented in this module's docstring. The other is
            # superseded_by linkage. Both are "linking" operations; no
            # original data is ever modified, only zeroed/pointed.
            # SD-AUD-W7-B1: zero change_note + source_filename too. The
            # wave-7 change_note column carries analyst free-text that
            # frequently is the very PII triggering the redaction request
            # (the upload form's placeholder literally encourages naming
            # people and dollars). source_filename historically encodes
            # client + date so it carries the same risk. Both are dropped
            # to NULL inside the same transaction as the cap_table sentinel
            # so the redaction is atomic.
            conn.execute(
                "UPDATE snapshot SET cap_table_json = ?, redacted = 1, "
                "change_note = NULL, source_filename = NULL WHERE id = ?",
                (sentinel, snapshot_id),
            )
        self._append_audit_event(
            engagement_id=snap.engagement_id,
            event_type=AuditEventType.pii_redacted,
            payload={
                "snapshot_id": snapshot_id,
                "redaction_event_id": redaction_event_id,
                "request_reference": request_reference,
                "legal_basis": legal_basis,
            },
            actor=actor,
        )
        return self.get_snapshot(snapshot_id)

    # ---- Audit log ------------------------------------------------------

    def _append_audit_event(
        self,
        engagement_id: str,
        event_type: AuditEventType,
        payload: dict,
        actor: User,
    ) -> AuditEvent:
        # Canonical JSON: sorted keys, no whitespace.
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        ts = datetime.now(timezone.utc)
        ts_iso = ts.isoformat()

        # B1 fix: serialise the read-modify-write across the hash chain.
        # SQLite's DEFERRED transaction does not promote the SELECT to a
        # write lock, so two concurrent appends can both read the same
        # prev_hash and fork the chain. Holding the process-local
        # _write_lock around the entire compute+insert+update sequence
        # prevents the fork. The RLock makes this safe for callers like
        # add_snapshot that already hold the lock.
        with self._write_lock:
            with closing(self._connect()) as conn, conn:
                row = conn.execute(
                    "SELECT audit_head_hash FROM engagement WHERE id = ?",
                    (engagement_id,),
                ).fetchone()
                if row is None:
                    raise EngagementNotFound(engagement_id)
                prev_hash = row["audit_head_hash"]
                row_hash = _compute_row_hash(
                    prev_hash, event_type.value, payload_json, actor.id, ts_iso
                )
                event_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO audit_event
                       (id, engagement_id, event_type, payload_json, actor, ts,
                        prev_row_hash, row_hash)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        engagement_id,
                        event_type.value,
                        payload_json,
                        actor.id,
                        ts_iso,
                        prev_hash,
                        row_hash,
                    ),
                )
                conn.execute(
                    "UPDATE engagement SET audit_head_hash = ? WHERE id = ?",
                    (row_hash, engagement_id),
                )
        return AuditEvent(
            id=event_id,
            engagement_id=engagement_id,
            event_type=event_type,
            payload_json=payload_json,
            actor=actor.id,
            ts=ts,
            prev_row_hash=prev_hash,
            row_hash=row_hash,
        )

    def list_audit_events(self, engagement_id: str) -> list[AuditEvent]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM audit_event WHERE engagement_id = ? ORDER BY ts, id",
                (engagement_id,),
            ).fetchall()
        return [
            AuditEvent(
                id=r["id"],
                engagement_id=r["engagement_id"],
                event_type=AuditEventType(r["event_type"]),
                payload_json=r["payload_json"],
                actor=r["actor"],
                ts=datetime.fromisoformat(r["ts"]),
                prev_row_hash=r["prev_row_hash"],
                row_hash=r["row_hash"],
            )
            for r in rows
        ]

    def verify_audit_log(self, engagement_id: str) -> tuple[bool, Optional[str]]:
        """Recompute the per-engagement hash chain. Returns (ok, problem)."""
        events = self.list_audit_events(engagement_id)
        prev = _GENESIS_HASH
        for ev in events:
            if ev.prev_row_hash != prev:
                return False, (
                    f"event {ev.id} has prev_row_hash {ev.prev_row_hash[:8]}..., "
                    f"expected {prev[:8]}..."
                )
            expected = _compute_row_hash(
                prev, ev.event_type.value, ev.payload_json, ev.actor, ev.ts.isoformat()
            )
            if expected != ev.row_hash:
                return False, (
                    f"event {ev.id} row_hash mismatch: stored {ev.row_hash[:8]}..., "
                    f"recomputed {expected[:8]}..."
                )
            prev = ev.row_hash
        # And the engagement's published head must equal the last row hash.
        eng = self.get_engagement(engagement_id)
        if events and eng.audit_head_hash != events[-1].row_hash:
            return False, "engagement audit_head_hash does not match last event"
        if not events and eng.audit_head_hash != _GENESIS_HASH:
            return False, "engagement has no events but audit_head_hash != genesis"
        return True, None
