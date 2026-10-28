"""India weekly run (BRIEF §2.1 "weekly", §4.3, §4.4 India prices). `python -m pipeline.india.weekly [--friday D]`.

1. Universe: the NSE securities list (EQ series; main board, so SME is out) and the ASM/GSM surveillance lists.
2. Prices: the week's last trading-day bhavcopy -> prices_w for every EQ company (ASM/GSM ones included: in_universe
   decides scoring only, and a gap in their history would break C1/C3 and split detection; review F7). NSE first;
   when NSE is stale (3 consecutive blocks or failed requests) or has no file, BSE's bhavcopy for the same day
   (matched by ISIN); when both fail, the manual CSV imports in imports/. A day that neither exchange has is a
   holiday: the run walks back to Thursday etc. Universe and prices are committed before any XBRL download.
3. Results: integrated-filing results XBRL (consolidated preferred) -> fundamentals_q (results_xbrl.py). The listing
   is read from the last complete listing (a cursor in the state, with a 2-day overlap) to the Friday, every page,
   so a blocked week is caught up the next week (review F3).
4. Shareholding: quarterly patterns -> ownership_q (shareholding.py), and pledge changes -> insider_events. Listed
   patterns wait in a queue until downloaded. When the listing fails, a shareholding CSV from the NSE page in
   imports/ gives the promoter % meanwhile (manual_import.py; review F4).
NSE allows ~1 request per 3 s, so XBRL downloads are capped per run (`--max-fetch`) and split between new results,
shareholding and the history backfill (SHARES; review F2), and a deadline stops NSE requests in time for the job's
timeout (review F9). The rest waits in the state file (kept in the database between runs: pipeline.db.state
`in_weekly`) for the next run. The state also keeps each company's parsed results of its last KEEP_YEARS financial
years, whole: a Q4 row's H2 cash flow is FY - H1, so a year's filings are kept or dropped together, and a run writes
only the rows of the years its new filings touched, never a stored version with fewer values (review F1). The history
loader (pipeline/india/history.py) shares this state: a company it has finished is in `backfilled` too.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg
import yaml

from pipeline.db import repo, seed
from pipeline.db.models import Company, FundamentalsRow, InsiderEvent, OwnershipRow, PriceW
from pipeline.india import bhavcopy, manual_import
from pipeline.india.bhavcopy import BhavRow
from pipeline.india.pledges import PERSON, pledge_event
from pipeline.india.results_xbrl import (
    Filed,
    ResultsListing,
    build_rows,
    company_listing_path,
    from_json,
    listing_path,
    load_ind_as_map,
    parse_listing,
    parse_results,
    preferred,
    to_json,
)
from pipeline.india.securities import NSE_EQUITY_LIST_URL, parse_asm, parse_equity_list, parse_gsm
from pipeline.india.shareholding import Shareholding, ShpListing, parse_shareholding
from pipeline.india.shareholding import parse_listing as parse_shp_listing
from pipeline.india.xbrl import XbrlError
from pipeline.net.bse import BseClient
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.prices import benchmarks
from pipeline.settings import REPO_ROOT, Settings

SHP_API = "corporate-share-holdings-master?index=equities"
RESULTS_LOOKBACK_DAYS = 10  # the first run (no cursor yet) lists the last 10 days of results filings
RESULTS_OVERLAP_DAYS = 2  # later runs re-list the 2 days before the cursor (a filing NSE lists late)
MAX_CATCH_UP_DAYS = 120  # an older cursor is listed from 120 days back (and reported)
MAX_PAGES = 400  # listing pages per window (20,000 rows; a results season is ~5,000 a month)
KEEP_YEARS = 3  # financial years of parsed results kept per company in the state (whole years)
MAX_FETCH = 600  # XBRL downloads per run (30 min at 3 s each)
SHARES = (("results", 0.40), ("shareholding", 0.35), ("backfill", 0.25))  # of MAX_FETCH; a share not needed moves on
BACKFILL_PER_RUN = 60  # companies whose filing history is queued per run (capex desk first, then by traded value)
TIME_BUDGET_S = 36 * 60  # no NSE request after 36 min by default (weekly.yml passes --minutes 75; SPEC_ISSUES 55)
MIN_SURVEILLANCE = 20  # fewer ASM/GSM entries than this means the lists changed format: keep last week's flags


@dataclass
class IndiaWeeklyStats:
    friday: str
    eq_companies: int = 0
    universe_changes: int = 0
    surveillance: int = 0
    backfill_companies: int = 0
    price_source: str = "none"  # NSE | BSE | manual | none
    price_day: str = ""
    prices: int = 0
    benchmarks: int = 0
    results_window: str = ""
    results_listed: int = 0
    results_fetched: int = 0
    fundamentals_rows: int = 0
    shp_listed: int = 0
    shp_fetched: int = 0
    ownership_rows: int = 0
    ownership_manual: int = 0  # promoter % rows from a shareholding CSV in imports/
    pledge_events: int = 0
    budget: dict[str, int] = field(default_factory=dict)  # downloads allotted per stream
    deferred: int = 0  # queued XBRLs left for the next run
    listings_ok: bool = False  # every NSE listing was read in full (source_health success)
    nse_stale: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class State:
    results_queue: list[dict[str, Any]] = field(default_factory=list)  # listed, not fetched yet
    results_seen: set[str] = field(default_factory=set)  # listing seq ids fetched (or unreadable)
    results_store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # symbol -> parsed filings
    results_listed_to: str = ""  # the last day of the last complete results listing (ISO date)
    shp_queue: list[dict[str, Any]] = field(default_factory=list)  # listed patterns not fetched yet
    shp_seen: set[str] = field(default_factory=set)  # pattern XBRL URLs fetched (or unreadable)
    shp_last: dict[str, dict[str, Any]] = field(default_factory=dict)  # symbol -> last pattern (pledge changes)
    backfilled: set[str] = field(default_factory=set)  # symbols whose filing history was queued
    history_done: set[str] = field(default_factory=set)  # symbols the history loader finished (history.py)
    history_tries: dict[str, int] = field(default_factory=dict)  # its attempts that didn't finish, per symbol
    history_prices: set[str] = field(default_factory=set)  # Fridays (ISO) it read a bhavcopy for, or found none

    @classmethod
    def load(cls, path: Path | None) -> State:
        state = cls()
        if path is None or not path.exists():
            return state
        d = json.loads(path.read_text(encoding="utf-8"))
        for f in fields(cls):
            if f.name in d:
                v = d[f.name]
                setattr(state, f.name, set(v) if isinstance(getattr(state, f.name), set) else v)
        return state

    def save(self, path: Path | None) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d = {k: sorted(v) if isinstance(v, set) else v for k, v in d.items()}
        path.write_text(json.dumps(d, sort_keys=True), encoding="utf-8")


def last_friday(today: date) -> date:
    return today - timedelta(days=(today.weekday() - 4) % 7)


# ---------------------------------------------------------------- 1. universe


def update_universe(conn: psycopg.Connection[Any], nse: NseClient, stats: IndiaWeeklyStats, root: Path) -> set[str]:
    """Apply the securities list and the surveillance lists. Returns the EQ symbols (this week's list, or the stored
    listed companies when the list can't be read)."""
    cfg = yaml.safe_load((root / "config" / "universe_in.yaml").read_text(encoding="utf-8"))
    try:
        securities = parse_equity_list(nse.get(NSE_EQUITY_LIST_URL))
    except (NseBlocked, httpx.HTTPError) as e:
        stats.errors.append(f"securities list: {type(e).__name__}: {e}"[:300])
        securities = []
    if securities and len(securities) >= int(cfg["min_count_check"]):
        capex = seed.capex_sets(yaml.safe_load((root / "config" / "capex_seed.yaml").read_text(encoding="utf-8")))[1]
        repo.upsert_in_companies(conn, seed.in_companies(securities, capex))
        stats.universe_changes += repo.mark_missing_out_of_universe(
            conn, "in", [s.symbol for s in securities], repo.SNAPSHOT_OUT["in"]
        )
        stats.eq_companies = len(securities)
        eq = {s.symbol for s in securities}
    else:
        if securities:
            stats.errors.append(f"securities list has {len(securities)} rows < {cfg['min_count_check']}: not applied")
        eq = {c.nse_symbol for c in repo.companies(conn, market="in")
              if c.nse_symbol and c.excluded_reason != repo.SNAPSHOT_OUT["in"]}  # fmt: skip
    try:
        lists = parse_asm(nse.api("reportASM")) + parse_gsm(nse.api("reportGSM"))
    except (NseBlocked, httpx.HTTPError, ValueError) as e:
        stats.errors.append(f"surveillance lists: {type(e).__name__}: {e}"[:300])
        return eq  # keep last week's flags rather than letting everyone back in
    if len(lists) < MIN_SURVEILLANCE:  # a renamed JSON key parses as an empty list: the same rule
        stats.errors.append(f"surveillance lists have {len(lists)} entries < {MIN_SURVEILLANCE}: not applied")
        return eq
    reasons: dict[str, str | None] = {}
    for s in lists:  # a company on several lists keeps the first (ASM long-term, short-term, then GSM)
        reasons.setdefault(s.symbol, s.reason)
    stats.surveillance = len(set(reasons) & eq)
    stats.universe_changes += repo.set_india_universe(conn, {sym: reasons.get(sym) for sym in eq})
    return eq


def listed_companies(conn: psycopg.Connection[Any], eq: set[str]) -> list[Company]:
    """Every EQ company, in the universe or not (ASM/GSM): prices and filings are read for all of them."""
    return [c for c in repo.companies(conn, market="in") if c.id is not None and c.nse_symbol in eq]


# ---------------------------------------------------------------- 2. prices


def write_prices(
    conn: psycopg.Connection[Any], companies: Sequence[Company], rows: list[BhavRow], source: str, friday: date
) -> int:
    by_symbol = {c.nse_symbol: c.id for c in companies if c.nse_symbol and c.id}
    by_isin = {c.isin: c.id for c in companies if c.isin and c.id}
    out: dict[UUID, PriceW] = {}
    for r in rows:
        cid = by_isin.get(r.isin) if source == "BSE" else (by_symbol.get(r.symbol) or by_isin.get(r.isin))
        if cid is None:
            continue
        out[cid] = PriceW(
            company_id=cid,
            week_end=friday,
            close=r.close,
            adj_close=r.close,
            volume=None if r.volume is None else Decimal(r.volume),
            source=f"{source.lower()}_bhavcopy",
        )
    repo.upsert_prices(conn, list(out.values()))
    return len(out)


# ---------------------------------------------------------------- download budget


def allocate(total: int, demand: Mapping[str, int]) -> dict[str, int]:
    """Split a run's downloads: each stream gets up to its share (SHARES); what a stream doesn't need goes to the
    next ones in SHARES order."""
    alloc = {k: min(demand.get(k, 0), int(total * share)) for k, share in SHARES}
    spare = total - sum(alloc.values())
    for k, _ in SHARES:
        extra = min(spare, demand.get(k, 0) - alloc[k])
        alloc[k] += extra
        spare -= extra
    return alloc


# ---------------------------------------------------------------- 3. results


def _listing_json(x: ResultsListing, backfill: bool = False) -> dict[str, Any]:
    return {"seq_id": x.seq_id, "symbol": x.symbol, "period_end": x.period_end.isoformat(), "basis": x.basis,
            "revision": x.revision, "filed_at": x.filed_at.isoformat(), "xbrl_url": x.xbrl_url,
            "backfill": backfill}  # fmt: skip


def read_pages(nse: NseClient, path: Callable[[int], str]) -> tuple[list[ResultsListing], str | None]:
    """Every row of a paged results listing (`path(page)`), page by page up to the total count. Returns the rows read
    and, when the listing is incomplete (a failed or short page), why."""
    rows: list[ResultsListing] = []
    seen = 0
    try:
        for page in range(1, MAX_PAGES + 1):
            got, total, n = parse_listing(nse.api(path(page)))
            rows += got
            seen += n
            if seen >= total:
                return rows, None
            if n == 0:
                return rows, f"page {page} is empty after {seen} of {total} rows"
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        return rows, f"{type(e).__name__}: {e}"
    return rows, f"more than {MAX_PAGES} pages"


def list_results(nse: NseClient, day_from: date, day_to: date) -> tuple[list[ResultsListing], str | None]:
    """Every row listed for [day_from, day_to] (read_pages)."""
    return read_pages(nse, partial(listing_path, day_from, day_to))


def results_window(state: State, friday: date, stats: IndiaWeeklyStats) -> tuple[date, date]:
    if state.results_listed_to:
        start = date.fromisoformat(state.results_listed_to) + timedelta(days=1 - RESULTS_OVERLAP_DAYS)
    else:
        start = friday - timedelta(days=RESULTS_LOOKBACK_DAYS)
    floor = friday - timedelta(days=MAX_CATCH_UP_DAYS)
    if start < floor:
        stats.errors.append(f"results listing: filings before {floor} were not listed ({MAX_CATCH_UP_DAYS}-day limit)")
        start = floor
    return min(start, friday), friday


def queue_results(nse: NseClient, state: State, friday: date, ids: Mapping[str, UUID], stats: IndiaWeeklyStats) -> bool:
    """Newly listed filings -> the queue. True when the listing was read in full (then the cursor moves)."""
    start, end = results_window(state, friday, stats)
    stats.results_window = f"{start}..{end}"
    rows, error = list_results(nse, start, end)
    listed = preferred(rows)
    stats.results_listed = len(listed)
    queued = {str(q["seq_id"]) for q in state.results_queue}
    for x in listed:
        if x.seq_id not in state.results_seen and x.seq_id not in queued and x.symbol in ids:
            state.results_queue.append(_listing_json(x))
            queued.add(x.seq_id)
    if error is not None:
        stats.errors.append(f"results listing {start}..{end}: {error}"[:300])
        return False
    state.results_listed_to = end.isoformat()
    return True


def queue_backfill(
    nse: NseClient, state: State, ids: Mapping[str, UUID], order: Sequence[str], n: int, friday: date,
    stats: IndiaWeeklyStats,
) -> None:  # fmt: skip
    """The integrated-filing history (FY2025 Q4 onwards, at most KEEP_YEARS years) of the next `n` companies."""
    horizon = friday - timedelta(days=round(365.25 * KEEP_YEARS))
    queued = {str(q["seq_id"]) for q in state.results_queue}
    for symbol in [s for s in order if s in ids and s not in state.backfilled][:n]:
        if nse.unavailable:
            break
        history, error = read_pages(nse, partial(company_listing_path, symbol))
        if error is not None:  # retried next week (the symbol isn't marked backfilled)
            stats.errors.append(f"results history {symbol}: {error}"[:300])
            continue
        state.backfilled.add(symbol)
        stats.backfill_companies += 1
        for x in preferred(history):
            if (
                x.symbol == symbol
                and x.period_end > horizon
                and x.seq_id not in state.results_seen
                and x.seq_id not in queued
            ):
                state.results_queue.append(_listing_json(x, backfill=True))
                queued.add(x.seq_id)


def keep_years(filings: Iterable[dict[str, Any]], years: int | None = None) -> list[dict[str, Any]]:
    """A company's stored filings of its `years` (KEEP_YEARS) latest financial years, whole years only, by filing
    time."""
    filings = list(filings)
    kept = sorted({str(s["fy_start"]) for s in filings})[-(KEEP_YEARS if years is None else years) :]
    return sorted((s for s in filings if str(s["fy_start"]) in kept), key=lambda s: str(s["filed_at"]))


def fetch_results(
    nse: NseClient, state: State, items: Sequence[dict[str, Any]], limit: int, stats: IndiaWeeklyStats,
    ind_as: Mapping[str, Sequence[str]], years: int | None = None,
) -> dict[str, set[date]]:  # fmt: skip
    """Download up to `limit` queued filings (oldest first) into the store, which keeps `years` (KEEP_YEARS) financial
    years per company. Returns symbol -> the financial years that got a new filing. Downloaded and unreadable filings
    leave the queue; the rest stay."""
    touched: dict[str, set[date]] = defaultdict(set)
    done: set[str] = set()
    used = 0
    for q in sorted(items, key=lambda q: str(q["filed_at"])):
        if used >= limit or nse.unavailable:
            break
        seq, symbol, url = str(q["seq_id"]), str(q["symbol"]), str(q["xbrl_url"])
        used += 1
        try:
            parsed = parse_results(nse.get(url, use_cache=True), ind_as)
        except NseBlocked as e:  # stays queued
            stats.errors.append(f"results {symbol}: {type(e).__name__}")
            continue
        except (httpx.HTTPError, XbrlError, ValueError) as e:  # a broken filing is skipped, not retried forever
            stats.errors.append(f"results {symbol} {url}: {type(e).__name__}: {e}"[:300])
            state.results_seen.add(seq)
            done.add(seq)
            continue
        stats.results_fetched += 1
        state.results_seen.add(seq)
        done.add(seq)
        filed = Filed(parsed, datetime.fromisoformat(str(q["filed_at"])), url)
        store = [s for s in state.results_store.get(symbol, []) if s.get("url") != url]
        state.results_store[symbol] = keep_years([*store, to_json(filed)], years)
        if any(s.get("url") == url for s in state.results_store[symbol]):  # not older than the kept years
            touched[symbol].add(parsed.fy_start)
    state.results_queue = [q for q in state.results_queue if str(q["seq_id"]) not in done]
    return touched


def write_results(
    conn: psycopg.Connection[Any], state: State, touched: Mapping[str, set[date]], ids: Mapping[str, UUID],
    stats: IndiaWeeklyStats,
) -> None:  # fmt: skip
    """The rows of the financial years a new filing touched (a year's rows depend on that year's filings only). The
    upsert fills gaps and never replaces a stored value with a null."""
    for symbol, years in sorted(touched.items()):
        cid = ids.get(symbol)
        if cid is None:
            continue
        build = build_rows([from_json(s) for s in state.results_store.get(symbol, [])])
        rows = [r for r in build.rows if r.fy_start in years]
        periods = {f"{r.period_end}:" for r in rows}
        stats.errors += [f"results {symbol}: {i}" for i in build.issues if i[:11] in periods]
        models = [
            FundamentalsRow.model_validate(
                {
                    "company_id": cid,
                    "period_end": r.period_end,
                    "fiscal_label": r.fiscal_label,
                    "filed_at": r.filed_at,
                    "currency": "INR",
                    "source": "nse_xbrl",
                    **r.values,
                }
            )
            for r in rows
        ]
        repo.insert_fundamentals(conn, models, fill_only=True)
        stats.fundamentals_rows += len(models)


# ---------------------------------------------------------------- 4. shareholding


def _shp_json(s: Shareholding) -> dict[str, Any]:
    return {"quarter_end": s.quarter_end.isoformat(), "promoter_shares": str(s.promoter_shares or ""),
            "pledged_shares": "" if s.pledged_shares is None else str(s.pledged_shares),
            "pledged_pct": "" if s.promoter_pledged_pct is None else str(s.promoter_pledged_pct)}  # fmt: skip


def _shp_from_json(symbol: str, d: dict[str, Any]) -> Shareholding:
    def num(v: Any) -> Decimal | None:
        return Decimal(str(v)) if v not in (None, "") else None

    return Shareholding(symbol, None, date.fromisoformat(d["quarter_end"]), None, num(d.get("promoter_shares")),
                        num(d.get("pledged_shares")), None, num(d.get("pledged_pct")), None, None, None)  # fmt: skip


def _shp_listing_json(x: ShpListing) -> dict[str, Any]:
    return {"symbol": x.symbol, "quarter_end": x.quarter_end.isoformat(), "filed_at": x.filed_at.isoformat(),
            "xbrl_url": x.xbrl_url}  # fmt: skip


def queue_shareholding(nse: NseClient, state: State, ids: Mapping[str, UUID], stats: IndiaWeeklyStats) -> bool:
    """Newly listed patterns -> the queue (the listing shows the latest quarter only, so a pattern not downloaded
    before it moves on waits here). True when the listing was read."""
    try:
        listed = parse_shp_listing(nse.api(SHP_API))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"shareholding listing: {type(e).__name__}: {e}"[:300])
        return False
    stats.shp_listed = len(listed)
    queued = {str(q["xbrl_url"]) for q in state.shp_queue}
    for x in listed:
        if x.symbol in ids and x.xbrl_url not in state.shp_seen and x.xbrl_url not in queued:
            state.shp_queue.append(_shp_listing_json(x))
            queued.add(x.xbrl_url)
    return True


def shareholding_from_imports(
    conn: psycopg.Connection[Any], state: State, companies: Sequence[Company], imports: Path, stats: IndiaWeeklyStats
) -> None:
    """The listing API failed: promoter % from the NSE page's CSV in imports/ (matched by company name), and each
    pattern's XBRL queued, so the full row replaces it once NSE answers."""
    names: dict[str, list[Company]] = defaultdict(list)
    for c in companies:
        names[manual_import.company_key(c.name)].append(c)
    queued = {str(q["xbrl_url"]) for q in state.shp_queue}
    rows: dict[tuple[UUID, date], OwnershipRow] = {}
    for imp in manual_import.import_dir(imports):
        for r in imp.shareholding:
            match = names.get(manual_import.company_key(r.company), [])
            if len(match) != 1 or r.xbrl_url in state.shp_seen:  # unknown or ambiguous name; or read in full already
                continue
            c = match[0]
            assert c.id is not None and c.nse_symbol is not None
            key = (c.id, r.quarter_end)
            if key not in rows or rows[key].filed_at < r.filed_at:
                rows[key] = OwnershipRow(company_id=c.id, quarter_end=r.quarter_end, filed_at=r.filed_at,
                                         promoter_pct=r.promoter_pct, source="manual_csv")  # fmt: skip
            if r.xbrl_url not in queued:
                state.shp_queue.append({"symbol": c.nse_symbol, "quarter_end": r.quarter_end.isoformat(),
                                        "filed_at": r.filed_at.isoformat(), "xbrl_url": r.xbrl_url})  # fmt: skip
                queued.add(r.xbrl_url)
    repo.upsert_ownership(conn, list(rows.values()))
    stats.ownership_manual = len(rows)


def fetch_shareholding(
    nse: NseClient, state: State, limit: int, ids: Mapping[str, UUID], stats: IndiaWeeklyStats,
    items: Sequence[dict[str, Any]] | None = None,
) -> tuple[list[OwnershipRow], list[InsiderEvent]]:  # fmt: skip
    """Download up to `limit` queued patterns (`items`, else the queue; oldest first): ownership rows and pledge events.
    A pledge event compares a pattern with the company's previous quarter only (pledges.pledge_event), so a history
    read after a newer pattern adds its rows but no events out of order."""
    rows: list[OwnershipRow] = []
    pledges: list[InsiderEvent] = []
    done: set[str] = set()
    used = 0
    for q in sorted(state.shp_queue if items is None else items, key=lambda q: str(q["filed_at"])):
        if used >= limit or nse.unavailable:
            break
        symbol, url, filed_at = str(q["symbol"]), str(q["xbrl_url"]), datetime.fromisoformat(str(q["filed_at"]))
        used += 1
        try:
            s = parse_shareholding(nse.get(url, use_cache=True))
        except NseBlocked as e:  # stays queued
            stats.errors.append(f"shareholding {symbol}: {type(e).__name__}")
            continue
        except (httpx.HTTPError, XbrlError, ValueError) as e:
            stats.errors.append(f"shareholding {symbol}: {type(e).__name__}: {e}"[:300])
            state.shp_seen.add(url)
            done.add(url)
            continue
        stats.shp_fetched += 1
        state.shp_seen.add(url)
        done.add(url)
        cid = ids.get(symbol)
        if cid is None:
            continue
        rows.append(OwnershipRow(company_id=cid, quarter_end=s.quarter_end, filed_at=filed_at,
                                 promoter_pct=s.promoter_pct, promoter_pledged_pct=s.promoter_pledged_pct,
                                 fii_pct=s.fii_pct, dii_pct=s.dii_pct, inst_pct=s.inst_pct,
                                 source="nse_shp"))  # fmt: skip
        prev = state.shp_last.get(symbol)
        ev = pledge_event(_shp_from_json(symbol, prev) if prev else None, s, filed_at)
        if ev is not None:
            pledges.append(InsiderEvent(company_id=cid, event_date=ev.event_date, filed_at=ev.filed_at, person=PERSON,
                                        role="promoter", kind=ev.kind, shares=ev.shares, value=None, currency="INR",
                                        planned=False, source_url=url))  # fmt: skip
        if prev is None or date.fromisoformat(prev["quarter_end"]) <= s.quarter_end:
            state.shp_last[symbol] = _shp_json(s)
    state.shp_queue = [q for q in state.shp_queue if str(q["xbrl_url"]) not in done]
    return rows, pledges


# ---------------------------------------------------------------- the run


def run_weekly(
    conn: psycopg.Connection[Any],
    nse: NseClient,
    bse: BseClient,
    friday: date,
    state_path: Path | None = None,
    imports: Path = manual_import.IMPORTS_DIR,
    max_fetch: int = MAX_FETCH,
    root: Path = REPO_ROOT,
    backfill: int = BACKFILL_PER_RUN,
) -> IndiaWeeklyStats:
    """Each stage commits on its own (a savepoint inside a caller's transaction): universe and prices first, then
    each batch of rows, so a run stopped later keeps them."""
    stats = IndiaWeeklyStats(friday.isoformat())
    state = State.load(state_path)
    with conn.transaction():
        eq = update_universe(conn, nse, stats, root)
        companies = listed_companies(conn, eq)
        rows, source, day, notes = bhavcopy.fetch_week(nse, bse, friday, imports)
        stats.errors += notes if source == "none" else []
        stats.price_source, stats.price_day = source, day.isoformat() if day else ""
        stats.prices = write_prices(conn, companies, rows, source, friday) if rows else 0
        if day is not None and source == "NSE":
            write_index_closes(conn, nse, day, stats, root)
    capex = {c.nse_symbol for c in companies if c.capex_desk}
    turnover = {r.symbol: r.turnover or 0 for r in rows}
    order = sorted(turnover, key=lambda s: (s not in capex, -turnover[s]))  # capex desk, then by traded value
    ingest_filings(conn, nse, state, friday, companies, order, stats, load_ind_as_map(root), max_fetch, backfill,
                   imports)  # fmt: skip
    stats.nse_stale = nse.stale
    state.save(state_path)
    return stats


def write_index_closes(conn: psycopg.Connection[Any], nse: NseClient, day: date, stats: IndiaWeeklyStats,
                       root: Path) -> None:  # fmt: skip
    """NIFTY 50 / NIFTY 500 closes for the bhavcopy's trading day (M4 benchmarks, config/context.yaml)."""
    names = yaml.safe_load((root / "config" / "context.yaml").read_text(encoding="utf-8"))["benchmarks"]["in"]
    try:
        rows = benchmarks.india_rows(nse.get(benchmarks.index_close_url(day)), names)
    except (NseBlocked, httpx.HTTPError) as e:
        stats.errors.append(f"index closes {day}: {type(e).__name__}: {e}"[:300])
        return
    repo.upsert_benchmarks(conn, rows)
    stats.benchmarks = len(rows)


def ingest_filings(
    conn: psycopg.Connection[Any], nse: NseClient, state: State, friday: date, companies: Sequence[Company],
    order: Sequence[str], stats: IndiaWeeklyStats, ind_as: Mapping[str, Sequence[str]], max_fetch: int = MAX_FETCH,
    backfill: int = BACKFILL_PER_RUN, imports: Path = manual_import.IMPORTS_DIR,
) -> None:  # fmt: skip
    """Steps 3 and 4: list, split the download budget, download, and write each stream's rows."""
    ids = {c.nse_symbol: c.id for c in companies if c.nse_symbol and c.id}
    results_ok = queue_results(nse, state, friday, ids, stats)
    queue_backfill(nse, state, ids, order, backfill, friday, stats)
    shp_ok = queue_shareholding(nse, state, ids, stats)
    if not shp_ok:
        with conn.transaction():
            shareholding_from_imports(conn, state, companies, imports, stats)
    new = [q for q in state.results_queue if not q.get("backfill")]
    old = [q for q in state.results_queue if q.get("backfill")]
    stats.budget = allocate(
        max_fetch, {"results": len(new), "shareholding": len(state.shp_queue), "backfill": len(old)}
    )
    touched = fetch_results(nse, state, new, stats.budget["results"], stats, ind_as)
    with conn.transaction():
        write_results(conn, state, touched, ids, stats)
    own, pledges = fetch_shareholding(nse, state, stats.budget["shareholding"], ids, stats)
    with conn.transaction():
        repo.upsert_ownership(conn, own)
        repo.insert_insider_events(conn, pledges)
    stats.ownership_rows += len(own)
    stats.pledge_events += len(pledges)
    touched = fetch_results(nse, state, old, stats.budget["backfill"], stats, ind_as)
    with conn.transaction():
        write_results(conn, state, touched, ids, stats)
    stats.deferred = len(state.results_queue) + len(state.shp_queue)
    stats.listings_ok = results_ok and shp_ok


def mark_sources(conn: psycopg.Connection[Any], stats: IndiaWeeklyStats, nse: NseClient) -> None:
    """source_health: NSE stale after 3 consecutive blocks or failed requests (the web shows the banner); an error
    without a success when a listing couldn't be read in full, so its SLA banner shows if that lasts; BSE when it
    was used."""
    if nse.stale:
        repo.mark_source_error(conn, "nse", "stale: " + "; ".join(nse.blocks[-3:]), stale=True)
    elif not stats.listings_ok:
        repo.mark_source_error(conn, "nse", next((e for e in stats.errors if "listing" in e), "listing"), stale=False)
    else:
        repo.mark_source_success(conn, "nse")
    if stats.price_source == "BSE":
        repo.mark_source_success(conn, "bse")


def main(argv: list[str] | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--friday", type=date.fromisoformat, default=None)
    ap.add_argument("--max-fetch", type=int, default=MAX_FETCH)
    ap.add_argument("--backfill", type=int, default=BACKFILL_PER_RUN, help="companies whose history to queue")
    ap.add_argument("--minutes", type=float, default=TIME_BUDGET_S / 60, help="time budget for NSE requests")
    a = ap.parse_args(argv)
    friday = a.friday or last_friday(clock().date())
    settings = Settings.from_env()
    http = HttpClient(settings)
    nse, bse = NseClient(http), BseClient(http)
    nse.deadline = nse.clock() + a.minutes * 60
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "in_weekly") as run:
        stats = run_weekly(
            conn,
            nse,
            bse,
            friday,
            settings.cache_dir / "in" / "weekly_state.json",
            max_fetch=a.max_fetch,
            backfill=a.backfill,
        )
        mark_sources(conn, stats, nse)
        run.update(stats.__dict__)
    print(
        f"india weekly {stats.friday}: prices {stats.prices} ({stats.price_source}), results {stats.results_fetched}, "
        f"shareholding {stats.shp_fetched}, deferred {stats.deferred}, nse stale {stats.nse_stale}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
