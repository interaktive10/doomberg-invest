#!/usr/bin/env python3
"""F-PX stand-ins (BRIEF §9): weekly CSVs in Stooq's exact format (Date,Open,High,Low,Close,Volume) for 10 symbols.

stooq.com resets connections from the build container (TLS reset through the egress proxy, 2026-09-25), so these
are synthetic series with fixed seeds, not real prices. `scripts/fetch_fixtures.py f-px` replaces them with the real
files where Stooq is reachable (docs/SPEC_ISSUES.md). Tests use them for parsing and ingestion only. One series
(jbl.us) carries an unadjusted 2:1 split in week 150 for the split tests; ^spx has no volume column, like Stooq's
index files."""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent
SYMBOLS = {"aapl.us": 150.0, "msft.us": 300.0, "nvda.us": 90.0, "cat.us": 250.0, "orcl.us": 110.0,
           "pwr.us": 200.0, "jbl.us": 120.0, "gev.us": 180.0, "xlk.us": 180.0, "^spx": 4500.0}  # fmt: skip
WEEKS = 260
LAST = date(2026, 9, 18)


def series(symbol: str, start: float) -> str:
    rnd = random.Random(f"f-px:{symbol}")
    rows, price = [], start
    for i in range(WEEKS):
        day = LAST - timedelta(weeks=WEEKS - 1 - i)
        if i % 26 == 25:
            day -= timedelta(days=1)  # a holiday week ends on Thursday, as Stooq dates it
        price *= 1 + rnd.gauss(0.002, 0.03)
        if symbol == "jbl.us" and i == 150:
            price /= 2  # an unadjusted 2:1 split
        o, h, low = price * 0.99, price * 1.02, price * 0.97
        vol = "" if symbol.startswith("^") else f",{rnd.randint(1_000_000, 90_000_000)}"
        rows.append(f"{day.isoformat()},{o:.2f},{h:.2f},{low:.2f},{price:.2f}{vol}")
    header = "Date,Open,High,Low,Close" + ("" if symbol.startswith("^") else ",Volume")
    return "\n".join([header, *rows]) + "\n"


def main() -> None:
    for sym, start in SYMBOLS.items():
        (OUT / f"{sym.replace('^', '_')}_w.csv").write_text(series(sym, start), encoding="utf-8")
    (OUT / "no_data.txt").write_text("No data", encoding="utf-8")
    (OUT / "limit.txt").write_text("Exceeded the daily hits limit", encoding="utf-8")


if __name__ == "__main__":
    main()
