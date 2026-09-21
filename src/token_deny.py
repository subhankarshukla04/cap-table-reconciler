"""Bearer-token deny list (W6.4 / closes SD-AUD-B5 second-half).

SPEC §11.2: logout-equivalent revocation for Bearer tokens.

The cookie-auth shim's `/logout` cleared only the session cookie; a Bearer
token issued for the same user kept working. For a production deploy where
SSO can't be relied on to instantly revoke tokens, the engagement service
holds a small deny list of SHA-256(token) hashes. Any subsequent request
that presents a denied token is rejected before identity resolution.

We store the *hash* of the token, never the raw value, so a database
compromise doesn't leak live credentials.

SD-AUD-W6M-2 / W6M-4 hardening:
  - Entries carry an `expires_at` so the deny list isn't a one-way
    permanent revocation. Default 30 days, matching typical SSO token
    lifetime.
  - sqlite connection is process-cached and WAL-mode so the engagement
    blueprint's per-request `is_revoked` check is not one fopen+fsync
    per HTTP call.
  - `size()` and `prune_older_than()` exposed for ops.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Optional


_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS token_deny (
    token_hash TEXT PRIMARY KEY,
    revoked_at REAL NOT NULL,
    expires_at REAL NOT NULL DEFAULT 0
)
"""

_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_token_deny_expires_at
ON token_deny(expires_at)
"""


DEFAULT_TTL_SECONDS = 30 * 86400  # 30 days


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenDenyList:
    """Process-shared sqlite-backed deny list. WAL mode + cached
    connection keep per-request lookup overhead minimal."""

    def __init__(self, db_path: Path, default_ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.db_path = Path(db_path)
        self.default_ttl_seconds = default_ttl_seconds
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Single cached connection per process. sqlite3.Connection is
        # thread-safe at the module level (check_same_thread=False), which
        # is what we want under Flask's threaded worker model.
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(_TABLE_SQL)
            # SD-AUD-W6M-4 migration: legacy table (wave-6 initial schema)
            # has no expires_at column. ALTER + backfill idempotently.
            try:
                self._conn.execute(
                    "ALTER TABLE token_deny ADD COLUMN expires_at REAL DEFAULT 0"
                )
                self._conn.execute(
                    "UPDATE token_deny SET expires_at = revoked_at + ? "
                    "WHERE expires_at = 0 OR expires_at IS NULL",
                    (self.default_ttl_seconds,),
                )
            except sqlite3.OperationalError:
                pass
            # Index must come after the migration so it can reference the
            # column on legacy DBs.
            self._conn.execute(_INDEX_SQL)

    def revoke(self, token: str, ttl_seconds: Optional[int] = None) -> None:
        """Add (or refresh) a deny entry for `token`. The hash is stored,
        never the raw token. TTL defaults to 30 days; pass a smaller value
        when the SSO issuance was short-lived."""
        if not token:
            return
        now = time.time()
        expires = now + (ttl_seconds or self.default_ttl_seconds)
        with self._lock:
            self._conn.execute(
                "INSERT INTO token_deny (token_hash, revoked_at, expires_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(token_hash) DO UPDATE SET "
                "  revoked_at = excluded.revoked_at, "
                "  expires_at = excluded.expires_at",
                (_hash(token), now, expires),
            )

    def is_revoked(self, token: str) -> bool:
        """True iff `token` has a non-expired deny entry. Expired entries
        are treated as not revoked — the lazy approach is fine because
        SSO would have rotated the credential past the TTL anyway."""
        if not token:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT expires_at FROM token_deny WHERE token_hash = ?",
                (_hash(token),),
            ).fetchone()
        if row is None:
            return False
        return float(row["expires_at"]) > time.time()

    def prune_older_than(self, ts: float) -> int:
        """Drop deny entries whose `revoked_at` is older than `ts`
        (epoch seconds). Returns rows deleted. Operators schedule this
        nightly using the SSO max token lifetime as the cutoff."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM token_deny WHERE revoked_at < ?", (ts,),
            )
            return cur.rowcount

    def prune_expired(self) -> int:
        """Drop deny entries whose `expires_at` has already passed. Cheap
        scheduled cleanup that doesn't need an SRE-supplied cutoff."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM token_deny WHERE expires_at < ?", (time.time(),),
            )
            return cur.rowcount

    def size(self) -> int:
        """Return current row count. Useful for /healthz exposure and for
        spotting DOS attacks that pump the deny list."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM token_deny"
            ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        """Close the cached sqlite connection. Tests + graceful shutdown
        call this; production never does."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
