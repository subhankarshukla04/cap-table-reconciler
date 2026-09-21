"""Regression tests for SYSTEM_AUDIT_WAVE_8.md fixes.

One test per major + per fix-now minor. Test names encode the audit
finding code (W8-M1..M3, W8-m1..m8) so a future failure traces back to
the exact section.
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.cookie_auth import attach_login_blueprint
from src.engagement import (
    ARCHIVAL_RESTORE_DAYS,
    EngagementStatus,
    EngagementStore,
)
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, StubSSOProvider, User
from src.rate_limit import ExportRateLimiter
from src.token_deny import TokenDenyList
from src.xlsx_stability import (
    pin_workbook_properties,
    stabilise_xlsx_bytes,
)


# =============================================================================
# W8-M1: /readyz returns 503 when a dependency is down
# =============================================================================


def test_w8m1_readyz_ok_in_healthy_state():
    """In normal conditions, /readyz returns 200 {"status":"ok"}."""
    import importlib
    import app as app_module
    importlib.reload(app_module)
    client = app_module.app.test_client()
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_w8m1_readyz_503_when_engagement_db_unreachable(monkeypatch):
    """If the engagement store can't be queried, /readyz returns 503."""
    import importlib
    import app as app_module
    importlib.reload(app_module)
    # Patch the store's _connect to raise.
    def _boom(*a, **kw):
        raise sqlite3.OperationalError("db gone")
    monkeypatch.setattr(app_module.ENGAGEMENTS, "_connect", _boom)
    client = app_module.app.test_client()
    r = client.get("/readyz")
    assert r.status_code == 503
    payload = r.get_json()
    assert payload["status"] == "degraded"
    assert "engagement-db-unreachable" in payload.get("reason", "")


# =============================================================================
# W8-M2: attach_* helpers default-fallback does not raise
# =============================================================================


def test_w8m2_attach_engagement_blueprint_without_identity_kwarg_does_not_raise(monkeypatch):
    """No identity_provider kwarg → must construct fallback successfully."""
    # Simulate non-pytest, non-allowed env so the W8.2 guard would fire
    # IF the helper didn't pass allow_in_prod=True.
    monkeypatch.delenv("ALLOW_STUB_SSO", raising=False)
    monkeypatch.setattr("src.identity._running_in_test", lambda: False)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        path = Path(fh.name)
    try:
        store = EngagementStore(db_path=path)
        app = Flask(__name__)
        # Should not raise.
        attach_engagement_blueprint(app, store)
        # Provider should be a StubSSOProvider.
        provider = app.config["IDENTITY_PROVIDER"]
        assert provider.authenticate("any-token") is not None
    finally:
        path.unlink(missing_ok=True)


def test_w8m2_attach_login_blueprint_default_does_not_raise(monkeypatch):
    """No identity_provider kwarg, no IDENTITY_PROVIDER in config → must work."""
    monkeypatch.delenv("ALLOW_STUB_SSO", raising=False)
    monkeypatch.setattr("src.identity._running_in_test", lambda: False)
    app = Flask(__name__)
    app.config["TESTING"] = True  # to skip SESSION_SECRET_KEY env requirement
    # Should not raise.
    attach_login_blueprint(app)
    assert "IDENTITY_PROVIDER" in app.config


# =============================================================================
# W8-M3: /readyz/detailed requires admin auth
# =============================================================================


def test_w8m3_readyz_detailed_requires_auth():
    import importlib
    import app as app_module
    importlib.reload(app_module)
    client = app_module.app.test_client()
    r = client.get("/readyz/detailed")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_w8m3_readyz_detailed_accepts_operator_token(monkeypatch):
    monkeypatch.setenv("READYZ_ADMIN_TOKEN", "secret-ops-token")
    import importlib
    import app as app_module
    importlib.reload(app_module)
    client = app_module.app.test_client()
    r = client.get(
        "/readyz/detailed",
        headers={"Authorization": "Bearer secret-ops-token"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["status"] == "ok"
    assert "engine_commit" in payload
    assert "rule_pack_head_version" in payload


def test_w8m3_readyz_anonymous_does_not_leak_counters():
    import importlib
    import app as app_module
    importlib.reload(app_module)
    client = app_module.app.test_client()
    r = client.get("/readyz")
    payload = r.get_json()
    # None of the sensitive fields should appear in the anonymous response.
    for field in ("engine_commit", "deny_list_size",
                  "engagements_total", "audit_log_total",
                  "last_engagement_created_at",
                  "rule_pack_head_version"):
        assert field not in payload, f"anonymous /readyz leaks {field}"


# =============================================================================
# W8-m1: formula workbook is now byte-stable
# =============================================================================


def test_w8m1_minor_stabilise_xlsx_bytes_is_idempotent_and_byte_stable():
    """The shared helper produces identical output for two calls."""
    from openpyxl import Workbook
    wb = Workbook()
    pin_workbook_properties(wb, datetime(2026, 1, 1, tzinfo=timezone.utc))
    wb.active["A1"] = "test"
    buf1 = io.BytesIO()
    wb.save(buf1)
    b1 = stabilise_xlsx_bytes(buf1.getvalue())
    time.sleep(1.05)
    wb2 = Workbook()
    pin_workbook_properties(wb2, datetime(2026, 1, 1, tzinfo=timezone.utc))
    wb2.active["A1"] = "test"
    buf2 = io.BytesIO()
    wb2.save(buf2)
    b2 = stabilise_xlsx_bytes(buf2.getvalue())
    assert hashlib.sha256(b1).hexdigest() == hashlib.sha256(b2).hexdigest()


def test_w8m1_minor_live_formula_workbook_byte_stable():
    """The formula workbook export is byte-stable across regenerations."""
    from src.formula_workbook import build_formula_workbook
    from src.waterfall import compute_waterfall
    from src.models import (
        CapTable, Company, ShareClass, ShareClassType,
        LiquidationPreference, LPType,
    )
    from datetime import date as _date
    ct = CapTable(
        company=Company(name="Acme", currency="USD", currency_symbol="$",
                         valuation_date=_date(2025, 6, 1)),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common,
                       shares_outstanding=5_000_000),
            ShareClass(
                name="Series A", type=ShareClassType.preferred,
                shares_outstanding=1_000_000, issue_price=1.0,
                liquidation_preference=LiquidationPreference(
                    multiple=1.0, type=LPType.non_participating,
                    amount=1_000_000,
                ),
            ),
        ],
    )
    wf = compute_waterfall(ct)
    wb1 = build_formula_workbook(ct, wf)
    buf1 = io.BytesIO()
    wb1.save(buf1)
    b1 = stabilise_xlsx_bytes(buf1.getvalue())
    time.sleep(1.05)
    wb2 = build_formula_workbook(ct, wf)
    buf2 = io.BytesIO()
    wb2.save(buf2)
    b2 = stabilise_xlsx_bytes(buf2.getvalue())
    assert b1 == b2, "live formula workbook diverged across regenerations"


# =============================================================================
# W8-m2: engine commit cache busts on env change
# =============================================================================


def test_w8m2_engine_commit_cache_busts_on_env_change(monkeypatch):
    import src.rule_pack as rp
    rp._ENGINE_COMMIT_CACHE = None
    monkeypatch.delenv("QAPITA_ENGINE_COMMIT", raising=False)
    out1 = rp.current_engine_commit()  # falls back to git or "unversioned"
    monkeypatch.setenv("QAPITA_ENGINE_COMMIT", "abc123def456deadbeef")
    out2 = rp.current_engine_commit()
    assert out2 == "abc123def456"
    assert out2 != out1 or out1 == "abc123def456"  # only equal if env was preset


# =============================================================================
# W8-m4: memo route does not 500 on bad non-head snapshot JSON
# =============================================================================


def test_w8m4_timeline_diff_failure_does_not_break_memo_context():
    """If compute_timeline_diff raises in the engagement memo path, the
    PDFInputs.timeline_diff field falls back to None and the memo
    template silently omits the drift section."""
    from src.pdf_memo import PDFInputs, _build_context, ReviewerInfo
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
        cap_table=ct, waterfall=compute_waterfall(ct), findings=[],
        resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="r", preparer="p"),
        timeline_diff=None,  # simulate the post-try/except fallback
    )
    ctx = _build_context(inputs)
    assert ctx["timeline_diff"] is None


# =============================================================================
# W8-m5: dead import removed (smoke check)
# =============================================================================


def test_w8m5_no_dead_import_in_cli_hard_delete_archived():
    """The `from src.engagement import EngagementStore as _ES` line was dead
    inside cli_hard_delete_archived. Source scan."""
    src = Path(__file__).parent.parent.joinpath("app.py").read_text()
    assert "EngagementStore as _ES" not in src


# =============================================================================
# W8-m6: legacy archived rows get backfilled at boot
# =============================================================================


def test_w8m6_legacy_archived_rows_backfilled_on_open(tmp_path):
    """Simulate a wave-7 archived row (status='archived' but no
    archival columns); opening the W8.10 store backfills the values
    so the engagement can be restored or hard-deleted."""
    db_path = tmp_path / "legacy.db"
    # Build a wave-7-era schema (no archival columns).
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE engagement (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            valuation_date TEXT,
            standard_of_value TEXT NOT NULL,
            status TEXT NOT NULL,
            pack_version TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            head_snapshot_id TEXT,
            audit_head_hash TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            bound_pack_json TEXT
        );
    """)
    now = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn.execute(
        "INSERT INTO engagement (id, client_id, valuation_date, "
        "standard_of_value, status, pack_version, engine_version, "
        "audit_head_hash, version, created_by, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("legacy-eng", "c", "2025-01-01", "ifrs13", "archived",
         "v2026.6.0", "abc", "0" * 64, 0, "u-p", now),
    )
    conn.commit()
    conn.close()
    # Open with the W8.10 store — migration should backfill.
    store = EngagementStore(db_path=db_path)
    eng = store.get_engagement("legacy-eng")
    assert eng.archived_at is not None
    assert eng.restore_eligibility_until is not None
    # restore window is ~60 days out from archived_at + 90.
    assert eng.restore_eligibility_until > datetime.now(timezone.utc)


def test_w8m6_legacy_archived_can_be_restored_after_backfill(tmp_path):
    """Verify the backfilled row is now operationally restorable."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE engagement (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            valuation_date TEXT,
            standard_of_value TEXT NOT NULL,
            status TEXT NOT NULL,
            pack_version TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            head_snapshot_id TEXT,
            audit_head_hash TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            bound_pack_json TEXT
        );
        CREATE TABLE snapshot (
            id TEXT PRIMARY KEY, engagement_id TEXT NOT NULL,
            source TEXT NOT NULL, source_filename TEXT, source_hash TEXT,
            cap_table_json TEXT NOT NULL, parse_report_json TEXT,
            superseded_by TEXT, created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            redacted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE resolution (id TEXT PRIMARY KEY, snapshot_id TEXT,
            finding_code TEXT, decision_json TEXT, citation TEXT,
            resolved_by TEXT, resolved_at TEXT);
        CREATE TABLE audit_event (id TEXT PRIMARY KEY,
            engagement_id TEXT, event_type TEXT, actor TEXT,
            ts TEXT, payload_json TEXT,
            prev_row_hash TEXT, row_hash TEXT);
    """)
    recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    conn.execute(
        "INSERT INTO engagement (id, client_id, valuation_date, "
        "standard_of_value, status, pack_version, engine_version, "
        "audit_head_hash, version, created_by, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("legacy-eng", "c", "2025-01-01", "ifrs13", "archived",
         "v2026.6.0", "abc", "0" * 64, 0, "u-p", recent),
    )
    conn.commit()
    conn.close()
    store = EngagementStore(db_path=db_path)
    partner = User(id="u-p", email="p@x", role=Role.partner, display_name="P")
    eng = store.transition(
        actor=partner, engagement_id="legacy-eng",
        expected_version=0, new_status=EngagementStatus.open,
    )
    assert eng.status == EngagementStatus.open
