"""Corpus integrity tests for the Singapore rule set.

These tests don't validate tax-law accuracy (that's source-citation discipline
in the JSON). They validate:

  - Every SG rule loads under the pydantic schema
  - Every rule has at least one citation
  - The deemed-exercise rule applies only to non-residents
  - The cross-border SG-IN cases all resolve to "no SG tax"
  - The reverse cross-border IN-SG cases follow the IRAS overseas-parent rule
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.corpus import Corpus
from src.models import (
    Confidence,
    Event,
    Jurisdiction,
    Rule,
    TaxStatus,
    TaxTreatment,
)

SG_PATH = Path(__file__).parent.parent / "src" / "rules" / "sg.json"


@pytest.fixture(scope="module")
def sg_rules() -> list[Rule]:
    raw = json.loads(SG_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


def test_sg_loads_cleanly(sg_rules):
    assert len(sg_rules) >= 14, "expect at least 14 SG rules"
    for r in sg_rules:
        assert r.citations, f"{r.rule_id} has no citations"
        for c in r.citations:
            assert c.authority and c.reference, f"{r.rule_id} has an empty citation field"


def test_sg_taxing_jurisdiction_always_sg(sg_rules):
    """sg.json should only contain rules where Singapore is the taxing jurisdiction."""
    for r in sg_rules:
        assert r.taxing_jurisdiction == Jurisdiction.SG, (
            f"{r.rule_id} has taxing_jurisdiction={r.taxing_jurisdiction.value}, expected SG"
        )


def test_sg_sg_within_jurisdiction_event_coverage(sg_rules):
    """SG-parent / SG-employee must cover grant, vest, exercise (resident), sale, deemed_exercise."""
    sg_sg = [r for r in sg_rules
             if r.parent_jurisdiction == Jurisdiction.SG and r.employee_jurisdiction == Jurisdiction.SG]
    events = {r.event for r in sg_sg}
    assert events >= {Event.GRANT, Event.VEST, Event.EXERCISE, Event.SALE, Event.DEEMED_EXERCISE}


def test_sg_no_tax_at_grant_or_vest(sg_rules):
    """Singapore taxes only at exercise. Grant and vest should be NO_TAX universally."""
    for r in sg_rules:
        if r.event in (Event.GRANT, Event.VEST):
            assert r.tax_treatment == TaxTreatment.NO_TAX, (
                f"{r.rule_id}: SG should not tax at {r.event.value}"
            )


def test_sg_no_capital_gains_on_sale(sg_rules):
    """Singapore has no general capital gains tax."""
    for r in sg_rules:
        if r.event == Event.SALE:
            assert r.tax_treatment == TaxTreatment.NO_TAX, (
                f"{r.rule_id}: SG sale should be NO_TAX (no general CGT in SG)"
            )


def test_sg_deemed_exercise_only_non_resident(sg_rules):
    """Deemed exercise applies only to non-citizen / non-PR employees."""
    deemed = [r for r in sg_rules if r.event == Event.DEEMED_EXERCISE]
    assert deemed, "must have at least one deemed-exercise rule"
    for r in deemed:
        assert r.tax_status == TaxStatus.NON_RESIDENT, (
            f"{r.rule_id}: deemed exercise only applies to non-residents"
        )
        assert r.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME


def test_sg_in_cross_border_no_sg_tax(sg_rules):
    """SG-parent / IN-employee: all SG-perspective rules should resolve to NO_TAX
    (employee never in SG, no nexus)."""
    cross = [r for r in sg_rules
             if r.parent_jurisdiction == Jurisdiction.SG and r.employee_jurisdiction == Jurisdiction.IN]
    assert cross, "must have SG-IN rules"
    for r in cross:
        assert r.tax_treatment == TaxTreatment.NO_TAX, (
            f"{r.rule_id}: SG-perspective on SG-IN should be NO_TAX (no nexus)"
        )


def test_sg_in_sg_overseas_parent_rule_taxes_exercise(sg_rules):
    """IN-parent / SG-employee at exercise: IRAS overseas-parent rule means SG taxes."""
    rules = [r for r in sg_rules
             if r.parent_jurisdiction == Jurisdiction.IN
             and r.employee_jurisdiction == Jurisdiction.SG
             and r.event == Event.EXERCISE]
    assert rules, "must have IN-SG exercise rule"
    for r in rules:
        assert r.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME, (
            f"{r.rule_id}: IN-parent / SG-employee exercise should be employment income per IRAS"
        )


def test_sg_all_rules_confidence_firm_or_conditional(sg_rules):
    """v1 must not ship 'requires-counsel' rules in the SG corpus."""
    for r in sg_rules:
        assert r.confidence in (Confidence.FIRM, Confidence.CONDITIONAL), (
            f"{r.rule_id} has confidence={r.confidence.value}"
        )


def test_sg_corpus_load_via_corpus_loader():
    """End-to-end: the Corpus.load() entry point picks up sg.json."""
    c = Corpus.load(SG_PATH.parent)
    assert len(c) >= 14
    # Spot-check: SG-IN exercise should resolve via the loader
    rules = c.lookup(Jurisdiction.SG, Jurisdiction.IN, Event.EXERCISE, TaxStatus.RESIDENT)
    assert any(r.taxing_jurisdiction == Jurisdiction.SG for r in rules)
