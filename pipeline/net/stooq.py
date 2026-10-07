"""Stooq's weekly CSV format (Date,Open,High,Low,Close,Volume; a bar dated at its week's last trading day): the format
of a manual price import (imports/us_prices/<TICKER>.csv, BRIEF §4.4's fallback) and of the F-PX fixtures. Stooq
itself is no longer asked: since 2026 its CSV needs a CAPTCHA-issued apikey (the first live run, 2026-09-29, got an
HTML page for every symbol), and US prices come from Yahoo (pipeline/net/yahoo.py, docs/SPEC_ISSUES.md 37).

Bars are keyed by their week's Friday, like prices_w everywhere."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


class StooqUnavailable(Exception):
    """Not a weekly CSV (a manual import that isn't one, or one of the pages Stooq answered instead)."""


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
