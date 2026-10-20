"""US daily run (BRIEF §2.1 "daily", §4.2): EDGAR daily index -> insider purchases, 8-K items, late filings,
spin-offs. `python -m pipeline.us.daily --date YYYY-MM-DD`.

By default the run catches up: it lists the quarter's published daily indexes (index.json) and processes every day
after the last one it finished (state file), so a day SEC publishes after the run starts is read the next day.
Without the state file (the Actions cache is evicted after 7 days unused) it resumes from the latest us_daily runs
row, so the days missed while the runs stopped are read too.
Spin-off registrants are not in the universe yet, so a small state file (cache dir) remembers CIKs that filed a
Form 10-12B; their later filings are checked until the registration is effective.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg

from pipeline.db import repo
from pipeline.db.models import Company, CorpEvent, FilingRow, InsiderEvent
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us.events import (
    FORM10,
    CorpEventDraft,
    TextFilingDraft,
    days_to_process,
    filing_events,
    master_index_url,
    parse_master_index,
    published_days,
    quarter_listing_url,
    quarters_between,
    select,
)
from pipeline.us.form4 import Form4, Form4Error, parse_submission
from pipeline.us.specials import effective_spinoff, html_to_text, parent_candidates
from pipeline.us.submissions import Submissions, end_of_day_utc, parse_submissions

RUN_KIND = "us_daily"  # its runs rows (repo.tracked_run)
RESCAN_DAYS = 120  # Form 10 registrations usually take 1-4 months to become effective
RETRY_RUNS = 3  # a day with failed downloads is read by up to this many runs (then logged and passed; review R2-F5)
# A catch-up resumed from the runs table (no state file) starts at most this many days back: about 22 business days
# of indexes, at well under a minute each (the SEC step took 20-60 s for a day in October 2026), fit the daily job's
# 30 minutes with the text step after it. An older gap is logged and left to `python -m pipeline.us.backfill` (its
# Form 4 purchases and 8-K/NT events).
CATCH_UP_DAYS = 31


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


@dataclass
class DailyStats:
    day: str
    index_rows: int = 0
    form4_filings: int = 0
    purchases: int = 0
    corp_events: int = 0
    text_filings: int = 0
    spinoffs: int = 0
    errors: list[str] = field(default_factory=list)
    retry: int = 0  # failed downloads (network, index not there yet): catch-up re-reads the day


def _pending(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def _save_pending(path: Path | None, ciks: set[str]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(ciks)), encoding="utf-8")


def rescan_form10(client: HttpClient, day: date, days: int) -> set[str]:
    """CIKs that filed a Form 10-12B in the `days` before `day`: rebuilds the pending set if the state file (Actions
    cache) was lost. One small index request per business day."""
    ciks: set[str] = set()
    for n in range(1, days + 1):
        d = day - timedelta(days=n)
        if d.weekday() >= 5:
            continue
        try:
            text = client.get_bytes(master_index_url(d)).decode("latin-1")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):  # holiday: no index
                continue
            raise
        ciks |= {r.cik for r in parse_master_index(text) if r.form in FORM10}
    return ciks


def run_daily(
    conn: psycopg.Connection[Any], client: HttpClient, day: date, state_path: Path | None = None
) -> DailyStats:
    stats = DailyStats(day.isoformat())
    by_cik = {c.cik: c for c in repo.companies(conn, market="us") if c.cik}
    universe = {cik for cik, c in by_cik.items() if c.in_universe}
    try:
        text = client.get_bytes(master_index_url(day)).decode("latin-1")
    except httpx.HTTPStatusError as e:
        if e.response.status_code not in (403, 404):
            raise
        if day.weekday() < 5:  # SEC answers 403 for an index it hasn't written yet: not a holiday (review F2)
            stats.errors.append(f"master index {day}: HTTP {e.response.status_code} (not published yet or holiday)")
            stats.retry += 1
        return stats
    rows = parse_master_index(text)
    stats.index_rows = len(rows)
    sel = select(rows, universe)
    pending = _pending(state_path) | {r.cik for r in rows if r.form in FORM10}
    _save_pending(state_path, pending)  # new registrants are remembered even if the run fails later

    insiders: list[InsiderEvent] = []
    for r in sel.form4:
        try:
            f4 = parse_submission(client.get_bytes(r.url).decode("utf-8", "replace"))
        except (Form4Error, httpx.HTTPError) as e:  # one bad filing never stops the run (it is marked partial)
            stats.errors.append(f"{r.accession}: {type(e).__name__}: {e}"[:300])
            stats.retry += isinstance(e, httpx.HTTPError)
            continue
        issuer = by_cik.get(f4.issuer_cik)
        if issuer is None or not issuer.in_universe or issuer.id is None:
            continue
        stats.form4_filings += 1
        insiders += insider_rows(f4, issuer.id, r.url, r.date_filed)
    repo.insert_insider_events(conn, insiders)
    stats.purchases = len(insiders)

    names = {cik: c.name for cik, c in by_cik.items() if c.in_universe}
    corp: list[CorpEvent] = []
    texts: list[FilingRow] = []
    for cik in sorted(sel.need_submissions | ({r.cik for r in rows} & pending)):
        try:
            subs = parse_submissions(json.loads(client.get_bytes(submissions_url(cik))))
        except (httpx.HTTPError, ValueError, KeyError) as e:
            stats.errors.append(f"submissions {cik}: {type(e).__name__}: {e}"[:300])
            stats.retry += isinstance(e, httpx.HTTPError)
            continue
        today = {r.accession for r in rows if r.cik == cik}
        company = by_cik.get(cik)
        if company is not None and company.in_universe and company.id is not None:
            evs, drafts = filing_events(subs, today, capex_desk=company.capex_desk)
            corp += corp_rows(evs, company.id)
            texts += filing_rows(drafts, company.id)
        if cik in pending:
            try:
                event = _spinoff_event(conn, client, subs, company, names)
            except httpx.HTTPError as e:  # retried at the registrant's next filing (the evidence stays in its history)
                stats.errors.append(f"form 10 {cik}: {type(e).__name__}: {e}"[:300])
                stats.retry += 1
                continue
            if event is not None:
                corp.append(event)
                stats.spinoffs += 1
                pending.discard(cik)
    repo.insert_corp_events(conn, corp)
    repo.insert_filings(conn, texts)
    stats.corp_events, stats.text_filings = len(corp), len(texts)
    _save_pending(state_path, pending)
    return stats


def insider_rows(f4: Form4, company_id: UUID, url: str, date_filed: date) -> list[InsiderEvent]:
    """A Form 4's open-market purchases as insider_events rows; `url` is the submission's (the natural key's
    source_url: the daily run and the backfill, pipeline/us/backfill.py, must give the same one)."""
    return [
        InsiderEvent(
            company_id=company_id,
            event_date=t.date,
            filed_at=f4.accepted_at or end_of_day_utc(date_filed),
            person=f4.person or "unknown",
            role=f4.role or None,
            kind="open_market_buy",
            shares=t.shares,
            value=t.value,
            currency="USD",
            planned=t.planned,
            source_url=url,
            amends=f4.original_date if f4.document_type.startswith("4/A") else None,
        )
        for t in f4.purchases()
    ]


def corp_rows(events: Sequence[CorpEventDraft], company_id: UUID) -> list[CorpEvent]:
    return [
        CorpEvent(
            company_id=company_id,
            event_date=e.event_date,
            filed_at=e.filed_at,
            kind=e.kind,
            detail=e.detail,
            source_url=e.source_url,
        )  # fmt: skip
        for e in events
    ]


def filing_rows(drafts: Sequence[TextFilingDraft], company_id: UUID) -> list[FilingRow]:
    return [
        FilingRow(
            company_id=company_id,
            accession_no=d.accession,
            form_type=d.form,
            items=list(d.items),
            filed_at=d.accepted_at,
            accepted_at=d.accepted_at,
            period_of_report=d.period_of_report,
            primary_doc_url=d.primary_doc_url,
            index_url=d.index_url,
        )  # fmt: skip
        for d in drafts
    ]


def _spinoff_event(
    conn: psycopg.Connection[Any],
    client: HttpClient,
    subs: Submissions,
    company: Company | None,
    names: dict[str, str],
) -> CorpEvent | None:
    spin = effective_spinoff(subs)
    if spin is None:
        return None
    text = html_to_text(client.get_bytes(spin.form10_doc_url).decode("utf-8", "replace"))
    candidates = parent_candidates(text, names, exclude_cik=subs.cik)
    company_id = (
        company.id
        if company is not None and company.id is not None
        else repo.ensure_company(
            conn,
            Company(
                market="us",
                name=subs.name,
                cik=subs.cik,
                ticker=subs.tickers[0] if subs.tickers else None,
                in_universe=False,
                excluded_reason="spin-off registrant; not yet in the universe",
            ),  # fmt: skip
        )
    )
    return CorpEvent(
        company_id=company_id,
        event_date=spin.event_date,
        filed_at=spin.filed_at,
        kind="spinoff",
        detail={
            "role": "spinco",
            "evidence": spin.evidence,
            "form10_accession": spin.form10_accession,
            "parent_candidates": candidates,
            "confirmed": False,  # confirmed by hand in the web app (BRIEF §4.2)
        },
        source_url=spin.form10_doc_url,
    )


def _state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return state


def load_last_day(path: Path | None) -> date | None:
    v = _state(path).get("last_day")
    return date.fromisoformat(v) if v else None


def resume_day(days: Sequence[Mapping[str, Any]]) -> date | None:
    """The cursor a lost state file held, from the days a us_daily runs row recorded (run_catch_up's DailyStats): the
    newest day read, or the day before the first one still being retried (failed downloads hold the cursor)."""
    read: list[tuple[date, int]] = []
    for d in days:
        try:
            read.append((date.fromisoformat(str(d.get("day"))), int(d.get("retry") or 0)))
        except ValueError:
            continue  # not a day: the listing errors' entry ("listings as of ...")
    if not read:
        return None
    retried = [day for day, retry in read if retry > 0]
    return min(retried) - timedelta(days=1) if retried else max(day for day, _ in read)


def save_last_day(path: Path | None, day: date, held: date | None = None, attempts: int = 0) -> None:
    """The cursor, plus the day being retried (if any) and how many runs have read it."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {"last_day": day.isoformat()}
        if held is not None:
            state |= {"held_day": held.isoformat(), "attempts": attempts}
        path.write_text(json.dumps(state), encoding="utf-8")


def listed_days(client: HttpClient, first: date, today: date, errors: list[str]) -> list[date]:
    """Published days from the quarters' index.json listings. SEC creates a new quarter's listing hours into its
    first day (the 01:30 UTC run on July 1 finds 403), so a missing listing for today's quarter is simply "nothing
    published yet" (review R2-F6); a missing earlier listing is logged and skipped."""
    out: list[date] = []
    quarters = quarters_between(min(first, today), today)
    for q in quarters:
        try:
            out += published_days(json.loads(client.get_bytes(quarter_listing_url(q))))
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (403, 404):
                raise
            if q != quarters[-1]:
                errors.append(f"daily-index listing {q:%Y} Q{(q.month - 1) // 3 + 1}: HTTP {e.response.status_code}")
    return [d for d in out if d <= today]


def run_catch_up(
    conn: psycopg.Connection[Any], client: HttpClient, today: date, pending_path: Path | None, day_path: Path | None
) -> list[DailyStats]:
    """Every published EDGAR day after the last one processed (review F2: at 01:30 UTC yesterday's index often
    isn't published yet; it is picked up by the next run instead of being skipped as a 'holiday').

    Each day is committed before the cursor moves past it, and the cursor is saved as it moves, so a run cut off
    part-way (the job's timeout) keeps the days it read and the next run resumes after them. A day with failed
    downloads holds the cursor, so the next run reads it again (inserts are idempotent). Retries are counted in runs,
    not calendar days: Friday's index is first read on Tuesday (review R2-F5). After RETRY_RUNS reads the cursor moves
    on and the errors stay logged.

    Without a state file the cursor comes from the latest us_daily runs row (resume_day), at most CATCH_UP_DAYS back;
    with no such row either, the run reads the latest few published days (a first run)."""
    state = _state(day_path)
    last = load_last_day(day_path)
    held_day = date.fromisoformat(state["held_day"]) if state.get("held_day") else None
    attempts = int(state.get("attempts", 0))
    notes: list[str] = []
    if last is None:
        # In a transaction of its own: a read left open would turn each day's transaction below into a savepoint,
        # committed only when tracked_run ends, after the cursor moved (overhaul PR 1 review, pipeline-F1).
        with conn.transaction():
            run_days = repo.latest_run_days(conn, RUN_KIND)
        last = resume_day(run_days)
        floor = today - timedelta(days=CATCH_UP_DAYS)
        if last is not None and last < floor:
            notes.append(f"no state file and the last run's cursor {last} is over {CATCH_UP_DAYS} days old: read from "
                         f"{floor + timedelta(days=1)}; python -m pipeline.us.backfill reads the Form 4s and 8-Ks "
                         "before that")  # fmt: skip
            last = floor
    first = (last + timedelta(days=1)) if last else today - timedelta(days=7)
    listing_errors: list[str] = []
    published = listed_days(client, first, today, listing_errors)
    out: list[DailyStats] = []
    held: date | None = None
    for day in days_to_process(published, last):
        with conn.transaction():
            stats = run_daily(conn, client, day, pending_path)
        out.append(stats)
        if held is not None:
            continue  # read, but the cursor waits for the held day
        if stats.retry > 0:
            tries = attempts + 1 if held_day == day else 1
            if tries < RETRY_RUNS:
                held, attempts = day, tries
                continue
            stats.errors.append(f"{day}: downloads still failing after {tries} runs; moving on")
        last = day
        save_last_day(day_path, last)  # committed above: a run cut off later still resumes after it (spec-F2)
    if listing_errors:
        out.insert(0, DailyStats(f"listings as of {today}", errors=listing_errors))
    if notes:
        out.insert(0, DailyStats(f"cursor as of {today}", errors=notes))
    if last is None and held is not None:
        last = held - timedelta(days=1)  # a first run that holds its first day still remembers the attempt
    if last is not None:
        save_last_day(day_path, last, held, attempts if held else 0)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", type=date.fromisoformat, default=None, help="one day only (default: catch up)")
    ap.add_argument("--rescan-days", type=int, default=None,
                    help=f"re-read this many past daily indexes for Form 10 filers (default: {RESCAN_DAYS} when the "
                         "pending-registrations state file is missing)")  # fmt: skip
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    client = HttpClient(settings)
    state = settings.cache_dir / "us" / "pending_form10.json"
    day_state = settings.cache_dir / "us" / "daily_state.json"
    today = datetime.now(UTC).date()
    rescan = a.rescan_days if a.rescan_days is not None else (0 if state.exists() else RESCAN_DAYS)
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, RUN_KIND, "sec") as run:
        if rescan:
            _save_pending(state, _pending(state) | rescan_form10(client, a.date or today, rescan))
        days = (
            [run_daily(conn, client, a.date, state)] if a.date else run_catch_up(conn, client, today, state, day_state)
        )
        run["date"] = a.date.isoformat() if a.date else None  # a one-day run: no cursor to resume from
        run.update({"days": [d.__dict__ for d in days], "errors": [e for d in days for e in d.errors]})
    for d in days:
        print(f"us daily {d.day}: {d.purchases} purchases, {d.corp_events} events, {d.spinoffs} spin-offs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
