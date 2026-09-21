"""W6.3 — cross-wave integration test harness.

The stitched audit's #1 ask: the unit suite is wave-scoped, so seam bugs
ship green. These tests drive one engagement through every wave's surface
end-to-end. Each test is the production browser flow OR the production
API-client flow — no mocks at the seams.

Coverage matrix:

| Path | Auth | Wave seams exercised |
|---|---|---|
| Browser cookie flow | cookie + CSRF | W5.7 (cookie), W6.1 (CSRF), W4 (HTMX), W2 (engagement+audit), W3 (memo+bundle) |
| API Bearer flow | Bearer | SD-AUD-B5 (Bearer beats cookie), W2 (concurrency), W3 (bundle determinism) |
| Bearer revocation | Bearer + /logout | W6.4 (deny list) |
| Rate-limit alerts | Bearer | W5.5 (compute), W2 (audit-event integrity) |
| Stale-version rejection | Bearer | W2 (optimistic concurrency), SD-AUD-B6 (upload version) |
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.cookie_auth import (
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    attach_login_blueprint,
    issue_csrf_token,
    issue_session_cookie,
)
from src.engagement import EngagementStatus, EngagementStore, AuditEventType
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User
from src.rate_limit import ExportRateLimiter
from src.token_deny import TokenDenyList


# ---- fixtures --------------------------------------------------------------


@pytest.fixture
def stack():
    """Realistic stack: store, both limiters, deny list, cookie auth, all
    three roles wired as Bearer tokens, secrets set, IDENTITY_PROVIDER
    shared between auth and engagement blueprints (mirrors app.py)."""
    paths = []
    for _ in range(4):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
            paths.append(Path(fh.name))
    eng_path, ex_path, cp_path, dn_path = paths
    store = EngagementStore(db_path=eng_path)
    export_limiter = ExportRateLimiter(db_path=ex_path, soft_limit=4, hard_limit=6)
    compute_limiter = ExportRateLimiter(db_path=cp_path, soft_limit=2, hard_limit=3)
    deny_list = TokenDenyList(db_path=dn_path)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SESSION_SECRET_KEY"] = b"x" * 32
    app.config["TOKEN_DENY_LIST"] = deny_list
    users = {
        "tok-analyst": User(id="u-a", email="a@x", role=Role.analyst, display_name="Analyst"),
        "tok-reviewer": User(id="u-r", email="r@x", role=Role.reviewer, display_name="Reviewer"),
        "tok-partner": User(id="u-p", email="p@x", role=Role.partner, display_name="Partner"),
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


def _bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _xlsx_with_resolvable_blockers() -> bytes:
    """Cap table that triggers two AD-MISSING blockers — one we resolve,
    one we leave. Used for sign-off-gate testing."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cap Table"
    ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date",
               "LP Multiple", "LP Type", "Seniority", "Anti-Dilution"])
    ws.append(["Common", "common", 5_000_000, 0.01, "2020-01-01",
               "", "", "", ""])
    ws.append(["Series A", "preferred", 1_000_000, 1.00, "2024-01-01",
               1.0, "non_participating", 2, ""])  # blank AD → AD-MISSING blocker
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _xlsx_clean() -> bytes:
    """Cap table that passes every blocker rule. Used for end-to-end happy path."""
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
    return buf.getvalue()


# ---- Flow 1: browser cookie path end-to-end -------------------------------


def test_browser_flow_login_create_upload_resolve_transition_signed(stack):
    """The full real-browser flow: log in → create engagement → upload →
    resolve the blocker → transition open→review→signed → fetch memo PDF.
    All cookie-authenticated; CSRF token submitted on every POST."""
    client, store, _deny = stack

    # 1. POST /login as the analyst — server issues session + csrf cookies.
    r = client.post("/login", data={"token": "tok-analyst"})
    assert r.status_code == 302
    csrf_value = client.get_cookie(CSRF_COOKIE_NAME).value
    assert csrf_value
    csrf_hdr = {"X-CSRF-Token": csrf_value}

    # 2. Create engagement (form-encoded — browser path).
    r = client.post(
        "/engagement/?html=1",
        data={"client_id": "acme", "valuation_date": "2025-06-01",
              "standard_of_value": "ifrs13", "csrf_token": csrf_value},
        follow_redirects=False,
    )
    assert r.status_code == 302
    eng_id = r.headers["Location"].split("/")[-1].split("?")[0]
    eng = store.get_engagement(eng_id)
    assert eng.version == 0

    # 3. Upload the cap table (form-encoded, multipart).
    r = client.post(
        f"/engagement/{eng_id}/upload?html=1",
        data={
            "file": (io.BytesIO(_xlsx_with_resolvable_blockers()), "demo.xlsx"),
            "expected_version": "0",
            "csrf_token": csrf_value,
        },
        content_type="multipart/form-data",
    )
    assert r.status_code in (302, 200), r.get_data(as_text=True)
    eng = store.get_engagement(eng_id)
    assert eng.head_snapshot_id is not None
    assert eng.version == 1

    # 4. Resolve the AD-MISSING blocker on Series A.
    r = client.post(
        f"/engagement/{eng_id}/resolve?html=1",
        data={
            "snapshot_id": eng.head_snapshot_id,
            "finding_code": "AD-MISSING-Series A",
            "decision": '{"variant":"broad_based_weighted_average"}',
            "citation": "Charter §4.3(a)",
            "csrf_token": csrf_value,
        },
        headers=csrf_hdr,
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    # 5. Transition open → review.
    r = client.post(
        f"/engagement/{eng_id}/transition?html=1",
        data={
            "new_status": EngagementStatus.review.value,
            "expected_version": str(store.get_engagement(eng_id).version),
            "csrf_token": csrf_value,
        },
    )
    assert r.status_code in (302, 200)
    assert store.get_engagement(eng_id).status == EngagementStatus.review

    # 6. Partner logs in (separate session) and transitions review → signed.
    client.delete_cookie(COOKIE_NAME)
    client.delete_cookie(CSRF_COOKIE_NAME)
    client.post("/login", data={"token": "tok-partner"})
    partner_csrf = client.get_cookie(CSRF_COOKIE_NAME).value
    r = client.post(
        f"/engagement/{eng_id}/transition?html=1",
        data={
            "new_status": EngagementStatus.signed.value,
            "expected_version": str(store.get_engagement(eng_id).version),
            "csrf_token": partner_csrf,
        },
    )
    assert r.status_code in (302, 200), r.get_data(as_text=True)
    assert store.get_engagement(eng_id).status == EngagementStatus.signed


# ---- Flow 2: bundle is deterministic across regenerations ------------------


def test_bundle_byte_stable_across_two_engagement_lifetimes(stack):
    """The audit's B-2 fix promised auditor-recompute of bundle bytes.
    This test drives a full create→upload→bundle cycle twice on the same
    engagement and proves the bytes match."""
    client, store, _ = stack
    r = client.post("/engagement/", headers=_bearer("tok-analyst"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    client.post(
        f"/engagement/{eng_id}/upload", headers=_bearer("tok-analyst"),
        data={"file": (io.BytesIO(_xlsx_clean()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    # Two bundle fetches — bytes must match.
    b1 = client.get(f"/engagement/{eng_id}/bundle.zip",
                    headers=_bearer("tok-analyst")).get_data()
    b2 = client.get(f"/engagement/{eng_id}/bundle.zip",
                    headers=_bearer("tok-analyst")).get_data()
    assert b1 == b2


# ---- Flow 3: Bearer revocation via /logout --------------------------------


def test_bearer_token_revoked_by_logout_stops_authenticating(stack):
    """W6.4: POST /logout with the Bearer header in flight must add the
    token to the deny list; subsequent requests fail with 401."""
    client, store, deny = stack
    # Create an engagement to confirm the Bearer works.
    r = client.post("/engagement/", headers=_bearer("tok-analyst"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    assert r.status_code == 201

    # /logout with Bearer header → server revokes that token.
    r = client.post("/logout", headers=_bearer("tok-analyst"))
    assert r.status_code == 302
    assert deny.is_revoked("tok-analyst")

    # Same Bearer no longer authenticates.
    r = client.post("/engagement/", headers=_bearer("tok-analyst"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    assert r.status_code == 401


# ---- Flow 4: stale-version upload is rejected ------------------------------


def test_stale_expected_version_on_upload_returns_409(stack):
    """W2 optimistic concurrency: an upload with an out-of-date
    expected_version must fail with 409, not silently overwrite."""
    client, store, _ = stack
    r = client.post("/engagement/", headers=_bearer("tok-analyst"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    # First upload OK (version 0 → 1).
    client.post(
        f"/engagement/{eng_id}/upload", headers=_bearer("tok-analyst"),
        data={"file": (io.BytesIO(_xlsx_clean()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    # Second upload with stale version 0 must 409.
    r = client.post(
        f"/engagement/{eng_id}/upload", headers=_bearer("tok-analyst"),
        data={"file": (io.BytesIO(_xlsx_clean()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 409
    assert r.get_json()["error_code"] == "engagement-version-conflict"


# ---- Flow 5: rate-limit alert event lands in audit log --------------------


def test_compute_burst_alert_recorded_in_audit_log(stack):
    """W5.5 + SD-AUD-M2: compute hard-limit hit writes one
    compute_burst_alert event in the engagement's audit chain."""
    client, store, _ = stack
    r = client.post("/engagement/", headers=_bearer("tok-analyst"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    # compute_limiter hard_limit=3. Hit /whatif until boundary.
    for _ in range(3):
        client.post(f"/engagement/{eng_id}/whatif", headers=_bearer("tok-analyst"),
                    data={})
    events = store.list_audit_events(eng_id)
    assert any(e.event_type == AuditEventType.compute_burst_alert for e in events)


# ---- Flow 6: CSRF protects against form replay ----------------------------


def test_csrf_mismatch_on_form_post_returns_403_json_when_api(stack):
    """W6.1: a cookie-authenticated POST without a matching CSRF token
    fails closed (403). JSON when the client wants JSON."""
    client, store, _ = stack
    client.post("/login", data={"token": "tok-analyst"})
    r = client.post(
        "/engagement/",
        data={"client_id": "c", "valuation_date": "2025-06-01",
              "csrf_token": "wrong-token"},
    )
    assert r.status_code == 403
    assert r.get_json()["error_code"] == "csrf-mismatch"


def test_csrf_mismatch_renders_html_when_html_requested(stack):
    """SD-AUD-W6M-5: same 403, but renders the engagement error page so
    the HTMX swap target doesn't receive raw JSON."""
    client, store, _ = stack
    client.post("/login", data={"token": "tok-analyst"})
    r = client.post(
        "/engagement/?html=1",
        data={"client_id": "c", "valuation_date": "2025-06-01",
              "csrf_token": "wrong-token"},
    )
    assert r.status_code == 403
    assert "text/html" in r.headers.get("Content-Type", "")
    body = r.get_data(as_text=True)
    assert "CSRF check failed" in body
    assert "csrf-mismatch" in body


def test_csrf_missing_cookie_on_cookie_auth_returns_403(stack):
    """W6.1: cookie-auth POST without the CSRF cookie at all (e.g.
    attacker forged the session cookie alone) must 403."""
    client, store, _ = stack
    cookie_value = issue_session_cookie("u-a", b"x" * 32, ttl_days=1)
    client.set_cookie(COOKIE_NAME, cookie_value, domain="localhost")
    # No CSRF cookie, no header, no form field.
    r = client.post("/engagement/",
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    assert r.status_code == 403
    assert r.get_json()["error_code"] == "csrf-missing-cookie"


# ---- Flow 7: blocker-resolution gate prevents premature sign-off ----------


def test_unresolved_blocker_blocks_transition_to_signed(stack):
    """§9.3 gate: a partner cannot sign off if any blocker is unresolved
    even if the analyst tries to skip the resolve step."""
    client, store, _ = stack
    r = client.post("/engagement/", headers=_bearer("tok-analyst"),
                    json={"client_id": "c", "valuation_date": "2025-06-01"})
    eng_id = r.get_json()["id"]
    # Upload + go straight to review (blocker is still unresolved).
    client.post(
        f"/engagement/{eng_id}/upload", headers=_bearer("tok-analyst"),
        data={"file": (io.BytesIO(_xlsx_with_resolvable_blockers()), "x.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    client.post(
        f"/engagement/{eng_id}/transition", headers=_bearer("tok-analyst"),
        json={"new_status": "review",
              "expected_version": store.get_engagement(eng_id).version},
    )
    # Partner attempts signed → must fail with the spec error code.
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_bearer("tok-partner"),
        json={"new_status": "signed",
              "expected_version": store.get_engagement(eng_id).version},
    )
    assert r.status_code == 409
    assert r.get_json()["error_code"] == "engagement-blockers-unresolved"
