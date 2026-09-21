"""Engine tests — verify the cross-product resolution logic.

The engine is the durable asset. Tests here are intentionally tight on shape
(structure of the Verdict) and looser on rule content (rules will grow over
Days 2–3 as the corpus is authored)."""

from __future__ import annotations

from datetime import date

import pytest

from src.corpus import Corpus
from src.engine import resolve
from src.models import (
    Citation,
    Confidence,
    Event,
    Jurisdiction,
    Query,
    Rule,
    TaxStatus,
    TaxTreatment,
)


def _make_rule(parent: Jurisdiction, employee: Jurisdiction, event: Event,
               status: TaxStatus | None, treatment: TaxTreatment,
               taxing: Jurisdiction | None = None,
               confidence: Confidence = Confidence.FIRM) -> Rule:
    """Synthesize a Rule for unit-test isolation. The real corpus is loaded
    from JSON in tests/test_rules_*."""
    taxing = taxing or employee
    rid_parts = [parent.value.lower(), employee.value.lower(), event.value, status.value if status else "any", f"tax_{taxing.value.lower()}"]
    return Rule(
        rule_id=".".join(rid_parts),
        parent_jurisdiction=parent,
        employee_jurisdiction=employee,
        taxing_jurisdiction=taxing,
        event=event,
        tax_status=status,
        tax_treatment=treatment,
        rate_description="test rate band",
        withholding="no",
        confidence=confidence,
        citations=[Citation(authority="Test", reference="Test rule")],
    )


@pytest.fixture
def synthetic_corpus() -> Corpus:
    """Build a tiny in-memory corpus for engine-only tests."""
    c = Corpus()
    rules = [
        _make_rule(Jurisdiction.SG, Jurisdiction.SG, Event.EXERCISE, TaxStatus.RESIDENT, TaxTreatment.EMPLOYMENT_INCOME),
        _make_rule(Jurisdiction.IN, Jurisdiction.IN, Event.EXERCISE, TaxStatus.RESIDENT, TaxTreatment.PERQUISITE),
        # SG-IN exercise: India-perspective (primary) + Singapore-perspective (secondary, no SG tax)
        _make_rule(Jurisdiction.SG, Jurisdiction.IN, Event.EXERCISE, TaxStatus.RESIDENT, TaxTreatment.PERQUISITE, taxing=Jurisdiction.IN),
        _make_rule(Jurisdiction.SG, Jurisdiction.IN, Event.EXERCISE, TaxStatus.RESIDENT, TaxTreatment.NO_TAX, taxing=Jurisdiction.SG),
        _make_rule(Jurisdiction.SG, Jurisdiction.SG, Event.DEEMED_EXERCISE, TaxStatus.NON_RESIDENT, TaxTreatment.EMPLOYMENT_INCOME),
    ]
    for r in rules:
        c._rules.append(r)
        key = (r.parent_jurisdiction, r.employee_jurisdiction, r.event, r.tax_status)
        c._by_key.setdefault(key, []).append(r)
    return c


def test_resolve_exact_match(synthetic_corpus):
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, synthetic_corpus)
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert v.weakest_confidence == Confidence.FIRM


def test_resolve_cross_border_attaches_sibling(synthetic_corpus):
    """For an SG-parent / IN-employee query, the engine should return:
    - primary: the India-perspective rule (taxing_jurisdiction = IN, the employee's)
    - secondary: the Singapore-perspective rule (taxing_jurisdiction = SG, "no SG tax")
    """
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, synthetic_corpus)
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert len(v.secondary_rules) == 1
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.SG
    assert v.secondary_rules[0].tax_treatment == TaxTreatment.NO_TAX


def test_resolve_unknown_returns_requires_counsel(synthetic_corpus):
    """Asking for a jurisdiction pair × event we don't have a rule for must
    return a 'requires-counsel' synthetic rule, never a guess."""
    q = Query(
        parent_jurisdiction=Jurisdiction.IN,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.SALE,
        tax_status=TaxStatus.RESIDENT,
    )
    v = resolve(q, synthetic_corpus)
    assert v.primary_rule.confidence == Confidence.REQUIRES_COUNSEL
    assert "unknown" in v.primary_rule.rule_id


def test_amount_taxable_computation():
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.IN,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        grant_date=date(2024, 1, 1),
        event_date=date(2026, 5, 1),
        fmv_at_event=0.50,
        exercise_price=0.10,
        options_in_event=4000,
    )
    # (0.50 - 0.10) * 4000 = 1600
    assert q.amount_taxable() == pytest.approx(1600.0)


def test_amount_taxable_none_for_non_exercise():
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.GRANT,
        fmv_at_event=1.00,
        exercise_price=0.10,
        options_in_event=1000,
    )
    assert q.amount_taxable() is None


def test_deemed_exercise_lookup(synthetic_corpus):
    """SG-SG deemed-exercise for a non-resident employee should resolve to
    employment income."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.SG,
        event=Event.DEEMED_EXERCISE,
        tax_status=TaxStatus.NON_RESIDENT,
    )
    v = resolve(q, synthetic_corpus)
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert v.primary_rule.confidence == Confidence.FIRM
