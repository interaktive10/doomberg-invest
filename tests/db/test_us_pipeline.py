"""US pipeline against the database (BRIEF §8 M2-02, M2-04, M2-05, M2-06): restatement versions through as_of(),
the daily run on real EDGAR files served by mocks, the 13F write, and the weekly run on F-US."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest

from pipeline.db import repo
from pipeline.db.models import Company
from pipeline.db.pit import as_of
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us.daily import run_daily, submissions_url
from pipeline.us.events import master_index_url, parse_master_index
from pipeline.us.fundamentals import load_xbrl_map, quarterize_company, write_company
from pipeline.us.quarterly import run_13f
from pipeline.us.submissions import parse_submissions
from pipeline.us.thirteenf import read_dataset
from pipeline.us.weekly import JsonSource, run_weekly

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "us"
F_US = {"0000320193": "Apple Inc.", "0000789019": "MICROSOFT CORP", "0001045810": "NVIDIA CORP",
        "0000018230": "CATERPILLAR INC", "0001341439": "ORACLE CORP", "0001050915": "QUANTA SERVICES, INC.",
        "0000898293": "JABIL INC", "0001996810": "GE Vernova Inc."}  # fmt: skip


def add(conn: psycopg.Connection[Any], cik: str, name: str, in_universe: bool = True, capex: bool = False) -> uuid.UUID:
    repo.upsert_us_companies(conn, [Company(market="us", name=name, cik=cik, in_universe=in_universe,
                                            capex_desk=capex)])  # fmt: skip
    return repo.company_ids_by(conn, "cik")[cik]


def mock_client(tmp_path: Path) -> HttpClient:
    return HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="test", cache_dir=tmp_path))


# ---------------------------------------------------------------- M2-02


def _load(conn: psycopg.Connection[Any], cik: str, name: str) -> uuid.UUID:
    cid = add(conn, cik, name)
    cf = json.loads((FIX / "companyfacts" / f"CIK{cik}.json").read_text(encoding="utf-8"))
    subs = parse_submissions(json.loads((FIX / "submissions" / f"CIK{cik}.json").read_text(encoding="utf-8")))
    result = quarterize_company(cf, subs, load_xbrl_map(), date(2026, 9, 20))
    assert write_company(conn, cid, result) == len(result.rows)
    return cid


def _value(conn: psycopg.Connection[Any], cid: uuid.UUID, q: date, col: str, w: date) -> Decimal | None | str:
    rows = [r for r in as_of(w).fundamentals(conn, [cid]) if r.period_end == q]
    return getattr(rows[0], col) if rows else "no row"


def test_restatement_is_a_new_row_and_as_of_returns_the_right_version(conn: psycopg.Connection[Any]) -> None:
    """CAT's FY2015 Q4 operating income: -114M from the FY2015 10-K (2016-02-16), restated to -175M by the FY2016
    10-K (2017-02-15). Both rows stay; as_of returns the one known at the time."""
    cid = _load(conn, "0000018230", "CATERPILLAR INC")
    q = date(2015, 12, 31)
    assert _value(conn, cid, q, "op_income", date(2016, 2, 15)) == "no row"
    assert _value(conn, cid, q, "op_income", date(2016, 2, 16)) == Decimal(-114000000)
    assert _value(conn, cid, q, "op_income", date(2017, 2, 14)) == Decimal(-114000000)
    assert _value(conn, cid, q, "op_income", date(2017, 2, 15)) == Decimal(-175000000)
    n = conn.execute("select count(*) from fundamentals_q where company_id = %s and period_end = %s", (cid, q))
    assert n.fetchone() == (4,)  # 2016-02-16, 2016-05-02 (total assets), 2017-02-15, 2019-02-14 (cash)
    result = quarterize_company(json.loads((FIX / "companyfacts" / "CIK0000018230.json").read_text(encoding="utf-8")),
                                parse_submissions(json.loads((FIX / "submissions" / "CIK0000018230.json").read_text(
                                    encoding="utf-8"))), load_xbrl_map(), date(2026, 9, 20))  # fmt: skip
    write_company(conn, cid, result)  # a re-run rewrites the same versions
    n = conn.execute("select count(*) from fundamentals_q where company_id = %s and period_end = %s", (cid, q))
    assert n.fetchone() == (4,)


def test_write_company_replaces_versions_it_no_longer_produces(conn: psycopg.Connection[Any]) -> None:
    """Review F10: versions the current code no longer produces, and quarters outside the 60-quarter window, go."""
    from datetime import UTC, datetime

    from pipeline.db.models import FundamentalsRow

    cid = _load(conn, "0000018230", "CATERPILLAR INC")
    before = conn.execute("select count(*) from fundamentals_q where company_id = %s", (cid,)).fetchone()
    stale = [
        FundamentalsRow(company_id=cid, period_end=date(2015, 12, 31), fiscal_label="FY2015Q4",
                        filed_at=datetime(2016, 3, 1, tzinfo=UTC), revenue=Decimal(1), currency="USD",
                        source="sec_xbrl"),  # a version an older code produced
        FundamentalsRow(company_id=cid, period_end=date(2009, 12, 31), fiscal_label="FY2009Q4",
                        filed_at=datetime(2010, 2, 20, tzinfo=UTC), revenue=Decimal(1), currency="USD",
                        source="sec_xbrl"),  # outside the 60-quarter window
    ]  # fmt: skip
    repo.insert_fundamentals(conn, stale)
    _load(conn, "0000018230", "CATERPILLAR INC")  # the weekly run rewrites the company
    after = conn.execute("select count(*) from fundamentals_q where company_id = %s", (cid,)).fetchone()
    assert after == before
    assert _value(conn, cid, date(2015, 12, 31), "revenue", date(2016, 3, 2)) == Decimal(11030000000)


def test_prune_with_nothing_to_keep_deletes_nothing(conn: psycopg.Connection[Any]) -> None:
    """Review R3 idea: a company whose facts gave no rows keeps its stored versions."""
    cid = _load(conn, "0000018230", "CATERPILLAR INC")
    before = conn.execute("select count(*) from fundamentals_q where company_id = %s", (cid,)).fetchone()
    assert repo.prune_fundamentals(conn, cid, [], date(2011, 1, 1)) == 0
    assert conn.execute("select count(*) from fundamentals_q where company_id = %s", (cid,)).fetchone() == before


def test_the_display_view_carries_the_amendment_link(conn: psycopg.Connection[Any]) -> None:
    """Review R3 idea: the web reads insider events through insider_events_display_v, which shows `amends`."""
    cols = conn.execute("select * from insider_events_display_v limit 0").description or []
    assert "amends" in [c.name for c in cols]


def test_derived_quarters_wait_for_a_consistent_vintage(conn: psycopg.Connection[Any]) -> None:
    """Review F3: Apple's FY2017 Q2 CFO. The FY2018 Q1 10-Q (2018-02-02) restated Q1 FY2017; YTD6 minus that
    restated Q1 (12,345M) was never reported by any filing. The FY2018 Q2 10-Q (2018-05-02) restated YTD6 too:
    12,570M."""
    cid = _load(conn, "0000320193", "Apple Inc.")
    q = date(2017, 4, 1)
    assert _value(conn, cid, q, "revenue", date(2017, 5, 3)) == Decimal(52896000000)
    assert _value(conn, cid, q, "cfo", date(2018, 3, 1)) is None
    assert _value(conn, cid, q, "cfo", date(2018, 5, 2)) == Decimal(12570000000)


# ---------------------------------------------------------------- M2-04


def daily_client(tmp_path: Path) -> HttpClient:
    c = mock_client(tmp_path)
    for day in ("20250303", "20250304"):
        text = (FIX / "events" / f"master.{day}.idx").read_bytes()
        c.register_mock(master_index_url(date(int(day[:4]), int(day[4:6]), int(day[6:]))), text)
    for p in (FIX / "form4").glob("0000950170-25-0303*.txt"):
        c.register_mock(f"https://www.sec.gov/Archives/edgar/data/886744/{p.name}", p.read_bytes())
    for p in (FIX / "events").glob("CIK*.json"):
        c.register_mock(submissions_url(p.stem.removeprefix("CIK")), p.read_bytes())
    return c


def test_daily_run_stores_purchases_late_filings_and_auditor_changes(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    ids = {cik: add(conn, cik, name) for cik, name in (
        ("0000886744", "GERON CORP"), ("0001906324", "QuidelOrtho Corp"), ("0001439095", "MRC GLOBAL INC."),
        ("0001446847", "IRONWOOD PHARMACEUTICALS INC"), ("0001368514", "ADMA BIOLOGICS, INC."))}  # fmt: skip
    client, state = daily_client(tmp_path), tmp_path / "pending.json"
    s1 = run_daily(conn, client, date(2025, 3, 3), state)
    s2 = run_daily(conn, client, date(2025, 3, 4), state)
    assert (s1.index_rows, s1.form4_filings, s1.purchases, s1.corp_events, s1.errors) == (33, 3, 3, 3, [])
    assert (s2.corp_events, s2.purchases, s2.errors) == (1, 0, [])

    buys = as_of(date(2025, 3, 3)).insider_events(conn, [ids["0000886744"]])
    assert sorted((b.person, b.value, b.planned) for b in buys) == [
        ("SCARLETT JOHN A", Decimal("22062.500"), False),
        ("Samuels Scott Alan", Decimal("24150.00"), False),
        ("Ziegler James", Decimal("160000.0"), False),
    ]
    assert all(b.kind == "open_market_buy" and b.event_date == date(2025, 2, 27) for b in buys)
    assert buys[0].source_url.startswith("https://www.sec.gov/Archives/edgar/data/886744/")

    late = as_of(date(2025, 3, 3)).corp_events(conn, [ids[c] for c in ("0001439095", "0001446847", "0001368514")])
    assert sorted(e.kind for e in late) == ["late_filing"] * 3
    quidel = ids["0001906324"]
    assert as_of(date(2025, 3, 3)).corp_events(conn, [quidel]) == []  # accepted 2025-03-04 21:15:31Z
    assert as_of(datetime(2025, 3, 4, 21, 15, 30, tzinfo=UTC)).corp_events(conn, [quidel]) == []
    change = as_of(date(2025, 3, 4)).corp_events(conn, [quidel])
    assert [(e.kind, e.detail["accession"]) for e in change] == [("auditor_change", "0001906324-25-000037")]

    run_daily(conn, client, date(2025, 3, 3), state)  # re-run: no duplicates
    assert len(as_of(date(2025, 3, 5)).insider_events(conn, [ids["0000886744"]])) == 3
    assert len(as_of(date(2025, 3, 5)).corp_events(conn, list(ids.values()))) == 4


def test_catch_up_processes_every_published_day_once(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Review F2: yesterday's index is often published after the 01:30 UTC run; catch-up reads it the next day."""
    from pipeline.us.daily import load_last_day, run_catch_up, save_last_day
    from pipeline.us.events import quarter_listing_url

    add(conn, "0000886744", "GERON CORP")
    client = daily_client(tmp_path)
    client.register_mock(
        quarter_listing_url(date(2025, 3, 1)), (FIX / "events" / "daily-index-2025-QTR1.json").read_bytes()
    )
    day_state, pending = tmp_path / "day.json", tmp_path / "pending.json"
    save_last_day(day_state, date(2025, 2, 28))
    stats = run_catch_up(conn, client, date(2025, 3, 5), pending, day_state)
    assert [s.day for s in stats] == ["2025-03-03", "2025-03-04"] and stats[0].purchases == 3
    assert load_last_day(day_state) == date(2025, 3, 4)
    assert run_catch_up(conn, client, date(2025, 3, 5), pending, day_state) == []  # nothing new until 03-05 is listed


class NotYet(HttpClient):
    """The mocks, except that `missing` URLs answer 403 (SEC's answer for an index it hasn't written yet)."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.missing: set[str] = set()

    def get_bytes(self, url: str, *, use_cache: bool = False, timeout: float = 60.0) -> bytes:
        import httpx

        if url in self.missing:
            raise httpx.HTTPStatusError("403", request=httpx.Request("GET", url), response=httpx.Response(403))
        return super().get_bytes(url, use_cache=use_cache, timeout=timeout)


def catch_up_client(tmp_path: Path) -> NotYet:
    from pipeline.us.events import quarter_listing_url

    client = NotYet(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    client.mocks = daily_client(tmp_path).mocks
    client.register_mock(
        quarter_listing_url(date(2025, 3, 1)), (FIX / "events" / "daily-index-2025-QTR1.json").read_bytes()
    )
    return client


def test_catch_up_rereads_a_day_whose_index_is_not_there_yet(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Review F2: a listed weekday whose index answers 403 isn't a holiday. It holds the cursor and the next run reads
    it; a day that keeps failing is passed after RETRY_RUNS runs with the error logged."""
    from pipeline.us.daily import RETRY_RUNS, load_last_day, run_catch_up, save_last_day

    add(conn, "0000886744", "GERON CORP")
    quidel = add(conn, "0001906324", "QuidelOrtho Corp")
    client = catch_up_client(tmp_path)
    client.missing = {master_index_url(date(2025, 3, 4))}
    day_state, pending = tmp_path / "day.json", tmp_path / "pending.json"
    save_last_day(day_state, date(2025, 2, 28))
    first = run_catch_up(conn, client, date(2025, 3, 5), pending, day_state)
    assert [(s.day, s.purchases, s.retry) for s in first] == [("2025-03-03", 3, 0), ("2025-03-04", 0, 1)]
    assert "not published yet" in first[1].errors[0] and load_last_day(day_state) == date(2025, 3, 3)

    client.missing = set()
    second = run_catch_up(conn, client, date(2025, 3, 5), pending, day_state)
    assert [(s.day, s.corp_events, s.retry) for s in second] == [("2025-03-04", 1, 0)]
    assert load_last_day(day_state) == date(2025, 3, 4)
    assert [e.kind for e in as_of(date(2025, 3, 5)).corp_events(conn, [quidel])] == ["auditor_change"]

    save_last_day(day_state, date(2025, 3, 3))
    client.missing = {master_index_url(date(2025, 3, 4))}
    for run in range(1, RETRY_RUNS + 1):
        stats = run_catch_up(conn, client, date(2025, 3, 20), pending, day_state)
        assert [s.retry for s in stats] == [1]
        held = run < RETRY_RUNS
        assert load_last_day(day_state) == (date(2025, 3, 3) if held else date(2025, 3, 4)), run
    assert "moving on" in stats[0].errors[-1]  # passed after the last run, with the error in the run's stats


def test_catch_up_retries_a_failed_download_by_runs_not_days(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Review R2-F5: Friday's index is first read on Tuesday, 4 days later. A Form 4 that fails to download on that
    first read still holds the cursor, and the next run stores the purchase."""
    from pipeline.us.daily import load_last_day, run_catch_up, save_last_day

    geron = add(conn, "0000886744", "GERON CORP")
    client = catch_up_client(tmp_path)
    form4 = "https://www.sec.gov/Archives/edgar/data/886744/0000950170-25-030327.txt"
    client.missing = {form4}
    day_state, pending = tmp_path / "day.json", tmp_path / "pending.json"
    save_last_day(day_state, date(2025, 2, 28))
    today = date(2025, 3, 11)  # a week after 03-03: a calendar-day window would already have given up
    first = run_catch_up(conn, client, today, pending, day_state)
    assert [(s.day, s.purchases, s.retry) for s in first] == [("2025-03-03", 2, 1), ("2025-03-04", 0, 0)]
    assert load_last_day(day_state) == date(2025, 2, 28)  # held at the day before the failed one
    client.missing = set()
    second = run_catch_up(conn, client, today, pending, day_state)
    assert [(s.day, s.retry) for s in second] == [("2025-03-03", 0), ("2025-03-04", 0)]
    assert load_last_day(day_state) == date(2025, 3, 4)
    assert len(as_of(date(2025, 3, 5)).insider_events(conn, [geron])) == 3


def test_catch_up_on_the_first_day_of_a_quarter(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Review R2-F6: at 01:30 UTC on a quarter's first day SEC hasn't created its listing (403). The run reads the
    previous quarter's remaining days and returns."""
    from pipeline.us.daily import load_last_day, run_catch_up, save_last_day
    from pipeline.us.events import quarter_listing_url

    add(conn, "0001906324", "QuidelOrtho Corp")
    client = catch_up_client(tmp_path)
    client.missing = {quarter_listing_url(date(2025, 4, 1))}
    day_state, pending = tmp_path / "day.json", tmp_path / "pending.json"
    save_last_day(day_state, date(2025, 3, 3))
    stats = run_catch_up(conn, client, date(2025, 4, 1), pending, day_state)
    assert [s.day for s in stats] == ["2025-03-04"] and stats[0].corp_events == 1
    assert load_last_day(day_state) == date(2025, 3, 4)


def test_companies_outside_the_universe_are_ignored(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    add(conn, "0000886744", "GERON CORP", in_universe=False)
    stats = run_daily(conn, daily_client(tmp_path), date(2025, 3, 3), tmp_path / "pending.json")
    assert (stats.form4_filings, stats.purchases, stats.corp_events) == (0, 0, 0)


def test_weekend_index_is_a_quiet_no_op(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    import httpx

    class NotFound(HttpClient):
        def get_bytes(self, url: str, *, use_cache: bool = False, timeout: float = 60.0) -> bytes:
            raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url), response=httpx.Response(404))

    c = NotFound(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    assert run_daily(conn, c, date(2025, 3, 1), None).index_rows == 0


def test_spinoff_becomes_effective_with_parent_candidates(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """GE Vernova filed its Form 10 in Feb 2024 (remembered in the pending state) and separated on 2024-04-02."""
    ge = add(conn, "0000040545", "GENERAL ELECTRIC CO")
    state = tmp_path / "pending.json"
    state.write_text(json.dumps(["0001996810"]), encoding="utf-8")
    index = ("Description: Daily Index of EDGAR Dissemination Feed by Company Name\n\n"
             "CIK|Company Name|Form Type|Date Filed|File Name\n" + "-" * 80 + "\n"
             "1996810|GE Vernova Inc.|8-K|20240402|edgar/data/1996810/0001193125-24-084048.txt\n")  # fmt: skip
    assert len(parse_master_index(index)) == 1
    c = mock_client(tmp_path)
    c.register_mock(master_index_url(date(2024, 4, 2)), index.encode())
    c.register_mock(submissions_url("0001996810"), (FIX / "submissions" / "CIK0001996810.json").read_bytes())
    c.register_mock("https://www.sec.gov/Archives/edgar/data/1996810/000119312524059354/d542465d1012ba.htm",
                    (FIX / "events" / "gev_form10.htm").read_bytes())  # fmt: skip
    stats = run_daily(conn, c, date(2024, 4, 2), state)
    assert (stats.spinoffs, stats.errors) == (1, [])
    assert json.loads(state.read_text(encoding="utf-8")) == []  # no longer pending
    gev = repo.company_ids_by(conn, "cik")["0001996810"]
    (event,) = as_of(date(2024, 4, 2)).corp_events(conn, [gev])
    assert (event.kind, event.event_date, event.filed_at) == (
        "spinoff", date(2024, 4, 2), datetime(2024, 4, 2, 10, 58, 4, tzinfo=UTC))  # fmt: skip
    assert event.detail["evidence"] == "8-K 5.01/3.03" and event.detail["confirmed"] is False
    assert [p["cik"] for p in event.detail["parent_candidates"]] == ["0000040545"]
    registrant = next(x for x in repo.companies(conn, market="us") if x.cik == "0001996810")
    assert not registrant.in_universe and ge != gev


# ---------------------------------------------------------------- M2-05


def test_13f_run_writes_holder_counts_available_after_the_window(conn: psycopg.Connection[Any]) -> None:
    aapl = add(conn, "0000320193", "Apple Inc.")
    googl = add(conn, "0001652044", "Alphabet Inc.")
    add(conn, "0000886744", "GERON CORP", in_universe=False)  # not in the universe: no row
    with (FIX / "13f" / "SUBMISSION.tsv").open(encoding="utf-8") as s, \
            (FIX / "13f" / "COVERPAGE.tsv").open(encoding="utf-8") as cp, \
            (FIX / "13f" / "INFOTABLE.tsv").open(encoding="utf-8") as i:  # fmt: skip
        ds = read_dataset(s, cp, i, date(2025, 2, 28))
    stats = run_13f(conn, ds)
    assert stats.period == "2024-12-31" and stats.companies == 2
    expected = {r.split(",")[0]: int(r.split(",")[1]) for r in
                (FIX / "13f" / "expected_counts.csv").read_text(encoding="utf-8").splitlines()[1:]}  # fmt: skip
    assert as_of(date(2025, 2, 28)).ownership(conn, [aapl, googl]) == []  # the window closes 2025-02-28
    rows = {r.company_id: r for r in as_of(date(2025, 3, 1)).ownership(conn, [aapl, googl])}
    assert rows[aapl].inst_holders == expected["037833100"] and rows[aapl].source == "sec_13f"
    assert max(expected["02079K107"], expected["02079K305"]) <= rows[googl].inst_holders
    assert rows[googl].inst_holders <= expected["02079K107"] + expected["02079K305"]


# ---------------------------------------------------------------- M2-06


def test_weekly_run_on_f_us(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    ids = {cik: add(conn, cik, name) for cik, name in F_US.items()}
    cf, subs, state = JsonSource(FIX / "companyfacts"), JsonSource(FIX / "submissions"), tmp_path / "state.json"
    t0 = time.monotonic()
    stats = run_weekly(conn, cf, subs, date(2026, 9, 20), state, issues_path=tmp_path / "issues.csv")
    assert time.monotonic() - t0 < 600  # BRIEF M2-06: < 10 min in CI
    assert (stats.companies, stats.quarterized, stats.errors, stats.in_universe) == (8, 8, [], 8)
    logged = (tmp_path / "issues.csv").read_text(encoding="utf-8").splitlines()
    assert logged[0] == "cik,period_end,column,reason" and len(logged) - 1 == stats.issues > 20  # review F8: all
    assert sum(stats.issue_counts.values()) == stats.issues
    n_rows = conn.execute("select count(*) from fundamentals_q").fetchone()
    assert n_rows is not None and n_rows[0] == stats.rows > 8 * 40
    again = run_weekly(conn, cf, subs, date(2026, 9, 20), state)  # unchanged files: nothing re-quarterized
    assert (again.quarterized, again.unchanged, again.in_universe) == (0, 8, 8)
    forced = run_weekly(conn, cf, subs, date(2026, 9, 20), state, force=True)
    assert forced.quarterized == 8 and conn.execute("select count(*) from fundamentals_q").fetchone() == n_rows
    saved = json.loads(state.read_text(encoding="utf-8"))
    saved["0000320193"]["v"] = "old-map"  # a changed xbrl_map / quarterize version re-quarterizes that company
    state.write_text(json.dumps(saved), encoding="utf-8")
    assert run_weekly(conn, cf, subs, date(2026, 9, 20), state).quarterized == 1
    companies = {c.cik: c for c in repo.companies(conn, market="us")}
    assert companies["0000320193"].sector == "technology" and companies["0000320193"].fiscal_year_end == "0926"
    latest = {r.company_id: r for r in as_of(date(2026, 9, 20)).fundamentals(conn, list(ids.values()))}
    assert all(latest[i].revenue is not None for i in ids.values())


def test_weekly_run_isolates_a_broken_company(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    add(conn, "0000320193", "Apple Inc.")
    add(conn, "0000789019", "MICROSOFT CORP")
    broken = tmp_path / "cf"
    broken.mkdir()
    (broken / "CIK0000320193.json").write_text("{not json", encoding="utf-8")
    (broken / "CIK0000789019.json").write_bytes((FIX / "companyfacts" / "CIK0000789019.json").read_bytes())
    stats = run_weekly(conn, JsonSource(broken), JsonSource(FIX / "submissions"), date(2026, 9, 20),
                       tmp_path / "state.json")  # fmt: skip
    assert stats.quarterized == 1 and len(stats.errors) == 1 and stats.errors[0].startswith("0000320193")
    assert "0000320193" not in json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))  # retried next run


class Killed(BaseException):
    """The job timeout: not an Exception, so nothing in the run catches it."""


class CutOff(JsonSource):
    def read(self, name: str) -> bytes | None:
        if name == "CIK0001050915.json":  # the second company (by name) is where the job is killed
            raise Killed
        return super().read(name)


def test_weekly_run_cut_off_by_the_timeout_keeps_finished_companies(migrated_url: str, tmp_path: Path) -> None:
    """Review F1: each company is committed on its own, so a run killed by the job timeout keeps the work it did."""
    cat, pwr = "0000018230", "0001050915"
    with psycopg.connect(migrated_url) as c, psycopg.connect(migrated_url, autocommit=True) as observer:
        ids = [add(c, cat, F_US[cat]), add(c, pwr, F_US[pwr])]
        c.commit()
        try:
            with pytest.raises(Killed):
                run_weekly(c, CutOff(FIX / "companyfacts"), JsonSource(FIX / "submissions"), date(2026, 9, 20),
                           tmp_path / "state.json")  # fmt: skip
            counts = [
                observer.execute("select count(*) from fundamentals_q where company_id = %s", (i,)).fetchone()
                for i in ids
            ]
            assert counts[0] is not None and counts[0][0] > 0 and counts[1] == (0,)
        finally:
            c.rollback()
            c.execute("delete from fundamentals_q where company_id = any(%s)", (ids,))
            c.execute("delete from companies where id = any(%s)", (ids,))
            c.commit()


# ---------------------------------------------------------------- runs bookkeeping


def test_tracked_run_records_ok_partial_and_failed(migrated_url: str) -> None:
    kind = f"test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(migrated_url) as c:
        try:
            with repo.tracked_run(c, kind, kind) as stats:
                stats["n"] = 1
            with repo.tracked_run(c, kind) as stats:
                stats["errors"] = ["one company failed"]
            with pytest.raises(RuntimeError), repo.tracked_run(c, kind, kind) as stats:
                c.execute("insert into benchmarks_w (symbol, week_end, close) values (%s, '2025-01-03', 1)", (kind,))
                raise RuntimeError("boom")
            runs = c.execute("select status, stats, error from runs where kind = %s order by started_at", (kind,))
            got = runs.fetchall()
            assert [(s, e) for s, _, e in got] == [("ok", None), ("partial", None), ("failed", "RuntimeError: boom")]
            assert got[0][1] == {"n": 1}
            left = c.execute("select count(*) from benchmarks_w where symbol = %s", (kind,)).fetchone()
            assert left == (0,)  # the failed job's writes were rolled back
            health = c.execute("select last_error from source_health where source = %s", (kind,)).fetchone()
            assert health == ("RuntimeError: boom",)
        finally:
            c.rollback()
            c.execute("delete from runs where kind = %s", (kind,))
            c.execute("delete from source_health where source = %s", (kind,))
            c.commit()


def test_reseed_keeps_the_weekly_metadata(conn: psycopg.Connection[Any]) -> None:
    add(conn, "0000320193", "Apple Inc.")
    repo.update_us_company(
        conn,
        "0000320193",
        name="Apple Inc.",
        sic="3571",
        industry="ELECTRONIC COMPUTERS",
        sector="technology",
        fiscal_year_end="0926",
        in_universe=True,
        excluded_reason=None,
    )
    add(conn, "0000320193", "Apple Inc.")  # the quarterly re-seed: the snapshot has no SIC or sector
    apple = next(c for c in repo.companies(conn, market="us") if c.cik == "0000320193")
    assert (apple.sic, apple.sector, apple.industry, apple.fiscal_year_end) == (
        "3571", "technology", "ELECTRONIC COMPUTERS", "0926")  # fmt: skip


def test_reseed_keeps_the_weekly_universe_decision(conn: psycopg.Connection[Any]) -> None:
    """Review F9: the quarterly seed runs before the 13F step, so it must not re-admit a company the weekly run
    excluded (a SPAC here). A company the snapshot step had moved out is re-admitted once it is listed again."""
    from pipeline.db import seed

    spac, relisted = "0002040475", "0000320193"  # both in the committed SEC snapshot
    add(conn, spac, "Drugs Made In America Acquisition II Corp.")
    add(conn, relisted, "Apple Inc.")
    weekly = {"name": None, "industry": None, "sector": None, "fiscal_year_end": None, "in_universe": False}
    repo.update_us_company(conn, spac, **weekly, sic="6770", excluded_reason="SPAC (SIC 6770)")
    repo.update_us_company(conn, relisted, **weekly, sic="3571", excluded_reason=repo.SNAPSHOT_OUT["us"])
    seed.seed(conn)
    rows = conn.execute(
        "select cik, in_universe, excluded_reason, sic from companies where cik = any(%s)", ([spac, relisted],)
    ).fetchall()
    assert {r[0]: r[1:] for r in rows} == {
        spac: (False, "SPAC (SIC 6770)", "6770"),
        relisted: (True, None, "3571"),
    }


def test_form4_amendment_counts_once_and_the_original_stays_visible_before_it(conn: psycopg.Connection[Any]) -> None:
    """Review F4: a Form 4/A restating purchases is stored as filed (point-in-time), and readers count only the latest
    filing per insider and trade date: the original before the amendment is filed, the amendment after."""
    from pipeline.db.models import InsiderEvent
    from pipeline.signals.insiders import latest_versions
    from pipeline.us.form4 import parse_submission

    cid = add(conn, "0001697500", "Solaris Energy Infrastructure, Inc.")
    amended = parse_submission((FIX / "form4" / "0000950170-25-055869.txt").read_text(encoding="utf-8"))
    assert amended.document_type == "4/A" and amended.accepted_at is not None

    def events(filed_at: datetime, url: str) -> list[InsiderEvent]:
        return [InsiderEvent(company_id=cid, event_date=t.date, filed_at=filed_at, person=amended.person or "unknown",
                             kind="open_market_buy", shares=t.shares, value=t.value, currency="USD", source_url=url,
                             amends=amended.original_date) for t in amended.purchases()]  # fmt: skip

    first = datetime(2025, 3, 10, 21, tzinfo=UTC)  # the first amendment, which the fixture's 4/A restates
    repo.insert_insider_events(conn, events(first, "https://www.sec.gov/first-4a.txt"))
    repo.insert_insider_events(conn, events(amended.accepted_at, "https://www.sec.gov/second-4a.txt"))
    before = as_of(amended.accepted_at - timedelta(seconds=1)).insider_events(conn, [cid])  # as_of(t) includes t
    after = as_of(amended.accepted_at).insider_events(conn, [cid])
    assert len(after) == 2 * len(before) and len(before) == len(amended.purchases()) > 0  # history is kept
    assert {e.amends for e in after} == {date(2025, 2, 28)}  # both amend the Form 4 filed 2025-02-28
    assert {e.source_url for e in latest_versions(before)} == {"https://www.sec.gov/first-4a.txt"}
    kept = latest_versions(after)
    assert len(kept) == len(before) and {e.source_url for e in kept} == {"https://www.sec.gov/second-4a.txt"}
