"""Flask app — DRHP Reader. Runs on :5001.

Routes:
  GET  /                            Landing + 3 demo filings
  POST /filings/upload              PDF upload, parse, redirect
  GET  /filings/<id>                Parsed cap-table + mechanics + compliance
  POST /filings/<id>/preview        HTMX slider recompute partial
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from flask import Flask, abort, redirect, render_template, request, url_for

from . import compliance, drhp_parser, mechanics, adapter
from .models import (
    EligibilityFilter, SellerMix, TenderParams, ComplianceParams,
)

ROOT = Path(__file__).resolve().parent.parent
DRHP_DIR = ROOT / "data" / "drhp"
UPLOAD_DIR = ROOT / "data" / "uploads"
PARSED_DIR = ROOT / "data" / "parsed"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)


app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB cap


DEMO_FILINGS = [
    {
        "id": "pinelabs",
        "name": "Pine Labs Limited",
        "filed": "2025-12-26",
        "amend": "Refiled 08-Apr-2026",
        "issue_cr": 2600,
        "blurb": "Fintech · Karnataka · 1,800 employees · Series I last raised 2022",
    },
    {
        "id": "razorpay",
        "name": "Razorpay Software Limited",
        "filed": "2026-04-14",
        "amend": "Original",
        "issue_cr": 5400,
        "blurb": "Fintech · Karnataka · 3,000 employees · Series F last raised Jul 2024",
    },
    {
        "id": "urbancompany",
        "name": "Urban Company Limited",
        "filed": "2025-12-15",
        "amend": "Addendum 21-Mar-2026",
        "issue_cr": 1900,
        "blurb": "Services · Delhi · 3,500 employees · Series G last raised Jun 2021",
    },
]


def _parsed_path(filing_id: str) -> Path:
    return PARSED_DIR / f"{filing_id}.json"


def _save_parsed(parsed) -> None:
    _parsed_path(parsed.filing_id).write_text(
        parsed.model_dump_json(indent=2)
    )


def _load_parsed(filing_id: str):
    from .models import ParsedDRHP
    p = _parsed_path(filing_id)
    if not p.exists():
        return None
    return ParsedDRHP.model_validate_json(p.read_text())


@app.route("/")
def landing():
    filings = list(DEMO_FILINGS)
    # add any user-uploaded filings
    extras = []
    for f in sorted(PARSED_DIR.glob("*.json")):
        fid = f.stem
        if fid in {d["id"] for d in DEMO_FILINGS}:
            continue
        try:
            parsed = _load_parsed(fid)
            if parsed:
                extras.append({
                    "id": fid,
                    "name": parsed.legal_name,
                    "filed": parsed.filing_date.isoformat() if parsed.filing_date else "—",
                    "amend": parsed.filing_type,
                    "issue_cr": parsed.issue_size_inr_cr or "—",
                    "blurb": f"User-uploaded · parsed {parsed.pages_processed} pages",
                })
        except Exception:
            continue
    return render_template("landing.html.j2", filings=filings, extras=extras)


@app.route("/filings/upload", methods=["POST"])
def upload():
    f = request.files.get("pdf")
    if not f or not f.filename.lower().endswith(".pdf"):
        abort(400, "PDF required")
    filing_id = uuid.uuid4().hex[:10]
    out = UPLOAD_DIR / f"{filing_id}.pdf"
    f.save(out)
    parsed = drhp_parser.parse(out, fixture_hint=None)
    parsed.filing_id = filing_id
    _save_parsed(parsed)
    return redirect(url_for("filing", filing_id=filing_id))


@app.route("/filings/<filing_id>")
def filing(filing_id: str):
    parsed = _load_parsed(filing_id)
    if not parsed:
        # First-time access of a demo filing → parse on demand
        demo = next((d for d in DEMO_FILINGS if d["id"] == filing_id), None)
        if not demo:
            abort(404)
        pdf_path = DRHP_DIR / f"{filing_id}_drhp.pdf"
        if not pdf_path.exists():
            abort(404, "Demo PDF missing")
        parsed = drhp_parser.parse(pdf_path, fixture_hint=filing_id)
        _save_parsed(parsed)

    issuer, holders = adapter.adapt(parsed)
    params = TenderParams(
        tender_size_usd=20_000_000,
        price_per_share_usd=issuer.last_round_price_per_share_usd or 1.0,
        eligibility_filter=EligibilityFilter(),
    )
    waterfall = mechanics.preview_tender(issuer, holders, params)

    mix = _default_seller_mix(issuer)
    cparams = ComplianceParams(
        issuer_state=issuer.state,
        seller_mix=mix,
        share_class="Common",
        transfer_price_per_share_local=issuer.last_round_price_per_share_local or 1.0,
        fair_value_proxy_local=issuer.last_round_price_per_share_local or 1.0,
    )
    cprev = compliance.preview_compliance(
        cparams, eligible_holders=waterfall.eligible_holder_count
    )

    return render_template(
        "filing.html.j2",
        parsed=parsed,
        issuer=issuer,
        params=params,
        waterfall=waterfall,
        compliance=cprev,
        holder_count=len(holders),
        synthetic_count=sum(1 for h in holders if h.is_synthetic),
    )


@app.route("/filings/<filing_id>/preview", methods=["POST"])
def filing_preview(filing_id: str):
    parsed = _load_parsed(filing_id)
    if not parsed:
        abort(404)
    issuer, holders = adapter.adapt(parsed)
    try:
        tender_size = float(request.form.get("tender_size_usd", 20_000_000))
        price = float(request.form.get(
            "price_per_share_usd", issuer.last_round_price_per_share_usd or 1.0
        ))
    except (TypeError, ValueError):
        abort(400)
    params = TenderParams(
        tender_size_usd=tender_size,
        price_per_share_usd=price,
        eligibility_filter=EligibilityFilter(),
    )
    waterfall = mechanics.preview_tender(issuer, holders, params)

    price_local = (
        price * (issuer.last_round_price_per_share_local /
                 issuer.last_round_price_per_share_usd)
        if issuer.last_round_price_per_share_usd else price
    )
    cparams = ComplianceParams(
        issuer_state=issuer.state,
        seller_mix=_default_seller_mix(issuer),
        share_class="Common",
        transfer_price_per_share_local=price_local,
        fair_value_proxy_local=issuer.last_round_price_per_share_local or 1.0,
    )
    cprev = compliance.preview_compliance(
        cparams, eligible_holders=waterfall.eligible_holder_count
    )
    return render_template(
        "_preview.html.j2",
        waterfall=waterfall, compliance=cprev, params=params,
    )


def _default_seller_mix(issuer):
    if issuer.geography == "IN":
        return SellerMix(resident_pct=78, nri_pct=14, foreign_pct=8)
    if issuer.geography == "SEA":
        return SellerMix(
            singapore_resident_pct=45, sea_resident_pct=35,
            foreign_pct=12, nri_pct=8,
        )
    return SellerMix(resident_pct=55, nri_pct=18, foreign_pct=15)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
