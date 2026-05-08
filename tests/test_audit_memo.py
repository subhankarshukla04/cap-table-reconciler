"""Tests for the audit-memo skeleton generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.audit_memo import build_audit_memo
from src.checklist import run_checklist
from src.parser import load_from_canonical_json
from src.waterfall import compute_waterfall


@pytest.mark.parametrize(
    "fixture_id",
    [
        "fixture_01_clean",
        "fixture_02_typical_messy",
        "fixture_03_edge_case",
        "fixture_04_down_round_ratchet",
    ],
)
def test_memo_has_required_sections(fixture_id):
    cap_table = load_from_canonical_json(
        Path(__file__).parent.parent / "fixtures" / fixture_id / "cap_table_input.json"
    )
    wf = compute_waterfall(cap_table)
    findings = run_checklist(cap_table)
    md = build_audit_memo(cap_table, wf, findings, [])

    # Every memo has these sections
    for s in (
        "# Audit Memo",
        "## 1. Capital structure",
        "## 4. Gap-detection findings",
        "## 5. Waterfall breakpoints",
        "## 6. Tranche allocation matrix",
        "## 7. Methodology disclosures",
        "## 8. Analyst sign-off",
    ):
        assert s in md, f"{fixture_id} missing section: {s}"

    # Company name surfaces
    assert cap_table.company.name in md
    # Has at least one breakpoint
    assert "BP1" in md
    # Has analyst placeholders
    assert "[ANALYST" in md


def test_memo_includes_resolutions_when_present():
    cap_table = load_from_canonical_json(
        Path(__file__).parent.parent / "fixtures" / "fixture_01_clean" / "cap_table_input.json"
    )
    wf = compute_waterfall(cap_table)
    findings = run_checklist(cap_table)
    resolutions = [{"code": "AD-MISSING-Foo", "summary": "Resolved as broad-based-WA"}]
    md = build_audit_memo(cap_table, wf, findings, resolutions)
    assert "Analyst resolutions applied in-session" in md
    assert "AD-MISSING-Foo" in md
    assert "broad-based-WA" in md


def test_memo_methodology_section_flags_capped_classes():
    cap_table = load_from_canonical_json(
        Path(__file__).parent.parent / "fixtures" / "fixture_03_edge_case" / "cap_table_input.json"
    )
    wf = compute_waterfall(cap_table)
    findings = run_checklist(cap_table)
    md = build_audit_memo(cap_table, wf, findings, [])
    assert "Participating-with-cap" in md
    assert "Series A CCPS" in md  # the capped class


def test_memo_methodology_flags_full_ratchet_for_f04():
    cap_table = load_from_canonical_json(
        Path(__file__).parent.parent / "fixtures" / "fixture_04_down_round_ratchet" / "cap_table_input.json"
    )
    wf = compute_waterfall(cap_table)
    findings = run_checklist(cap_table)
    md = build_audit_memo(cap_table, wf, findings, [])
    assert "Full-ratchet" in md
    assert "Series Seed CCPS" in md


def test_bundle_zip_contains_all_artifacts():
    import io
    import zipfile
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/demo/fixture_03_edge_case", follow_redirects=False)
        token = r.headers["Location"].split("/")[-1]
        r2 = c.get(f"/export/{token}.zip")
        assert r2.status_code == 200
        assert r2.mimetype == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r2.data))
        names = zf.namelist()
        assert any(n.endswith(".json") for n in names)
        assert any(n.endswith("_static.xlsx") for n in names)
        assert any(n.endswith("_live_formulas.xlsx") for n in names)
        assert any(n.endswith(".md") for n in names)
    SESSIONS.clear()


def test_memo_route_renders_for_each_fixture():
    from app import app, SESSIONS

    SESSIONS.clear()
    app.config["TESTING"] = True
    with app.test_client() as c:
        for fix in (
            "fixture_01_clean",
            "fixture_02_typical_messy",
            "fixture_03_edge_case",
            "fixture_04_down_round_ratchet",
        ):
            r = c.get(f"/demo/{fix}", follow_redirects=False)
            token = r.headers["Location"].split("/")[-1]
            r2 = c.get(f"/export/{token}.md")
            assert r2.status_code == 200
            assert r2.mimetype.startswith("text/markdown")
            assert b"# Audit Memo" in r2.data
            assert b"[ANALYST" in r2.data
    SESSIONS.clear()
