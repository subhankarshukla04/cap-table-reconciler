"""
SQLite-backed session store for the Cap Table Reconciler.

Replaces the in-memory `SESSIONS: dict[str, dict]` so that uploaded sessions
survive a server restart. The store is a lazy-write cache: reads come from
memory first, falling back to the DB; writes are flushed to disk via
`flush(token)` after every mutation.

Schema (single table):

  sessions(
    token              TEXT PRIMARY KEY,
    created_at         TEXT NOT NULL,
    fixture_id         TEXT,
    cap_table_json     TEXT NOT NULL,
    parse_report_json  TEXT,
    raw_excerpt_json   TEXT,
    resolutions_json   TEXT NOT NULL DEFAULT '[]'
  )

Waterfall + findings are NOT persisted — they are deterministic functions of
the cap table and are recomputed on read. This keeps the DB small and avoids
schema churn when waterfall/checklist code evolves.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .checklist import run_checklist
from .models import CapTable
from .parser import ParseReport, ParseWarning
from .waterfall import compute_waterfall


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token                       TEXT PRIMARY KEY,
    created_at                  TEXT NOT NULL,
    fixture_id                  TEXT,
    cap_table_json              TEXT NOT NULL,
    original_cap_table_json     TEXT,
    parse_report_json           TEXT,
    raw_excerpt_json            TEXT,
    resolutions_json            TEXT NOT NULL DEFAULT '[]'
);
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Idempotent migration for older DBs missing original_cap_table_json."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "original_cap_table_json" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN original_cap_table_json TEXT")


def _serialize_parse_report(report: Optional[ParseReport]) -> Optional[str]:
    if report is None:
        return None
    return json.dumps(asdict(report))


def _deserialize_parse_report(blob: Optional[str]) -> Optional[ParseReport]:
    if blob is None:
        return None
    raw = json.loads(blob)
    warnings = [ParseWarning(**w) for w in raw.get("warnings", [])]
    return ParseReport(
        cap_table_sheet=raw.get("cap_table_sheet"),
        column_mapping=raw.get("column_mapping", {}),
        unmapped_headers=raw.get("unmapped_headers", []),
        warnings=warnings,
    )


class SessionStore:
    """Dict-like SQLite-backed store with in-memory cache.

    Behaviour:
    - `__contains__` / `get` / `__getitem__` check cache first, then DB.
    - `__setitem__` updates cache and immediately persists.
    - `flush(token)` re-persists after in-place mutation of the cached dict.

    The dict shape returned matches the original `SESSIONS` schema, so route
    handlers don't need to change beyond adding `flush(token)` calls.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)
            _ensure_columns(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _hydrate(self, row: sqlite3.Row) -> dict:
        cap_table = CapTable.model_validate_json(row["cap_table_json"])
        original_blob = row["original_cap_table_json"] if "original_cap_table_json" in row.keys() else None
        original_cap_table = (
            CapTable.model_validate_json(original_blob) if original_blob else cap_table
        )
        parse_report = _deserialize_parse_report(row["parse_report_json"])
        raw_excerpt = json.loads(row["raw_excerpt_json"]) if row["raw_excerpt_json"] else None
        resolutions = json.loads(row["resolutions_json"]) if row["resolutions_json"] else []
        sess = {
            "cap_table": cap_table,
            "original_cap_table": original_cap_table,
            "parse_report": parse_report,
            "raw_excerpt": raw_excerpt,
            "fixture_id": row["fixture_id"],
            "resolutions": resolutions,
            "waterfall": compute_waterfall(cap_table),
            "findings": run_checklist(cap_table),
        }
        return sess

    def _persist(self, token: str, sess: dict) -> None:
        cap_table_json = sess["cap_table"].model_dump_json()
        original_ct = sess.get("original_cap_table") or sess["cap_table"]
        original_cap_table_json = original_ct.model_dump_json()
        parse_report_json = _serialize_parse_report(sess.get("parse_report"))
        raw_excerpt_json = (
            json.dumps(sess["raw_excerpt"]) if sess.get("raw_excerpt") else None
        )
        resolutions_json = json.dumps(sess.get("resolutions", []))
        created_at = sess.get("created_at") or datetime.now(timezone.utc).isoformat()
        sess["created_at"] = created_at
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO sessions
                  (token, created_at, fixture_id, cap_table_json,
                   original_cap_table_json, parse_report_json,
                   raw_excerpt_json, resolutions_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET
                  fixture_id = excluded.fixture_id,
                  cap_table_json = excluded.cap_table_json,
                  parse_report_json = excluded.parse_report_json,
                  raw_excerpt_json = excluded.raw_excerpt_json,
                  resolutions_json = excluded.resolutions_json
                """,
                (
                    token,
                    created_at,
                    sess.get("fixture_id"),
                    cap_table_json,
                    original_cap_table_json,
                    parse_report_json,
                    raw_excerpt_json,
                    resolutions_json,
                ),
            )

    # ---- dict-like API -----------------------------------------------------

    def __contains__(self, token: str) -> bool:
        if token in self._cache:
            return True
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE token = ?", (token,)
            ).fetchone()
        return row is not None

    def __getitem__(self, token: str) -> dict:
        if token in self._cache:
            return self._cache[token]
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token = ?", (token,)
            ).fetchone()
        if row is None:
            raise KeyError(token)
        sess = self._hydrate(row)
        self._cache[token] = sess
        return sess

    def get(self, token: str, default=None) -> Optional[dict]:
        try:
            return self[token]
        except KeyError:
            return default

    def __setitem__(self, token: str, sess: dict) -> None:
        # Auto-derive waterfall + findings if caller didn't supply them.
        if "waterfall" not in sess:
            sess["waterfall"] = compute_waterfall(sess["cap_table"])
        if "findings" not in sess:
            sess["findings"] = run_checklist(sess["cap_table"])
        self._cache[token] = sess
        self._persist(token, sess)

    def flush(self, token: str) -> None:
        """Re-persist a cached session after in-place mutation."""
        if token not in self._cache:
            return
        self._persist(token, self._cache[token])

    def clear(self) -> None:
        self._cache.clear()
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM sessions")

    def __len__(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
        return int(row["n"])

    def list_sessions(self) -> list[dict]:
        """Return a lightweight summary of every persisted session, newest first."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT token, created_at, fixture_id, cap_table_json, resolutions_json
                FROM sessions
                ORDER BY created_at DESC
                """
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            try:
                ct = CapTable.model_validate_json(r["cap_table_json"])
                company_name = ct.company.name
                n_classes = len(ct.share_classes)
            except Exception:
                company_name = "(unparseable)"
                n_classes = 0
            try:
                resolutions = json.loads(r["resolutions_json"]) if r["resolutions_json"] else []
            except Exception:
                resolutions = []
            out.append(
                {
                    "token": r["token"],
                    "created_at": r["created_at"],
                    "fixture_id": r["fixture_id"],
                    "company_name": company_name,
                    "n_classes": n_classes,
                    "n_resolutions": len(resolutions),
                }
            )
        return out

    def delete(self, token: str) -> bool:
        """Remove a session from cache + DB. Returns True if it existed."""
        existed = token in self._cache
        self._cache.pop(token, None)
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            existed = existed or (cur.rowcount > 0)
        return bool(existed)
