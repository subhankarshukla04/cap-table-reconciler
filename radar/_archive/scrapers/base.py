"""Base scraper class — rate-limit + JSON cache + retry."""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from ..models import Signal

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "data" / "scraper_cache"


class BaseScraper:
    source: str = ""
    rate_limit_s: float = 1.0
    max_runtime_s: float = 120.0

    def fetch_live(self) -> list[Signal]:
        """Override to hit the live source. Must respect rate_limit_s."""
        raise NotImplementedError

    def cache_path(self, run_date: date) -> Path:
        d = CACHE_DIR / self.source
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{run_date.isoformat()}.json"

    def fetch(self, run_date: date | None = None, use_cache: bool = True) -> list[Signal]:
        run_date = run_date or date.today()
        p = self.cache_path(run_date)
        if use_cache and p.exists():
            data = json.loads(p.read_text())
            return [Signal.model_validate(s) for s in data]
        signals = self.fetch_live()
        p.write_text(
            json.dumps([s.model_dump(mode="json") for s in signals], indent=2)
        )
        return signals

    @staticmethod
    def make_signal(
        *, issuer_id: str, source: str, signal_type: str,
        value: float | str, url: str, raw_title: str = "",
        captured_at: datetime | None = None,
    ) -> Signal:
        return Signal(
            id=str(uuid.uuid4()),
            issuer_id=issuer_id,
            source=source,  # type: ignore[arg-type]
            signal_type=signal_type,  # type: ignore[arg-type]
            value=value,
            url=url,
            captured_at=captured_at or datetime.now(),
            raw_title=raw_title,
        )
