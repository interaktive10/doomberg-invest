"""India daily run (BRIEF §2.1 "daily", §4.3). `python -m pipeline.india.daily [--date YYYY-MM-DD]`.

- NSE corporate announcements -> corp_events(kind='announcement') with the PDF link (triage is M5's). One request per
  day, from the day after the last day read in full (a cursor in the state) to `--date` (yesterday by default), so
  the Tuesday run reads Saturday, Sunday and Monday, and a failed day is read by the next run (review F3). A day the
  API can't give is read from an announcements CSV of the NSE page in imports/ when there is one (review F4).
- Insider-trading (PIT) disclosures -> the disclosure XBRLs -> promoter market purchases and sales -> insider_events
  (pit.py). The index lists about five months; the run reads it from the oldest disclosure not read yet (a cursor),
  and remembers the disclosures read (the state file, Actions cache).
Every EQ company is kept, ASM/GSM ones included (review F7; in_universe decides scoring only). NSE's rate (1 request
per 3 s) caps the XBRL downloads per run; the rest are read the next day.
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
from pipeline.db.models import CorpEvent, CorpEventKind, InsiderEvent
from pipeline.india import announcements, manual_import, pit
from pipeline.india.announcements import Announcement
from pipeline.india.xbrl import XbrlError
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.settings import Settings

ANNOUNCEMENTS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
FIRST_RUN_DAYS = 3  # with no cursor yet, the run reads the last 3 days (a Tuesday: Saturday to Monday)
MAX_CATCH_UP_DAYS = 14  # an older cursor is read from 14 days back (and reported)
PIT_LOOKBACK_DAYS = 7
MAX_PIT_FETCH = 80  # ~4 min at 3 s per request
SEEN_KEEP_DAYS = 200
TIME_BUDGET_S = 10 * 60  # no NSE request after 10 min (daily.yml's India job times out at 15 min)


@dataclass
class IndiaDailyStats:
    day: str
    announcement_days: list[str] = field(default_factory=list)  # days read (manual: from imports/)
    announcements: int = 0
    pit_listed: int = 0
    pit_fetched: int = 0
    promoter_trades: int = 0
    deferred: int = 0
    listings_ok: bool = False  # announcements read up to the day and the PIT index read (source_health success)
    nse_stale: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class DailyState:
    pit_seen: dict[str, str] = field(default_factory=dict)  # disclosure XBRL URL -> its filing day
    announcements_to: str = ""  # the last day whose announcements were stored in full (ISO date)
    pit_from: str = ""  # the oldest filing day not read in full yet (ISO date)

    @classmethod
    def load(cls, path: Path | None) -> DailyState:
        if path is None or not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(dict(d.get("pit_seen", {})), str(d.get("announcements_to", "")), str(d.get("pit_from", "")))

    def save(self, path: Path | None, today: date) -> None:
        if path is None:
            return
        cutoff = (today - timedelta(days=SEEN_KEEP_DAYS)).isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        kept = {u: d for u, d in self.pit_seen.items() if d >= cutoff}
        doc = {"pit_seen": kept, "announcements_to": self.announcements_to, "pit_from": self.pit_from}
        path.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")


def _events(items: list[Announcement], ids: dict[str, Any]) -> list[CorpEvent]:
    """Each announcement as a corp_event; one that announces an acquisition also as kind 'acquisition' (R4's
    exception), which isn't pruned with the announcements after 120 days (M4 review R1-F5)."""
    out = []
    for a in items:
        if a.symbol not in ids:
            continue
        url = a.pdf_url or f"{ANNOUNCEMENTS_PAGE}#{a.seq_id or a.symbol + a.filed_at.strftime('%Y%m%dT%H%M%S')}"
        detail = {"category": a.category, "text": a.text, "seq_id": a.seq_id, "has_xbrl": a.has_xbrl}
        kinds: tuple[CorpEventKind, ...] = ("announcement", "acquisition") if announcements.is_acquisition(
            a.category, a.text) else ("announcement",)  # fmt: skip
        out += [CorpEvent(company_id=ids[a.symbol], event_date=a.event_date, filed_at=a.filed_at, kind=k,
                          detail=detail, source_url=url) for k in kinds]  # fmt: skip
    return out


def ingest_announcements(
    conn: psycopg.Connection[Any], nse: NseClient, day: date, ids: dict[str, Any], state: DailyState,
    stats: IndiaDailyStats, imports: Path,
) -> bool:  # fmt: skip
    """Every day from the cursor to `day`, one day at a time; the cursor moves after each stored day. True when
    the run got to `day`."""
    if state.announcements_to:
        start = date.fromisoformat(state.announcements_to) + timedelta(days=1)
    else:
        start = day - timedelta(days=FIRST_RUN_DAYS - 1)
    floor = day - timedelta(days=MAX_CATCH_UP_DAYS - 1)
    if start < floor:
        stats.errors.append(f"announcements before {floor} were not read ({MAX_CATCH_UP_DAYS}-day limit)")
        start = floor
    manual: dict[date, list[Announcement]] | None = None
    for n in range((day - start).days + 1):
        d = start + timedelta(days=n)
        try:
            items = announcements.parse(nse.api(announcements.api_path(d, d)))
            label = d.isoformat()
        except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
            if manual is None:
                manual = manual_import.announcements_by_day(imports)
            if d not in manual:
                stats.errors.append(f"announcements {d}: {type(e).__name__}: {e}"[:300])
                return False
            items, label = manual[d], f"{d} (manual)"
        events = _events(items, ids)
        with conn.transaction():
            repo.insert_corp_events(conn, events)
        stats.announcements += len(events)
        stats.announcement_days.append(label)
        state.announcements_to = d.isoformat()
    return True


def ingest_pit(conn: psycopg.Connection[Any], nse: NseClient, day: date, ids: dict[str, Any], state: DailyState,
               stats: IndiaDailyStats, max_fetch: int, lookback_days: int = PIT_LOOKBACK_DAYS) -> bool:  # fmt: skip
    """Disclosures filed since the cursor (and at least the last `lookback_days`). True when the index was read."""
    try:
        index = pit.parse_index_json(nse.api(pit.API_PATH, referer=pit.PAGE))
    except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"insider-trading index: {type(e).__name__}: {e}"[:300])
        return False
    since_day = day - timedelta(days=lookback_days)
    if state.pit_from:  # the index itself reaches back about five months
        since_day = min(since_day, date.fromisoformat(state.pit_from))
    since = datetime.combine(since_day, datetime.min.time(), tzinfo=UTC)
    todo = sorted((f for f in index if f.symbol in ids and f.xbrl_url not in state.pit_seen and f.filed_at >= since),
                  key=lambda f: f.filed_at)  # fmt: skip
    stats.pit_listed = len(todo)
    events: list[InsiderEvent] = []
    left: list[date] = []  # filing days of disclosures not read this run
    for f in todo:
        if stats.pit_fetched >= max_fetch or nse.unavailable:
            left.append(f.filed_at.date())
            continue
        try:
            trades = pit.parse_disclosure(nse.get(f.xbrl_url, use_cache=True))
        except NseBlocked as e:
            stats.errors.append(f"insider trading {f.symbol}: {type(e).__name__}")
            left.append(f.filed_at.date())
            continue
        except (httpx.HTTPError, XbrlError, ValueError) as e:
            stats.errors.append(f"insider trading {f.symbol} {f.xbrl_url}: {type(e).__name__}: {e}"[:300])
            state.pit_seen[f.xbrl_url] = f.filed_at.date().isoformat()
            continue
        stats.pit_fetched += 1
        state.pit_seen[f.xbrl_url] = f.filed_at.date().isoformat()
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
                    line=t.line or None,
                )
            )
    with conn.transaction():
        repo.insert_insider_events(conn, events)
    stats.promoter_trades = len(events)
    stats.deferred = len(left)
    state.pit_from = (min(left) if left else day - timedelta(days=1)).isoformat()
    return True


def listed_ids(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """NSE symbol -> company id for every company still on the EQ list (ASM/GSM included)."""
    with conn.transaction():
        companies = repo.companies(conn, market="in")
    return {c.nse_symbol: c.id for c in companies
            if c.nse_symbol and c.id and c.excluded_reason != repo.SNAPSHOT_OUT["in"]}  # fmt: skip


def run_daily(conn: psycopg.Connection[Any], nse: NseClient, day: date, state_path: Path | None = None,
              max_fetch: int = MAX_PIT_FETCH, lookback_days: int = PIT_LOOKBACK_DAYS,
              imports: Path = manual_import.IMPORTS_DIR) -> IndiaDailyStats:  # fmt: skip
    stats = IndiaDailyStats(day.isoformat())
    ids = listed_ids(conn)
    state = DailyState.load(state_path)
    ann_ok = ingest_announcements(conn, nse, day, ids, state, stats, imports)
    pit_ok = ingest_pit(conn, nse, day, ids, state, stats, max_fetch, lookback_days)
    state.save(state_path, day)
    stats.listings_ok = ann_ok and pit_ok
    stats.nse_stale = nse.stale
    return stats


def mark_source(conn: psycopg.Connection[Any], stats: IndiaDailyStats, nse: NseClient) -> None:
    if nse.stale:
        repo.mark_source_error(conn, "nse", "stale: " + "; ".join(nse.blocks[-3:]), stale=True)
    elif not stats.listings_ok:
        repo.mark_source_error(conn, "nse", stats.errors[0] if stats.errors else "listing", stale=False)
    else:
        repo.mark_source_success(conn, "nse")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", type=date.fromisoformat, default=(datetime.now(UTC) - timedelta(days=1)).date())
    ap.add_argument("--max-fetch", type=int, default=MAX_PIT_FETCH)
    ap.add_argument("--minutes", type=float, default=TIME_BUDGET_S / 60, help="time budget for NSE requests")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    nse = NseClient(HttpClient(settings))
    nse.deadline = nse.clock() + a.minutes * 60
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "in_daily") as run:
        stats = run_daily(conn, nse, a.date, settings.cache_dir / "in" / "daily_state.json", a.max_fetch)
        mark_source(conn, stats, nse)
        run.update(stats.__dict__)
    print(
        f"india daily {stats.day}: {stats.announcements} announcements ({len(stats.announcement_days)} days), "
        f"{stats.promoter_trades} promoter trades, {stats.deferred} deferred, nse stale {stats.nse_stale}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
