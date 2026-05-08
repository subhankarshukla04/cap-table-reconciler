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

    @model_validator(mode="after")
    def share_class_names_unique(self):
        names = [sc.name for sc in self.share_classes]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate share class names: {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def preferred_seniority_unique(self):
        ranks = [
            sc.seniority_rank
            for sc in self.share_classes
            if sc.type == ShareClassType.preferred
        ]
        dupes = {r for r in ranks if ranks.count(r) > 1}
        if dupes:
            raise ValueError(
                f"duplicate seniority ranks among preferred classes: {sorted(dupes)}"
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
        """Most-senior first (rank 1)."""
        return sorted(
            [sc for sc in self.share_classes if sc.type == ShareClassType.preferred],
            key=lambda c: c.seniority_rank,
        )
