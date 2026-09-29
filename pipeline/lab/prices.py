"""Month-end prices for the Signal Lab (BRIEF §4.10.1).

The Stooq bulk daily file (`d_us_txt.zip`: it has a CAPTCHA, so Manzoor downloads it once and keeps it as a private
GitHub release asset, §2.7) holds one text file per symbol, e.g. `data/daily/us/nasdaq stocks/1/aapl.us.txt`:

    <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
    AAPL.US,D,19840907,000000,0.100763,0.101999,0.0997,0.100763,97676604,0

Read by column name. Each calendar month becomes one bar: the month's last close and its highest and lowest close
(the 52-week high/low of the legacy rules use closes). Stooq's closes are split-adjusted, not dividend-adjusted, so
Lab returns are price returns (§7 caveat 3).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass(frozen=True)
class MonthBar:
    month_end: date  # the calendar month's last day
    close: Decimal  # the month's last close
    high: Decimal  # the month's highest close
    low: Decimal  # the month's lowest close


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def add_months(d: date, n: int) -> date:
    """The month-end `n` months after the month-end `d`."""
    k = d.year * 12 + d.month - 1 + n
    return month_end(date(k // 12, k % 12 + 1, 1))


def month_ends(start: date, end: date) -> list[date]:
    out, m = [], month_end(start)
    while m <= end:
        out.append(m)
        m = add_months(m, 1)
    return out


def parse_daily(text: str) -> list[tuple[date, Decimal]]:
    """(day, close) rows of one Stooq daily file, by column name; unparseable rows are skipped."""
    reader = csv.DictReader(io.StringIO(text))
    names = {(h or "").strip().strip("<>").upper(): h for h in (reader.fieldnames or [])}
    if "DATE" not in names or "CLOSE" not in names:
        raise ValueError(f"not a Stooq daily file (header {reader.fieldnames})")
    out: list[tuple[date, Decimal]] = []
    for r in reader:
        try:
            day = datetime.strptime((r[names["DATE"]] or "").strip(), "%Y%m%d").date()
            close = Decimal((r[names["CLOSE"]] or "").strip())
        except (ValueError, InvalidOperation):
            continue
        if close > 0:
            out.append((day, close))
    return out


def month_bars(daily: Sequence[tuple[date, Decimal]]) -> list[MonthBar]:
    by: dict[date, list[tuple[date, Decimal]]] = {}
    for d, c in sorted(daily):
        by.setdefault(month_end(d), []).append((d, c))
    return [
        MonthBar(m, rows[-1][1], max(c for _, c in rows), min(c for _, c in rows)) for m, rows in sorted(by.items())
    ]


def read_bulk(path: Path, tickers: Iterable[str], suffix: str = ".us.txt") -> dict[str, list[MonthBar]]:
    """Month bars for the wanted tickers (e.g. "AAPL", "BRK-B") from the bulk zip; tickers without a file are left
    out."""
    want = {t.lower() + suffix: t for t in tickers}
    out: dict[str, list[MonthBar]] = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            ticker = want.get(name.rsplit("/", 1)[-1].lower())
            if ticker is not None:
                out[ticker] = month_bars(parse_daily(z.read(name).decode("utf-8", errors="replace")))
    return out


def read_month_csv(text: str) -> dict[str, list[MonthBar]]:
    """ticker,month_end,close[,high,low] rows (F-LAB and manual imports)."""
    out: dict[str, list[MonthBar]] = {}
    for r in csv.DictReader(io.StringIO(text)):
        close = Decimal(r["close"])
        high, low = Decimal(r.get("high") or close), Decimal(r.get("low") or close)
        out.setdefault(r["ticker"], []).append(MonthBar(date.fromisoformat(r["month_end"]), close, high, low))
    return {t: sorted(bars, key=lambda b: b.month_end) for t, bars in out.items()}
