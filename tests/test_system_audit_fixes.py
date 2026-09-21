"""Regression tests for SYSTEM_AUDIT_COMPILED.md fix batch."""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from flask import Flask

from src.engagement import (
    BlockerFindingsOutstanding,
    EngagementStatus,
    EngagementStore,
    SnapshotSource,
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
from src.rule_pack import (
    load_engagement_bound_pack,
    load_pack_from_file,
)
from src.structured_diff import FieldDiff
from src.subsequent_events import _classify, compute_subsequent_events


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    s = EngagementStore(db_path=p)
    yield s
    p.unlink(missing_ok=True)


def _user(role=Role.analyst, uid="u-1"):
    return User(id=uid, email=f"{uid}@x", role=role, display_name=uid)


def _ct_with_blocker():
    """CapTable that produces an AD-MISSING blocker finding."""
    return CapTable(
        company=Company(name="X", currency="USD"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=1000),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=1000,
                issue_price=1.0, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=1000, type=LPType.non_participating),
                anti_dilution=None,  # → AD-MISSING blocker
            ),
        ],
    )


def _ct_clean():
    return CapTable(
        company=Company(name="X", currency="USD"),
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


# ---- B-1: engagement-bound pack at memo time --------------------------------


def test_b1_load_engagement_bound_pack_returns_specific_version():
    pack = load_engagement_bound_pack("v2026.1.0")
    assert pack.version == "v2026.1.0"
    assert len(pack.rule_ids) == 8  # baseline pack


def test_b1_load_engagement_bound_pack_raises_on_missing_pack():
    with pytest.raises(FileNotFoundError):
        load_engagement_bound_pack("v9999.0.0")


def test_b1_load_engagement_bound_pack_refuses_dev_in_production():
    # Make sure the env var is not set
    os.environ.pop("QAPITA_ALLOW_DEV_PACK", None)
    with pytest.raises(ValueError, match="QAPITA_ALLOW_DEV_PACK"):
        load_engagement_bound_pack("v0.0.0-dev")


# ---- B-2: bundle loads pack from absolute path -----------------------------


def test_b2_bundle_carries_rule_pack_when_cwd_not_repo_root(store, monkeypatch):
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    store.add_snapshot(
        actor=user, engagement_id=eng.id, expected_version=0,
        cap_table=_ct_clean(), source=SnapshotSource.excel_upload,
    )
    # Pretend we're running from /tmp (deployment cwd ≠ repo root)
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.chdir(td)
        blob = build_engagement_bundle(store, eng.id)
        with zipfile.ZipFile(BytesIO(blob)) as z:
            names = set(z.namelist())
    # B-2 fix: bundle must STILL contain rule_pack.json even when cwd is wrong.
    assert "rule_pack.json" in names


# ---- B-3: review → signed gates on unresolved blockers ---------------------


def test_b3_sign_with_unresolved_blocker_raises(store):
    analyst = _user(Role.analyst, "a")
    partner = _user(Role.partner, "p")
    reviewer = _user(Role.reviewer, "r")
    eng = store.create_engagement(
        actor=analyst, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    # Upload a cap table with an AD-MISSING blocker
    store.add_snapshot(
        actor=analyst, engagement_id=eng.id, expected_version=0,
        cap_table=_ct_with_blocker(), source=SnapshotSource.excel_upload,
    )
    eng = store.transition(
        actor=analyst, engagement_id=eng.id, expected_version=1,
        new_status=EngagementStatus.review,
    )
    # Reviewer trying to sign → must be refused with engagement-blockers-unresolved
    with pytest.raises(BlockerFindingsOutstanding) as exc:
        store.transition(
            actor=reviewer, engagement_id=eng.id, expected_version=eng.version,
            new_status=EngagementStatus.signed,
        )
    assert exc.value.error_code == "engagement-blockers-unresolved"
    assert exc.value.http_status == 409


def test_b3_sign_succeeds_after_blocker_resolved(store):
    analyst = _user(Role.analyst, "a")
    reviewer = _user(Role.reviewer, "r")
    eng = store.create_engagement(
        actor=analyst, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snap = store.add_snapshot(
        actor=analyst, engagement_id=eng.id, expected_version=0,
        cap_table=_ct_with_blocker(), source=SnapshotSource.excel_upload,
    )
    # Resolve the AD-MISSING blocker
    store.record_resolution(
        actor=analyst, snapshot_id=snap.id,
        finding_code="AD-MISSING-A",
        decision={"variant": "broad_based_weighted_average"},
        citation="Charter §4.3(a)",
    )
    eng = store.transition(
        actor=analyst, engagement_id=eng.id, expected_version=1,
        new_status=EngagementStatus.review,
    )
    # Now sign-off should succeed
    signed = store.transition(
        actor=reviewer, engagement_id=eng.id, expected_version=eng.version,
        new_status=EngagementStatus.signed,
    )
    assert signed.status == EngagementStatus.signed


def test_b3_sign_with_clean_cap_table_succeeds(store):
    analyst = _user(Role.analyst, "a")
    reviewer = _user(Role.reviewer, "r")
    eng = store.create_engagement(
        actor=analyst, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    store.add_snapshot(
        actor=analyst, engagement_id=eng.id, expected_version=0,
        cap_table=_ct_clean(), source=SnapshotSource.excel_upload,
    )
    eng = store.transition(
        actor=analyst, engagement_id=eng.id, expected_version=1,
        new_status=EngagementStatus.review,
    )
    signed = store.transition(
        actor=reviewer, engagement_id=eng.id, expected_version=eng.version,
        new_status=EngagementStatus.signed,
    )
    assert signed.status == EngagementStatus.signed


# ---- M-1: subsequent_events uses engagement.head_snapshot_id ---------------


def test_m1_subsequent_events_uses_head_snapshot_id(store):
    """The head must be the engagement's recorded head_snapshot_id,
    not list[-1]. Add multiple snapshots and verify."""
    user = _user()
    eng = store.create_engagement(
        actor=user, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    snaps = []
    for i in range(3):
        s = store.add_snapshot(
            actor=user, engagement_id=eng.id, expected_version=i,
            cap_table=_ct_clean(), source=SnapshotSource.manual_edit,
        )
        snaps.append(s.id)
    rollup = compute_subsequent_events(store, eng.id)
    # head must equal the last add_snapshot id (= engagement.head_snapshot_id)
    assert rollup.head_snapshot_id == snaps[-1]
    # original is the first snapshot in the chain
    assert rollup.original_snapshot_id == snaps[0]


# ---- M-2: rule pack effective_to closures ----------------------------------


def test_m2_prior_packs_have_effective_to_set():
    v1 = load_pack_from_file(Path("rule_packs/v2026.1.0.json"))
    v2 = load_pack_from_file(Path("rule_packs/v2026.2.0.json"))
    v3 = load_pack_from_file(Path("rule_packs/v2026.3.0.json"))
    v4 = load_pack_from_file(Path("rule_packs/v2026.4.0.json"))
    v5 = load_pack_from_file(Path("rule_packs/v2026.5.0.json"))
    v6 = load_pack_from_file(Path("rule_packs/v2026.6.0.json"))
    # All prior packs closed; head (v6 after W5.6) stays open.
    assert v1.effective_to is not None
    assert v2.effective_to is not None
    assert v3.effective_to is not None
    assert v4.effective_to is not None
    assert v5.effective_to is not None
    assert v6.effective_to is None  # head pack
    # No overlap on any single date
    assert v1.effective_to < v2.effective_from
    assert v2.effective_to < v3.effective_from
    assert v3.effective_to < v4.effective_from
    assert v4.effective_to < v5.effective_from
    assert v5.effective_to < v6.effective_from


def test_m2_is_effective_on_returns_single_pack_per_date():
    """For any past date, exactly one or zero packs claim it."""
    from src.rule_pack import list_available_packs
    packs = list_available_packs()
    # Per W4-AUDIT release-config fix, packs are renumbered so they
    # form a non-overlapping monthly chronology ending at today.
    for probe in (date(2026, 1, 15), date(2026, 2, 15),
                  date(2026, 3, 15), date(2026, 4, 15),
                  date(2026, 5, 25), date(2026, 6, 1)):
        active = [p for p in packs if p.is_effective_on(probe)]
        assert len(active) <= 1, (
            f"date {probe} matches {len(active)} packs: "
            f"{[p.version for p in active]}"
        )


# ---- M-3: error code rename ------------------------------------------------


def test_m3_illegal_transition_uses_spec_code(store):
    user = _user(Role.partner, "p")
    analyst = _user(Role.analyst, "a")
    eng = store.create_engagement(
        actor=analyst, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    # Try open → signed (not allowed)
    from src.engagement import IllegalStateTransition
    with pytest.raises(IllegalStateTransition) as exc:
        store.transition(
            actor=user, engagement_id=eng.id, expected_version=0,
            new_status=EngagementStatus.signed,
        )
    assert exc.value.error_code == "engagement-invalid-transition"


# ---- M-5: voting_differential classification -------------------------------


def test_m5_voting_differential_classified_correctly():
    diff = FieldDiff(
        path="share_classes[A].voting_differential",
        change_type="modified", old_value=None, new_value="10x",
        source_snapshot="snap",
    )
    assert _classify(diff) == "Voting / governance"


# ---- HTTP-level: B-3 returns 409 with the new code through the route ------


def test_b3_http_signoff_blocker_returns_409():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as eng_fh:
        eng_path = Path(eng_fh.name)
    store = EngagementStore(db_path=eng_path)
    app = Flask(__name__)
    app.config["TESTING"] = True
    users = {
        "tok-a": User(id="u-a", email="a@x", role=Role.analyst, display_name="A"),
        "tok-r": User(id="u-r", email="r@x", role=Role.reviewer, display_name="R"),
    }
    attach_engagement_blueprint(app, store, StaticUserProvider(users))
    client = app.test_client()
    try:
        eng_id = client.post(
            "/engagement/", headers={"Authorization": "Bearer tok-a"},
            json={"client_id": "c"},
        ).get_json()["id"]
        # Upload a blocker-producing cap table via Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Cap Table"
        ws.append(["Class Name", "Type", "Shares", "Issue Price", "Issue Date",
                   "LP Multiple", "LP Type", "Seniority", "Anti-Dilution"])
        ws.append(["Common", "common", 1_000_000, 0.01, "2020-01-01",
                   "", "", "", ""])
        ws.append(["Series A", "preferred", 1_000_000, 1.00, "2024-01-01",
                   1.0, "non_participating", 1, ""])  # blank AD
        buf = io.BytesIO()
        wb.save(buf)
        client.post(
            f"/engagement/{eng_id}/upload",
            headers={"Authorization": "Bearer tok-a"},
            data={"file": (io.BytesIO(buf.getvalue()), "demo.xlsx"),
                  "expected_version": "0"},
            content_type="multipart/form-data",
        )
        # Analyst → review
        client.post(
            f"/engagement/{eng_id}/transition",
            headers={"Authorization": "Bearer tok-a"},
            json={"new_status": "review", "expected_version": 1},
        )
        # Reviewer attempts to sign → 409 engagement-blockers-unresolved
        r = client.post(
            f"/engagement/{eng_id}/transition",
            headers={"Authorization": "Bearer tok-r"},
            json={"new_status": "signed", "expected_version": 2},
        )
        assert r.status_code == 409
        assert r.get_json()["error_code"] == "engagement-blockers-unresolved"
    finally:
        eng_path.unlink(missing_ok=True)
