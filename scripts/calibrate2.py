"""Read-only calibration, round 2 (scratch branch, never merged): the investigations' data requests. Market data and
aggregate counts only; no journal, positions or post-mortems."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg


def main() -> None:
    reqs = json.loads((Path(__file__).parent / "calib2.json").read_text())
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        for r in reqs:
            print(f"\n===== {r['id']}: {r['why'][:160]}")
            try:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute("set transaction read only")
                    cur.execute("set local statement_timeout = '90s'")
                    cur.execute(r["sql"])
                    cols = [d.name for d in cur.description or []]
                    print(" | ".join(cols))
                    for row in cur.fetchmany(80):
                        print(" | ".join("" if v is None else str(v) for v in row))
            except Exception as e:  # noqa: BLE001
                print(f"ERROR {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    main()
