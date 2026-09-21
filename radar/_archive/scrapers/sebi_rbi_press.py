"""SEBI + RBI press release RSS — reg_delta signals."""
from __future__ import annotations

from datetime import datetime

import feedparser

from .base import BaseScraper
from ..models import Signal

FEEDS = [
    "https://www.sebi.gov.in/sebirss.xml",
    "https://www.rbi.org.in/Scripts/Rss_Custom.aspx?Id=70",
]
KEYWORDS = (
    "private", "secondary", "fc-trs", "transfer", "unlisted",
    "preferential", "esop", "drhp", "tender",
)


class SebiRbiPressScraper(BaseScraper):
    source = "sebi_rbi_press"

    def fetch_live(self) -> list[Signal]:
        out: list[Signal] = []
        for url in FEEDS:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "").lower()
                if not any(kw in title for kw in KEYWORDS):
                    continue
                try:
                    pub = datetime(*entry.published_parsed[:6])
                except Exception:
                    pub = datetime.now()
                # Reg-deltas apply across roster; use sentinel issuer_id "_reg"
                out.append(self.make_signal(
                    issuer_id="_reg", source=self.source,
                    signal_type="reg_delta", value=entry.get("title", ""),
                    url=entry.get("link", ""),
                    raw_title=entry.get("title", ""),
                    captured_at=pub,
                ))
        return out
