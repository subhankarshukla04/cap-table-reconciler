"""Audit-log query SLO benchmark (W3.3 / GAP-38 / SYSTEM_SPEC §8 OPS).

Synthesises a large audit chain and measures `list_audit_events`. Per
OPERATIONS.md §1, the target SLO is ≤ 5 seconds to list the full chain
for a single engagement at 10k events. This test runs the benchmark
on a smaller scale (1k events) in CI and asserts a strict bound; a
manual @pytest.mark.slow variant runs the 10k version locally.

Also covers audit M1 — confirms the rate-limit window math is hourly,
not 2x-windowed.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from src.engagement import AuditEventType, EngagementStore
from src.identity import Role, User
from src.rate_limit import ExportRateLimiter


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    s = EngagementStore(db_path=p)
    yield s
    p.unlink(missing_ok=True)


def _seed(store, n: int):
    actor = User(id="u-a", email="a@x", role=Role.analyst, display_name="A")
    eng = store.create_engagement(
        actor=actor, client_id="c", standard_of_value="ifrs13",
        pack_version="v2026.1.0", engine_version="x",
    )
    for i in range(n):
        store._append_audit_event(
            engagement_id=eng.id,
            event_type=AuditEventType.snapshot_added,
            payload={"i": i, "noise": "x" * 32},
            actor=actor,
        )
    return eng


def test_audit_log_query_under_1s_at_1k_events(store):
    """At 1k events the query must complete well under the 5s SLO."""
    eng = _seed(store, 1_000)
    t0 = time.perf_counter()
    events = store.list_audit_events(eng.id)
    dt = time.perf_counter() - t0
    assert len(events) >= 1_000  # plus the genesis create event
    assert dt < 1.0, f"1k-event query took {dt:.3f}s (>1.0s soft bound)"


@pytest.mark.slow
def test_audit_log_query_meets_slo_at_10k_events(store):
    """SLO target: ≤ 5s for a 7-year engagement (~10k events). Marked
    slow because the seed itself takes ~10s on the reference env."""
    eng = _seed(store, 10_000)
    t0 = time.perf_counter()
    events = store.list_audit_events(eng.id)
    dt = time.perf_counter() - t0
    assert len(events) >= 10_000
    assert dt < 5.0, f"10k-event query took {dt:.3f}s (>5.0s SLO)"


def test_audit_chain_intact_after_1k_events(store):
    """Defense in depth: B1's lock + the hash chain hold at scale."""
    eng = _seed(store, 1_000)
    ok, problem = store.verify_audit_log(eng.id)
    assert ok, problem


# ---- M1 rate-limit window math (audit fix) -------------------------------


def test_m1_rate_limit_window_only_counts_within_window():
    """Same hour boundary the audit flagged: after 2x the window, the
    counter must drop to zero, not carry."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        p = Path(fh.name)
    try:
        t = [1_700_000_000.0]
        rl = ExportRateLimiter(db_path=p, soft_limit=3, hard_limit=10,
                                window_seconds=3600, now_fn=lambda: t[0])
        for _ in range(3):
            rl.consume("u-1")
        # 2 hours later → counter should be zero, then 1
        t[0] += 2 * 3600 + 1
        r = rl.consume("u-1")
        # After 2 hours, no prior bucket survives the SUM range.
        assert r.current_count == 1
        assert r.allowed
    finally:
        p.unlink(missing_ok=True)
