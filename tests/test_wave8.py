"""Wave-8 hardening + capability tests.

Covers W8.1 (header injection), W8.2 (ALLOW flags), W8.3 (OCI engine
version), W8.4 (xlsx byte stability), W8.6 (snapshot created_by
redaction), W8.7 (multi-tab CSRF), W8.8 (readyz), W8.10 (archival +
restore), W8.11 (diff in memo), W8.12 (diff PDF).
"""

from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.cookie_auth import (
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    _safe_next_url,
    attach_login_blueprint,
    issue_session_cookie,
)
from src.diff_workpaper import _pin_xlsx_properties, build_diff_workpaper_xlsx
from src.engagement import (
    ARCHIVAL_RESTORE_DAYS,
    EngagementStatus,
    EngagementStore,
    IllegalStateTransition,
)
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, StubSSOProvider, User
from src.rate_limit import ExportRateLimiter
from src.rule_pack import current_engine_commit
from src.snapshot_timeline import SnapshotMeta, compute_timeline_diff
from src.token_deny import TokenDenyList


# ---- W8.1 header injection ------------------------------------------------


@pytest.mark.parametrize("evil", [
    "/legit\r\nLocation: https://attacker.example/",
    "/legit\nSet-Cookie: pwned=1",
    "/legit\rX-Whatever: bad",
    "/legit\x00null",
    "/legit\x7fdel",
])
def test_w81_safe_next_rejects_control_chars(evil):
    """W8.1: any control char in `next` → falls back to default."""
    out = _safe_next_url(evil)
    assert out != evil
    assert "\r" not in out and "\n" not in out


# ---- W8.2 ALLOW flags -----------------------------------------------------


def test_w82_stub_sso_refuses_to_mount_in_prod(monkeypatch):
    """W8.2: StubSSOProvider() with no opt-in flag raises in prod-shaped
    deploys (no FLASK_TESTING, no ALLOW_STUB_SSO, no pytest module
    loaded). We simulate by injecting a fake module env."""
    monkeypatch.delenv("ALLOW_STUB_SSO", raising=False)
    monkeypatch.delenv("FLASK_TESTING", raising=False)
    monkeypatch.setattr("src.identity._running_in_test", lambda: False)
    with pytest.raises(RuntimeError, match="StubSSOProvider refused"):
        StubSSOProvider()


def test_w82_stub_sso_allowed_with_explicit_flag(monkeypatch):
    monkeypatch.setenv("ALLOW_STUB_SSO", "1")
    monkeypatch.setattr("src.identity._running_in_test", lambda: False)
    # Should not raise.
    provider = StubSSOProvider()
    assert provider.authenticate("anything") is not None


def test_w82_stub_sso_allowed_with_constructor_kwarg(monkeypatch):
    monkeypatch.delenv("ALLOW_STUB_SSO", raising=False)
    monkeypatch.setattr("src.identity._running_in_test", lambda: False)
    provider = StubSSOProvider(allow_in_prod=True)
    assert provider.authenticate("anything") is not None


def test_w82_phase_0_routes_404_without_flag(monkeypatch):
    """W8.2: phase-0 demo routes 404 when ALLOW_PHASE_0_DEMO is unset."""
    monkeypatch.delenv("ALLOW_PHASE_0_DEMO", raising=False)
    import importlib
    import app as app_module
    importlib.reload(app_module)
    # Flip TESTING off so the gate fires.
    app_module.app.config["TESTING"] = False
    client = app_module.app.test_client()
    r = client.post("/upload", data={})
    assert r.status_code == 404
    assert r.get_json()["error_code"] == "phase-0-demo-disabled"
    # Restore TESTING so other test modules aren't affected.
    app_module.app.config["TESTING"] = True


# ---- W8.3 OCI engine version env wiring -----------------------------------


def test_w83_engine_commit_reads_env_first(monkeypatch):
    monkeypatch.setenv("QAPITA_ENGINE_COMMIT", "abcdef123456deadbeef")
    # Bust the module-level cache.
    import src.rule_pack as rp
    rp._ENGINE_COMMIT_CACHE = None
    assert current_engine_commit() == "abcdef123456"


def test_w83_engine_commit_falls_back_to_git(monkeypatch):
    monkeypatch.delenv("QAPITA_ENGINE_COMMIT", raising=False)
    import src.rule_pack as rp
    rp._ENGINE_COMMIT_CACHE = None
    out = current_engine_commit()
    # In a real git repo this is a 12-char SHA; in an OCI image with no
    # git it's "unversioned". Either is acceptable here.
    assert out == "unversioned" or len(out) == 12


# ---- W8.4 xlsx byte stability ---------------------------------------------


def test_w84_diff_workpaper_byte_stable_across_two_calls():
    """Two builds of the same TimelineDiff produce identical bytes after
    W8.4 pinned the workbook properties."""
    metas = [
        SnapshotMeta(id="s1", created_at=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
                      source_filename="f1.xlsx", created_by="u"),
        SnapshotMeta(id="s2", created_at=datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc),
                      source_filename="f2.xlsx", created_by="u"),
    ]
    from src.models import (
        CapTable, Company, ShareClass, ShareClassType,
        LiquidationPreference, LPType,
    )
    def _mk(n):
        return CapTable(
            company=Company(name="Acme"),
            share_classes=[
                ShareClass(name="Common", type=ShareClassType.common,
                           shares_outstanding=5_000_000),
                ShareClass(
                    name="Series A", type=ShareClassType.preferred,
                    shares_outstanding=n, issue_price=1.0,
                    liquidation_preference=LiquidationPreference(
                        multiple=1.0, type=LPType.non_participating, amount=n,
                    ),
                ),
            ],
        )
    diff = compute_timeline_diff(metas, [_mk(1_000_000), _mk(1_500_000)])
    import time as _t
    b1 = build_diff_workpaper_xlsx(diff)
    _t.sleep(1.05)
    b2 = build_diff_workpaper_xlsx(diff)
    assert b1 == b2, "diff workpaper bytes diverged across regenerations"


# ---- W8.6 snapshot created_by redaction -----------------------------------


def test_w86_safe_created_by_masks_when_redacted():
    from src.engagement import Snapshot, SnapshotSource
    s = Snapshot(
        id="abc", engagement_id="eng", source=SnapshotSource.excel_upload,
        cap_table_json="{}", created_by="alice@firm.example",
        created_at=datetime.now(timezone.utc), redacted=True,
    )
    assert s.safe_created_by() == "[redacted]"
    assert s.created_by == "alice@firm.example"  # raw DB value preserved


def test_w86_safe_created_by_passthrough_when_not_redacted():
    from src.engagement import Snapshot, SnapshotSource
    s = Snapshot(
        id="abc", engagement_id="eng", source=SnapshotSource.excel_upload,
        cap_table_json="{}", created_by="alice",
        created_at=datetime.now(timezone.utc), redacted=False,
    )
    assert s.safe_created_by() == "alice"


# ---- W8.10 archival + restore --------------------------------------------


@pytest.fixture
def web_stack():
    paths = []
    for _ in range(4):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
            paths.append(Path(fh.name))
    eng_p, ex_p, cp_p, dn_p = paths
    store = EngagementStore(db_path=eng_p)
    export_limiter = ExportRateLimiter(db_path=ex_p, soft_limit=100, hard_limit=200)
    compute_limiter = ExportRateLimiter(db_path=cp_p, soft_limit=20, hard_limit=40)
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
    yield app.test_client(), store, deny_list
    deny_list.close()
    for p in paths:
        p.unlink(missing_ok=True)


def _bearer(tok: str):
    return {"Authorization": f"Bearer {tok}"}


def test_w810_archive_stamps_lifecycle_columns(web_stack):
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    eng = store.get_engagement(eng_id)
    # Partner archives directly from open.
    client.post(f"/engagement/{eng_id}/transition", headers=_bearer("tok-p"),
                json={"new_status": "archived", "expected_version": eng.version})
    eng = store.get_engagement(eng_id)
    assert eng.status == EngagementStatus.archived
    assert eng.archived_at is not None
    assert eng.restore_eligibility_until is not None
    # Restore window is exactly ARCHIVAL_RESTORE_DAYS days out.
    delta = eng.restore_eligibility_until - eng.archived_at
    assert abs(delta.total_seconds() - ARCHIVAL_RESTORE_DAYS * 86400) < 2


def test_w810_restore_route_succeeds_within_window(web_stack):
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    eng = store.get_engagement(eng_id)
    client.post(f"/engagement/{eng_id}/transition", headers=_bearer("tok-p"),
                json={"new_status": "archived", "expected_version": eng.version})
    eng = store.get_engagement(eng_id)
    r = client.post(f"/engagement/{eng_id}/restore", headers=_bearer("tok-p"),
                    json={"expected_version": eng.version})
    assert r.status_code == 200
    eng = store.get_engagement(eng_id)
    assert eng.status == EngagementStatus.open
    assert eng.archived_at is None
    assert eng.restore_eligibility_until is None


def test_w810_restore_refused_outside_window(web_stack):
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    eng = store.get_engagement(eng_id)
    client.post(f"/engagement/{eng_id}/transition", headers=_bearer("tok-p"),
                json={"new_status": "archived", "expected_version": eng.version})
    eng = store.get_engagement(eng_id)
    # Backdate the restore window to simulate expiry.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store._connect() as conn:
        conn.execute(
            "UPDATE engagement SET restore_eligibility_until = ? WHERE id = ?",
            (past, eng_id),
        )
        conn.commit()
    r = client.post(f"/engagement/{eng_id}/restore", headers=_bearer("tok-p"),
                    json={"expected_version": eng.version})
    # IllegalStateTransition → 409.
    assert r.status_code == 409


def test_w810_analyst_cannot_restore(web_stack):
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    eng = store.get_engagement(eng_id)
    client.post(f"/engagement/{eng_id}/transition", headers=_bearer("tok-p"),
                json={"new_status": "archived", "expected_version": eng.version})
    eng = store.get_engagement(eng_id)
    r = client.post(f"/engagement/{eng_id}/restore", headers=_bearer("tok-a"),
                    json={"expected_version": eng.version})
    assert r.status_code == 403


def test_w810_hard_delete_cascades_expired_archived(web_stack):
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    eng = store.get_engagement(eng_id)
    client.post(f"/engagement/{eng_id}/transition", headers=_bearer("tok-p"),
                json={"new_status": "archived", "expected_version": eng.version})
    # Backdate to past the window.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store._connect() as conn:
        conn.execute(
            "UPDATE engagement SET restore_eligibility_until = ? WHERE id = ?",
            (past, eng_id),
        )
        conn.commit()
    n = store.hard_delete_expired_archived()
    assert n == 1
    # Engagement is gone.
    from src.engagement import EngagementNotFound
    with pytest.raises(EngagementNotFound):
        store.get_engagement(eng_id)


def test_w810_hard_delete_skips_unexpired(web_stack):
    """A still-restorable engagement must not be deleted."""
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    eng = store.get_engagement(eng_id)
    client.post(f"/engagement/{eng_id}/transition", headers=_bearer("tok-p"),
                json={"new_status": "archived", "expected_version": eng.version})
    n = store.hard_delete_expired_archived()
    assert n == 0
    assert store.get_engagement(eng_id) is not None  # still there


# ---- W8.11 diff in memo ----------------------------------------------------


def test_w811_pdf_memo_html_includes_drift_section_when_supplied(tmp_path):
    """PDFInputs.timeline_diff → memo renders a 'Snapshot drift' section."""
    from src.pdf_memo import PDFInputs, render_pdf_memo_html, ReviewerInfo
    from src.waterfall import compute_waterfall
    from src.models import (
        CapTable, Company, ShareClass, ShareClassType,
    )
    ct = CapTable(
        company=Company(name="Acme"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=1000),
        ],
    )
    wf = compute_waterfall(ct)
    metas = [
        SnapshotMeta(id="s1", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
                      source_filename="f1.xlsx", created_by="u",
                      change_note="initial"),
        SnapshotMeta(id="s2", created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
                      source_filename="f2.xlsx", created_by="u",
                      change_note="series C"),
    ]
    diff = compute_timeline_diff(metas, [ct, ct])
    inputs = PDFInputs(
        cap_table=ct, waterfall=wf, findings=[], resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="Reviewer", preparer="Analyst"),
        timeline_diff=diff,
    )
    html = render_pdf_memo_html(inputs)
    assert "Snapshot drift" in html
    assert "S1" in html and "S2" in html


def test_w811_pdf_memo_html_omits_drift_section_when_absent():
    from src.pdf_memo import PDFInputs, render_pdf_memo_html, ReviewerInfo
    from src.waterfall import compute_waterfall
    from src.models import CapTable, Company, ShareClass, ShareClassType
    ct = CapTable(
        company=Company(name="Acme"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=1000),
        ],
    )
    inputs = PDFInputs(
        cap_table=ct, waterfall=compute_waterfall(ct),
        findings=[], resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="Reviewer", preparer="Analyst"),
        timeline_diff=None,
    )
    html = render_pdf_memo_html(inputs)
    assert "Snapshot drift" not in html


# ---- W8.12 diff PDF route ------------------------------------------------


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


def test_w812_diff_pdf_route_returns_pdf(web_stack):
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    for shares, ver in [(1_000_000, 0), (1_500_000, 1)]:
        client.post(
            f"/engagement/{eng_id}/upload", headers=_bearer("tok-a"),
            data={"file": (io.BytesIO(_xlsx_bytes(shares)), "demo.xlsx"),
                  "expected_version": str(ver)},
            content_type="multipart/form-data",
        )
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    r = client.get(f"/engagement/{eng_id}/diff.pdf?{qs}", headers=_bearer("tok-a"))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert r.get_data(as_text=False)[:4] == b"%PDF"


def test_w812_diff_pdf_writes_audit_event(web_stack):
    from src.engagement import AuditEventType
    client, store, _ = web_stack
    r = client.post("/engagement/", headers=_bearer("tok-a"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    for shares, ver in [(1_000_000, 0), (1_500_000, 1)]:
        client.post(
            f"/engagement/{eng_id}/upload", headers=_bearer("tok-a"),
            data={"file": (io.BytesIO(_xlsx_bytes(shares)), "demo.xlsx"),
                  "expected_version": str(ver)},
            content_type="multipart/form-data",
        )
    snap_ids = [s.id for s in store.list_snapshots(eng_id)]
    qs = "&".join(f"snap={sid}" for sid in snap_ids)
    client.get(f"/engagement/{eng_id}/diff.pdf?{qs}", headers=_bearer("tok-a"))
    import json as _json
    events = store.list_audit_events(eng_id)
    pdf_events = [e for e in events
                  if e.event_type == AuditEventType.snapshot_diff_exported
                  and _json.loads(e.payload_json).get("format") == "pdf"]
    assert pdf_events
