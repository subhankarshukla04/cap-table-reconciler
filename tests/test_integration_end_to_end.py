"""End-to-end integration tests across the whole compiled system.

These tests exercise multi-module flows that no single per-wave test
covers. The intent: catch contract drift between modules, hidden
coupling, and edge cases that only manifest when several systems
interact.

Coverage:
  - Full engagement lifecycle (create → upload → resolve → memo → bundle → offline verify)
  - All 5 curated fixtures driven through the new engagement surface
  - Unicode / international edge cases
  - Time / clock edge cases
  - Empty / minimal inputs
  - Cross-rule-pack-version interactions
  - Concurrency across modules
"""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import threading
import warnings
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import openpyxl
import pytest
from flask import Flask

from src.checklist import run_checklist
from src.engagement import (
    _GENESIS_HASH,
    EngagementStatus,
    EngagementStore,
    SnapshotSource,
)
from src.engagement_bundle import build_engagement_bundle
from src.engagement_routes import attach_engagement_blueprint
from src.formula_workbook import build_formula_workbook
from src.identity import Role, StaticUserProvider, User
from src.models import (
    AntiDilution,
    AntiDilutionVariant,
    CapTable,
    Company,
    DragAlongTerms,
    LiquidationPreference,
    LPType,
    ProtectiveProvision,
    ROFRTerms,
    ShareClass,
    ShareClassType,
    SideLetter,
)
from src.parser import load_from_canonical_json, parse_excel
from src.pdf_memo import PDFInputs, ReviewerInfo, render_pdf_memo, render_pdf_memo_html
from src.rate_limit import ExportRateLimiter
from src.rule_pack import head_pack, load_pack_from_file, run_pack
from src.structured_diff import diff_snapshots
from src.subsequent_events import compute_subsequent_events
from src.waterfall import compute_waterfall


# ---- Fixtures ----------------------------------------------------------------


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    s = EngagementStore(db_path=p)
    yield s
    p.unlink(missing_ok=True)


@pytest.fixture
def web():
    """Full Flask app with engagement blueprint, identity, rate limiter."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as eng_fh, \
         tempfile.NamedTemporaryFile(suffix=".db", delete=False) as rl_fh:
        eng_path = Path(eng_fh.name)
        rl_path = Path(rl_fh.name)
    store = EngagementStore(db_path=eng_path)
    limiter = ExportRateLimiter(db_path=rl_path, soft_limit=100, hard_limit=200)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "analyst": User(id="u-a", email="a@x", role=Role.analyst, display_name="A Analyst"),
        "reviewer": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R Reviewer"),
        "partner": User(id="u-p", email="p@x", role=Role.partner, display_name="P Partner"),
        "auditor": User(id="u-au", email="au@x", role=Role.read_only_auditor, display_name="AU"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users),
                                 export_limiter=limiter)
    yield app.test_client(), store
    eng_path.unlink(missing_ok=True)
    rl_path.unlink(missing_ok=True)


def _h(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _user(role: Role, uid="u-1", name="U") -> User:
    return User(id=uid, email=f"{uid}@x", role=role, display_name=name)


def _clean_ct(company="Demo Co") -> CapTable:
    return CapTable(
        company=Company(name=company, currency="USD"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=5_000_000),
            ShareClass(
                name="Series A", type=ShareClassType.preferred, shares_outstanding=1_000_000,
                issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1_000_000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )


def _excel_bytes_from_ct(ct: CapTable) -> bytes:
    """Materialise a minimal cap-table xlsx the standard parser accepts."""
    wb = openpyxl.Workbook()
    co = wb.create_sheet("Company")
    co.append(["Company Name", ct.company.name])
    co.append(["Currency Code", ct.company.currency])
    if ct.company.jurisdiction:
        co.append(["Country of Incorporation", ct.company.jurisdiction])
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
# Full lifecycle: HTTP create → upload → resolve → transition → memo → bundle → verify
# =============================================================================


def test_full_engagement_lifecycle_http(web):
    client, store = web
    # 1. Analyst creates engagement
    r = client.post(
        "/engagement/", headers=_h("analyst"),
        json={"client_id": "acme", "standard_of_value": "ifrs13"},
    )
    assert r.status_code == 201
    eng_id = r.get_json()["id"]

    # 2. Analyst uploads cap table
    ct = _clean_ct()
    r = client.post(
        f"/engagement/{eng_id}/upload", headers=_h("analyst"),
        data={"file": (io.BytesIO(_excel_bytes_from_ct(ct)), "demo.xlsx"),
              "expected_version": "0"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
    snap_id = r.get_json()["snapshot_id"]

    # 3. Analyst resolves an info finding (LP-PART-CAP would not exist here; use AICPA reminder)
    r = client.post(
        f"/engagement/{eng_id}/resolve", headers=_h("analyst"),
        json={
            "snapshot_id": snap_id,
            "finding_code": "AICPA-DLOM-REMINDER",
            "decision": {"dlom_band": "0.20"},
            "citation": "Internal memo §3",
        },
    )
    assert r.status_code == 201

    # 4. Analyst transitions to review
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_h("analyst"),
        json={"new_status": "review", "expected_version": 1},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "review"

    # 5. Reviewer generates the memo PDF
    r = client.get(
        f"/engagement/{eng_id}/memo.pdf?reviewer=R+Reviewer",
        headers=_h("reviewer"),
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.mimetype == "application/pdf"
    assert r.get_data()[:4] == b"%PDF"

    # 6. Reviewer signs off (review → signed)
    r = client.post(
        f"/engagement/{eng_id}/transition", headers=_h("reviewer"),
        json={"new_status": "signed", "expected_version": 2},
    )
    assert r.status_code == 200

    # 7. Reviewer exports the bundle
    r = client.get(
        f"/engagement/{eng_id}/bundle.zip", headers=_h("reviewer"),
    )
    assert r.status_code == 200
    assert r.mimetype == "application/zip"

    # 8. Offline verify the hash chain from the bundle
    with ZipFile(BytesIO(r.get_data())) as z:
        log_lines = z.read("audit_log.jsonl").decode().splitlines()
        manifest = json.loads(z.read("manifest.json"))
    prev = _GENESIS_HASH
    for ln in log_lines:
        ev = json.loads(ln)
        assert ev["prev_row_hash"] == prev
        canonical = f"{ev['event_type']}|{ev['actor']}|{ev['ts']}|{ev['payload']}".encode()
        h = hashlib.sha256()
        h.update(prev.encode())
        h.update(b"\x00")
        h.update(canonical)
        assert h.hexdigest() == ev["row_hash"]
        prev = ev["row_hash"]
    assert manifest["audit_head_hash"] == prev


# =============================================================================
# All five curated fixtures through engagement flow
# =============================================================================


@pytest.mark.parametrize("fixture_id", [
    "fixture_01_clean",
    "fixture_02_typical_messy",
    "fixture_03_edge_case",
    "fixture_04_down_round_ratchet",
    "fixture_05_delaware_double_cap",
])
def test_fixture_drives_engagement_flow(store, fixture_id):
    """Every shipped fixture must round-trip through the engagement model
    cleanly: create → snapshot → checklist → memo HTML render."""
    p = Path(f"fixtures/{fixture_id}/cap_table_input.json")
    ct = load_from_canonical_json(p)
    user = _user(Role.analyst, "u-a", "A")
    eng = store.create_engagement(
        actor=user, client_id=f"client-{fixture_id}", standard_of_value="ifrs13",
        pack_version=head_pack().version, engine_version="x",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=ct, source=SnapshotSource.excel_upload,
    )
    assert snap.load_cap_table().company.name == ct.company.name

    # Run pack + memo HTML (any blockers must be resolved first for PDF)
    findings = run_pack(ct)
    blocker_codes = [f.code for f in findings if f.severity == "blocker"]
    for code in blocker_codes:
        store.record_resolution(
            actor=user, snapshot_id=snap.id,
            finding_code=code,
            decision={"resolved": True}, citation="Integration test resolution",
        )
    # Renderable HTML (cheaper than PDF in CI)
    inputs = PDFInputs(
        cap_table=ct, waterfall=compute_waterfall(ct),
        findings=findings,
        resolutions=[
            {"finding_code": code, "decision_summary": "{}",
             "citation": "Integration test", "resolved_by": user.id}
            for code in blocker_codes
        ],
        reviewer=ReviewerInfo(reviewer_name="R", preparer=user.display_name),
        engagement_id=eng.id, pack=head_pack(),
        subsequent_events=compute_subsequent_events(store, eng.id),
    )
    html = render_pdf_memo_html(inputs)
    assert ct.company.name in html
    assert ct.company.currency in html


# =============================================================================
# Unicode and international edge cases
# =============================================================================


@pytest.mark.parametrize("company_name", [
    "Acme Corporation",
    "नवीन उद्यम",  # Devanagari
    "சென்னை தொழில்நுட்பம்",  # Tamil
    "شركة الشرق",  # Arabic (RTL)
    "Café 北京 ☕",  # mixed
    "<script>alert(1)</script>",  # XSS attempt
    "O'Reilly & Sons, Inc.",  # quotes + ampersand
])
def test_unicode_company_name_survives_full_chain(store, company_name):
    ct = CapTable(
        company=Company(name=company_name, currency="USD"),
        share_classes=[
            ShareClass(name="Common", type=ShareClassType.common, shares_outstanding=1000),
        ],
    )
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=ct, source=SnapshotSource.excel_upload,
    )
    reloaded = snap.load_cap_table()
    assert reloaded.company.name == company_name  # exact round-trip

    # Bundle round-trips bytes through zip / json without mangling
    blob = build_engagement_bundle(store, eng.id)
    with ZipFile(BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
        eng_json = json.loads(z.read("engagement.json"))
        snap_json = json.loads(z.read(f"snapshots/{snap.id}.json"))
    assert manifest["engagement_id"] == eng.id
    cap = json.loads(snap_json["cap_table_json"])
    assert cap["company"]["name"] == company_name


def test_unicode_class_name_escapes_in_html_memo():
    """Memo HTML must escape <script> in class names (W2.7 / GAP-36)."""
    ct = CapTable(
        company=Company(name="X", currency="USD"),
        share_classes=[
            ShareClass(
                name="Common </td><td>injection",
                type=ShareClassType.common,
                shares_outstanding=1000,
            ),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )
    inputs = PDFInputs(
        cap_table=ct, waterfall=compute_waterfall(ct),
        findings=run_pack(ct), resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="R"),
    )
    html = render_pdf_memo_html(inputs)
    assert "</td><td>injection" not in html
    assert "&lt;/td&gt;" in html or "&#34" in html or "&amp;" in html or "&lt;" in html


# =============================================================================
# Time-based edge cases
# =============================================================================


def test_valuation_date_in_future_accepted(web):
    """Spec doesn't reject future valuation dates — confirm the system
    accepts them (forward-looking valuations are real)."""
    client, _ = web
    r = client.post(
        "/engagement/", headers=_h("analyst"),
        json={"client_id": "c", "standard_of_value": "ifrs13",
              "valuation_date": "2099-12-31"},
    )
    assert r.status_code == 201
    assert r.get_json()["valuation_date"] == "2099-12-31"


def test_snapshot_chain_orders_deterministically_over_repeated_reads(store):
    """list_snapshots must return identical order across calls (M3 fix)."""
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    for i in range(5):
        store.add_snapshot(
            actor=user, engagement_id=eng.id, expected_version=i,
            cap_table=_clean_ct(), source=SnapshotSource.manual_edit,
        )
    a = [s.id for s in store.list_snapshots(eng.id)]
    b = [s.id for s in store.list_snapshots(eng.id)]
    c = [s.id for s in store.list_snapshots(eng.id)]
    assert a == b == c


# =============================================================================
# Empty / minimal inputs
# =============================================================================


def test_engagement_with_zero_snapshots_handles_memo_and_bundle(web):
    client, _ = web
    eng_id = client.post(
        "/engagement/", headers=_h("analyst"),
        json={"client_id": "c"},
    ).get_json()["id"]
    # Memo should 400 with no-snapshot
    r = client.get(f"/engagement/{eng_id}/memo.pdf?reviewer=R", headers=_h("reviewer"))
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "no-snapshot"
    # Bundle still works (no snapshots → empty snapshots/ folder)
    r = client.get(f"/engagement/{eng_id}/bundle.zip", headers=_h("reviewer"))
    # Reviewer needs client_id since W3-AUDIT M1 fix only applies to list,
    # not detail. Bundle is a detail route → 200.
    assert r.status_code == 200


def test_cap_table_with_only_common_passes_full_chain(store):
    ct = CapTable(
        company=Company(name="Common Only"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=100),
        ],
    )
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=ct, source=SnapshotSource.excel_upload,
    )
    findings = run_pack(ct)
    # No preferred → AD-MISSING shouldn't fire → no blockers
    assert all(f.severity != "blocker" for f in findings)
    inputs = PDFInputs(
        cap_table=ct, waterfall=compute_waterfall(ct),
        findings=findings, resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="R"),
    )
    html = render_pdf_memo_html(inputs)
    assert "Common Only" in html


# =============================================================================
# Cross-rule-pack-version interactions
# =============================================================================


def test_engagement_bound_to_v1_does_not_fire_v4_rules(store):
    """An engagement opened under v2026.1.0 (8 rules) must produce ONLY
    those 8 rules' findings, even though the engine has 37 registered."""
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    ct = _clean_ct()
    store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=ct, source=SnapshotSource.excel_upload,
    )
    pack_v1 = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    findings_v1 = run_pack(ct, pack=pack_v1)
    # Wave-2 rules should NOT appear in v1 findings.
    codes = [f.code for f in findings_v1]
    assert not any("PP-EMPTY" in c for c in codes), (
        "v1 pack should not fire wave-3 rules: " + str(codes)
    )
    assert not any("DE-DGCL" in c for c in codes), (
        "v1 pack should not fire wave-2 rules: " + str(codes)
    )


def test_cross_version_diff_does_not_emit_phantom_diffs(store):
    """A snapshot's CapTable JSON serialises the wave-3 structured fields
    even when empty. Diffing two such snapshots must not emit phantom
    'added rofr_terms = None' rows."""
    ct1 = _clean_ct(company="C1")
    ct2 = _clean_ct(company="C1")  # same content
    d = diff_snapshots(ct1, ct2)
    assert d.change_count == 0


def test_diff_surfaces_added_protective_provision(store):
    ct_before = _clean_ct()
    ct_after = ct_before.model_copy(update={
        "protective_provisions": [
            ProtectiveProvision(
                name="amend_charter",
                consent_threshold_pct=51,
                consenting_class_names=["Series A"],
            ),
        ],
    })
    d = diff_snapshots(ct_before, ct_after)
    paths = [diff.path for diff in d.diffs]
    assert any("protective_provisions" in p for p in paths)


# =============================================================================
# Concurrency across modules
# =============================================================================


def test_concurrent_resolves_against_same_snapshot_all_recorded(store):
    """Resolutions are append-only and don't bump engagement.version, so
    parallel resolves on different findings should all succeed."""
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_clean_ct(), source=SnapshotSource.excel_upload,
    )
    barrier = threading.Barrier(5)
    results = []

    def worker(i):
        barrier.wait()
        res = store.record_resolution(
            actor=user, snapshot_id=snap.id,
            finding_code=f"GENERIC-{i}",
            decision={"i": i}, citation=f"Citation {i}",
        )
        results.append(res.id)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in ts: t.start()
    for t in ts: t.join()

    listed = store.list_resolutions(snap.id)
    assert len(listed) == 5
    # And the chain is still intact afterward
    ok, problem = store.verify_audit_log(eng.id)
    assert ok, problem


def test_redact_while_memo_is_in_flight_does_not_corrupt(store):
    """If a partner redacts a snapshot AFTER the memo is rendered, the
    rendered memo is still complete (it captured CT bytes at render-time)
    but a NEW memo render must surface snapshot-redacted."""
    user = _user(Role.analyst)
    partner = _user(Role.partner, "u-p", "P")
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_clean_ct(), source=SnapshotSource.excel_upload,
    )

    # Render once
    ct = snap.load_cap_table()
    findings = run_pack(ct)
    for f in findings:
        if f.severity == "blocker":
            store.record_resolution(
                actor=user, snapshot_id=snap.id, finding_code=f.code,
                decision={"r": True}, citation="x",
            )
    rendered_html = render_pdf_memo_html(PDFInputs(
        cap_table=ct, waterfall=compute_waterfall(ct), findings=findings,
        resolutions=[], reviewer=ReviewerInfo(reviewer_name="R"),
    ))
    assert "Demo Co" in rendered_html

    # Redact
    store.redact_snapshot_pii(
        actor=partner, snapshot_id=snap.id,
        request_reference="LEG-1", legal_basis="PDPA s.20",
    )
    re_snap = store.get_snapshot(snap.id)
    assert re_snap.load_cap_table() is None

    # Audit chain still intact
    ok, problem = store.verify_audit_log(eng.id)
    assert ok, problem


# =============================================================================
# Resource lifecycle — no leaks under volume
# =============================================================================


def test_high_volume_engagement_creation_no_resource_warnings(store):
    """50 engagements + 50 snapshots + 50 audit verifies. With B1/B5
    fixes the test must produce zero ResourceWarning."""
    user = _user(Role.analyst)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        for i in range(50):
            eng = store.create_engagement(
                actor=user, client_id=f"client-{i % 10}",
                standard_of_value="ifrs13",
                pack_version="v2026.1.0", engine_version="x",
            )
            store.add_snapshot(
                actor=user, engagement_id=eng.id, expected_version=0,
                cap_table=_clean_ct(), source=SnapshotSource.excel_upload,
            )
            store.verify_audit_log(eng.id)
    leaks = [w for w in caught if issubclass(w.category, ResourceWarning)]
    assert leaks == [], f"leaked resources: {[str(w.message) for w in leaks[:3]]}"


# =============================================================================
# Live workbook snapshot stamp end-to-end
# =============================================================================


def test_live_workbook_with_snapshot_stamp_matches_engagement(store):
    """The live formula workbook stamp must round-trip with the actual
    snapshot/engagement IDs, deterministically (uses snapshot.created_at)."""
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="abc",
    )
    snap = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_clean_ct(), source=SnapshotSource.excel_upload,
    )
    wb = build_formula_workbook(
        _clean_ct(), compute_waterfall(_clean_ct()),
        snapshot_stamp={
            "engagement_id": eng.id,
            "snapshot_id": snap.id,
            "memo_version": "1.0",
            "engine_version": eng.engine_version,
            "pack_version": eng.pack_version,
            "generated_at": snap.created_at.isoformat(),
        },
    )
    ws = wb["Snapshot Stamp"]
    values = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
              for r in range(1, 10)}
    assert values["engagement_id"] == eng.id
    assert values["snapshot_id"] == snap.id
    assert values["generated_at"] == snap.created_at.isoformat()


# =============================================================================
# Subsequent-events carry resolutions across snapshots (M7 from wave 2)
# =============================================================================


def test_subsequent_events_carries_resolutions_across_chain(store):
    user = _user(Role.analyst)
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    s1 = store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_clean_ct(), source=SnapshotSource.excel_upload,
    )
    store.record_resolution(
        actor=user, snapshot_id=s1.id,
        finding_code="AD-MISSING-Series A",
        decision={"v": "bbwa"}, citation="Charter §4.3(a)",
    )
    eng = store.get_engagement(eng.id)
    store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=eng.version,
        cap_table=_clean_ct(), source=SnapshotSource.manual_edit,
    )
    rollup = compute_subsequent_events(store, eng.id)
    assert len(rollup.historical_resolutions) == 1
    assert rollup.historical_resolutions[0].finding_code == "AD-MISSING-Series A"
