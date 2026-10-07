"""One-off backfill of what the US daily run (pipeline/us/daily.py) reads day by day, for the days before it started:
Form 4 open-market purchases filed in the last INSIDER_DAYS (S7's 60-day window and the amendments that move a trade)
and the 8-K and NT events (auditor changes, acquisitions, late filings: R3, R4) filed in the last EVENT_MONTHS. The
daily run's first catch-up read 7 days back (2026-09-23), so S7 saw two weeks of filings (docs/SPEC_ISSUES.md 39).
Text filings for the Capex Desk are left to the daily run: old ones would only queue LLM work.

The companies are the latest candidate stage's (Evidence >= 40; --all for the whole US universe): S7 lifts a company
into a bucket only when another family has fired already. The rows are the daily run's own (its row builders and the
same submission URLs, the natural keys' source_url), so a re-run, and the days both runs read, insert nothing twice.
Each company commits on its own. `python -m pipeline.us.backfill [--all] [--days N]`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import psycopg

from pipeline.db import repo
from pipeline.db.models import Company, InsiderEvent
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us.daily import corp_rows, insider_rows, submissions_url
from pipeline.us.events import FORM4, filing_events
from pipeline.us.form4 import Form4Error, parse_submission
from pipeline.us.submissions import parse_submissions

INSIDER_DAYS = 100  # pipeline/signals/weekly.py INSIDER_DAYS: S7's windows (60 and 90 days) plus room
EVENT_MONTHS = 25  # pipeline/signals/weekly.py EVENT_MONTHS: R3/R4 (12 months) and S10 (24 months)
STAGE_MIN_EVIDENCE = Decimal(40)  # config/signals.yaml scores.us_price_candidate_min_evidence
FORM4_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"  # the master index's (daily run's) URL


def form4_url(cik: str, accession: str) -> str:
    return FORM4_URL.format(cik=int(cik), accession=accession)


@dataclass
class BackfillStats:
    companies: int = 0
    form4_filings: int = 0
    purchases: int = 0
    corp_events: int = 0
    errors: list[str] = field(default_factory=list)


def backfill_company(
    conn: psycopg.Connection[Any],
    client: HttpClient,
    company: Company,
    by_cik: Mapping[str, Company],
    since: date,
    events_since: date,
    stats: BackfillStats,
) -> None:
    """One company's events from its submissions file: the 8-K/NT events filed on or after `events_since`, and the
    purchases in its Form 4s filed on or after `since` (only those it is the issuer of: a company that files as
    another's owner is skipped)."""
    assert company.cik and company.id is not None
    try:
        subs = parse_submissions(json.loads(client.get_bytes(submissions_url(company.cik))))
    except (httpx.HTTPError, ValueError, KeyError) as e:
        stats.errors.append(f"submissions {company.cik}: {type(e).__name__}: {e}"[:300])
        return
    recent = {f.accession for f in subs.filings if f.filing_date >= events_since}
    events, _ = filing_events(subs, recent)
    corp = corp_rows(events, company.id)
    insiders: list[InsiderEvent] = []
    for f in subs.filings:
        if f.form not in FORM4 or f.filing_date < since:
            continue
        url = form4_url(company.cik, f.accession)
        try:
            f4 = parse_submission(client.get_bytes(url).decode("utf-8", "replace"))
        except (Form4Error, httpx.HTTPError) as e:
            stats.errors.append(f"{f.accession}: {type(e).__name__}: {e}"[:300])
            continue
        issuer = by_cik.get(f4.issuer_cik)
        if f4.issuer_cik != company.cik or issuer is None or issuer.id is None:
            continue
        stats.form4_filings += 1
        insiders += insider_rows(f4, issuer.id, url, f.filing_date)
    with conn.transaction():
        repo.insert_corp_events(conn, corp)
        repo.insert_insider_events(conn, insiders)
    stats.companies += 1
    stats.corp_events += len(corp)
    stats.purchases += len(insiders)


def targets(conn: psycopg.Connection[Any], every: bool) -> tuple[list[Company], dict[str, Company]]:
    """The US universe companies to read (the latest candidate stage's unless `every`) and every US company by CIK."""
    us = [c for c in repo.companies(conn, market="us") if c.cik and c.id is not None]
    by_cik = {c.cik: c for c in us if c.cik}
    universe = [c for c in us if c.in_universe]
    if every:
        return universe, by_cik
    stage = repo.stage_company_ids(conn, STAGE_MIN_EVIDENCE)
    return [c for c in universe if c.id in stage], by_cik


def run(
    conn: psycopg.Connection[Any], client: HttpClient, today: date, days: int, companies: Sequence[Company],
    by_cik: Mapping[str, Company],
) -> BackfillStats:  # fmt: skip
    stats = BackfillStats()
    since, events_since = today - timedelta(days=days), today - timedelta(days=31 * EVENT_MONTHS)
    for c in companies:
        backfill_company(conn, client, c, by_cik, since, events_since, stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="the whole US universe, not only the latest candidate stage")
    ap.add_argument("--days", type=int, default=INSIDER_DAYS, help="Form 4s filed this many days back")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    client = HttpClient(settings)
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "us_backfill", "sec") as run_:
        companies, by_cik = targets(conn, a.all)
        conn.commit()  # so each company's block commits on its own (a run cut short keeps the companies it finished)
        stats = run(conn, client, datetime.now(UTC).date(), a.days, companies, by_cik)
        run_.update(stats.__dict__)
    print(f"us backfill: {stats.companies} companies, {stats.form4_filings} Form 4s, {stats.purchases} purchases, "
          f"{stats.corp_events} events, {len(stats.errors)} errors")  # fmt: skip
    for e in stats.errors[:20]:
        print(f"  {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
