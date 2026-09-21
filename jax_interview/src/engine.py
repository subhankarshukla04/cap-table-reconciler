"""Cross-product compliance engine.

Given a Query (parent jurisdiction × employee jurisdiction × event × status),
resolve to a Verdict composed of:

  - primary_rule: the employee-jurisdiction tax view (the rule whose
    taxing_jurisdiction equals the employee's jurisdiction)
  - secondary_rules: other-jurisdiction perspectives on the same query
    (typically the parent-jurisdiction view — frequently "no tax here because
    employee was never in our jurisdiction")

No LLM. Pure dict lookup + a single ordering rule (employee-perspective first).
Same inputs → same outputs forever.
"""

from __future__ import annotations

from .corpus import Corpus
from .models import (
    Citation,
    Confidence,
    Event,
    Jurisdiction,
    Query,
    Rule,
    TaxStatus,
    TaxTreatment,
    Verdict,
)


class EngineError(Exception):
    """Raised when the engine cannot resolve a query."""


def _summary_for(primary: Rule, query: Query) -> str:
    amt = query.amount_taxable()
    amt_str = ""
    if amt is not None:
        amt_str = f" Taxable amount: {amt:,.2f} (FMV × options − exercise price × options)."
    event_str = query.event.value.replace("_", " ")
    pair = f"{query.parent_jurisdiction.value} parent → {query.employee_jurisdiction.value} employee"
    return (
        f"{pair}, event = {event_str}. "
        f"Primary tax treatment ({primary.taxing_jurisdiction.value}): "
        f"{primary.tax_treatment.value.replace('_', ' ')}. "
        f"{primary.rate_description}.{amt_str}"
    )


def resolve(query: Query, corpus: Corpus) -> Verdict:
    """Resolve a query to a Verdict using the loaded corpus.

    The corpus returns all rules at the key, ordered so the
    employee-jurisdiction-perspective rule comes first. The first is the
    primary; the rest become secondaries.

    If no rule exists for the key, the engine returns a synthetic
    'requires-counsel' rule rather than guessing.
    """
    rules = corpus.lookup(
        query.parent_jurisdiction,
        query.employee_jurisdiction,
        query.event,
        query.tax_status,
    )

    if not rules:
        primary = _requires_counsel_rule(query)
        secondaries: list[Rule] = []
    else:
        primary = rules[0]
        secondaries = rules[1:]

    return Verdict(
        query=query,
        primary_rule=primary,
        secondary_rules=secondaries,
        computed_amount_taxable=query.amount_taxable(),
        summary=_summary_for(primary, query),
    )


def _requires_counsel_rule(query: Query) -> Rule:
    """Synthesize an honest 'requires-counsel' verdict for any (parent, employee, event)
    we don't have a rule for. Better than guessing."""
    return Rule(
        rule_id=(
            f"unknown."
            f"{query.parent_jurisdiction.value.lower()}."
            f"{query.employee_jurisdiction.value.lower()}."
            f"{query.event.value}"
        ),
        parent_jurisdiction=query.parent_jurisdiction,
        employee_jurisdiction=query.employee_jurisdiction,
        taxing_jurisdiction=query.employee_jurisdiction,
        event=query.event,
        tax_status=query.tax_status,
        tax_treatment=TaxTreatment.NO_TAX,
        rate_description=(
            "No rule loaded for this combination. "
            "Refer to counsel before quoting a treatment."
        ),
        withholding="conditional",
        withholding_note="Unverified — confirm with tax counsel.",
        confidence=Confidence.REQUIRES_COUNSEL,
        citations=[
            Citation(
                authority="ESOP Atlas",
                reference="No rule loaded",
                note=(
                    "This combination is not in the v1 corpus. Phase 2 work item: "
                    "add the rule with statutory citation."
                ),
            )
        ],
        caveats=[
            "No verified rule for this jurisdiction pair × event in v1.",
            "Verdict surface intentionally returns a 'requires-counsel' flag rather than guessing.",
        ],
    )
