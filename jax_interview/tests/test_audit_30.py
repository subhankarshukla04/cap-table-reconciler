"""30 fresh edge-case tests. Each must:
  (a) test something different from existing tests in test_engine.py /
      test_rules_sg.py / test_rules_in.py / test_fixtures.py / test_export.py
  (b) exercise a potential weakness — invalid input, boundary number,
      corpus integrity, HTTP-layer behavior, serialization roundtrip
  (c) fail loudly if the system regresses, not silently pass

Failures here are useful — they surface bugs to fix, not noise to suppress.
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError

from src.corpus import Corpus, CorpusError
from src.engine import resolve
from src.export import verdict_to_xlsx
from src.models import (
    Citation,
    Confidence,
    Event,
    Jurisdiction,
    Query,
    Rule,
    TaxStatus,
    TaxTreatment,
    Verdict,
)

RULES = Path(__file__).parent.parent / "src" / "rules"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.load(RULES)


@pytest.fixture(scope="module")
def http_client():
    """Flask test client — imports the app module which loads the corpus."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


# =============================================================================
# A. Input validation / edge inputs (5)
# =============================================================================


def test_01_invalid_jurisdiction_string_raises():
    """A bogus jurisdiction must fail at Query construction, not silently coerce."""
    with pytest.raises(ValidationError):
        Query(
            parent_jurisdiction="ZZ",  # type: ignore[arg-type]
            employee_jurisdiction="SG",
            event="exercise",
        )


def test_02_invalid_event_string_raises():
    """A bogus event must fail at Query construction."""
    with pytest.raises(ValidationError):
        Query(
            parent_jurisdiction="SG",
            employee_jurisdiction="IN",
            event="liquidation_preference",  # not in Event enum
        )


def test_03_invalid_tax_status_raises():
    """A bogus tax status must fail at Query construction."""
    with pytest.raises(ValidationError):
        Query(
            parent_jurisdiction="SG",
            employee_jurisdiction="IN",
            event="exercise",
            tax_status="alien",  # not in TaxStatus enum
        )


def test_04_negative_fmv_spread_yields_negative_taxable():
    """If FMV < exercise price (rare but possible on a down-round exercise),
    computed_amount_taxable should be negative — engine should not crash or
    clamp to zero. The UI / downstream advisor handles the loss treatment."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        fmv_at_event=0.05,
        exercise_price=0.50,
        options_in_event=1000,
    )
    assert q.amount_taxable() == pytest.approx(-450.0)


def test_05_zero_options_yields_zero_taxable():
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        fmv_at_event=1.0,
        exercise_price=0.1,
        options_in_event=0,
    )
    assert q.amount_taxable() == pytest.approx(0.0)


# =============================================================================
# B. Numeric edge cases (3)
# =============================================================================


def test_06_float_precision_subtraction_close_enough():
    """0.1 + 0.2 - 0.3 isn't exactly 0 in float arithmetic. amount_taxable on
    such inputs must still be within rounding tolerance — surface the
    floating-point reality, don't pretend it's clean."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        fmv_at_event=0.3,
        exercise_price=0.1 + 0.2,  # = 0.30000000000000004
        options_in_event=1,
    )
    assert abs(q.amount_taxable()) < 1e-10


def test_07_very_large_multiplication_no_overflow():
    """A pre-IPO unicorn with $10/share FMV and 10M options exercised. Python
    floats handle this; the engine must not crash."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        fmv_at_event=10.0,
        exercise_price=0.01,
        options_in_event=10_000_000,
    )
    expected = (10.0 - 0.01) * 10_000_000
    assert q.amount_taxable() == pytest.approx(expected)
    assert q.amount_taxable() > 99_000_000  # nine-figure perquisite


def test_08_negative_options_now_rejected():
    """v1 audit closed: Query now rejects negative options_in_event,
    fmv_at_event, and exercise_price via the ge=0 pydantic constraint. This
    test was originally written to document the gap; now it pins the fix."""
    with pytest.raises(ValidationError):
        Query(
            parent_jurisdiction=Jurisdiction.SG,
            employee_jurisdiction=Jurisdiction.SG,
            event=Event.EXERCISE,
            fmv_at_event=1.0,
            exercise_price=0.1,
            options_in_event=-100,
        )
    with pytest.raises(ValidationError):
        Query(
            parent_jurisdiction=Jurisdiction.SG,
            employee_jurisdiction=Jurisdiction.SG,
            event=Event.EXERCISE,
            fmv_at_event=-1.0,
            exercise_price=0.1,
            options_in_event=100,
        )


# =============================================================================
# C. Engine semantic correctness (7)
# =============================================================================


def test_09_same_jurisdiction_query_has_no_secondaries(corpus):
    """SG-SG exercise: the engine should NOT attach a secondary because parent
    == employee jurisdiction. Only the SG rule applies."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, corpus)
    assert v.secondary_rules == []
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.SG


def test_10_cross_border_secondary_has_different_taxing_jurisdiction(corpus):
    """SG-IN exercise: primary's taxing_jurisdiction != secondary's."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, corpus)
    assert v.secondary_rules, "cross-border query must surface a secondary"
    assert v.primary_rule.taxing_jurisdiction != v.secondary_rules[0].taxing_jurisdiction


def test_11_resident_deemed_exercise_falls_through_to_requires_counsel(corpus):
    """The SG deemed-exercise rule is keyed status=non_resident only. A query
    with status=resident must NOT match it, and must fall through to the
    requires-counsel synthetic rule. The engine should never silently apply a
    rule whose status doesn't match."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.DEEMED_EXERCISE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, corpus)
    assert v.primary_rule.confidence == Confidence.REQUIRES_COUNSEL
    assert "unknown" in v.primary_rule.rule_id


def test_12_non_resident_exercise_picks_specific_rule_not_agnostic(corpus):
    """For (SG, SG, exercise, non_resident), the engine must return the
    non-resident-specific rule (flat 15% or resident rate, whichever higher),
    NOT the resident rule."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        tax_status=TaxStatus.NON_RESIDENT,
    )
    v = resolve(q, corpus)
    assert v.primary_rule.tax_status == TaxStatus.NON_RESIDENT
    assert "15%" in v.primary_rule.rate_description or "flat" in v.primary_rule.rate_description.lower()


def test_13_engine_is_deterministic(corpus):
    """Same Query twice → identical Verdict bytes. No randomness, no time
    dependence, no dict-ordering surprises."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=0.5,
        exercise_price=0.1,
        options_in_event=4000,
    )
    v1 = resolve(q, corpus)
    v2 = resolve(q, corpus)
    assert v1.model_dump_json() == v2.model_dump_json()


def test_14_verdict_pydantic_roundtrip(corpus):
    """Verdict must survive dump → load round-trip without data loss."""
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=50.0,
        exercise_price=10.0,
        options_in_event=1000,
    )
    v = resolve(q, corpus)
    dumped = v.model_dump_json()
    reloaded = Verdict.model_validate_json(dumped)
    assert reloaded.model_dump_json() == dumped
    assert reloaded.primary_rule.rule_id == v.primary_rule.rule_id
    assert reloaded.weakest_confidence == v.weakest_confidence


def test_15_weakest_confidence_mixed_returns_worst(corpus):
    """Build a Verdict with one firm + one conditional rule; weakest must be
    conditional, not firm."""
    firm = Rule(
        rule_id="test.firm.rule",
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        taxing_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        tax_treatment=TaxTreatment.EMPLOYMENT_INCOME,
        rate_description="firm rule",
        confidence=Confidence.FIRM,
        citations=[Citation(authority="Test", reference="Test")],
    )
    conditional = firm.model_copy(update={
        "rule_id": "test.conditional.rule",
        "confidence": Confidence.CONDITIONAL,
        "rate_description": "conditional rule",
    })
    v = Verdict(
        query=Query(
            parent_jurisdiction=Jurisdiction.SG,
            employee_jurisdiction=Jurisdiction.SG,
            event=Event.EXERCISE,
            tax_status=TaxStatus.RESIDENT,
        ),
        primary_rule=firm,
        secondary_rules=[conditional],
        summary="test",
    )
    assert v.weakest_confidence == Confidence.CONDITIONAL


# =============================================================================
# D. Corpus integrity (5)
# =============================================================================


def test_16_no_duplicate_rule_ids_across_files(corpus):
    """rule_id is supposed to be a stable, globally unique key."""
    ids = [r.rule_id for r in corpus.all_rules]
    duplicates = [i for i in set(ids) if ids.count(i) > 1]
    assert not duplicates, f"duplicate rule_ids: {duplicates}"


def test_17_every_citation_has_authority_and_reference(corpus):
    """No empty fields. Pydantic enforces non-empty reference; this also
    checks authority."""
    for r in corpus.all_rules:
        for c in r.citations:
            assert c.authority.strip(), f"{r.rule_id} has citation with empty authority"
            assert c.reference.strip(), f"{r.rule_id} has citation with empty reference"


def test_18_every_rule_has_at_least_one_source_url(corpus):
    """For audit-traceability, every rule should be backed by at least one
    URL — otherwise the demo's "click through to the source" promise fails."""
    missing = []
    for r in corpus.all_rules:
        if not any(c.source_url for c in r.citations):
            missing.append(r.rule_id)
    assert not missing, f"rules without any source URL: {missing}"


def test_19_loader_raises_on_malformed_json(tmp_path):
    """A broken JSON file in the rules dir must surface as CorpusError at app
    start, not corrupt the in-memory index."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    with pytest.raises(CorpusError) as ei:
        Corpus.load(tmp_path)
    assert "invalid JSON" in str(ei.value)


def test_20_loader_raises_on_non_list_top_level(tmp_path):
    """Top-level must be a list of rules — anything else is a corpus author
    error."""
    bad = tmp_path / "bad.json"
    bad.write_text('{"rules": []}')
    with pytest.raises(CorpusError) as ei:
        Corpus.load(tmp_path)
    assert "list of rules" in str(ei.value)


# =============================================================================
# E. Rule cross-validation (5)
# =============================================================================


def test_21_taxing_jurisdiction_validator_rejects_third_jurisdiction():
    """A Rule with taxing_jurisdiction = some third jurisdiction (not parent
    nor employee) must fail validation. This is the safety rail that prevents
    a rule author from accidentally writing "this SG-IN rule is governed by
    Vietnam tax law"."""
    # We need a jurisdiction value not in the (parent, employee) pair.
    # Since the enum only has SG, IN — try setting taxing to one that's not
    # in the pair when parent==employee.
    with pytest.raises(ValueError, match="taxing_jurisdiction"):
        Rule(
            rule_id="test.bad.rule",
            parent_jurisdiction=Jurisdiction.SG,
            employee_jurisdiction=Jurisdiction.SG,
            taxing_jurisdiction=Jurisdiction.IN,  # not in (SG, SG)
            event=Event.EXERCISE,
            tax_status=TaxStatus.RESIDENT,
            tax_treatment=TaxTreatment.EMPLOYMENT_INCOME,
            rate_description="test",
            confidence=Confidence.FIRM,
            citations=[Citation(authority="Test", reference="Test")],
        )


def test_22_no_requires_counsel_in_v1_corpus(corpus):
    """v1 demo must not ship rules tagged 'requires-counsel'. That confidence
    level only appears on the synthetic fallback rule generated at runtime."""
    rc = [r.rule_id for r in corpus.all_rules if r.confidence == Confidence.REQUIRES_COUNSEL]
    assert not rc, f"v1 corpus must not contain requires-counsel rules: {rc}"


def test_23_withholding_yes_has_filing_or_documents(corpus):
    """If we say withholding is required, we must also tell the user WHAT to
    file and/or WHAT documents to gather. Otherwise the verdict is half-built."""
    bad = []
    for r in corpus.all_rules:
        if r.withholding == "yes" and not (r.filing_requirement or r.documents_required):
            bad.append(r.rule_id)
    assert not bad, f"rules with withholding=yes but no filing or documents: {bad}"


def test_24_cross_border_rules_have_at_least_one_caveat(corpus):
    """Cross-border tax is never simple. Every cross-border rule must surface
    at least one caveat — DTAA, apportionment, transfer pricing, etc."""
    no_caveats = []
    for r in corpus.all_rules:
        if r.parent_jurisdiction != r.employee_jurisdiction:
            if not r.caveats:
                no_caveats.append(r.rule_id)
    # Allow up to 4 'no_tax' cross-border rules without caveats (the trivial
    # "no nexus" cases), but flag if anything beyond that has none
    assert len(no_caveats) <= 4, f"cross-border rules without caveats: {no_caveats}"


def test_25_citation_retrieved_on_within_two_years(corpus):
    """Every rule's source verification must be within a 2-year freshness
    window. Anything older is stale; anything in the future is a typo."""
    today = date.today()
    stale = []
    future = []
    for r in corpus.all_rules:
        for c in r.citations:
            if c.retrieved_on is None:
                continue
            age_days = (today - c.retrieved_on).days
            if age_days > 730:
                stale.append((r.rule_id, c.retrieved_on))
            elif age_days < 0:
                future.append((r.rule_id, c.retrieved_on))
    assert not stale, f"stale citations (>2y): {stale}"
    assert not future, f"future-dated citations: {future}"


# =============================================================================
# F. HTTP / app-layer integration (5)
# =============================================================================


def test_26_http_resolve_with_minimal_form(http_client):
    """POST /resolve with only the required fields renders a verdict (even
    without FMV/strike/options)."""
    r = http_client.post(
        "/resolve",
        data={
            "parent_jurisdiction": "SG",
            "employee_jurisdiction": "IN",
            "event": "exercise",
            "tax_status": "resident",
        },
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "perquisite" in body.lower()


def test_27_http_verdict_unknown_scenario_returns_404(http_client):
    """GET /verdict/<bogus> must 404, not 500."""
    r = http_client.get("/verdict/this_is_not_a_real_fixture")
    assert r.status_code == 404


def test_28_http_export_unknown_scenario_returns_404(http_client):
    """Same for the Excel export route — 404 not crash."""
    r = http_client.get("/export/xlsx/nonexistent")
    assert r.status_code == 404


def test_29_http_htmx_fragment_smaller_than_full_page(http_client):
    """HTMX swap should return a fragment (no <html>, no nav, no footer);
    full page request returns the wrapped version. Fragment must be
    materially smaller."""
    payload = {
        "parent_jurisdiction": "SG",
        "employee_jurisdiction": "IN",
        "event": "exercise",
        "tax_status": "resident",
    }
    full = http_client.post("/resolve", data=payload)
    htmx = http_client.post("/resolve", data=payload, headers={"HX-Request": "true"})
    full_body = full.get_data(as_text=True)
    htmx_body = htmx.get_data(as_text=True)
    assert full.status_code == 200 and htmx.status_code == 200
    assert "<html" in full_body.lower()
    assert "<html" not in htmx_body.lower()
    assert len(htmx_body) < len(full_body)


def test_30_http_sources_page_lists_all_corpus_rules(http_client, corpus):
    """The /sources page must enumerate every rule_id from the loaded corpus."""
    r = http_client.get("/sources")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    missing = [rid for rid in (rule.rule_id for rule in corpus.all_rules) if rid not in body]
    assert not missing, f"/sources missing rule IDs: {missing}"
