"""US weekly prices from Twelve Data's time_series (docs/SPEC_ISSUES.md 38): symbols, bars keyed by Friday, the key in
a header and never in an error, and the answers Twelve Data gives instead of a series."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest

from pipeline.net.http import HttpClient
from pipeline.net.stooq import parse_csv
from pipeline.net.twelvedata import (
    TwelveDataClient,
    TwelveDataNoSuchSymbol,
    TwelveDataUnavailable,
    parse_series,
    series_url,
    td_symbol,
    week_end,
)
from pipeline.prices.source import NoSuchSymbol
from pipeline.settings import Settings
from pipeline.signals.weekly import price_source

PX = Path(__file__).resolve().parents[2] / "fixtures" / "px"
TD = PX / "twelvedata"
KEY = "td-key-0123456789abcdef"


def mock_http(tmp_path: Path, key: str | None = KEY, source: str = "twelvedata") -> HttpClient:
    settings = Settings(
        database_url="x",
        mock_externals=True,
        sec_user_agent="t",
        cache_dir=tmp_path,
        twelvedata_api_key=key,
        price_source=source,
    )
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


def test_the_source_follows_price_source(tmp_path: Path) -> None:
    assert price_source(mock_http(tmp_path)).name == "twelvedata"
    assert price_source(mock_http(tmp_path, source="yahoo")).name == "yahoo"
