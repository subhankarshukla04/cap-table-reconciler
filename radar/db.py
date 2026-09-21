"""SQLite helpers for Tender Radar. Schema is intentionally tiny."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "radar.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS issuers (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS holders (
    issuer_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (issuer_id) REFERENCES issuers(id)
);
CREATE INDEX IF NOT EXISTS idx_holders_issuer ON holders(issuer_id);
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL,
    source TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_issuer ON signals(issuer_id);
CREATE INDEX IF NOT EXISTS idx_signals_captured ON signals(captured_at);
CREATE TABLE IF NOT EXISTS scores (
    issuer_id TEXT NOT NULL,
    run_date TEXT NOT NULL,
    score INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (issuer_id, run_date)
);
CREATE TABLE IF NOT EXISTS digest_runs (
    run_date TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bark_log (
    issuer_id TEXT NOT NULL,
    fired_at TEXT NOT NULL,
    score INTEGER NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def load_issuers() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM issuers").fetchall()
    return [json.loads(r["payload"]) for r in rows]


def load_holders(issuer_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM holders WHERE issuer_id = ?", (issuer_id,)
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def load_signals_for_issuer(issuer_id: str, since_iso: str | None = None) -> list[dict]:
    sql = "SELECT payload FROM signals WHERE issuer_id = ?"
    args: tuple = (issuer_id,)
    if since_iso:
        sql += " AND captured_at >= ?"
        args = (issuer_id, since_iso)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def load_all_signals(since_iso: str | None = None) -> list[dict]:
    sql = "SELECT payload FROM signals"
    args: tuple = ()
    if since_iso:
        sql += " WHERE captured_at >= ?"
        args = (since_iso,)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def upsert_signal(sig: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO signals
               (id, issuer_id, source, signal_type, captured_at, payload)
               VALUES (?,?,?,?,?,?)""",
            (sig["id"], sig["issuer_id"], sig["source"], sig["signal_type"],
             sig["captured_at"], json.dumps(sig, default=str)),
        )
        conn.commit()


def upsert_score(issuer_id: str, run_date: str, score: int, payload: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO scores (issuer_id, run_date, score, payload)
               VALUES (?,?,?,?)""",
            (issuer_id, run_date, score, json.dumps(payload, default=str)),
        )
        conn.commit()


def load_scores_for_date(run_date: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM scores WHERE run_date = ? ORDER BY score DESC",
            (run_date,),
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def latest_score(issuer_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT payload FROM scores WHERE issuer_id = ?
               ORDER BY run_date DESC LIMIT 1""",
            (issuer_id,),
        ).fetchone()
    return json.loads(row["payload"]) if row else None
