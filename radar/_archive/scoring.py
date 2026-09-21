"""Scoring engine — pure functions only. No I/O.

Every score component carries: rule_id, points, rationale, signal_url.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from .models import ScoreComponent, TenderReadinessScore
from .scoring_config import BARK_THRESHOLD, MAX_SCORE, WEIGHTS


def _months_since(iso: str | None, today: date) -> float | None:
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return None
    return (today - d).days / 30.4


def score_fundraise_age(issuer: dict, today: date) -> list[ScoreComponent]:
    months = _months_since(issuer.get("last_round_date"), today)
    if months is None or months < 12:
        return []
    if 12 <= months < 18:
        rule_id = "fundraise_age_12_18"
        label = "12–18 months"
    elif 18 <= months < 36:
        rule_id = "fundraise_age_18_36"
        label = "18–36 months"
    elif 36 <= months < 60:
        rule_id = "fundraise_age_36_60"
        label = "36–60 months"
    else:
        rule_id = "fundraise_age_over_60"
        label = "60+ months"
    return [ScoreComponent(
        rule_id=rule_id,
        points=WEIGHTS[rule_id],
        rationale=f"Last round closed {months:.0f} months ago — band {label}",
        signal_url=None,
    )]


def score_price_drift(signals: Iterable[dict]) -> list[ScoreComponent]:
    out: list[ScoreComponent] = []
    for s in signals:
        if s.get("signal_type") != "price_drift":
            continue
        try:
            pct = float(s["value"])
        except (TypeError, ValueError):
            continue
        if pct >= 20:
            out.append(ScoreComponent(
                rule_id="price_drift_20plus",
                points=WEIGHTS["price_drift_20plus"],
                rationale=f"Unlisted-share price up {pct:.1f}% in last 30 days (UnlistedKart)",
                signal_url=s.get("url"),
            ))
        elif pct >= 10:
            out.append(ScoreComponent(
                rule_id="price_drift_10_20",
                points=WEIGHTS["price_drift_10_20"],
                rationale=f"Unlisted-share price up {pct:.1f}% in last 30 days (UnlistedKart)",
                signal_url=s.get("url"),
            ))
    return out


def score_drhp(signals: Iterable[dict], today: date) -> list[ScoreComponent]:
    out: list[ScoreComponent] = []
    for s in signals:
        if s.get("signal_type") != "drhp_filing":
            continue
        cap = s.get("captured_at", "")
        try:
            filed = datetime.fromisoformat(cap).date()
        except ValueError:
            continue
        if (today - filed).days <= 90:
            out.append(ScoreComponent(
                rule_id="drhp_filed_90d",
                points=WEIGHTS["drhp_filed_90d"],
                rationale=f"DRHP filed {s.get('value', filed.isoformat())} — pre-IPO secondary window opening",
                signal_url=s.get("url"),
            ))
    return out


def score_employee_pressure(signals: Iterable[dict]) -> list[ScoreComponent]:
    out: list[ScoreComponent] = []
    for s in signals:
        if s.get("signal_type") != "employee_pressure":
            continue
        try:
            count = int(s["value"])
        except (TypeError, ValueError):
            continue
        if count >= 3:
            out.append(ScoreComponent(
                rule_id="employee_pressure_3plus",
                points=WEIGHTS["employee_pressure_3plus"],
                rationale=f"{count} negative-keyword mentions in last 30d (layoffs / ESOP cliff)",
                signal_url=s.get("url"),
            ))
        elif count >= 1:
            out.append(ScoreComponent(
                rule_id="employee_pressure_1_2",
                points=WEIGHTS["employee_pressure_1_2"],
                rationale=f"{count} negative-keyword mentions in last 30d",
                signal_url=s.get("url"),
            ))
    return out


def score_employee_count(issuer: dict) -> list[ScoreComponent]:
    n = issuer.get("employee_count") or 0
    if n >= 500:
        return [ScoreComponent(
            rule_id="employee_count_500plus",
            points=WEIGHTS["employee_count_500plus"],
            rationale=f"Headcount {n:,} > 500 — material ESOP pool",
            signal_url=None,
        )]
    return []


def score_issuer(issuer: dict, signals: list[dict], today: date) -> TenderReadinessScore:
    components: list[ScoreComponent] = []
    components += score_fundraise_age(issuer, today)
    components += score_price_drift(signals)
    components += score_drhp(signals, today)
    components += score_employee_pressure(signals)
    components += score_employee_count(issuer)
    total = min(MAX_SCORE, sum(c.points for c in components))
    components.sort(key=lambda c: c.points, reverse=True)
    return TenderReadinessScore(
        issuer_id=issuer["id"],
        score=total,
        components=components,
        computed_at=datetime.now(),
    )
