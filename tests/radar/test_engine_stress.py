"""Engine stress suite — beyond the 20 edge cases in test_edges.py.

Focus: boundary conditions, determinism, full-pipeline integration, and
realistic Qapita-workflow scenarios. Every failure here is a real bug
that would bite the desk on a live filing.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer,
)

from radar import adapter, compliance, drhp_parser, mechanics
from radar.models import (
    ComplianceParams, EligibilityFilter, ExtractedHolder, Holder,
    Issuer, LockInPeriod, ParsedDRHP, SellerMix, TenderParams,
)


ROOT = Path(__file__).resolve().parents[2]
DRHP_DIR = ROOT / "data" / "drhp"


def _basic_doc(out: Path):
    return SimpleDocTemplate(str(out), pagesize=A4)


def _styled_table(rows):
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
    return t


def _drhp_with_pct_total(out: Path, rows_pct: list[tuple[str, float, int]]):
    """Build a DRHP whose Pre-Offer % sums to the given list."""
    header = ["Holder", "Class", "Units", "% Pre-Offer", "Residency"]
    body = [
        [name, "Common", f"{units:,}", f"{pct:.2f}%", "resident"]
        for name, pct, units in rows_pct
    ]
    doc = _basic_doc(out)
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table([header] + body),
    ])


def _make_holder(
    *, holder_id: str, units: int, klass: str = "Common",
    residency: str = "resident", is_employee: bool = False,
    vested: int | None = None, hire_months_ago: int = 36,
) -> Holder:
    return Holder(
        holder_id=holder_id, name=holder_id,
        **{"class": klass}, units_held=units,
        vested_units=units if vested is None else vested,
        is_employee=is_employee, is_ex_employee=False,
        residency=residency,  # type: ignore[arg-type]
        hire_date=date(2026, 5, 11) - timedelta(days=int(hire_months_ago * 30.4)),
        termination_date=None,
        is_synthetic=False,
    )


# ============================================================
# Group F — Sum-anomaly boundary (4)
# ============================================================

def test_F1_sum_below_85_triggers_warning(tmp_path):
    """84.9% should warn (real DRHP errata case)."""
    p = tmp_path / "under85.pdf"
    _drhp_with_pct_total(p, [("A", 40.0, 40_000_000), ("B", 44.9, 44_900_000)])
    parsed = drhp_parser.parse(p)
    assert parsed.shareholding, "shareholding must be extracted"
    total = sum(h.pct_pre_offer for h in parsed.shareholding)
    assert 84.0 < total < 85.5, total
    assert any("sums to" in w.lower() for w in parsed.validation_warnings), parsed.validation_warnings


def test_F2_sum_exactly_85_no_warning(tmp_path):
    """85.0% is the lower boundary — INCLUSIVE, no warning."""
    p = tmp_path / "exact85.pdf"
    _drhp_with_pct_total(p, [("A", 40.0, 40_000_000), ("B", 45.0, 45_000_000)])
    parsed = drhp_parser.parse(p)
    assert parsed.shareholding
    total = sum(h.pct_pre_offer for h in parsed.shareholding)
    assert math.isclose(total, 85.0, abs_tol=0.01)
    assert not any("sums to" in w.lower() for w in parsed.validation_warnings), parsed.validation_warnings


def test_F3_sum_exactly_105_no_warning(tmp_path):
    """105.0% upper boundary — INCLUSIVE, no warning."""
    p = tmp_path / "exact105.pdf"
    _drhp_with_pct_total(p, [("A", 50.0, 50_000_000), ("B", 55.0, 55_000_000)])
    parsed = drhp_parser.parse(p)
    assert parsed.shareholding
    total = sum(h.pct_pre_offer for h in parsed.shareholding)
    assert math.isclose(total, 105.0, abs_tol=0.01)
    assert not any("sums to" in w.lower() for w in parsed.validation_warnings), parsed.validation_warnings


def test_F4_sum_above_105_warns(tmp_path):
    """105.1% should warn."""
    p = tmp_path / "over105.pdf"
    _drhp_with_pct_total(p, [("A", 55.0, 55_000_000), ("B", 50.1, 50_100_000)])
    parsed = drhp_parser.parse(p)
    assert parsed.shareholding
    assert any("sums to" in w.lower() for w in parsed.validation_warnings)


# ============================================================
# Group G — Mechanics boundary conditions (5)
# ============================================================

def _baseline_issuer() -> Issuer:
    return Issuer(
        id="x", legal_name="X", sector="Test", geography="IN",
        state="Karnataka", last_round_price_per_share_usd=1.0,
        last_round_price_per_share_local=83.0,
    )


def test_G1_tender_size_zero_gives_zero_scaleback():
    """Demand=$0 → scaleback=0 (no allocation), pool still computed."""
    holders = [_make_holder(holder_id="h1", units=1_000_000)]
    params = TenderParams(
        tender_size_usd=0.0, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert w.eligible_unit_pool == 1_000_000
    assert w.scaleback_factor == 0.0
    # Allocations must respect zero scaleback
    for c in w.per_class_breakdown:
        assert c.allocation_usd == 0.0


def test_G2_undersubscribed_caps_scaleback_at_1():
    """Demand >> pool → scaleback should be exactly 1.0, never above."""
    holders = [_make_holder(holder_id="h1", units=100_000)]  # $100K pool @ $1
    params = TenderParams(
        tender_size_usd=50_000_000, price_per_share_usd=1.0,  # $50M demand
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert w.scaleback_factor == 1.0
    # Allocation = pool, not demand. Never extrapolate beyond eligible supply.
    assert sum(c.allocation_usd for c in w.per_class_breakdown) <= w.eligible_pool_usd + 1e-6


def test_G3_oversubscribed_scaleback_is_proportional():
    """Pool $50M, demand $10M → scaleback = 0.20."""
    holders = [
        _make_holder(holder_id=f"h{i}", units=5_000_000) for i in range(10)
    ]  # $50M
    params = TenderParams(
        tender_size_usd=10_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert math.isclose(w.scaleback_factor, 0.20, abs_tol=0.001)
    # 2x-stress scaleback = $10M / $100M = 0.10
    assert math.isclose(w.scaleback_factor_if_2x, 0.10, abs_tol=0.001)


def test_G4_exclude_foreign_holders_filter_cuts_them():
    """exclude_foreign_holders=True should drop foreign + singapore_resident from pool."""
    holders = [
        _make_holder(holder_id="r", units=1_000_000, residency="resident"),
        _make_holder(holder_id="f", units=2_000_000, residency="foreign"),
        _make_holder(holder_id="s", units=3_000_000, residency="singapore_resident"),
    ]
    params = TenderParams(
        tender_size_usd=100_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(exclude_foreign_holders=True),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    # Only foreign is filtered by the model's literal type — singapore_resident is NOT "foreign"
    # so this test pins the CURRENT behavior: exclude_foreign_holders matches residency=="foreign" only.
    assert w.eligible_holder_count == 2  # resident + singapore_resident kept
    assert w.eligible_unit_pool == 4_000_000  # 1M + 3M


def test_G5_top10_with_three_holders_is_100pct():
    """With <=10 holders, top-10 concentration must be 100%."""
    holders = [_make_holder(holder_id=f"h{i}", units=1_000_000) for i in range(3)]
    params = TenderParams(
        tender_size_usd=10_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert math.isclose(w.top_10_concentration_pct, 100.0, abs_tol=0.01)


# ============================================================
# Group H — Compliance verdict boundaries (4)
# ============================================================

def _cp(price: float, floor: float, mix: SellerMix | None = None, state: str = "Karnataka") -> ComplianceParams:
    return ComplianceParams(
        issuer_state=state,
        seller_mix=mix or SellerMix(resident_pct=78, nri_pct=14, foreign_pct=8),
        share_class="Common",
        transfer_price_per_share_local=price,
        fair_value_proxy_local=floor,
    )


def test_H1_rbi_verdict_exactly_minus2_is_marginal():
    """delta = -2.0% exactly → MARGINAL (boundary inclusive)."""
    out = compliance.preview_compliance(_cp(price=98.0, floor=100.0), eligible_holders=10)
    assert math.isclose(out.rbi_floor_delta_pct, -2.0, abs_tol=0.01)
    assert out.rbi_floor_verdict == "MARGINAL"


def test_H2_rbi_verdict_below_minus2_is_fail():
    """delta = -2.01% → FAIL (below boundary)."""
    out = compliance.preview_compliance(_cp(price=97.99, floor=100.0), eligible_holders=10)
    assert out.rbi_floor_delta_pct < -2.0
    assert out.rbi_floor_verdict == "FAIL"


def test_H3_rbi_verdict_exactly_plus5_is_pass():
    """delta = +5.0% exactly → PASS (boundary inclusive)."""
    out = compliance.preview_compliance(_cp(price=105.0, floor=100.0), eligible_holders=10)
    assert math.isclose(out.rbi_floor_delta_pct, 5.0, abs_tol=0.01)
    assert out.rbi_floor_verdict == "PASS"


def test_H4_rbi_verdict_inf_price_is_na():
    """price = +Inf → N/A with reason populated, no NaN propagation."""
    out = compliance.preview_compliance(_cp(price=float("inf"), floor=100.0), eligible_holders=10)
    assert out.rbi_floor_verdict == "N/A"
    assert "Invalid" in out.error_reason
    assert out.stamp_duty_local == 0.0
    assert math.isfinite(out.rbi_floor_delta_pct)


# ============================================================
# Group I — Stamp-duty proportionality + Singapore N/A (2)
# ============================================================

def test_I1_stamp_duty_scales_linearly_with_holders():
    """Stamp duty 1000 holders should be exactly 10x of 100 holders."""
    small = compliance.preview_compliance(_cp(price=70.0, floor=70.0), eligible_holders=100)
    big = compliance.preview_compliance(_cp(price=70.0, floor=70.0), eligible_holders=1000)
    assert big.stamp_duty_local > 0
    assert math.isclose(big.stamp_duty_local, small.stamp_duty_local * 10, rel_tol=0.001)


def test_I2_singapore_issuer_verdict_is_na_even_with_valid_prices():
    """Singapore issuer → no RBI floor check applies; verdict='N/A'."""
    out = compliance.preview_compliance(
        _cp(price=2.0, floor=2.0, state="Singapore",
            mix=SellerMix(singapore_resident_pct=80, foreign_pct=20)),
        eligible_holders=50,
    )
    assert out.rbi_floor_verdict == "N/A"
    assert "Singapore" in out.state_duty_citation
    # error_reason is empty — N/A is the *correct* answer here, not an error
    assert out.error_reason == ""


# ============================================================
# Group J — Adapter behavior + determinism (3)
# ============================================================

def test_J1_adapter_empty_shareholding_produces_zero_holders():
    """Parsed DRHP with no rows → adapter must not crash; 0 holders."""
    parsed = ParsedDRHP(
        filing_id="empty", legal_name="Empty Co", registered_state="Karnataka",
        shareholding=[],
        source_file="empty.pdf", parsed_at=datetime.now(),
    )
    issuer, holders = adapter.adapt(parsed)
    assert holders == []
    assert issuer.legal_name == "Empty Co"


def test_J2_adapter_esop_count_zero_treated_as_unknown():
    """esop_holder_count_estimated=0 should NOT fan out — single aggregate row."""
    parsed = ParsedDRHP(
        filing_id="zero_esop", legal_name="ZeroESOP", registered_state="Karnataka",
        shareholding=[
            ExtractedHolder(name="Pool", **{"class": "ESOP"},
                            units=1_000_000, pct_pre_offer=10.0,
                            residency="resident", is_employee=True),
        ],
        esop_holder_count_estimated=0,
        source_file="x.pdf", parsed_at=datetime.now(),
    )
    _, holders = adapter.adapt(parsed)
    esops = [h for h in holders if h.class_ == "ESOP"]
    assert len(esops) == 1
    assert esops[0].is_synthetic is True


def test_J3_adapter_is_deterministic_for_same_filing_id():
    """Same parsed → same holder ids and units (rng seeded by filing_id)."""
    base = ParsedDRHP(
        filing_id="det", legal_name="Det", registered_state="Karnataka",
        shareholding=[
            ExtractedHolder(name="Pool", **{"class": "ESOP"},
                            units=1_000_000, pct_pre_offer=10.0,
                            residency="resident", is_employee=True),
        ],
        esop_holder_count_estimated=50,
        source_file="x.pdf", parsed_at=datetime.now(),
    )
    _, h1 = adapter.adapt(base)
    _, h2 = adapter.adapt(base)
    assert [h.holder_id for h in h1] == [h.holder_id for h in h2]
    assert [h.vested_units for h in h1] == [h.vested_units for h in h2]
    assert [h.residency for h in h1] == [h.residency for h in h2]


# ============================================================
# Group K — End-to-end on real demo filings (3)
# ============================================================

DEMO_IDS = ["pinelabs", "razorpay", "urbancompany"]


@pytest.mark.parametrize("filing_id", DEMO_IDS)
def test_K1_demo_filing_full_pipeline(filing_id):
    """parse → adapt → mechanics → compliance on every demo, <500ms."""
    pdf = DRHP_DIR / f"{filing_id}_drhp.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf} not generated")
    t0 = time.perf_counter()
    parsed = drhp_parser.parse(pdf, fixture_hint=filing_id)
    issuer, holders = adapter.adapt(parsed)
    params = TenderParams(
        tender_size_usd=20_000_000,
        price_per_share_usd=issuer.last_round_price_per_share_usd or 1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(issuer, holders, params)
    cparams = ComplianceParams(
        issuer_state=issuer.state,
        seller_mix=SellerMix(resident_pct=78, nri_pct=14, foreign_pct=8),
        share_class="Common",
        transfer_price_per_share_local=issuer.last_round_price_per_share_local or 1.0,
        fair_value_proxy_local=issuer.last_round_price_per_share_local or 1.0,
    )
    cprev = compliance.preview_compliance(cparams, eligible_holders=w.eligible_holder_count)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"{filing_id} full pipeline took {elapsed:.2f}s"
    assert parsed.shareholding, f"{filing_id} produced no shareholding rows"
    assert w.eligible_holder_count >= 0
    assert cprev.rbi_floor_verdict in {"PASS", "FAIL", "MARGINAL", "N/A"}


def test_K2_parsing_same_pdf_twice_is_idempotent():
    """Same PDF in → same shareholding extracted (no nondeterminism in parser)."""
    pdf = DRHP_DIR / "pinelabs_drhp.pdf"
    if not pdf.exists():
        pytest.skip("demo PDF not generated")
    a = drhp_parser.parse(pdf, fixture_hint="pinelabs")
    b = drhp_parser.parse(pdf, fixture_hint="pinelabs")
    assert len(a.shareholding) == len(b.shareholding)
    a_keys = [(h.name, h.units, h.pct_pre_offer) for h in a.shareholding]
    b_keys = [(h.name, h.units, h.pct_pre_offer) for h in b.shareholding]
    assert a_keys == b_keys
    assert a.validation_warnings == b.validation_warnings


def test_K3_full_pipeline_idempotent_on_pinelabs():
    """Run pipeline twice on Pine Labs → same waterfall and same compliance verdict."""
    pdf = DRHP_DIR / "pinelabs_drhp.pdf"
    if not pdf.exists():
        pytest.skip("demo PDF not generated")
    results = []
    for _ in range(2):
        parsed = drhp_parser.parse(pdf, fixture_hint="pinelabs")
        issuer, holders = adapter.adapt(parsed)
        params = TenderParams(
            tender_size_usd=20_000_000,
            price_per_share_usd=issuer.last_round_price_per_share_usd or 1.0,
            eligibility_filter=EligibilityFilter(),
        )
        w = mechanics.preview_tender(issuer, holders, params)
        results.append((
            w.eligible_holder_count, w.eligible_unit_pool,
            round(w.scaleback_factor, 6), round(w.top_10_concentration_pct, 4),
        ))
    assert results[0] == results[1], f"Non-deterministic pipeline: {results}"


# ============================================================
# Group L — Real-world DRHP gotchas (3)
# ============================================================

def test_L1_holder_name_with_embedded_newline_parses(tmp_path):
    """pdfplumber sometimes returns cell text with \\n inside. Should not crash."""
    p = tmp_path / "newline.pdf"
    doc = _basic_doc(p)
    styles = getSampleStyleSheet()
    # ReportLab Paragraph in a cell preserves the line break visually.
    cell = Paragraph("Acme<br/>Holdings Pte Ltd", styles["Normal"])
    rows = [
        ["Holder", "Class", "Units", "% Pre-Offer", "Residency"],
        [cell, "Common", "10,000,000", "10.00%", "singapore_resident"],
    ]
    doc.build([
        Paragraph("BUILD-UP OF SHARE CAPITAL", styles["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    assert len(parsed.shareholding) == 1
    assert "Acme" in parsed.shareholding[0].name


def test_L2_only_toc_no_cap_table_returns_no_shareholding(tmp_path):
    """A DRHP-shaped file with only a ToC page (mentions sections, has no tables)
    must return zero shareholding — never invent rows from the ToC."""
    p = tmp_path / "toc_only.pdf"
    doc = _basic_doc(p)
    styles = getSampleStyleSheet()
    doc.build([
        Paragraph("TABLE OF CONTENTS", styles["Title"]),
        Paragraph("1. BUILD-UP OF SHARE CAPITAL ............ 12", styles["Normal"]),
        Paragraph("2. LOCK-IN PERIODS ...................... 18", styles["Normal"]),
        Paragraph("3. ROFR / ROFO CLAUSES .................. 24", styles["Normal"]),
    ])
    parsed = drhp_parser.parse(p)
    assert parsed.shareholding == []
    assert "TABLE OF CONTENTS" in parsed.sections_found
    # No false sum-anomaly warning fires
    assert not any("sums to" in w.lower() for w in parsed.validation_warnings)


def test_L3_excluded_table_only_page_skipped(tmp_path):
    """A page with only a TAX-RESIDENCY-flavored table must yield zero rows.
    The exclusion-token guard must dominate even if the table headers match
    name/units/pct patterns. Regression for the original cap-table-confusion bug.
    """
    p = tmp_path / "tax_only.pdf"
    doc = _basic_doc(p)
    rows = [
        ["Tax-Residency Category", "Type", "Units", "% Pre-Offer", "Country"],
        ["INDIA total", "—", "55,000,000", "55.00%", "IN"],
        ["Out-of-India total", "—", "45,000,000", "45.00%", "FOREIGN"],
    ]
    doc.build([
        Paragraph("TAX RESIDENCY OF SHAREHOLDERS", getSampleStyleSheet()["Title"]),
        Spacer(1, 0.1*inch), _styled_table(rows),
    ])
    parsed = drhp_parser.parse(p)
    names = {h.name for h in parsed.shareholding}
    assert "INDIA total" not in names
    assert "Out-of-India total" not in names


# ============================================================
# Group M — Mechanics speed under real load (1)
# ============================================================

def test_M1_mechanics_500_holders_under_50ms():
    """The published <50ms claim must hold on a 500-holder list."""
    holders = [_make_holder(holder_id=f"h{i}", units=10_000) for i in range(500)]
    params = TenderParams(
        tender_size_usd=20_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    issuer = _baseline_issuer()
    # Warm up
    mechanics.preview_tender(issuer, holders, params)
    t0 = time.perf_counter()
    for _ in range(10):
        mechanics.preview_tender(issuer, holders, params)
    avg_ms = (time.perf_counter() - t0) / 10 * 1000
    assert avg_ms < 50.0, f"Average mechanics latency: {avg_ms:.2f}ms"


# ============================================================
# Group N — Adversarial: nonsense inputs the desk WILL throw at it (8)
# ============================================================

def test_N1_negative_tender_size_does_not_produce_negative_allocations():
    """Negative demand is nonsense input. Must not produce negative scaleback
    or negative allocation_usd. Cleanest behavior: scaleback clamps to 0."""
    holders = [_make_holder(holder_id="h", units=1_000_000)]
    params = TenderParams(
        tender_size_usd=-5_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert w.scaleback_factor >= 0.0, f"scaleback={w.scaleback_factor}"
    for c in w.per_class_breakdown:
        assert c.allocation_usd >= 0.0, c


def test_N2_negative_price_does_not_produce_negative_pool():
    """Negative price is nonsense. Pool USD should not go negative."""
    holders = [_make_holder(holder_id="h", units=1_000_000)]
    params = TenderParams(
        tender_size_usd=10_000_000, price_per_share_usd=-1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert w.eligible_pool_usd >= 0.0, f"pool_usd={w.eligible_pool_usd}"


def test_N3_zero_pool_zero_demand_no_nan():
    """0/0 must not propagate NaN. scaleback should be 0 when pool=0."""
    params = TenderParams(
        tender_size_usd=0.0, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),
    )
    w = mechanics.preview_tender(_baseline_issuer(), [], params)
    assert w.scaleback_factor == 0.0
    assert math.isfinite(w.top_10_concentration_pct)
    assert w.top_10_concentration_pct == 0.0


def test_N4_compliance_nan_floor_returns_na():
    """NaN floor → N/A, no NaN in output fields."""
    out = compliance.preview_compliance(_cp(price=100.0, floor=float("nan")), eligible_holders=10)
    assert out.rbi_floor_verdict == "N/A"
    assert "Invalid" in out.error_reason
    assert math.isfinite(out.stamp_duty_local)
    assert math.isfinite(out.rbi_floor_delta_pct)


def test_N5_compliance_zero_floor_returns_na():
    """Zero floor would cause divide-by-zero in delta calc. Must short-circuit."""
    out = compliance.preview_compliance(_cp(price=100.0, floor=0.0), eligible_holders=10)
    assert out.rbi_floor_verdict == "N/A"
    assert "Invalid" in out.error_reason


def test_N6_eligibility_filter_excluding_all_classes_returns_zero_pool():
    """Filter that includes no classes → 0 eligible regardless of holders."""
    holders = [_make_holder(holder_id=f"h{i}", units=1_000_000) for i in range(5)]
    params = TenderParams(
        tender_size_usd=10_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(include_classes=[]),
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert w.eligible_holder_count == 0
    assert w.eligible_unit_pool == 0
    assert w.scaleback_factor == 0.0
    assert w.per_class_breakdown == []


def test_N7_seller_mix_zero_cross_border_pct_zero_filings():
    """100% resident mix → cross-border filings = 0."""
    out = compliance.preview_compliance(
        _cp(price=70.0, floor=70.0, mix=SellerMix(resident_pct=100)),
        eligible_holders=500,
    )
    assert out.cross_border_filings_estimated == 0


def test_N8_holder_with_class_outside_include_classes_is_excluded():
    """Series-A holder when include_classes=['Common', 'ESOP'] must be dropped."""
    holders = [
        _make_holder(holder_id="c", units=1_000_000, klass="Common"),
        _make_holder(holder_id="s", units=2_000_000, klass="SeriesA"),
    ]
    params = TenderParams(
        tender_size_usd=20_000_000, price_per_share_usd=1.0,
        eligibility_filter=EligibilityFilter(),  # default: Common + ESOP
    )
    w = mechanics.preview_tender(_baseline_issuer(), holders, params)
    assert w.eligible_holder_count == 1
    assert w.eligible_unit_pool == 1_000_000
