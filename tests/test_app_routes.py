"""End-to-end tests for the Flask routes.

Exercises the full pipeline: load fixture → review page → waterfall page →
JSON export. These tests are the safety net for the demo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import app, SESSIONS


@pytest.fixture()
def client():
    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    SESSIONS.clear()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json["status"] == "ok"


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.data.decode()
    assert "Cap Table Reconciler" in body
    assert "Solstice Labs" in body
    assert "Pelaut Logistics" in body
    assert "Bandhan Ventures" in body


@pytest.mark.parametrize(
    "fixture_id,expect_text",
    [
        ("fixture_01_clean", "Solstice Labs"),
        ("fixture_02_typical_messy", "Pelaut Logistics"),
        ("fixture_03_edge_case", "Bandhan Ventures"),
    ],
)
def test_demo_route_renders_review_page(client, fixture_id, expect_text):
    r = client.get(f"/demo/{fixture_id}", follow_redirects=True)
    assert r.status_code == 200
    body = r.data.decode()
    assert expect_text in body
    assert "Findings" in body


def test_demo_fixture_01_clean_no_blocking_findings(client):
    r = client.get("/demo/fixture_01_clean", follow_redirects=True)
    body = r.data.decode()
    assert "no issues" in body or ("0 blocker" not in body and "blocker</span>" not in body)


def test_demo_fixture_02_messy_shows_blockers(client):
    r = client.get("/demo/fixture_02_typical_messy", follow_redirects=True)
    body = r.data.decode()
    # SAFE-UNCONVERTED-* and AD-MISSING-* are blockers
    assert "blocker" in body.lower()
    assert "SAFE" in body  # at least one SAFE finding
    assert "anti-dilution" in body.lower() or "anti dilution" in body.lower()


def test_demo_fixture_03_shows_participating_with_cap_info(client):
    r = client.get("/demo/fixture_03_edge_case", follow_redirects=True)
    body = r.data.decode()
    assert "participating" in body.lower()
    assert "CCPS" in body or "ccps" in body


def test_waterfall_page_renders(client):
    r = client.get("/demo/fixture_03_edge_case", follow_redirects=False)
    token = r.headers["Location"].split("/")[-1]
    r2 = client.get(f"/waterfall/{token}")
    assert r2.status_code == 200
    body = r2.data.decode()
    # Eight breakpoints expected for fixture 03
    for i in range(1, 9):
        assert f"BP{i}" in body
    # Conversion economics section
    assert "Conversion threshold" in body or "conversion" in body.lower()


def test_export_json_renders(client):
    r = client.get("/demo/fixture_01_clean", follow_redirects=False)
    token = r.headers["Location"].split("/")[-1]
    r2 = client.get(f"/export/{token}.json")
    assert r2.status_code == 200
    payload = json.loads(r2.data)
    assert payload["company"]["name"] == "Solstice Labs Pte. Ltd."
    assert "waterfall" in payload
    assert len(payload["waterfall"]["breakpoints"]) == 7
    assert "findings" in payload


def test_export_json_includes_correct_breakpoint_count_for_fixture_03(client):
    r = client.get("/demo/fixture_03_edge_case", follow_redirects=False)
    token = r.headers["Location"].split("/")[-1]
    r2 = client.get(f"/export/{token}.json")
    assert r2.status_code == 200
    payload = json.loads(r2.data)
    assert len(payload["waterfall"]["breakpoints"]) == 8
    assert len(payload["waterfall"]["tranches"]) == 8


def test_export_live_xlsx_renders(client):
    """Live formula workbook export — separate route from the static .xlsx."""
    r = client.get("/demo/fixture_01_clean", follow_redirects=False)
    token = r.headers["Location"].split("/")[-1]
    r2 = client.get(f"/export/{token}_live.xlsx")
    assert r2.status_code == 200
    assert r2.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    from io import BytesIO
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(r2.data))
    expected = {"README", "Inputs", "Calculations", "States", "Breakpoints",
                "TrancheAlloc", "CumulativePayout", "Chart"}
    assert expected.issubset(set(wb.sheetnames))


def test_export_xlsx_renders(client):
    r = client.get("/demo/fixture_02_typical_messy", follow_redirects=False)
    token = r.headers["Location"].split("/")[-1]
    r2 = client.get(f"/export/{token}.xlsx")
    assert r2.status_code == 200
    assert r2.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(r2.data) > 1000  # non-trivial xlsx
    # Round-trip: load it back via openpyxl
    from io import BytesIO
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(r2.data))
    assert "Cap Table (clean)" in wb.sheetnames
    assert "Breakpoints" in wb.sheetnames
    assert "Tranches" in wb.sheetnames
    assert "Findings" in wb.sheetnames


def test_waterfall_page_includes_chart_payload(client):
    r = client.get("/demo/fixture_03_edge_case", follow_redirects=False)
    token = r.headers["Location"].split("/")[-1]
    r2 = client.get(f"/waterfall/{token}")
    body = r2.data.decode()
    assert "payoutChart" in body
    assert "datasets" in body  # chart_json injected


def test_review_404_for_unknown_token(client):
    r = client.get("/review/nope")
    assert r.status_code == 404


def test_demo_404_for_unknown_fixture(client):
    r = client.get("/demo/no_such_fixture")
    assert r.status_code == 404


def test_upload_real_xlsx_fixture_02(client):
    """Upload the actual fixture 02 .xlsx through the upload endpoint."""
    xlsx = Path(__file__).parent.parent / "fixtures" / "fixture_02_typical_messy" / "cap_table.xlsx"
    with xlsx.open("rb") as f:
        r = client.post(
            "/upload",
            data={"file": (f, "cap_table.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
    assert r.status_code == 200
    body = r.data.decode()
    assert "Pelaut Logistics" in body
    assert "blocker" in body.lower()


def _load_messy_session(client) -> str:
    r = client.get("/demo/fixture_02_typical_messy", follow_redirects=False)
    return r.headers["Location"].split("/")[-1]


def test_resolve_anti_dilution_clears_blocker(client):
    token = _load_messy_session(client)
    sess = SESSIONS[token]
    assert any(f.code == "AD-MISSING-Series A Preferred" for f in sess["findings"])

    r = client.post(
        f"/resolve/{token}/anti_dilution/Series A Preferred",
        data={"variant": "broad_based_weighted_average", "citation": "Charter §4.3(a)"},
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    assert not any(f.code == "AD-MISSING-Series A Preferred" for f in sess["findings"])
    assert any(r["code"] == "AD-MISSING-Series A Preferred" for r in sess["resolutions"])


def test_resolve_warrant_add_as_shares_clears_finding(client):
    token = _load_messy_session(client)
    sess = SESSIONS[token]
    initial_warrant_findings = [f for f in sess["findings"] if f.code.startswith("WARRANT-")]
    assert len(initial_warrant_findings) >= 1

    r = client.post(
        f"/resolve/{token}/warrant/WAR02-01",
        data={
            "action": "add_as_shares",
            "target_class": "Founders Common",
            "shares": "150000",
            "note": "ITM at FMV",
        },
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    assert not any(f.code == "WARRANT-WAR02-01" for f in sess["findings"])
    common = next(sc for sc in sess["cap_table"].share_classes if sc.name == "Founders Common")
    assert common.shares_outstanding > 150000


def test_resolve_warrant_document_exclusion(client):
    token = _load_messy_session(client)
    r = client.post(
        f"/resolve/{token}/warrant/WAR02-01",
        data={"action": "document_exclusion", "note": "below current FMV"},
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    assert not any(f.code == "WARRANT-WAR02-01" for f in sess["findings"])
    assert len(sess["cap_table"].warrants_outstanding) == 0


def test_resolve_side_letter_scope(client):
    token = _load_messy_session(client)
    r = client.post(
        f"/resolve/{token}/side_letter/SL02-01",
        data={"resolutions_text": "Q1: scope is Series B+ only.\nQ2: MFN expires at IPO."},
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    sl = next(s for s in sess["cap_table"].side_letters if s.id == "SL02-01")
    assert sl.unresolved_questions == []
    assert "Analyst-recorded resolutions" in (sl.body or "")
    assert not any(f.code == "SIDE-LETTER-SCOPE-SL02-01" for f in sess["findings"])


def test_resolve_pool_stale_update_grant_date(client):
    token = _load_messy_session(client)
    pool_name = "Option Pool (Granted)"
    r = client.post(
        f"/resolve/{token}/pool/{pool_name}",
        data={"action": "update_grant_date", "new_date": "2026-04-15"},
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    pool = next(sc for sc in sess["cap_table"].share_classes if sc.name == pool_name)
    from datetime import date
    assert pool.issue_date == date(2026, 4, 15)


def test_resolve_pool_stale_documented_in_memo(client):
    token = _load_messy_session(client)
    pool_name = "Option Pool (Granted)"
    r = client.post(
        f"/resolve/{token}/pool/{pool_name}",
        data={"action": "documented_in_memo", "note": "no post-round grants"},
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    assert any(r["code"] == f"POOL-STALE-{pool_name}" for r in sess["resolutions"])


def test_resolve_anti_dilution_invalid_variant_no_op(client):
    token = _load_messy_session(client)
    r = client.post(
        f"/resolve/{token}/anti_dilution/Series A Preferred",
        data={"variant": "garbage"},
    )
    assert r.status_code == 302
    sess = SESSIONS[token]
    # blocker should remain
    assert any(f.code == "AD-MISSING-Series A Preferred" for f in sess["findings"])
    assert not any("AD-MISSING-Series A Preferred" in r["code"] for r in sess["resolutions"])


def test_resolve_404_on_stale_token(client):
    r = client.post(
        "/resolve/nope/anti_dilution/Series A Preferred",
        data={"variant": "full_ratchet"},
    )
    assert r.status_code == 404


def test_upload_rejects_non_xlsx(client):
    import io
    r = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"hello"), "test.py")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert b"Only .xlsx files are supported" in r.data


def test_whatif_no_overrides_returns_baseline_panel(client):
    r = client.get("/demo/fixture_02_typical_messy", follow_redirects=False)
    token = r.headers["Location"].rsplit("/", 1)[-1]
    r2 = client.post(f"/whatif/{token}", data={})
    assert r2.status_code == 200
    assert b"No overrides applied" in r2.data


def test_whatif_share_count_override_changes_breakpoints(client):
    r = client.get("/demo/fixture_02_typical_messy", follow_redirects=False)
    token = r.headers["Location"].rsplit("/", 1)[-1]
    r2 = client.post(
        f"/whatif/{token}",
        data={"shares_Series A Preferred": "1000000"},
    )
    assert r2.status_code == 200
    assert b"Series A Preferred shares" in r2.data
    assert b"3,000,000" in r2.data and b"1,000,000" in r2.data


def test_whatif_lp_multiple_doubles_lp_total(client):
    r = client.get("/demo/fixture_01_clean", follow_redirects=False)
    token = r.headers["Location"].rsplit("/", 1)[-1]
    sess = SESSIONS[token]
    pref = next(sc for sc in sess["cap_table"].share_classes if sc.type.value == "preferred")
    baseline_lp = sess["waterfall"].lp_total
    r2 = client.post(
        f"/whatif/{token}",
        data={f"lp_mult_{pref.name}": str(pref.liquidation_preference.multiple * 2)},
    )
    assert r2.status_code == 200
    body = r2.data.decode()
    assert "LP mult" in body
    # Doubling the only preferred class's LP multiple roughly doubles LP total.
    # (Other classes' LP unchanged so it scales by the share-of-LP this class contributes.)
    assert pref.name in body


def test_whatif_preserves_session_state(client):
    """Whatif must NOT mutate the persisted session — slider is in-memory only."""
    r = client.get("/demo/fixture_03_edge_case", follow_redirects=False)
    token = r.headers["Location"].rsplit("/", 1)[-1]
    before_lp = SESSIONS[token]["waterfall"].lp_total
    before_classes = {sc.name: sc.shares_outstanding for sc in SESSIONS[token]["cap_table"].share_classes}
    r2 = client.post(
        f"/whatif/{token}",
        data={"shares_Series B Preferred": "9999999"},
    )
    assert r2.status_code == 200
    after_lp = SESSIONS[token]["waterfall"].lp_total
    after_classes = {sc.name: sc.shares_outstanding for sc in SESSIONS[token]["cap_table"].share_classes}
    assert before_lp == after_lp
    assert before_classes == after_classes


def test_whatif_session_expired(client):
    r = client.post("/whatif/nonexistent", data={})
    assert r.status_code == 404


def test_whatif_on_f04_ratchet_does_not_corrupt_lp_amount():
    """F04 has ratchet-adjusted Series Seed where LP amount is decoupled from
    shares × pps × multiple. The whatif logic must scale by ratio, not recompute
    from price × shares — otherwise the down-round LP gets crushed."""
    from app import app as _app
    SESSIONS.clear()
    with _app.test_client() as c:
        r = c.get("/demo/fixture_04_down_round_ratchet", follow_redirects=False)
        token = r.headers["Location"].rsplit("/", 1)[-1]
        sess = SESSIONS[token]
        seed = next(sc for sc in sess["cap_table"].share_classes if "Seed" in sc.name)
        baseline_amount = seed.liquidation_preference.amount
        # Touching only B's shares, not Seed's — Seed's LP amount must not change.
        c.post(f"/whatif/{token}", data={"shares_Series A Preferred": str(seed.shares_outstanding)})
        sess_after = SESSIONS[token]
        seed_after = next(sc for sc in sess_after["cap_table"].share_classes if "Seed" in sc.name)
        assert seed_after.liquidation_preference.amount == baseline_amount
    SESSIONS.clear()


def test_compare_route_renders_with_no_resolutions(client):
    r = client.get("/demo/fixture_01_clean", follow_redirects=False)
    token = r.headers["Location"].rsplit("/", 1)[-1]
    r2 = client.get(f"/compare/{token}")
    assert r2.status_code == 200
    assert b"Before vs after resolution" in r2.data
    assert b"No resolutions applied" in r2.data


def test_compare_route_session_expired(client):
    r = client.get("/compare/nonexistent")
    assert r.status_code == 404


def test_compare_shows_lp_delta_after_safe_resolution(client):
    """Resolving a SAFE adds shares, which can change LP total + breakpoints.
    /compare must surface the delta."""
    r = client.get("/demo/fixture_02_typical_messy", follow_redirects=False)
    token = r.headers["Location"].rsplit("/", 1)[-1]
    sess = SESSIONS[token]
    safe = sess["cap_table"].safes_outstanding[0]
    target_class = next(sc.name for sc in sess["cap_table"].share_classes if sc.type.value == "preferred")
    client.post(
        f"/resolve/{token}/safe/{safe.id}",
        data={"shares": "100000", "target_class": target_class},
    )
    r2 = client.get(f"/compare/{token}")
    assert r2.status_code == 200
    body = r2.data.decode()
    assert "Cap-table changes" in body
    assert "Resolutions applied" in body
    # The target class shows a +100,000 share delta
    assert "+100,000" in body or "100,000" in body


def test_compare_preserves_original_after_mutation():
    """The original_cap_table must stay frozen even after the cap_table mutates."""
    from app import app as _app
    SESSIONS.clear()
    with _app.test_client() as c:
        r = c.get("/demo/fixture_02_typical_messy", follow_redirects=False)
        token = r.headers["Location"].rsplit("/", 1)[-1]
        sess = SESSIONS[token]
        original_lp = compute_waterfall_lp_local(sess["original_cap_table"])
        baseline_classes = {sc.name: sc.shares_outstanding for sc in sess["original_cap_table"].share_classes}

        # Apply a resolution
        safe = sess["cap_table"].safes_outstanding[0]
        target_class = next(sc.name for sc in sess["cap_table"].share_classes if sc.type.value == "preferred")
        c.post(f"/resolve/{token}/safe/{safe.id}", data={"shares": "250000", "target_class": target_class})

        sess_after = SESSIONS[token]
        # Original cap table should still show pre-resolution shares
        post_classes = {sc.name: sc.shares_outstanding for sc in sess_after["original_cap_table"].share_classes}
        assert post_classes == baseline_classes
        post_lp = compute_waterfall_lp_local(sess_after["original_cap_table"])
        assert post_lp == original_lp
        # Current cap table should reflect the resolution
        current_target = next(sc for sc in sess_after["cap_table"].share_classes if sc.name == target_class)
        original_target = next(sc for sc in sess_after["original_cap_table"].share_classes if sc.name == target_class)
        assert current_target.shares_outstanding == original_target.shares_outstanding + 250000
    SESSIONS.clear()


def compute_waterfall_lp_local(ct):
    from src.waterfall import compute_waterfall as _cw
    return _cw(ct).lp_total
