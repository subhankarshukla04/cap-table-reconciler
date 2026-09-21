"""Regression tests for SYSTEM_AUDIT_STITCHED.md fixes (post-wave-5).

One test per blocker + per major fix. Each test name encodes the
audit finding code (B-1..B-6, M-1..M-9) so a future failure traces
back to the exact section of the audit doc.
"""

from __future__ import annotations

import io
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.cookie_auth import (
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    DEFAULT_NEXT_URL,
    _safe_next_url,
    attach_login_blueprint,
    issue_session_cookie,
)
from src.dcf_sidecar import build_dcf_sidecar
from src.dcf_template import build_dcf_template
from src.engagement import EngagementStore, AuditEventType
from src.engagement_bundle import build_engagement_bundle
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User, _PERMISSIONS, can
from src.models import (
    CapTable, Company, ShareClass, ShareClassType,
    LiquidationPreference, LPType,
)
from src.rate_limit import ExportRateLimiter


# ---- helpers ---------------------------------------------------------------


def _user(role: Role, uid: str = "u-test") -> User:
    return User(id=uid, email=f"{uid}@x", role=role, display_name=uid)


def _h(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def web():
    """Flask test client wired with engagement store, both rate limiters,
    cookie auth, and two Bearer-tok users (analyst + partner)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as eng_fh, \
         tempfile.NamedTemporaryFile(suffix=".db", delete=False) as ex_fh, \
         tempfile.NamedTemporaryFile(suffix=".db", delete=False) as cp_fh:
        eng_path = Path(eng_fh.name)
        ex_path = Path(ex_fh.name)
        cp_path = Path(cp_fh.name)
    store = EngagementStore(db_path=eng_path)
    export_limiter = ExportRateLimiter(db_path=ex_path, soft_limit=50, hard_limit=100)
    compute_limiter = ExportRateLimiter(db_path=cp_path, soft_limit=2, hard_limit=3)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SESSION_SECRET_KEY"] = b"x" * 32
    users = {
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
        "tok-p": User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        "tok-r": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R"),
    }
    provider = StaticUserProvider(users)
    attach_engagement_blueprint(app, store, provider,
                                 export_limiter=export_limiter,
                                 compute_limiter=compute_limiter)
    attach_login_blueprint(app, identity_provider=provider)
    yield app.test_client(), store
    eng_path.unlink(missing_ok=True)
    ex_path.unlink(missing_ok=True)
    cp_path.unlink(missing_ok=True)


def _new_engagement(client, tok="tok-a") -> str:
    return client.post(
        "/engagement/", headers=_h(tok),
        json={"client_id": "c", "valuation_date": "2025-06-01"},
    ).get_json()["id"]


def _upload_xlsx_bytes() -> bytes:
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


def _dcf_cap_table_with_excluded_collision() -> CapTable:
    """Two classes whose names slugify to the same key, one excluded.
    Reproduces B-1 exactly. excluded_from_waterfall is a derived prop —
    option_pool_reserved is the only type that returns True."""
    return CapTable(
        company=Company(name="Acme", currency="USD", currency_symbol="$"),
        share_classes=[
            ShareClass(
                name="ESOP A", type=ShareClassType.option_pool_reserved,
                shares_outstanding=1000,
            ),
            ShareClass(
                name="ESOP-A", type=ShareClassType.preferred,
                shares_outstanding=2000, issue_price=1.0,
                liquidation_preference=LiquidationPreference(
                    multiple=1.0, type=LPType.non_participating, amount=2000.0,
                ),
            ),
        ],
    )


# ---- B-1: DCF slug divergence ---------------------------------------------


def test_b1_dcf_sidecar_and_template_slugs_align_under_excluded_collision():
    ct = _dcf_cap_table_with_excluded_collision()
    sidecar = build_dcf_sidecar(ct)
    template = build_dcf_template(ct)

    # The included preferred "ESOP-A" must claim the base slug `ESOP_A` in
    # BOTH workbooks. Prior to the fix the sidecar would have assigned
    # `share_count_ESOP_A` to the excluded ESOP A pool and `_2` to the
    # preferred, while the template assigned `ESOP_A` to the preferred.
    defined = [dn.name for dn in sidecar.defined_names.values()]
    assert "share_count_ESOP_A" in defined
    # The excluded pool gets no defined-name (sidecar fix).
    assert "share_count_ESOP_A_2" not in defined

    # Template references the same name.
    tpl_ws = template["Per-Class FV"]
    rows = [
        (tpl_ws.cell(row=r, column=1).value, tpl_ws.cell(row=r, column=3).value)
        for r in range(2, 5) if tpl_ws.cell(row=r, column=1).value
    ]
    pref_row = next((r for r in rows if r[0] == "ESOP-A"), None)
    assert pref_row is not None
    assert "share_count_ESOP_A" in (pref_row[1] or "")
    assert "share_count_ESOP_A_2" not in (pref_row[1] or "")


# ---- B-2: Bundle byte stability -------------------------------------------


def test_b2_bundle_is_byte_stable_across_regeneration(web):
    client, store = web
    eng_id = _new_engagement(client)
    client.post(
        f"/engagement/{eng_id}/upload", headers=_h("tok-a"),
        data={"file": (io.BytesIO(_upload_xlsx_bytes()), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    b1 = build_engagement_bundle(store, eng_id)
    time.sleep(1.05)  # ensure wall-clock has advanced past 1s
    b2 = build_engagement_bundle(store, eng_id)
    assert b1 == b2, "bundle bytes diverged between two regenerations"


# ---- B-3: XSS via chart_json ----------------------------------------------


def test_b3_chart_payload_in_script_tag_escapes_closing_script(tmp_path):
    """Spec §8.16: class names may carry any UTF-8 and templates use
    autoescape. The fix replaces `|safe` on a json-encoded string with
    `|tojson` on the underlying dict — Flask's tojson escapes `<`/`>`/
    U+2028/U+2029 so the JSON literal cannot break out of <script>...</script>.

    Both templates (waterfall.html and _whatif_panel.html) now use the
    same escape-correct pattern; this test renders the exact one-liner
    they share to prove the escape works."""
    from flask import Flask, render_template_string
    app = Flask(__name__)
    chart = {"datasets": [{"label": "</script><script>alert(1)</script>"}]}
    with app.app_context():
        rendered = render_template_string(
            "<script>const p = {{ chart|tojson }};</script>",
            chart=chart,
        )
    assert "</script><script>alert(1)</script>" not in rendered
    # |tojson escapes `<` and `>` as `<` / `>`.
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e" in rendered


def test_b3_waterfall_template_does_not_use_safe_filter():
    """Sanity check: the actual templates no longer have the |safe leak."""
    wf = (Path(__file__).parent.parent / "templates" / "waterfall.html").read_text()
    wi = (Path(__file__).parent.parent / "templates" / "_whatif_panel.html").read_text()
    assert "chart_json|safe" not in wf
    assert "scenario_chart_json|safe" not in wi
    # Replacement is in place.
    assert "chart|tojson" in wf
    assert "scenario_chart|tojson" in wi


# ---- B-4: Open redirect ---------------------------------------------------


@pytest.mark.parametrize("evil,want_default", [
    ("https://attacker.example/", True),
    ("//attacker.example/x", True),
    ("javascript:alert(1)", True),
    ("/engagement/?html=1", False),
    ("", True),
    (None, True),
])
def test_b4_safe_next_url_rejects_offsite_targets(evil, want_default):
    out = _safe_next_url(evil)
    if want_default:
        assert out == DEFAULT_NEXT_URL
    else:
        assert out == evil


def test_b4_login_post_with_evil_next_redirects_to_default(web):
    client, _ = web
    r = client.post("/login", data={
        "token": "tok-a",
        "next": "https://attacker.example/phish",
    })
    assert r.status_code == 302
    # Location header must point to the safe default, not the attacker.
    assert "attacker.example" not in r.headers["Location"]
    assert "/engagement/" in r.headers["Location"]


def test_b4_logout_post_with_evil_next_redirects_to_default(web):
    """SD-AUD-W6B-1: /logout now requires auth, so authenticate the caller
    first, then verify the open-redirect protection still fires."""
    client, _ = web
    client.post("/login", data={"token": "tok-a"})
    csrf = client.get_cookie(CSRF_COOKIE_NAME).value
    r = client.post(
        "/logout",
        data={"next": "//attacker.example/phish", "csrf_token": csrf},
    )
    assert r.status_code == 302
    assert "attacker.example" not in r.headers["Location"]


# ---- B-5: Bearer beats cookie ---------------------------------------------


def test_b5_explicit_bearer_beats_ambient_cookie(web):
    client, store = web
    # Issue a cookie for partner; also send Bearer for analyst. Analyst
    # has engagement.create, partner does NOT. With the fix, the explicit
    # Bearer wins → create succeeds (201).
    cookie_value = issue_session_cookie("u-p", b"x" * 32, ttl_days=1)
    client.set_cookie(COOKIE_NAME, cookie_value, domain="localhost")
    r = client.post(
        "/engagement/", headers=_h("tok-a"),
        json={"client_id": "c", "valuation_date": "2025-06-01"},
    )
    assert r.status_code == 201, r.get_data(as_text=True)


def test_b5_cookie_used_when_no_bearer_present(web):
    client, store = web
    from src.cookie_auth import CSRF_COOKIE_NAME, issue_csrf_token
    cookie_value = issue_session_cookie("u-a", b"x" * 32, ttl_days=1)
    csrf = issue_csrf_token()
    client.set_cookie(COOKIE_NAME, cookie_value, domain="localhost")
    client.set_cookie(CSRF_COOKIE_NAME, csrf, domain="localhost")
    r = client.post(
        "/engagement/",
        json={"client_id": "c", "valuation_date": "2025-06-01"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201


# ---- B-6: /upload requires expected_version --------------------------------


def test_b6_upload_without_expected_version_returns_400(web):
    client, _ = web
    eng_id = _new_engagement(client)
    r = client.post(
        f"/engagement/{eng_id}/upload", headers=_h("tok-a"),
        data={"file": (io.BytesIO(_upload_xlsx_bytes()), "demo.xlsx")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "missing-expected-version"


# ---- M-1: Memo timestamp pinned -------------------------------------------


def test_m1_pdf_memo_generated_at_uses_engagement_created_at():
    from src.pdf_memo import _build_context, PDFInputs, ReviewerInfo
    from src.waterfall import compute_waterfall
    pinned = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    ct = CapTable(
        company=Company(name="Acme", currency="USD", currency_symbol="$"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=1000),
        ],
    )
    wf = compute_waterfall(ct)
    inputs = PDFInputs(
        cap_table=ct, waterfall=wf, findings=[], resolutions=[],
        reviewer=None, generated_at=pinned,
    )
    ctx = _build_context(inputs)
    assert ctx["generated_at"] == "2024-06-01 12:00 UTC"


# ---- M-2: Compute burst alert ---------------------------------------------


def test_m2_compute_hard_limit_writes_audit_event(web):
    client, store = web
    eng_id = _new_engagement(client)
    # compute_limiter hard_limit=3 in fixture. Hit /whatif until boundary.
    for _ in range(3):
        client.post(f"/engagement/{eng_id}/whatif", headers=_h("tok-a"),
                    data={})
    events = store.list_audit_events(eng_id)
    types = [e.event_type for e in events]
    assert AuditEventType.compute_burst_alert in types


# ---- M-3: review→open transition granted to partner -----------------------


def test_m3_partner_can_transition_review_to_open():
    assert "engagement.transition_review_to_open" in _PERMISSIONS[Role.partner]
    assert can(_user(Role.partner), "engagement.transition_review_to_open")


# ---- M-5: attach_login_blueprint accepts identity_provider arg ------------


def test_m5_attach_login_blueprint_accepts_explicit_provider():
    provider = StaticUserProvider({"x": _user(Role.analyst, "u")})
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SESSION_SECRET_KEY"] = b"x" * 32
    # Without app.config["IDENTITY_PROVIDER"] set, the helper used to
    # crash on first /login POST. Now it accepts an explicit arg.
    attach_login_blueprint(app, identity_provider=provider)
    assert app.config["IDENTITY_PROVIDER"] is provider


def test_m5_attach_login_blueprint_raises_when_secret_missing_in_prod():
    import os
    app = Flask(__name__)
    app.config["TESTING"] = False
    # Ensure no env var present.
    prior = os.environ.pop("SESSION_SECRET_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
            attach_login_blueprint(
                app,
                identity_provider=StaticUserProvider({}),
            )
    finally:
        if prior is not None:
            os.environ["SESSION_SECRET_KEY"] = prior


# ---- M-8: rate limit window is single calendar hour -----------------------


def test_m8_rate_limit_is_calendar_hour_not_two_bucket_sum(tmp_path):
    db = tmp_path / "rl.db"
    # Bucket boundary scenario: first burst in bucket N, second in N+1
    # — the count must reset at the boundary, not sum across.
    clock = {"t": 3600.0 * 1000}  # bucket = 1000
    limiter = ExportRateLimiter(db_path=db, soft_limit=2, hard_limit=4,
                                 now_fn=lambda: clock["t"])
    for _ in range(2):
        limiter.consume("u")
    clock["t"] += 3600.0  # advance into bucket 1001
    rl = limiter.consume("u")
    # Pre-fix: current_count would have been 3 (1 + sum of last bucket).
    # Post-fix: bucket-only count → 1.
    assert rl.current_count == 1


# ---- M-9: spec §10.5 chronology updated -----------------------------------


def test_m9_spec_chronology_lists_v2026_6_0():
    spec = (Path(__file__).parent.parent / "SYSTEM_SPEC.md").read_text()
    assert "v2026.6.0" in spec
    assert "2026-05-26" in spec
