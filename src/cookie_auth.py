"""Browser session-cookie auth shim (W5.7 / closes SD-4 + m-8).

Real browsers cannot attach `Authorization: Bearer` headers to plain
`<a href=...>` links, so the HTMX UI was dev-only — the audit explicitly
flagged this. This module adds two pieces:

  1. A `/login` page that issues a server-signed session cookie carrying
     the user identity (resolved via the existing IdentityProvider).
  2. A `_resolve_session_cookie()` helper the engagement-blueprint auth
     guard consults before falling back to Bearer headers.

The cookie is a Fernet-style signed token (HMAC-SHA256 by stdlib —
no external dep) carrying (user_id, expiry_iso). The shim doesn't
implement an SSO bridge; that's still Evelyn-blocked. What it DOES is
let a developer or future Qapita-internal SSO callback issue a cookie
that browser sessions can rely on.

Cookie shape (URL-safe, opaque to client):

    payload = base64url(user_id|expiry_iso|HMAC(secret_key, user_id|expiry_iso))

Verified server-side via constant-time HMAC compare. The secret key
comes from `app.config["SESSION_SECRET_KEY"]` (set in app.py from env
var or a random per-process key in dev).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Flask,
    current_app,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from .identity import IdentityProvider, User


COOKIE_NAME = "qapita_session"
CSRF_COOKIE_NAME = "qapita_csrf"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
COOKIE_TTL_DAYS = 7
DEFAULT_NEXT_URL = "/engagement/?html=1"


# ---- CSRF helpers (W6.1) ---------------------------------------------------
# Double-submit cookie pattern. The csrf cookie is readable by JS (no httponly)
# so HTMX forms can pluck it; the session cookie is HttpOnly. A cross-site
# attacker cannot read the csrf cookie (same-origin policy + SameSite=Strict),
# so they cannot forge a matching `csrf_token` form field. Bearer-authenticated
# requests are exempt because they are explicit credentials, not ambient
# session — matches the SD-AUD-B5 precedence model.


# W9.5 / closes wave-6 W6M-6: encode issuance time in the CSRF token so
# the engagement blueprint's after_request hook can rotate stale tokens
# without an extra cookie. Format: `<unix_seconds>.<random>`. The
# `verify_csrf` comparison uses `hmac.compare_digest` on the full
# string, so the prefix doesn't weaken the check — the random suffix
# remains the secret.
CSRF_ROTATION_SECONDS = 3600  # rotate after 1 hour


def issue_csrf_token() -> str:
    import time as _time
    return f"{int(_time.time())}.{secrets.token_urlsafe(32)}"


def csrf_token_age_seconds(token: str) -> Optional[int]:
    """Parse the `<unix_seconds>.<random>` prefix and return age. None
    if token is in the pre-W9.5 opaque format (treated as 'rotate me'
    by callers)."""
    if not token or "." not in token:
        return None
    head, _ = token.split(".", 1)
    try:
        import time as _time
        return int(_time.time()) - int(head)
    except (TypeError, ValueError):
        return None


def attach_csrf_cookie(resp, value: str) -> None:
    resp.set_cookie(
        CSRF_COOKIE_NAME, value,
        max_age=COOKIE_TTL_DAYS * 86400,
        httponly=False,  # JS reads it for the form submit
        samesite="Strict",
        secure=not current_app.config.get("TESTING", False),
    )


def csrf_token_for_request() -> Optional[str]:
    """Return the csrf token from cookie, or None if no session is in play."""
    return request.cookies.get(CSRF_COOKIE_NAME)


def verify_csrf(allow_methods=("GET", "HEAD", "OPTIONS")) -> Optional[str]:
    """Return error code string when CSRF check fails; None when OK.

    Caller is expected to gate on auth-source (only call when the request
    authenticated via cookie). Safe methods are skipped here as well.
    """
    if request.method in allow_methods:
        return None
    expected = request.cookies.get(CSRF_COOKIE_NAME)
    if not expected:
        return "csrf-missing-cookie"
    supplied = (
        request.headers.get(CSRF_HEADER)
        or (request.form.get(CSRF_FORM_FIELD) if request.form else None)
    )
    if not supplied or not hmac.compare_digest(supplied, expected):
        return "csrf-mismatch"
    return None


def _safe_next_url(candidate: Optional[str], default: str = DEFAULT_NEXT_URL) -> str:
    """Accept only same-origin paths. Reject any absolute URL or scheme to
    prevent open-redirect phishing (B-4 / SD-AUD-B4) and reject any
    control char that would split the Location header (W8.1 closes
    W6m-1: `\\r\\n` in next → 500 instead of 400)."""
    if not candidate:
        return default
    # Any control char in the candidate corrupts the Location header
    # (werkzeug raises ValueError on \r or \n in header values, → 500).
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in candidate):
        return default
    p = urlparse(candidate)
    if p.scheme or p.netloc:
        return default
    if not candidate.startswith("/"):
        return default
    # Reject protocol-relative `//attacker.example/...`
    if candidate.startswith("//"):
        return default
    return candidate


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_session_cookie(
    user_id: str,
    secret_key: bytes,
    ttl_days: int = COOKIE_TTL_DAYS,
) -> str:
    """Build a signed session cookie value for `user_id`."""
    expiry = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    payload = f"{user_id}|{expiry.isoformat()}".encode("utf-8")
    sig = hmac.new(secret_key, payload, hashlib.sha256).digest()
    return f"{_b64url_encode(payload)}.{_b64url_encode(sig)}"


def verify_session_cookie(
    cookie_value: str,
    secret_key: bytes,
) -> Optional[str]:
    """Return the user_id if the cookie verifies; None otherwise.

    Constant-time compare on the HMAC. Expired cookies return None
    even if the signature checks out.
    """
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        payload_b64, sig_b64 = cookie_value.split(".", 1)
        payload = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:
        return None
    expected_sig = hmac.new(secret_key, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        user_id, expiry_iso = payload.decode("utf-8").split("|", 1)
        expiry = datetime.fromisoformat(expiry_iso)
    except Exception:
        return None
    if datetime.now(timezone.utc) > expiry:
        return None
    return user_id


def resolve_session_cookie(provider: IdentityProvider) -> Optional[User]:
    """Read the cookie off the current request and return the User
    object via the IdentityProvider, or None if no valid cookie."""
    cookie_value = request.cookies.get(COOKIE_NAME)
    if not cookie_value:
        return None
    secret_key = current_app.config.get("SESSION_SECRET_KEY")
    if not secret_key:
        return None
    if isinstance(secret_key, str):
        secret_key = secret_key.encode("utf-8")
    user_id = verify_session_cookie(cookie_value, secret_key)
    if not user_id:
        return None
    return provider.lookup_user(user_id)


# ---- Login blueprint --------------------------------------------------------


def build_login_blueprint() -> Blueprint:
    """Issues + clears session cookies for browser users.

    /login (GET)        — render the login form
    /login (POST)       — accept user_id, validate via IdentityProvider, set cookie
    /logout (POST)      — clear cookie

    The login form is a dev stub: real production replaces it with the
    Qapita SSO callback. The shim lives in templates/engagement/login.html.
    """
    from pathlib import Path as _Path
    _templates_dir = _Path(__file__).parent.parent / "templates"
    bp = Blueprint(
        "auth",
        __name__,
        template_folder=str(_templates_dir),
    )

    @bp.get("/login")
    def login_get():
        next_url = _safe_next_url(request.args.get("next"))
        return render_template("engagement/login.html",
                                next_url=next_url, current_user=None)

    @bp.post("/login")
    def login_post():
        provider: IdentityProvider = current_app.config["IDENTITY_PROVIDER"]
        user_id_or_token = (request.form.get("token") or "").strip()
        next_url = _safe_next_url(request.form.get("next"))
        if not user_id_or_token:
            return render_template("engagement/login.html",
                                    next_url=next_url, current_user=None,
                                    error="token required"), 400
        user = provider.authenticate(user_id_or_token)
        if user is None:
            return render_template("engagement/login.html",
                                    next_url=next_url, current_user=None,
                                    error="unknown token"), 401
        secret_key = current_app.config.get("SESSION_SECRET_KEY")
        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")
        cookie_value = issue_session_cookie(user.id, secret_key)
        resp = make_response(redirect(next_url))
        resp.set_cookie(
            COOKIE_NAME, cookie_value,
            max_age=COOKIE_TTL_DAYS * 86400,
            httponly=True,
            samesite="Strict",
            secure=not current_app.config.get("TESTING", False),
        )
        # W6.1: issue a fresh CSRF token tied to this session.
        attach_csrf_cookie(resp, issue_csrf_token())
        return resp

    @bp.post("/logout")
    def logout_post():
        # SD-AUD-W6B-1: /logout MUST authenticate the caller before revoking
        # anything. Without this check, any anonymous attacker who knows or
        # guesses a victim's Bearer token can permanently revoke it.
        provider: IdentityProvider = current_app.config["IDENTITY_PROVIDER"]

        bearer_token = None
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            bearer_token = auth.split(" ", 1)[1].strip()
        x_auth = request.headers.get("X-Auth-Token")
        if x_auth and bearer_token is None:
            bearer_token = x_auth

        # Resolve caller identity: Bearer wins (matches SD-AUD-B5 precedence),
        # cookie fallback. If neither resolves, refuse — the caller has no
        # session to log out.
        caller = None
        bearer_caller = (
            provider.authenticate(bearer_token) if bearer_token else None
        )
        if bearer_caller is not None:
            caller = bearer_caller
        else:
            caller = resolve_session_cookie(provider)
        if caller is None:
            return make_response(("unauthenticated", 401))

        # SD-AUD-W6M-3: cookie-authenticated /logout requires the CSRF token
        # (forged cross-site POST else nukes the user's session). Bearer
        # callers are exempt (explicit credential, not ambient).
        if bearer_caller is None:
            err = verify_csrf()
            if err is not None:
                return make_response((err, 403))

        # Only NOW write to the deny list — and only the Bearer that
        # actually authenticated this request. We never revoke an arbitrary
        # token a caller happens to mention in their headers.
        deny_list = current_app.config.get("TOKEN_DENY_LIST")
        if deny_list is not None and bearer_caller is not None and bearer_token:
            deny_list.revoke(bearer_token)

        next_url = _safe_next_url(request.form.get("next"), default="/login")
        resp = make_response(redirect(next_url))
        resp.set_cookie(COOKIE_NAME, "", max_age=0, expires=0)
        # W8.7 / closes wave-6 m-W7-9: do NOT clear CSRF cookie here. If
        # the user has multiple tabs open and logs out in one, the other
        # tabs' next POST would otherwise 403 with csrf-missing-cookie.
        # The CSRF cookie has no security value without the session cookie
        # (verify_csrf only runs when auth_source == "cookie"), and the
        # auto-heal hook on the engagement blueprint mints a fresh one
        # on the next authenticated GET.
        return resp

    return bp


def attach_login_blueprint(
    app: Flask,
    identity_provider: Optional[IdentityProvider] = None,
) -> None:
    """Attach /login + /logout.

    If `identity_provider` is supplied it overrides any prior
    `app.config["IDENTITY_PROVIDER"]`. If neither is set, falls back
    to a `StubSSOProvider` (matching `attach_engagement_blueprint`).

    SESSION_SECRET_KEY must come from `os.environ["SESSION_SECRET_KEY"]`
    in any non-TESTING deploy; the function raises if missing in
    production mode to prevent silent ephemeral-key footguns.
    """
    if identity_provider is not None:
        app.config["IDENTITY_PROVIDER"] = identity_provider
    elif "IDENTITY_PROVIDER" not in app.config:
        from .identity import StubSSOProvider
        # SD-AUD-W8-M2: helpers default to the stub for the dev path
        # (matches their documented contract). Prod hardening is enforced
        # by StubSSOProvider() construction WITHOUT allow_in_prod — i.e.
        # callers who construct directly without the helper still trip
        # the guard. This helper is the explicit dev opt-in.
        app.config["IDENTITY_PROVIDER"] = StubSSOProvider(allow_in_prod=True)
    if "SESSION_SECRET_KEY" not in app.config:
        env_secret = os.environ.get("SESSION_SECRET_KEY")
        if env_secret:
            app.config["SESSION_SECRET_KEY"] = env_secret.encode("utf-8")
        elif app.config.get("TESTING", False):
            app.config["SESSION_SECRET_KEY"] = secrets.token_bytes(32)
        else:
            raise RuntimeError(
                "SESSION_SECRET_KEY is unset; set the env var or "
                "app.config before attach_login_blueprint in non-TESTING mode"
            )
    app.register_blueprint(build_login_blueprint())
