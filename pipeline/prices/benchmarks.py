"""Benchmarks (BRIEF §4.4, config/context.yaml `benchmarks`) -> benchmarks_w, keyed by the week's Friday.

- US: ^spx and the sector ETFs from the US price source's weekly bars (pipeline/prices/source.py: Twelve Data, which
  asks SPY for ^spx, or Yahoo, which asks ^GSPC; ten years come with each download). Rows keep the symbols
  config/context.yaml names.
- India: NIFTY 50 and NIFTY 500 from NSE's daily index-close file for the week's last trading day, fetched by the
  India weekly run next to the bhavcopy (it knows which day traded). History builds up week by week."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from pipeline.db.models import BenchmarkW
from pipeline.net.stooq import Bar, friday_of
from pipeline.prices.source import PriceUnavailable, WeeklySource

NSE_INDEX_CLOSE = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{day:%d%m%Y}.csv"
US_HISTORY_WEEKS = 520  # C1 looks back up to 10 years; C3 needs 52 weeks


def index_close_url(day: date) -> str:
    return NSE_INDEX_CLOSE.format(day=day)


def parse_index_closes(raw: bytes) -> dict[str, tuple[date, Decimal]]:
    """Upper-cased index name -> (date, closing value) from NSE's ind_close_all file."""
    out: dict[str, tuple[date, Decimal]] = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))):
        try:
            name = row["Index Name"].strip().upper()
            day = datetime.strptime(row["Index Date"].strip(), "%d-%m-%Y").date()
            out[name] = (day, Decimal(row["Closing Index Value"].strip()))
        except (KeyError, ValueError, InvalidOperation, AttributeError):
            continue
    return out


def india_rows(raw: bytes, names: Sequence[str]) -> list[BenchmarkW]:
    closes = parse_index_closes(raw)
    return [
        BenchmarkW(symbol=n, week_end=friday_of(closes[n.upper()][0]), close=closes[n.upper()][1])
        for n in names
        if n.upper() in closes
    ]


def us_rows(bars: Sequence[Bar], symbol: str, week: date, weeks: int = US_HISTORY_WEEKS) -> list[BenchmarkW]:
    start = week - timedelta(weeks=weeks)
    return [BenchmarkW(symbol=symbol, week_end=b.week_end, close=b.close) for b in bars if start < b.week_end <= week]


def fetch_us(source: WeeklySource, symbols: Sequence[str], week: date) -> tuple[list[BenchmarkW], list[str]]:
    rows: list[BenchmarkW] = []
    errors: list[str] = []
    for s in symbols:
        try:
            rows += us_rows(source.weekly(s), s, week)
        except (PriceUnavailable, OSError) as e:
            errors.append(f"benchmark {s}: {type(e).__name__}: {e}"[:200])
        except Exception as e:  # noqa: BLE001 — httpx errors and the like: one symbol never stops the run
            errors.append(f"benchmark {s}: {type(e).__name__}: {e}"[:200])
    return rows, errors
