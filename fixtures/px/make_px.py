#!/usr/bin/env python3
"""F-PX stand-ins (BRIEF §9): weekly CSVs in Stooq's exact format (Date,Open,High,Low,Close,Volume) for 10 symbols.

stooq.com resets connections from the build container (TLS reset through the egress proxy, 2026-09-25), so these
are synthetic series with fixed seeds, not real prices. `scripts/fetch_fixtures.py f-px` replaces them with the real
files where Stooq is reachable (docs/SPEC_ISSUES.md). Tests use them for parsing and ingestion only. One series
(jbl.us) carries an unadjusted 2:1 split in week 150 for the split tests; ^spx has no volume column, like Stooq's
index files.

yahoo/ holds the same series as Yahoo's chart endpoint answers them (v8/finance/chart, interval=1wk), which the weekly
run asks since 2026-10 (docs/SPEC_ISSUES.md 37): every bar stamped at its week's Monday midnight, New York time, and
prices as single-precision values written as doubles. AAPL's also carries Yahoo's quirks: a week of nulls and the week
in progress twice (its Monday bar and a later one at the latest trade).

twelvedata/ holds them as Twelve Data's time_series answers them (interval=1week; the weekly run asks it since 2026-10,
docs/SPEC_ISSUES.md 38): newest first, each bar dated at its week's Monday, prices as decimal strings; the ^spx series
stands in for SPY, which the client asks for the S&P 500."""

from __future__ import annotations

import json
import random
import struct
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent
SYMBOLS = {"aapl.us": 150.0, "msft.us": 300.0, "nvda.us": 90.0, "cat.us": 250.0, "orcl.us": 110.0,
           "pwr.us": 200.0, "jbl.us": 120.0, "gev.us": 180.0, "xlk.us": 180.0, "^spx": 4500.0}  # fmt: skip
WEEKS = 260
LAST = date(2026, 9, 18)
NEW_YORK = ZoneInfo("America/New_York")
YAHOO_SYMBOL = {"^spx": "^GSPC"}
TWELVEDATA_SYMBOL = {"^spx": "SPY"}


def series(symbol: str, start: float) -> str:
    rnd = random.Random(f"f-px:{symbol}")
    rows, price = [], start
    for i in range(WEEKS):
        day = LAST - timedelta(weeks=WEEKS - 1 - i)
        if i % 26 == 25:
            day -= timedelta(days=1)  # a holiday week ends on Thursday, as Stooq dates it
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


def single(x: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", x))[0])


def stamp(day: date, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(day.year, day.month, day.day, hour, minute, tzinfo=NEW_YORK).timestamp())


def chart(symbol: str, csv_text: str) -> str:
    ysym = YAHOO_SYMBOL.get(symbol, symbol.removesuffix(".us").upper())
    rows = [line.split(",") for line in csv_text.splitlines()[1:]]
    bars: list[tuple[int, list[float | None]]] = []
    for r in rows:
        day = date.fromisoformat(r[0])
        values = [single(float(v)) for v in r[1:5]] + [float(r[5]) if len(r) > 5 else None]
        bars.append((stamp(day - timedelta(days=day.weekday())), values))
    if symbol == "aapl.us":
        bars[100] = (bars[100][0], [None] * 5)  # a week Yahoo has nothing for
        monday = LAST + timedelta(days=3)
        bars.append((stamp(monday), [single(v) for v in (310.0, 312.0, 305.0, 306.5)] + [12_000_000.0]))
        bars.append((stamp(monday + timedelta(days=2), 15, 59), [single(v) for v in (310.0, 314.0, 305.0, 313.25)]
                     + [31_000_000.0]))  # fmt: skip
    quote: dict[str, list[Any]] = {k: [] for k in ("open", "high", "low", "close", "volume")}
    for _, values in bars:
        for k, v in zip(quote, values, strict=True):
            quote[k].append(int(v) if k == "volume" and v is not None else v)
    meta = {"currency": "USD", "symbol": ysym, "exchangeName": "SNP" if ysym.startswith("^") else "NYQ",
            "instrumentType": "INDEX" if ysym.startswith("^") else "EQUITY", "gmtoffset": -14400, "timezone": "EDT",
            "exchangeTimezoneName": "America/New_York", "dataGranularity": "1wk", "range": "10y"}  # fmt: skip
    doc = {"chart": {"result": [{"meta": meta, "timestamp": [t for t, _ in bars],
                                 "indicators": {"quote": [quote], "adjclose": [{"adjclose": quote["close"]}]}}],
                     "error": None}}  # fmt: skip
    return json.dumps(doc, separators=(",", ":"))


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
    (OUT / "yahoo").mkdir(exist_ok=True)
    for sym, start in SYMBOLS.items():
        text = series(sym, start)
        (OUT / f"{sym.replace('^', '_')}_w.csv").write_text(text, encoding="utf-8")
        ysym = YAHOO_SYMBOL.get(sym, sym.removesuffix(".us").upper())
        (OUT / "yahoo" / f"{ysym.replace('^', '_')}.json").write_text(chart(sym, text), encoding="utf-8")
        tsym = TWELVEDATA_SYMBOL.get(sym, sym.removesuffix(".us").upper())
        (OUT / "twelvedata" / f"{tsym}.json").write_text(series_json(sym, text), encoding="utf-8")
    not_found = {
        "chart": {
            "result": None,
            "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"},
        }
    }
    (OUT / "yahoo" / "not_found.json").write_text(json.dumps(not_found, separators=(",", ":")), encoding="utf-8")
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
    (OUT / "no_data.txt").write_text("No data", encoding="utf-8")
    (OUT / "limit.txt").write_text("Exceeded the daily hits limit", encoding="utf-8")


if __name__ == "__main__":
    main()
