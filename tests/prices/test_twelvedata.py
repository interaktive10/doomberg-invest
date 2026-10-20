"""US weekly prices from Twelve Data's time_series (docs/SPEC_ISSUES.md 38): symbols, bars keyed by Friday, the key in
a header and never in an error, and the answers Twelve Data gives instead of a series. The Signal Lab's daily and
monthly history (SPEC_ISSUES 51): end-of-day intervals only, a spent minute retried, a spent day told apart."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest

from pipeline.net.http import HttpClient
from pipeline.net.twelvedata import (
    HISTORY_SIZE,
    INTERVALS,
    MINUTE_RETRIES,
    MINUTE_WAIT,
    TwelveDataClient,
    TwelveDataDayCredits,
    TwelveDataMinuteCredits,
    TwelveDataNoSuchSymbol,
    TwelveDataUnavailable,
    parse_series,
    series_url,
    td_symbol,
    week_end,
)
from pipeline.prices.bars import parse_csv
from pipeline.prices.source import NoSuchSymbol
from pipeline.settings import Settings

PX = Path(__file__).resolve().parents[2] / "fixtures" / "px"
TD = PX / "twelvedata"
KEY = "td-key-0123456789abcdef"


def mock_http(tmp_path: Path, key: str | None = KEY) -> HttpClient:
    settings = Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path,
                        twelvedata_api_key=key)  # fmt: skip
    return HttpClient(settings)


def test_symbols() -> None:
    assert [td_symbol(t) for t in ("AAPL", "brk-b", "BF/B", "^spx", "XLK")] == ["AAPL", "BRK.B", "BF.B", "SPY", "XLK"]
    assert series_url("BRK.B") == "https://api.twelvedata.com/time_series?symbol=BRK.B&interval=1week&outputsize=530"


@pytest.mark.parametrize(("name", "csv"), [("PWR", "pwr.us"), ("JBL", "jbl.us"), ("XLK", "xlk.us"), ("SPY", "_spx")])
def test_bars_match_the_same_series_from_a_csv(name: str, csv: str) -> None:
    """Twelve Data dates a weekly bar at its Monday and lists the newest first; the CSV dates it at its last trading
    day (a Thursday in a holiday week). Both are keyed by the same Friday, oldest first."""
    bars = parse_series((TD / f"{name}.json").read_bytes())
    assert bars == parse_csv((PX / f"{csv}_w.csv").read_bytes())
    assert len(bars) == 260 and all(b.week_end.weekday() == 4 for b in bars) and bars[-1].week_end == date(2026, 9, 18)


def test_a_weekend_date_starts_the_next_week() -> None:
    assert [week_end(date(2026, 9, d)) for d in (14, 18, 19, 20)] == [
        date(2026, 9, 18), date(2026, 9, 18), date(2026, 9, 25), date(2026, 9, 25)]  # fmt: skip


def test_prices_are_decimals_without_padding() -> None:
    doc = {"values": [{"datetime": "2026-09-14", "close": "254.86000", "volume": "153384000"},
                      {"datetime": "2026-09-07", "close": "1500.00000", "volume": ""},
                      {"datetime": "2026-08-31", "close": "0", "volume": "1"},
                      {"datetime": "bad", "close": "1.0"}], "status": "ok"}  # fmt: skip
    bars = parse_series(json.dumps(doc).encode())
    assert [(b.week_end, str(b.close), b.volume) for b in bars] == [
        (date(2026, 9, 11), "1500", None), (date(2026, 9, 18), "254.86", D(153384000))]  # fmt: skip


def test_the_key_rides_in_a_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    http = mock_http(tmp_path)
    seen: list[tuple[str, dict[str, str] | None]] = []

    def get_bytes(url: str, **kw: Any) -> bytes:
        seen.append((url, kw.get("headers")))
        return (TD / "PWR.json").read_bytes()

    monkeypatch.setattr(http, "get_bytes", get_bytes)
    assert len(TwelveDataClient(http).weekly("PWR")) == 260
    assert seen == [(series_url("PWR"), {"Authorization": f"apikey {KEY}"})] and KEY not in seen[0][0]


def test_the_client_reads_through_the_allowlisted_http_client(tmp_path: Path) -> None:
    http = mock_http(tmp_path)
    http.register_mock(series_url("SPY"), (TD / "SPY.json").read_bytes())
    bars = TwelveDataClient(http).weekly("^spx")
    assert http.calls == [series_url("SPY")] and len(bars) == 260


def test_without_a_key_nothing_is_asked(tmp_path: Path) -> None:
    http = mock_http(tmp_path, key=None)
    with pytest.raises(TwelveDataUnavailable, match="^TWELVEDATA_API_KEY is not set$") as e:
        TwelveDataClient(http).weekly("PWR")
    assert http.calls == [] and not isinstance(e.value, NoSuchSymbol)


@pytest.mark.parametrize("name", ["not_found.json"])
def test_an_unknown_symbol_is_an_answer(tmp_path: Path, name: str) -> None:
    http = mock_http(tmp_path)
    http.register_mock(series_url("ZZZZ"), (TD / name).read_bytes())
    with pytest.raises(TwelveDataNoSuchSymbol, match=r"^404: \*\*symbol\*\* not found"):
        TwelveDataClient(http).weekly("ZZZZ")
    plan = {"code": 403, "message": "**symbol** QQQX is not available with your plan.", "status": "error"}
    with pytest.raises(NoSuchSymbol):
        parse_series(json.dumps(plan).encode())


@pytest.mark.parametrize(
    "body",
    [(TD / "minute_credits.json").read_bytes(), (TD / "bad_key.json").read_bytes(), b"<!doctype html><html>502",
     b"", b'{"status":"ok"}', b"[1, 2]"],
)  # fmt: skip
def test_answers_that_are_not_a_series(tmp_path: Path, body: bytes) -> None:
    http = mock_http(tmp_path)
    http.register_mock(series_url("PWR"), body)
    with pytest.raises(TwelveDataUnavailable) as e:
        TwelveDataClient(http).weekly("PWR")
    assert not isinstance(e.value, NoSuchSymbol)


def test_http_errors_are_classified_and_never_carry_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    http = mock_http(tmp_path)
    http.register_error(series_url("PWR"), 429)
    with pytest.raises(TwelveDataUnavailable, match=r"^429: Twelve Data request failed$") as e:
        TwelveDataClient(http).weekly("PWR")
    assert not isinstance(e.value, NoSuchSymbol)
    echo = {"code": 401, "message": f"**apikey** {KEY} is incorrect", "status": "error"}
    http.register_mock(series_url("PWR"), json.dumps(echo).encode())
    with pytest.raises(TwelveDataUnavailable) as echoed:
        TwelveDataClient(http).weekly("PWR")
    assert KEY not in str(echoed.value) and "***" in str(echoed.value)


def test_twelve_data_is_the_only_price_source() -> None:
    """Overhaul PR 4 (docs/SPEC_ISSUES.md 52): the Yahoo and Stooq clients and PRICE_SOURCE are gone; the weekly run
    asks Twelve Data, and a manual CSV import still reads through pipeline/prices/bars.py."""
    import importlib.util

    from pipeline.signals import weekly

    assert all(importlib.util.find_spec(f"pipeline.net.{m}") is None for m in ("yahoo", "stooq"))
    assert not hasattr(weekly, "price_source") and "price_source" not in Settings.__dataclass_fields__
    assert weekly.parse_csv is parse_csv


def test_the_daily_url_and_parse(tmp_path: Path) -> None:
    """Overhaul PR 3: the Lab's history asks one request of HISTORY_SIZE days per symbol and gets every day's close,
    oldest first (Twelve Data lists the newest first)."""
    http = mock_http(tmp_path)
    url = series_url("AAPL", HISTORY_SIZE, "1day")
    assert url == "https://api.twelvedata.com/time_series?symbol=AAPL&interval=1day&outputsize=5000"
    http.register_mock(url, (TD / "daily_AAPL.json").read_bytes())
    closes = TwelveDataClient(http).daily("AAPL")
    assert http.calls == [url] and len(closes) == 11
    assert closes[0] == (date(2010, 1, 4), D("7.6432")) and closes[-1] == (date(2026, 10, 16), D("252.1"))
    assert [d for d, _ in closes] == sorted(d for d, _ in closes)


def test_the_monthly_url(tmp_path: Path) -> None:
    http = mock_http(tmp_path)
    url = series_url("BRK.B", HISTORY_SIZE, "1month")
    body = {"values": [{"datetime": "2026-10-01", "close": "480.5"}, {"datetime": "2009-12-01", "close": "99.0"}],
            "status": "ok"}  # fmt: skip
    http.register_mock(url, json.dumps(body).encode())
    assert TwelveDataClient(http).monthly("BRK-B") == [(date(2009, 12, 1), D(99)), (date(2026, 10, 1), D("480.5"))]
    assert http.calls == ["https://api.twelvedata.com/time_series?symbol=BRK.B&interval=1month&outputsize=5000"]


@pytest.mark.parametrize("interval", ["1min", "5min", "15min", "30min", "45min", "1h", "2h", "4h", "8h", "1d", ""])
def test_an_intraday_interval_raises(tmp_path: Path, interval: str) -> None:
    """CLAUDE.md: a research tool, no intraday data. Only end-of-day intervals build a URL, so nothing is asked."""
    assert INTERVALS == ("1day", "1week", "1month")
    with pytest.raises(ValueError, match="no intraday data"):
        series_url("AAPL", HISTORY_SIZE, interval)
    http = mock_http(tmp_path)
    with pytest.raises(ValueError):
        TwelveDataClient(http)._history("AAPL", interval)
    assert http.calls == []


def test_a_spent_minute_is_asked_again_after_the_minute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    http = mock_http(tmp_path)
    answers = [(TD / "minute_credits.json").read_bytes(), (TD / "daily_AAPL.json").read_bytes()]
    monkeypatch.setattr(http, "get_bytes", lambda url, **kw: answers.pop(0))
    waits: list[float] = []
    assert len(TwelveDataClient(http, sleep=waits.append).daily("AAPL")) == 11
    assert waits == [MINUTE_WAIT] and MINUTE_WAIT > 60
    monkeypatch.setattr(http, "get_bytes", lambda url, **kw: (TD / "minute_credits.json").read_bytes())
    waits.clear()
    with pytest.raises(TwelveDataMinuteCredits):
        TwelveDataClient(http, sleep=waits.append).daily("AAPL")
    assert waits == [MINUTE_WAIT] * MINUTE_RETRIES


def test_a_spent_day_is_its_own_failure_and_never_waited_for(tmp_path: Path) -> None:
    http = mock_http(tmp_path)
    http.register_mock(series_url("AAPL", HISTORY_SIZE, "1day"), (TD / "daily_day_credits.json").read_bytes())
    waits: list[float] = []
    with pytest.raises(TwelveDataDayCredits) as e:
        TwelveDataClient(http, sleep=waits.append).daily("AAPL")
    assert waits == [] and len(http.calls) == 1 and not isinstance(e.value, NoSuchSymbol)
    assert isinstance(e.value, TwelveDataUnavailable)  # the weekly run counts it as a failure, as before
    with pytest.raises(TwelveDataMinuteCredits):  # the weekly run doesn't wait for a spent minute
        parse_series((TD / "minute_credits.json").read_bytes())
