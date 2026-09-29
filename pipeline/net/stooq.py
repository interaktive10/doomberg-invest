"""Stooq per-symbol weekly CSV (BRIEF §2.7, §4.4): the US candidate set and benchmarks only, <= 400 symbols a week,
1 request per 2 s (pipeline/net/http.py). Fragile by nature: an answer that isn't the CSV ("No data", a daily hit
limit, an HTML page) raises StooqUnavailable; the caller marks 'stooq' stale and falls back to a manual CSV in the
same format (imports/us_prices/<TICKER>.csv).

Bars are dated at the week's last trading day; they are keyed by that week's Friday, like prices_w everywhere."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from pipeline.net.http import HttpClient

STOOQ_CSV = "https://stooq.com/q/d/l/?s={symbol}&i=w"


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
        return parse_csv(self.http.get_bytes(csv_url(stooq_symbol(ticker)), timeout=30.0))
