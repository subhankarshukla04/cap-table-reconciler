"""
Pydantic data model for the Cap Table Reconciler.

Captures share classes, liquidation preferences (with participation variants),
anti-dilution, side letters, SAFEs, warrants, and convertible notes. The model
is the single source of truth shared across the parser, checklist, waterfall,
and exporters.

Design notes:
- Currency is metadata at the company level (USD, INR, SGD, etc.). Amounts are
  stored as floats in the company's home currency. The waterfall is currency-
  agnostic; the formatter handles symbol display.
- Liquidation preferences are stored as both `multiple` and absolute `amount`.
  The parser fills in whichever is present; validators ensure consistency.
- Option pools are split: `option_pool_granted` participates in the waterfall;
  `option_pool_reserved` is excluded per market practice (only granted options
  share in liquidation proceeds).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ShareClassType(str, Enum):
    common = "common"
    preferred = "preferred"
    option_pool_granted = "option_pool_granted"
    option_pool_reserved = "option_pool_reserved"


class LPType(str, Enum):
    non_participating = "non_participating"
    participating_uncapped = "participating_uncapped"
    participating_capped = "participating_capped"


class AntiDilutionVariant(str, Enum):
    broad_based_weighted_average = "broad_based_weighted_average"
    narrow_based_weighted_average = "narrow_based_weighted_average"
    full_ratchet = "full_ratchet"


class ParticipationMode(str, Enum):
    none_ = "none"
    with_cap = "with_cap"
    without_cap = "without_cap"


class LiquidationPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    multiple: float = Field(..., ge=0)
    amount: float = Field(..., ge=0)
    type: LPType
    cap_multiple: Optional[float] = Field(None, ge=0)
    cap_amount: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def cap_required_when_capped(self):
        if self.type == LPType.participating_capped:
            if self.cap_multiple is None and self.cap_amount is None:
                raise ValueError(
                    "participating_capped LP must specify cap_multiple or cap_amount"
                )
            if self.cap_multiple is not None and self.cap_amount is not None:
                raise ValueError(
                    "participating_capped LP must specify exactly one of "
                    "cap_multiple or cap_amount, not both — they may disagree"
                )
            if self.cap_multiple is not None and self.cap_multiple < 1.0:
                raise ValueError(
                    "participating_capped LP cap_multiple must be >= 1.0 "
                    "(cap below LP is contradictory; the LP itself violates the cap)"
                )
            if self.cap_amount is not None and self.cap_amount < self.amount:
                raise ValueError(
                    "participating_capped LP cap_amount must be >= LP amount "
                    "(cap below LP is contradictory)"
                )
        return self


class AntiDilution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: Optional[AntiDilutionVariant] = None
    notes: Optional[str] = None


class Participation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ParticipationMode = ParticipationMode.none_
    cap_multiple_of_lp: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class ShareClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: ShareClassType
    shares_outstanding: int = Field(..., ge=0)
    issue_price: Optional[float] = Field(None, ge=0)
    issue_date: Optional[date] = None
    seniority_rank: int = Field(99, ge=1, le=99)
    # Pari-passu sub-rank. Two preferred classes with the same seniority_rank
    # but different seniority_sub_rank share a pari-passu group (common in SEA
    # B-1 / B-2 same-day closes). Default 0 keeps legacy CapTables valid.
    seniority_sub_rank: int = Field(0, ge=0, le=99)
    liquidation_preference: Optional[LiquidationPreference] = None
    anti_dilution: Optional[AntiDilution] = None
    conversion_ratio: Optional[float] = Field(None, ge=0)
    participation: Optional[Participation] = None
    instrument_subtype: Optional[str] = None
    voting_differential: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def preferred_must_have_lp(self):
        if self.type == ShareClassType.preferred and self.liquidation_preference is None:
            raise ValueError(
                f"preferred share class '{self.name}' must have a liquidation_preference"
            )
        if self.type in (ShareClassType.common, ShareClassType.option_pool_granted, ShareClassType.option_pool_reserved):
            if self.liquidation_preference is not None:
                raise ValueError(
                    f"non-preferred share class '{self.name}' must not have a liquidation_preference"
                )
        return self

    @property
    def is_common_pool_member(self) -> bool:
        """Whether this class contributes to the common-pool sharing residual after LPs (when not converted)."""
        return self.type in (
            ShareClassType.common,
            ShareClassType.option_pool_granted,
        )

    @property
    def excluded_from_waterfall(self) -> bool:
        """Reserved (unallocated) option pool is excluded from waterfall per market practice."""
        return self.type == ShareClassType.option_pool_reserved


class ProtectiveProvision(BaseModel):
    """One protective-provision entry (NVCA Model Charter §6).

    Tracked as a structured list on CapTable so rules can query it
    (closes GAP-14). Examples:
      - "amend_charter" requiring majority of preferred
      - "issue_senior_security" requiring 67% of preferred
      - "incur_indebtedness_above" with threshold_value
    """

    model_config = ConfigDict(extra="forbid")

    name: str  # short identifier, e.g. "amend_charter"
    description: Optional[str] = None
    consent_threshold_pct: Optional[float] = Field(None, ge=0, le=100)
    consenting_class_names: list[str] = Field(default_factory=list)
    threshold_value: Optional[float] = None  # for amount-bound provisions


class ROFRTerms(BaseModel):
    """ROFR/ROFO terms (closes GAP-14 partially)."""

    model_config = ConfigDict(extra="forbid")

    notice_period_days: Optional[int] = Field(None, ge=0)
    applies_to_transfers_above: Optional[float] = Field(None, ge=0)
    excluded_transfer_types: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class DragAlongTerms(BaseModel):
    """Drag-along terms (closes GAP-14 partially)."""

    model_config = ConfigDict(extra="forbid")

    threshold_pct: Optional[float] = Field(None, ge=0, le=100)
    drag_classes: list[str] = Field(default_factory=list)
    minimum_consideration_per_share: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class SideLetter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    summary: Optional[str] = None
    body: Optional[str] = None
    unresolved_questions: list[str] = Field(default_factory=list)


class SAFE(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    principal: float = Field(..., ge=0)
    valuation_cap: Optional[float] = Field(None, ge=0)
    discount_rate: Optional[float] = Field(None, ge=0, le=1)
    issue_date: Optional[date] = None
    conversion_trigger_threshold: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class Warrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    holder: str
    shares: int = Field(..., ge=0)
    share_class: str
    strike_price: float = Field(..., ge=0)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


class ConvertibleNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    principal: float = Field(..., ge=0)
    valuation_cap: Optional[float] = Field(None, ge=0)
    discount_rate: Optional[float] = Field(None, ge=0, le=1)
    interest_rate: Optional[float] = Field(None, ge=0, le=1)
    issue_date: Optional[date] = None
    qualified_financing_threshold: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class Company(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    jurisdiction: Optional[str] = None
    sector: Optional[str] = None
    stage: Optional[str] = None
    valuation_date: Optional[date] = None
    currency: str = "USD"
    currency_symbol: str = "$"
    summary: Optional[str] = None


class CapTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: Company
    share_classes: list[ShareClass] = Field(default_factory=list)
    side_letters: list[SideLetter] = Field(default_factory=list)
    safes_outstanding: list[SAFE] = Field(default_factory=list)
    warrants_outstanding: list[Warrant] = Field(default_factory=list)
    convertible_notes_outstanding: list[ConvertibleNote] = Field(default_factory=list)
    # W3.6 / GAP-14 closure: structured fields the rule pack can query
    # against rather than scraping side-letter body text. Optional —
    # legacy CapTable JSONs that omit these still validate.
    protective_provisions: list[ProtectiveProvision] = Field(default_factory=list)
    rofr_terms: Optional[ROFRTerms] = None
    drag_along_terms: Optional[DragAlongTerms] = None

    @model_validator(mode="after")
    def share_class_names_unique(self):
        names = [sc.name for sc in self.share_classes]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate share class names: {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def preferred_seniority_tier_unique(self):
        """Reject duplicate (rank, sub_rank) tuples. Same rank is OK if
        sub_rank differs — that's pari-passu."""
        tiers = [
            (sc.seniority_rank, sc.seniority_sub_rank)
            for sc in self.share_classes
            if sc.type == ShareClassType.preferred
        ]
        dupes = {t for t in tiers if tiers.count(t) > 1}
        if dupes:
            raise ValueError(
                f"duplicate (seniority_rank, seniority_sub_rank) tuples among "
                f"preferred classes: {sorted(dupes)}. Two pari-passu classes "
                f"must share seniority_rank but differ in seniority_sub_rank."
            )
        return self

    @model_validator(mode="after")
    def pari_passu_groups_homogeneous_lp(self):
        """GAP-21: refuse pari-passu groups that mix LP types. Within a single
        seniority rank, the LP type (non_participating / participating_*) must
        agree so the marginal-allocation math is well-defined."""
        groups: dict[int, list[str]] = {}
        types: dict[int, set[str]] = {}
        for sc in self.share_classes:
            if sc.type != ShareClassType.preferred or sc.liquidation_preference is None:
                continue
            groups.setdefault(sc.seniority_rank, []).append(sc.name)
            types.setdefault(sc.seniority_rank, set()).add(sc.liquidation_preference.type.value)
        for rank, type_set in types.items():
            if len(type_set) > 1:
                names = sorted(groups[rank])
                raise ValueError(
                    f"pari-passu group at seniority_rank={rank} mixes LP types "
                    f"({sorted(type_set)}) across classes {names}. Mixed-LP "
                    f"pari-passu is unsupported; either split into distinct "
                    f"ranks or harmonise the LP type."
                )
        return self

    @field_validator("share_classes")
    @classmethod
    def at_least_one_class(cls, v: list[ShareClass]) -> list[ShareClass]:
        if not v:
            raise ValueError("cap table must have at least one share class")
        return v

    @property
    def total_fully_diluted_for_waterfall(self) -> int:
        return sum(
            sc.shares_outstanding
            for sc in self.share_classes
            if not sc.excluded_from_waterfall
        )

    @property
    def preferred_classes_by_seniority(self) -> list[ShareClass]:
        """Most-senior first (rank 1). Pari-passu classes share a rank;
        within-rank order is by sub_rank then by name (deterministic)."""
        return sorted(
            [sc for sc in self.share_classes if sc.type == ShareClassType.preferred],
            key=lambda c: (c.seniority_rank, c.seniority_sub_rank, c.name),
        )

    @property
    def preferred_seniority_groups(self) -> list[list[ShareClass]]:
        """List of pari-passu groups, most-senior first. Each group is one
        list[ShareClass]; a non-pari-passu rank is a one-element group."""
        groups: dict[int, list[ShareClass]] = {}
        for sc in self.preferred_classes_by_seniority:
            groups.setdefault(sc.seniority_rank, []).append(sc)
        return [groups[r] for r in sorted(groups.keys())]
