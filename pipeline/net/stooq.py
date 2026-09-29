"""Stooq per-symbol weekly CSV (BRIEF §2.7, §4.4): the US candidate set and benchmarks only, <= 400 symbols a week,
1 request per 2 s (pipeline/net/http.py). Fragile by nature: an answer that isn't the CSV ("No data", a daily hit
limit, an HTML page) raises StooqUnavailable; the caller marks 'stooq' stale and falls back to a manual CSV in the
same format (imports/us_prices/<TICKER>.csv).

Bars are dated at the week's last trading day; they are keyed by that week's Friday, like prices_w everywhere.

Since 2026 Stooq answers a CSV request only with an apikey ("Get your apikey: 1. Open
https://stooq.com/q/d/?s=^spx&get_apikey" plus a CAPTCHA, done once by a person; the first live run, 2026-09-29, got
an HTML page for every symbol). The key comes from STOOQ_API_KEY and rides in the URL, so no error raised here carries
the URL or the key."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

from pipeline.net.http import HttpClient

STOOQ_CSV = "https://stooq.com/q/d/l/?s={symbol}&i=w"
KEY_IN_TEXT = re.compile(r"apikey=[^&\s\"'<>]*")  # also a key cut short by parse_csv's 120 characters


class StooqUnavailable(Exception):
    """Stooq answered something other than a weekly CSV."""


@dataclass(frozen=True)
class Bar:
    week_end: date
    close: Decimal
    volume: Decimal | None


def friday_of(d: date) -> date:
    """The Friday of d's week (Saturday and Sunday belong to the Friday before)."""
    return d + timedelta(days=4 - d.weekday()) if d.weekday() <= 4 else d - timedelta(days=d.weekday() - 4)


def stooq_symbol(ticker: str) -> str:
    """AAPL -> aapl.us, BRK-B -> brk-b.us, ^spx stays ^spx (indices carry their own prefix)."""
    t = ticker.strip().lower().replace(".", "-")
    return t if t.startswith("^") or t.endswith(".us") else f"{t}.us"


def csv_url(symbol: str) -> str:
    return STOOQ_CSV.format(symbol=quote(symbol, safe="-.^"))


def parse_csv(body: bytes) -> list[Bar]:
    text = body.decode("utf-8-sig", "replace").strip()
    if not text.lower().startswith("date,"):
        raise StooqUnavailable(text[:120] or "empty response")
    bars: dict[date, Bar] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            day, close = date.fromisoformat(row["Date"]), Decimal(row["Close"])
        except (KeyError, ValueError, InvalidOperation):
            continue
        vol = row.get("Volume") or ""
        try:
            volume = Decimal(vol) if vol else None
        except InvalidOperation:
            volume = None
        if close > 0:
            bars[friday_of(day)] = Bar(friday_of(day), close, volume)
    if not bars:
        raise StooqUnavailable("CSV without price rows")
    return [bars[k] for k in sorted(bars)]


@dataclass
class StooqClient:
    http: HttpClient

    def weekly(self, ticker: str) -> list[Bar]:
        key = self.http.settings.stooq_api_key
        url = csv_url(stooq_symbol(ticker)) + (f"&apikey={quote(key, safe='')}" if key else "")
        try:
            return parse_csv(self.http.get_bytes(url, timeout=30.0))
        except httpx.HTTPError as e:
            status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else type(e).__name__
            raise StooqUnavailable(f"Stooq request failed ({status})") from None
        except StooqUnavailable as e:
            text = (
                KEY_IN_TEXT.sub("apikey=***", str(e).replace(key, "***")) if key else f"STOOQ_API_KEY is not set: {e}"
            )
            raise StooqUnavailable(text) from None
