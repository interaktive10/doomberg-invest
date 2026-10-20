#!/usr/bin/env python3
"""F-PX stand-ins (BRIEF §9): weekly CSVs in the manual price import's format (Date,Open,High,Low,Close,Volume, the
format Stooq's weekly CSV had; pipeline/prices/bars.py) for 10 symbols.

These are synthetic series with fixed seeds, not real prices: the build container reaches no price source, and the one
the pipeline asks, Twelve Data, needs a key. Tests use them for parsing and ingestion only. One series (jbl.us) carries
an unadjusted 2:1 split in week 150 for the split tests; ^spx has no volume column, like an index file.

twelvedata/ holds them as Twelve Data's time_series answers them (interval=1week; the weekly run asks it since 2026-10,
docs/SPEC_ISSUES.md 38): newest first, each bar dated at its week's Monday, prices as decimal strings; the ^spx series
stands in for SPY, which the client asks for the S&P 500."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent
SYMBOLS = {"aapl.us": 150.0, "msft.us": 300.0, "nvda.us": 90.0, "cat.us": 250.0, "orcl.us": 110.0,
           "pwr.us": 200.0, "jbl.us": 120.0, "gev.us": 180.0, "xlk.us": 180.0, "^spx": 4500.0}  # fmt: skip
WEEKS = 260
LAST = date(2026, 9, 18)
TWELVEDATA_SYMBOL = {"^spx": "SPY"}


def series(symbol: str, start: float) -> str:
    rnd = random.Random(f"f-px:{symbol}")
    rows, price = [], start
    for i in range(WEEKS):
        day = LAST - timedelta(weeks=WEEKS - 1 - i)
        if i % 26 == 25:
            day -= timedelta(days=1)  # a holiday week ends on Thursday, dated at its last trading day
        move = rnd.gauss(0.002, 0.03)
        if symbol == "jbl.us" and i == 150:
            price /= 2  # an unadjusted 2:1 split, exactly half the week before (no market move on top)
        else:
            price *= 1 + move
        o, h, low = price * 0.99, price * 1.02, price * 0.97
        vol = "" if symbol.startswith("^") else f",{rnd.randint(1_000_000, 90_000_000)}"
        rows.append(f"{day.isoformat()},{o:.2f},{h:.2f},{low:.2f},{price:.2f}{vol}")
    header = "Date,Open,High,Low,Close" + ("" if symbol.startswith("^") else ",Volume")
    return "\n".join([header, *rows]) + "\n"


def series_json(symbol: str, csv_text: str) -> str:
    tsym = TWELVEDATA_SYMBOL.get(symbol, symbol.removesuffix(".us").upper())
    values = []
    for r in reversed([line.split(",") for line in csv_text.splitlines()[1:]]):
        day = date.fromisoformat(r[0])
        v = {"datetime": (day - timedelta(days=day.weekday())).isoformat(), "open": f"{float(r[1]):.5f}",
             "high": f"{float(r[2]):.5f}", "low": f"{float(r[3]):.5f}", "close": f"{float(r[4]):.5f}"}  # fmt: skip
        if len(r) > 5:
            v["volume"] = r[5]
        values.append(v)
    meta = {"symbol": tsym, "interval": "1week", "currency": "USD", "exchange_timezone": "America/New_York",
            "exchange": "NYSE", "mic_code": "XNYS", "type": "ETF" if tsym in ("SPY", "XLK") else "Common Stock"}  # fmt: skip
    return json.dumps({"meta": meta, "values": values, "status": "ok"}, separators=(",", ":"))


def main() -> None:
    (OUT / "twelvedata").mkdir(exist_ok=True)
    for sym, start in SYMBOLS.items():
        text = series(sym, start)
        (OUT / f"{sym.replace('^', '_')}_w.csv").write_text(text, encoding="utf-8")
        tsym = TWELVEDATA_SYMBOL.get(sym, sym.removesuffix(".us").upper())
        (OUT / "twelvedata" / f"{tsym}.json").write_text(series_json(sym, text), encoding="utf-8")
    errors = {
        "not_found.json": {"code": 404, "message": "**symbol** not found: ZZZZ. Please specify it correctly according "
                           "to API Reference.", "status": "error"},
        "minute_credits.json": {"code": 429, "message": "You have run out of API credits for the current minute. 9 API "
                                "credits were used, with the current limit being 8. Wait for the next minute or "
                                "consider switching to a higher tier plan at https://twelvedata.com/pricing",
                                "status": "error"},
        "bad_key.json": {"code": 401, "message": "**apikey** parameter is incorrect or not specified. You can get your "
                         "free API key instantly following this link: https://twelvedata.com/pricing",
                         "status": "error"},
    }  # fmt: skip
    for name, doc in errors.items():
        (OUT / "twelvedata" / name).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
