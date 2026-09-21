"""W4.6 — /whatif HTMX partial endpoint tests."""

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
        p = Path(fh.name)
    store = EngagementStore(db_path=p)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users))
    yield app.test_client(), store
    p.unlink(missing_ok=True)


def _h():
    return {"Authorization": "Bearer tok-a"}


def _upload_demo_cap_table(client, eng_id):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cap Table"
    ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date",
               "LP Multiple", "LP Type", "Seniority", "Anti-Dilution"])
    ws.append(["Common", "common", 5_000_000, 0.01, "2020-01-01",
               "", "", "", ""])
    ws.append(["Series A", "preferred", 1_000_000, 1.00, "2024-01-01",
               1.0, "non_participating", 1, "broad_based_weighted_average"])
    buf = io.BytesIO()
    wb.save(buf)
    client.post(
        f"/engagement/{eng_id}/upload", headers=_h(),
        data={"file": (io.BytesIO(buf.getvalue()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )


def test_whatif_returns_empty_partial_when_no_snapshot(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h(),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.post(f"/engagement/{eng_id}/whatif?html=1", headers=_h(),
                     data={})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "What-if scenario" in body
    assert "Adjust a share count" in body


def test_whatif_computes_scenario_after_upload(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h(),
        json={"client_id": "c"},
    ).get_json()["id"]
    _upload_demo_cap_table(client, eng_id)
    # No overrides → scenario equals baseline (no "changed" entries)
    r = client.post(f"/engagement/{eng_id}/whatif?html=1", headers=_h(),
                     data={})
    body = r.get_data(as_text=True)
    assert "What-if scenario" in body
    assert "BP" in body  # the breakpoint table header
    assert "Inputs changed" not in body


def test_whatif_override_share_count_appears_in_changed_list(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h(),
        json={"client_id": "c"},
    ).get_json()["id"]
    _upload_demo_cap_table(client, eng_id)
    r = client.post(
        f"/engagement/{eng_id}/whatif?html=1", headers=_h(),
        data={"shares_Series A": "2000000"},
    )
    body = r.get_data(as_text=True)
    assert "Series A shares" in body
    assert "1,000,000 → 2,000,000" in body


def test_whatif_lp_mult_override_appears_in_changed_list(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h(),
        json={"client_id": "c"},
    ).get_json()["id"]
    _upload_demo_cap_table(client, eng_id)
    r = client.post(
        f"/engagement/{eng_id}/whatif?html=1", headers=_h(),
        data={"lp_mult_Series A": "2.0"},
    )
    body = r.get_data(as_text=True)
    assert "LP mult" in body
    assert "1.0× → 2.0×" in body
