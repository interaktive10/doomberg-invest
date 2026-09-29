"""Stooq bulk daily file -> month bars (BRIEF §4.10.1)."""

from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from pipeline.lab.prices import add_months, month_bars, month_end, month_ends, parse_daily, read_bulk, read_month_csv

DAILY = """<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
AAPL.US,D,20240130,000000,1,1,1,10.5,100,0
AAPL.US,D,20240131,000000,1,1,1,11.0,100,0
AAPL.US,D,20240201,000000,1,1,1,12.0,100,0
AAPL.US,D,20240215,000000,1,1,1,9.0,100,0
AAPL.US,D,20240229,000000,1,1,1,10.0,100,0
AAPL.US,D,bad,000000,1,1,1,10.0,100,0
"""


def test_month_bars_from_daily_closes() -> None:
    bars = month_bars(parse_daily(DAILY))
    assert [(b.month_end, b.close, b.high, b.low) for b in bars] == [
        (date(2024, 1, 31), D("11.0"), D("11.0"), D("10.5")),
        (date(2024, 2, 29), D("10.0"), D("12.0"), D("9.0")),
    ]


def test_month_arithmetic() -> None:
    assert month_end(date(2024, 2, 3)) == date(2024, 2, 29) and add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2024, 3, 31), -13) == date(2023, 2, 28)
    assert month_ends(date(2023, 11, 30), date(2024, 2, 29))[-1] == date(2024, 2, 29)


def test_read_bulk_zip(tmp_path: Path) -> None:
    z = tmp_path / "d_us_txt.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("data/daily/us/nasdaq stocks/1/aapl.us.txt", DAILY)
        f.writestr("data/daily/us/nyse stocks/1/brk-b.us.txt", DAILY.replace("AAPL", "BRK-B"))
    got = read_bulk(z, ["AAPL", "BRK-B", "MISSING"])
    assert sorted(got) == ["AAPL", "BRK-B"] and got["AAPL"][-1].close == D("10.0")


def test_read_month_csv() -> None:
    bars = read_month_csv("ticker,month_end,close\nX,2024-02-29,5\nX,2024-01-31,4\n")
    assert [(b.month_end, b.close) for b in bars["X"]] == [(date(2024, 1, 31), D(4)), (date(2024, 2, 29), D(5))]
