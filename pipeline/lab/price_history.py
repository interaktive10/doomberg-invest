"""The Signal Lab's price history from Twelve Data (BRIEF §4.10.1, docs/SPEC_ISSUES.md 51; lab-prices.yml).

`python -m pipeline.lab.price_history --dir .cache/lab` resumes a download of month-end prices for every company the
Lab reads (run.lab_companies), with the files lab-prices.yml keeps in the private `lab-data-v1` release
(config/lab.yaml `prices`): the price asset (prices.write_month_csv) and the download's state (prices.DownloadState).

- Probe, once: the probe symbol's (AAPL's) daily series must reach config/lab.yaml `start`; if it doesn't, its monthly
  series must; if neither does, the download is blocked, with the reason, and asks nothing more.
- Each ticker is asked once per attempt (one credit): `ok` with its complete months (prices.complete_months),
  `no_such_symbol` (Twelve Data has no series for it; never asked again), or, after `max_attempts` failures, `error`.
- A run stops itself after `max_minutes` or `max_credits` (lab-prices.yml's job limit is 120 minutes, the free plan's
  day 800 credits), when Twelve Data says the day's credits are spent, or after MAX_FAILURES_IN_A_ROW failures in a
  row (Twelve Data is down or refuses the key: the rest of the run would bill minutes for nothing). The prices and the
  state are saved every `save_every` tickers and when it stops.
- `complete` once every ticker has a final status; then $GITHUB_OUTPUT gets complete=true, and lab-prices.yml
  dispatches the first Lab run and disables itself (blocked=true disables it too).
- Each run records a `lab_prices` runs row (the Lab page's progress line): ok when complete, partial while tickers
  remain, failed when blocked, with run.blocked_reason's text.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import psycopg

from pipeline.db import repo
from pipeline.lab import run
from pipeline.lab.prices import FINAL, DownloadState, MonthBar, TickerState, complete_months, write_month_csv
from pipeline.net.http import HttpClient
from pipeline.net.twelvedata import Close, TwelveDataClient, TwelveDataDayCredits
from pipeline.prices.source import NoSuchSymbol, PriceUnavailable
from pipeline.settings import REPO_ROOT, Settings

MAX_FAILURES_IN_A_ROW = 5  # as the weekly run's price stage (pipeline/signals/weekly.py)
RUN_STATUS = {"complete": "ok", "blocked": "failed"}  # runs.status; anything else is partial


class HistorySource(Protocol):
    """pipeline.net.twelvedata.TwelveDataClient, or a test's stand-in."""

    def daily(self, ticker: str) -> list[Close]: ...

    def monthly(self, ticker: str) -> list[Close]: ...


@dataclass(frozen=True)
class Limits:
    max_minutes: float = 90
    max_credits: int = 650
    max_attempts: int = 3
    save_every: int = 50

    @classmethod
    def of(cls, prices: Mapping[str, Any]) -> Limits:
        return cls(float(prices["max_minutes"]), int(prices["max_credits"]), int(prices["max_attempts"]),
                   int(prices["save_every"]))  # fmt: skip


@dataclass
class Outcome:
    state: DownloadState
    credits: int = 0  # requests this run made (one credit each)
    stopped: str | None = None  # minutes | credits | day_credits | failures | None (nothing left to ask)
    saved: list[int] = field(default_factory=list)  # tickers settled at each save

    def stats(self) -> dict[str, Any]:
        s = self.state
        return {"status": s.status, "interval": s.interval, "tickers": len(s.tickers), "ok": s.count("ok"),
                "no_such_symbol": s.count("no_such_symbol"), "error": s.count("error"), "pending": s.count("pending"),
                "credits": self.credits, "stopped": self.stopped}  # fmt: skip


def probe(source: HistorySource, symbol: str, reach: date) -> tuple[str | None, str | None, int]:
    """(interval, None, credits) for the first of daily and monthly whose series reaches `reach`, else (None, the
    reason, credits). A symbol Twelve Data doesn't know reaches nothing; any other failure is raised."""
    firsts: dict[str, date | None] = {}
    for interval, ask in (("1day", source.daily), ("1month", source.monthly)):
        try:
            closes = ask(symbol)
        except NoSuchSymbol:
            closes = []
        firsts[interval] = closes[0][0] if closes else None
        first = firsts[interval]
        if first is not None and first <= reach:
            return interval, None, len(firsts)
    daily, monthly = (str(firsts[k] or "nowhere") for k in ("1day", "1month"))
    return None, (f"{symbol}'s daily series starts {daily} and its monthly series {monthly}; the Lab needs prices "
                  f"from {reach} (config/lab.yaml start)"), len(firsts)  # fmt: skip


def download(
    source: HistorySource,
    tickers: Iterable[str],
    state_path: Path,
    prices_path: Path,
    today: date,
    reach: date,
    probe_symbol: str = "AAPL",
    limits: Limits | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    """One run of the download: resume the saved state, ask what is left within the limits, save."""
    limits = limits or Limits()
    t0 = clock()
    state = DownloadState.load(state_path) or DownloadState()
    for t in tickers:
        state.tickers.setdefault(t, TickerState())
    out = Outcome(state)
    batch: dict[str, list[MonthBar]] = {}

    def save() -> None:
        if batch:
            write_month_csv(prices_path, batch, append=True)
            batch.clear()
        state.save(state_path)
        out.saved.append(state.settled())

    if state.interval is None:
        try:
            interval, reason, used = probe(source, probe_symbol, reach)
        except TwelveDataDayCredits:
            out.stopped = "day_credits"
            save()
            return out
        out.credits += used
        state.interval, state.reason = interval, reason
        if interval is None:
            state.status = "blocked"
            save()
            return out
    fetch = source.daily if state.interval == "1day" else source.monthly
    state.status = "partial"
    queue = deque(sorted((t for t, s in state.tickers.items() if s.status not in FINAL),
                         key=lambda t: (state.tickers[t].attempts, t)))  # fmt: skip
    failures, since_save = 0, 0  # failures in a row
    while queue:
        if out.credits >= limits.max_credits:
            out.stopped = "credits"
        elif clock() - t0 >= limits.max_minutes * 60:
            out.stopped = "minutes"
        elif failures >= MAX_FAILURES_IN_A_ROW:
            out.stopped = "failures"
        if out.stopped:
            break
        ticker = queue.popleft()
        ts = state.tickers[ticker]
        try:
            closes = fetch(ticker)
        except TwelveDataDayCredits:
            out.stopped = "day_credits"  # not this ticker's fault: no attempt is counted
            break
        except NoSuchSymbol as e:
            ts.status, ts.error, failures = "no_such_symbol", str(e)[:200], 0
        except PriceUnavailable as e:
            ts.attempts, ts.error, failures = ts.attempts + 1, str(e)[:200], failures + 1
            if ts.attempts >= limits.max_attempts:
                ts.status = "error"
            else:
                queue.append(ticker)  # asked again after every ticker not yet asked
        else:
            batch[ticker] = complete_months(closes, today)
            ts.status, ts.error, failures = "ok", None, 0
        out.credits += 1
        since_save += 1
        if since_save >= limits.save_every:
            save()
            since_save = 0
    if state.settled() == len(state.tickers):
        state.status = "complete"
    save()
    return out


def finish(conn: psycopg.Connection[Any], run_id: UUID, out: Outcome, prices_path: Path, cfg: dict[str, Any]) -> None:
    """The lab_prices runs row: ok when complete, partial while tickers remain, failed when blocked, with the text
    the Lab itself prints (run.blocked_reason)."""
    s = out.state
    reason = run.blocked_reason(prices_path, s, cfg) if s.status == "blocked" else None
    repo.finish_run(conn, run_id, RUN_STATUS.get(s.status, "partial"), out.stats(), reason)


def github_output(**values: bool) -> None:
    """lab-prices.yml reads these (steps.download.outputs.*)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={str(v).lower()}\n" for k, v in values.items())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=REPO_ROOT / ".cache" / "lab", help="where the asset and state live")
    a = ap.parse_args(argv)
    cfg = run.lab_config()
    p = cfg["prices"]
    state_path, prices_path = a.dir / p["state"], a.dir / p["asset"]
    settings = Settings.from_env()
    client = TwelveDataClient(HttpClient(settings))
    with psycopg.connect(settings.database_url) as conn:
        kept, _ = run.lab_companies(conn, "us")
        tickers = sorted({c.ticker for c in kept if c.ticker})
        run_id = repo.start_run(conn, "lab_prices")
        conn.commit()
        try:
            out = download(client, tickers, state_path, prices_path, datetime.now(UTC).date(),
                           date.fromisoformat(str(cfg["start"])), str(p["probe"]), Limits.of(p))  # fmt: skip
        except BaseException as e:
            conn.rollback()
            repo.finish_run(conn, run_id, "failed", {}, f"{type(e).__name__}: {e}"[:2000])
            conn.commit()
            raise
        finish(conn, run_id, out, prices_path, cfg)
        conn.commit()
    s = out.state
    github_output(complete=s.status == "complete", blocked=s.status == "blocked")
    print(f"lab prices: {s.status} ({s.interval or 'no interval'}), {s.settled():,} of {len(s.tickers):,} tickers "
          f"settled ({s.count('ok'):,} ok, {s.count('no_such_symbol'):,} no such symbol, {s.count('error'):,} error), "
          f"{out.credits} credits, stopped: {out.stopped or 'nothing left'}")  # fmt: skip
    if s.status == "blocked":
        print(f"::warning::lab prices: {run.blocked_reason(prices_path, s, cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
