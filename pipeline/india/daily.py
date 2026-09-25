"""India daily run (BRIEF §2.1 "daily", §4.3). `python -m pipeline.india.daily [--date YYYY-MM-DD]`.

- NSE corporate announcements of the day -> corp_events(kind='announcement') with the PDF link (triage is M5's).
- Insider-trading (PIT) disclosures of the last few days -> the disclosure XBRLs -> promoter market purchases and
  sales -> insider_events (pit.py). Disclosures already read are remembered in a state file (Actions cache).
Only universe companies are kept. NSE's rate (1 request per 3 s) caps the XBRL downloads per run; the rest are read
the next day (the index lists about five months of disclosures).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg

from pipeline.db import repo
from pipeline.db.models import CorpEvent, InsiderEvent
from pipeline.india import announcements, pit
from pipeline.india.xbrl import XbrlError
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.settings import Settings

ANNOUNCEMENTS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
PIT_LOOKBACK_DAYS = 7
MAX_PIT_FETCH = 80  # ~4 min at 3 s per request
SEEN_KEEP_DAYS = 200


@dataclass
class IndiaDailyStats:
    day: str
    announcements: int = 0
    pit_listed: int = 0
    pit_fetched: int = 0
    promoter_trades: int = 0
    deferred: int = 0
    nse_stale: bool = False
    errors: list[str] = field(default_factory=list)


def _load_seen(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")).get("pit_seen", {}))


def _save_seen(path: Path | None, seen: dict[str, str], today: date) -> None:
    if path is None:
        return
    cutoff = (today - timedelta(days=SEEN_KEEP_DAYS)).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {u: d for u, d in seen.items() if d >= cutoff}
    path.write_text(json.dumps({"pit_seen": kept}, sort_keys=True), encoding="utf-8")


def ingest_announcements(conn: psycopg.Connection[Any], nse: NseClient, day: date, ids: dict[str, Any],
                         stats: IndiaDailyStats) -> None:  # fmt: skip
    try:
        items = announcements.parse(nse.api(announcements.api_path(day, day)))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"announcements: {type(e).__name__}: {e}"[:300])
        return
    events = [
        CorpEvent(
            company_id=ids[a.symbol],
            event_date=a.event_date,
            filed_at=a.filed_at,
            kind="announcement",
            detail={"category": a.category, "text": a.text, "seq_id": a.seq_id, "has_xbrl": a.has_xbrl},
            source_url=a.pdf_url or f"{ANNOUNCEMENTS_PAGE}#{a.seq_id}",
        )
        for a in items
        if a.symbol in ids
    ]
    repo.insert_corp_events(conn, events)
    stats.announcements = len(events)


def ingest_pit(conn: psycopg.Connection[Any], nse: NseClient, day: date, ids: dict[str, Any], seen: dict[str, str],
               stats: IndiaDailyStats, max_fetch: int, lookback_days: int = PIT_LOOKBACK_DAYS) -> None:  # fmt: skip
    try:
        index = pit.parse_index_json(nse.api(pit.API_PATH, referer=pit.PAGE))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"insider-trading index: {type(e).__name__}: {e}"[:300])
        return
    since = datetime.combine(day - timedelta(days=lookback_days), datetime.min.time(), tzinfo=UTC)
    todo = sorted((f for f in index if f.symbol in ids and f.xbrl_url not in seen and f.filed_at >= since),
                  key=lambda f: f.filed_at)  # fmt: skip
    stats.pit_listed = len(todo)
    events: list[InsiderEvent] = []
    for f in todo:
        if stats.pit_fetched >= max_fetch or nse.stale:
            stats.deferred += 1
            continue
        try:
            trades = pit.parse_disclosure(nse.get(f.xbrl_url, use_cache=True))
        except NseBlocked as e:
            stats.errors.append(f"insider trading {f.symbol}: {type(e).__name__}")
            stats.deferred += 1
            continue
        except (httpx.HTTPError, XbrlError, ValueError) as e:
            stats.errors.append(f"insider trading {f.symbol} {f.xbrl_url}: {type(e).__name__}: {e}"[:300])
            seen[f.xbrl_url] = f.filed_at.date().isoformat()
            continue
        stats.pit_fetched += 1
        seen[f.xbrl_url] = f.filed_at.date().isoformat()
        for t in trades:
            kind, when = t.kind, t.event_date
            if kind is None or when is None:
                continue
            events.append(
                InsiderEvent(
                    company_id=ids[f.symbol],
                    event_date=when,
                    filed_at=f.filed_at,
                    person=t.person or "unknown",
                    role=t.category or None,
                    kind=kind,
                    shares=t.shares,
                    value=t.value,
                    currency="INR",
                    planned=False,  # India has no trading-plan flag in PIT disclosures
                    source_url=f.xbrl_url,
                )
            )
    repo.insert_insider_events(conn, events)
    stats.promoter_trades = len(events)


def run_daily(conn: psycopg.Connection[Any], nse: NseClient, day: date, state_path: Path | None = None,
              max_fetch: int = MAX_PIT_FETCH, lookback_days: int = PIT_LOOKBACK_DAYS) -> IndiaDailyStats:  # fmt: skip
    stats = IndiaDailyStats(day.isoformat())
    ids = {c.nse_symbol: c.id for c in repo.companies(conn, market="in", in_universe=True) if c.nse_symbol and c.id}
    seen = _load_seen(state_path)
    ingest_announcements(conn, nse, day, ids, stats)
    ingest_pit(conn, nse, day, ids, seen, stats, max_fetch, lookback_days)
    _save_seen(state_path, seen, day)
    stats.nse_stale = nse.stale
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", type=date.fromisoformat, default=(datetime.now(UTC) - timedelta(days=1)).date())
    ap.add_argument("--max-fetch", type=int, default=MAX_PIT_FETCH)
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    nse = NseClient(HttpClient(settings))
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "in_daily") as run:
        stats = run_daily(conn, nse, a.date, settings.cache_dir / "in" / "daily_state.json", a.max_fetch)
        if nse.stale:
            repo.mark_source_error(conn, "nse", "3 consecutive blocks: " + "; ".join(nse.blocks[-3:]), stale=True)
        else:
            repo.mark_source_success(conn, "nse")
        run.update(stats.__dict__)
    print(f"india daily {stats.day}: {stats.announcements} announcements, {stats.promoter_trades} promoter trades, "
          f"{stats.deferred} deferred, nse stale {stats.nse_stale}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
