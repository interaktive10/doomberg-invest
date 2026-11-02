"""Recent daily closes for Winners and Themes (2026-11-02, Manzoor: "This year's moves run to Wed, Sep 30 - why does it
say sep 30? come on. everything should be latest"; docs/SPEC_ISSUES.md 75).

Winners' US prices are the Signal Lab's month-end download, which completes once and stops; India's are the weekly
bhavcopy closes. Neither reaches the last trading day. This keeps each name's latest few daily closes in the database
(pipeline_state `recent_closes`) and winners.py / themes.py append them to those series:

- India: the latest trading day's bhavcopy, one file for every listed stock (one request; the weekly fetch's code).
- US: Twelve Data's free plan answers 8 symbols a minute and 800 a day, so a run asks at most `--us-budget` tickers
  (default 700, a day's credits with room for the Saturday run), stalest first; every priced US name is fresh within
  about three trading days. Each answer is the last KEEP daily closes, so a name refreshed earlier still has a close
  on the day Winners measures to.

Only what is missing is fetched; nothing here calls an LLM. End-of-day closes only (no intraday data).
`python -m pipeline.reports.closes [--us-budget 700] [--minutes 100]`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.db import repo
from pipeline.db import state as db_state
from pipeline.settings import Settings

STATE = "recent_closes"
KEEP = 10  # daily closes kept per name
US_BUDGET = 700
MINUTES = 100.0

Closes = list[tuple[date, Decimal]]


@dataclass
class Recent:
    """Each name's latest daily closes, oldest first: US by ticker, India by NSE symbol."""

    us: dict[str, Closes] = field(default_factory=dict)
    india: dict[str, Closes] = field(default_factory=dict)

    @classmethod
    def from_json(cls, body: bytes) -> Recent:
        doc = json.loads(body)

        def side(d: Mapping[str, Any]) -> dict[str, Closes]:
            return {k: [(date.fromisoformat(a), Decimal(str(b))) for a, b in v] for k, v in d.items()}

        return cls(side(doc.get("us") or {}), side(doc.get("in") or {}))

    def to_json(self) -> bytes:
        def side(d: Mapping[str, Closes]) -> dict[str, list[list[str]]]:
            return {k: [[a.isoformat(), str(b)] for a, b in v] for k, v in d.items()}

        return json.dumps({"us": side(self.us), "in": side(self.india)}).encode()


def load(conn: psycopg.Connection[Any]) -> Recent:
    stored = db_state.get(conn, STATE)
    return Recent.from_json(stored.body) if stored is not None else Recent()


def save(conn: psycopg.Connection[Any], recent: Recent) -> None:
    db_state.put(conn, STATE, recent.to_json())


def merge(old: Closes, new: Sequence[tuple[date, Decimal]], keep: int = KEEP) -> Closes:
    """Old and new closes by date (a new one wins), the latest `keep`, oldest first."""
    by = dict(old)
    by.update(new)
    return sorted(by.items())[-keep:]


Series = Sequence[tuple[date, Decimal]]


def extend(series: Series, recent: Series) -> list[tuple[date, Decimal]]:
    """A month-end or week-end series with the recent daily closes after its last date appended."""
    last = series[-1][0] if series else date.min
    return [*series, *((d, c) for d, c in recent if d > last)]


def stalest(tickers: Sequence[str], recent: Mapping[str, Closes], budget: int) -> list[str]:
    """The `budget` tickers to ask today: never asked first, then the oldest latest close; ties by ticker."""
    return sorted(tickers, key=lambda t: (recent[t][-1][0] if recent.get(t) else date.min, t))[:budget]


@dataclass
class Stats:
    us_asked: int = 0
    us_ok: int = 0
    us_failed: int = 0
    us_stopped: str = ""
    india_day: date | None = None
    india_rows: int = 0
    notes: list[str] = field(default_factory=list)


SAVE_EVERY = 100  # tickers between saves, so a run cut off by the job's limit keeps what it fetched


def refresh_us(ask: Callable[[str], Sequence[tuple[date, Decimal]]], tickers: Sequence[str], recent: Recent,
               budget: int, minutes: float, stats: Stats, clock: Callable[[], float] = time.monotonic,
               save: Callable[[], None] | None = None) -> None:  # fmt: skip
    """Ask the stalest `budget` tickers for their latest daily closes, until the time or the day's credits run out;
    `save` every SAVE_EVERY answers."""
    from pipeline.net.twelvedata import TwelveDataDayCredits, TwelveDataUnavailable

    t0 = clock()
    for t in stalest(tickers, recent.us, budget):
        if clock() - t0 > minutes * 60:
            stats.us_stopped = f"past {minutes:.0f} minutes"
            break
        stats.us_asked += 1
        try:
            closes = ask(t)
        except TwelveDataDayCredits:
            stats.us_stopped = "the day's credits are spent"
            break
        except TwelveDataUnavailable:
            stats.us_failed += 1
            continue
        if closes:
            recent.us[t] = merge(recent.us.get(t, []), closes)
            stats.us_ok += 1
            if save is not None and stats.us_ok % SAVE_EVERY == 0:
                save()


def refresh_india(rows: Sequence[Any], day: date | None, recent: Recent, stats: Stats) -> None:
    """The latest trading day's bhavcopy rows (pipeline.india.bhavcopy.BhavRow) into each symbol's closes."""
    stats.india_day = day
    for r in rows:
        if r.close is not None and r.close > 0:
            recent.india[r.symbol] = merge(recent.india.get(r.symbol, []), [(r.trade_date, r.close)])
            stats.india_rows += 1


def us_tickers(conn: psycopg.Connection[Any]) -> list[str]:
    """The US tickers Winners and Themes can use: those in the universe with a month-end history (the Lab's price
    file); a credit spent on any other buys nothing."""
    from pipeline.reports.winners import us_series

    cs = [c for c in repo.companies(conn, market="us", in_universe=True) if c.ticker]
    priced = us_series(conn, cs)
    return sorted({c.ticker for c in cs if c.id in priced and c.ticker})


def upcoming_friday(today: date) -> date:
    return today + timedelta(days=(4 - today.weekday()) % 7)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--us-budget", type=int, default=US_BUDGET, help="US tickers to ask at most (one credit each)")
    ap.add_argument("--minutes", type=float, default=MINUTES, help="stop asking US tickers after this long")
    ap.add_argument("--skip-us", action="store_true")
    ap.add_argument("--skip-india", action="store_true")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    today = datetime.now(UTC).date()
    stats = Stats()
    with psycopg.connect(settings.database_url) as conn:
        recent = load(conn)
        if not a.skip_india:
            from pipeline.india import manual_import
            from pipeline.india.bhavcopy import fetch_week
            from pipeline.net.bse import BseClient
            from pipeline.net.http import HttpClient
            from pipeline.net.nse import NseClient

            http = HttpClient(settings)
            # the latest trading day: the week's files from Friday back, so a weekday before Friday finds today's
            rows, _, day, notes = fetch_week(NseClient(http), BseClient(http), upcoming_friday(today),
                                             manual_import.IMPORTS_DIR)  # fmt: skip
            stats.notes += notes
            refresh_india(rows, day, recent, stats)
            save(conn, recent)
            conn.commit()
        if not a.skip_us and settings.twelvedata_api_key:
            from pipeline.net.http import HttpClient
            from pipeline.net.twelvedata import TwelveDataClient

            client = TwelveDataClient(HttpClient(settings))

            def checkpoint() -> None:
                save(conn, recent)
                conn.commit()

            refresh_us(client.recent, us_tickers(conn), recent, a.us_budget, a.minutes, stats, save=checkpoint)
            save(conn, recent)
            conn.commit()
        elif not a.skip_us:
            stats.notes.append("TWELVEDATA_API_KEY is not set: US closes not refreshed")
    fresh = sum(1 for v in recent.us.values() if v and (today - v[-1][0]).days <= 4)
    stopped = f" (stopped: {stats.us_stopped})" if stats.us_stopped else ""
    print(f"closes: India {stats.india_rows} names on {stats.india_day}; US asked {stats.us_asked}, "
          f"{stats.us_ok} answered, {stats.us_failed} failed{stopped}; "
          f"US names with a close in the last 4 days: {fresh} of {len(recent.us)}")  # fmt: skip
    for n in stats.notes[:5]:
        print(f"  note: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
