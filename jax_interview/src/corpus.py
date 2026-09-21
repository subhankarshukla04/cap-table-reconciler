"""Rule corpus loader.

Loads per-jurisdiction JSON files from src/rules/, validates each rule against
the pydantic schema, and indexes them by (parent, employee, event, status) key.
A rule with no citation fails to load — surfaced at app start, not in production.

For cross-border queries the same key may have *multiple* rules — one per
taxing_jurisdiction perspective. lookup() returns them all; the engine decides
which is primary based on `taxing_jurisdiction == employee_jurisdiction`.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Event, Jurisdiction, Rule, TaxStatus

RULES_DIR = Path(__file__).parent / "rules"


class CorpusError(Exception):
    """Raised when a rule file is malformed or missing required fields."""


class Corpus:
    """In-memory index of all loaded rules."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []
        self._by_key: dict[tuple, list[Rule]] = {}

    @classmethod
    def load(cls, rules_dir: Path = RULES_DIR) -> Corpus:
        c = cls()
        if not rules_dir.exists():
            return c
        for path in sorted(rules_dir.glob("*.json")):
            c._load_file(path)
        return c

    def _load_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise CorpusError(f"{path.name}: invalid JSON — {e}") from e
        if not isinstance(data, list):
            raise CorpusError(f"{path.name}: top level must be a list of rules")
        for i, raw in enumerate(data):
            try:
                rule = Rule.model_validate(raw)
            except Exception as e:
                raise CorpusError(f"{path.name}[{i}]: rule failed validation — {e}") from e
            self._rules.append(rule)
            key = (rule.parent_jurisdiction, rule.employee_jurisdiction, rule.event, rule.tax_status)
            self._by_key.setdefault(key, []).append(rule)

    def lookup(
        self,
        parent: Jurisdiction,
        employee: Jurisdiction,
        event: Event,
        status: TaxStatus,
    ) -> list[Rule]:
        """Return all rules for the (parent, employee, event, status) tuple,
        falling back to status-agnostic rules (tax_status=None) when no exact
        match exists. Result is sorted so the employee-perspective rule comes
        first (so the engine can treat it as primary).
        """
        rules = list(self._by_key.get((parent, employee, event, status), []))
        rules.extend(self._by_key.get((parent, employee, event, None), []))
        # Deduplicate (a status-None rule can leak in twice if both keys hit)
        seen = set()
        unique: list[Rule] = []
        for r in rules:
            if r.rule_id not in seen:
                seen.add(r.rule_id)
                unique.append(r)
        # Sort: employee-perspective first, then parent-perspective
        unique.sort(key=lambda r: 0 if r.taxing_jurisdiction == employee else 1)
        return unique

    @property
    def all_rules(self) -> list[Rule]:
        return list(self._rules)

    def __len__(self) -> int:
        return len(self._rules)
