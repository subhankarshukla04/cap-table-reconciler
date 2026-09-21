"""Corpus integrity tests for the India rule set."""

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

IN_PATH = Path(__file__).parent.parent / "src" / "rules" / "in.json"


@pytest.fixture(scope="module")
def in_rules() -> list[Rule]:
    raw = json.loads(IN_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


def test_in_loads_cleanly(in_rules):
    assert len(in_rules) >= 10
    for r in in_rules:
        assert r.citations, f"{r.rule_id} has no citations"


def test_in_taxing_jurisdiction_always_in(in_rules):
    for r in in_rules:
        assert r.taxing_jurisdiction == Jurisdiction.IN, (
            f"{r.rule_id} has taxing_jurisdiction={r.taxing_jurisdiction.value}, expected IN"
        )


def test_in_no_tax_at_grant_or_vest(in_rules):
    for r in in_rules:
        if r.event in (Event.GRANT, Event.VEST):
            assert r.tax_treatment == TaxTreatment.NO_TAX


def test_in_in_exercise_resident_is_perquisite(in_rules):
    rules = [r for r in in_rules
             if r.parent_jurisdiction == Jurisdiction.IN
             and r.employee_jurisdiction == Jurisdiction.IN
             and r.event == Event.EXERCISE
             and r.tax_status == TaxStatus.RESIDENT]
    assert rules, "must have IN-IN exercise resident rule"
    r = rules[0]
    assert r.tax_treatment == TaxTreatment.PERQUISITE
    assert r.withholding == "yes"
    assert "192" in " ".join(c.reference for c in r.citations) or "TDS" in r.rate_description
    assert any("rule 3(8)" in c.reference.lower() or "rule 3(8)" in (c.note or "").lower() for c in r.citations)


def test_in_in_sale_is_capital_gain(in_rules):
    rules = [r for r in in_rules
             if r.parent_jurisdiction == Jurisdiction.IN
             and r.employee_jurisdiction == Jurisdiction.IN
             and r.event == Event.SALE]
    assert rules
    assert all(r.tax_treatment == TaxTreatment.CAPITAL_GAIN for r in rules)


def test_in_sg_in_cross_border_perquisite_applies(in_rules):
    """SG-parent / IN-employee exercise: India perquisite tax still applies."""
    rules = [r for r in in_rules
             if r.parent_jurisdiction == Jurisdiction.SG
             and r.employee_jurisdiction == Jurisdiction.IN
             and r.event == Event.EXERCISE]
    assert rules
    assert rules[0].tax_treatment == TaxTreatment.PERQUISITE
    assert rules[0].withholding == "yes"


def test_in_sg_employee_no_indian_tax_on_exercise(in_rules):
    """IN-parent / SG-employee exercise: no Indian tax (employee non-resident, services in SG)."""
    rules = [r for r in in_rules
             if r.parent_jurisdiction == Jurisdiction.IN
             and r.employee_jurisdiction == Jurisdiction.SG
             and r.event == Event.EXERCISE]
    assert rules
    assert rules[0].tax_treatment == TaxTreatment.NO_TAX
    assert any("DTAA" in c.reference or "Section 9" in c.reference for c in rules[0].citations)


def test_in_dtaa_article_13_referenced_for_share_sale_by_sg_resident(in_rules):
    rules = [r for r in in_rules
             if r.parent_jurisdiction == Jurisdiction.IN
             and r.employee_jurisdiction == Jurisdiction.SG
             and r.event == Event.SALE]
    assert rules
    refs = " ".join(c.reference for c in rules[0].citations)
    assert "13" in refs or "DTAA" in refs


def test_in_corpus_loads_via_corpus_loader_with_sg():
    """End-to-end: both rule files load together; engine can resolve cross-border."""
    c = Corpus.load(IN_PATH.parent)
    assert len(c) >= 24  # 14 SG + 10 IN
    rules = c.lookup(Jurisdiction.SG, Jurisdiction.IN, Event.EXERCISE, TaxStatus.RESIDENT)
    assert len(rules) >= 2, "SG-IN exercise must have at least 2 rules (IN primary + SG secondary)"
    assert rules[0].taxing_jurisdiction == Jurisdiction.IN  # employee perspective is primary
    assert rules[1].taxing_jurisdiction == Jurisdiction.SG  # parent perspective is secondary
