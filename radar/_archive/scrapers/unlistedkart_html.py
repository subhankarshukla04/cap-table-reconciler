"""UnlistedKart (now Qapita-owned) HTML scrape — unlisted-share price drift."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper
from ..models import Signal

BASE = "https://www.unlistedkart.com/buy-share"
SLUGS = {
    "razorpay": "razorpay",
    "pinelabs": "pine-labs",
    "boat": "boat-imagine-marketing",
    "physicswallah": "physicswallah",
    "rebelfoods": "rebel-foods",
    "urbancompany": "urban-company",
}


class UnlistedKartScraper(BaseScraper):
    source = "unlistedkart_html"
    rate_limit_s = 10.0

    def fetch_live(self) -> list[Signal]:
        import time
        out: list[Signal] = []
        with httpx.Client(timeout=20.0, headers={"User-Agent": "tender-radar/0.1"}) as client:
            for issuer_id, slug in SLUGS.items():
                try:
                    r = client.get(f"{BASE}/{slug}")
                    if r.status_code != 200:
                        continue
                    tree = HTMLParser(r.text)
                    price_node = tree.css_first("[class*=price], .share-price")
                    if not price_node:
                        continue
                    text = price_node.text(strip=True)
                    m = re.search(r"[\d,]+\.?\d*", text)
                    if not m:
                        continue
                    price = float(m.group().replace(",", ""))
                    # We don't have the 30-day moving average here; emit raw price.
                    # The scoring layer compares against a baseline cache.
                    out.append(self.make_signal(
                        issuer_id=issuer_id, source=self.source,
                        signal_type="price_drift", value=price,
                        url=f"{BASE}/{slug}",
                        raw_title=f"Unlisted price {issuer_id}: {text}",
                    ))
                except Exception:
                    continue
                time.sleep(self.rate_limit_s)
        return out
