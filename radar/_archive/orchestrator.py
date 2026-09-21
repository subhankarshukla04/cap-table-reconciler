"""End-to-end pipeline: scrape → score → render → push.

Use cache by default so the demo runs offline.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from . import db, scoring
from .scrapers.base import BaseScraper
from .scrapers.inc42_rss import Inc42RssScraper
from .scrapers.unlistedkart_html import UnlistedKartScraper
from .scrapers.sebi_edifar_drhp import SebiEdifarDrhpScraper
from .scrapers.sebi_rbi_press import SebiRbiPressScraper
from .scrapers.googlenews_employee import GoogleNewsEmployeeScraper

ALL_SCRAPERS: list[BaseScraper] = [
    Inc42RssScraper(),
    UnlistedKartScraper(),
    SebiEdifarDrhpScraper(),
    SebiRbiPressScraper(),
    GoogleNewsEmployeeScraper(),
]


def run(use_cache: bool = True, run_date: date | None = None) -> dict:
    run_date = run_date or date.today()
    started = datetime.now()
    db.init()
    # Reset signals for this run date — a fresh scrape replaces, not appends.
    with db.connect() as conn:
        conn.execute("DELETE FROM signals")
        conn.commit()

    all_signals: list = []
    for sc in ALL_SCRAPERS:
        try:
            sigs = sc.fetch(run_date=run_date, use_cache=use_cache)
            for s in sigs:
                db.upsert_signal(s.model_dump(mode="json"))
            all_signals.extend(sigs)
            print(f"  {sc.source:24s}  {len(sigs):3d} signals")
        except Exception as e:
            print(f"  {sc.source:24s}  ERROR: {e}")

    # Score every issuer using freshly-loaded signals
    issuers = db.load_issuers()
    crossings: list[tuple[str, int]] = []
    for issuer_dict in issuers:
        sigs = db.load_signals_for_issuer(issuer_dict["id"])
        s = scoring.score_issuer(issuer_dict, sigs, today=run_date)
        db.upsert_score(
            issuer_dict["id"], run_date.isoformat(),
            s.score, s.model_dump(mode="json"),
        )
        if s.score >= scoring.BARK_THRESHOLD:
            crossings.append((issuer_dict["id"], s.score))

    finished = datetime.now()
    summary = {
        "run_date": run_date.isoformat(),
        "signal_count": len(all_signals),
        "issuer_count": len(issuers),
        "crossings": crossings,
        "elapsed_s": (finished - started).total_seconds(),
    }
    print(f"\n  total signals: {summary['signal_count']}  "
          f"crossings: {len(crossings)}  elapsed: {summary['elapsed_s']:.2f}s")
    return summary


if __name__ == "__main__":
    live = "--live" in sys.argv
    run(use_cache=not live)
