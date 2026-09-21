"""Inc42 / VCCircle / YourStory RSS — fundraise-age signals.

Parses RSS titles like "Razorpay raises $X in Series F" and emits
`fundraise_age` signals (value = months-since-round).
"""
from __future__ import annotations

import re
from datetime import datetime

import feedparser

from .base import BaseScraper
from ..matching import match_issuer
from ..models import Signal

FEEDS = [
    "https://inc42.com/feed/",
    "https://yourstory.com/feed",
    "https://www.vccircle.com/rss/news",
]

ROUND_RE = re.compile(
    r"\b(?:Series\s*[A-J]\d?|seed|pre-series|pre-IPO)\b", re.IGNORECASE
)


class Inc42RssScraper(BaseScraper):
    source = "inc42_rss"

    def fetch_live(self) -> list[Signal]:
        out: list[Signal] = []
        for url in FEEDS:
            feed = feedparser.parse(url)
            for entry in feed.entries[:50]:
                title = entry.get("title", "")
                if "raise" not in title.lower() and "fund" not in title.lower():
                    continue
                if not ROUND_RE.search(title):
                    continue
                issuer_id = match_issuer(title)
                if not issuer_id:
                    continue
                try:
                    pub = datetime(*entry.published_parsed[:6])
                except Exception:
                    pub = datetime.now()
                months = (datetime.now() - pub).days / 30.4
                out.append(self.make_signal(
                    issuer_id=issuer_id, source=self.source,
                    signal_type="fundraise_age", value=months,
                    url=entry.get("link", ""),
                    raw_title=title, captured_at=datetime.now(),
                ))
        return out
