"""Weekly bars, keyed by their week's Friday like prices_w everywhere, and the manual price import's CSV format
(imports/us_prices/<TICKER>.csv, BRIEF §4.4's fallback; the F-PX fixtures): Date,Open,High,Low,Close,Volume, a bar
dated at its week's last trading day, the format Stooq's weekly CSV had. Twelve Data (pipeline/net/twelvedata.py) is
the only price source that is asked (docs/SPEC_ISSUES.md 38, 52)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


class NotWeeklyCsv(Exception):
    """A manual import that isn't a weekly price CSV."""


@dataclass(frozen=True)
class Bar:
    week_end: date
    close: Decimal
    volume: Decimal | None


def friday_of(d: date) -> date:
    """The Friday of d's week (Saturday and Sunday belong to the Friday before)."""
    return d + timedelta(days=4 - d.weekday()) if d.weekday() <= 4 else d - timedelta(days=d.weekday() - 4)


def parse_csv(body: bytes) -> list[Bar]:
    text = body.decode("utf-8-sig", "replace").strip()
    if not text.lower().startswith("date,"):
        raise NotWeeklyCsv(text[:120] or "empty file")
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
        raise NotWeeklyCsv("CSV without price rows")
    return [bars[k] for k in sorted(bars)]
