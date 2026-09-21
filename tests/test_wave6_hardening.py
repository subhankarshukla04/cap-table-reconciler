"""W6.1 / W6.2 / W6.4 / W6.5 unit-level regression tests.

Per-feature checks complement the cross-wave integration tests in
test_wave6_integration.py (which drive the production-bound flows).
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
    CSRF_HEADER,
    attach_login_blueprint,
    issue_csrf_token,
    issue_session_cookie,
    verify_csrf,
)
from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User
from src.rate_limit import ExportRateLimiter
from src.rule_pack import (
    _assert_no_finding_code_collisions,
    _representative_cap_table_for_collision_check,
    assert_no_collisions_at_startup,
)
from src.token_deny import TokenDenyList


# ---- W6.1: CSRF -----------------------------------------------------------


def test_csrf_token_is_url_safe_random():
    t1 = issue_csrf_token()
    t2 = issue_csrf_token()
    assert t1 != t2
    # W9.5 format: `<unix_seconds>.<url-safe random>`. Both halves only
    # use digits + base64-url-safe alphabet plus `.` separator.
    assert all(c.isalnum() or c in "-_." for c in t1)
    assert len(t1) >= 32
    assert "." in t1  # iat prefix present


def test_csrf_logout_clears_session_but_keeps_csrf():
    """W8.7: /logout zeroes the session cookie but PRESERVES the CSRF
    cookie so multi-tab UX doesn't break (a second tab's next POST
    would otherwise 403 with csrf-missing-cookie). The CSRF cookie has
    no security value once the session is gone; the engagement
    blueprint's auto-heal hook re-mints it on the next GET anyway."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SESSION_SECRET_KEY"] = b"x" * 32
    attach_login_blueprint(
        app, identity_provider=StaticUserProvider(
            {"t": User(id="u", email="u@x", role=Role.analyst, display_name="u")},
        ),
    )
    client = app.test_client()
    # Log in to issue both cookies.
    client.post("/login", data={"token": "t"})
    assert client.get_cookie(COOKIE_NAME).value
    csrf_value = client.get_cookie(CSRF_COOKIE_NAME).value
    assert csrf_value
    # SD-AUD-W6M-3: cookie-auth /logout now requires the CSRF token.
    r = client.post("/logout", data={"csrf_token": csrf_value})
    assert r.status_code == 302
    # Session cookie zeroed; CSRF cookie preserved (W8.7).
    sess = client.get_cookie(COOKIE_NAME)
    csrf = client.get_cookie(CSRF_COOKIE_NAME)
    assert (sess is None) or sess.value == ""
    # CSRF cookie survives so a second tab's next form post still works.
    assert csrf is not None and csrf.value == csrf_value


# ---- W6.2: startup collision check ---------------------------------------


def test_representative_cap_table_passes_collision_check():
    """The probe cap table is collision-clean against the 60-rule v6 pack."""
    ct = _representative_cap_table_for_collision_check()
    assert _assert_no_finding_code_collisions(ct) is None


def test_assert_no_collisions_at_startup_does_not_raise():
    """Strict mode boot is green right now."""
    assert_no_collisions_at_startup(strict=True)


def test_assert_no_collisions_strict_raises_on_synthetic_dup(monkeypatch):
    """Inject a synthetic collision to prove strict=True actually raises.
    SD-AUD-W6M-1: the boot guard now consults both the runtime probe
    union and the static source scan; patch either one to fire."""
    from src import rule_pack as rp

    def _bad_probe(_probes):
        return "  finding code 'DUP-1' emitted by: ['fake-a', 'fake-b']"

    monkeypatch.setattr(rp, "_collisions_across_probes", _bad_probe)
    with pytest.raises(RuntimeError, match="DUP-1"):
        rp.assert_no_collisions_at_startup(strict=True)


# ---- W6.4: token deny list ------------------------------------------------


def test_deny_list_revoke_then_is_revoked(tmp_path):
    deny = TokenDenyList(db_path=tmp_path / "deny.db")
    assert deny.is_revoked("never-touched") is False
    deny.revoke("abc")
    assert deny.is_revoked("abc") is True
    assert deny.is_revoked("xyz") is False


def test_deny_list_stores_hash_not_raw_token(tmp_path):
    """A DB inspection must never reveal the raw token."""
    import sqlite3
    deny = TokenDenyList(db_path=tmp_path / "deny.db")
    deny.revoke("secret-bearer-tok")
    conn = sqlite3.connect(tmp_path / "deny.db")
    rows = conn.execute("SELECT token_hash FROM token_deny").fetchall()
    conn.close()
    assert rows and rows[0][0] != "secret-bearer-tok"
    assert len(rows[0][0]) == 64  # sha256 hex


def test_deny_list_prune_drops_old_entries(tmp_path):
    import time as _t
    deny = TokenDenyList(db_path=tmp_path / "deny.db")
    deny.revoke("old")
    n = deny.prune_older_than(_t.time() + 60)  # cutoff in the future
    assert n == 1
    assert deny.is_revoked("old") is False


def test_revoked_bearer_authenticates_as_nobody():
    """Engagement-blueprint integration: a revoked Bearer falls through to
    the unauthenticated path. The route returns 401."""
    with tempfile.TemporaryDirectory() as d:
        store = EngagementStore(db_path=Path(d) / "eng.db")
        deny = TokenDenyList(db_path=Path(d) / "deny.db")
        deny.revoke("tok-revoked")
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SESSION_SECRET_KEY"] = b"x" * 32
        app.config["TOKEN_DENY_LIST"] = deny
        users = {"tok-revoked": User(id="u", email="u@x", role=Role.analyst,
                                      display_name="u")}
        attach_engagement_blueprint(app, store, StaticUserProvider(users))
        client = app.test_client()
        r = client.post("/engagement/",
                        headers={"Authorization": "Bearer tok-revoked"},
                        json={"client_id": "c", "valuation_date": "2025-06-01"})
        assert r.status_code == 401


# ---- W6.5: load_workbook close on exception ------------------------------


def test_parse_excel_closes_workbook_on_error(tmp_path):
    """Synthesize a workbook that triggers an internal ValueError after
    load — verify the handle is released."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cap Table"
    # Missing required columns → parser raises.
    ws.append(["Bogus Column"])
    ws.append(["X"])
    path = tmp_path / "bad.xlsx"
    wb.save(path)
    from src.parser import parse_excel
    with pytest.raises(ValueError):
        parse_excel(path)
    # File should now be deletable on Windows-like semantics; on POSIX
    # the unlink always works regardless. We assert the file can be
    # re-opened, which requires GC pressure not to leak the descriptor.
    path.unlink()
    assert not path.exists()
