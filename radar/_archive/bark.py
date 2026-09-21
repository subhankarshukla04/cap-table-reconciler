"""Bark notifier — fires a push when score crosses BARK_THRESHOLD.

Uses BARK_DEVICE_KEY from environment. No key → silently log only.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx

from . import db

DEDUP_WINDOW_HOURS = 24


def _recently_fired(issuer_id: str) -> bool:
    cutoff = (datetime.now() - timedelta(hours=DEDUP_WINDOW_HOURS)).isoformat()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM bark_log WHERE issuer_id = ? AND fired_at >= ? LIMIT 1",
            (issuer_id, cutoff),
        ).fetchone()
    return row is not None


def _log(issuer_id: str, score: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO bark_log (issuer_id, fired_at, score) VALUES (?,?,?)",
            (issuer_id, datetime.now().isoformat(), score),
        )
        conn.commit()


def send_alert(issuer_id: str, issuer_name: str, score: int,
               top_trigger: str = "") -> bool:
    if _recently_fired(issuer_id):
        print(f"  [bark] {issuer_id} alerted within {DEDUP_WINDOW_HOURS}h — skip")
        return False
    key = (os.environ.get("BARK_DEVICE_KEY")
           or os.environ.get("BARK_KEY") or "").strip()
    title = f"Tender Radar · {issuer_name} → {score}"
    body = top_trigger or "Score crossed alert threshold"
    if not key:
        print(f"  [bark] NO KEY · would push: {title} — {body}")
        _log(issuer_id, score)
        return False
    try:
        url = f"https://api.day.app/{key}/{quote(title)}/{quote(body)}"
        r = httpx.get(url, timeout=10.0, params={"url": f"http://localhost:5001/issuer/{issuer_id}"})
        ok = r.status_code == 200
    except Exception as e:
        print(f"  [bark] ERROR: {e}")
        ok = False
    if ok:
        _log(issuer_id, score)
        print(f"  [bark] pushed: {title}")
    return ok
