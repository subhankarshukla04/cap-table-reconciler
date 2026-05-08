"""Tests for the CLI shim."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.cli import main


def test_cli_demo_emits_all_artifacts(tmp_path):
    out = tmp_path / "out"
    bundle = tmp_path / "bundle.zip"
    rc = main([
        "demo", "fixture_03_edge_case",
        "--out", str(out),
        "--bundle", str(bundle),
    ])
    assert rc == 0
    files = {p.name for p in out.iterdir()}
    assert any(n.endswith("_clean.json") for n in files)
    assert any(n.endswith("_static.xlsx") for n in files)
    assert any(n.endswith("_live_formulas.xlsx") for n in files)
    assert any(n.startswith("audit_memo_") for n in files)
    assert bundle.exists()
    with zipfile.ZipFile(bundle) as zf:
        assert len(zf.namelist()) == 4


def test_cli_reconcile_on_fixture_xlsx(tmp_path):
    src = Path(__file__).parent.parent / "fixtures" / "fixture_02_typical_messy" / "cap_table.xlsx"
    out = tmp_path / "out"
    rc = main([
        "reconcile", str(src),
        "--out", str(out),
    ])
    assert rc == 0
    assert (out / "Pelaut_Logistics_Pte_Ltd_clean.json").exists()


def test_cli_reconcile_returns_error_for_missing_input(tmp_path):
    rc = main(["reconcile", str(tmp_path / "nope.xlsx")])
    assert rc == 2


def test_cli_demo_rejects_invalid_fixture(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["demo", "fixture_99_does_not_exist"])
