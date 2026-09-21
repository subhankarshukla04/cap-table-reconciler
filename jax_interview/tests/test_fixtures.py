"""Integration tests — the three named demo fixtures must each resolve
to a fully-cited Verdict against the live SG + IN corpus."""

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
    TaxStatus,
    TaxTreatment,
)

FIXTURES = Path(__file__).parent / "fixtures"
RULES = Path(__file__).parent.parent / "src" / "rules"


@pytest.fixture(scope="module")
def live_corpus() -> Corpus:
    return Corpus.load(RULES)


def _load_query(name: str) -> Query:
    raw = json.loads((FIXTURES / f"{name}.json").read_text())
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}
    return Query.model_validate(raw)


def test_praxis_sg_parent_in_engineer_exercise(live_corpus):
    """Praxis Labs — SG parent / IN engineer / exercise. Should resolve to:
    - Primary: IN perquisite tax (TDS by Indian subsidiary)
    - Secondary: SG no_tax (employee never in SG)
    - Computed amount: (0.50 - 0.10) * 4000 = 1600
    """
    q = _load_query("praxis")
    v = resolve(q, live_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert v.primary_rule.withholding == "yes"
    assert len(v.secondary_rules) >= 1
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.SG
    assert v.secondary_rules[0].tax_treatment == TaxTreatment.NO_TAX
    assert v.computed_amount_taxable == pytest.approx(1600.0)
    assert v.weakest_confidence == Confidence.FIRM


def test_pelaut_in_parent_sg_employee_exercise(live_corpus):
    """Pelaut Maritime — IN parent / SG employee / exercise. Should resolve to:
    - Primary: SG employment_income (IRAS overseas-parent rule applies)
    - Secondary: IN no_tax (employee non-resident, services in SG, DTAA Article 15)
    - Computed amount: (4 - 2) * 20000 = 40000
    """
    q = _load_query("pelaut")
    v = resolve(q, live_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.SG
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert len(v.secondary_rules) >= 1
    assert v.secondary_rules[0].taxing_jurisdiction == Jurisdiction.IN
    assert v.secondary_rules[0].tax_treatment == TaxTreatment.NO_TAX
    assert v.computed_amount_taxable == pytest.approx(40000.0)


def test_solstice_deemed_exercise_singapore_only(live_corpus):
    """Solstice Holdings — SG parent / SG employee non-resident / deemed exercise.
    No cross-border secondary because parent == employee jurisdiction.
    """
    q = _load_query("solstice")
    v = resolve(q, live_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.SG
    assert v.primary_rule.event == Event.DEEMED_EXERCISE
    assert v.primary_rule.tax_treatment == TaxTreatment.EMPLOYMENT_INCOME
    assert v.primary_rule.withholding == "yes"
    assert any("IR21" in (d or "") for d in v.primary_rule.documents_required)
    assert v.weakest_confidence == Confidence.FIRM


def test_all_fixtures_resolve_with_firm_or_conditional(live_corpus):
    """No demo fixture should land in 'requires-counsel' territory."""
    for name in ("praxis", "pelaut", "solstice", "atlas_corp", "avalon_uk", "horizon_hk", "zenith_ae"):
        q = _load_query(name)
        v = resolve(q, live_corpus)
        assert v.weakest_confidence != Confidence.REQUIRES_COUNSEL, (
            f"Fixture {name} resolved to requires-counsel — would kill the demo"
        )


def test_atlas_corp_us_parent_in_engineer(live_corpus):
    """Atlas Corp — US parent, IN engineer, exercise.
    Primary: IN perquisite tax (TDS by Indian subsidiary)
    Secondary: US no-tax (§861 sources to where services performed)
    Computed: (4.00 - 0.50) * 8000 = 28,000
    """
    q = _load_query("atlas_corp")
    v = resolve(q, live_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert v.primary_rule.withholding == "yes"
    assert any(r.taxing_jurisdiction == Jurisdiction.US for r in v.secondary_rules)
    assert v.computed_amount_taxable == pytest.approx(28000.0)


def test_avalon_uk_parent_in_engineer(live_corpus):
    """Avalon Labs — UK parent (EMI), IN engineer, exercise.
    Primary: IN perquisite tax
    Secondary: UK no-tax (zero UK workdays)
    Computed: (1.50 - 0.20) * 5000 = 6,500
    """
    q = _load_query("avalon_uk")
    v = resolve(q, live_corpus)
    assert v.primary_rule.taxing_jurisdiction == Jurisdiction.IN
    assert v.primary_rule.tax_treatment == TaxTreatment.PERQUISITE
    assert any(r.taxing_jurisdiction == Jurisdiction.UK for r in v.secondary_rules)
    assert v.computed_amount_taxable == pytest.approx(6500.0)
