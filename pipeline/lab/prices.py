"""Month-end prices for the Signal Lab (BRIEF §4.10.1, docs/SPEC_ISSUES.md 51).

pipeline/lab/price_history.py downloads every company's daily closes from Twelve Data (monthly closes if the free plan's
daily history doesn't reach config/lab.yaml `start`) and keeps them as month bars in a private GitHub release asset
(`lab-data-v1`, §2.7), one row per ticker and month:

    ticker,month_end,close,high,low
    AAPL,2024-01-31,184.40,195.18,181.18

Each calendar month becomes one bar: the month's last close and its highest and lowest close (the 52-week high/low of
the legacy rules use closes); the current month isn't complete and is left out. A monthly series has one close a
month, so its high and low are that close. Twelve Data's closes are split-adjusted, not dividend-adjusted, so Lab
returns are price returns (§7 caveat 3).

The download's progress is a small JSON state next to the asset (DownloadState), so each run resumes where the last
one stopped.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

COLUMNS = ("ticker", "month_end", "close", "high", "low")
FINAL = ("ok", "no_such_symbol", "error")  # a ticker in one of these is never asked again


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


def month_bars(daily: Sequence[tuple[date, Decimal]]) -> list[MonthBar]:
    by: dict[date, list[tuple[date, Decimal]]] = {}
    for d, c in sorted(daily):
        by.setdefault(month_end(d), []).append((d, c))
    return [
        MonthBar(m, rows[-1][1], max(c for _, c in rows), min(c for _, c in rows)) for m, rows in sorted(by.items())
    ]


def complete_months(closes: Sequence[tuple[date, Decimal]], today: date) -> list[MonthBar]:
    """Month bars of daily (or monthly) closes, closed at each month's last close; the current month, still
    incomplete on `today`, is dropped."""
    return [b for b in month_bars(closes) if b.month_end < month_end(today)]


def _rows(bars: Mapping[str, Sequence[MonthBar]]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    for ticker, rows in bars.items():
        w.writerows((ticker, b.month_end.isoformat(), b.close, b.high, b.low) for b in rows)
    return out.getvalue()


def write_month_csv(path: Path, bars: Mapping[str, Sequence[MonthBar]], append: bool = False) -> None:
    """ticker,month_end,close,high,low rows, gzip-compressed when the name ends in .gz. With `append` the rows are
    added (a further gzip member) to a copy of the file that then replaces it, so a run stopped mid-write keeps the
    file as it was."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fresh = not (append and path.exists())
    data = ((",".join(COLUMNS) + "\n" if fresh else "") + _rows(bars)).encode("utf-8")
    if path.suffix == ".gz":
        data = gzip.compress(data)  # one member; gzip readers read a file of several members as one stream
    if fresh:
        tmp.write_bytes(data)
    else:
        shutil.copyfile(path, tmp)
        with tmp.open("ab") as fh:
            fh.write(data)
    os.replace(tmp, path)


def read_month_csv(text: str) -> dict[str, list[MonthBar]]:
    """ticker,month_end,close[,high,low] rows (F-LAB, manual imports and the Lab's price asset); a month a ticker has
    twice keeps its last row (a download resumed after a stop may save a ticker again)."""
    out: dict[str, dict[date, MonthBar]] = {}
    for r in csv.DictReader(io.StringIO(text)):
        close = Decimal(r["close"])
        high, low = Decimal(r.get("high") or close), Decimal(r.get("low") or close)
        m = date.fromisoformat(r["month_end"])
        out.setdefault(r["ticker"], {})[m] = MonthBar(m, close, high, low)
    return {t: [bars[m] for m in sorted(bars)] for t, bars in out.items()}


def read_prices(path: Path, tickers: Iterable[str] | None = None) -> dict[str, list[MonthBar]]:
    """The Lab's month bars (the release asset write_month_csv builds), for the wanted tickers (e.g. "AAPL", "BRK-B")
    or all; tickers without rows are left out."""
    with gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8") as fh:
        bars = read_month_csv(fh.read())
    if tickers is None:
        return bars
    return {t: bars[t] for t in dict.fromkeys(tickers) if t in bars}


@dataclass
class TickerState:
    status: str = "pending"  # pending | ok | no_such_symbol | error (FINAL: never asked again)
    attempts: int = 0  # failed requests so far (a spent day of credits isn't one)
    error: str | None = None  # the last failure


@dataclass
class DownloadState:
    """The progress of price_history's download, saved as JSON next to the price asset."""

    interval: str | None = None  # "1day" or "1month", chosen once by the probe
    status: str = "pending"  # pending | partial | complete | blocked
    reason: str | None = None  # why the probe blocked the download
    tickers: dict[str, TickerState] = field(default_factory=dict)

    def count(self, *statuses: str) -> int:
        return sum(t.status in statuses for t in self.tickers.values())

    def settled(self) -> int:
        """Tickers with a final status: asked until they answered, had no series, or failed MAX_ATTEMPTS times."""
        return self.count(*FINAL)

    @classmethod
    def load(cls, path: Path) -> DownloadState | None:
        if not path.exists():
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
        tickers = {str(k): TickerState(**v) for k, v in (doc.get("tickers") or {}).items()}
        return cls(interval=doc.get("interval"), status=str(doc.get("status") or "pending"), reason=doc.get("reason"),
                   tickers=tickers)  # fmt: skip

    def save(self, path: Path) -> None:
        """Written to a temporary file that then replaces the state, so a stopped run never leaves half a file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(self), sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
