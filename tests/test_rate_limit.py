"""ExportRateLimiter tests (W2.2 / SYSTEM_SPEC §8.17 / GAP-40)."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User
from src.rate_limit import ExportRateLimiter


@pytest.fixture
def limiter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    rl = ExportRateLimiter(db_path=p, soft_limit=3, hard_limit=5)
    yield rl
    p.unlink(missing_ok=True)


def test_under_soft_limit_allowed(limiter):
    r1 = limiter.consume("u-1")
    r2 = limiter.consume("u-1")
    r3 = limiter.consume("u-1")
    assert r1.allowed and r2.allowed and r3.allowed
    assert r3.current_count == 3
    assert not r3.triggered_hard_alert


def test_above_soft_limit_blocked_but_counter_advances(limiter):
    for _ in range(3):
        limiter.consume("u-1")
    r = limiter.consume("u-1")
    assert not r.allowed  # rate-limited
    assert r.current_count == 4  # counter still moved
    assert r.retry_after_seconds > 0


def test_above_hard_limit_triggers_alert(limiter):
    for _ in range(4):
        limiter.consume("u-1")
    r = limiter.consume("u-1")  # 5th — equals hard_limit
    assert r.triggered_hard_alert


def test_per_user_isolation(limiter):
    for _ in range(4):
        limiter.consume("u-1")
    r = limiter.consume("u-2")
    assert r.allowed
    assert r.current_count == 1


def test_reset_user_clears_count(limiter):
    for _ in range(3):
        limiter.consume("u-1")
    limiter.reset_user("u-1")
    r = limiter.consume("u-1")
    assert r.allowed
    assert r.current_count == 1


def test_bucket_rolls_over_time():
    """Inject an advancing clock to verify the sliding window."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    try:
        t = [1_700_000_000.0]
        rl = ExportRateLimiter(db_path=p, soft_limit=2, hard_limit=10,
                                window_seconds=3600, now_fn=lambda: t[0])
        rl.consume("u-1")
        rl.consume("u-1")
        # 4 hours later → counter should drop below the limit
        t[0] += 4 * 3600
        r = rl.consume("u-1")
        assert r.current_count == 1
        assert r.allowed
    finally:
        p.unlink(missing_ok=True)


# ---- HTTP integration -----------------------------------------------------


def _make_excel_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cap Table"
    ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date",
               "LP Multiple", "LP Type", "Seniority", "Anti-Dilution"])
    ws.append(["Common", "common", 1_000_000, 0.01, "2020-01-01",
               "", "", "", ""])
    ws.append(["Series A", "preferred", 1_000_000, 1.00, "2024-01-01",
               1.0, "non_participating", 1, "broad_based_weighted_average"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def app_with_low_limit():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as eng_fh, \
         tempfile.NamedTemporaryFile(suffix=".db", delete=False) as rl_fh:
        eng_path = Path(eng_fh.name)
        rl_path = Path(rl_fh.name)
    store = EngagementStore(db_path=eng_path)
    limiter = ExportRateLimiter(db_path=rl_path, soft_limit=2, hard_limit=3)
    app = Flask(__name__)
    users = {
        "tok-analyst": User(id="u-a", email="a@x", role=Role.analyst,
                            display_name="A Analyst"),
        "tok-reviewer": User(id="u-r", email="r@x", role=Role.reviewer,
                             display_name="R Reviewer"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users),
                                 export_limiter=limiter)
    yield app.test_client(), store
    eng_path.unlink(missing_ok=True)
    rl_path.unlink(missing_ok=True)


def test_memo_returns_429_after_soft_limit(app_with_low_limit):
    client, store = app_with_low_limit
    create_headers = {"Authorization": "Bearer tok-analyst"}
    headers = {"Authorization": "Bearer tok-reviewer"}
    eng_id = client.post("/engagement/", headers=create_headers,
                          json={"client_id": "c"}).get_json()["id"]
    client.post(
        f"/engagement/{eng_id}/upload", headers=create_headers,
        data={"file": (io.BytesIO(_make_excel_bytes()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    # 2 allowed memo generations
    r1 = client.get(f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer", headers=headers)
    r2 = client.get(f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer", headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # 3rd → 429
    r3 = client.get(f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer", headers=headers)
    assert r3.status_code == 429
    assert r3.headers.get("Retry-After")
    body = r3.get_json()
    assert body["error_code"] == "export-rate-limit"
    assert body["current_count"] == 3


def test_hard_alert_writes_audit_event(app_with_low_limit):
    client, store = app_with_low_limit
    create_headers = {"Authorization": "Bearer tok-analyst"}
    headers = {"Authorization": "Bearer tok-reviewer"}
    eng_id = client.post("/engagement/", headers=create_headers,
                          json={"client_id": "c"}).get_json()["id"]
    client.post(
        f"/engagement/{eng_id}/upload", headers=create_headers,
        data={"file": (io.BytesIO(_make_excel_bytes()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    # Hit hard limit (limiter has hard=3): 3 attempts
    for _ in range(3):
        client.get(f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer", headers=headers)
    events = store.list_audit_events(eng_id)
    alerts = [e for e in events if e.event_type.value == "bulk_export_alert"]
    assert len(alerts) >= 1
