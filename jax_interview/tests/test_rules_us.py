"""Corpus integrity + engine integration tests for the US rule set."""

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

US_PATH = Path(__file__).parent.parent / "src" / "rules" / "us.json"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def us_rules() -> list[Rule]:
    raw = json.loads(US_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


@pytest.fixture(scope="module")
def full_corpus() -> Corpus:
    return Corpus.load(RULES)


def test_us_loads_cleanly(us_rules):
    """All US rules pass schema + carry citations."""
    assert len(us_rules) >= 12
    for r in us_rules:
        assert r.citations, f"{r.rule_id} has no citations"
        for c in r.citations:
            assert c.authority and c.reference, f"{r.rule_id} has incomplete citation"


def test_us_taxing_jurisdictions_valid(us_rules):
    """us.json contains rules where taxing=US (within-US + US perspective on
    cross-border) OR taxing=neighbor (cross-border counterparty perspectives)."""
    for r in us_rules:
        assert r.taxing_jurisdiction in {Jurisdiction.US, Jurisdiction.SG, Jurisdiction.IN}


def test_us_within_jurisdiction_event_coverage(us_rules):
    """US-US must cover grant, vest, exercise (resident), sale (resident)."""
    us_us = [r for r in us_rules
             if r.parent_jurisdiction == Jurisdiction.US
             and r.employee_jurisdiction == Jurisdiction.US]
    events = {r.event for r in us_us}
    assert events >= {Event.GRANT, Event.VEST, Event.EXERCISE, Event.SALE}


def test_us_no_tax_at_grant_or_vest_us_perspective(us_rules):
    """US tax law: no tax at grant or vest for standard option grants
    (assumes no readily ascertainable FMV; standard private-co fact pattern)."""
    for r in us_rules:
        if r.event in (Event.GRANT, Event.VEST) and r.taxing_jurisdiction == Jurisdiction.US:
            assert r.tax_treatment == TaxTreatment.NO_TAX


def test_us_exercise_rule_covers_both_iso_and_nso(us_rules):
    """The canonical US-US exercise rule must mention BOTH ISO and NSO treatment."""
    canonical = [r for r in us_rules
                 if r.parent_jurisdiction == Jurisdiction.US
                 and r.employee_jurisdiction == Jurisdiction.US
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    rd = canonical[0].rate_description
    assert "ISO" in rd and "NSO" in rd


def test_us_exercise_cites_section_56_amt(us_rules):
    """The US-US exercise rule must cite IRC §56(b)(3) for the ISO AMT
    adjustment — this is the headline edge case."""
    canonical = [r for r in us_rules
                 if r.parent_jurisdiction == Jurisdiction.US
                 and r.employee_jurisdiction == Jurisdiction.US
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    blob = " ".join(f"{c.authority} {c.reference}" for c in canonical[0].citations)
    assert "56" in blob or "AMT" in blob or "alternative minimum" in blob.lower()


def test_us_exercise_iso_form_3921_in_documents(us_rules):
    """ISO exercise triggers Form 3921 filing — must be in the documents list."""
    canonical = [r for r in us_rules
                 if r.parent_jurisdiction == Jurisdiction.US
                 and r.employee_jurisdiction == Jurisdiction.US
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    docs = " ".join(canonical[0].documents_required)
    assert "3921" in docs or "Form 3921" in docs


def test_us_sale_references_ltcg_holding_period(us_rules):
    """The US sale rule must mention the ISO qualifying-disposition holding
    period (2 years grant + 1 year exercise) as a key concept."""
    rules = [r for r in us_rules
             if r.parent_jurisdiction == Jurisdiction.US
             and r.employee_jurisdiction == Jurisdiction.US
             and r.event == Event.SALE]
    assert rules
    rd = rules[0].rate_description
    assert "2 year" in rd or "2 years" in rd or "qualifying" in rd.lower()
    assert "LTCG" in rd or "long-term" in rd.lower()


def test_us_sg_cross_border_has_no_treaty_caveat(us_rules):
    """US-SG cross-border rules must flag the absence of a comprehensive
    income tax treaty — this is a frequently-missed fact."""
    sg_rules = [r for r in us_rules
                if Jurisdiction.SG in (r.parent_jurisdiction, r.employee_jurisdiction)
                and Jurisdiction.US in (r.parent_jurisdiction, r.employee_jurisdiction)]
    assert sg_rules
    found_treaty_note = False
    for r in sg_rules:
        all_text = r.rate_description + " " + " ".join(r.caveats) + " " + " ".join(
            f"{c.authority} {c.reference} {c.note or ''}" for c in r.citations
        )
        if "no comprehensive" in all_text.lower() or "no US-Singapore" in all_text or "no US-SG" in all_text or "§901" in all_text:
            found_treaty_note = True
            break
    assert found_treaty_note, "US-SG rules must flag absence of comprehensive treaty"


def test_us_engine_us_in_exercise_cross_border(full_corpus):
    """End-to-end: US parent, IN employee exercise must produce IN perquisite
    primary + US no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.US,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=10.0,
        exercise_price=1.0,
        options_in_event=2000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert v.primary_rule.withholding == "yes"
    assert len(v.secondary_rules) >= 1
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.US
    assert v.secondary_rules[0].tax_treatment == TaxTreatment.NO_TAX
    # Spread = (10 - 1) * 2000 = 18000
    assert v.computed_amount_taxable == pytest.approx(18000.0)


def test_us_engine_in_us_exercise_cross_border(full_corpus):
    """IN parent, US employee: US worldwide-income rule applies (primary), IN
    no-tax for non-resident services-outside-India (secondary)."""
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.US,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=5.0,
        exercise_price=0.5,
        options_in_event=10000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.US
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert v.primary_rule.withholding == "yes"
    assert len(v.secondary_rules) >= 1
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.IN
    assert v.secondary_rules[0].tax_treatment == TaxTreatment.NO_TAX
    # Spread = (5 - 0.5) * 10000 = 45000
    assert v.computed_amount_taxable == pytest.approx(45000.0)


def test_us_engine_sg_us_exercise_cross_border(full_corpus):
    """SG parent, US employee: US worldwide primary, SG no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.US,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=2.0,
        exercise_price=0.2,
        options_in_event=5000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.US
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert v.secondary_rules
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.SG
    # No US-SG comprehensive treaty — the caveat must surface
    all_caveats = " ".join(v.primary_rule.caveats)
    assert "treaty" in all_caveats.lower() or "§901" in all_caveats or "FTC" in all_caveats


def test_us_engine_us_us_exercise_resident(full_corpus):
    """Pure within-US exercise resolves to dual-treatment employment_income."""
    q = Query(
        parent_jurisdiction=Jurisdiction.US,
        employee_jurisdiction=Jurisdiction.US,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=50.0,
        exercise_price=10.0,
        options_in_event=1000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.US
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    # No cross-border secondary for within-US query
    assert v.secondary_rules == []
    assert v.computed_amount_taxable == pytest.approx(40000.0)


def test_us_409a_caveat_present(us_rules):
    """The US grant rule must surface §409A discount-option risk."""
    grant_rules = [r for r in us_rules
                   if r.parent_jurisdiction == Jurisdiction.US
                   and r.employee_jurisdiction == Jurisdiction.US
                   and r.event == Event.GRANT]
    assert grant_rules
    caveats_text = " ".join(grant_rules[0].caveats)
    assert "§409A" in caveats_text or "409A" in caveats_text


def test_us_every_cross_border_rule_has_caveats(us_rules):
    """All US cross-border rules must have at least one caveat."""
    for r in us_rules:
        if r.parent_jurisdiction != r.employee_jurisdiction:
            assert r.caveats, f"{r.rule_id}: cross-border rule lacks caveats"


def test_us_total_corpus_loads_via_loader_at_45_rules():
    """Sanity: SG (14) + IN (10) + ID (8) + US (12) + 1 (in.id.exercise.resident already split into 2 in id.json) = at least 44."""
    c = Corpus.load(RULES)
    assert len(c) >= 44, f"corpus should now have ≥44 rules; got {len(c)}"
