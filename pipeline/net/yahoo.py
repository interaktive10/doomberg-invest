"""Yahoo Finance's chart endpoint: weekly bars for the US candidate set and the US benchmarks (BRIEF §4.4 names Stooq;
Stooq has served its CSV only with a CAPTCHA-issued apikey since 2026 and renamed ^SPX, so Manzoor chose Yahoo on
2026-10-07, docs/SPEC_ISSUES.md 37). No key, no account, <= 400 symbols a week, 1 request per second
(pipeline/net/http.py). Unofficial and undocumented: an answer that isn't a chart (a symbol Yahoo doesn't know, a
"Too Many Requests" page, a redirect off the allowlist) raises YahooUnavailable; the caller marks 'yahoo' stale and
falls back to a manual CSV (imports/us_prices/<TICKER>.csv, the format net/stooq.py parses).

As the old Doomberg did (doomberg/brokers/market_feed.py): a browser User-Agent, no crumb (the chart endpoint doesn't
need one, unlike /v7 quote and /v10 quoteSummary), and query2 when query1 doesn't answer.

`close` is split-adjusted and not dividend-adjusted, like Stooq's, so pipeline/prices/splits.py works unchanged. Bars
are keyed by their week's Friday, like prices_w everywhere."""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from pipeline.net.http import DomainNotAllowed, HttpClient
from pipeline.net.stooq import Bar, friday_of

YAHOO_CHART = "https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1wk&range=10y"
HOSTS = ("query1", "query2")
INDEX_SYMBOLS = {"^spx": "^GSPC"}  # config/context.yaml names the S&P 500 the way Stooq did
# A weekly bar is stamped at its Monday's midnight, exchange time (the week in progress, at its latest trade). Today's
# UTC offset may differ from the bar's by an hour of daylight saving; half a day later is still the same week.
HALF_DAY = timedelta(hours=12)


class YahooUnavailable(Exception):
    """Yahoo answered something other than a chart, or didn't answer."""


class YahooNoSuchSymbol(YahooUnavailable):
    """Yahoo answered, but has no chart for the symbol (delisted, renamed, or a ticker it spells differently)."""


def yahoo_symbol(ticker: str) -> str:
    """AAPL -> AAPL, BRK.B -> BRK-B (Yahoo's spelling of a share class), ^spx -> ^GSPC."""
    t = ticker.strip()
    return INDEX_SYMBOLS.get(t.lower()) or t.upper().replace(".", "-").replace("/", "-")


def chart_url(symbol: str, host: str = HOSTS[0]) -> str:
    return YAHOO_CHART.format(host=host, symbol=quote(symbol, safe="-^"))


def _error_text(body: bytes) -> str:
    """A chart error's code and description ({"chart": {"error": {...}}}), else the start of the body."""
    try:
        err = json.loads(body)["chart"]["error"]
    except (ValueError, KeyError, TypeError):
        return body.decode("utf-8", "replace").strip()[:120] or "empty response"
    if isinstance(err, dict):
        return f"{err.get('code')}: {err.get('description')}"[:120]
    return "a chart without results"


def price(x: Any) -> Decimal | None:
    """Yahoo serves single-precision closes as doubles (227.52 arrives as 227.52000427246094): the price is the
    shortest decimal with the same single-precision value. A week without a trade is null."""
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x) or x <= 0:
        return None
    try:
        single = struct.pack("<f", x)
    except OverflowError:
        return None
    for digits in range(1, 10):
        text = f"{x:.{digits}g}"
        if struct.pack("<f", float(text)) == single:
            return Decimal(text).quantize(Decimal(1)) if "e+" in text else Decimal(text)
    return None


def _volume(x: Any) -> Decimal | None:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x) or x <= 0:
        return None
    return Decimal(int(x))


def _bars(r: dict[str, Any]) -> list[Bar]:
    offset = timedelta(seconds=int((r.get("meta") or {}).get("gmtoffset") or 0))
    q = r["indicators"]["quote"][0]
    times, closes, volumes = r.get("timestamp") or [], q.get("close") or [], q.get("volume") or []
    bars: dict[date, Bar] = {}
    for i, ts in enumerate(times):
        close = price(closes[i]) if i < len(closes) else None
        if close is None or isinstance(ts, bool) or not isinstance(ts, int | float):
            continue
        week_end = friday_of((datetime.fromtimestamp(ts, UTC) + offset + HALF_DAY).date())
        volume = _volume(volumes[i]) if i < len(volumes) else None
        bars[week_end] = Bar(week_end, close, volume)  # a later bar of a week wins
    return [bars[k] for k in sorted(bars)]


def parse_chart(body: bytes) -> list[Bar]:
    try:
        results = json.loads(body)["chart"]["result"]
    except (ValueError, KeyError, TypeError):
        raise YahooUnavailable(_error_text(body)) from None
    if not results or not isinstance(results, list) or not isinstance(results[0], dict):
        raise YahooNoSuchSymbol(_error_text(body))
    try:
        bars = _bars(results[0])
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, OSError) as e:
        raise YahooUnavailable(f"a malformed chart ({type(e).__name__})") from None
    if not bars:
        raise YahooNoSuchSymbol("a chart without price rows")
    return bars


@dataclass
class YahooClient:
    http: HttpClient

    def weekly(self, ticker: str) -> list[Bar]:
        symbol, failed = yahoo_symbol(ticker), YahooUnavailable("no host asked")
        for host in HOSTS:
            try:
                return self._chart(chart_url(symbol, host))
            except YahooNoSuchSymbol:
                raise  # an answer: the other host knows no more
            except YahooUnavailable as e:
                failed = e
        raise failed

    def _chart(self, url: str) -> list[Bar]:
        try:
            return parse_chart(self.http.get_bytes(url, timeout=30.0))
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:  # {"chart": {"result": null, "error": {"code": "Not Found", "description": ...}}}
                raise YahooNoSuchSymbol(f"404 {_error_text(e.response.content)}") from None
            raise YahooUnavailable(f"Yahoo request failed ({status})") from None
        except httpx.HTTPError as e:
            raise YahooUnavailable(f"Yahoo request failed ({type(e).__name__})") from None
        except DomainNotAllowed as e:  # e.g. a consent page on another host
            raise YahooUnavailable(f"Yahoo redirected off the allowlist: {e}"[:200]) from None
