"""HTMX UI tests (W4.1) — confirms HTML branches render alongside JSON."""

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


@pytest.fixture
def web():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        eng_path = Path(fh.name)
    store = EngagementStore(db_path=eng_path)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A Analyst"),
        "tok-r": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R Reviewer"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users))
    yield app.test_client(), store
    eng_path.unlink(missing_ok=True)


def _h(tok: str, accept_html: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {tok}"}
    if accept_html:
        headers["Accept"] = "text/html"
    return headers


def test_list_renders_html_with_accept_header(web):
    client, _ = web
    r = client.get("/engagement/", headers=_h("tok-a", accept_html=True))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "<html" in body
    assert "Engagements" in body
    assert "Create new engagement" in body  # analyst can create


def test_list_renders_html_with_query_param(web):
    client, _ = web
    r = client.get("/engagement/?html=1", headers=_h("tok-a"))
    assert r.status_code == 200
    assert "<html" in r.get_data(as_text=True)


def test_list_returns_json_by_default(web):
    client, _ = web
    r = client.get("/engagement/", headers=_h("tok-a"))
    assert r.status_code == 200
    # Should still be JSON when no html opt-in
    assert r.is_json
    assert "items" in r.get_json()


def test_create_via_form_html_redirects_to_detail(web):
    client, _ = web
    r = client.post(
        "/engagement/?html=1",
        headers=_h("tok-a"),
        data={"client_id": "acme", "standard_of_value": "ifrs13"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/engagement/" in r.headers["Location"]
    assert "html=1" in r.headers["Location"]


def test_detail_renders_html(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h("tok-a"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.get(f"/engagement/{eng_id}?html=1", headers=_h("tok-a"))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "<html" in body
    assert eng_id[:8] in body
    assert "Snapshots" in body


def test_detail_shows_allowed_transitions(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h("tok-a"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.get(f"/engagement/{eng_id}?html=1", headers=_h("tok-a"))
    body = r.get_data(as_text=True)
    # open → review is allowed for analyst
    assert "Move to review" in body
    # open → signed is NOT allowed (must go via review)
    assert "Move to signed" not in body


def test_upload_via_form_html_redirects_back_to_detail(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h("tok-a"),
        json={"client_id": "c"},
    ).get_json()["id"]
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
    r = client.post(
        f"/engagement/{eng_id}/upload?html=1",
        headers=_h("tok-a"),
        data={"file": (io.BytesIO(buf.getvalue()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert f"/engagement/{eng_id}" in r.headers["Location"]


def test_transition_via_form_html_redirects(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h("tok-a"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.post(
        f"/engagement/{eng_id}/transition?html=1",
        headers=_h("tok-a"),
        data={"new_status": "review", "expected_version": "0"},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_xss_safe_in_html_render(web):
    """Client ID containing HTML special chars must not break the page."""
    client, _ = web
    payload_client_id = "<script>alert('xss')</script>"
    client.post(
        "/engagement/", headers=_h("tok-a"),
        json={"client_id": payload_client_id},
    )
    r = client.get("/engagement/?html=1", headers=_h("tok-a"))
    body = r.get_data(as_text=True)
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body
