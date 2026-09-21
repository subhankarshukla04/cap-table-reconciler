"""Corpus integrity + engine integration tests for the Hong Kong rule set."""

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

HK_PATH = Path(__file__).parent.parent / "src" / "rules" / "hk.json"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def hk_rules() -> list[Rule]:
    raw = json.loads(HK_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


@pytest.fixture(scope="module")
def full_corpus() -> Corpus:
    return Corpus.load(RULES)


def test_hk_loads_cleanly(hk_rules):
    assert len(hk_rules) >= 10
    for r in hk_rules:
        assert r.citations, f"{r.rule_id} has no citations"


def test_hk_taxing_jurisdiction_always_hk(hk_rules):
    for r in hk_rules:
        assert r.taxing_jurisdiction == Jurisdiction.HK, (
            f"{r.rule_id} has taxing={r.taxing_jurisdiction.value}, expected HK"
        )


def test_hk_within_jurisdiction_event_coverage(hk_rules):
    """HK-HK must cover grant, vest, exercise (resident + non_resident), deemed_exercise, sale."""
    hk_hk = [r for r in hk_rules
             if r.parent_jurisdiction == Jurisdiction.HK
             and r.employee_jurisdiction == Jurisdiction.HK]
    events = {r.event for r in hk_hk}
    assert events >= {Event.GRANT, Event.VEST, Event.EXERCISE, Event.SALE, Event.DEEMED_EXERCISE}


def test_hk_no_tax_at_grant_vest_and_sale(hk_rules):
    """HK: no tax at grant, no tax at vest (options), no CGT on sale."""
    for r in hk_rules:
        if r.event in (Event.GRANT, Event.VEST, Event.SALE) and \
                r.parent_jurisdiction == Jurisdiction.HK and \
                r.employee_jurisdiction == Jurisdiction.HK:
            assert r.tax_treatment == TaxTreatment.NO_TAX, (
                f"{r.rule_id} should be NO_TAX, got {r.tax_treatment}"
            )


def test_hk_exercise_cites_iro_section_9(hk_rules):
    """HK-HK exercise must cite IRO s.9(1)(d) or s.9(4)."""
    canonical = [r for r in hk_rules
                 if r.parent_jurisdiction == Jurisdiction.HK
                 and r.employee_jurisdiction == Jurisdiction.HK
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    blob = " ".join(f"{c.authority} {c.reference}" for c in canonical[0].citations)
    assert "9(1)(d)" in blob or "9(4)" in blob


def test_hk_exercise_cites_dipn38(hk_rules):
    """HK exercise rule must cite DIPN 38."""
    canonical = [r for r in hk_rules
                 if r.parent_jurisdiction == Jurisdiction.HK
                 and r.employee_jurisdiction == Jurisdiction.HK
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical
    blob = " ".join(f"{c.authority} {c.reference}" for c in canonical[0].citations)
    assert "DIPN 38" in blob or "dipn38" in blob.lower()


def test_hk_non_resident_60_day_rule(hk_rules):
    """HK non-resident exercise rule must mention the 60-day rule / time apportionment."""
    rules = [r for r in hk_rules
             if r.event == Event.EXERCISE
             and r.tax_status == TaxStatus.NON_RESIDENT
             and r.parent_jurisdiction == Jurisdiction.HK
             and r.employee_jurisdiction == Jurisdiction.HK]
    assert rules
    blob = rules[0].rate_description + " " + " ".join(rules[0].caveats)
    assert "60" in blob
    assert "apportion" in blob.lower() or "time-basis" in blob.lower() or "time basis" in blob.lower()


def test_hk_deemed_exercise_cites_ir56g(hk_rules):
    """HK deemed-exercise rule must reference IR56G."""
    rules = [r for r in hk_rules
             if r.event == Event.DEEMED_EXERCISE
             and r.parent_jurisdiction == Jurisdiction.HK
             and r.employee_jurisdiction == Jurisdiction.HK]
    assert rules
    blob = (rules[0].rate_description + " " +
            " ".join(d or "" for d in rules[0].documents_required) + " " +
            " ".join(rules[0].caveats) + " " +
            " ".join(f"{c.authority} {c.reference}" for c in rules[0].citations))
    assert "IR56G" in blob


def test_hk_sale_explains_no_cgt(hk_rules):
    """HK-HK sale must explain no capital gains tax."""
    rules = [r for r in hk_rules
             if r.event == Event.SALE
             and r.parent_jurisdiction == Jurisdiction.HK
             and r.employee_jurisdiction == Jurisdiction.HK]
    assert rules
    rd = rules[0].rate_description
    assert "no capital gains" in rd.lower() or "no cgt" in rd.lower()


def test_hk_every_cross_border_rule_has_caveats(hk_rules):
    for r in hk_rules:
        if r.parent_jurisdiction != r.employee_jurisdiction:
            assert r.caveats, f"{r.rule_id}: cross-border rule lacks caveats"


def test_hk_engine_hk_hk_exercise_resident(full_corpus):
    """HK-HK exercise resolves to HK Salaries Tax."""
    q = Query(
        parent_jurisdiction=Jurisdiction.HK,
        employee_jurisdiction=Jurisdiction.HK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=10.0,
        exercise_price=1.0,
        options_in_event=2000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.HK
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert v.computed_amount_taxable == pytest.approx(18000.0)
    assert v.secondary_rules == []


def test_hk_engine_hk_in_cross_border(full_corpus):
    """HK parent, IN employee: IN perquisite primary, HK no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.HK,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=3.0,
        exercise_price=0.30,
        options_in_event=6000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert any(r.taxing_jurisdiction == Jurisdiction.HK for r in v.secondary_rules)
    assert v.computed_amount_taxable == pytest.approx(16200.0)


def test_hk_engine_in_hk_cross_border(full_corpus):
    """IN parent, HK employee: HK Salaries Tax primary, IN no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.HK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=5.0,
        exercise_price=1.0,
        options_in_event=3000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.HK
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.IN for r in v.secondary_rules)
    assert v.computed_amount_taxable == pytest.approx(12000.0)


def test_hk_engine_hk_sg_cross_border(full_corpus):
    """HK parent, SG employee: SG employment_income primary, HK no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.HK,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=8.0,
        exercise_price=2.0,
        options_in_event=1000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.SG
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.HK for r in v.secondary_rules)


def test_hk_engine_sg_hk_cross_border(full_corpus):
    """SG parent, HK employee: HK Salaries Tax primary, SG no-tax secondary."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.HK,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=12.0,
        exercise_price=3.0,
        options_in_event=500,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.HK
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert any(r.taxing_jurisdiction == Jurisdiction.SG for r in v.secondary_rules)


def test_hk_deemed_exercise_resolves_to_employment_income(full_corpus):
    """HK-HK deemed_exercise (departure) resolves to employment income."""
    q = Query(
        parent_jurisdiction=Jurisdiction.HK,
        employee_jurisdiction=Jurisdiction.HK,
        event=Event.DEEMED_EXERCISE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.HK
    assert v.primary_rule.event == Event.DEEMED_EXERCISE
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME


def test_total_corpus_size_after_6_jurisdictions():
    """Sanity: 6 jurisdictions (SG, IN, ID, US, UK, HK), corpus ≥ 70 rules."""
    c = Corpus.load(RULES)
    assert len(c) >= 70, f"corpus size {len(c)} below threshold"
