"""The Lab's month-end prices (BRIEF §4.10.1, docs/SPEC_ISSUES.md 51): daily closes -> month bars, the release asset
written and read back, and the download's state."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path

from pipeline.lab.prices import (
    DownloadState,
    MonthBar,
    TickerState,
    add_months,
    complete_months,
    month_bars,
    month_end,
    month_ends,
    read_month_csv,
    read_prices,
    write_month_csv,
)

DAILY = [(date(2024, 1, 30), D("10.5")), (date(2024, 1, 31), D("11.0")), (date(2024, 2, 1), D("12.0")),
         (date(2024, 2, 15), D("9.0")), (date(2024, 2, 29), D("10.0"))]  # fmt: skip


def test_month_bars_from_daily_closes() -> None:
    bars = month_bars(DAILY)
    assert [(b.month_end, b.close, b.high, b.low) for b in bars] == [
        (date(2024, 1, 31), D("11.0"), D("11.0"), D("10.5")),
        (date(2024, 2, 29), D("10.0"), D("12.0"), D("9.0")),
    ]


def test_month_arithmetic() -> None:
    assert month_end(date(2024, 2, 3)) == date(2024, 2, 29) and add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2024, 3, 31), -13) == date(2023, 2, 28)
    assert month_ends(date(2023, 11, 30), date(2024, 2, 29))[-1] == date(2024, 2, 29)


def test_complete_months_drop_the_current_month() -> None:
    """A month's bar is its last close; the month `today` is in isn't over, so it has no bar (not even on its last
    day, nor for a monthly series dated at the month's first day)."""
    closes = [*DAILY, (date(2024, 3, 1), D("13.0")), (date(2024, 3, 28), D("14.0"))]
    for today in (date(2024, 3, 2), date(2024, 3, 31)):
        assert [b.month_end for b in complete_months(closes, today)] == [date(2024, 1, 31), date(2024, 2, 29)]
    assert complete_months(closes, date(2024, 4, 1))[-1] == MonthBar(date(2024, 3, 31), D(14), D(14), D(13))
    monthly = [(date(2024, 1, 1), D(5)), (date(2024, 2, 1), D(6))]
    assert complete_months(monthly, date(2024, 2, 20)) == [MonthBar(date(2024, 1, 31), D(5), D(5), D(5))]


def test_read_month_csv() -> None:
    bars = read_month_csv("ticker,month_end,close\nX,2024-02-29,5\nX,2024-01-31,4\n")
    assert [(b.month_end, b.close) for b in bars["X"]] == [(date(2024, 1, 31), D(4)), (date(2024, 2, 29), D(5))]


def test_the_asset_round_trips_and_appends(tmp_path: Path) -> None:
    """write_month_csv appends a gzip member per save; read_prices reads every member, keeps the last row of a month
    saved twice (a ticker asked again after a stop) and only the wanted tickers."""
    asset = tmp_path / "us_month_prices.csv.gz"
    jan, feb = month_bars(DAILY)
    write_month_csv(asset, {"AAPL": [jan], "BRK-B": [jan, feb]}, append=True)  # no file yet: a fresh one
    write_month_csv(asset, {"AAPL": [jan, feb], "MSFT": []}, append=True)
    assert not (tmp_path / "us_month_prices.csv.gz.tmp").exists()
    got = read_prices(asset, ["AAPL", "BRK-B", "MSFT", "AAPL"])
    assert got == {"AAPL": [jan, feb], "BRK-B": [jan, feb]}
    assert read_prices(asset) == got
    plain = tmp_path / "prices.csv"
    write_month_csv(plain, {"X": [feb]})
    assert plain.read_text(encoding="utf-8") == "ticker,month_end,close,high,low\nX,2024-02-29,10.0,12.0,9.0\n"
    write_month_csv(plain, {"Y": [jan]})  # without append: replaced
    assert list(read_prices(plain)) == ["Y"]


def test_the_state_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert DownloadState.load(path) is None
    state = DownloadState(
        "1day",
        "partial",
        None,
        {
            "A": TickerState("ok"),
            "B": TickerState("pending", 2, "502"),
            "C": TickerState("no_such_symbol"),
            "D": TickerState("error", 3),
        },
    )
    state.save(path)
    back = DownloadState.load(path)
    assert back == state and back is not None and back.settled() == 3 and back.count("pending") == 1
    assert not (tmp_path / "state.json.tmp").exists()
