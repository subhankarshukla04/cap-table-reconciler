"""Corpus integrity + engine integration tests for the Indonesia rule set."""

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

ID_PATH = Path(__file__).parent.parent / "src" / "rules" / "id.json"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def id_rules() -> list[Rule]:
    raw = json.loads(ID_PATH.read_text())
    return [Rule.model_validate(r) for r in raw]


@pytest.fixture(scope="module")
def full_corpus() -> Corpus:
    return Corpus.load(RULES)


def test_id_loads_cleanly(id_rules):
    """All Indonesia rules pass schema validation and carry citations."""
    assert len(id_rules) >= 8
    for r in id_rules:
        assert r.citations, f"{r.rule_id} has no citations"
        for c in r.citations:
            assert c.authority and c.reference, f"{r.rule_id} has incomplete citation"


def test_id_taxing_jurisdictions_only_id_or_neighbor(id_rules):
    """id.json may carry rules where taxing=ID (within-ID + cross-border ID perspective)
    or taxing=SG/IN (cross-border secondary perspective from the other side)."""
    for r in id_rules:
        assert r.taxing_jurisdiction in {Jurisdiction.ID, Jurisdiction.SG, Jurisdiction.IN}


def test_id_within_jurisdiction_event_coverage(id_rules):
    """ID-ID coverage: grant, vest, exercise (resident), sale (resident) all
    present."""
    id_id = [r for r in id_rules
             if r.parent_jurisdiction == Jurisdiction.ID
             and r.employee_jurisdiction == Jurisdiction.ID]
    events = {r.event for r in id_id}
    assert events >= {Event.GRANT, Event.VEST, Event.EXERCISE, Event.SALE}


def test_id_no_tax_at_grant_or_vest(id_rules):
    """Indonesia, like SG and IN, does not tax at grant or vest."""
    for r in id_rules:
        if r.event in (Event.GRANT, Event.VEST) and r.taxing_jurisdiction == Jurisdiction.ID:
            assert r.tax_treatment == TaxTreatment.NO_TAX, (
                f"{r.rule_id}: ID should not tax at {r.event.value}"
            )


def test_id_exercise_is_employment_income_pph21(id_rules):
    """ID-ID exercise must use the PPh 21 employment-income head."""
    rules = [r for r in id_rules
             if r.parent_jurisdiction == Jurisdiction.ID
             and r.employee_jurisdiction == Jurisdiction.ID
             and r.event == Event.EXERCISE
             and r.tax_status == TaxStatus.RESIDENT]
    assert rules, "missing ID-ID exercise resident rule"
    r = rules[0]
    assert r.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert r.withholding == "yes"
    refs = " ".join(c.reference for c in r.citations)
    assert "PPh 21" in r.rate_description or "Article 21" in refs


def test_id_progressive_rates_referenced(id_rules):
    """At least one ID-perspective exercise rule must spell out the post-UU-HPP
    bracket structure explicitly (5% bottom, 35% top). Cross-border rules can
    DRY-reference the within-jurisdiction rule; only the canonical one needs
    explicit brackets."""
    canonical = [r for r in id_rules
                 if r.parent_jurisdiction == Jurisdiction.ID
                 and r.employee_jurisdiction == Jurisdiction.ID
                 and r.event == Event.EXERCISE
                 and r.tax_status == TaxStatus.RESIDENT]
    assert canonical, "missing canonical ID-ID exercise resident rule"
    rd = canonical[0].rate_description
    assert "5%" in rd, "bottom PIT bracket must be visible in canonical rule"
    assert "35%" in rd, "top PIT bracket (added by UU HPP) must be visible"


def test_id_pmk_168_supersedes_pmk_252(id_rules):
    """The current PPh 21 implementing regulation is PMK 168/2023 — not
    PMK 252/2008. Verify the corpus uses the current regulation."""
    citation_strs = []
    for r in id_rules:
        for c in r.citations:
            citation_strs.append(f"{c.authority} {c.reference}")
    blob = " ".join(citation_strs)
    assert "PMK 168" in blob or "168/PMK.03/2023" in blob
    # Negative: PMK 252 should NOT appear as a current authority — only as a
    # 'supersedes PMK 252' contextual reference.
    primary_use_252 = any(
        "PMK 252" in (c.authority or "") and "supersede" not in (c.authority or "").lower()
        for r in id_rules for c in r.citations
    )
    assert not primary_use_252, "PMK 252/2008 is superseded; do not cite as current authority"


def test_id_listed_share_sale_cites_pp_41_1994(id_rules):
    """Indonesian capital-gains rule on listed shares must cite PP 41/1994
    somewhere — authority, reference, or rate description."""
    rules = [r for r in id_rules
             if r.event == Event.SALE
             and r.taxing_jurisdiction == Jurisdiction.ID
             and r.employee_jurisdiction == Jurisdiction.ID]
    assert rules
    r = rules[0]
    blob = r.rate_description + " " + " ".join(f"{c.authority} {c.reference}" for c in r.citations)
    assert "41/1994" in blob or "PP No. 41" in blob or "PP 41" in blob


def test_id_cross_border_sg_id_exercise_has_two_rules(full_corpus):
    """SG-parent / ID-employee at exercise: corpus.lookup must return at least
    2 rules — the ID-perspective (primary) and the SG-perspective (secondary)."""
    rules = full_corpus.lookup(Jurisdiction.SG, Jurisdiction.ID, Event.EXERCISE, TaxStatus.RESIDENT)
    assert len(rules) >= 2
    taxing = {r.taxing_jurisdiction for r in rules}
    assert taxing == {Jurisdiction.ID, Jurisdiction.SG}


def test_id_cross_border_in_id_exercise_has_two_rules(full_corpus):
    """IN-parent / ID-employee at exercise: ID + IN perspectives."""
    rules = full_corpus.lookup(Jurisdiction.IN, Jurisdiction.ID, Event.EXERCISE, TaxStatus.RESIDENT)
    assert len(rules) >= 2
    taxing = {r.taxing_jurisdiction for r in rules}
    assert taxing == {Jurisdiction.ID, Jurisdiction.IN}


def test_id_engine_sg_id_exercise_perquisite_primary(full_corpus):
    """End-to-end engine resolution: SG-ID exercise yields a primary verdict
    of EMPLOYMENT_INCOME (PPh 21) from the ID perspective."""
    q = Query(
        parent_jurisdiction=Jurisdiction.SG,
        employee_jurisdiction=Jurisdiction.ID,
        event=Event.EXERCISE,
        tax_status=TaxStatus.RESIDENT,
        fmv_at_event=1.0,
        exercise_price=0.10,
        options_in_event=5000,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.ID
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert v.primary_rule.withholding == "yes"
    assert len(v.secondary_rules) >= 1
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.SG
    assert v.secondary_rules[0].tax_treatment == TaxTreatment.NO_TAX
    # Spread = (1.0 - 0.10) * 5000 = 4500
    assert v.computed_amount_taxable == pytest.approx(4500.0)
    assert v.weakest_confidence == Confidence.FIRM


def test_id_engine_unknown_jurisdiction_pair_falls_through(full_corpus):
    """ID-ID deemed-exercise has no rule in v1 (deemed exercise is SG-specific
    statute) — must fall through to requires-counsel, not silently produce
    wrong output."""
    q = Query(
        parent_jurisdiction=Jurisdiction.ID,
        employee_jurisdiction=Jurisdiction.ID,
        event=Event.DEEMED_EXERCISE,
        tax_status=TaxStatus.NON_RESIDENT,
    )
    v = resolve(q, full_corpus)
    assert v.primary_rule.confidence == Confidence.REQUIRES_COUNSEL


def test_id_every_cross_border_rule_has_caveats(id_rules):
    """All ID cross-border rules must have at least one caveat — cross-border
    tax is never trivial."""
    for r in id_rules:
        if r.parent_jurisdiction != r.employee_jurisdiction:
            assert r.caveats, f"{r.rule_id}: cross-border rule must have caveats"


def test_id_no_pre_2023_pmk_cited_as_current():
    """Sanity: no place in id.json says 'PMK 252' as the active rule."""
    raw = ID_PATH.read_text()
    # PMK 252 may appear ONLY in the context of "supersedes PMK 252"
    if "PMK 252" in raw:
        # Verify each occurrence is in a "supersede" context
        import re
        for m in re.finditer(r".{0,100}PMK 252.{0,100}", raw):
            snippet = m.group().lower()
            assert "supersede" in snippet, f"PMK 252 referenced outside 'supersedes' context: {snippet}"
