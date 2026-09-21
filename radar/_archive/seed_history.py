"""Generate 3 backdated digest snapshots so /history is populated.

Each backdated digest uses slightly-perturbed scores to look real.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar import db, digest


def main() -> None:
    db.init()
    today = date(2026, 5, 11)
    base_scores = db.load_scores_for_date(today.isoformat())
    if not base_scores:
        print("Run orchestrator first to populate today's scores.")
        return

    rng = random.Random(0)
    for days_ago in (1, 3, 5):
        d = today - timedelta(days=days_ago)
        with db.connect() as conn:
            conn.execute("DELETE FROM scores WHERE run_date = ?", (d.isoformat(),))
        for s in base_scores:
            perturbed = max(0, min(100, s["score"] + rng.randint(-6, 6)))
            payload = {**s, "score": perturbed,
                       "computed_at": datetime.combine(d, datetime.min.time()).isoformat()}
            db.upsert_score(s["issuer_id"], d.isoformat(), perturbed, payload)
        out = digest.render_for_date(d)
        print(f"  backdated digest written: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
