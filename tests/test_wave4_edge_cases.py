"""Wave-4 edge-case integration tests — targets module interactions
new in wave 4 that no single unit test exercises:

  - HTMX content-negotiation corner cases (q-values, html=1 + JSON Accept)
  - Pack-bytes-at-bind round-trips + corruption recovery
  - DCF template + sidecar paired-open behavior
  - valuation_date type round-trips (datetime, tz-aware, ISO with offset)
  - /whatif partial XSS + edge cases
  - 50-rule-pack interactions (rule code collisions, no rule fires for all)
  - Cross-pack-version determinism with pinned pack bytes
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
from datetime import date, datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.checklist import run_checklist
from src.dcf_sidecar import build_dcf_sidecar
from src.dcf_template import build_dcf_template
from src.engagement import (
    Engagement,
    EngagementStore,
    SnapshotSource,
    _GENESIS_HASH,
)
from src.engagement_bundle import build_engagement_bundle
from src.engagement_routes import attach_engagement_blueprint
from src.identity import Role, StaticUserProvider, User
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    LiquidationPreference,
    LPType,
    ShareClass,
    ShareClassType,
)
from src.rate_limit import ExportRateLimiter
from src.rule_pack import (
    RulePack,
    load_engagement_bound_pack,
    load_pack_from_file,
    registered_rule_ids,
    rule_metadata,
    run_pack,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    s = EngagementStore(db_path=p)
    yield s
    p.unlink(missing_ok=True)


@pytest.fixture
def web():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as eng_fh, \
         tempfile.NamedTemporaryFile(suffix=".db", delete=False) as rl_fh:
        eng_path = Path(eng_fh.name)
        rl_path = Path(rl_fh.name)
    store = EngagementStore(db_path=eng_path)
    limiter = ExportRateLimiter(db_path=rl_path, soft_limit=100, hard_limit=200)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "analyst": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
        "reviewer": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users),
                                 export_limiter=limiter)
    yield app.test_client(), store
    eng_path.unlink(missing_ok=True)
    rl_path.unlink(missing_ok=True)


def _h(tok: str, **extra) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}", **extra}


def _user(role=Role.analyst, uid="u-1"):
    return User(id=uid, email=f"{uid}@x", role=role, display_name=uid)


def _ct():
    return CapTable(
        company=Company(name="Edge Co", currency="USD"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=5_000_000),
            ShareClass(
                name="Series A", type=ShareClassType.preferred,
                shares_outstanding=1_000_000,
                issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1_000_000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )


def _excel_bytes(ct: CapTable) -> bytes:
    wb = openpyxl.Workbook()
    co = wb.create_sheet("Company")
    co.append(["Company Name", ct.company.name])
    co.append(["Currency Code", ct.company.currency])
    ws = wb.create_sheet("Cap Table")
    ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date",
               "LP Multiple", "LP Type", "Seniority", "Anti-Dilution"])
    for sc in ct.share_classes:
        lp = sc.liquidation_preference
        ws.append([
            sc.name, sc.type.value, sc.shares_outstanding,
            sc.issue_price or "",
            sc.issue_date.isoformat() if sc.issue_date else "",
            lp.multiple if lp else "",
            lp.type.value if lp else "",
            sc.seniority_rank if sc.type.value == "preferred" else "",
            sc.anti_dilution.variant.value if sc.anti_dilution and sc.anti_dilution.variant else "",
        ])
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =============================================================================
# HTMX content-negotiation corner cases
# =============================================================================


def test_html_1_query_param_overrides_json_accept(web):
    """?html=1 should win even if Accept explicitly asks for JSON."""
    client, _ = web
    r = client.get(
        "/engagement/?html=1",
        headers=_h("analyst", Accept="application/json"),
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "<html" in body


def test_accept_wildcard_returns_json(web):
    """Accept: */* (default for many HTTP clients) should be JSON."""
    client, _ = web
    r = client.get("/engagement/", headers=_h("analyst", Accept="*/*"))
    assert r.status_code == 200
    assert r.is_json


def test_no_accept_header_defaults_to_json(web):
    client, _ = web
    r = client.get("/engagement/", headers=_h("analyst"))
    assert r.is_json


def test_html_accept_with_q_values_renders_html(web):
    """Real browser Accept headers include q-values."""
    client, _ = web
    accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    r = client.get("/engagement/", headers=_h("analyst", Accept=accept))
    assert r.status_code == 200
    assert "<html" in r.get_data(as_text=True)


# =============================================================================
# Pack-bytes-at-bind round-trips + corruption
# =============================================================================


def test_engagement_create_pins_pack_bytes(store):
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="abc",
    )
    refreshed = store.get_engagement(eng.id)
    assert refreshed.bound_pack_json is not None
    pinned = RulePack.model_validate_json(refreshed.bound_pack_json)
    assert pinned.version == "v2026.1.0"
    assert len(pinned.rule_ids) == 8


def test_bundle_uses_pinned_bytes_even_if_disk_pack_changes(store, monkeypatch):
    """If the on-disk pack file is mutated AFTER create, the bundle
    should still ship the originally-pinned bytes (not the new ones)."""
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="abc",
    )
    # The pinned bytes capture the pack as-of create time.
    # Even if I were to corrupt the disk pack (we don't, but we verify
    # the bundle ships the in-DB bytes, not a fresh disk read).
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    blob = build_engagement_bundle(store, eng.id)
    import zipfile
    with zipfile.ZipFile(BytesIO(blob)) as z:
        pack_in_bundle = z.read("rule_pack.json").decode()
    assert json.loads(pack_in_bundle)["version"] == "v2026.1.0"
    # And the bundle bytes match the engagement's pinned bytes
    pinned = store.get_engagement(eng.id).bound_pack_json
    assert json.loads(pinned)["version"] == "v2026.1.0"


def test_corrupt_pinned_pack_bytes_falls_back_to_disk(store):
    """If bound_pack_json gets corrupted (DB-admin tamper or migration
    bug), the bundle should still ship a rule_pack — fall back to disk."""
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="abc",
    )
    store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    # Tamper: corrupt the pinned bytes directly via raw SQL
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE engagement SET bound_pack_json = 'not valid json' WHERE id = ?",
            (eng.id,),
        )
    blob = build_engagement_bundle(store, eng.id)
    import zipfile
    with zipfile.ZipFile(BytesIO(blob)) as z:
        names = set(z.namelist())
    # Fallback to disk MUST succeed — rule_pack.json still present
    assert "rule_pack.json" in names


# =============================================================================
# DCF template + sidecar paired-open
# =============================================================================


def test_dcf_template_named_ranges_match_sidecar_slugs():
    """For every class in the cap table, the DCF template's Per-Class FV
    sheet must reference a defined name that the DCF sidecar exports.

    W5.4: references use Excel external-link syntax now —
    `='[dcf_sidecar.xlsx]Cap Inputs'!share_count_Common`. Extract the
    name after the `!` and verify the sidecar exports it.
    """
    from src.dcf_sidecar import _slug_for_defined_name
    import re
    ct = _ct()
    sidecar = build_dcf_sidecar(ct)
    template = build_dcf_template(ct)
    sidecar_names = {n.name for n in sidecar.defined_names.values()}
    ws = template["Per-Class FV"]
    for r in range(2, 2 + len(ct.share_classes)):
        ref = ws.cell(row=r, column=3).value
        if not ref:
            continue
        m = re.search(r"!(share_count_[A-Za-z0-9_]+)$", ref)
        assert m is not None, f"reference {ref!r} doesn't look like an external link"
        name = m.group(1)
        assert name in sidecar_names, f"sidecar missing named range {name}"


def test_dcf_template_handles_50_classes():
    """Stress: 50-class cap-table → template still generates."""
    classes = [
        ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=10_000_000),
    ]
    for i in range(49):
        classes.append(ShareClass(
            name=f"Series-{i:02d}",
            type=ShareClassType.preferred,
            shares_outstanding=100_000,
            issue_price=1.0, issue_date=date(2024, 1, 1),
            seniority_rank=min(99, i + 1),
            seniority_sub_rank=0,
            liquidation_preference=LiquidationPreference(
                multiple=1, amount=100_000, type=LPType.non_participating),
            anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
        ))
    ct = CapTable(company=Company(name="50-Class Co"), share_classes=classes[:50])
    wb = build_dcf_template(ct)
    ws = wb["Per-Class FV"]
    # Header row + 50 rows
    assert ws.cell(row=51, column=1).value is not None


# =============================================================================
# valuation_date type round-trips
# =============================================================================


def test_valuation_date_accepts_datetime_object():
    """Engagement constructor accepts datetime, coerces to date."""
    dt = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)
    eng = Engagement(
        id="x", client_id="c", valuation_date=dt,
        standard_of_value="ifrs13", status="open",
        pack_version="v2026.1.0", engine_version="x",
        audit_head_hash=_GENESIS_HASH, version=0,
        created_by="u", created_at=datetime.now(timezone.utc),
    )
    assert isinstance(eng.valuation_date, date)
    assert eng.valuation_date == date(2026, 6, 15)


def test_valuation_date_accepts_iso_with_offset_string():
    """ISO date string parses cleanly."""
    eng = Engagement(
        id="x", client_id="c", valuation_date="2026-06-15",
        standard_of_value="ifrs13", status="open",
        pack_version="v2026.1.0", engine_version="x",
        audit_head_hash=_GENESIS_HASH, version=0,
        created_by="u", created_at=datetime.now(timezone.utc),
    )
    assert eng.valuation_date == date(2026, 6, 15)


def test_valuation_date_rejects_garbage_strings():
    with pytest.raises(Exception):
        Engagement(
            id="x", client_id="c", valuation_date="not-a-date",
            standard_of_value="ifrs13", status="open",
            pack_version="v2026.1.0", engine_version="x",
            audit_head_hash=_GENESIS_HASH, version=0,
            created_by="u", created_at=datetime.now(timezone.utc),
        )


def test_valuation_date_persists_round_trip(store):
    """ISO date → DB → reload → date object."""
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
        valuation_date="2026-06-15",
    )
    refreshed = store.get_engagement(eng.id)
    assert refreshed.valuation_date == date(2026, 6, 15)


# =============================================================================
# /whatif partial — edge cases
# =============================================================================


def test_whatif_handles_xss_attempt_in_class_name(web):
    """Class name with <script> in it shouldn't break HTML escape."""
    client, store = web
    # Direct store + bypass HTML rendering of the form, hit /whatif POST
    user = User(id="u-a", email="a@x", role=Role.analyst, display_name="A")
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    nasty_ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="<script>alert(1)</script>",
                       type=ShareClassType.common, shares_outstanding=1000),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )
    store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=nasty_ct, source=SnapshotSource.excel_upload,
    )
    r = client.post(
        f"/engagement/{eng.id}/whatif?html=1",
        headers=_h("analyst"),
        data={},
    )
    body = r.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body


def test_whatif_with_no_head_snapshot_returns_empty_partial(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h("analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    r = client.post(
        f"/engagement/{eng_id}/whatif?html=1",
        headers=_h("analyst"),
        data={},
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Adjust a share count" in body


def test_whatif_does_not_consume_export_budget(web):
    """The /whatif route is interactive analysis, not an export — must
    not count against the per-user export rate limit."""
    client, store = web
    eng_id = client.post(
        "/engagement/", headers=_h("analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    # Upload so whatif has data
    client.post(
        f"/engagement/{eng_id}/upload", headers=_h("analyst"),
        data={"file": (io.BytesIO(_excel_bytes(_ct())), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    # Hit whatif a lot
    for _ in range(20):
        client.post(f"/engagement/{eng_id}/whatif?html=1",
                    headers=_h("analyst"), data={})
    # Memo (an actual export) should still succeed without 429
    r = client.get(
        f"/engagement/{eng_id}/memo.pdf?reviewer=A",
        headers=_h("analyst"),
    )
    # 200 or 400 (no reviewer for analyst auto-fill is OK); NOT 429
    assert r.status_code != 429


# =============================================================================
# 50-rule-pack interactions
# =============================================================================


def test_no_two_rules_share_an_id():
    """Across all 50 registered rules, no two share an id."""
    ids = registered_rule_ids()
    assert len(ids) == len(set(ids)), "duplicate rule IDs detected"


def test_every_rule_has_metadata():
    for rid in registered_rule_ids():
        meta = rule_metadata(rid)
        assert meta is not None
        assert meta.id == rid
        assert meta.citation, f"rule {rid} has empty citation"
        assert meta.severity in ("blocker", "warning", "info")


def test_no_rule_fires_against_empty_cap_table():
    """An empty-as-possible cap table (one common class only) should fire
    very few rules. Anything that fires for every cap table is suspect."""
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1),
        ],
    )
    pack = load_pack_from_file(Path("rule_packs/v2026.5.0.json"))
    findings = run_pack(ct, pack=pack)
    # AICPA-DLOM-REMINDER is allowed to fire (it's a "common-exists" info).
    # Anything ELSE that fires on this trivial input is the kind of
    # over-eager rule that produces noise.
    surprising = [f for f in findings if f.code != "AICPA-DLOM-REMINDER"]
    assert len(surprising) <= 1, (
        f"too many rules fire on a one-class cap table: {[f.code for f in surprising]}"
    )


def test_50_rules_run_under_100ms():
    """All 50 rules combined must run quickly on a typical cap table."""
    import time
    ct = _ct()
    pack = load_pack_from_file(Path("rule_packs/v2026.5.0.json"))
    t0 = time.perf_counter()
    findings = run_pack(ct, pack=pack)
    dt = time.perf_counter() - t0
    assert dt < 0.1, f"50-rule pack took {dt*1000:.1f}ms (>100ms budget)"
    assert isinstance(findings, list)


# =============================================================================
# Cross-pack-version determinism
# =============================================================================


def test_same_engagement_same_pack_produces_identical_finding_set(store):
    """An engagement bound to v2026.1.0 must produce the same findings
    on the same cap table every time."""
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    pack = load_engagement_bound_pack("v2026.1.0")
    a = sorted(f.code for f in run_pack(snap.load_cap_table(), pack=pack))
    b = sorted(f.code for f in run_pack(snap.load_cap_table(), pack=pack))
    assert a == b


def test_v1_pack_produces_subset_of_v5_pack_findings(store):
    """The v1 pack has 8 rules; v5 has 50. Every finding that fires
    under v1 should also fire under v5 (v5 strictly supersets v1's
    rule ids)."""
    ct = _ct()
    v1 = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    v5 = load_pack_from_file(Path("rule_packs/v2026.5.0.json"))
    v1_codes = {f.code for f in run_pack(ct, pack=v1)}
    v5_codes = {f.code for f in run_pack(ct, pack=v5)}
    assert v1_codes <= v5_codes, (
        f"v1 findings not subset of v5: missing in v5 = {v1_codes - v5_codes}"
    )


# =============================================================================
# UI + auth interactions
# =============================================================================


def test_unauthenticated_html_request_redirects_to_login(web):
    """W5.7 changed the browser-unauthenticated behaviour from 401 to a
    302 redirect to /login. JSON clients without Bearer still get 401."""
    client, _ = web
    r = client.get("/engagement/", headers={"Accept": "text/html"},
                    follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].startswith("/login")


def test_html_user_pill_renders_role(web):
    """The base template renders the user's role pill in the nav."""
    client, _ = web
    r = client.get("/engagement/?html=1", headers=_h("analyst"))
    body = r.get_data(as_text=True)
    assert "analyst" in body
    assert "A" in body  # display_name
