"""India history loader (docs/SPEC_ISSUES.md 55, part 2). `python -m pipeline.india.history [--minutes N]`.

India could never be scored on more than a few quarters: its results history came only from SEBI Integrated Filing
(FY2025 Q4 onwards), queued 60 companies a run and fetched oldest first, and its prices only from the weeks India ran
(4 by October 2026), so C1, C3 and every Gap were unknown. This loader fills the history once, resumably, at NSE's
one request every 3 s (the client's limit), over as many india-backfill.yml runs as it takes:

1. **Prices:** each of the last PRICE_WEEKS Fridays (before today's) whose India prices aren't stored yet: the week's
   last trading-day bhavcopy (bhavcopy.fetch_week asks BSE whether a day traded, so NSE is never asked for a holiday)
   -> prices_w, and the NIFTY 50/500 closes. 104 weeks: C3 reads the close 52 weeks back, C1 wants at least 52 weeks
   of valuations.
2. **Filings, company by company** (a company is finished before the next starts): live research names first, then
   the most traded (mean close x volume over the last 4 stored weeks), so the liquid names are complete early. For
   each, every results filing from HISTORY_FROM in NSE's integrated-filing listing and in its legacy listing (quarters
   before FY2025 Q4), the consolidated one preferred -> the results store and fundamentals_q (results_xbrl.build_rows:
   a Q4 row's H2 cash flow is FY - H1, so whole years); then its shareholding patterns from SHP_FROM -> ownership_q
   (S8-IN reads three consecutive quarters).
3. Done when every week and company is: `complete=true` in $GITHUB_OUTPUT, and india-backfill.yml switches itself
   off (until then, with `stale=false`, it starts its next run at once). A company that fails (its own listing or
   file, or NSE stopping on it after answering other requests this run; never the clock) goes to the back of the
   queue, and after MAX_TRIES failures is left to the weekly run's own history queue, so one bad company can never
   hold the others up.

The state is the India weekly state (weekly.State, pipeline_state `in_weekly`: the results store, the files read,
`history_done`), saved to the database every SAVE_EVERY_S and at the end, so a stopped run loses at most that much;
each company's rows are committed once it is read, each price week once it is stored. While a company is read its
store keeps every year from HISTORY_FROM; once it is done the store is trimmed to weekly.KEEP_YEARS. A company started
again re-reads the filings its store lacks (a weekly run in between may have trimmed them).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
import psycopg

from pipeline.db import repo
from pipeline.db import state as db_state
from pipeline.db.models import Company
from pipeline.india import bhavcopy, manual_import
from pipeline.india.results_xbrl import (
    LEGACY_BEFORE,
    company_listing_path,
    legacy_listing_path,
    load_ind_as_map,
    parse_legacy_listing,
    preferred,
)
from pipeline.india.shareholding import parse_listing as parse_shp_listing
from pipeline.india.weekly import (
    SHP_API,
    IndiaWeeklyStats,
    State,
    _listing_json,
    _shp_listing_json,
    fetch_results,
    fetch_shareholding,
    keep_years,
    last_friday,
    read_pages,
    write_index_closes,
    write_prices,
    write_results,
)
from pipeline.net.bse import BseClient
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.settings import REPO_ROOT, Settings

HISTORY_FROM = date(2022, 6, 30)  # FY2023 Q1 on: 17 quarters by September 2026 (S2's 16 and every YoY check)
HISTORY_YEARS = 10  # the store keeps every year from HISTORY_FROM while a company is read
SHP_FROM = date(2026, 3, 31)  # with June and September 2026: the three consecutive quarters S8-IN reads
PRICE_WEEKS = 104
MIN_WEEK_ROWS = 1000  # a stored week with fewer India prices than this is read again (about 2,000 a week)
MAX_TRIES = 3
SAVE_EVERY_S = 15 * 60
MAX_ERRORS = 200  # kept in the runs row (errors_total counts them all)
STATE_NAME = "in_weekly"
TIME_BUDGET_MIN = 320  # india-backfill.yml's job has 345 minutes


@dataclass
class HistoryStats:
    price_weeks_stored: int = 0
    price_weeks_left: int = 0
    companies_done: int = 0
    companies_left: int = 0
    companies_given_up: int = 0
    results_fetched: int = 0
    fundamentals_rows: int = 0
    shp_fetched: int = 0
    ownership_rows: int = 0
    complete: bool = False
    nse_stale: bool = False
    errors_total: int = 0
    errors: list[str] = field(default_factory=list)

    def add_errors(self, errors: Sequence[str]) -> None:
        self.errors_total += len(errors)
        self.errors = [*self.errors, *errors][:MAX_ERRORS]

    def note(self, sink: IndiaWeeklyStats) -> None:
        """Move the counts of a weekly-stats sink (the shared fetch and write helpers fill one) into these."""
        self.results_fetched += sink.results_fetched
        self.fundamentals_rows += sink.fundamentals_rows
        self.shp_fetched += sink.shp_fetched
        self.ownership_rows += sink.ownership_rows
        self.add_errors(sink.errors)
        sink.results_fetched = sink.fundamentals_rows = sink.shp_fetched = sink.ownership_rows = 0
        sink.errors = []


def fridays(today: date, weeks: int) -> list[date]:
    """The last `weeks` Fridays before today, newest first (today's week, Friday included, is the weekly run's)."""
    last = last_friday(today - timedelta(days=1))
    return [last - timedelta(weeks=k) for k in range(weeks)]


def load_prices(
    conn: psycopg.Connection[Any], nse: NseClient, bse: BseClient, state: State, weeks: Sequence[date],
    companies: Sequence[Company], stats: HistoryStats, imports: Path, root: Path, commit: Callable[[], None],
) -> None:  # fmt: skip
    """Each week not stored yet, newest first: its bhavcopy -> prices_w (and the NIFTY closes when NSE gave it). A week
    neither exchange has a file for (every weekday a holiday) is recorded as read, with a note."""
    if not weeks:
        return
    stored = repo.price_week_counts(conn, "in", min(weeks), max(weeks))
    sink = IndiaWeeklyStats(friday="history")

    def todo(friday: date) -> bool:
        return stored.get(friday, 0) < MIN_WEEK_ROWS and friday.isoformat() not in state.history_prices

    for friday in [f for f in weeks if todo(f)]:
        if nse.unavailable:
            break
        rows, source, day, notes = bhavcopy.fetch_week(nse, bse, friday, imports)
        if not rows and nse.unavailable:  # NSE stopped answering: the week stays to do
            break
        if rows:
            with conn.transaction():
                write_prices(conn, companies, rows, source, friday)
                if day is not None and source == "NSE":
                    write_index_closes(conn, nse, day, sink, root)
            commit()
            stats.price_weeks_stored += 1
        else:
            sink.errors.append(f"prices {friday}: no bhavcopy for the week ({'; '.join(notes)})"[:300])
        state.history_prices.add(friday.isoformat())
    stats.note(sink)
    stats.price_weeks_left = sum(1 for f in weeks if todo(f))


def company_items(nse: NseClient, symbol: str, sink: IndiaWeeklyStats) -> list[dict[str, Any]] | None:
    """Every results filing of one company from HISTORY_FROM, from the integrated-filing listing and the legacy one,
    the consolidated filing preferred, as queue items; None when a listing couldn't be read in full."""
    integrated, error = read_pages(nse, partial(company_listing_path, symbol))
    if error is not None:
        sink.errors.append(f"results history {symbol}: {error}"[:300])
        return None
    try:
        legacy = parse_legacy_listing(nse.api(legacy_listing_path(symbol)))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        sink.errors.append(f"legacy results {symbol}: {type(e).__name__}: {e}"[:300])
        return None
    rows = [x for x in preferred(integrated) if x.period_end >= HISTORY_FROM]
    rows += [x for x in preferred(legacy) if HISTORY_FROM <= x.period_end < LEGACY_BEFORE]
    return [_listing_json(x, backfill=True) for x in rows if x.symbol == symbol]


def load_company(
    conn: psycopg.Connection[Any], nse: NseClient, state: State, symbol: str, ids: Mapping[str, UUID],
    sink: IndiaWeeklyStats, ind_as: Mapping[str, Sequence[str]],
) -> bool:  # fmt: skip
    """One company's results and shareholding history. True when every listed file was read (or found unreadable)."""
    items = company_items(nse, symbol, sink)
    if items is None:
        return False
    stored = {str(s.get("url")) for s in state.results_store.get(symbol, [])}
    todo = [q for q in items if str(q["xbrl_url"]) not in stored]
    state.results_seen -= {str(q["seq_id"]) for q in todo}  # so "seen" below means read by this call
    touched = fetch_results(nse, state, todo, len(todo), sink, ind_as, years=HISTORY_YEARS)
    with conn.transaction():
        write_results(conn, state, touched, ids, sink)
    if any(str(q["seq_id"]) not in state.results_seen for q in todo):
        return False  # a download was blocked or the time ran out: the rest next run
    try:
        listed = parse_shp_listing(nse.api(f"{SHP_API}&symbol={quote(symbol, safe='')}"))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        sink.errors.append(f"shareholding history {symbol}: {type(e).__name__}: {e}"[:300])
        return False
    patterns = [_shp_listing_json(x) for x in listed
                if x.symbol == symbol and x.quarter_end >= SHP_FROM and x.xbrl_url not in state.shp_seen]  # fmt: skip
    own, pledges = fetch_shareholding(nse, state, len(patterns), ids, sink, items=patterns)
    with conn.transaction():
        repo.upsert_ownership(conn, own)
        repo.insert_insider_events(conn, pledges)
    sink.ownership_rows += len(own)
    if any(str(p["xbrl_url"]) not in state.shp_seen for p in patterns):
        return False
    if symbol in state.results_store:
        state.results_store[symbol] = keep_years(state.results_store[symbol])
    return True


def ordered(
    companies: Sequence[Company], research: Collection[UUID], turnover: Mapping[UUID, Decimal],
    symbols: Collection[str] | None = None, tries: Mapping[str, int] | None = None,
) -> list[Company]:  # fmt: skip
    """The companies to read, in order: live research names (scored even outside the universe), then the universe's
    most traded first, a company that failed before (`tries`) after the others; with `symbols`, only those."""

    def rank(c: Company) -> tuple[bool, bool, Decimal, str]:
        assert c.id is not None
        failed = (tries or {}).get(c.nse_symbol or "", 0) > 0
        return c.id not in research, failed, -turnover.get(c.id, Decimal(0)), c.nse_symbol or ""

    keep = [c for c in companies if c.id is not None and (c.in_universe or c.id in research)]
    return sorted((c for c in keep if symbols is None or c.nse_symbol in symbols), key=rank)


def run_history(
    conn: psycopg.Connection[Any], nse: NseClient, bse: BseClient, today: date, state_path: Path | None,
    save: Callable[[State], None], price_weeks: int = PRICE_WEEKS, imports: Path = manual_import.IMPORTS_DIR,
    root: Path = REPO_ROOT, clock: Callable[[], float] = time.monotonic, limit: int | None = None,
    symbols: Collection[str] | None = None, commit: Callable[[], None] | None = None,
) -> HistoryStats:  # fmt: skip
    """The prices, then the companies in order, until NSE's time budget (nse.deadline) or its patience (stale) runs
    out, or `limit` companies were tried; `save(state)` after the prices, every SAVE_EVERY_S and at the end. Each
    price week and each company is committed (`commit`: conn.commit; a test's no-op keeps its transaction). With
    `symbols` only those companies are read, and the run is never `complete`."""
    commit = commit or conn.commit
    stats = HistoryStats()
    state = State.load(state_path)
    listed = [c for c in repo.companies(conn, market="in")
              if c.id is not None and c.nse_symbol and c.excluded_reason != repo.SNAPSHOT_OUT["in"]]  # fmt: skip
    load_prices(conn, nse, bse, state, fridays(today, price_weeks), listed, stats, imports, root, commit)
    save(state)
    order = ordered(listed, repo.research_company_ids(conn), repo.latest_turnover(conn, "in"), symbols,
                    state.history_tries)  # fmt: skip
    ids = {c.nse_symbol: c.id for c in listed if c.nse_symbol and c.id}
    ind_as = load_ind_as_map(root)
    sink = IndiaWeeklyStats(friday="history")

    def open_(symbol: str) -> bool:
        return symbol not in state.history_done and state.history_tries.get(symbol, 0) < MAX_TRIES

    saved_at, tried = clock(), 0
    for c in order:
        symbol = c.nse_symbol or ""
        if not open_(symbol):
            continue
        if nse.unavailable or (limit is not None and tried >= limit):
            break
        tried, answered = tried + 1, nse.answered
        if load_company(conn, nse, state, symbol, ids, sink, ind_as):
            state.history_done.add(symbol)
            state.backfilled.add(symbol)  # the weekly run's own history queue skips it
            state.history_tries.pop(symbol, None)
            stats.companies_done += 1
        elif not nse.out_of_time and (not nse.stale or answered > 0):  # not the clock, nor NSE refusing everything
            state.history_tries[symbol] = state.history_tries.get(symbol, 0) + 1
            if state.history_tries[symbol] >= MAX_TRIES:
                sink.errors.append(f"history {symbol}: left to the weekly run after {MAX_TRIES} runs")
        commit()
        stats.note(sink)
        if clock() - saved_at >= SAVE_EVERY_S:
            save(state)
            saved_at = clock()
    names = [c.nse_symbol or "" for c in order]
    stats.companies_left = sum(1 for s in names if open_(s))
    stats.companies_given_up = sum(1 for s in names if s not in state.history_done and not open_(s))
    stats.nse_stale = nse.stale
    stats.complete = symbols is None and stats.companies_left == 0 and stats.price_weeks_left == 0
    save(state)
    return stats


def saver(
    conn: psycopg.Connection[Any], path: Path, commit: Callable[[], None] | None = None
) -> Callable[[State], None]:
    """Save the state file, then its copy in the database, committed at once (a run killed later keeps it)."""
    done = commit or conn.commit

    def save(state: State) -> None:
        state.save(path)
        db_state.put(conn, STATE_NAME, path.read_bytes())
        done()

    return save


def github_output(path: str | None, stats: HistoryStats) -> None:
    """complete= (india-backfill.yml switches itself off) and stale= (with complete=false: start the next run)."""
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for key, value in (("complete", stats.complete), ("stale", stats.nse_stale)):
                fh.write(f"{key}={'true' if value else 'false'}\n")


def main(argv: Sequence[str] | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=TIME_BUDGET_MIN, help="time budget for NSE requests")
    ap.add_argument("--price-weeks", type=int, default=PRICE_WEEKS)
    ap.add_argument("--companies", type=int, default=None, help="try at most this many companies")
    ap.add_argument("--symbols", default=None, help="only these NSE symbols, comma-separated (never `complete`)")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    http = HttpClient(settings)
    nse, bse = NseClient(http), BseClient(http)
    nse.deadline = nse.clock() + a.minutes * 60
    path = settings.cache_dir / "in" / "weekly_state.json"
    symbols = None if a.symbols is None else {s.strip().upper() for s in a.symbols.split(",") if s.strip()}
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "in_history") as run:
        stats = run_history(conn, nse, bse, clock().date(), path, saver(conn, path), a.price_weeks,
                            limit=a.companies, symbols=symbols)  # fmt: skip
        if nse.stale:
            repo.mark_source_error(conn, "nse", "stale: " + "; ".join(nse.blocks[-3:]), stale=True)
        run.update(stats.__dict__)
    github_output(os.environ.get("GITHUB_OUTPUT"), stats)
    print(
        f"india history: price weeks {stats.price_weeks_stored} stored, {stats.price_weeks_left} left; companies "
        f"{stats.companies_done} done, {stats.companies_left} left, {stats.companies_given_up} left to the weekly run; "
        f"results {stats.results_fetched}, shareholding {stats.shp_fetched}, errors {stats.errors_total}, "
        f"nse stale {stats.nse_stale}, complete {stats.complete}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
