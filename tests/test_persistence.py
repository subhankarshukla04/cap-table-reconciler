"""SQLite SessionStore — persistence + restart-survival tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.parser import load_from_canonical_json, parse_excel
from src.persistence import SessionStore


FIXTURE = Path(__file__).parent.parent / "fixtures" / "fixture_02_typical_messy"


def _make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


def test_put_and_get_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")
    store["abc"] = {
        "cap_table": cap_table,
        "parse_report": None,
        "raw_excerpt": None,
        "fixture_id": "fixture_02_typical_messy",
        "resolutions": [],
    }
    sess = store["abc"]
    assert sess["cap_table"].company.name == "Pelaut Logistics Pte. Ltd."
    assert sess["fixture_id"] == "fixture_02_typical_messy"
    assert sess["waterfall"] is not None
    assert len(sess["findings"]) > 0


def test_survives_process_restart(tmp_path):
    db = tmp_path / "sessions.db"
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")

    store1 = SessionStore(db)
    store1["tok1"] = {
        "cap_table": cap_table,
        "parse_report": None,
        "raw_excerpt": None,
        "fixture_id": "fixture_02_typical_messy",
        "resolutions": [{"code": "X", "summary": "test"}],
    }

    # Simulate process restart by creating a fresh store on the same DB file.
    store2 = SessionStore(db)
    assert "tok1" in store2
    sess = store2["tok1"]
    assert sess["cap_table"].company.name == "Pelaut Logistics Pte. Ltd."
    assert sess["resolutions"] == [{"code": "X", "summary": "test"}]


def test_flush_persists_in_place_mutation(tmp_path):
    store = _make_store(tmp_path)
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")
    store["t"] = {
        "cap_table": cap_table,
        "parse_report": None,
        "raw_excerpt": None,
        "fixture_id": None,
        "resolutions": [],
    }
    sess = store["t"]
    sess["resolutions"].append({"code": "MUT", "summary": "mutated"})
    store.flush("t")

    fresh = SessionStore(store.db_path)
    assert fresh["t"]["resolutions"] == [{"code": "MUT", "summary": "mutated"}]


def test_parse_report_serialization_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    cap_table, report = parse_excel(FIXTURE / "cap_table.xlsx")
    store["p"] = {
        "cap_table": cap_table,
        "parse_report": report,
        "raw_excerpt": None,
        "fixture_id": None,
        "resolutions": [],
    }

    fresh = SessionStore(store.db_path)
    sess = fresh["p"]
    assert sess["parse_report"].cap_table_sheet == report.cap_table_sheet
    assert sess["parse_report"].column_mapping == report.column_mapping
    assert len(sess["parse_report"].warnings) == len(report.warnings)
    assert sess["parse_report"].warnings[0].code == report.warnings[0].code


def test_clear_wipes_db(tmp_path):
    store = _make_store(tmp_path)
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")
    store["x"] = {
        "cap_table": cap_table,
        "parse_report": None,
        "raw_excerpt": None,
        "fixture_id": None,
        "resolutions": [],
    }
    store.clear()
    assert "x" not in store
    fresh = SessionStore(store.db_path)
    assert "x" not in fresh


def test_get_returns_default_for_missing(tmp_path):
    store = _make_store(tmp_path)
    assert store.get("missing") is None
    assert store.get("missing", "fallback") == "fallback"


def test_contains_returns_false_for_missing(tmp_path):
    store = _make_store(tmp_path)
    assert "nope" not in store


def test_list_sessions_returns_summary(tmp_path):
    store = _make_store(tmp_path)
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")
    for tok in ("alpha", "beta"):
        store[tok] = {
            "cap_table": cap_table,
            "parse_report": None,
            "raw_excerpt": None,
            "fixture_id": "fixture_02_typical_messy",
            "resolutions": [],
        }
    items = store.list_sessions()
    assert len(items) == 2
    tokens = {s["token"] for s in items}
    assert tokens == {"alpha", "beta"}
    assert all(s["company_name"] == "Pelaut Logistics Pte. Ltd." for s in items)
    assert all(s["fixture_id"] == "fixture_02_typical_messy" for s in items)


def test_delete_removes_session(tmp_path):
    store = _make_store(tmp_path)
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")
    store["zap"] = {
        "cap_table": cap_table,
        "parse_report": None,
        "raw_excerpt": None,
        "fixture_id": None,
        "resolutions": [],
    }
    assert "zap" in store
    assert store.delete("zap") is True
    assert "zap" not in store
    # Idempotent
    assert store.delete("zap") is False


def test_len_counts_db_rows(tmp_path):
    store = _make_store(tmp_path)
    cap_table = load_from_canonical_json(FIXTURE / "cap_table_input.json")
    for tok in ("a", "b", "c"):
        store[tok] = {
            "cap_table": cap_table,
            "parse_report": None,
            "raw_excerpt": None,
            "fixture_id": None,
            "resolutions": [],
        }
    assert len(store) == 3
