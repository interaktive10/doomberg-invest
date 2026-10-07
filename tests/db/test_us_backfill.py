"""The US events backfill (pipeline/us/backfill.py, docs/SPEC_ISSUES.md 39) against the database: Form 4 purchases of
the last 100 days and 8-K/NT events of the last 25 months from each company's submissions, the daily run's own rows
(no duplicates where both read a filing), and the candidate stage as the default set of companies."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from pipeline.db import repo
from pipeline.db.models import Company, Score
from pipeline.db.pit import as_of
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us import backfill
from pipeline.us.daily import run_daily, submissions_url
from pipeline.us.events import master_index_url

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "us"
GERON = "0000886744"
CLUSTER = ("0000950170-25-030327", "0000950170-25-030329", "0000950170-25-030330")  # filed 2025-03-03 (F-F4)
TODAY = date(2025, 4, 1)


def add(conn: psycopg.Connection[Any], cik: str, name: str, in_universe: bool = True) -> uuid.UUID:
    repo.upsert_us_companies(conn, [Company(market="us", name=name, cik=cik, in_universe=in_universe)])
    return repo.company_ids_by(conn, "cik")[cik]


def submissions(cik: str, name: str, filings: list[tuple[str, str, str, str]]) -> bytes:
    """A submissions file: (accession, form, filing date, 8-K items) rows, accepted at 21:30 UTC on the filing day."""
    cols: dict[str, list[str]] = {k: [] for k in ("accessionNumber", "form", "filingDate", "reportDate",
                                                  "acceptanceDateTime", "items", "primaryDocument")}  # fmt: skip
    for acc, form, filed, items in filings:
        for k, v in zip(cols, (acc, form, filed, "", f"{filed}T21:30:00.000Z", items, f"{acc}.htm"), strict=True):
            cols[k].append(v)
    return json.dumps({"cik": cik, "name": name, "filings": {"recent": cols}}).encode()


def client(tmp_path: Path) -> HttpClient:
    """Geron's submissions: the F-F4 cluster, a Form 4 filed before the 100 days (never requested: no mock), a Form 4
    it filed as another issuer's owner, an 8-K 4.01 and an NT 10-K inside 25 months, and an 8-K 4.01 before them."""
    c = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="test", cache_dir=tmp_path))
    c.register_mock(submissions_url(GERON), submissions(GERON, "GERON CORP", [
        *[(acc, "4", "2025-03-03", "") for acc in CLUSTER],
        ("0000950170-24-000001", "4", "2024-11-01", ""),
        ("0009999901-25-000001", "4", "2025-03-10", ""),
        ("0000886744-25-000010", "8-K", "2025-02-10", "4.01,9.01"),
        ("0000886744-25-000020", "NT 10-K", "2025-03-17", ""),
        ("0000886744-22-000005", "8-K", "2022-01-10", "4.01"),
    ]))  # fmt: skip
    for acc in CLUSTER:
        c.register_mock(backfill.form4_url(GERON, acc), (FIX / "form4" / f"{acc}.txt").read_bytes())
    owner = (FIX / "form4" / "synthetic" / "0009999901-25-000001.txt").read_bytes()  # issuer 0009999901
    c.register_mock(backfill.form4_url(GERON, "0009999901-25-000001"), owner)
    return c


def test_purchases_and_events_from_the_submissions_file(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    gid = add(conn, GERON, "GERON CORP")
    add(conn, "0009999901", "SYNTHETIC CLUSTER CORP")
    companies, by_cik = backfill.targets(conn, every=True)
    http = client(tmp_path)
    stats = backfill.run(conn, http, TODAY, backfill.INSIDER_DAYS, [c for c in companies if c.cik == GERON], by_cik)
    assert (stats.companies, stats.form4_filings, stats.purchases, stats.corp_events, stats.errors) == (1, 3, 3, 2, [])
    assert backfill.form4_url(GERON, "0000950170-24-000001") not in http.calls  # filed before the 100 days
    buys = as_of(date(2025, 3, 5)).insider_events(conn, [gid])
    assert sorted((b.person, b.value) for b in buys) == [
        ("SCARLETT JOHN A", Decimal("22062.500")), ("Samuels Scott Alan", Decimal("24150.00")),
        ("Ziegler James", Decimal("160000.0"))]  # fmt: skip
    assert {b.source_url for b in buys} == {f"https://www.sec.gov/Archives/edgar/data/886744/{a}.txt" for a in CLUSTER}
    events = as_of(TODAY).corp_events(conn, [gid])
    assert sorted((e.kind, e.event_date) for e in events) == [
        ("auditor_change", date(2025, 2, 10)), ("late_filing", date(2025, 3, 17))]  # fmt: skip
    # a re-run inserts nothing twice
    backfill.run(conn, client(tmp_path / "b"), TODAY, backfill.INSIDER_DAYS, [c for c in companies if c.cik == GERON],
                 by_cik)  # fmt: skip
    assert len(as_of(TODAY).insider_events(conn, [gid])) == 3 and len(as_of(TODAY).corp_events(conn, [gid])) == 2


def test_a_day_the_daily_run_read_is_not_counted_twice(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """The daily run stores Geron's cluster from the 2025-03-03 index under the same submission URLs."""
    gid = add(conn, GERON, "GERON CORP")
    http = client(tmp_path)
    http.register_mock(master_index_url(date(2025, 3, 3)), (FIX / "events" / "master.20250303.idx").read_bytes())
    for p in (FIX / "events").glob("CIK*.json"):
        http.register_mock(submissions_url(p.stem.removeprefix("CIK")), p.read_bytes())
    assert run_daily(conn, http, date(2025, 3, 3), tmp_path / "pending.json").purchases == 3
    companies, by_cik = backfill.targets(conn, every=True)
    stats = backfill.run(conn, http, TODAY, backfill.INSIDER_DAYS, [c for c in companies if c.cik == GERON], by_cik)
    assert stats.purchases == 3 and len(as_of(TODAY).insider_events(conn, [gid])) == 3


def test_the_default_companies_are_the_latest_candidate_stage(conn: psycopg.Connection[Any]) -> None:
    ids = {name: add(conn, cik, name) for cik, name in (("0000000001", "STAGED"), ("0000000002", "WEAK"),
                                                         ("0000000003", "LAST WEEK ONLY"))}  # fmt: skip
    add(conn, "0000000004", "OUTSIDE", in_universe=False)

    def score(cid: uuid.UUID, week: date, evidence: int) -> Score:
        return Score(company_id=cid, week_end=week, evidence=Decimal(evidence), gap=None, families=["fundamentals"],
                     bucket="none", weights_version="w0-equal")  # fmt: skip

    repo.upsert_scores(conn, [score(ids["STAGED"], date(2026, 10, 2), 50), score(ids["WEAK"], date(2026, 10, 2), 20),
                              score(ids["LAST WEEK ONLY"], date(2026, 9, 25), 50)])  # fmt: skip
    staged, _ = backfill.targets(conn, every=False)
    assert [c.name for c in staged] == ["STAGED"]
    everyone, by_cik = backfill.targets(conn, every=True)
    assert {c.name for c in everyone} == {"STAGED", "WEAK", "LAST WEEK ONLY"} and "0000000004" in by_cik
