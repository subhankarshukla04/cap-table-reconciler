"""Engagement-aware Flask blueprint tests (W2.1 / SYSTEM_SPEC §3.2)."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        db_path = Path(fh.name)
    store = EngagementStore(db_path=db_path)
    app = Flask(__name__)
    users = {
        "tok-analyst": User(id="u-1", email="a@x", role=Role.analyst, display_name="A Analyst"),
        "tok-reviewer": User(id="u-2", email="r@x", role=Role.reviewer, display_name="R Reviewer"),
        "tok-partner": User(id="u-3", email="p@x", role=Role.partner, display_name="P Partner"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users))
    yield app.test_client()
    db_path.unlink(missing_ok=True)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


# ---- Auth ------------------------------------------------------------------


def test_unauthenticated_returns_401(client):
    r = client.get("/engagement/")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"
    assert r.get_json()["error_code"] == "auth-required"


def test_authenticated_list_returns_empty_initially(client):
    r = client.get("/engagement/", headers=_auth("tok-analyst"))
    assert r.status_code == 200
    # W3.2: paginated response shape
    body = r.get_json()
    assert body["total"] == 0
    assert body["items"] == []


# ---- Create + show --------------------------------------------------------


def test_create_engagement_returns_201_with_metadata(client):
    r = client.post(
        "/engagement/",
        headers=_auth("tok-analyst"),
        json={"client_id": "client-001", "standard_of_value": "ifrs13"},
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["client_id"] == "client-001"
    assert body["status"] == "open"
    assert body["version"] == 0


def test_create_requires_client_id(client):
    r = client.post("/engagement/", headers=_auth("tok-analyst"), json={})
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "client-id-required"


def test_read_only_auditor_cannot_create(client):
    """Auditor role missing from fixture; verify by sending an unknown token."""
    r = client.post(
        "/engagement/", headers=_auth("tok-ghost"),
        json={"client_id": "c"},
    )
    assert r.status_code == 401


# ---- Upload --------------------------------------------------------------


def test_upload_creates_new_snapshot_and_bumps_version(client):
    r = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c", "standard_of_value": "ifrs13"},
    )
    eng_id = r.get_json()["id"]
    excel = _make_excel_bytes()
    r2 = client.post(
        f"/engagement/{eng_id}/upload",
        headers=_auth("tok-analyst"),
        data={"file": (io.BytesIO(excel), "demo.xlsx"), "expected_version": "0"},
        content_type="multipart/form-data",
    )
    assert r2.status_code == 201, r2.get_data(as_text=True)
    body = r2.get_json()
    assert body["snapshot_id"]
    assert body["engagement_version"] == 1


def test_upload_with_stale_expected_version_returns_409(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    excel = _make_excel_bytes()
    client.post(
        f"/engagement/{eng_id}/upload",
        headers=_auth("tok-analyst"),
        data={"file": (io.BytesIO(excel), "a.xlsx"), "expected_version": "0"},
        content_type="multipart/form-data",
    )
    # Second upload with stale expected_version=0 → 409
    r = client.post(
        f"/engagement/{eng_id}/upload",
        headers=_auth("tok-analyst"),
        data={"file": (io.BytesIO(excel), "b.xlsx"), "expected_version": "0"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["error_code"] == "engagement-version-conflict"
    assert body["expected_version"] == 0
    assert body["current_version"] == 1


def test_upload_unsupported_file_type(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.post(
        f"/engagement/{eng_id}/upload",
        headers=_auth("tok-analyst"),
        data={"file": (io.BytesIO(b"not an excel file"), "ouch.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "unsupported-file-type"


# ---- Transition ----------------------------------------------------------


def test_transition_open_to_review_then_signed(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    # analyst: open → review
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_auth("tok-analyst"),
        json={"new_status": "review", "expected_version": 0},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "review"
    # analyst CANNOT review → signed
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_auth("tok-analyst"),
        json={"new_status": "signed", "expected_version": 1},
    )
    assert r.status_code == 403
    assert r.get_json()["error_code"] == "permission-denied"
    # reviewer CAN
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_auth("tok-reviewer"),
        json={"new_status": "signed", "expected_version": 1},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "signed"


def test_illegal_transition_returns_409(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    # open → signed (not allowed)
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_auth("tok-analyst"),
        json={"new_status": "signed", "expected_version": 0},
    )
    assert r.status_code == 409
    # SPEC §3.2 / audit M-3 rename
    assert r.get_json()["error_code"] == "engagement-invalid-transition"


# ---- Audit log + integrity verify ----------------------------------------


def test_audit_log_returns_events(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.get(f"/engagement/{eng_id}/audit-log", headers=_auth("tok-analyst"))
    assert r.status_code == 200
    events = r.get_json()
    assert len(events) >= 1
    assert events[0]["event_type"] == "engagement_created"


def test_verify_returns_ok_on_clean_history(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.get(f"/engagement/{eng_id}/verify", headers=_auth("tok-analyst"))
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


# ---- Memo ----------------------------------------------------------------


def test_memo_pdf_404s_when_no_snapshot(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.get(
        f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer",
        headers=_auth("tok-analyst"),
    )
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "no-snapshot"


def test_memo_pdf_renders_after_upload(client):
    eng_id = client.post(
        "/engagement/", headers=_auth("tok-analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    excel = _make_excel_bytes()
    client.post(
        f"/engagement/{eng_id}/upload",
        headers=_auth("tok-analyst"),
        data={"file": (io.BytesIO(excel), "a.xlsx"), "expected_version": "0"},
        content_type="multipart/form-data",
    )
    r = client.get(
        f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer",
        headers=_auth("tok-reviewer"),
    )
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.get_data()[:4] == b"%PDF"
