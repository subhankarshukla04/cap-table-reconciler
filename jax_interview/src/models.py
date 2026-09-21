"""Pydantic models for the ESOP Atlas rule engine.

Three core concepts:

- Query: what the BD person inputs in the call (jurisdictions, event, status).
- Rule: a single statutory rule, loaded from the per-jurisdiction JSON corpus.
- Verdict: the structured answer the engine returns for a Query — composed of
  one or more Rules selected by the engine.

Citations are first-class. Every Rule carries a Citation; the Verdict displays
the full citation chain. A Rule with no Citation cannot be loaded — the
corpus validator rejects it.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Jurisdiction(str, Enum):
    SG = "SG"
    IN = "IN"
    ID = "ID"
    US = "US"
    UK = "UK"
    HK = "HK"
    AE = "AE"


class Event(str, Enum):
    GRANT = "grant"
    VEST = "vest"
    EXERCISE = "exercise"
    SALE = "sale"
    DEEMED_EXERCISE = "deemed_exercise"


class TaxStatus(str, Enum):
    RESIDENT = "resident"
    NON_RESIDENT = "non_resident"


class Confidence(str, Enum):
    FIRM = "firm"
    CONDITIONAL = "conditional"
    REQUIRES_COUNSEL = "requires_counsel"


class TaxTreatment(str, Enum):
    EMPLOYMENT_INCOME = "employment_income"
    CAPITAL_GAIN = "capital_gain"
    NO_TAX = "no_tax"
    PERQUISITE = "perquisite"


class Citation(BaseModel):
    """A statutory citation. Required on every Rule."""

    authority: str = Field(..., description="e.g., 'IRAS', 'Income Tax Act 1961', 'CBDT'")
    reference: str = Field(..., description="e.g., 'Section 17(2)(vi)', 'e-Tax Guide para 4.3'")
    source_url: str | None = Field(None, description="Primary source URL")
    retrieved_on: date | None = Field(None, description="Date the rule was last verified against source")
    note: str | None = Field(None, description="Free text — context if the citation needs one")

    @field_validator("reference")
    @classmethod
    def _reference_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("citation reference must be non-empty")
        return v


class Rule(BaseModel):
    """A single rule keyed by (parent, employee, event, status) tuple.

    The `taxing_jurisdiction` field identifies WHICH jurisdiction's tax law
    this rule expresses. For a cross-border query like SG-parent / IN-employee,
    both files contribute a rule at the same key — in.json contributes the
    India-tax rule (taxing_jurisdiction=IN, the primary) and sg.json
    contributes the Singapore-perspective rule (taxing_jurisdiction=SG, a
    secondary that often resolves to NO_TAX with an "employee not in SG"
    explanation)."""

    rule_id: str = Field(..., description="Stable ID, e.g., 'sg.sg.exercise.resident'")
    parent_jurisdiction: Jurisdiction
    employee_jurisdiction: Jurisdiction
    taxing_jurisdiction: Jurisdiction = Field(
        ..., description="The jurisdiction whose tax law this rule expresses"
    )
    event: Event
    tax_status: TaxStatus | None = Field(
        None, description="None means rule applies regardless of residency status"
    )

    tax_treatment: TaxTreatment
    rate_description: str = Field(..., description="Human-readable rate or rate band")
    withholding: Literal["yes", "no", "conditional"] = "no"
    withholding_note: str | None = None

    filing_requirement: str | None = Field(
        None, description="Form name + deadline, e.g., 'Form 12BA + Form 16 (annual)'"
    )
    documents_required: list[str] = Field(default_factory=list)

    confidence: Confidence
    citations: list[Citation] = Field(..., min_length=1, description="At least one citation required")
    caveats: list[str] = Field(default_factory=list)

    @field_validator("rule_id")
    @classmethod
    def _rule_id_format(cls, v: str) -> str:
        if not v or "." not in v:
            raise ValueError("rule_id must be dotted, e.g., 'sg.sg.exercise.resident'")
        return v

    def model_post_init(self, __context):  # pydantic v2 hook
        if self.taxing_jurisdiction not in (self.parent_jurisdiction, self.employee_jurisdiction):
            raise ValueError(
                f"taxing_jurisdiction ({self.taxing_jurisdiction}) must equal either "
                f"parent_jurisdiction ({self.parent_jurisdiction}) or "
                f"employee_jurisdiction ({self.employee_jurisdiction})"
            )


class Query(BaseModel):
    """What the BD person inputs in the call."""

    parent_jurisdiction: Jurisdiction
    employee_jurisdiction: Jurisdiction
    event: Event
    tax_status: TaxStatus = TaxStatus.RESIDENT
    grant_date: date | None = None
    vesting_date: date | None = None
    event_date: date | None = None
    fmv_at_event: float | None = Field(None, ge=0, description="FMV at event; must be ≥ 0")
    exercise_price: float | None = Field(None, ge=0, description="Exercise price; must be ≥ 0")
    options_in_event: int | None = Field(None, ge=0, description="Options in event; must be ≥ 0")

    def amount_taxable(self) -> float | None:
        """For exercise events: (FMV - exercise price) * options. None if inputs missing.
        Can be negative if exercise price exceeds FMV (down-round exercise)."""
        if self.event != Event.EXERCISE:
            return None
        if self.fmv_at_event is None or self.exercise_price is None or self.options_in_event is None:
            return None
        return (self.fmv_at_event - self.exercise_price) * self.options_in_event


class Verdict(BaseModel):
    """Structured answer returned by the engine for a Query."""

    query: Query
    primary_rule: Rule
    secondary_rules: list[Rule] = Field(
        default_factory=list,
        description="Other-jurisdiction rules that apply to the same query "
                    "(e.g., the home-country rule when the event is taxed cross-border)",
    )
    computed_amount_taxable: float | None = None
    summary: str = Field(..., description="One-paragraph plain-language summary of the verdict")

    @property
    def all_citations(self) -> list[Citation]:
        out = list(self.primary_rule.citations)
        for r in self.secondary_rules:
            out.extend(r.citations)
        return out

    @property
    def weakest_confidence(self) -> Confidence:
        """The lowest confidence across all rules in the verdict."""
        order = {Confidence.FIRM: 0, Confidence.CONDITIONAL: 1, Confidence.REQUIRES_COUNSEL: 2}
        rules = [self.primary_rule, *self.secondary_rules]
        return max(rules, key=lambda r: order[r.confidence]).confidence
