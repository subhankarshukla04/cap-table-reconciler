"""SEBI EDIFAR-style DRHP filings index — drhp_filing signals."""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper
from ..matching import match_issuer
from ..models import Signal

URL = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15"


class SebiEdifarDrhpScraper(BaseScraper):
    source = "sebi_edifar_drhp"

    def fetch_live(self) -> list[Signal]:
        out: list[Signal] = []
        try:
            r = httpx.get(URL, timeout=20.0, headers={"User-Agent": "tender-radar/0.1"})
            if r.status_code != 200:
                return out
            tree = HTMLParser(r.text)
            rows = tree.css("tr") or []
            cutoff = datetime.now() - timedelta(days=90)
            for row in rows[:100]:
                cells = row.css("td")
                if len(cells) < 2:
                    continue
                filer_text = cells[0].text(strip=True)
                date_text = cells[-1].text(strip=True)
                try:
                    filed_at = datetime.strptime(date_text, "%d-%m-%Y")
                except ValueError:
                    continue
                if filed_at < cutoff:
                    continue
                issuer_id = match_issuer(filer_text)
                if not issuer_id:
                    continue
                link_node = row.css_first("a")
                href = link_node.attributes.get("href", "") if link_node else ""
                out.append(self.make_signal(
                    issuer_id=issuer_id, source=self.source,
                    signal_type="drhp_filing", value=date_text,
                    url=href or URL,
                    raw_title=f"DRHP filed: {filer_text} on {date_text}",
                    captured_at=filed_at,
                ))
        except Exception:
            pass
        return out
