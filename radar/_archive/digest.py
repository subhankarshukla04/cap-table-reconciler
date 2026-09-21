"""Render the morning digest to a flat HTML file under data/digests/."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import render_template

from . import db
from .app import app

ROOT = Path(__file__).resolve().parent.parent
DIGESTS_DIR = ROOT / "data" / "digests"


def render_for_date(run_date: date) -> Path:
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    scores = db.load_scores_for_date(run_date.isoformat())
    issuers_by_id = {i["id"]: i for i in db.load_issuers()}
    top_10 = [
        {"score": s, "issuer": issuers_by_id.get(s["issuer_id"], {})}
        for s in scores[:10]
    ]
    reg = [s for s in db.load_all_signals() if s.get("signal_type") == "reg_delta"][:3]

    with app.test_request_context():
        html = render_template(
            "digest.html.j2",
            run_date=run_date.isoformat(),
            top_10=top_10,
            reg_signals=reg,
            score_count=len(scores),
        )

    out = DIGESTS_DIR / f"{run_date.isoformat()}.html"
    out.write_text(html)
    return out
