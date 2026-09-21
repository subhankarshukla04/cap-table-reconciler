"""Subsequent-events tests (W3.1 / closes audit M7)."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.engagement import EngagementStore, SnapshotSource
from src.identity import Role, User
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
from src.subsequent_events import (
    compute_subsequent_events,
    group_events_by_category,
)


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    s = EngagementStore(db_path=p)
    yield s
    p.unlink(missing_ok=True)


def _analyst():
    return User(id="u-a", email="a@x", role=Role.analyst, display_name="A")


def _ct(shares=1000, price=1.0, ad=AntiDilutionVariant.broad_based_weighted_average):
    return CapTable(
        company=Company(name="Co", currency="USD"),
        share_classes=[
            ShareClass(name="C", type=ShareClassType.common, shares_outstanding=2000),
            ShareClass(
                name="A", type=ShareClassType.preferred, shares_outstanding=shares,
                issue_price=price, issue_date=date(2024, 1, 1), seniority_rank=1,
                liquidation_preference=LiquidationPreference(
                    multiple=1, amount=shares * price, type=LPType.non_participating),
                anti_dilution=AntiDilution(variant=ad),
            ),
        ],
    )


def _eng(store):
    return store.create_engagement(
        actor=_analyst(), client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )


def test_empty_engagement_returns_empty_rollup(store):
    eng = _eng(store)
    rollup = compute_subsequent_events(store, eng.id)
    assert rollup.original_snapshot_id is None
    assert rollup.head_snapshot_id is None
    assert not rollup.has_changes


def test_single_snapshot_no_events(store):
    eng = _eng(store)
    store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=0,
        cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    rollup = compute_subsequent_events(store, eng.id)
    assert rollup.original_snapshot_id == rollup.head_snapshot_id
    assert rollup.events == []
    assert not rollup.has_changes


def test_shares_increase_produces_event(store):
    eng = _eng(store)
    store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=0,
        cap_table=_ct(shares=1000), source=SnapshotSource.excel_upload,
    )
    eng = store.get_engagement(eng.id)
    store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=eng.version,
        cap_table=_ct(shares=1500), source=SnapshotSource.manual_edit,
    )
    rollup = compute_subsequent_events(store, eng.id)
    assert rollup.has_changes
    by_cat = group_events_by_category(rollup)
    assert "Share count" in by_cat


def test_resolutions_carry_across_snapshots(store):  # closes audit M7
    eng = _eng(store)
    s1 = store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=0,
        cap_table=_ct(), source=SnapshotSource.excel_upload,
    )
    store.record_resolution(
        actor=_analyst(), snapshot_id=s1.id,
        finding_code="AD-MISSING-A",
        decision={"variant": "broad_based_weighted_average"},
        citation="Charter §4.3(a)",
    )
    eng = store.get_engagement(eng.id)
    store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=eng.version,
        cap_table=_ct(shares=1500), source=SnapshotSource.manual_edit,
    )
    rollup = compute_subsequent_events(store, eng.id)
    assert len(rollup.historical_resolutions) == 1
    assert rollup.historical_resolutions[0].finding_code == "AD-MISSING-A"


def test_lp_change_classified_correctly(store):
    eng = _eng(store)
    store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=0,
        cap_table=_ct(shares=1000, price=1.0),
        source=SnapshotSource.excel_upload,
    )
    eng = store.get_engagement(eng.id)
    store.add_snapshot(
        actor=_analyst(), engagement_id=eng.id, expected_version=eng.version,
        cap_table=_ct(shares=1000, price=2.0),  # price up → LP amount up
        source=SnapshotSource.manual_edit,
    )
    rollup = compute_subsequent_events(store, eng.id)
    by_cat = group_events_by_category(rollup)
    assert "Issue price" in by_cat or "Liquidation preference" in by_cat
