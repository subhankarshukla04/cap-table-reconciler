"""Regression tests for SYSTEM_AUDIT_WAVE_7.md fixes.

One test per blocker + per fix-now major. Test names encode the audit
finding code (B-W7-1, B-W7-2, M-W7-1..M-W7-4, m-W7-5, m-W7-6) so a
future failure traces back to the exact section.
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.cookie_auth import attach_login_blueprint
from src.diff_workpaper import build_diff_workpaper_xlsx, _safe_cell
from src.engagement import (
    EngagementError,
    EngagementStore,
    SnapshotNotFound,
)
from src.engagement_bundle import build_engagement_bundle
from src.engagement_routes import (
    MAX_DIFF_SNAPSHOTS,
    attach_engagement_blueprint,
)
from src.identity import Role, StaticUserProvider, User
from src.rate_limit import ExportRateLimiter
from src.token_deny import TokenDenyList


# ---- fixture --------------------------------------------------------------


@pytest.fixture
def web():
    paths = []
    for _ in range(4):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
            paths.append(Path(fh.name))
    eng_p, ex_p, cp_p, dn_p = paths
    store = EngagementStore(db_path=eng_p)
    export_limiter = ExportRateLimiter(db_path=ex_p, soft_limit=50, hard_limit=100)
    # tight compute limiter so the rate-limit test hits the cap quickly
    compute_limiter = ExportRateLimiter(db_path=cp_p, soft_limit=2, hard_limit=3)
    deny_list = TokenDenyList(db_path=dn_p)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SESSION_SECRET_KEY"] = b"x" * 32
    app.config["TOKEN_DENY_LIST"] = deny_list
    users = {
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
        "tok-p": User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
    }
    provider = StaticUserProvider(users)
    attach_engagement_blueprint(app, store, provider,
                                 export_limiter=export_limiter,
                                 compute_limiter=compute_limiter)
    attach_login_blueprint(app, identity_provider=provider)
    yield app.test_client(), store
    deny_list.close()
    for p in paths:
        p.unlink(missing_ok=True)


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _xlsx_bytes(shares_a: int) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cap Table"
    ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date",
               "LP Multiple", "LP Type", "Seniority", "Anti-Dilution"])
    ws.append(["Common", "common", 5_000_000, 0.01, "2020-01-01",
               "", "", "", ""])
    ws.append(["Series A", "preferred", shares_a, 1.00, "2024-01-01",
               1.0, "non_participating", 1, "broad_based_weighted_average"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _new_engagement(client, tok="tok-a"):
    r = client.post("/engagement/", headers=_bearer(tok),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    return r.get_json()["id"]


def _upload(client, eng_id, shares_a, change_note=None, expected_version=0,
            tok="tok-a"):
    data = {
        "file": (io.BytesIO(_xlsx_bytes(shares_a)), "demo.xlsx"),
        "expected_version": str(expected_version),
    }
    if change_note is not None:
        data["change_note"] = change_note
    return client.post(
        f"/engagement/{eng_id}/upload", headers=_bearer(tok),
        data=data, content_type="multipart/form-data",
    )


# =============================================================================
# B-W7-1: redaction drops change_note from every consumer
# =============================================================================


def test_bw71_redaction_zeros_change_note_in_db(web):
    """Partner redaction MUST zero change_note + source_filename
    atomically with the cap_table sentinel."""
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000,
            change_note="PII: investor mary@example.com paid 1.5M")
    snap = store.list_snapshots(eng_id)[0]
    assert snap.change_note  # before redaction
    assert snap.source_filename  # before redaction
    store.redact_snapshot_pii(
        actor=User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        snapshot_id=snap.id,
        request_reference="test-req",
        legal_basis="PDPA §13",
    )
    snap_after = store.get_snapshot(snap.id)
    assert snap_after.redacted is True
    assert snap_after.change_note is None
    assert snap_after.source_filename is None


def test_bw71_timeline_json_hides_change_note_for_redacted(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000,
            change_note="initial cap from charter")
    snap = store.list_snapshots(eng_id)[0]
    store.redact_snapshot_pii(
        actor=User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        snapshot_id=snap.id,
        request_reference="t", legal_basis="t",
    )
    r = client.get(f"/engagement/{eng_id}/snapshots", headers=_bearer("tok-a"))
    payload = r.get_json()
    assert payload[0]["redacted"] is True
    assert payload[0]["change_note"] is None
    assert payload[0]["source_filename"] is None


def test_bw71_diff_json_hides_change_note_for_redacted(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000,
            change_note="initial PII text", expected_version=0)
    _upload(client, eng_id, 1_500_000,
            change_note="series C closing", expected_version=1)
    snap_to_redact = store.list_snapshots(eng_id)[0]
    store.redact_snapshot_pii(
        actor=User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        snapshot_id=snap_to_redact.id,
        request_reference="t", legal_basis="t",
    )
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    r = client.get(f"/engagement/{eng_id}/diff?{qs}", headers=_bearer("tok-a"))
    snaps = r.get_json()["snapshots"]
    notes = [s["change_note"] for s in snaps]
    assert notes[0] is None  # redacted
    assert notes[1] == "series C closing"


def test_bw71_diff_html_does_not_leak_change_note_for_redacted(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000,
            change_note="investor mary@example.com paid 1.5M")
    _upload(client, eng_id, 1_500_000,
            change_note="clean public note", expected_version=1)
    snap_to_redact = store.list_snapshots(eng_id)[0]
    store.redact_snapshot_pii(
        actor=User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        snapshot_id=snap_to_redact.id,
        request_reference="t", legal_basis="t",
    )
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    r = client.get(f"/engagement/{eng_id}/diff?html=1&{qs}",
                   headers=_bearer("tok-a"))
    body = r.get_data(as_text=True)
    assert "mary@example.com" not in body
    # clean note still rendered (non-redacted snapshot)
    assert "clean public note" in body


def test_bw71_xlsx_workpaper_does_not_leak_change_note_for_redacted(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000,
            change_note="investor mary@example.com paid 1.5M")
    _upload(client, eng_id, 1_500_000,
            change_note="ok note", expected_version=1)
    redact_id = store.list_snapshots(eng_id)[0].id
    store.redact_snapshot_pii(
        actor=User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        snapshot_id=redact_id,
        request_reference="t", legal_basis="t",
    )
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    r = client.get(f"/engagement/{eng_id}/diff.xlsx?{qs}",
                   headers=_bearer("tok-a"))
    assert r.status_code == 200
    # The xlsx is a zip; grep the contained xml for the PII string.
    z = zipfile.ZipFile(io.BytesIO(r.get_data()))
    all_text = "".join(
        z.read(name).decode("utf-8", errors="ignore")
        for name in z.namelist() if name.endswith(".xml")
    )
    assert "mary@example.com" not in all_text


def test_mw74_bundle_does_not_leak_change_note_for_redacted(web):
    """M-W7-4: the bundle is the Big-4 deliverable; PII must not survive
    redaction into the zip."""
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000,
            change_note="investor mary@example.com paid 1.5M")
    redact_id = store.list_snapshots(eng_id)[0].id
    store.redact_snapshot_pii(
        actor=User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        snapshot_id=redact_id,
        request_reference="t", legal_basis="t",
    )
    blob = build_engagement_bundle(store, eng_id)
    z = zipfile.ZipFile(io.BytesIO(blob))
    snap_json = z.read(f"snapshots/{redact_id}.json").decode("utf-8")
    parsed = json.loads(snap_json)
    assert parsed["redacted"] is True
    assert parsed["change_note"] is None
    assert parsed["source_filename"] is None
    assert "mary@example.com" not in snap_json


# =============================================================================
# B-W7-2 + m-W7-2: input validation on change_note
# =============================================================================


def test_bw72_upload_rejects_control_char_in_change_note(web):
    client, _ = web
    eng_id = _new_engagement(client)
    r = _upload(client, eng_id, 1_000_000, change_note="pre\x01post")
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "change-note-illegal-character"


def test_bw72_upload_rejects_nul_in_change_note(web):
    client, _ = web
    eng_id = _new_engagement(client)
    r = _upload(client, eng_id, 1_000_000, change_note="\x00")
    assert r.status_code == 400


def test_mw72_upload_rejects_change_note_over_32767_chars(web):
    client, _ = web
    eng_id = _new_engagement(client)
    r = _upload(client, eng_id, 1_000_000, change_note="x" * 32768)
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "change-note-too-long"


def test_bw72_xlsx_sanitizer_strips_illegal_chars():
    """Defense in depth: even if a legacy snapshot somehow holds illegal
    chars, the workpaper builder doesn't crash."""
    assert _safe_cell("pre\x01\x02post") == "prepost"
    assert _safe_cell("\x00") == ""
    assert _safe_cell("normal text") == "normal text"
    # newline + tab + cr are PRESERVED (Excel accepts them).
    assert _safe_cell("a\nb\tc\rd") == "a\nb\tc\rd"
    # 32767 cap
    assert len(_safe_cell("x" * 40000)) == 32767


# =============================================================================
# M-W7-1: /diff consumes the compute limiter
# =============================================================================


def test_mw71_diff_consumes_compute_limiter(web):
    """compute_limiter soft=2, hard=3 in fixture. After 2 successful diff
    calls the third returns 429 compute-rate-limit."""
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000, expected_version=0)
    _upload(client, eng_id, 1_500_000, expected_version=1)
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    # Two allowed calls.
    assert client.get(f"/engagement/{eng_id}/diff?{qs}",
                      headers=_bearer("tok-a")).status_code == 200
    assert client.get(f"/engagement/{eng_id}/diff?{qs}",
                      headers=_bearer("tok-a")).status_code == 200
    # Third call → 429.
    r = client.get(f"/engagement/{eng_id}/diff?{qs}", headers=_bearer("tok-a"))
    assert r.status_code == 429
    assert r.get_json()["error_code"] == "compute-rate-limit"


def test_mw71_diff_hard_limit_writes_audit_event(web):
    """Hard limit boundary writes compute_burst_alert."""
    from src.engagement import AuditEventType
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000, expected_version=0)
    _upload(client, eng_id, 1_500_000, expected_version=1)
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    for _ in range(3):  # hard limit = 3 in fixture
        client.get(f"/engagement/{eng_id}/diff?{qs}", headers=_bearer("tok-a"))
    events = store.list_audit_events(eng_id)
    bursts = [e for e in events
              if e.event_type == AuditEventType.compute_burst_alert]
    assert bursts
    # Confirm the alert payload identifies the diff route.
    assert any(json.loads(e.payload_json).get("route") == "diff" for e in bursts)


# =============================================================================
# M-W7-2: snap dedupe + cap
# =============================================================================


def test_mw72_diff_dedupes_repeated_snap_ids(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000, expected_version=0)
    _upload(client, eng_id, 1_500_000, expected_version=1)
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    # Repeat each id 5x in the query string.
    qs = "&".join(f"snap={sid}" for sid in snap_ids * 5)
    r = client.get(f"/engagement/{eng_id}/diff?{qs}", headers=_bearer("tok-a"))
    assert r.status_code == 200
    # Response should carry exactly 2 snapshots, not 10.
    assert len(r.get_json()["snapshots"]) == 2


def test_mw72_diff_rejects_more_than_max_unique_ids(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000, expected_version=0)
    # Submit MAX+1 unique fake ids (caller never reaches snapshot lookup).
    fake_ids = [f"fake-{i:04d}" for i in range(MAX_DIFF_SNAPSHOTS + 1)]
    qs = "&".join(f"snap={sid}" for sid in fake_ids)
    r = client.get(f"/engagement/{eng_id}/diff?{qs}", headers=_bearer("tok-a"))
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "diff-too-many-snapshots"


def test_mw72_xlsx_route_also_caps_snap_count(web):
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000, expected_version=0)
    fake_ids = [f"fake-{i:04d}" for i in range(MAX_DIFF_SNAPSHOTS + 5)]
    qs = "&".join(f"snap={sid}" for sid in fake_ids)
    r = client.get(f"/engagement/{eng_id}/diff.xlsx?{qs}",
                   headers=_bearer("tok-a"))
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "diff-too-many-snapshots"


# =============================================================================
# M-W7-3 + m-W7-6: HTML/JSON content negotiation + SnapshotNotFound
# =============================================================================


def test_mw73_diff_error_renders_html_when_html_requested(web):
    """HTMX form submit with only one snapshot ticked must get the
    engagement/error.html page, not raw JSON."""
    client, _ = web
    eng_id = _new_engagement(client)
    r = client.get(f"/engagement/{eng_id}/diff?html=1&snap=any",
                   headers=_bearer("tok-a"))
    assert r.status_code == 400
    assert "text/html" in r.headers.get("Content-Type", "")
    body = r.get_data(as_text=True)
    assert "diff-needs-two-snapshots" in body


def test_mw73_unknown_snapshot_id_returns_404_snapshot_not_found(web):
    """Bad snap id returns the dedicated error code, not the generic
    engagement-error catch-all (m-W7-6)."""
    client, store = web
    eng_id = _new_engagement(client)
    _upload(client, eng_id, 1_000_000, expected_version=0)
    real_id = store.list_snapshots(eng_id)[0].id
    r = client.get(
        f"/engagement/{eng_id}/diff?snap={real_id}&snap=does-not-exist",
        headers=_bearer("tok-a"),
    )
    assert r.status_code == 404
    assert r.get_json()["error_code"] == "snapshot-not-found"


def test_mw76_get_snapshot_raises_snapshot_not_found(web):
    """The store now raises the dedicated subclass."""
    _, store = web
    with pytest.raises(SnapshotNotFound):
        store.get_snapshot("does-not-exist")


def test_mw76_snapshot_not_found_subclass_carries_404_error_code():
    """The error-code-and-status contract is stable per spec §9.6."""
    e = SnapshotNotFound("snapshot zzz not found")
    assert e.error_code == "snapshot-not-found"
    assert e.http_status == 404
    assert isinstance(e, EngagementError)
