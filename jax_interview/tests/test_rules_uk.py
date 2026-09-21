"""Corpus integrity + engine integration tests for the UK rule set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.corpus import Corpus
from src.engine import resolve
from src.models import (
    Confidence,
    Event,
    Jurisdiction,
    Query,
    Rule,
    TaxStatus,
    TaxTreatment,
)

UK_PATH = Path(__file__).parent.parent / "src" / "rules" / "uk.json"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def uk_rules() -> list[Rule]:
    raw = json.loads(UK_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


@pytest.fixture(scope="module")
def full_corpus() -> Corpus:
    return Corpus.load(RULES)


def test_uk_loads_cleanly(uk_rules):
    assert len(uk_rules) >= 10
    for r in uk_rules:
        assert r.citations, f"{r.rule_id} has no citations"


def test_uk_taxing_jurisdiction_always_uk(uk_rules):
    """uk.json is the UK-perspective corpus; all rules tax under UK law."""
    for r in uk_rules:
        assert r.taxing_jurisdiction == Jurisdiction.UK, (
            f"{r.rule_id} has taxing={r.taxing_jurisdiction.value}, expected UK"
        )


def test_uk_within_jurisdiction_event_coverage(uk_rules):
    """UK-UK must cover grant, vest, exercise (resident), sale (resident)."""
    uk_uk = [r for r in uk_rules
             if r.parent_jurisdiction == Jurisdiction.UK
             and r.employee_jurisdiction == Jurisdiction.UK]
    events = {r.event for r in uk_uk}
    assert events >= {Event.GRANT, Event.VEST, Event.EXERCISE, Event.SALE}


def test_uk_no_tax_at_grant_or_vest(uk_rules):
    for r in uk_rules:
        if r.event in (Event.GRANT, Event.VEST) and r.parent_jurisdiction == Jurisdiction.UK \
                and r.employee_jurisdiction == Jurisdiction.UK:
            assert r.tax_treatment == TaxTreatment.NO_TAX


def test_uk_exercise_rule_covers_emi_and_unapproved(uk_rules):
    """The canonical UK-UK exercise rule must spell out EMI vs unapproved-option
    treatment dichotomy."""
    canonical = [r for r in uk_rules
                 if r.parent_jurisdiction == Jurisdiction.UK
                 and r.employee_jurisdiction == Jurisdiction.UK
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    rd = canonical[0].rate_description
    assert "EMI" in rd
    assert "unapproved" in rd.lower() or "non-statutory" in rd.lower()


def test_uk_exercise_cites_itepa_section_477(uk_rules):
    """UK exercise rule must cite ITEPA 2003 §477 (chargeable events)."""
    canonical = [r for r in uk_rules
                 if r.parent_jurisdiction == Jurisdiction.UK
                 and r.employee_jurisdiction == Jurisdiction.UK
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    blob = " ".join(f"{c.authority} {c.reference}" for c in canonical[0].citations)
    assert "477" in blob


def test_uk_sale_references_badr_lifetime_cap(uk_rules):
    """The UK sale rule must reference Business Asset Disposal Relief (BADR)."""
    rules = [r for r in uk_rules
             if r.parent_jurisdiction == Jurisdiction.UK
             and r.employee_jurisdiction == Jurisdiction.UK
             and r.event == Event.SALE]
    assert rules
    blob = rules[0].rate_description + " " + " ".join(rules[0].caveats)
    assert "BADR" in blob or "Business Asset Disposal Relief" in blob
    assert "£1M" in blob or "1M lifetime" in blob


def test_uk_sale_post_oct_2024_rates_present(uk_rules):
    """Confirm the post-Budget 30 October 2024 rates (18%/24%) are cited."""
    rules = [r for r in uk_rules
             if r.parent_jurisdiction == Jurisdiction.UK
             and r.employee_jurisdiction == Jurisdiction.UK
             and r.event == Event.SALE]
    assert rules
    rd = rules[0].rate_description
    assert "18%" in rd or "18 %" in rd
    assert "24%" in rd or "24 %" in rd


def test_uk_engine_uk_uk_exercise_resolves_with_emi_in_summary(full_corpus):
    """UK-UK exercise yields a verdict with EMI mentioned in either rule or
    summary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.UK,
        employee_jurisdiction=Jurisdiction.UK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=5.0,
        exercise_price=0.5,
        options_in_event=10000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.UK
    assert v.computed_amount_taxable == pytest.approx(45000.0)
    # No cross-border secondary
    assert v.secondary_rules == []


def test_uk_engine_uk_in_cross_border(full_corpus):
    """UK parent, IN employee: IN perquisite primary + UK no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.UK,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=2.0,
        exercise_price=0.20,
        options_in_event=8000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert any(r.taxing_jurisdiction == Jurisdiction.UK for r in v.secondary_rules)
    # Spread = (2 - 0.20) * 8000 = 14400
    assert v.computed_amount_taxable == pytest.approx(14400.0)


def test_uk_engine_uk_us_cross_border(full_corpus):
    """UK parent, US employee: US worldwide primary + UK no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.UK,
        employee_jurisdiction=Jurisdiction.US,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=10.0,
        exercise_price=2.0,
        options_in_event=1500,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.US
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.UK for r in v.secondary_rules)


def test_uk_engine_in_uk_cross_border(full_corpus):
    """IN parent, UK employee: UK ITEPA primary + IN no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.UK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=4.0,
        exercise_price=1.0,
        options_in_event=3000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.UK
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.IN for r in v.secondary_rules)


def test_uk_engine_us_uk_cross_border(full_corpus):
    """US parent, UK employee: UK ITEPA primary + US no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.US,
        employee_jurisdiction=Jurisdiction.UK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=20.0,
        exercise_price=5.0,
        options_in_event=500,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.UK
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.US for r in v.secondary_rules)


def test_uk_engine_sg_uk_cross_border(full_corpus):
    """SG parent, UK employee: UK ITEPA primary + SG no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.UK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=3.5,
        exercise_price=0.5,
        options_in_event=2000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.UK
    assert any(r.taxing_jurisdiction == Jurisdiction.SG for r in v.secondary_rules)


def test_uk_every_cross_border_rule_has_caveats(uk_rules):
    """All UK cross-border rules must have caveats."""
    for r in uk_rules:
        if r.parent_jurisdiction != r.employee_jurisdiction:
            assert r.caveats, f"{r.rule_id}: cross-border rule lacks caveats"


def test_total_corpus_size_after_5_jurisdictions():
    """Sanity: 5 jurisdictions, full corpus should be ≥ 55 rules."""
    c = Corpus.load(RULES)
    assert len(c) >= 55, f"corpus size {len(c)} below threshold"
