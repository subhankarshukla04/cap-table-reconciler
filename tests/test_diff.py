"""Tests for cap-table snapshot diff."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.diff import _lev, _similarity, diff_cap_tables
from src.parser import load_from_canonical_json


F01 = Path(__file__).parent.parent / "fixtures" / "fixture_01_clean" / "cap_table_input.json"
F04 = Path(__file__).parent.parent / "fixtures" / "fixture_04_down_round_ratchet" / "cap_table_input.json"


def test_levenshtein_basics():
    assert _lev("abc", "abc") == 0
    assert _lev("abc", "abd") == 1
    assert _lev("", "abc") == 3
    assert _lev("kitten", "sitting") == 3


def test_similarity_normalizes_case_and_punctuation():
    assert _similarity("Series A Pref", "series a pref") == 1.0
    assert _similarity("Series A Pref", "Series A Preferred") > 0.6


def test_diff_self_returns_all_matched():
    ct = load_from_canonical_json(F01)
    d = diff_cap_tables(ct, ct)
    statuses = [m.status for m in d.matches]
    assert all(s == "matched" for s in statuses)
    assert all(not cd.deltas for cd in d.class_diffs)


def test_diff_detects_share_count_change():
    ct1 = load_from_canonical_json(F01)
    ct2 = ct1.model_copy(deep=True)
    # Bump Series B shares
    new_classes = []
    for sc in ct2.share_classes:
        if "Series B" in sc.name:
            new_classes.append(sc.model_copy(update={"shares_outstanding": sc.shares_outstanding + 500_000}))
        else:
            new_classes.append(sc)
    ct2 = ct2.model_copy(update={"share_classes": new_classes})

    d = diff_cap_tables(ct1, ct2)
    series_b_diff = next(cd for cd in d.class_diffs if cd.match.left_name and "Series B" in cd.match.left_name)
    assert any(d.field == "shares_outstanding" for d in series_b_diff.deltas)


def test_diff_detects_added_class():
    ct1 = load_from_canonical_json(F01)
    ct2 = load_from_canonical_json(F04)  # different fixture, more classes
    d = diff_cap_tables(ct1, ct2)
    statuses = {m.status for m in d.matches}
    # Different companies → many added/removed
    assert "added" in statuses or "removed" in statuses


def test_diff_fuzzy_matches_renamed_class():
    ct1 = load_from_canonical_json(F01)
    ct2 = ct1.model_copy(deep=True)
    new_classes = []
    for sc in ct2.share_classes:
        if sc.name == "Series A Preferred":
            new_classes.append(sc.model_copy(update={"name": "Series A Pref"}))
        else:
            new_classes.append(sc)
    ct2 = ct2.model_copy(update={"share_classes": new_classes})
    d = diff_cap_tables(ct1, ct2)
    renamed = [m for m in d.matches if m.status == "renamed"]
    assert len(renamed) == 1
    assert renamed[0].left_name == "Series A Preferred"
    assert renamed[0].right_name == "Series A Pref"


def test_diff_route_renders():
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/diff")
        assert r.status_code == 200
        assert b"snapshot diff" in r.data.lower()


def test_diff_route_runs_with_fixture_xlsx():
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    f02 = Path(__file__).parent.parent / "fixtures" / "fixture_02_typical_messy" / "cap_table.xlsx"
    f04 = Path(__file__).parent.parent / "fixtures" / "fixture_04_down_round_ratchet" / "cap_table.xlsx"
    with app.test_client() as c:
        with f02.open("rb") as l, f04.open("rb") as r:
            resp = c.post(
                "/diff",
                data={
                    "left": (l, "f02.xlsx"),
                    "right": (r, "f04.xlsx"),
                },
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Diff result" in body or "Field deltas" in body
