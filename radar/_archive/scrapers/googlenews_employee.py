"""Google News RSS — employee_pressure signals (layoffs / ESOP / attrition)."""
from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

import feedparser

from .base import BaseScraper
from ..matching import ALIASES
from ..models import Signal

QUERY_TPL = "{name} (layoffs OR ESOP OR attrition OR \"hiring freeze\" OR resign)"
NEGATIVE_KEYWORDS = (
    "layoff", "layoffs", "fire", "fires", "attrition", "resign",
    "exit", "exodus", "hiring freeze", "freeze hiring", "cliff",
)


class GoogleNewsEmployeeScraper(BaseScraper):
    source = "googlenews_employee"

    def fetch_live(self) -> list[Signal]:
        out: list[Signal] = []
        cutoff = datetime.now() - timedelta(days=30)
        for issuer_id, aliases in ALIASES.items():
            name = aliases[0]
            q = quote(QUERY_TPL.format(name=name))
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:20]:
                title = entry.get("title", "").lower()
                if not any(kw in title for kw in NEGATIVE_KEYWORDS):
                    continue
                try:
                    pub = datetime(*entry.published_parsed[:6])
                except Exception:
                    pub = datetime.now()
                if pub < cutoff:
                    continue
                count += 1
            if count > 0:
                out.append(self.make_signal(
                    issuer_id=issuer_id, source=self.source,
                    signal_type="employee_pressure", value=count,
                    url=f"https://news.google.com/rss/search?q={q}",
                    raw_title=f"{count} negative-keyword mentions for {name} in last 30d",
                ))
        return out
