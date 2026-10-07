"""Twelve Data's time_series endpoint: weekly bars for the US candidate set and the US benchmarks since 2026-10
(docs/SPEC_ISSUES.md 38). Yahoo answers GitHub's runners 429 from the first request; Twelve Data is an official API
with a free plan (8 credits a minute, 800 a day, no card; "internal non-display use", a private tool's case). One
credit per symbol, one request every 8 s (pipeline/net/http.py). The key rides in a header, never in a URL, and is
cut out of any error text.

A weekly bar is dated at its week's first day; it is keyed by that week's Friday, like prices_w everywhere. Prices are
decimal strings, split-adjusted and not dividend-adjusted, like Stooq's and Yahoo's closes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx

from pipeline.net.http import DomainNotAllowed, HttpClient
from pipeline.net.stooq import Bar, friday_of
from pipeline.prices.source import NoSuchSymbol, PriceUnavailable

TIME_SERIES = "https://api.twelvedata.com/time_series?symbol={symbol}&interval=1week&outputsize={size}"
OUTPUT_SIZE = 530  # ten years of weeks (C1 looks back up to ten years), and a few to spare
INDEX_SYMBOLS = {"^spx": "SPY"}  # the S&P 500 index needs a paid plan; the ETF that tracks it doesn't


class TwelveDataUnavailable(PriceUnavailable):
    """Twelve Data answered something other than a time series, or didn't answer."""


class TwelveDataNoSuchSymbol(TwelveDataUnavailable, NoSuchSymbol):
    """Twelve Data answered, but has no series for the symbol (unknown, or not on the free plan)."""


def td_symbol(ticker: str) -> str:
    """AAPL -> AAPL, BRK-B -> BRK.B (Twelve Data's spelling of a share class), ^spx -> SPY."""
    t = ticker.strip()
    return INDEX_SYMBOLS.get(t.lower()) or t.upper().replace("-", ".").replace("/", ".")


def series_url(symbol: str, size: int = OUTPUT_SIZE) -> str:
    return TIME_SERIES.format(symbol=quote(symbol, safe="."), size=size)


def week_end(day: date) -> date:
    """The Friday of the week a bar dated `day` covers: its own week's for a weekday, the next one for a weekend date
    (a week counted from Sunday)."""
    return friday_of(day) if day.weekday() <= 4 else day + timedelta(days=(4 - day.weekday()) % 7)


def _decimal(x: Any) -> Decimal | None:
    """'254.86000' -> 254.86; None for anything that isn't a positive number."""
    try:
        d = Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d <= 0:
        return None
    return d.quantize(Decimal(1)) if d == d.to_integral_value() else d.normalize()


def error(code: Any, message: str) -> TwelveDataUnavailable:
    """An error answer ({"code": 404, "message": "...", "status": "error"}): a symbol the plan doesn't know or doesn't
    cover is an answer; anything else (a spent minute or day of credits, a bad key, a server error) isn't."""
    text = f"{code}: {message}".strip()[:160]
    low = message.lower()
    if code == 404 or "not found" in low or "not available with your" in low:
        return TwelveDataNoSuchSymbol(text)
    return TwelveDataUnavailable(text)


def parse_series(body: bytes) -> list[Bar]:
    try:
        doc = json.loads(body)
    except ValueError:
        raise TwelveDataUnavailable(body.decode("utf-8", "replace").strip()[:120] or "empty response") from None
    if not isinstance(doc, dict):
        raise TwelveDataUnavailable("not a time series")
    if doc.get("status") == "error":
        raise error(doc.get("code"), str(doc.get("message") or ""))
    values = doc.get("values")
    if not isinstance(values, list):
        raise TwelveDataUnavailable("a time series without values")
    rows: list[tuple[date, Decimal, Decimal | None]] = []
    for v in values:
        if not isinstance(v, dict):
            continue
        try:
            day = date.fromisoformat(str(v.get("datetime"))[:10])
        except ValueError:
            continue
        close = _decimal(v.get("close"))
        if close is not None:
            vol = v.get("volume")
            rows.append((day, close, _decimal(vol) if vol not in (None, "") else None))
    bars = {week_end(day): Bar(week_end(day), close, vol) for day, close, vol in sorted(rows, key=lambda r: r[0])}
    if not bars:
        raise TwelveDataNoSuchSymbol("a time series without price rows")
    return [bars[k] for k in sorted(bars)]


@dataclass
class TwelveDataClient:
    http: HttpClient
    name: str = "twelvedata"

    def weekly(self, ticker: str) -> list[Bar]:
        key = self.http.settings.twelvedata_api_key
        if not key:
            raise TwelveDataUnavailable("TWELVEDATA_API_KEY is not set")
        try:
            return self._series(series_url(td_symbol(ticker)), key)
        except TwelveDataUnavailable as e:
            raise type(e)(str(e).replace(key, "***")) from None

    def _series(self, url: str, key: str) -> list[Bar]:
        try:
            body = self.http.get_bytes(url, timeout=30.0, headers={"Authorization": f"apikey {key}"})
        except httpx.HTTPStatusError as e:
            try:
                doc = json.loads(e.response.content)
                message = str(doc.get("message") or "") if isinstance(doc, dict) else ""
            except ValueError:
                message = ""
            raise error(e.response.status_code, message or "Twelve Data request failed") from None
        except httpx.HTTPError as e:
            raise TwelveDataUnavailable(f"Twelve Data request failed ({type(e).__name__})") from None
        except DomainNotAllowed as e:
            raise TwelveDataUnavailable(f"Twelve Data redirected off the allowlist: {e}"[:200]) from None
        return parse_series(body)
