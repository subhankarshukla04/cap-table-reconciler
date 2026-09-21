"""Engagement-aware Flask blueprint (BUILD_WAVE_2 W2.1).

Wires the EngagementStore from src.engagement into HTTP routes with
auth via the IdentityProvider. All routes require an authenticated
user (per SYSTEM_SPEC §3.2); the StubSSOProvider lets a developer use
any non-empty token for the dev analyst.

URL design:

  POST /engagement/                      → create engagement
  GET  /engagement/                      → list engagements (filtered by role)
  GET  /engagement/<id>                  → engagement detail (latest snapshot)
  POST /engagement/<id>/upload           → upload an Excel cap table → new snapshot
  POST /engagement/<id>/resolve          → record a resolution against the head snapshot
  POST /engagement/<id>/transition       → state transition
  POST /engagement/<id>/redact/<snap_id> → PDPA redaction (partner only)
  GET  /engagement/<id>/memo.pdf         → generate PDF memo
  GET  /engagement/<id>/audit-log        → list audit events (with hash chain)
  GET  /engagement/<id>/verify           → recompute hash chain, return integrity report

Auth:

  Every route reads `Authorization: Bearer <token>` (or `X-Auth-Token`
  in the query string for tests) and resolves it via the registered
  IdentityProvider. Unauthenticated requests return 401 with
  `WWW-Authenticate: Bearer`. Permission failures return 403 with the
  spec's error code.
"""

from __future__ import annotations

import tempfile
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional

import openpyxl
from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from pydantic import ValidationError

from .engagement import (
    EngagementError,
    SnapshotNotFound,
    EngagementNotFound,
    EngagementStatus,
    EngagementStore,
    EngagementVersionConflict,
    IllegalStateTransition,
    PermissionDenied,
    SnapshotSource,
)
from .engagement_bundle import build_engagement_bundle
from .identity import IdentityProvider, Role, StubSSOProvider, User, can
from .parser import parse_excel
from .pdf_memo import (
    PDFInputs,
    PDFMemoError,
    ReviewerInfo,
    render_diff_workpaper_pdf,
    render_pdf_memo,
)
from .rate_limit import ExportRateLimiter
from .rule_pack import (
    EngagementPackBinding,
    head_pack,
    load_engagement_bound_pack,
    run_pack,
    current_engine_commit,
)
from .subsequent_events import compute_subsequent_events


# ---- Auth wiring ------------------------------------------------------------


def _extract_token() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    # m10 fix: query-string tokens are test-only. Putting tokens in URLs
    # leaks them to access logs, referrers, browser history, and shared
    # screenshots. Header is the only production path.
    header_token = request.headers.get("X-Auth-Token")
    if header_token:
        return header_token
    if current_app.config.get("TESTING"):
        return request.args.get("token")
    return None


def _require_user() -> User:
    provider: IdentityProvider = current_app.config["IDENTITY_PROVIDER"]
    # SD-AUD-B5: explicit Authorization / X-Auth-Token / test ?token= beats
    # the ambient session cookie. Browser HTMX never sends Bearer, so the
    # cookie path is still primary for browser flows; API clients carrying
    # an explicit credential always get the identity they asked for, even
    # when a stale cookie is also attached.
    from .cookie_auth import resolve_session_cookie
    token = _extract_token()
    # W6.4: a revoked Bearer token authenticates as nobody. We swallow the
    # token before identity resolution; the request falls through to the
    # cookie/anonymous path with the same flow as a missing Bearer.
    deny_list = current_app.config.get("TOKEN_DENY_LIST")
    if token and deny_list is not None and deny_list.is_revoked(token):
        token = None
    user = provider.authenticate(token or "") if token else None
    auth_source = "bearer" if user is not None else None
    if user is None:
        user = resolve_session_cookie(provider)
        if user is not None:
            auth_source = "cookie"
    if user is None:
        # Browser request → redirect to /login (HTMX UI usability).
        # API client → 401 with WWW-Authenticate.
        try:
            html_wanted = _wants_html()
        except Exception:
            html_wanted = False
        if html_wanted:
            from werkzeug.wrappers import Response as _R
            next_url = request.full_path or "/engagement/?html=1"
            r = _R(status=302, headers={"Location": "/login?next=" + next_url})
            abort(r)
        resp = jsonify({"error": "unauthenticated", "error_code": "auth-required"})
        resp.status_code = 401
        resp.headers["WWW-Authenticate"] = "Bearer"
        abort(resp)
    g.current_user = user
    g.auth_source = auth_source  # "bearer" | "cookie" — W6.1 CSRF gates on this
    return user


def _store() -> EngagementStore:
    return current_app.config["ENGAGEMENT_STORE"]


def _format_money(value: Optional[float], symbol: str = "$") -> str:
    if value is None:
        return "—"
    if abs(value) >= 1_000_000_000:
        return f"{symbol}{value/1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"{symbol}{value/1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"{symbol}{value/1_000:,.0f}K"
    return f"{symbol}{value:,.2f}"


def _wants_html() -> bool:
    """W4.1 content negotiation: ?html=1 or Accept: text/html → render
    HTMX page; otherwise return JSON. Tests + machine clients keep
    JSON behaviour by default.

    W4-AUDIT m-1/m-2 fixes: case-insensitive Accept; respect q-values.
    A header like `text/html;q=0.5, application/json;q=0.9` should yield
    JSON; `Accept: TEXT/HTML, application/json;q=0.9` should yield HTML.
    """
    if request.args.get("html") == "1":
        return True
    accept = request.headers.get("Accept", "").lower()
    if not accept:
        return False
    # Parse comma-separated media types with optional q-values.
    types = []
    for chunk in accept.split(","):
        parts = [p.strip() for p in chunk.strip().split(";")]
        media = parts[0]
        q = 1.0
        for p in parts[1:]:
            if p.startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    pass
        types.append((media, q))
    # Pick the highest-q media type the client prefers.
    types.sort(key=lambda t: t[1], reverse=True)
    for media, _q in types:
        if media == "text/html" or media == "application/xhtml+xml":
            return True
        if media == "application/json":
            return False
    # Wildcards default to JSON for backward compat with API clients
    # (curl sends `Accept: */*` by default).
    return False


# SD-AUD-W7-M2: cap on the N-way diff to keep RAM + response size bounded
# even when an analyst checks every box. 20 covers the realistic
# memo-grade workflow ceiling (~10) with headroom.
MAX_DIFF_SNAPSHOTS = 20


def _diff_error(error_code: str, message: str, status: int):
    """SD-AUD-W7-M3: branch on content negotiation so HTMX form submits
    receive the styled engagement/error.html instead of raw JSON in the
    swap target. Mirrors the wave-6 CSRF 403 fix discipline."""
    if _wants_html():
        body = render_template(
            "engagement/error.html",
            error_code=error_code,
            error_message=message,
            current_user=g.get("current_user"),
        )
        return Response(body, status=status, mimetype="text/html")
    resp = jsonify({"error": message, "error_code": error_code})
    resp.status_code = status
    return resp


def _diff_error_from_response(err_tuple):
    """Unwrap (jsonify_response, status_code) produced by
    _parse_diff_snap_ids and re-emit through _diff_error."""
    json_resp, status = err_tuple
    payload = json_resp.get_json() or {}
    return _diff_error(
        payload.get("error_code", "diff-error"),
        payload.get("error", "diff error"),
        status,
    )


def _parse_diff_snap_ids():
    """Parse ?snap=... query params for /diff + /diff.xlsx. Dedupes
    (preserving order — chronological sort happens later) and caps at
    MAX_DIFF_SNAPSHOTS. Returns (snap_ids, error_response_or_None)."""
    raw = request.args.getlist("snap")
    # dict.fromkeys preserves insertion order while deduping.
    snap_ids = list(dict.fromkeys(raw))
    if len(snap_ids) < 2:
        return None, (jsonify({
            "error": "need at least 2 snapshot ids via ?snap=… repeated",
            "error_code": "diff-needs-two-snapshots",
        }), 400)
    if len(snap_ids) > MAX_DIFF_SNAPSHOTS:
        return None, (jsonify({
            "error": (
                f"diff supports at most {MAX_DIFF_SNAPSHOTS} snapshots "
                f"(received {len(snap_ids)} unique ids)"
            ),
            "error_code": "diff-too-many-snapshots",
        }), 400)
    return snap_ids, None


def _enforce_export_limit(eng, user: User):
    """Consume the per-user export-rate budget and write the hard-alert
    audit event exactly once (edge-trigger, not level-trigger). Returns
    a Flask Response when the limit is hit (caller short-circuits), or
    None when the call is allowed to proceed.

    SD-AUD-M7: takes a validated Engagement object (not a raw id) so the
    audit-event append cannot crash on an unverified engagement and an
    attacker cannot trip the alert for an engagement they don't own.
    """
    limiter: Optional[ExportRateLimiter] = current_app.config.get("EXPORT_LIMITER")
    if limiter is None:
        return None
    rl = limiter.consume(user.id)
    # M2 fix: edge-trigger — fire exactly once at the boundary.
    if rl.current_count == rl.hard_limit:
        from .engagement import AuditEventType
        _store()._append_audit_event(
            engagement_id=eng.id,
            event_type=AuditEventType.bulk_export_alert,
            payload={
                "user_id": user.id,
                "count": rl.current_count,
                "soft_limit": rl.soft_limit,
                "hard_limit": rl.hard_limit,
            },
            actor=user,
        )
    if not rl.allowed:
        resp = jsonify({
            "error": (
                f"export rate limit exceeded "
                f"({rl.current_count}/{rl.soft_limit} per hour)"
            ),
            "error_code": "export-rate-limit",
            "current_count": rl.current_count,
            "soft_limit": rl.soft_limit,
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(rl.retry_after_seconds)
        return resp
    return None


# ---- Error handler decorator -----------------------------------------------


def _engagement_errors(fn: Callable) -> Callable:
    """Translate EngagementError subclasses to spec-compliant HTTP responses.

    W4-AUDIT M-3 fix: respect content-negotiation. The HTMX UI submits
    HTML forms and expects HTML responses on 4xx/5xx. Returning JSON
    crashed the UI (browser renders raw JSON). When _wants_html(),
    render the engagement base template with an error banner.
    """

    def wrapper(*args: Any, **kwargs: Any):
        try:
            return fn(*args, **kwargs)
        except EngagementError as e:
            body = {
                "error": str(e),
                "error_code": e.error_code,
            }
            if isinstance(e, EngagementVersionConflict):
                body["expected_version"] = e.expected
                body["current_version"] = e.current
            try:
                wants_html = _wants_html()
            except RuntimeError:
                wants_html = False
            if wants_html:
                return render_template(
                    "engagement/base.html",
                    error=f"[{e.error_code}] {e}",
                    current_user=getattr(g, "current_user", None),
                ), e.http_status
            return jsonify(body), e.http_status
        except PDFMemoError as e:
            try:
                wants_html = _wants_html()
            except RuntimeError:
                wants_html = False
            if wants_html:
                return render_template(
                    "engagement/base.html",
                    error=f"[{e.error_code}] {e}",
                    current_user=getattr(g, "current_user", None),
                ), e.http_status
            return jsonify({"error": str(e), "error_code": e.error_code}), e.http_status
        except ValidationError as e:
            try:
                wants_html = _wants_html()
            except RuntimeError:
                wants_html = False
            if wants_html:
                return render_template(
                    "engagement/base.html",
                    error=f"[validation-failed] {e}",
                    current_user=getattr(g, "current_user", None),
                ), 400
            return jsonify({"error": str(e), "error_code": "validation-failed"}), 400

    wrapper.__name__ = fn.__name__
    return wrapper


# ---- Blueprint factory -----------------------------------------------------


def build_engagement_blueprint() -> Blueprint:
    # W4.1: point the blueprint at the repo's `templates/` so HTML
    # renders even when the host Flask app didn't configure a template
    # folder (e.g., the test fixtures).
    _templates_dir = Path(__file__).parent.parent / "templates"
    bp = Blueprint(
        "engagement",
        __name__,
        url_prefix="/engagement",
        template_folder=str(_templates_dir),
    )

    @bp.before_request
    def _auth_guard():
        _require_user()
        # W6.1: CSRF check only when this request authenticated via the
        # ambient session cookie. Bearer-authenticated requests are exempt
        # because the credential is explicit (matches SD-AUD-B5 model).
        if g.get("auth_source") == "cookie":
            from .cookie_auth import verify_csrf
            err = verify_csrf()
            if err is not None:
                # SD-AUD-W6M-5: render HTML when the request wanted HTML so
                # the HTMX swap target receives a styled error rather than
                # raw JSON. Match the rest of the 4xx UX discipline.
                if _wants_html():
                    from flask import render_template
                    body = render_template(
                        "engagement/error.html",
                        error_code=err,
                        error_message="CSRF check failed",
                        current_user=g.current_user,
                    )
                    abort(Response(body, status=403, mimetype="text/html"))
                resp = jsonify({"error": "CSRF check failed", "error_code": err})
                resp.status_code = 403
                abort(resp)

    @bp.after_request
    def _heal_csrf_cookie(response):
        # SD-AUD-W6B-2: pre-W6 cookie sessions hold a valid session
        # cookie but no CSRF cookie; auto-issue on the next safe-method
        # response so the next form submit succeeds.
        # SD-AUD-W9-B1: rotation MUST happen in the same code path that
        # injects the template variable, otherwise the form body
        # carries the OLD token while the cookie holds the NEW token →
        # next POST 403s with csrf-mismatch. The context_processor
        # below decides the rotation and stashes the chosen value on
        # `g._minted_csrf`; this hook just attaches the cookie that
        # matches whatever the template rendered.
        from .cookie_auth import attach_csrf_cookie
        if (
            g.get("auth_source") == "cookie"
            and request.method in ("GET", "HEAD")
            and response.status_code < 400
            and g.get("_minted_csrf") is not None
        ):
            attach_csrf_cookie(response, g._minted_csrf)
        return response

    @bp.context_processor
    def _inject_csrf():
        # W6.1: every Jinja template that posts a form reads csrf_token
        # from context and renders it as a hidden input.
        # SD-AUD-W9-B1: this is the SINGLE place that decides whether
        # the request rotates its CSRF token. Decision lattice:
        #   - no existing cookie  → mint new (auto-heal)
        #   - existing is stale or invalid → mint new (rotation)
        #   - existing is fresh   → keep
        # The chosen value is stashed on g._minted_csrf so the
        # after_request hook attaches the matching cookie. Template
        # form body and response cookie therefore agree on the same
        # token regardless of rotation timing.
        from .cookie_auth import (
            CSRF_ROTATION_SECONDS, csrf_token_age_seconds,
            csrf_token_for_request, issue_csrf_token,
        )
        existing = csrf_token_for_request()
        chosen: Optional[str]
        if not existing:
            chosen = issue_csrf_token() if g.get("auth_source") == "cookie" else ""
        else:
            age = csrf_token_age_seconds(existing)
            if (
                g.get("auth_source") == "cookie"
                and (age is None or age > CSRF_ROTATION_SECONDS or age < 0)
            ):
                chosen = issue_csrf_token()
            else:
                chosen = existing
        # Stash the rotation/auto-heal decision so after_request can
        # attach the matching cookie. Only when we actually changed the
        # value — passing the existing token through doesn't need a
        # cookie write.
        if (
            chosen and chosen != existing
            and g.get("auth_source") == "cookie"
        ):
            g._minted_csrf = chosen
        return {"csrf_token": chosen or ""}

    # ---- Create + list ----------------------------------------------

    @bp.post("/")
    @_engagement_errors
    def create_engagement():
        user = g.current_user
        # W4.1: accept both JSON and form-encoded payloads.
        payload = request.get_json(silent=True) or {}
        if not payload and request.form:
            payload = request.form.to_dict()
        client_id = payload.get("client_id")
        standard = payload.get("standard_of_value", "ifrs13")
        valuation_date = payload.get("valuation_date") or None
        if not client_id:
            if _wants_html():
                return render_template(
                    "engagement/list.html",
                    items=[], total=0, offset=0, filters={},
                    can_create=can(user, "engagement.create"),
                    current_user=user,
                    error="client_id required",
                ), 400
            return jsonify({
                "error": "client_id required",
                "error_code": "client-id-required",
            }), 400
        pack = head_pack()
        eng = _store().create_engagement(
            actor=user,
            client_id=client_id,
            standard_of_value=standard,
            pack_version=pack.version,
            engine_version=current_engine_commit(),
            valuation_date=valuation_date,
        )
        if _wants_html():
            return redirect(url_for("engagement.show", eng_id=eng.id) + "?html=1")
        return jsonify(eng.model_dump(mode="json")), 201

    @bp.get("/")
    @_engagement_errors
    def list_engagements():
        user = g.current_user
        # W3.2: structured filter + pagination surface.
        client_id = request.args.get("client_id")
        status_filter = request.args.get("status")
        standard_filter = request.args.get("standard_of_value")
        date_from = request.args.get("date_from")  # ISO date or empty
        date_to = request.args.get("date_to")
        q = (request.args.get("q") or "").strip().lower()
        try:
            limit = max(1, min(int(request.args.get("limit", "50")), 200))
            offset = max(0, int(request.args.get("offset", "0")))
        except ValueError:
            return jsonify({
                "error": "limit/offset must be integers",
                "error_code": "bad-pagination",
            }), 400

        # W3-AUDIT M1: reviewer/partner cannot enumerate the full
        # engagement table without first scoping to a client_id. Without
        # this, the new W3.2 pagination surface lets a reviewer iterate
        # every engagement in the database. The deep tenancy ACL is
        # GAP-39 — this is a partial mitigation.
        if user.role in (Role.reviewer, Role.partner) and not client_id:
            return jsonify({
                "error": (
                    f"{user.role.value} must scope list queries by client_id "
                    f"(use ?client_id=...). Engagement-level tenancy ACL "
                    f"(GAP-39) is a future enhancement."
                ),
                "error_code": "client-id-required-for-role",
            }), 400

        engagements = _store().list_engagements(client_id=client_id)

        # Role-based prefilter
        if user.role == Role.analyst:
            engagements = [e for e in engagements if e.created_by == user.id]
        elif user.role == Role.read_only_auditor:
            engagements = []

        # Field filters
        if status_filter:
            engagements = [e for e in engagements if e.status.value == status_filter]
        if standard_filter:
            engagements = [
                e for e in engagements
                if e.standard_of_value == standard_filter
            ]
        # W4.5: valuation_date is now `date`, not str. Parse query
        # params with date.fromisoformat; reject malformed.
        date_from_d = None
        date_to_d = None
        if date_from:
            try:
                date_from_d = date.fromisoformat(date_from)
            except ValueError:
                return jsonify({
                    "error": f"date_from must be ISO date (YYYY-MM-DD), got {date_from!r}",
                    "error_code": "bad-date-filter",
                }), 400
        if date_to:
            try:
                date_to_d = date.fromisoformat(date_to)
            except ValueError:
                return jsonify({
                    "error": f"date_to must be ISO date (YYYY-MM-DD), got {date_to!r}",
                    "error_code": "bad-date-filter",
                }), 400
        if date_from_d:
            engagements = [
                e for e in engagements
                if e.valuation_date and e.valuation_date >= date_from_d
            ]
        if date_to_d:
            engagements = [
                e for e in engagements
                if e.valuation_date and e.valuation_date <= date_to_d
            ]
        if q:
            engagements = [
                e for e in engagements
                if q in (e.client_id or "").lower()
                or q in (e.id or "").lower()
                or q in (e.standard_of_value or "").lower()
            ]

        total = len(engagements)
        page = engagements[offset:offset + limit]
        if _wants_html():
            return render_template(
                "engagement/list.html",
                items=[e.model_dump(mode="json") for e in page],
                total=total, offset=offset, limit=limit,
                filters={
                    "client_id": client_id, "status": status_filter,
                    "standard_of_value": standard_filter,
                    "date_from": date_from, "date_to": date_to, "q": q,
                },
                can_create=can(user, "engagement.create"),
                current_user=user,
            )
        return jsonify({
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [e.model_dump(mode="json") for e in page],
        })

    # ---- Show -------------------------------------------------------

    @bp.get("/<eng_id>")
    @_engagement_errors
    def show(eng_id: str):
        user = g.current_user
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        eng = _store().get_engagement(eng_id)
        snapshots = _store().list_snapshots(eng_id)
        if _wants_html():
            # Compute allowed-next-statuses for the action buttons.
            from .engagement import _ALLOWED_TRANSITIONS, _TRANSITION_PERMISSION
            allowed = []
            for target in _ALLOWED_TRANSITIONS.get(eng.status, set()):
                action = _TRANSITION_PERMISSION.get((eng.status, target))
                if action is None or can(user, action):
                    allowed.append(target.value)
            # W5.1: collect preferred-class names for /whatif form
            # auto-generation. W5.2: collect head-snapshot findings for
            # inline resolution form. W5.3: build subsequent-events
            # rollup.
            preferred_classes: list[str] = []
            findings_for_ui: list[dict] = []
            subsequent_events_rollup = None
            if eng.head_snapshot_id:
                try:
                    head = _store().get_snapshot(eng.head_snapshot_id)
                    head_ct = head.load_cap_table()
                    if head_ct is not None:
                        for sc in head_ct.share_classes:
                            if sc.type.value == "preferred":
                                preferred_classes.append({
                                    "name": sc.name,
                                    "shares": sc.shares_outstanding,
                                    "lp_mult": (
                                        sc.liquidation_preference.multiple
                                        if sc.liquidation_preference else 1.0
                                    ),
                                })
                        # Findings + resolved set for the inline form.
                        from .rule_pack import RulePack as _RulePack
                        bound_pack = None
                        if eng.bound_pack_json:
                            try:
                                bound_pack = _RulePack.model_validate_json(eng.bound_pack_json)
                            except Exception:
                                pass
                        from .rule_pack import load_engagement_bound_pack
                        if bound_pack is None:
                            try:
                                bound_pack = load_engagement_bound_pack(eng.pack_version)
                            except Exception:
                                pass
                        findings = run_pack(head_ct, pack=bound_pack) if bound_pack else []
                        resolved = {
                            r.finding_code
                            for r in _store().list_resolutions(head.id)
                        }
                        for f in findings:
                            findings_for_ui.append({
                                "code": f.code,
                                "severity": f.severity,
                                "summary": f.summary,
                                "resolved": f.code in resolved,
                                "snapshot_id": head.id,
                            })
                        # W5.3 — subsequent events rollup
                        from .subsequent_events import (
                            compute_subsequent_events, group_events_by_category,
                        )
                        rollup = compute_subsequent_events(_store(), eng.id, pack=bound_pack)
                        subsequent_events_rollup = {
                            "rollup": rollup,
                            "by_category": group_events_by_category(rollup),
                        }
                except Exception:
                    pass

            return render_template(
                "engagement/detail.html",
                engagement=eng,
                snapshots=[
                    {
                        "id": s.id,
                        "source": s.source.value,
                        "source_filename": s.source_filename,
                        "created_at": s.created_at.isoformat(),
                        "redacted": s.redacted,
                        "superseded_by": s.superseded_by,
                    }
                    for s in snapshots
                ],
                can_upload=can(user, "engagement.upload_cap_table"),
                can_resolve=can(user, "engagement.resolve_finding"),
                allowed_transitions=allowed,
                preferred_classes=preferred_classes,
                findings_for_ui=findings_for_ui,
                subsequent_events=subsequent_events_rollup,
                current_user=user,
            )
        return jsonify({
            "engagement": eng.model_dump(mode="json"),
            "snapshots": [
                {
                    "id": s.id,
                    "source": s.source.value,
                    "source_filename": s.source_filename,
                    "created_at": s.created_at.isoformat(),
                    "redacted": s.redacted,
                    "superseded_by": s.superseded_by,
                }
                for s in snapshots
            ],
        })

    # ---- Upload (Excel → new snapshot) ------------------------------

    @bp.post("/<eng_id>/upload")
    @_engagement_errors
    def upload(eng_id: str):
        user = g.current_user
        # M6 fix: gate on upload permission explicitly. Without this,
        # reviewer (who has engagement.add_snapshot) could upload Excel.
        # Per SYSTEM_SPEC §3.2 the analyst is the only role that uploads.
        if not can(user, "engagement.upload_cap_table"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.upload_cap_table",
                "error_code": "permission-denied",
            }), 403
        file = request.files.get("file")
        if file is None or not file.filename:
            return jsonify({
                "error": "no file uploaded",
                "error_code": "no-file",
            }), 400
        if not file.filename.lower().endswith((".xlsx", ".xlsm")):
            return jsonify({
                "error": "only .xlsx / .xlsm supported",
                "error_code": "unsupported-file-type",
            }), 400
        eng = _store().get_engagement(eng_id)
        expected_version_raw = request.form.get("expected_version")
        if expected_version_raw is None or expected_version_raw == "":
            return jsonify({
                "error": "expected_version required",
                "error_code": "missing-expected-version",
            }), 400
        try:
            expected_version = int(expected_version_raw)
        except ValueError:
            return jsonify({
                "error": "expected_version must be an integer",
                "error_code": "missing-expected-version",
            }), 400
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
            fh.write(file.read())
            tmp_path = Path(fh.name)
        try:
            try:
                cap_table, report = parse_excel(tmp_path)
            except (ValueError, KeyError, ValidationError,
                    openpyxl.utils.exceptions.InvalidFileException,
                    zipfile.BadZipFile) as e:
                return jsonify({
                    "error": f"could not parse: {e}",
                    "error_code": "parse-failed",
                }), 400
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

        # Persist the parse_report alongside the snapshot.
        import json
        from dataclasses import asdict as _asdict
        try:
            parse_report_json = json.dumps(_asdict(report))
        except Exception:
            parse_report_json = None

        change_note = (request.form.get("change_note") or "").strip() or None
        # SD-AUD-W7-B2 + m-W7-2: validate at upload boundary so the bad
        # bytes never reach SQLite (and therefore never reach openpyxl).
        if change_note is not None:
            import re as _re
            _ILLEGAL_XLSX = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
            if _ILLEGAL_XLSX.search(change_note):
                return jsonify({
                    "error": "change_note contains control characters that the workpaper exporter cannot render",
                    "error_code": "change-note-illegal-character",
                }), 400
            if len(change_note) > 32767:
                return jsonify({
                    "error": "change_note exceeds 32767 characters (Excel cell limit)",
                    "error_code": "change-note-too-long",
                }), 400
        snap = _store().add_snapshot(
            actor=user,
            engagement_id=eng_id,
            expected_version=expected_version,
            cap_table=cap_table,
            source=SnapshotSource.excel_upload,
            source_filename=file.filename,
            parse_report_json=parse_report_json,
            change_note=change_note,
        )
        if _wants_html():
            return redirect(url_for("engagement.show", eng_id=eng_id) + "?html=1")
        return jsonify({
            "snapshot_id": snap.id,
            "engagement_version": _store().get_engagement(eng_id).version,
            "warnings": [
                {"code": w.code, "message": w.message}
                for w in (report.warnings if report else [])
            ],
        }), 201

    # ---- Resolution -------------------------------------------------

    @bp.post("/<eng_id>/resolve")
    @_engagement_errors
    def resolve(eng_id: str):
        user = g.current_user
        # W5.2: accept JSON or form-encoded.
        payload = request.get_json(silent=True) or {}
        if not payload and request.form:
            payload = request.form.to_dict()
            # decision may arrive as a plain JSON string in the form
            import json as _json
            decision_raw = payload.get("decision")
            if isinstance(decision_raw, str):
                try:
                    payload["decision"] = _json.loads(decision_raw)
                except Exception:
                    payload["decision"] = {"note": decision_raw}
        snapshot_id = payload.get("snapshot_id")
        finding_code = payload.get("finding_code")
        decision = payload.get("decision") or {}
        citation = payload.get("citation", "")
        if not snapshot_id or not finding_code:
            return jsonify({
                "error": "snapshot_id and finding_code required",
                "error_code": "missing-resolution-fields",
            }), 400
        res = _store().record_resolution(
            actor=user,
            snapshot_id=snapshot_id,
            finding_code=finding_code,
            decision=decision,
            citation=citation,
        )
        if _wants_html():
            # Return an HTMX-swap partial confirming the resolution.
            return render_template(
                "engagement/_resolution_ok.html",
                finding_code=finding_code,
                resolved_at=res.resolved_at.isoformat(),
                current_user=user,
            )
        return jsonify({
            "resolution_id": res.id,
            "resolved_at": res.resolved_at.isoformat(),
        }), 201

    # ---- Transition -------------------------------------------------

    @bp.post("/<eng_id>/transition")
    @_engagement_errors
    def transition(eng_id: str):
        user = g.current_user
        # W4.1: accept JSON or form-encoded
        payload = request.get_json(silent=True) or {}
        if not payload and request.form:
            payload = request.form.to_dict()
        new_status = payload.get("new_status")
        expected_version = payload.get("expected_version")
        note = payload.get("note")
        if not new_status:
            return jsonify({
                "error": "new_status required",
                "error_code": "missing-status",
            }), 400
        if expected_version is None:
            return jsonify({
                "error": "expected_version required",
                "error_code": "missing-expected-version",
            }), 400
        try:
            target = EngagementStatus(new_status)
        except ValueError:
            return jsonify({
                "error": f"unknown status {new_status!r}",
                "error_code": "unknown-status",
            }), 400
        eng = _store().transition(
            actor=user, engagement_id=eng_id,
            expected_version=int(expected_version),
            new_status=target, note=note,
        )
        if _wants_html():
            return redirect(url_for("engagement.show", eng_id=eng.id) + "?html=1")
        return jsonify(eng.model_dump(mode="json"))

    # ---- Restore archived (W8.10, partner only within 90-day window) ----

    @bp.post("/<eng_id>/restore")
    @_engagement_errors
    def restore_archived(eng_id: str):
        """W8.10: partner restores an archived engagement within the
        90-day window. Implemented as a status transition (archived →
        open) so the audit chain captures it via the existing
        transition event; the transition() method enforces the window."""
        user = g.current_user
        payload = request.get_json(silent=True) or {}
        if not payload and request.form:
            payload = request.form.to_dict()
        expected_version = payload.get("expected_version")
        if expected_version is None:
            return jsonify({
                "error": "expected_version required",
                "error_code": "missing-expected-version",
            }), 400
        eng = _store().transition(
            actor=user, engagement_id=eng_id,
            expected_version=int(expected_version),
            new_status=EngagementStatus.open,
            note=payload.get("note", "restored from archive"),
        )
        if _wants_html():
            return redirect(url_for("engagement.show", eng_id=eng.id) + "?html=1")
        return jsonify(eng.model_dump(mode="json"))

    # ---- Redaction (partner only) -----------------------------------

    @bp.post("/<eng_id>/redact/<snap_id>")
    @_engagement_errors
    def redact(eng_id: str, snap_id: str):
        user = g.current_user
        payload = request.get_json(silent=True) or {}
        request_ref = payload.get("request_reference", "")
        legal_basis = payload.get("legal_basis", "")
        if not request_ref or not legal_basis:
            return jsonify({
                "error": "request_reference and legal_basis required",
                "error_code": "missing-redaction-fields",
            }), 400
        snap = _store().redact_snapshot_pii(
            actor=user, snapshot_id=snap_id,
            request_reference=request_ref, legal_basis=legal_basis,
        )
        return jsonify({"snapshot_id": snap.id, "redacted": snap.redacted})

    # ---- Memo -------------------------------------------------------

    @bp.get("/<eng_id>/memo.pdf")
    @_engagement_errors
    def memo(eng_id: str):
        user = g.current_user
        # M3 fix: authorise BEFORE consuming rate budget. Otherwise a
        # token-holder with the wrong role can DOS another user's hourly
        # export budget through repeated 403'd requests.
        if not can(user, "export.memo_pdf"):
            return jsonify({
                "error": f"{user.role.value} cannot export.memo_pdf",
                "error_code": "permission-denied",
            }), 403
        # Fetch BEFORE rate-limit consume so the audit event referenced by
        # a hard-limit hit always points at a real engagement (SD-AUD-M7).
        eng = _store().get_engagement(eng_id)
        limit_response = _enforce_export_limit(eng, user)
        if limit_response is not None:
            return limit_response
        if not eng.head_snapshot_id:
            return jsonify({
                "error": "engagement has no snapshot",
                "error_code": "no-snapshot",
            }), 400
        snap = _store().get_snapshot(eng.head_snapshot_id)
        cap_table = snap.load_cap_table()
        if cap_table is None:
            return jsonify({
                "error": "head snapshot is redacted",
                "error_code": "snapshot-redacted",
            }), 410

        from .waterfall import compute_waterfall
        waterfall = compute_waterfall(cap_table)
        # B-1 (system-audit-1) fix: bind to engagement's pack, not head.
        # W4-AUDIT B-2 fix: prefer pinned bytes over disk lookup (same
        # precedence as bundle); only fall back to disk if pinned bytes
        # are absent or corrupt. Otherwise memo and bundle disagree on
        # findings when the disk file is mutated post-create.
        from .rule_pack import RulePack as _RulePack
        pack = None
        if eng.bound_pack_json:
            try:
                pack = _RulePack.model_validate_json(eng.bound_pack_json)
            except Exception:
                pack = None
        if pack is None:
            pack = load_engagement_bound_pack(eng.pack_version)
        findings = run_pack(cap_table, pack=pack)
        resolutions_list = _store().list_resolutions(snap.id)
        # The reviewer name comes from the query string in dev; in production
        # it comes from the engagement's reviewer-assignment table (future).
        reviewer_name = request.args.get("reviewer", "").strip()
        if not reviewer_name and user.role in (Role.reviewer, Role.partner):
            reviewer_name = user.display_name
        reviewer = ReviewerInfo(
            reviewer_name=reviewer_name,
            preparer=user.display_name,
        ) if reviewer_name else None

        # W3.1: compute subsequent events from the engagement's snapshot
        # chain (closes audit M7 — prior resolutions stay visible).
        rollup = compute_subsequent_events(_store(), eng.id, pack=pack)

        # W8.11: auto-compute the N-way timeline diff across the
        # engagement's snapshot chain. Memo renders the per-class drift
        # table only when 2+ snapshots exist; otherwise the section
        # silently omits.
        # SD-AUD-W8-m4: never regress memo generation because a stale
        # non-head snapshot has bad JSON. The head snapshot already
        # validated upstream; if any historical snapshot raises during
        # CapTable revalidation, drop the timeline section and log.
        timeline_diff = None
        all_snaps = _store().list_snapshots(eng.id)
        if len(all_snaps) >= 2:
            from .snapshot_timeline import compute_timeline_diff, SnapshotMeta
            try:
                metas = [
                    SnapshotMeta(
                        id=s.id, created_at=s.created_at,
                        source_filename=s.safe_source_filename(),
                        created_by=s.safe_created_by(),
                        change_note=s.safe_change_note(),
                    )
                    for s in all_snaps
                ]
                timeline_diff = compute_timeline_diff(
                    metas, [s.load_cap_table() for s in all_snaps],
                )
            except Exception as exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "memo timeline-diff auto-compute failed for eng %s: %s",
                    eng.id, exc,
                )
                timeline_diff = None

        inputs = PDFInputs(
            cap_table=cap_table,
            waterfall=waterfall,
            findings=findings,
            resolutions=[
                {
                    "finding_code": r.finding_code,
                    "decision_summary": r.decision_json,
                    "citation": r.citation,
                    "resolved_by": r.resolved_by,
                }
                for r in resolutions_list
            ],
            reviewer=reviewer,
            engagement_id=eng.id,
            pack=pack,
            engine_version=eng.engine_version,
            memo_version="1.0",
            standard_of_value=eng.standard_of_value,
            subsequent_events=rollup,
            timeline_diff=timeline_diff,  # W8.11
            generated_at=eng.created_at,  # SD-AUD-M1 pin
        )
        pdf_bytes = render_pdf_memo(inputs)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"memo-{eng.id[:8]}.pdf",
        )

    # ---- W9.2 OPM Backsolve (engagement-bound) ----------------------

    @bp.post("/<eng_id>/opm")
    @_engagement_errors
    def opm_backsolve_route(eng_id: str):
        """W9.2: run OPM Backsolve against the engagement's head snapshot.

        Posture (per Evelyn's "expert-led" register): the tool does NOT
        pick volatility, TTL, risk-free rate, DLOM, or the anchor — the
        analyst defends those numbers in the workpaper. This route is
        purely the solver wrapper that takes their numbers and returns
        per-class fair value.

        Permission: `engagement.read` (the backsolve doesn't mutate the
        cap table; the analyst still has to write the result into a
        memo). Compute-rate-limited via COMPUTE_LIMITER. Audit event
        `opm_backsolve_run` records the inputs + solved equity value so
        the chain captures the calibration moment.

        Body (JSON or form):
          volatility, time_to_liquidity_years, risk_free_rate,
          dividend_yield (opt), dlom (opt),
          anchor_class_name, anchor_price_per_share,
          anchor_raise_amount (opt).
        """
        user = g.current_user
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        eng = _store().get_engagement(eng_id)
        if not eng.head_snapshot_id:
            return jsonify({
                "error": "engagement has no snapshot — upload first",
                "error_code": "no-snapshot",
            }), 400

        # Compute-budget gate (mirrors /whatif + /diff).
        # SD-AUD-W9-M4: also emit compute_burst_alert at the hard-limit
        # boundary so OPM abuse lands in the engagement audit chain the
        # same way /whatif and /diff already do.
        compute_limiter: Optional[ExportRateLimiter] = current_app.config.get("COMPUTE_LIMITER")
        if compute_limiter is not None:
            rl = compute_limiter.consume(user.id)
            if rl.current_count == rl.hard_limit:
                from .engagement import AuditEventType
                _store()._append_audit_event(
                    engagement_id=eng.id,
                    event_type=AuditEventType.compute_burst_alert,
                    payload={
                        "user_id": user.id,
                        "count": rl.current_count,
                        "soft_limit": rl.soft_limit,
                        "hard_limit": rl.hard_limit,
                        "route": "opm",
                    },
                    actor=user,
                )
            if not rl.allowed:
                resp = jsonify({
                    "error": (
                        f"compute rate limit exceeded "
                        f"({rl.current_count}/{rl.soft_limit} per hour)"
                    ),
                    "error_code": "compute-rate-limit",
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(rl.retry_after_seconds)
                return resp

        payload = request.get_json(silent=True) or {}
        if not payload and request.form:
            payload = request.form.to_dict()

        # SD-AUD-W9-M2 + m-6: stable kebab-case error codes per
        # BacksolveError subclass; MarketInputs domain checks live in
        # its __post_init__ so a negative-vol typo is rejected here
        # instead of silently producing "defendable" output downstream.
        from .opm.backsolve import (
            AnchorInputs, BacksolveAnchorMissing, BacksolveBlockersOutstanding,
            BacksolveError, BacksolveSolverFailed, MarketInputs, backsolve,
        )
        _OPM_ERROR_CODES = {
            BacksolveBlockersOutstanding: "backsolve-blockers-outstanding",
            BacksolveSolverFailed: "backsolve-solver-failed",
            BacksolveAnchorMissing: "backsolve-anchor-missing",
        }
        try:
            market = MarketInputs(
                volatility=float(payload["volatility"]),
                time_to_liquidity_years=float(payload["time_to_liquidity_years"]),
                risk_free_rate=float(payload["risk_free_rate"]),
                dividend_yield=float(payload.get("dividend_yield", 0.0) or 0.0),
                dlom=float(payload.get("dlom", 0.0) or 0.0),
            )
            anchor = AnchorInputs(
                class_name=str(payload["anchor_class_name"]),
                price_per_share=float(payload["anchor_price_per_share"]),
                raise_amount=(
                    float(payload["anchor_raise_amount"])
                    if payload.get("anchor_raise_amount") else None
                ),
            )
        except BacksolveError as exc:
            # Domain-check rejection from MarketInputs.__post_init__.
            return jsonify({
                "error": str(exc),
                "error_code": "opm-bad-inputs",
            }), 400
        except (KeyError, ValueError, TypeError) as exc:
            return jsonify({
                "error": f"missing or invalid OPM input: {exc}",
                "error_code": "opm-bad-inputs",
            }), 400

        snap = _store().get_snapshot(eng.head_snapshot_id)
        cap_table = snap.load_cap_table()
        if cap_table is None:
            return jsonify({
                "error": "head snapshot is redacted",
                "error_code": "snapshot-redacted",
            }), 410

        from .checklist import run_checklist
        from .rule_pack import RulePack as _RulePack, load_engagement_bound_pack
        pack = None
        if eng.bound_pack_json:
            try:
                pack = _RulePack.model_validate_json(eng.bound_pack_json)
            except Exception:
                pack = None
        if pack is None:
            try:
                pack = load_engagement_bound_pack(eng.pack_version)
            except Exception:
                pack = None
        from .rule_pack import run_pack
        findings = run_pack(cap_table, pack=pack)

        try:
            result = backsolve(cap_table, findings, market, anchor)
        except BacksolveError as exc:
            code = _OPM_ERROR_CODES.get(type(exc), "backsolve-error")
            return jsonify({"error": str(exc), "error_code": code}), 400

        # W9.2 audit event: capture the inputs + result so the chain
        # records the calibration moment.
        from .engagement import AuditEventType
        _store()._append_audit_event(
            engagement_id=eng.id,
            event_type=AuditEventType.opm_backsolve_run,
            payload={
                "snapshot_id": snap.id,
                "anchor_class": anchor.class_name,
                "anchor_pps": anchor.price_per_share,
                "volatility": market.volatility,
                "ttl_years": market.time_to_liquidity_years,
                "risk_free": market.risk_free_rate,
                "dlom": market.dlom,
                "implied_total_equity_value": result.implied_total_equity_value,
            },
            actor=user,
        )

        return jsonify({
            "implied_total_equity_value": result.implied_total_equity_value,
            "market_inputs": {
                "volatility": market.volatility,
                "time_to_liquidity_years": market.time_to_liquidity_years,
                "risk_free_rate": market.risk_free_rate,
                "dividend_yield": market.dividend_yield,
                "dlom": market.dlom,
            },
            "anchor": {
                "class_name": anchor.class_name,
                "price_per_share": anchor.price_per_share,
                "raise_amount": anchor.raise_amount,
            },
            "per_class": [
                {
                    "name": pc.name,
                    "total_value": pc.total_value,
                    "shares_for_fv": pc.shares_for_fv,
                    "fair_value_per_share": pc.fair_value_per_share,
                    "fair_value_per_share_after_dlom": pc.fair_value_per_share_after_dlom,
                }
                for pc in result.per_class
            ],
        })

    # ---- Audit log --------------------------------------------------

    @bp.get("/<eng_id>/audit-log")
    @_engagement_errors
    def audit_log(eng_id: str):
        user = g.current_user
        # B4 fix: enforce engagement.read on every detail route. Full
        # engagement-level tenancy ACL (one specific token tied to one
        # specific engagement_id) is GAP-39, deferred to a later wave.
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        events = _store().list_audit_events(eng_id)
        return jsonify([
            {
                "id": e.id,
                "event_type": e.event_type.value,
                "actor": e.actor,
                "ts": e.ts.isoformat(),
                "payload": e.payload_json,
                "prev_row_hash": e.prev_row_hash,
                "row_hash": e.row_hash,
            }
            for e in events
        ])

    @bp.get("/<eng_id>/verify")
    @_engagement_errors
    def verify(eng_id: str):
        user = g.current_user
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        ok, problem = _store().verify_audit_log(eng_id)
        return jsonify({"ok": ok, "problem": problem})

    # ---- W7.1 Snapshot timeline -------------------------------------

    @bp.get("/<eng_id>/snapshots")
    @_engagement_errors
    def snapshots_timeline(eng_id: str):
        """Chronological snapshot listing for the engagement. HTML page
        renders the analyst-facing timeline; JSON returns the raw
        metadata for API clients (W7.1).

        W9.7: pagination via ?limit + ?offset (defaults limit=50, max
        100). The HTML template renders prev/next links + an N-of-total
        counter. The JSON response wraps the items in a small envelope
        so the API stays stable as the list grows.
        """
        user = g.current_user
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        try:
            limit = int(request.args.get("limit", "50"))
            offset = int(request.args.get("offset", "0"))
        except ValueError:
            return jsonify({
                "error": "limit and offset must be integers",
                "error_code": "bad-pagination",
            }), 400
        if limit < 1 or limit > 100 or offset < 0:
            return jsonify({
                "error": "limit must be 1..100, offset must be >= 0",
                "error_code": "bad-pagination",
            }), 400
        eng = _store().get_engagement(eng_id)
        # SD-AUD-W9-M1: pagination pushed into SQL so a `?limit=1`
        # request doesn't materialise every snapshot's cap_table_json
        # blob into memory.
        total = _store().count_snapshots(eng_id)
        snaps = _store().list_snapshots(eng_id, limit=limit, offset=offset)
        if _wants_html():
            return render_template(
                "engagement/snapshots.html",
                engagement=eng,
                snapshots=snaps,
                pagination={
                    "limit": limit,
                    "offset": offset,
                    "total": total,
                    "has_prev": offset > 0,
                    "has_next": offset + limit < total,
                    "prev_offset": max(0, offset - limit),
                    "next_offset": offset + limit,
                },
                current_user=user,
            )
        return jsonify([
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                # W8.6: created_by goes through the redaction-safe view too.
                "created_by": s.safe_created_by(),
                # SD-AUD-W7-B1: redacted snapshots drop the PII-bearing
                # fields at the rendering boundary, in addition to the
                # DB-level zero.
                "source_filename": s.safe_source_filename(),
                "redacted": s.redacted,
                "change_note": s.safe_change_note(),
                "is_head": s.id == eng.head_snapshot_id,
            }
            for s in snaps
        ])

    # ---- W7.2 N-way snapshot diff -----------------------------------

    @bp.get("/<eng_id>/diff")
    @_engagement_errors
    def snapshots_diff(eng_id: str):
        """N-way diff across the snapshot IDs given via repeated ?snap=
        query params. Supports HTML (analyst page) + JSON (API)."""
        user = g.current_user
        if not can(user, "engagement.read"):
            return _diff_error(
                "permission-denied",
                f"{user.role.value} cannot engagement.read",
                403,
            )
        snap_ids, err = _parse_diff_snap_ids()
        if err is not None:
            return _diff_error_from_response(err)
        eng = _store().get_engagement(eng_id)
        # SD-AUD-W7-M1: /diff does material compute (N JSON loads +
        # CapTable revalidations + class union); gate it on the same
        # COMPUTE_LIMITER as /whatif so abusive callers can't burn CPU
        # silently. Emit a compute_burst_alert at the hard boundary so
        # the abuse lands in the engagement's audit chain.
        compute_limiter: Optional[ExportRateLimiter] = current_app.config.get("COMPUTE_LIMITER")
        if compute_limiter is not None:
            rl = compute_limiter.consume(user.id)
            if rl.current_count == rl.hard_limit:
                from .engagement import AuditEventType
                _store()._append_audit_event(
                    engagement_id=eng.id,
                    event_type=AuditEventType.compute_burst_alert,
                    payload={
                        "user_id": user.id,
                        "count": rl.current_count,
                        "soft_limit": rl.soft_limit,
                        "hard_limit": rl.hard_limit,
                        "route": "diff",
                    },
                    actor=user,
                )
            if not rl.allowed:
                resp = jsonify({
                    "error": (
                        f"compute rate limit exceeded "
                        f"({rl.current_count}/{rl.soft_limit} per hour)"
                    ),
                    "error_code": "compute-rate-limit",
                    "current_count": rl.current_count,
                    "soft_limit": rl.soft_limit,
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(rl.retry_after_seconds)
                return resp
        snaps = []
        for sid in snap_ids:
            try:
                snap = _store().get_snapshot(sid)
            except SnapshotNotFound:
                return _diff_error(
                    "snapshot-not-found",
                    f"snapshot {sid} not found",
                    404,
                )
            if snap.engagement_id != eng_id:
                return _diff_error(
                    "snapshot-engagement-mismatch",
                    f"snapshot {sid} does not belong to engagement {eng_id}",
                    400,
                )
            snaps.append(snap)
        # Sort chronologically — analyst may pick out of order.
        snaps.sort(key=lambda s: s.created_at)

        from .snapshot_timeline import compute_timeline_diff, SnapshotMeta
        # SD-AUD-W7-B1: use the safe accessors so redacted snapshots don't
        # leak change_note or source_filename through the diff surface.
        metas = [
            SnapshotMeta(
                id=s.id, created_at=s.created_at,
                source_filename=s.safe_source_filename(),
                created_by=s.safe_created_by(),  # W8.6
                change_note=s.safe_change_note(),
            )
            for s in snaps
        ]
        cap_tables = [s.load_cap_table() for s in snaps]
        diff = compute_timeline_diff(metas, cap_tables)

        if _wants_html():
            return render_template(
                "engagement/diff.html",
                engagement=eng,
                diff=diff,
                current_user=user,
            )
        return jsonify({
            "snapshots": [
                {"id": m.id, "created_at": m.created_at.isoformat(),
                 "change_note": m.change_note}
                for m in diff.snapshots
            ],
            "summary": {
                "classes_added": diff.classes_added,
                "classes_removed": diff.classes_removed,
                "classes_changed": diff.classes_changed,
            },
            "rows": [
                {
                    "class_name": r.class_name,
                    "overall_tier": r.overall_tier,
                    "field_tiers": r.field_tiers,
                    "values": [
                        {
                            "snapshot_id": v.snapshot_id,
                            "present": v.class_name is not None,
                            "shares_outstanding": v.shares_outstanding,
                            "issue_price": v.issue_price,
                            "seniority_rank": v.seniority_rank,
                            "lp_variant_label": v.lp_variant_label,
                            "anti_dilution_variant": v.anti_dilution_variant,
                            "conversion_ratio": v.conversion_ratio,
                        }
                        for v in r.views
                    ],
                }
                for r in diff.class_rows
            ],
        })

    # ---- W7.5 Diff workpaper export ---------------------------------

    @bp.get("/<eng_id>/diff.xlsx")
    @_engagement_errors
    def diff_workpaper_xlsx(eng_id: str):
        """Render the N-way diff as an xlsx workpaper. Permission gate
        + export-rate-limit gate + audit event (snapshot_diff_exported)."""
        user = g.current_user
        if not can(user, "export.xlsx"):
            return _diff_error(
                "permission-denied",
                f"{user.role.value} cannot export.xlsx",
                403,
            )
        snap_ids, err = _parse_diff_snap_ids()
        if err is not None:
            return _diff_error_from_response(err)
        eng = _store().get_engagement(eng_id)
        snaps = []
        for sid in snap_ids:
            try:
                snap = _store().get_snapshot(sid)
            except SnapshotNotFound:
                return _diff_error(
                    "snapshot-not-found",
                    f"snapshot {sid} not found",
                    404,
                )
            if snap.engagement_id != eng_id:
                return _diff_error(
                    "snapshot-engagement-mismatch",
                    f"snapshot {sid} does not belong to engagement {eng_id}",
                    400,
                )
            snaps.append(snap)
        snaps.sort(key=lambda s: s.created_at)

        # Rate limit (shares the export budget).
        limit_response = _enforce_export_limit(eng, user)
        if limit_response is not None:
            return limit_response

        from .snapshot_timeline import compute_timeline_diff, SnapshotMeta
        from .diff_workpaper import build_diff_workpaper_xlsx
        # SD-AUD-W7-B1: redaction-safe accessors at the xlsx boundary too.
        metas = [
            SnapshotMeta(
                id=s.id, created_at=s.created_at,
                source_filename=s.safe_source_filename(),
                created_by=s.safe_created_by(),  # W8.6
                change_note=s.safe_change_note(),
            )
            for s in snaps
        ]
        diff = compute_timeline_diff(metas, [s.load_cap_table() for s in snaps])
        blob = build_diff_workpaper_xlsx(diff)

        # W7.6 audit event — the export IS a workpaper deliverable.
        from .engagement import AuditEventType
        _store()._append_audit_event(
            engagement_id=eng.id,
            event_type=AuditEventType.snapshot_diff_exported,
            payload={
                "snapshot_ids": [s.id for s in snaps],
                "format": "xlsx",
                "class_count": len(diff.class_rows),
            },
            actor=user,
        )
        return send_file(
            BytesIO(blob),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"diff-{eng.id[:8]}-{len(snaps)}snaps.xlsx",
        )

    # ---- W8.12 Diff workpaper PDF ----------------------------------

    @bp.get("/<eng_id>/diff.pdf")
    @_engagement_errors
    def diff_workpaper_pdf(eng_id: str):
        """W8.12: same N-way diff, rendered as a stand-alone PDF cover
        sheet + drift table. Permission `export.memo_pdf` (PDF surface);
        consumes the export rate budget; emits the same audit event as
        the xlsx variant for chain-of-custody parity."""
        user = g.current_user
        if not can(user, "export.memo_pdf"):
            return _diff_error(
                "permission-denied",
                f"{user.role.value} cannot export.memo_pdf",
                403,
            )
        snap_ids, err = _parse_diff_snap_ids()
        if err is not None:
            return _diff_error_from_response(err)
        eng = _store().get_engagement(eng_id)
        snaps = []
        for sid in snap_ids:
            try:
                snap = _store().get_snapshot(sid)
            except SnapshotNotFound:
                return _diff_error(
                    "snapshot-not-found",
                    f"snapshot {sid} not found",
                    404,
                )
            if snap.engagement_id != eng_id:
                return _diff_error(
                    "snapshot-engagement-mismatch",
                    f"snapshot {sid} does not belong to engagement {eng_id}",
                    400,
                )
            snaps.append(snap)
        snaps.sort(key=lambda s: s.created_at)
        limit_response = _enforce_export_limit(eng, user)
        if limit_response is not None:
            return limit_response

        from .snapshot_timeline import compute_timeline_diff, SnapshotMeta
        metas = [
            SnapshotMeta(
                id=s.id, created_at=s.created_at,
                source_filename=s.safe_source_filename(),
                created_by=s.safe_created_by(),
                change_note=s.safe_change_note(),
            )
            for s in snaps
        ]
        diff = compute_timeline_diff(metas, [s.load_cap_table() for s in snaps])
        pdf_bytes = render_diff_workpaper_pdf(eng, diff)

        from .engagement import AuditEventType
        _store()._append_audit_event(
            engagement_id=eng.id,
            event_type=AuditEventType.snapshot_diff_exported,
            payload={
                "snapshot_ids": [s.id for s in snaps],
                "format": "pdf",
                "class_count": len(diff.class_rows),
            },
            actor=user,
        )
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"diff-{eng.id[:8]}-{len(snaps)}snaps.pdf",
        )

    @bp.post("/<eng_id>/whatif")
    @_engagement_errors
    def whatif(eng_id: str):
        """W4.6: HTMX scenarios panel. POST form with overrides
        (shares_<name>=N, lp_mult_<name>=X). Returns the rendered
        partial template — htmx swaps it into the detail page."""
        user = g.current_user
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        # W5.5: compute-budget rate limit (separate from export budget).
        # Closes wave-4 audit m-6. Each /whatif costs one waterfall
        # recompute; abusive spam would burn CPU without tripping any
        # alert. Use the compute limiter if configured.
        # SD-AUD-M2: write a compute_burst_alert audit event at the hard
        # boundary so the chain records compute-side abuse the same way it
        # records bulk-export abuse.
        eng = _store().get_engagement(eng_id)
        compute_limiter: Optional[ExportRateLimiter] = current_app.config.get("COMPUTE_LIMITER")
        if compute_limiter is not None:
            rl = compute_limiter.consume(user.id)
            if rl.current_count == rl.hard_limit:
                from .engagement import AuditEventType
                _store()._append_audit_event(
                    engagement_id=eng.id,
                    event_type=AuditEventType.compute_burst_alert,
                    payload={
                        "user_id": user.id,
                        "count": rl.current_count,
                        "soft_limit": rl.soft_limit,
                        "hard_limit": rl.hard_limit,
                    },
                    actor=user,
                )
            if not rl.allowed:
                resp = jsonify({
                    "error": (
                        f"compute rate limit exceeded "
                        f"({rl.current_count}/{rl.soft_limit} per hour)"
                    ),
                    "error_code": "compute-rate-limit",
                    "current_count": rl.current_count,
                    "soft_limit": rl.soft_limit,
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(rl.retry_after_seconds)
                return resp
        if not eng.head_snapshot_id:
            return render_template(
                "engagement/_whatif.html",
                scenario=None, current_user=user,
            )
        snap = _store().get_snapshot(eng.head_snapshot_id)
        cap_table = snap.load_cap_table()
        if cap_table is None:
            return render_template(
                "engagement/_whatif.html",
                scenario=None, current_user=user,
            )
        from .waterfall import compute_waterfall
        baseline_wf = compute_waterfall(cap_table)

        # Apply overrides
        changed: list[str] = []
        new_classes = []
        for sc in cap_table.share_classes:
            upd: dict = {}
            new_shares = sc.shares_outstanding
            raw = (request.form.get(f"shares_{sc.name}") or "").replace(",", "").strip()
            if raw:
                try:
                    n = int(float(raw))
                    if n >= 0 and n != sc.shares_outstanding:
                        upd["shares_outstanding"] = n
                        new_shares = n
                        changed.append(
                            f"{sc.name} shares: {sc.shares_outstanding:,} → {n:,}"
                        )
                except ValueError:
                    pass
            if sc.type.value == "preferred" and sc.liquidation_preference is not None:
                old_lp = sc.liquidation_preference
                new_mult = old_lp.multiple
                mu_raw = (request.form.get(f"lp_mult_{sc.name}") or "").strip()
                if mu_raw:
                    try:
                        mu = float(mu_raw)
                        if mu > 0 and abs(mu - old_lp.multiple) > 1e-9:
                            new_mult = mu
                            changed.append(
                                f"{sc.name} LP mult: {old_lp.multiple}× → {mu}×"
                            )
                    except ValueError:
                        pass
                mult_ratio = new_mult / old_lp.multiple if old_lp.multiple else 1.0
                # BUG-010 fix logic, reused here.
                if sc.shares_outstanding == 0 and new_shares > 0:
                    price = sc.issue_price or 0.0
                    if price > 0:
                        new_amount = new_shares * price * new_mult
                    else:
                        new_amount = old_lp.amount * mult_ratio
                    upd["liquidation_preference"] = old_lp.model_copy(update={
                        "multiple": new_mult, "amount": new_amount,
                    })
                else:
                    shares_ratio = (
                        new_shares / sc.shares_outstanding
                        if sc.shares_outstanding else 1.0
                    )
                    if abs(shares_ratio * mult_ratio - 1.0) > 1e-9:
                        upd["liquidation_preference"] = old_lp.model_copy(update={
                            "multiple": new_mult,
                            "amount": old_lp.amount * shares_ratio * mult_ratio,
                        })
            new_classes.append(sc.model_copy(update=upd) if upd else sc)
        scenario_ct = cap_table.model_copy(update={"share_classes": new_classes})
        scenario_wf = compute_waterfall(scenario_ct)

        # Build paired rows for the template
        from .waterfall import Breakpoint as _BP
        baseline_by_event = {bp.event: bp.value for bp in baseline_wf.breakpoints}
        rows = []
        for bp in scenario_wf.breakpoints:
            baseline_val = baseline_by_event.get(bp.event)
            rows.append({
                "id": bp.id,
                "event": bp.event,
                "scenario_value": _format_money(bp.value, cap_table.company.currency_symbol),
                "baseline_value": (
                    _format_money(baseline_val, cap_table.company.currency_symbol)
                    if baseline_val is not None else "—"
                ),
            })
        return render_template(
            "engagement/_whatif.html",
            scenario={"rows": rows, "changed": changed},
            current_user=user,
        )

    @bp.get("/<eng_id>/bundle.zip")
    @_engagement_errors
    def bundle(eng_id: str):
        user = g.current_user
        if not can(user, "engagement.read"):
            return jsonify({
                "error": f"{user.role.value} cannot engagement.read",
                "error_code": "permission-denied",
            }), 403
        # M2 fix: shared helper so bundle + memo emit the same alert
        # behaviour and the alert fires exactly once at the boundary.
        # M7 fix: fetch eng first so the helper writes against a real id.
        eng = _store().get_engagement(eng_id)
        limit_response = _enforce_export_limit(eng, user)
        if limit_response is not None:
            return limit_response
        blob = build_engagement_bundle(_store(), eng_id)
        return send_file(
            BytesIO(blob),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"engagement-{eng_id[:8]}.zip",
        )

    return bp


def attach_engagement_blueprint(
    app: Flask,
    store: EngagementStore,
    identity_provider: Optional[IdentityProvider] = None,
    export_limiter: Optional[ExportRateLimiter] = None,
    compute_limiter: Optional[ExportRateLimiter] = None,
) -> None:
    """Attach the engagement blueprint to a Flask app.

    Caller supplies the EngagementStore, IdentityProvider (defaults to
    StubSSOProvider), and two optional rate limiters:
      - export_limiter: gates memo + bundle exports (per SPEC §8.17)
      - compute_limiter: gates /whatif (W5.5, separate budget so the
        what-if scratchpad doesn't burn the analyst's export budget
        and conversely export traffic doesn't lock them out of
        scenarios)

    All stored in app.config so the blueprint reads per-request.
    """
    app.config["ENGAGEMENT_STORE"] = store
    # SD-AUD-W8-M2: the wrapper helper is itself the documented dev-path
    # opt-in for the stub provider; the W8.2 guard exists for production
    # callers that construct StubSSOProvider directly. Helpers passing
    # `allow_in_prod=True` keeps the documented "defaults to a working
    # stub" contract intact for non-pytest consumers (SRE smoke harnesses,
    # vendored apps, etc.).
    app.config["IDENTITY_PROVIDER"] = (
        identity_provider or StubSSOProvider(allow_in_prod=True)
    )
    app.config["EXPORT_LIMITER"] = export_limiter
    app.config["COMPUTE_LIMITER"] = compute_limiter
    app.register_blueprint(build_engagement_blueprint())
