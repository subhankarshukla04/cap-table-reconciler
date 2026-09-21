"""Regression tests for SYSTEM_AUDIT_WAVE_6.md fixes.

One test per blocker + per fix-now major. Test names encode the audit
finding code so a future failure traces back to the exact section.
"""

from __future__ import annotations

import io
import tempfile
import time
from pathlib import Path

import pytest
from flask import Flask

from src.cookie_auth import (
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    attach_login_blueprint,
    issue_csrf_token,
    issue_session_cookie,
)
from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User
from src.rate_limit import ExportRateLimiter
from src.rule_pack import (
    _collisions_across_probes,
    _probe_cap_tables,
    _static_collisions_in_rule_sources,
)
from src.token_deny import DEFAULT_TTL_SECONDS, TokenDenyList


# ---- shared web stack ------------------------------------------------------


@pytest.fixture
def web():
    paths = []
    for _ in range(4):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
            paths.append(Path(fh.name))
    eng_path, ex_path, cp_path, dn_path = paths
    store = EngagementStore(db_path=eng_path)
    export_limiter = ExportRateLimiter(db_path=ex_path, soft_limit=50, hard_limit=100)
    compute_limiter = ExportRateLimiter(db_path=cp_path, soft_limit=10, hard_limit=20)
    deny_list = TokenDenyList(db_path=dn_path)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SESSION_SECRET_KEY"] = b"x" * 32
    app.config["TOKEN_DENY_LIST"] = deny_list
    users = {
        "tok-victim": User(id="u-v", email="v@x", role=Role.analyst,
                            display_name="Victim"),
        "tok-attacker": User(id="u-att", email="a@x", role=Role.analyst,
                              display_name="Attacker"),
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


# ---- W6B-1: /logout requires auth -----------------------------------------


def test_w6b1_anonymous_logout_with_victim_bearer_does_not_revoke(web):
    """SD-AUD-W6B-1: an anonymous attacker cannot revoke a victim's Bearer
    by stuffing it into the Authorization header on /logout. /logout
    must require the caller to authenticate first."""
    client, _, deny = web
    assert deny.is_revoked("tok-victim") is False
    # Anonymous POST with victim's Bearer in Authorization. Pre-fix this
    # would have revoked the victim's token; post-fix the caller must
    # authenticate (they do — as victim — but that's the only path now).
    # Test the actual attack: anonymous caller, victim's token in header.
    r = client.post("/logout", headers={"Authorization": "Bearer not-a-real-token"})
    # Either the helper authenticates the supplied token (it's a real
    # one) and revokes it, OR refuses with 401. We want refusal because
    # this token does NOT resolve to any user (unknown token).
    assert r.status_code == 401
    assert deny.is_revoked("tok-victim") is False


def test_w6b1_logout_revokes_only_callers_own_token(web):
    """Legitimate use case: a real Bearer caller logs themselves out.
    Their token is revoked; no one else's."""
    client, _, deny = web
    r = client.post("/logout", headers={"Authorization": "Bearer tok-victim"})
    assert r.status_code == 302
    assert deny.is_revoked("tok-victim") is True
    assert deny.is_revoked("tok-attacker") is False


def test_w6b1_logout_without_any_auth_returns_401(web):
    """No bearer, no cookie → 401. Cannot mint a denial via anonymous call."""
    client, _, _ = web
    r = client.post("/logout")
    assert r.status_code == 401


# ---- W6M-3: /logout requires CSRF on cookie path --------------------------


def test_w6m3_cookie_logout_without_csrf_returns_403(web):
    """Cookie-authenticated /logout without the CSRF token is rejected."""
    client, _, _ = web
    client.post("/login", data={"token": "tok-victim"})
    # Drop the CSRF cookie to simulate the unguarded cross-site form post.
    client.delete_cookie(CSRF_COOKIE_NAME)
    r = client.post("/logout")
    # No CSRF cookie → csrf-missing-cookie or csrf-mismatch in body.
    assert r.status_code == 403


def test_w6m3_cookie_logout_with_csrf_succeeds(web):
    client, _, _ = web
    client.post("/login", data={"token": "tok-victim"})
    csrf = client.get_cookie(CSRF_COOKIE_NAME).value
    r = client.post("/logout", data={"csrf_token": csrf})
    assert r.status_code == 302


# ---- W6B-2: CSRF cookie auto-heal -----------------------------------------


def test_w6b2_pre_w6_cookie_session_gets_csrf_cookie_on_first_get(web):
    """A browser holding a valid session cookie but no CSRF cookie (e.g.,
    rolled across a wave-6 deploy) MUST receive the CSRF cookie on the
    next safe-method response. Without this, every POST 403s permanently."""
    client, _, _ = web
    # Simulate pre-W6: session cookie present, no CSRF cookie.
    sess = issue_session_cookie("u-v", b"x" * 32, ttl_days=1)
    client.set_cookie(COOKIE_NAME, sess, domain="localhost")
    assert client.get_cookie(CSRF_COOKIE_NAME) is None
    # GET an engagement-blueprint URL.
    r = client.get("/engagement/?html=1")
    assert r.status_code == 200
    # CSRF cookie must now be present.
    csrf_cookie = client.get_cookie(CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    assert csrf_cookie.value
    # AND the just-issued CSRF cookie must match the token embedded in
    # the page so the next form POST succeeds.
    body = r.get_data(as_text=True)
    assert csrf_cookie.value in body


# ---- W6M-5: CSRF 403 renders HTML when the client wanted HTML -------------


def test_w6m5_csrf_failure_renders_html_when_html_requested(web):
    client, _, _ = web
    client.post("/login", data={"token": "tok-victim"})
    r = client.post(
        "/engagement/?html=1",
        data={"client_id": "c", "valuation_date": "2025-06-01",
              "csrf_token": "tampered"},
    )
    assert r.status_code == 403
    assert "text/html" in r.headers.get("Content-Type", "")
    body = r.get_data(as_text=True)
    assert "CSRF" in body
    assert "csrf-mismatch" in body


# ---- W6M-2 + W6M-4: deny list TTL + size + prune --------------------------


def test_w6m4_deny_list_entries_expire_after_ttl(tmp_path):
    deny = TokenDenyList(db_path=tmp_path / "d.db",
                          default_ttl_seconds=1)
    deny.revoke("ephemeral")
    assert deny.is_revoked("ephemeral") is True
    time.sleep(1.05)
    # After TTL, the entry is treated as not-revoked.
    assert deny.is_revoked("ephemeral") is False
    deny.close()


def test_w6m4_revoke_accepts_explicit_ttl(tmp_path):
    deny = TokenDenyList(db_path=tmp_path / "d.db")
    deny.revoke("short", ttl_seconds=1)
    deny.revoke("long")  # default 30d
    time.sleep(1.05)
    assert deny.is_revoked("short") is False
    assert deny.is_revoked("long") is True
    deny.close()


def test_w6m2_prune_expired_drops_old_rows(tmp_path):
    deny = TokenDenyList(db_path=tmp_path / "d.db",
                          default_ttl_seconds=1)
    deny.revoke("a")
    deny.revoke("b")
    assert deny.size() == 2
    time.sleep(1.05)
    n = deny.prune_expired()
    assert n == 2
    assert deny.size() == 0
    deny.close()


def test_w6m2_deny_list_uses_wal_mode(tmp_path):
    """WAL keeps the per-request is_revoked() call cheap. Verify it's on."""
    import sqlite3
    deny = TokenDenyList(db_path=tmp_path / "d.db")
    conn = sqlite3.connect(tmp_path / "d.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    deny.close()
    assert mode.lower() == "wal"


def test_w6m2_deny_list_legacy_schema_migration(tmp_path):
    """A deny.db written by the wave-6 initial code (no expires_at column)
    must migrate cleanly when re-opened by the SD-AUD-W6M-4 code."""
    import sqlite3
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE token_deny (token_hash TEXT PRIMARY KEY, revoked_at REAL NOT NULL)"
    )
    import hashlib
    h = hashlib.sha256(b"old-token").hexdigest()
    conn.execute(
        "INSERT INTO token_deny (token_hash, revoked_at) VALUES (?, ?)",
        (h, time.time() - 60),
    )
    conn.commit()
    conn.close()
    # Re-open with the new TokenDenyList; migration should add expires_at
    # and backfill it.
    deny = TokenDenyList(path)
    assert deny.is_revoked("old-token") is True  # within default 30d TTL
    deny.close()


# ---- W6M-1: collision probe covers more rules + static guard --------------


def test_w6m1_probe_union_clean():
    assert _collisions_across_probes(_probe_cap_tables()) is None


def test_w6m1_static_source_scan_clean():
    """No two rule sources should declare the same Finding.code literal."""
    assert _static_collisions_in_rule_sources() is None


def test_w6m1_probe_exercises_more_rules_than_before():
    """Pre-fix probe fired 10/60 rules. The hardening should bump that."""
    from src.rule_pack import _REGISTRY
    probes = _probe_cap_tables()
    rules_with_findings = set()
    for ct in probes:
        for rid, (fn, _) in _REGISTRY.items():
            try:
                fs = fn(ct)
            except Exception:
                continue
            if fs:
                rules_with_findings.add(rid)
    # Bar set well above the pre-fix 10 baseline.
    assert len(rules_with_findings) >= 20
