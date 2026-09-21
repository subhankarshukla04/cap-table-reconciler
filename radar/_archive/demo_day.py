"""End-to-end: run pipeline, render today's digest, fire Bark alerts.

Use --live to hit live scrapers; otherwise reads from cached JSON fixtures.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from radar import bark, db, digest, orchestrator
from radar.scoring_config import BARK_THRESHOLD


def main() -> None:
    live = "--live" in sys.argv
    today = date(2026, 5, 11)  # demo-frozen
    summary = orchestrator.run(use_cache=not live, run_date=today)
    out = digest.render_for_date(today)
    print(f"\n  digest written: {out.relative_to(ROOT)}")

    issuers_by_id = {i["id"]: i for i in db.load_issuers()}
    scores = db.load_scores_for_date(today.isoformat())
    for s in scores:
        if s["score"] < BARK_THRESHOLD:
            continue
        issuer = issuers_by_id.get(s["issuer_id"], {})
        trigger = s["components"][0]["rationale"] if s.get("components") else ""
        bark.send_alert(
            issuer_id=s["issuer_id"],
            issuer_name=issuer.get("legal_name", s["issuer_id"]),
            score=s["score"],
            top_trigger=trigger,
        )
    print(f"\n  open http://localhost:5001/ to view digest")


if __name__ == "__main__":
    main()
