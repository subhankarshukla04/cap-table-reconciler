"""Seed radar.db from data/fixtures/."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "fixtures"


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    from radar.db import connect, init

    init()
    issuers = json.loads((FIXTURES / "issuers.json").read_text())["issuers"]

    with connect() as conn:
        conn.execute("DELETE FROM issuers")
        conn.execute("DELETE FROM holders")
        for issuer in issuers:
            issuer.pop("_design_target", None)
            conn.execute(
                "INSERT INTO issuers (id, payload) VALUES (?, ?)",
                (issuer["id"], json.dumps(issuer)),
            )
            holder_file = FIXTURES / "holders" / f"{issuer['id']}.json"
            if not holder_file.exists():
                print(f"  WARN: missing holders for {issuer['id']}")
                continue
            holders = json.loads(holder_file.read_text())["holders"]
            for h in holders:
                conn.execute(
                    "INSERT INTO holders (issuer_id, payload) VALUES (?, ?)",
                    (issuer["id"], json.dumps(h)),
                )
            print(f"  seeded {issuer['id']:18s} ({len(holders)} holders)")
        conn.commit()
    print(f"\nDB ready at {ROOT / 'data' / 'radar.db'}")


if __name__ == "__main__":
    main()
