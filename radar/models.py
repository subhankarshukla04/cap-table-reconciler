"""Pydantic v2 models for Tender Radar.

Pure data classes. No I/O, no DB. Imported by engines, scrapers, templates.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


Geography = Literal["IN", "SEA", "Cross"]
Residency = Literal["resident", "nri", "foreign", "singapore_resident", "sea_resident"]
SignalSource = Literal[
    "inc42_rss", "unlistedkart_html", "sebi_edifar_drhp",
    "sebi_rbi_press", "googlenews_employee",
]
SignalType = Literal[
    "fundraise_age", "price_drift", "drhp_filing",
    "reg_delta", "employee_pressure",
]


class Issuer(BaseModel):
    id: str
    legal_name: str
    sector: str
    geography: Geography
    state: str
    employee_count: Optional[int] = None
    founded_year: Optional[int] = None
    last_round_amount_usd: Optional[float] = None
    last_round_date: Optional[date] = None
    last_round_price_per_share_usd: Optional[float] = None
    last_round_price_per_share_local: Optional[float] = None
    drhp_filed_date: Optional[date] = None


class Holder(BaseModel):
    holder_id: str
    name: str
    class_: str = Field(..., alias="class")
    units_held: int
    vested_units: int
    is_employee: bool
    is_ex_employee: bool
    residency: Residency
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    is_synthetic: bool = False  # True when DRHP didn't disclose per-holder detail

    model_config = {"populate_by_name": True}


class Signal(BaseModel):
    id: str
    issuer_id: str
    source: SignalSource
    signal_type: SignalType
    value: float | str
    url: str
    captured_at: datetime
    raw_title: str = ""


class ScoreComponent(BaseModel):
    rule_id: str
    points: int
    rationale: str
    signal_url: Optional[str] = None


class TenderReadinessScore(BaseModel):
    issuer_id: str
    score: int
    components: list[ScoreComponent]
    computed_at: datetime


class EligibilityFilter(BaseModel):
    include_vested_esops: bool = True
    include_ex_employees_within_months: Optional[int] = 12
    include_classes: list[str] = Field(default_factory=lambda: ["Common", "ESOP"])
    min_vesting_months: int = 12
    exclude_foreign_holders: bool = False


class TenderParams(BaseModel):
    tender_size_usd: float
    price_per_share_usd: float
    eligibility_filter: EligibilityFilter


class ClassAllocation(BaseModel):
    class_name: str
    eligible_holders: int
    eligible_units: int
    allocation_usd: float


class WaterfallPreview(BaseModel):
    eligible_holder_count: int
    eligible_unit_pool: int
    eligible_pool_usd: float
    scaleback_factor: float
    scaleback_factor_if_2x: float
    top_10_concentration_pct: float
    per_class_breakdown: list[ClassAllocation]


class SellerMix(BaseModel):
    resident_pct: float = 0.0
    nri_pct: float = 0.0
    foreign_pct: float = 0.0
    singapore_resident_pct: float = 0.0
    sea_resident_pct: float = 0.0


class ComplianceParams(BaseModel):
    issuer_state: str
    seller_mix: SellerMix
    share_class: str = "Common"
    transfer_price_per_share_local: float
    fair_value_proxy_local: float


class CompliancePreview(BaseModel):
    rbi_floor_verdict: Literal["PASS", "FAIL", "MARGINAL", "N/A"]
    rbi_floor_delta_pct: float
    cross_border_filings_estimated: int
    stamp_duty_local: float
    stamp_duty_rate_used: float
    state_duty_citation: str
    required_attachments: list[str]
    proxy_disclaimer: str
    error_reason: str = ""


class ExtractedHolder(BaseModel):
    """A holder extracted from a DRHP table row."""
    name: str
    class_: str = Field(..., alias="class")
    units: int
    pct_pre_offer: float
    residency: Residency = "resident"
    is_employee: bool = False
    model_config = {"populate_by_name": True}


class LockInPeriod(BaseModel):
    category: str
    duration_months: int


class ParsedDRHP(BaseModel):
    """A DRHP/RHP parsed from PDF. Captures the cap-table-relevant sections."""
    filing_id: str
    legal_name: str
    registered_state: str
    founded_year: Optional[int] = None
    filing_date: Optional[date] = None
    filing_type: str = "DRHP"
    employee_count: Optional[int] = None
    issue_size_inr_cr: Optional[float] = None
    fresh_issue_inr_cr: Optional[float] = None
    ofs_inr_cr: Optional[float] = None
    last_round_inr_per_share: Optional[float] = None
    capital_structure_summary: str = ""
    shareholding: list[ExtractedHolder] = Field(default_factory=list)
    esop_pool_pct: Optional[float] = None
    esop_holder_count_estimated: Optional[int] = None
    foreign_holder_pct: Optional[float] = None
    lock_in_periods: list[LockInPeriod] = Field(default_factory=list)
    rofr_clause_summary: str = ""
    risk_factors_count_extracted: Optional[int] = None
    source_file: str
    parsed_at: datetime
    sections_found: list[str] = Field(default_factory=list)
    pages_processed: int = 0
    validation_warnings: list[str] = Field(default_factory=list)


class DigestRun(BaseModel):
    run_date: date
    top_10_issuer_ids: list[str]
    alerts_fired: list[str]
    fresh_signal_count: int
    started_at: datetime
    finished_at: datetime
