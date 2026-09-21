"""Compliance preview — RBI floor proxy, cross-border filing volume, stamp duty.

Hardened against negative / zero / NaN inputs per BUG_REPORT.md:
- Any non-positive price or fair-value → verdict='N/A' + error_reason populated
- Stamp duty clamped to >= 0
- Cross-border filings clamped to >= 0

Fair-value proxy = last-round price-per-share. Real RBI floor needs
ICAI-method valuation. Counsel sign-off required.
"""
from __future__ import annotations

import math

from . import stamp_duty
from .models import ComplianceParams, CompliancePreview


PROXY_DISCLAIMER = (
    "Fair-value proxy: last-round price-per-share. Real RBI/SEBI "
    "floor requires ICAI-prescribed valuation. Counsel sign-off needed."
)

REQUIRED_ATTACHMENTS_INDIA = [
    "PAN (seller + buyer)",
    "FIRC (for inward remittance)",
    "Valuation certificate (ICAI-method)",
    "Board resolution approving transfer",
    "SHA / Deed of Adherence waiver",
    "Form FC-TRS (RBI)",
    "KYC bundle (seller + buyer)",
]
REQUIRED_ATTACHMENTS_SEA = [
    "Identification (seller + buyer)",
    "Share Transfer Form (per local Companies Act)",
    "Board resolution approving transfer",
    "Updated Register of Members",
    "Inward-remittance proof (per local rules)",
    "Stamp duty receipt",
    "KYC bundle",
]


def _is_invalid_price(x: float | None) -> bool:
    if x is None:
        return True
    try:
        if math.isnan(x) or math.isinf(x):
            return True
    except TypeError:
        return True
    return x <= 0


def preview_compliance(
    params: ComplianceParams,
    eligible_holders: int,
) -> CompliancePreview:
    state = params.issuer_state
    is_india = state in ("Karnataka", "Maharashtra", "Delhi")
    eligible_holders = max(0, int(eligible_holders or 0))
    error_reason = ""

    # ----- input validation -----
    if _is_invalid_price(params.transfer_price_per_share_local):
        error_reason = "Invalid transfer price (must be > 0)."
    elif _is_invalid_price(params.fair_value_proxy_local):
        error_reason = "Invalid fair-value proxy (must be > 0)."

    duty_row = stamp_duty.lookup(state)
    attachments = REQUIRED_ATTACHMENTS_INDIA if is_india else REQUIRED_ATTACHMENTS_SEA

    if error_reason:
        return CompliancePreview(
            rbi_floor_verdict="N/A",
            rbi_floor_delta_pct=0.0,
            cross_border_filings_estimated=0,
            stamp_duty_local=0.0,
            stamp_duty_rate_used=duty_row["rate"],
            state_duty_citation=duty_row["citation"],
            required_attachments=attachments,
            proxy_disclaimer=PROXY_DISCLAIMER,
            error_reason=error_reason,
        )

    # ----- RBI floor check -----
    if is_india:
        floor = params.fair_value_proxy_local
        delta = (params.transfer_price_per_share_local - floor) / floor * 100
        if delta >= 5:
            verdict = "PASS"
        elif delta >= -2:
            verdict = "MARGINAL"
        else:
            verdict = "FAIL"
    else:
        verdict, delta = "N/A", 0.0

    # ----- cross-border filings -----
    mix = params.seller_mix
    if is_india:
        cross_border_pct = (mix.nri_pct + mix.foreign_pct +
                            mix.singapore_resident_pct)
    else:
        cross_border_pct = mix.foreign_pct + mix.nri_pct
    filings = max(0, int(eligible_holders * cross_border_pct / 100))

    # ----- stamp duty (always >= 0) -----
    duty_amount = max(
        0.0,
        params.transfer_price_per_share_local
        * eligible_holders
        * 500  # avg lot size — explained in UI
        * duty_row["rate"],
    )

    return CompliancePreview(
        rbi_floor_verdict=verdict,  # type: ignore[arg-type]
        rbi_floor_delta_pct=delta,
        cross_border_filings_estimated=filings,
        stamp_duty_local=duty_amount,
        stamp_duty_rate_used=duty_row["rate"],
        state_duty_citation=duty_row["citation"],
        required_attachments=attachments,
        proxy_disclaimer=PROXY_DISCLAIMER,
        error_reason="",
    )
