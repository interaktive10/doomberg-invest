"""US weekly prices from Yahoo's chart endpoint (docs/SPEC_ISSUES.md 37): symbols, bars keyed by Friday whatever the
daylight-saving offset, Yahoo's quirks (null weeks, the week in progress twice, single-precision prices), and the
answers Yahoo gives instead of a chart."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from pipeline.net.http import DomainNotAllowed, HttpClient
from pipeline.net.stooq import parse_csv
from pipeline.net.yahoo import (
    HOSTS,
    YahooClient,
    YahooNoSuchSymbol,
    YahooUnavailable,
    chart_url,
    parse_chart,
    price,
    yahoo_symbol,
)
from pipeline.settings import Settings

PX = Path(__file__).resolve().parents[2] / "fixtures" / "px"


def mock_http(tmp_path: Path) -> HttpClient:
    return HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))


def test_symbols() -> None:
    assert [yahoo_symbol(t) for t in ("AAPL", "brk.b", "BF/B", "^spx", "^SPX", "XLK")] == [
        "AAPL", "BRK-B", "BF-B", "^GSPC", "^GSPC", "XLK"]  # fmt: skip
    assert chart_url("^GSPC") == "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?interval=1wk&range=10y"


@pytest.mark.parametrize("name", ["PWR", "JBL", "XLK", "_GSPC"])
def test_bars_match_the_same_series_from_a_csv(name: str) -> None:
    """Yahoo stamps a weekly bar at its Monday's midnight, New York time (04:00 or 05:00 UTC with daylight saving);
    the CSV dates it at its last trading day (a Thursday in a holiday week). Both are keyed by the same Friday."""
    stooq = {"PWR": "pwr.us", "JBL": "jbl.us", "XLK": "xlk.us", "_GSPC": "_spx"}[name]
    bars = parse_chart((PX / "yahoo" / f"{name}.json").read_bytes())
    assert bars == parse_csv((PX / f"{stooq}_w.csv").read_bytes())
    assert len(bars) == 260 and all(b.week_end.weekday() == 4 for b in bars) and bars[-1].week_end == date(2026, 9, 18)


def test_yahoo_quirks() -> None:
    """AAPL's chart has a week of nulls, and the week in progress twice: its Monday bar, then one at the latest trade
    (Wednesday 15:59 New York time); the later one is the week's."""
    bars = parse_chart((PX / "yahoo" / "AAPL.json").read_bytes())
    csv = parse_csv((PX / "aapl.us_w.csv").read_bytes())
    assert [b.week_end for b in bars[:-1]] == [b.week_end for i, b in enumerate(csv) if i != 100]
    assert bars[-1].week_end == date(2026, 9, 25) and bars[-1].close == D("313.25")
    assert bars[-1].volume == D(31_000_000)


def test_a_market_east_of_utc_keeps_its_week() -> None:
    """Monday midnight in Mumbai (UTC+5:30) is Sunday evening in UTC; the bar still belongs to the Friday after it."""
    monday = int(datetime(2026, 9, 13, 18, 30, tzinfo=UTC).timestamp())  # 2026-09-14 00:00 IST
    doc = {
        "chart": {
            "result": [
                {
                    "meta": {"gmtoffset": 19800},
                    "timestamp": [monday],
                    "indicators": {"quote": [{"close": [1234.5], "volume": [10]}]},
                }
            ],
            "error": None,
        }
    }
    assert parse_chart(json.dumps(doc).encode())[0].week_end == date(2026, 9, 18)


def test_prices_are_the_shortest_decimal_of_their_single_precision_value() -> None:
    assert price(227.52000427246094) == D("227.52") and price(5815.02978515625) == D("5815.03")
    assert price(1500.0) == D("1500") and str(price(1500.0)) == "1500" and price(0.1234) == D("0.1234")
    assert [price(x) for x in (None, 0, -1.0, True, float("nan"), float("inf"), "12.5")] == [None] * 7


def test_the_client_reads_through_the_allowlisted_http_client(tmp_path: Path) -> None:
    http = mock_http(tmp_path)
    http.register_mock(chart_url("PWR"), (PX / "yahoo" / "PWR.json").read_bytes())
    bars = YahooClient(http).weekly("pwr")
    assert http.calls == ["https://query1.finance.yahoo.com/v8/finance/chart/PWR?interval=1wk&range=10y"]
    assert bars[-1].close == D((PX / "pwr.us_w.csv").read_text().splitlines()[-1].split(",")[4])


def test_query2_answers_when_query1_does_not(tmp_path: Path) -> None:
    """The old Doomberg's fallback (doomberg/brokers/market_feed.py): query2 when query1 refuses."""
    http = mock_http(tmp_path)
    http.register_error(chart_url("PWR"), 429)
    http.register_mock(chart_url("PWR", "query2"), (PX / "yahoo" / "PWR.json").read_bytes())
    assert len(YahooClient(http).weekly("PWR")) == 260
    assert http.calls == [chart_url("PWR", "query1"), chart_url("PWR", "query2")]
    assert http.calls[1] == "https://query2.finance.yahoo.com/v8/finance/chart/PWR?interval=1wk&range=10y"


def test_an_unknown_symbol_is_an_answer(tmp_path: Path) -> None:
    """Yahoo answers a symbol it doesn't know with 404 and a JSON error: the site is up, so the weekly run keeps
    asking, and the other host isn't asked."""
    http = mock_http(tmp_path)
    http.register_error(chart_url("ZZZZ"), 404)
    with pytest.raises(YahooNoSuchSymbol, match=r"^404 "):
        YahooClient(http).weekly("ZZZZ")
    assert http.calls == [chart_url("ZZZZ")]
    with pytest.raises(YahooNoSuchSymbol, match="No data found, symbol may be delisted"):
        parse_chart((PX / "yahoo" / "not_found.json").read_bytes())
    with pytest.raises(YahooNoSuchSymbol):
        parse_chart(b'{"chart":{"result":[{"meta":{},"indicators":{"quote":[{}]}}],"error":null}}')


@pytest.mark.parametrize(
    "body",
    [b"Too Many Requests\r\n", b"<!doctype html><html><title>Yahoo</title>Will be right back...", b"",
     b'{"chart":{"result":[{"timestamp":[1],"indicators":{"quote":"x"}}]}}', b'{"finance":{"error":null}}'],
)  # fmt: skip
def test_answers_that_are_not_a_chart(tmp_path: Path, body: bytes) -> None:
    http = mock_http(tmp_path)
    for host in HOSTS:
        http.register_mock(chart_url("PWR", host), body)
    with pytest.raises(YahooUnavailable) as e:
        YahooClient(http).weekly("PWR")
    assert not isinstance(e.value, YahooNoSuchSymbol) and len(http.calls) == 2


def test_refusals_are_unavailable_not_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    http = mock_http(tmp_path)
    for host in HOSTS:
        http.register_error(chart_url("PWR", host), 429)
    with pytest.raises(YahooUnavailable, match=r"^Yahoo request failed \(429\)$") as e:
        YahooClient(http).weekly("PWR")
    assert not isinstance(e.value, YahooNoSuchSymbol)

    def consent(url: str, **_: object) -> bytes:
        raise DomainNotAllowed("https://consent.yahoo.com is not on the allowlist (pipeline/net/http.py)")

    monkeypatch.setattr(http, "get_bytes", consent)
    with pytest.raises(YahooUnavailable, match="redirected off the allowlist"):
        YahooClient(http).weekly("PWR")
