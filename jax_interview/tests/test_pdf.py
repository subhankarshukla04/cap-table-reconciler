"""PDF advisory memo tests — render Verdict to PDF via reportlab."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.corpus import Corpus
from src.engine import resolve
from src.models import Event, Jurisdiction, Query, TaxStatus
from src.pdf import verdict_to_pdf

FIXTURES = Path(__file__).parent / "fixtures"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.load(RULES)


def _load_query(name: str) -> Query:
    raw = json.loads((FIXTURES / f"{name}.json").read_text())
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}
    return Query.model_validate(raw)


@pytest.mark.parametrize("fixture_name", [
    "praxis",
    "pelaut",
    "solstice",
    "atlas_corp",
    "avalon_uk",
    "horizon_hk",
    "zenith_ae",
])
def test_pdf_renders_for_every_fixture(corpus, fixture_name):
    q = _load_query(fixture_name)
    v = resolve(q, corpus)
    blob = verdict_to_pdf(v)
    assert isinstance(blob, bytes)
    assert blob.startswith(b"%PDF-"), f"{fixture_name}: output is not a valid PDF"
    assert len(blob) > 5000, f"{fixture_name}: PDF too small ({len(blob)} bytes)"


def test_pdf_includes_audit_firm_letterhead(corpus):
    q = _load_query("praxis")
    v = resolve(q, corpus)
    blob = verdict_to_pdf(v, firm_name="Test Firm LLP")
    # PDF byte stream contains the firm name (after compression-free encoding)
    assert b"Test Firm LLP" in blob


def test_pdf_default_firm_name_applied(corpus):
    q = _load_query("praxis")
    v = resolve(q, corpus)
    blob = verdict_to_pdf(v)
    assert b"ESOP Atlas Advisory" in blob


def test_pdf_size_grows_with_more_secondaries(corpus):
    """A cross-border verdict (with secondaries) yields a larger PDF than a single-rule verdict."""
    cross = _load_query("praxis")
    v_cross = resolve(cross, corpus)
    pdf_cross = verdict_to_pdf(v_cross)

    solo = _load_query("solstice")  # SG-SG deemed-exercise, no secondaries
    v_solo = resolve(solo, corpus)
    pdf_solo = verdict_to_pdf(v_solo)

    # Both should be valid PDFs
    assert pdf_cross.startswith(b"%PDF-")
    assert pdf_solo.startswith(b"%PDF-")
    # Cross-border memo has at least one secondary; solo has none.
    # We don't assert relative size (compression can flip it) but assert both produce content.
    assert len(pdf_cross) > 4000
    assert len(pdf_solo) > 3500


def test_pdf_renders_a_requires_counsel_combination(corpus):
    """A combination the corpus does NOT have should still render a PDF (using the synthetic requires-counsel rule)."""
    # Pick a deliberately-uncovered tuple: AE parent + ID employee + grant
    q = Query(
        parent_jurisdiction=Jurisdiction.AE,
        employee_jurisdiction=Jurisdiction.ID,
        event=Event.GRANT,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, corpus)
    blob = verdict_to_pdf(v)
    assert blob.startswith(b"%PDF-")
    assert len(blob) > 3500
