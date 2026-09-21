"""End-to-end route smoke tests with Flask's test client.

Covers the full surface so a deployment regression is caught immediately:
- /            (form renders)
- /resolve     (POST renders verdict)
- /verdict/<f> (fixture renders)
- /batch       (form renders)
- /batch/run   (CSV uploads, returns Excel)
- /batch/sample(CSV downloads)
- /export/xlsx (POST returns Excel)
- /export/xlsx/<f>
- /pdf/<f>
- POST /pdf    (returns PDF)
- /print/<f>
- /sources
- /healthz     (returns rich JSON)
- /missing     (404 renders error page)
"""

from __future__ import annotations

import io

import pytest

import app as flask_app  # type: ignore[no-redef]


@pytest.fixture()
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"ESOP Atlas" in r.data


def test_resolve_post_renders_verdict(client):
    r = client.post(
        "/resolve",
        data={
            "parent_jurisdiction": "SG",
            "employee_jurisdiction": "IN",
            "event": "exercise",
            "tax_status": "resident",
            "fmv_at_event": "0.50",
            "exercise_price": "0.10",
            "options_in_event": "4000",
        },
    )
    assert r.status_code == 200
    assert b"Primary rule" in r.data or b"primary" in r.data.lower()


@pytest.mark.parametrize("fixture", [
    "praxis", "pelaut", "solstice", "atlas_corp", "avalon_uk", "horizon_hk", "zenith_ae",
])
def test_verdict_scenario_route(client, fixture):
    r = client.get(f"/verdict/{fixture}")
    assert r.status_code == 200, f"{fixture}: {r.status_code}"
    assert len(r.data) > 1000


def test_batch_form_renders(client):
    r = client.get("/batch")
    assert r.status_code == 200
    assert b"Batch" in r.data
    assert b"CSV" in r.data


def test_batch_sample_csv_downloads(client):
    r = client.get("/batch/sample")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    body = r.data.decode("utf-8")
    assert "parent_jurisdiction" in body
    assert "AE" in body  # sample includes a UAE row


def test_batch_run_with_valid_csv_returns_excel(client):
    csv_body = (
        "employee_name,parent_jurisdiction,employee_jurisdiction,event,tax_status,"
        "grant_date,vesting_date,event_date,fmv_at_event,exercise_price,options_in_event\n"
        "Test,SG,IN,exercise,resident,2024-01-01,2025-01-01,2026-04-01,0.50,0.10,4000\n"
    )
    r = client.post(
        "/batch/run",
        data={"csv": (io.BytesIO(csv_body.encode()), "test.csv")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert r.data[:2] == b"PK"  # xlsx is a zip


def test_batch_run_with_no_file_shows_error(client):
    r = client.post("/batch/run", data={}, content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"No file uploaded" in r.data


def test_batch_run_with_malformed_csv_shows_error(client):
    csv_body = "wrong,columns\nfoo,bar\n"
    r = client.post(
        "/batch/run",
        data={"csv": (io.BytesIO(csv_body.encode()), "bad.csv")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert b"missing required columns" in r.data


def test_xlsx_export_post(client):
    r = client.post(
        "/export/xlsx",
        data={
            "parent_jurisdiction": "SG",
            "employee_jurisdiction": "IN",
            "event": "exercise",
            "tax_status": "resident",
            "fmv_at_event": "0.50",
            "exercise_price": "0.10",
            "options_in_event": "4000",
        },
    )
    assert r.status_code == 200
    assert r.data[:2] == b"PK"


@pytest.mark.parametrize("fixture", ["praxis", "zenith_ae", "horizon_hk"])
def test_xlsx_export_scenario(client, fixture):
    r = client.get(f"/export/xlsx/{fixture}")
    assert r.status_code == 200
    assert r.data[:2] == b"PK"


@pytest.mark.parametrize("fixture", ["praxis", "zenith_ae", "horizon_hk"])
def test_pdf_scenario(client, fixture):
    r = client.get(f"/pdf/{fixture}")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF-")


def test_pdf_post_route(client):
    r = client.post(
        "/pdf",
        data={
            "parent_jurisdiction": "AE",
            "employee_jurisdiction": "IN",
            "event": "exercise",
            "tax_status": "resident",
            "fmv_at_event": "6.0",
            "exercise_price": "1.0",
            "options_in_event": "10000",
        },
    )
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")


def test_print_route_renders_html(client):
    r = client.get("/print/praxis")
    assert r.status_code == 200
    assert b"<html" in r.data.lower() or b"<!doctype" in r.data.lower()


def test_sources_route_lists_every_rule(client):
    r = client.get("/sources")
    assert r.status_code == 200
    assert b"hk.hk.exercise.resident" in r.data
    assert b"ae.ae.exercise.any" in r.data
    assert b"Federal Decree-Law" in r.data or b"Decree-Law" in r.data


def test_healthz_returns_rich_status(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["corpus_size"] >= 80
    assert set(body["jurisdictions"]) >= {"SG", "IN", "ID", "US", "UK", "HK", "AE"}
    assert body["rules_by_jurisdiction"]
    assert "praxis" in body["fixtures"]
    assert "version" in body


def test_404_renders_friendly_page(client):
    r = client.get("/verdict/no_such_fixture")
    assert r.status_code == 404
    assert b"404" in r.data


def test_404_xlsx_unknown_scenario(client):
    r = client.get("/export/xlsx/no_such_fixture")
    assert r.status_code == 404


def test_404_pdf_unknown_scenario(client):
    r = client.get("/pdf/no_such_fixture")
    assert r.status_code == 404
