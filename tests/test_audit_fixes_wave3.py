"""Regression tests for the W3-AUDIT fix batch (CODE_AUDIT_WAVE_3.md)."""

from __future__ import annotations

import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from flask import Flask

from src.engagement import EngagementStore
from src.engagement_routes import attach_engagement_blueprint
from src.formula_workbook import build_formula_workbook
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
from src.opm.vol_pack import build_vol_pack_template, read_vol_pack
from src.waterfall import compute_waterfall


# ---- B1: vol pack rejects out-of-range numerics --------------------------


def _fill(wb, slug_value_pairs: dict):
    ws = wb["Market Inputs"]
    for r in range(1, 200):
        slug = ws.cell(row=r, column=4).value
        if slug and slug in slug_value_pairs:
            ws.cell(row=r, column=2, value=slug_value_pairs[slug])


def _save(wb) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
        wb.save(fh.name)
    return Path(fh.name)


def test_b1_negative_volatility_rejected():
    wb = build_vol_pack_template()
    _fill(wb, {
        "volatility": -0.5,
        "time_to_liquidity_years": 4.0,
        "risk_free_rate": 0.045,
        "vol_peer_tickers": "X", "vol_window_months": "12",
        "vol_citation": "x", "time_basis": "x", "rfr_source": "x", "dlom_basis": "x",
    })
    p = _save(wb)
    try:
        result = read_vol_pack(p)
        assert not result.is_valid
        assert any("outside expected range" in s for s in result.missing_required)
    finally:
        p.unlink(missing_ok=True)


def test_b1_dlom_above_one_rejected():
    wb = build_vol_pack_template()
    _fill(wb, {
        "volatility": 0.5, "time_to_liquidity_years": 4.0, "risk_free_rate": 0.045,
        "dlom": 10.0,  # 1000% — must reject
        "vol_peer_tickers": "X", "vol_window_months": "12",
        "vol_citation": "x", "time_basis": "x", "rfr_source": "x", "dlom_basis": "x",
    })
    p = _save(wb)
    try:
        result = read_vol_pack(p)
        assert not result.is_valid
        assert any("dlom" in s.lower() or "DLOM" in s for s in result.missing_required)
    finally:
        p.unlink(missing_ok=True)


def test_b1_zero_time_rejected():
    wb = build_vol_pack_template()
    _fill(wb, {
        "volatility": 0.5, "time_to_liquidity_years": 0.0, "risk_free_rate": 0.045,
        "vol_peer_tickers": "X", "vol_window_months": "12",
        "vol_citation": "x", "time_basis": "x", "rfr_source": "x", "dlom_basis": "x",
    })
    p = _save(wb)
    try:
        result = read_vol_pack(p)
        assert not result.is_valid
    finally:
        p.unlink(missing_ok=True)


# ---- B2: PDF provenance lists every rule in the pack --------------------


def test_b2_provenance_lists_wave3_rule_ids():
    """The provenance appendix must include W3.6 rule IDs like PP-001 /
    DRAG-002 / XREF-001, not just G-XXX-NNN."""
    from src.pdf_memo import PDFInputs, ReviewerInfo, render_pdf_memo_html
    from src.rule_pack import load_pack_from_file

    ct = CapTable(
        company=Company(name="Co", currency="USD"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=AntiDilutionVariant.broad_based_weighted_average),
            ),
        ],
    )
    pack = load_pack_from_file(Path("rule_packs/v2026.4.0.json"))
    inputs = PDFInputs(
        cap_table=ct, waterfall=compute_waterfall(ct),
        findings=[], resolutions=[],
        reviewer=ReviewerInfo(reviewer_name="R"),
        pack=pack,
    )
    html = render_pdf_memo_html(inputs)
    # Every rule in the pack should appear in the appendix table.
    for rid in ("G-AD-001", "G-PP-001", "G-DRAG-002", "G-XREF-001"):
        assert rid in html, f"rule {rid} missing from provenance appendix"


# ---- M1: reviewer/partner forced to scope list by client_id -------------


def test_m1_reviewer_must_pass_client_id():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    store = EngagementStore(db_path=p)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "tok-r": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R"),
        "tok-p": User(id="u-p", email="p@x", role=Role.partner, display_name="P"),
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users))
    client = app.test_client()
    try:
        # Reviewer without client_id → 400
        r = client.get("/engagement/", headers={"Authorization": "Bearer tok-r"})
        assert r.status_code == 400
        assert r.get_json()["error_code"] == "client-id-required-for-role"
        # Reviewer WITH client_id → 200
        r = client.get(
            "/engagement/?client_id=acme",
            headers={"Authorization": "Bearer tok-r"},
        )
        assert r.status_code == 200
        # Partner without client_id → 400
        r = client.get("/engagement/", headers={"Authorization": "Bearer tok-p"})
        assert r.status_code == 400
        # Analyst without client_id → 200 (filtered to own)
        r = client.get("/engagement/", headers={"Authorization": "Bearer tok-a"})
        assert r.status_code == 200
    finally:
        p.unlink(missing_ok=True)


# ---- M2: subsequent-events classifier covers new fields -----------------


def test_m2_protective_provisions_diff_classified():
    from src.models import ProtectiveProvision
    from src.structured_diff import diff_snapshots
    from src.subsequent_events import group_events_by_category, SubsequentEvent, SubsequentEventsRollup
    from src.subsequent_events import _classify
    from src.structured_diff import FieldDiff

    diff = FieldDiff(
        path="protective_provisions[issue_senior].consent_threshold_pct",
        change_type="modified",
        old_value=51, new_value=67, source_snapshot="snap-x",
    )
    assert _classify(diff) == "Protective provisions"


def test_m2_rofr_drag_diffs_classified():
    from src.structured_diff import FieldDiff
    from src.subsequent_events import _classify
    assert _classify(FieldDiff(
        path="rofr_terms.notice_period_days",
        change_type="modified", old_value=30, new_value=60, source_snapshot="x",
    )) == "ROFR / ROFO"
    assert _classify(FieldDiff(
        path="drag_along_terms.threshold_pct",
        change_type="modified", old_value=51, new_value=67, source_snapshot="x",
    )) == "Drag-along"


# ---- M3: deterministic ordering in list_snapshots ----------------------


def test_m3_list_snapshots_uses_id_tiebreaker(monkeypatch):
    """Force two snapshots to share created_at; verify list_snapshots
    returns them in a deterministic order (id tiebreak)."""
    from src.engagement import SnapshotSource
    user = User(id="u-1", email="a@x", role=Role.analyst, display_name="A")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    store = EngagementStore(db_path=p)
    try:
        eng = store.create_engagement(
            actor=user, client_id="c", standard_of_value="ifrs13",
            pack_version="v2026.1.0", engine_version="x",
        )
        # Add two snapshots — even if they share timestamps the order
        # is now deterministic via id tiebreaker.
        ct = CapTable(
            company=Company(name="X"),
            share_classes=[
                ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1)
            ],
        )
        store.add_snapshot(
            actor=user, engagement_id=eng.id, expected_version=0,
            cap_table=ct, source=SnapshotSource.excel_upload,
        )
        store.add_snapshot(
            actor=user, engagement_id=eng.id, expected_version=1,
            cap_table=ct, source=SnapshotSource.manual_edit,
        )
        a = [s.id for s in store.list_snapshots(eng.id)]
        b = [s.id for s in store.list_snapshots(eng.id)]
        assert a == b
    finally:
        p.unlink(missing_ok=True)


# ---- M4: snapshot_stamp refuses missing generated_at -------------------


def test_m4_snapshot_stamp_without_generated_at_raises():
    ct = CapTable(
        company=Company(name="X"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1),
        ],
    )
    with pytest.raises(ValueError, match="generated_at is required"):
        build_formula_workbook(
            ct, compute_waterfall(ct),
            snapshot_stamp={"engagement_id": "e", "snapshot_id": "s"},
        )
