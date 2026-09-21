"""Bulk-export rate limiting (SYSTEM_SPEC §8.17 / GAP-40).

Per-user export counter with two thresholds:
  - Soft (default 30/hr) → HTTP 429 with Retry-After + code export-rate-limit
  - Hard (default 100/hr) → audit_event bulk_export_alert + notify Risk role

State persists in SQLite via a single `export_counter` table so counters
survive restart. Per-user, not per-IP — auth must be wired before this
is meaningful.

Sliding-window design: keep one row per (user_id, hour_bucket). Lookup
counts in the trailing window via SUM over buckets in [now-window, now].
Cheap and deterministic.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS export_counter (
    user_id      TEXT NOT NULL,
    hour_bucket  INTEGER NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, hour_bucket)
);

CREATE INDEX IF NOT EXISTS ix_export_counter_bucket
ON export_counter(hour_bucket);
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    current_count: int
    soft_limit: int
    hard_limit: int
    triggered_hard_alert: bool
    retry_after_seconds: int


@dataclass
class ExportRateLimiter:
    db_path: Path
    soft_limit: int = 30
    hard_limit: int = 100
    window_seconds: int = 3600  # 1 hour
    # Injectable clock for tests
    now_fn: callable = time.time  # type: ignore[assignment]

    def __post_init__(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _bucket(self, ts: float) -> int:
        return int(ts // self.window_seconds)

    def consume(self, user_id: str) -> RateLimitResult:
        """Atomically increment the per-user counter and check thresholds.

        Returns RateLimitResult. Caller (HTTP layer) is responsible for
        translating .allowed=False into HTTP 429 with the retry header,
        and .triggered_hard_alert=True into the audit_event hook.

        Important: this method ALWAYS increments — even when the soft limit
        is hit. That way the audit log records the attempt. The HTTP layer
        rejects the request body / file generation; the counter still
        moves forward so abusive callers don't reset their state by
        retrying past the limit.
        """
        now = self.now_fn()
        bucket = self._bucket(now)
        # SD-AUD-M8: single calendar-hour bucket policy. The prior 2-bucket
        # sum gave an effective trailing window between 1h and 2h depending
        # on position within the bucket, doubling the soft limit just after
        # a boundary. Calendar-hour is what §8.17 documents.
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """INSERT INTO export_counter (user_id, hour_bucket, count)
                   VALUES (?, ?, 1)
                   ON CONFLICT(user_id, hour_bucket) DO UPDATE SET
                     count = count + 1""",
                (user_id, bucket),
            )
            row = conn.execute(
                """SELECT COALESCE(SUM(count), 0) AS n
                   FROM export_counter
                   WHERE user_id = ? AND hour_bucket = ?""",
                (user_id, bucket),
            ).fetchone()
        current = int(row["n"])
        # Edge-trigger: alert fires exactly once at the boundary, not on
        # every subsequent call. (M2 fix from CODE_AUDIT_WAVE_2.) The
        # caller is the place that records the audit event, gated on
        # current == hard_limit.
        triggered_hard = current == self.hard_limit
        allowed = current <= self.soft_limit
        # Retry-after: seconds remaining until the head bucket rolls off.
        retry_after = int((bucket + 1) * self.window_seconds - now)
        return RateLimitResult(
            allowed=allowed,
            current_count=current,
            soft_limit=self.soft_limit,
            hard_limit=self.hard_limit,
            triggered_hard_alert=triggered_hard,
            retry_after_seconds=max(retry_after, 1),
        )

    def reset_user(self, user_id: str) -> None:
        """Used in tests."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM export_counter WHERE user_id = ?", (user_id,))

    def prune_older_than(self, ts: float) -> int:
        """Garbage-collect buckets older than `ts`. Returns rows deleted."""
        cutoff = self._bucket(ts)
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "DELETE FROM export_counter WHERE hour_bucket < ?",
                (cutoff,),
            )
            return cur.rowcount
