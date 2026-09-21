"""Engagement list / search tests (W3.2)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from flask import Flask

from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    store = EngagementStore(db_path=p)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
        "tok-a2": User(id="u-a2", email="a2@x", role=Role.analyst, display_name="A2"),
        "tok-r": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R"),
        "tok-ro": User(id="u-ro", email="ro@x", role=Role.read_only_auditor, display_name="RO"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users))
    c = app.test_client()
    yield c
    p.unlink(missing_ok=True)


def _h(tok: str):
    return {"Authorization": f"Bearer {tok}"}


def _create(client, tok, client_id="c1", standard="ifrs13", valuation_date=None):
    body = {"client_id": client_id, "standard_of_value": standard}
    if valuation_date:
        body["valuation_date"] = valuation_date
    return client.post("/engagement/", headers=_h(tok), json=body).get_json()


def test_list_paginated_response_shape(client):
    _create(client, "tok-a")
    r = client.get("/engagement/", headers=_h("tok-a"))
    body = r.get_json()
    assert "total" in body and "items" in body
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_list_filter_by_status(client):
    e1 = _create(client, "tok-a")
    e2 = _create(client, "tok-a")
    # Move e2 to review
    client.post(
        f"/engagement/{e2['id']}/transition", headers=_h("tok-a"),
        json={"new_status": "review", "expected_version": 0},
    )
    r = client.get("/engagement/?status=review", headers=_h("tok-a"))
    body = r.get_json()
    ids = [it["id"] for it in body["items"]]
    assert e2["id"] in ids
    assert e1["id"] not in ids


def test_list_filter_by_client_id(client):
    a = _create(client, "tok-a", client_id="acme")
    b = _create(client, "tok-a", client_id="beta")
    r = client.get("/engagement/?client_id=acme", headers=_h("tok-a"))
    ids = [it["id"] for it in r.get_json()["items"]]
    assert a["id"] in ids
    assert b["id"] not in ids


def test_list_filter_by_date_range(client):
    early = _create(client, "tok-a", valuation_date="2024-06-01")
    late = _create(client, "tok-a", valuation_date="2025-03-15")
    r = client.get(
        "/engagement/?date_from=2025-01-01&date_to=2025-12-31",
        headers=_h("tok-a"),
    )
    ids = [it["id"] for it in r.get_json()["items"]]
    assert late["id"] in ids
    assert early["id"] not in ids


def test_list_search_query_matches_client_id(client):
    _create(client, "tok-a", client_id="acme-tech")
    _create(client, "tok-a", client_id="other")
    r = client.get("/engagement/?q=acme", headers=_h("tok-a"))
    items = r.get_json()["items"]
    assert len(items) == 1
    assert items[0]["client_id"] == "acme-tech"


def test_list_pagination_offset_and_limit(client):
    for _ in range(7):
        _create(client, "tok-a")
    r = client.get("/engagement/?limit=3&offset=2", headers=_h("tok-a"))
    body = r.get_json()
    assert body["total"] == 7
    assert body["limit"] == 3
    assert body["offset"] == 2
    assert len(body["items"]) == 3


def test_list_role_scope_analyst_sees_own(client):
    a1 = _create(client, "tok-a")
    a2 = _create(client, "tok-a2")
    r = client.get("/engagement/", headers=_h("tok-a"))
    ids = [it["id"] for it in r.get_json()["items"]]
    assert a1["id"] in ids
    assert a2["id"] not in ids


def test_list_role_scope_read_only_auditor_sees_none(client):
    _create(client, "tok-a")
    r = client.get("/engagement/", headers=_h("tok-ro"))
    body = r.get_json()
    assert body["total"] == 0


def test_list_bad_pagination_returns_400(client):
    r = client.get("/engagement/?limit=nope", headers=_h("tok-a"))
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "bad-pagination"


def test_list_combined_filters(client):
    e_match = _create(client, "tok-a", client_id="acme", standard="ifrs13",
                      valuation_date="2025-01-01")
    e_other = _create(client, "tok-a", client_id="beta", standard="asc820",
                      valuation_date="2025-01-01")
    r = client.get(
        "/engagement/?client_id=acme&standard_of_value=ifrs13",
        headers=_h("tok-a"),
    )
    ids = [it["id"] for it in r.get_json()["items"]]
    assert e_match["id"] in ids
    assert e_other["id"] not in ids
