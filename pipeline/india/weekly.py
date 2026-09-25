"""India weekly run (BRIEF §2.1 "weekly", §4.3, §4.4 India prices). `python -m pipeline.india.weekly [--friday D]`.

1. Universe: the NSE securities list (EQ series; main board, so SME is out) and the ASM/GSM surveillance lists.
2. Prices: the week's last trading-day bhavcopy -> prices_w for every universe company. NSE first; when NSE is stale
   (3 consecutive blocks) or has no file, BSE's bhavcopy for the same day (matched by ISIN); when both fail, the
   manual CSV imports in imports/. A day that neither exchange has is a holiday: the run walks back to Thursday etc.
3. Results: new integrated-filing results XBRL (consolidated preferred) -> fundamentals_q (results_xbrl.py).
4. Shareholding: new quarterly patterns -> ownership_q (shareholding.py), and pledge changes -> insider_events.
NSE allows ~1 request per 3 s, so XBRL downloads are capped per run (`--max-fetch`); the rest waits in the state
file (Actions cache) for the next run. The state also keeps each company's recent parsed results, which the Q4 row
needs for its H2 cash flow (H2 = FY - H1).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg
import yaml

from pipeline.db import repo, seed
from pipeline.db.models import FundamentalsRow, InsiderEvent, OwnershipRow, PriceW
from pipeline.india import bhavcopy, manual_import
from pipeline.india.bhavcopy import BhavRow
from pipeline.india.pledges import PERSON, pledge_event
from pipeline.india.results_xbrl import (
    LISTING_API,
    Filed,
    ResultsListing,
    build_rows,
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
from pipeline.settings import REPO_ROOT, Settings

SHP_API = "corporate-share-holdings-master?index=equities"
RESULTS_LOOKBACK_DAYS = 10  # each run lists the last 10 days of results filings (overlap covers a missed week)
KEEP_FILINGS = 8  # parsed results kept per company in the state (two financial years)
MAX_FETCH = 400  # XBRL downloads per run (~20 min at 3 s each)
BACKFILL_PER_RUN = 60  # companies whose filing history is queued per run (capex desk first, then by traded value)


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
    results_listed: int = 0
    results_fetched: int = 0
    fundamentals_rows: int = 0
    shp_listed: int = 0
    shp_fetched: int = 0
    ownership_rows: int = 0
    pledge_events: int = 0
    deferred: int = 0
    nse_stale: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class State:
    results_queue: list[dict[str, Any]] = field(default_factory=list)  # listed, not fetched yet
    results_seen: set[str] = field(default_factory=set)
    results_store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # symbol -> parsed filings
    shp_seen: set[str] = field(default_factory=set)
    shp_last: dict[str, dict[str, Any]] = field(default_factory=dict)  # symbol -> last pattern (pledge changes)
    backfilled: set[str] = field(default_factory=set)  # symbols whose filing history was queued

    @classmethod
    def load(cls, path: Path | None) -> State:
        if path is None or not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d.get("results_queue", []), set(d.get("results_seen", [])), d.get("results_store", {}),
                   set(d.get("shp_seen", [])), d.get("shp_last", {}), set(d.get("backfilled", [])))  # fmt: skip

    def save(self, path: Path | None) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"results_queue": self.results_queue, "results_seen": sorted(self.results_seen),
                                    "results_store": self.results_store, "shp_seen": sorted(self.shp_seen),
                                    "shp_last": self.shp_last, "backfilled": sorted(self.backfilled)},
                                   sort_keys=True), encoding="utf-8")  # fmt: skip


def last_friday(today: date) -> date:
    return today - timedelta(days=(today.weekday() - 4) % 7)


# ---------------------------------------------------------------- 1. universe


def update_universe(conn: psycopg.Connection[Any], nse: NseClient, stats: IndiaWeeklyStats, root: Path) -> None:
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
            conn, "in", [s.symbol for s in securities], "not in the NSE EQ snapshot"
        )
        stats.eq_companies = len(securities)
    elif securities:
        stats.errors.append(f"securities list has {len(securities)} rows < {cfg['min_count_check']}: not applied")
    eq = {s.symbol for s in securities} or {
        c.nse_symbol for c in repo.companies(conn, market="in")
        if c.nse_symbol and c.excluded_reason != "not in the NSE EQ snapshot"
    }  # fmt: skip
    try:
        lists = parse_asm(nse.api("reportASM")) + parse_gsm(nse.api("reportGSM"))
    except (NseBlocked, httpx.HTTPError, ValueError) as e:
        stats.errors.append(f"surveillance lists: {type(e).__name__}: {e}"[:300])
        return  # keep last week's flags rather than letting everyone back in
    reasons: dict[str, str | None] = {}
    for s in lists:  # a company on several lists keeps the first (ASM long-term, short-term, then GSM)
        reasons.setdefault(s.symbol, s.reason)
    stats.surveillance = len(set(reasons) & eq)
    stats.universe_changes += repo.set_india_universe(conn, {sym: reasons.get(sym) for sym in eq})


# ---------------------------------------------------------------- 2. prices


def write_prices(conn: psycopg.Connection[Any], rows: list[BhavRow], source: str, friday: date) -> int:
    companies = [c for c in repo.companies(conn, market="in", in_universe=True) if c.id is not None]
    by_symbol = {c.nse_symbol: c.id for c in companies if c.nse_symbol}
    by_isin = {c.isin: c.id for c in companies if c.isin}
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


# ---------------------------------------------------------------- 3. results


def _listing_json(x: ResultsListing, backfill: bool = False) -> dict[str, Any]:
    return {"seq_id": x.seq_id, "symbol": x.symbol, "period_end": x.period_end.isoformat(), "basis": x.basis,
            "revision": x.revision, "filed_at": x.filed_at.isoformat(), "xbrl_url": x.xbrl_url,
            "backfill": backfill}  # fmt: skip


def list_results(nse: NseClient, day_from: date, day_to: date) -> list[ResultsListing]:
    rows: list[ResultsListing] = []
    page, total = 1, 1
    while len(rows) < total and page <= 40:
        got, total = parse_listing(nse.api(listing_path(day_from, day_to, page)))
        if not got:
            break
        rows += got
        page += 1
    return rows


def ingest_results(
    conn: psycopg.Connection[Any], nse: NseClient, state: State, friday: date, budget: list[int],
    stats: IndiaWeeklyStats, ind_as: dict[str, list[str]], backfill_order: Sequence[str] = (), backfill: int = 0,
) -> None:  # fmt: skip
    ids = {c.nse_symbol: c.id for c in repo.companies(conn, market="in", in_universe=True) if c.nse_symbol and c.id}
    try:
        listed = preferred(list_results(nse, friday - timedelta(days=RESULTS_LOOKBACK_DAYS), friday))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"results listing: {type(e).__name__}: {e}"[:300])
        listed = []
    stats.results_listed = len(listed)
    queue = {q["seq_id"]: q for q in state.results_queue}
    for x in listed:
        if x.seq_id not in state.results_seen and x.symbol in ids:
            queue.setdefault(x.seq_id, _listing_json(x))
    for symbol in [s for s in backfill_order if s in ids and s not in state.backfilled][:backfill]:
        if nse.stale:
            break
        try:  # the company's integrated-filing history (FY2025 Q4 onwards): about six quarters
            history, _ = parse_listing(nse.api(f"{LISTING_API}&symbol={symbol}"))
        except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
            stats.errors.append(f"results history {symbol}: {type(e).__name__}"[:300])
            continue
        state.backfilled.add(symbol)
        stats.backfill_companies += 1
        for x in preferred(history):
            if x.seq_id not in state.results_seen and x.symbol == symbol:
                queue.setdefault(x.seq_id, _listing_json(x, backfill=True))
    touched: set[str] = set()
    remaining: list[dict[str, Any]] = []
    for q in sorted(queue.values(), key=lambda q: (bool(q.get("backfill")), str(q["filed_at"]))):  # new filings first
        if budget[0] <= 0 or nse.stale:
            remaining.append(q)
            continue
        try:
            raw = nse.get(str(q["xbrl_url"]), use_cache=True)
            budget[0] -= 1
            parsed = parse_results(raw, ind_as)
        except NseBlocked as e:
            stats.errors.append(f"results {q['symbol']}: {type(e).__name__}")
            remaining.append(q)
            continue
        except (httpx.HTTPError, XbrlError, ValueError) as e:  # a broken filing is skipped, not retried forever
            stats.errors.append(f"results {q['symbol']} {q['xbrl_url']}: {type(e).__name__}: {e}"[:300])
            state.results_seen.add(str(q["seq_id"]))
            continue
        stats.results_fetched += 1
        state.results_seen.add(str(q["seq_id"]))
        filed = Filed(parsed, datetime.fromisoformat(str(q["filed_at"])), str(q["xbrl_url"]))
        store = [s for s in state.results_store.get(str(q["symbol"]), []) if s.get("url") != filed.source_url]
        state.results_store[str(q["symbol"])] = sorted([*store, to_json(filed)], key=lambda s: str(s["filed_at"]))[
            -KEEP_FILINGS:
        ]
        touched.add(str(q["symbol"]))
    state.results_queue = remaining
    stats.deferred += len(remaining)
    for symbol in sorted(touched):
        cid = ids.get(symbol)
        if cid is None:
            continue
        build = build_rows([from_json(s) for s in state.results_store[symbol]])
        stats.errors += [f"results {symbol}: {i}" for i in build.issues]
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
            for r in build.rows
        ]
        repo.insert_fundamentals(conn, models)
        stats.fundamentals_rows += len(models)


# ---------------------------------------------------------------- 4. shareholding


def _shp_json(s: Shareholding) -> dict[str, Any]:
    return {"quarter_end": s.quarter_end.isoformat(), "promoter_shares": str(s.promoter_shares or ""),
            "pledged_shares": "" if s.pledged_shares is None else str(s.pledged_shares),
            "pledged_pct": "" if s.promoter_pledged_pct is None else str(s.promoter_pledged_pct)}  # fmt: skip


def _shp_from_json(symbol: str, d: dict[str, Any]) -> Shareholding:
    from decimal import Decimal

    def num(v: Any) -> Decimal | None:
        return Decimal(str(v)) if v not in (None, "") else None

    return Shareholding(symbol, None, date.fromisoformat(d["quarter_end"]), None, num(d.get("promoter_shares")),
                        num(d.get("pledged_shares")), None, num(d.get("pledged_pct")), None, None, None)  # fmt: skip


def ingest_shareholding(
    conn: psycopg.Connection[Any], nse: NseClient, state: State, budget: list[int], stats: IndiaWeeklyStats
) -> None:
    ids = {c.nse_symbol: c.id for c in repo.companies(conn, market="in", in_universe=True) if c.nse_symbol and c.id}
    try:
        listed: list[ShpListing] = parse_shp_listing(nse.api(SHP_API))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"shareholding listing: {type(e).__name__}: {e}"[:300])
        return
    stats.shp_listed = len(listed)
    todo = sorted(
        (x for x in listed if x.record_id not in state.shp_seen and x.symbol in ids), key=lambda x: x.filed_at
    )
    rows: list[OwnershipRow] = []
    pledges: list[InsiderEvent] = []
    for x in todo:
        if budget[0] <= 0 or nse.stale:
            stats.deferred += 1
            continue
        try:
            raw = nse.get(x.xbrl_url, use_cache=True)
            budget[0] -= 1
            s = parse_shareholding(raw)
        except NseBlocked as e:
            stats.errors.append(f"shareholding {x.symbol}: {type(e).__name__}")
            stats.deferred += 1
            continue
        except (httpx.HTTPError, XbrlError, ValueError) as e:
            stats.errors.append(f"shareholding {x.symbol}: {type(e).__name__}: {e}"[:300])
            state.shp_seen.add(x.record_id)
            continue
        stats.shp_fetched += 1
        state.shp_seen.add(x.record_id)
        cid = ids[x.symbol]
        rows.append(OwnershipRow(company_id=cid, quarter_end=s.quarter_end, filed_at=x.filed_at,
                                 promoter_pct=s.promoter_pct, promoter_pledged_pct=s.promoter_pledged_pct,
                                 fii_pct=s.fii_pct, dii_pct=s.dii_pct, inst_pct=s.inst_pct,
                                 source="nse_shp"))  # fmt: skip
        prev = state.shp_last.get(x.symbol)
        ev = pledge_event(_shp_from_json(x.symbol, prev) if prev else None, s, x.filed_at)
        if ev is not None:
            pledges.append(InsiderEvent(company_id=cid, event_date=ev.event_date, filed_at=ev.filed_at, person=PERSON,
                                        role="promoter", kind=ev.kind, shares=ev.shares, value=None, currency="INR",
                                        planned=False, source_url=x.xbrl_url))  # fmt: skip
        if prev is None or date.fromisoformat(prev["quarter_end"]) <= s.quarter_end:
            state.shp_last[x.symbol] = _shp_json(s)
    repo.upsert_ownership(conn, rows)
    repo.insert_insider_events(conn, pledges)
    stats.ownership_rows, stats.pledge_events = len(rows), len(pledges)


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
    stats = IndiaWeeklyStats(friday.isoformat())
    state = State.load(state_path)
    update_universe(conn, nse, stats, root)
    rows, source, day, notes = bhavcopy.fetch_week(nse, bse, friday, imports)
    stats.errors += notes if source == "none" else []
    stats.price_source, stats.price_day = source, day.isoformat() if day else ""
    stats.prices = write_prices(conn, rows, source, friday) if rows else 0
    capex = {c.nse_symbol for c in repo.companies(conn, market="in", in_universe=True) if c.capex_desk}
    turnover = {r.symbol: r.turnover or 0 for r in rows}
    order = sorted(turnover, key=lambda s: (s not in capex, -turnover[s]))  # capex desk, then by traded value
    budget = [max_fetch]
    ingest_results(conn, nse, state, friday, budget, stats, load_ind_as_map(root), order, backfill)
    ingest_shareholding(conn, nse, state, budget, stats)
    stats.nse_stale = nse.stale
    state.save(state_path)
    return stats


def mark_sources(conn: psycopg.Connection[Any], stats: IndiaWeeklyStats, nse: NseClient) -> None:
    """source_health: NSE stale after 3 consecutive blocks (the web shows the banner); BSE when it was used."""
    if nse.stale:
        repo.mark_source_error(conn, "nse", "3 consecutive blocks: " + "; ".join(nse.blocks[-3:]), stale=True)
    else:
        repo.mark_source_success(conn, "nse")
    if stats.price_source == "BSE":
        repo.mark_source_success(conn, "bse")


def main(argv: list[str] | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--friday", type=date.fromisoformat, default=None)
    ap.add_argument("--max-fetch", type=int, default=MAX_FETCH)
    ap.add_argument("--backfill", type=int, default=BACKFILL_PER_RUN, help="companies whose history to queue")
    a = ap.parse_args(argv)
    friday = a.friday or last_friday(clock().date())
    settings = Settings.from_env()
    http = HttpClient(settings)
    nse, bse = NseClient(http), BseClient(http)
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
