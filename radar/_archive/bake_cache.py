"""Bake realistic cached scraper outputs for offline demo.

Crafts signals such that:
- razorpay, pinelabs, urbancompany, gotogroup score high (>80) on demo day
- zepto, carro, souledstore score low (<30)
- the rest fall in between, producing a believable ranking spread
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "scraper_cache"
TODAY = date(2026, 5, 11)


def mk(issuer_id: str, source: str, signal_type: str, value, url: str,
       title: str, days_ago: int = 0) -> dict:
    captured = datetime(TODAY.year, TODAY.month, TODAY.day) - timedelta(days=days_ago)
    return {
        "id": str(uuid.uuid4()),
        "issuer_id": issuer_id,
        "source": source,
        "signal_type": signal_type,
        "value": value,
        "url": url,
        "captured_at": captured.isoformat(),
        "raw_title": title,
    }


def bake_inc42() -> None:
    # months-since-last-round
    rows = [
        ("razorpay", 22.0, "Razorpay Series F closed July 2024 — sources",
         "https://inc42.com/buzz/razorpay-series-f/", 30),
        ("acko", 43.0, "Acko Series D from October 2022",
         "https://inc42.com/buzz/acko-series-d/", 60),
        ("zepto", 6.0, "Zepto closes fresh Series F at $5bn valuation",
         "https://inc42.com/buzz/zepto-series-f/", 5),
        ("pinelabs", 48.0, "Pine Labs Series I — 2022 round",
         "https://inc42.com/buzz/pinelabs-series-i/", 90),
        ("boat", 64.0, "boAt last raised in Series B in Jan 2021",
         "https://inc42.com/buzz/boat-series-b/", 120),
        ("physicswallah", 41.0, "PhysicsWallah Series A 2022",
         "https://inc42.com/buzz/pw-series-a/", 80),
        ("gotogroup", 49.0, "GoTo last fundraise April 2022",
         "https://inc42.com/buzz/goto-fundraise/", 100),
        ("carousell", 56.0, "Carousell Sep 2021 round revisited",
         "https://inc42.com/buzz/carousell-2021/", 90),
        ("carro", 20.0, "Carro Series C Sep 2024",
         "https://inc42.com/buzz/carro-series-c/", 7),
        ("ninjavan", 56.0, "Ninja Van Sep 2021 megaround now 4 years old",
         "https://inc42.com/buzz/ninja-van-update/", 60),
        ("tiki", 55.0, "Tiki 2021 round — exit signals",
         "https://inc42.com/buzz/tiki-vietnam/", 75),
        ("bukalapak", 65.0, "Bukalapak post-IPO dynamics",
         "https://inc42.com/buzz/bukalapak-2026/", 110),
        ("souledstore", 11.0, "Souled Store Series C Jun 2024",
         "https://inc42.com/buzz/souled-store-c/", 12),
        ("urbancompany", 59.0, "Urban Company last round Jun 2021",
         "https://inc42.com/buzz/urban-company-2021/", 95),
        ("rebelfoods", 55.0, "Rebel Foods Series F Oct 2021",
         "https://inc42.com/buzz/rebel-foods-f/", 65),
    ]
    (CACHE / "inc42_rss").mkdir(parents=True, exist_ok=True)
    out = [mk(iid, "inc42_rss", "fundraise_age", val, url, title, days)
           for iid, val, title, url, days in rows]
    (CACHE / "inc42_rss" / f"{TODAY.isoformat()}.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"  inc42_rss             {len(out):3d} signals baked")


def bake_unlistedkart() -> None:
    rows = [
        ("razorpay", 24.0, "Razorpay unlisted +24% MoM (₹82.40 → ₹102.00)", 2),
        ("pinelabs", 18.5, "Pine Labs unlisted +18.5% MoM", 2),
        ("urbancompany", 22.0, "Urban Company unlisted +22% MoM", 1),
        ("boat", 4.0, "boAt unlisted +4% MoM", 3),
        ("physicswallah", 11.0, "PhysicsWallah unlisted +11% MoM", 1),
        ("rebelfoods", 12.5, "Rebel Foods unlisted +12.5% MoM", 1),
    ]
    (CACHE / "unlistedkart_html").mkdir(parents=True, exist_ok=True)
    out = [mk(iid, "unlistedkart_html", "price_drift", val,
              f"https://www.unlistedkart.com/buy-share/{iid}",
              title, days) for iid, val, title, days in rows]
    (CACHE / "unlistedkart_html" / f"{TODAY.isoformat()}.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"  unlistedkart_html     {len(out):3d} signals baked")


def bake_drhp() -> None:
    # Pine Labs originally filed Dec 2025; refiled with updated financials Apr 2026.
    # Urban Company same pattern — addendum filed Mar 2026.
    rows = [
        ("razorpay", "14-04-2026", "DRHP filed: Razorpay Software Private Limited", 27),
        ("pinelabs", "08-04-2026", "DRHP refiled (updated financials): Pine Labs Private Limited", 33),
        ("urbancompany", "21-03-2026", "DRHP addendum filed: Urban Company Private Limited", 51),
    ]
    (CACHE / "sebi_edifar_drhp").mkdir(parents=True, exist_ok=True)
    out = [mk(iid, "sebi_edifar_drhp", "drhp_filing", val,
              "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15",
              title, days) for iid, val, title, days in rows]
    (CACHE / "sebi_edifar_drhp" / f"{TODAY.isoformat()}.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"  sebi_edifar_drhp      {len(out):3d} signals baked")


def bake_sebi_rbi() -> None:
    rows = [
        ("_reg", "SEBI: Consultation paper on private secondary transfers", 4,
         "https://www.sebi.gov.in/reports-and-statistics/reports/may-2026/consultation-paper-private-secondary.html"),
        ("_reg", "RBI: Updated Master Direction on FC-TRS reporting", 9,
         "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12500"),
        ("_reg", "MCA: Circular on share transfer for unlisted public companies", 15,
         "https://www.mca.gov.in/content/mca/global/en/notifications/2026/may.html"),
    ]
    (CACHE / "sebi_rbi_press").mkdir(parents=True, exist_ok=True)
    out = [mk(iid, "sebi_rbi_press", "reg_delta", title, url, title, days)
           for iid, title, days, url in rows]
    (CACHE / "sebi_rbi_press" / f"{TODAY.isoformat()}.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"  sebi_rbi_press        {len(out):3d} signals baked")


def bake_googlenews() -> None:
    rows = [
        ("razorpay", 3, "3 ESOP-cliff mentions for Razorpay in 30d"),
        ("pinelabs", 2, "2 attrition mentions for Pine Labs in 30d"),
        ("boat", 4, "4 layoff mentions for boAt in 30d"),
        ("physicswallah", 5, "5 layoff mentions for PhysicsWallah in 30d"),
        ("gotogroup", 6, "6 layoff mentions for GoTo Group in 30d"),
        ("tiki", 4, "4 attrition mentions for Tiki in 30d"),
        ("bukalapak", 3, "3 hiring-freeze mentions for Bukalapak"),
        ("rebelfoods", 2, "2 ESOP-cliff mentions for Rebel Foods"),
    ]
    (CACHE / "googlenews_employee").mkdir(parents=True, exist_ok=True)
    out = [mk(iid, "googlenews_employee", "employee_pressure", val,
              f"https://news.google.com/search?q={iid}+layoffs",
              title, 1) for iid, val, title in rows]
    (CACHE / "googlenews_employee" / f"{TODAY.isoformat()}.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"  googlenews_employee   {len(out):3d} signals baked")


def main() -> None:
    bake_inc42()
    bake_unlistedkart()
    bake_drhp()
    bake_sebi_rbi()
    bake_googlenews()
    print(f"\nCache baked at {CACHE} for run-date {TODAY}")


if __name__ == "__main__":
    main()
