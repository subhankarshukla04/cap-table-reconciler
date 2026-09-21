"""Corpus integrity + engine integration tests for the UAE rule set."""

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

AE_PATH = Path(__file__).parent.parent / "src" / "rules" / "ae.json"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def ae_rules() -> list[Rule]:
    raw = json.loads(AE_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


@pytest.fixture(scope="module")
def full_corpus() -> Corpus:
    return Corpus.load(RULES)


def test_ae_loads_cleanly(ae_rules):
    assert len(ae_rules) >= 6
    for r in ae_rules:
        assert r.citations, f"{r.rule_id} has no citations"


def test_ae_taxing_jurisdiction_always_ae(ae_rules):
    for r in ae_rules:
        assert r.taxing_jurisdiction == Jurisdiction.AE, (
            f"{r.rule_id} has taxing={r.taxing_jurisdiction.value}, expected AE"
        )


def test_ae_all_events_no_tax_for_individuals(ae_rules):
    """UAE: no personal income tax — every AE-perspective rule should be NO_TAX."""
    for r in ae_rules:
        assert r.tax_treatment == TaxTreatment.NO_TAX, (
            f"{r.rule_id} should be NO_TAX (UAE has no personal income tax), got {r.tax_treatment}"
        )


def test_ae_self_event_coverage(ae_rules):
    """AE-AE must cover grant, vest, exercise, sale."""
    ae_ae = [r for r in ae_rules
             if r.parent_jurisdiction == Jurisdiction.AE
             and r.employee_jurisdiction == Jurisdiction.AE]
    events = {r.event for r in ae_ae}
    assert events >= {Event.GRANT, Event.VEST, Event.EXERCISE, Event.SALE}


def test_ae_cites_federal_decree_law_47(ae_rules):
    """At least one AE rule must cite Federal Decree-Law 47 of 2022."""
    any_cite = False
    for r in ae_rules:
        blob = " ".join(f"{c.authority} {c.reference}" for c in r.citations)
        if "47 of 2022" in blob or "Decree-Law No. 47" in blob:
            any_cite = True
            break
    assert any_cite, "Expected at least one citation to Federal Decree-Law No. 47 of 2022"


def test_ae_article_11_6_carve_out_referenced(ae_rules):
    """The Article 11(6) personal-income carve-out from Corporate Tax must be cited."""
    found = False
    for r in ae_rules:
        blob = " ".join(f"{c.authority} {c.reference}" for c in r.citations)
        if "11(6)" in blob or "Article 11" in blob:
            found = True
            break
    assert found, "Expected at least one rule to cite Article 11(6) of FDL 47/2022"


def test_ae_every_cross_border_rule_has_caveats(ae_rules):
    for r in ae_rules:
        if r.parent_jurisdiction != r.employee_jurisdiction:
            assert r.caveats, f"{r.rule_id}: cross-border rule lacks caveats"


def test_ae_engine_ae_ae_exercise(full_corpus):
    """AE-AE exercise: no UAE tax, no withholding."""
    q = Query(
        parent_jurisdiction=Jurisdiction.AE,
        employee_jurisdiction=Jurisdiction.AE,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=10.0,
        exercise_price=1.0,
        options_in_event=5000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.AE
    assert v.primary_rule.tax_treatment == TaxTreatment.NO_TAX
    assert v.primary_rule.withholding == "no"
    # Even though no tax, the calculator still computes the gain (for accounting / parent IFRS 2)
    assert v.computed_amount_taxable == pytest.approx(45000.0)


def test_ae_engine_ae_ae_sale_no_cgt(full_corpus):
    """AE-AE sale: no capital gains tax."""
    q = Query(
        parent_jurisdiction=Jurisdiction.AE,
        employee_jurisdiction=Jurisdiction.AE,
        event=Event.SALE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.AE
    assert v.primary_rule.tax_treatment == TaxTreatment.NO_TAX


def test_ae_engine_ae_in_cross_border(full_corpus):
    """AE parent, IN employee: IN perquisite primary, AE no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.AE,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=2.5,
        exercise_price=0.25,
        options_in_event=10000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert any(r.taxing_jurisdiction == Jurisdiction.AE for r in v.secondary_rules)
    assert v.computed_amount_taxable == pytest.approx(22500.0)


def test_ae_engine_in_ae_cross_border(full_corpus):
    """IN parent, AE employee: AE no_tax primary, IN no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.AE,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=8.0,
        exercise_price=2.0,
        options_in_event=2000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.AE
    assert v.primary_rule.tax_treatment == TaxTreatment.NO_TAX
    # IN side also no-tax (UAE-resident, services outside India)
    assert any(r.taxing_jurisdiction == Jurisdiction.IN for r in v.secondary_rules)


def test_ae_engine_ae_sg_cross_border(full_corpus):
    """AE parent, SG employee: SG employment_income primary, AE no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.AE,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=5.0,
        exercise_price=1.0,
        options_in_event=3000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.SG
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.AE for r in v.secondary_rules)


def test_total_corpus_size_after_7_jurisdictions():
    """Sanity: 7 jurisdictions (SG, IN, ID, US, UK, HK, AE), corpus ≥ 80 rules."""
    c = Corpus.load(RULES)
    assert len(c) >= 80, f"corpus size {len(c)} below threshold"
