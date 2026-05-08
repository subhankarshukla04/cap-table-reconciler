"""
Integration tests: full demo flow per fixture.

For each of the four fixtures, exercise:
  1. /demo/<fixture> — load
  2. /review/<token> — render review
  3. /waterfall/<token> — render waterfall page
  4. /export/<token>.xlsx — static export
  5. /export/<token>_live.xlsx — live formula export
  6. /export/<token>.json — JSON export

Plus PDF intake + diff smoke tests for the new flows.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app import app, SESSIONS

FIXTURES = [
    "fixture_01_clean",
    "fixture_02_typical_messy",
    "fixture_03_edge_case",
    "fixture_04_down_round_ratchet",
]


@pytest.fixture()
def client():
    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    SESSIONS.clear()


@pytest.mark.parametrize("fixture_id", FIXTURES)
def test_full_flow_per_fixture(client, fixture_id):
    # Step 1: load fixture
    r = client.get(f"/demo/{fixture_id}", follow_redirects=False)
    assert r.status_code == 302
    token = r.headers["Location"].split("/")[-1]

    # Step 2: review page
    r = client.get(f"/review/{token}")
    assert r.status_code == 200
    assert b"Cap table" in r.data

    # Step 3: waterfall page
    r = client.get(f"/waterfall/{token}")
    assert r.status_code == 200
    assert b"BP1" in r.data

    # Step 4: static xlsx
    r = client.get(f"/export/{token}.xlsx")
    assert r.status_code == 200
    assert len(r.data) > 1000

    # Step 5: live formula xlsx
    r = client.get(f"/export/{token}_live.xlsx")
    assert r.status_code == 200
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(r.data))
    assert "Inputs" in wb.sheetnames
    assert "Chart" in wb.sheetnames

    # Step 6: JSON
    r = client.get(f"/export/{token}.json")
    assert r.status_code == 200
    import json

    payload = json.loads(r.data)
    assert payload["company"]["name"]
    assert payload["waterfall"]["breakpoints"]


def test_index_lists_all_four_fixtures(client):
    r = client.get("/")
    body = r.data.decode()
    assert "Solstice Labs" in body
    assert "Pelaut Logistics" in body
    assert "Bandhan Ventures" in body
    assert "Surya Foods" in body
    assert "Live formula workbook" in body
    assert "Cap-table snapshot diff" in body


def test_diff_page_links_from_index(client):
    r = client.get("/")
    assert b"Diff" in r.data
    r = client.get("/diff")
    assert r.status_code == 200
