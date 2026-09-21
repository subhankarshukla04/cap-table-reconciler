"""Fuzzy match issuer names across scraped sources.

Each issuer has a curated alias list. Scraped text is normalized then matched
against the alias set with rapidfuzz. Strict token-set ratio >= 85 wins.
"""
from __future__ import annotations

import re
from rapidfuzz import fuzz

ALIASES: dict[str, list[str]] = {
    "razorpay": ["razorpay", "razorpay software", "razorpay software private limited"],
    "acko": ["acko", "acko technology", "acko general insurance", "acko technology and services"],
    "zepto": ["zepto", "kiranakart", "kiranakart technologies"],
    "pinelabs": ["pine labs", "pinelabs", "pine labs private limited"],
    "boat": ["boat", "boat lifestyle", "imagine marketing", "boat audio"],
    "physicswallah": ["physicswallah", "physics wallah", "pw edutech", "physicswallah ltd"],
    "gotogroup": ["goto", "goto group", "gojek", "tokopedia", "goto gojek tokopedia",
                  "pt goto gojek tokopedia"],
    "carousell": ["carousell", "carousell group", "carousell pte"],
    "carro": ["carro", "carro pte", "carro singapore"],
    "ninjavan": ["ninja van", "ninjavan", "ninja logistics", "ninja logistics pte"],
    "tiki": ["tiki", "tiki vn", "tiki corporation", "tiki global"],
    "bukalapak": ["bukalapak", "pt bukalapak", "bukalapak com"],
    "souledstore": ["souled store", "the souled store", "souledstore"],
    "urbancompany": ["urban company", "urbanclap", "urban company private limited"],
    "rebelfoods": ["rebel foods", "rebelfoods", "faasos"],
}

_normalize_re = re.compile(r"[^a-z0-9 ]+")


def normalize(s: str) -> str:
    return _normalize_re.sub(" ", s.lower()).strip()


def match_issuer(text: str, threshold: int = 85) -> str | None:
    """Return issuer_id if any alias scores above threshold in `text`, else None."""
    norm = normalize(text)
    best_id: str | None = None
    best_score = 0
    for issuer_id, aliases in ALIASES.items():
        for alias in aliases:
            score = fuzz.token_set_ratio(alias, norm)
            if score > best_score:
                best_score = score
                best_id = issuer_id
    return best_id if best_score >= threshold else None
