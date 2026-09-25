"""M5 against the database: F-SYN through the text-facts pipeline (M5-02: every stored verified quote is its document's
canonical text at the stored offsets; the database refuses one that isn't), fact diffs, counterparty links, risk
changes, deferral to the next day (M5-03 at the pipeline level), the daily run's queue from SEC submissions and
filing indexes, and India announcement triage (P-07)."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from pipeline.db import facts_repo, repo
from pipeline.db.models import Company, CorpEvent
from pipeline.facts import run
from pipeline.facts.evaluate import SYN, load_truth
from pipeline.facts.process import normalize
from pipeline.llm.router import Router
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us.daily import submissions_url
from tests.facts.fakes import MultiOracle
from tests.llm.conftest import FakeClock, quotas

TRUTH = load_truth()
CIKS = {"NMBS": "0000999001", "VOLT": "0000999002", "KYST": "0000999003", "CLST": "0000999004"}
BASE = "https://www.sec.gov/Archives/edgar/data/999/syn"


def add_companies(conn: psycopg.Connection[Any]) -> dict[str, Company]:
    for t, c in TRUTH["companies"].items():
        if c["market"] == "us":
            conn.execute("insert into companies (market, name, cik, ticker, fiscal_year_end, capex_desk) "
                         "values ('us', %s, %s, %s, %s, true)", (c["name"], CIKS[t], t, c["fye"]))  # fmt: skip
        else:
            conn.execute("insert into companies (market, name, nse_symbol, isin, fiscal_year_end, capex_desk) "
                         "values ('in', %s, %s, 'INE000A01010', %s, true)", (c["name"], t, c["fye"]))  # fmt: skip
    return {(c.ticker or c.nse_symbol or ""): c for c in repo.companies(conn)}


def router(fail: bool = False, clock: FakeClock | None = None) -> Router:
    return Router({"gemini": MultiOracle(TRUTH, fail)}, quotas(["gemini"], rpd=10_000), clock or FakeClock())


def fetch(job: run.DocJob) -> bytes:
    return (SYN / job.url.rsplit("/", 1)[1]).read_bytes()


def jobs(companies: dict[str, Company]) -> list[run.DocJob]:
    out = []
    for d in sorted(TRUTH["documents"], key=lambda d: d["published_at"]):
        out.append(run.DocJob(companies[d["ticker"]], d["kind"], f"{BASE}/{d['file']}", d["title"],
                              datetime.fromisoformat(d["published_at"])))  # fmt: skip
    return out


def test_f_syn_in_the_database_keeps_every_quote_grounded(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    cos = add_companies(conn)
    r = router()
    stats = run.TextStats("2027-08-01")
    for job in jobs(cos):
        assert run.process(conn, job, fetch, r, tmp_path, stats) == "extracted", job.url
    run.link_pending(conn, r, stats)

    # M5-02: 100% grounding on the stored verified facts
    rows = conn.execute("select f.quote, f.char_start, f.char_end, d.url from facts f join documents d "
                        "on d.id = f.document_id where f.verification_status = 'verified'").fetchall()  # fmt: skip
    assert len(rows) == 23  # 24 planted; Aravalli's rupee order waits for review
    texts: dict[str, str] = {}
    for quote, s, e, url in rows:
        if url not in texts:
            texts[url] = normalize(url, (SYN / url.rsplit("/", 1)[1]).read_bytes()).text
        assert texts[url][s:e] == quote
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute("update facts set char_end = char_end + 1 where id = (select id from facts limit 1)")

    # diffs (F.6): Nimbus raised its fiscal 2027 capex guidance between the two 10-Qs
    kinds = dict(conn.execute("select subject_key, array_agg(change_kind order by created_at) from diffs "
                              "group by subject_key").fetchall())  # fmt: skip
    assert kinds["capex_guidance:FY2027"] == ["new", "raised"] and kinds["capex_guidance:FY2028"] == ["new"]
    note = conn.execute("select computed_note from diffs where change_kind = 'raised'").fetchone()
    assert note is not None and "→" in note[0] and "%" in note[0]
    superseded = conn.execute("select count(*) from facts where superseded_by is not null").fetchone()
    assert superseded == (1,)

    # links: three companies name Nimbus Compute as a counterparty; the entity is the company (CIK carried over)
    links = conn.execute("select c.ticker, l.relation, e.cik from links l join companies c on c.id = l.from_company_id "
                         "join entities e on e.id = l.to_entity_id order by 1").fetchall()  # fmt: skip
    assert [(t, rel) for t, rel, _ in links] == [("CLST", "customer"), ("KYST", "ppa_counterparty"),
                                                 ("VOLT", "partner")]  # fmt: skip
    assert {cik for _, _, cik in links} == {CIKS["NMBS"]} and stats.links == 3

    # risk changes (F.6): the 2026 10-K added a data-center demand paragraph; only tagged changes are stored
    rc = conn.execute("select change_kind, topic_tags, text_after, char_start, char_end from risk_changes").fetchall()
    added = [x for x in rc if x[0] == "added"]
    assert len(added) == 1 and "data_center" in added[0][1] and all(x[1] for x in rc)
    kyst = normalize("x.htm", (SYN / "kyst_10k_2026_risk.htm").read_bytes()).text
    assert kyst[added[0][3] : added[0][4]] == added[0][2] and len(added[0][2].split()) <= 25


def test_a_deferred_document_is_read_the_next_day(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    cos = add_companies(conn)
    job = next(j for j in jobs(cos) if j.url.endswith("volt_10q.htm"))
    clock = FakeClock(datetime(2026, 9, 25, 9, tzinfo=UTC))
    stats = run.TextStats("2026-09-25")
    assert run.process(conn, job, fetch, router(fail=True, clock=clock), tmp_path, stats) == "deferred"
    deferred = facts_repo.deferred_documents(conn)
    assert [d["url"] for d in deferred] == [job.url] and stats.deferred == 1
    assert conn.execute("select count(*) from facts").fetchone() == (0,)  # all or nothing per document
    assert run.process(conn, job, fetch, router(clock=clock), tmp_path, stats) == "extracted"  # the next day's run
    assert conn.execute("select status from documents where url = %s", (job.url,)).fetchone() == ("extracted",)
    assert conn.execute("select count(*) from facts").fetchone() == (5,)


def submissions(cik: str) -> bytes:
    recent = {"accessionNumber": ["0000999001-26-000101", "0000999001-26-000102"], "form": ["10-Q", "8-K"],
              "filingDate": ["2026-09-10", "2026-09-15"], "reportDate": ["2026-06-30", "2026-09-15"],
              "acceptanceDateTime": ["2026-09-10T16:05:00.000Z", "2026-09-15T20:05:00.000Z"],
              "items": ["", "2.02,9.01"], "primaryDocument": ["nmbs-10q.htm", "nmbs-8k.htm"]}  # fmt: skip
    return json.dumps({"cik": cik, "name": "Nimbus Compute Corp.", "fiscalYearEnd": "0630", "tickers": ["NMBS"],
                       "filings": {"recent": recent, "files": []}}).encode()  # fmt: skip


def nimbus(conn: psycopg.Connection[Any], tmp_path: Path) -> HttpClient:
    """A capex-desk company with a 10-Q and an 8-K (EX-99.1 press release) filed in the last days."""
    conn.execute("insert into companies (market, name, cik, ticker, fiscal_year_end, capex_desk) values "
                 "('us', 'Nimbus Compute Corp.', %s, 'NMBS', '0630', true)", (CIKS["NMBS"],))  # fmt: skip
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    arch = "https://www.sec.gov/Archives/edgar/data/999001"
    http.register_mock(submissions_url(CIKS["NMBS"]), submissions(CIKS["NMBS"]))
    http.register_mock(f"{arch}/000099900126000101/nmbs-10q.htm", (SYN / "nmbs_10q_q1.htm").read_bytes())
    index = ('<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr><tr><td>1</td><td>8-K</td>'
             '<td><a href="/Archives/edgar/data/999001/000099900126000102/nmbs-8k.htm">nmbs-8k.htm</a></td><td>8-K</td>'
             '</tr><tr><td>2</td><td>PRESS RELEASE</td><td><a href="/Archives/edgar/data/999001/000099900126000102/'
             'ex991.htm">ex991.htm</a></td><td>EX-99.1</td></tr></table>')  # fmt: skip
    http.register_mock(f"{arch}/000099900126000102/0000999001-26-000102-index.htm", index.encode())
    http.register_mock(f"{arch}/000099900126000102/ex991.htm", (SYN / "nmbs_pr_guidance.htm").read_bytes())
    return http


def test_the_daily_run_queues_fetches_and_extracts(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    http = nimbus(conn, tmp_path)
    stats = run.run(conn, date(2026, 9, 25), router(), http, None, tmp_path)
    assert stats.queued_filings == 2 and stats.extracted == 2 and stats.errors == [], stats
    statuses = dict(conn.execute("select form_type, status from filings").fetchall())
    assert statuses == {"10-Q": "extracted", "8-K": "extracted"}
    kinds = {r[0] for r in conn.execute("select kind from documents").fetchall()}
    assert kinds == {"10-Q", "EX-99.1"} and stats.facts_verified == 4 + 2
    again = run.run(conn, date(2026, 9, 26), router(), http, None, tmp_path)
    assert again.queued_filings == 0 and again.documents == 0  # nothing new: nothing re-read


def test_a_deferred_filing_is_read_once_the_next_day(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M5 review R1-F2: on day 1 every provider is rate-limited, so the 10-Q defers and its filing stays new; on day 2
    each document is read once (not from the deferred list and again from its filing): one fact row per distinct
    fact, no "reaffirmed" diff between two facts of one document, and the P-01 requests of a clean single run."""
    http = nimbus(conn, tmp_path)
    with conn.transaction(force_rollback=True):
        clean = MultiOracle(TRUTH)
        run.run(conn, date(2026, 9, 26), Router({"gemini": clean}, quotas(["gemini"], rpd=10_000), FakeClock()),
                http, None, tmp_path)  # fmt: skip
        expected = sorted(r.user for r in clean.requests if r.prompt_id == "P-01")
    first = run.run(conn, date(2026, 9, 25), router(fail=True), http, None, tmp_path)
    assert first.deferred >= 1 and conn.execute("select count(*) from facts").fetchone() == (0,)
    oracle = MultiOracle(TRUTH)
    second = run.run(conn, date(2026, 9, 26), Router({"gemini": oracle}, quotas(["gemini"], rpd=10_000),
                                                       FakeClock()), http, None, tmp_path)  # fmt: skip
    assert second.errors == [] and second.extracted == 2, second
    rows = conn.execute("select count(*), count(distinct (document_id, subject_key, value_num, value_low, value_high)) "
                        "from facts").fetchone()  # fmt: skip
    assert rows is not None and rows[0] == rows[1] and rows[0] > 0
    same_doc = conn.execute("select count(*) from diffs d join facts a on a.id = d.new_fact_id join facts b on "
                            "b.id = d.prev_fact_id where d.change_kind = 'reaffirmed' and a.document_id = "
                            "b.document_id").fetchone()  # fmt: skip
    assert same_doc == (0,)
    assert sorted(r.user for r in oracle.requests if r.prompt_id == "P-01") == expected
    statuses = dict(conn.execute("select form_type, status from filings").fetchall())
    assert statuses == {"10-Q": "extracted", "8-K": "extracted"}


def test_the_time_budget_stops_between_documents(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """BRIEF §2.5's minutes budget: no document starts after `minutes`; the rest stays queued for the next run."""
    http = nimbus(conn, tmp_path)
    ticks = itertools.count(0, 300)  # every look at the clock is 5 minutes later
    stats = run.run(
        conn, date(2026, 9, 25), router(), http, None, tmp_path, minutes=8, clock=lambda: float(next(ticks))
    )
    assert stats.stopped == "time budget (8 min)" and stats.extracted == 1
    statuses = sorted(r[0] for r in conn.execute("select status from filings").fetchall())
    assert statuses == ["extracted", "new"]
    later = run.run(conn, date(2026, 9, 26), router(), http, None, tmp_path)
    assert later.extracted == 1 and later.stopped is None


def test_india_announcements_are_triaged_once(conn: psycopg.Connection[Any]) -> None:
    cos = add_companies(conn)
    arvl = cos["ARVL"]
    assert arvl.id is not None
    events = [
        CorpEvent(company_id=arvl.id, event_date=date(2026, 9, 24), filed_at=datetime(2026, 9, 24, 10, tzinfo=UTC),
                  kind="announcement", detail={"category": "Award of Order", "text": "Order for HV cables."},
                  source_url="https://nsearchives.nseindia.com/corporate/ARVL_24092026.pdf"),
        CorpEvent(company_id=arvl.id, event_date=date(2026, 9, 24), filed_at=datetime(2026, 9, 24, 11, tzinfo=UTC),
                  kind="announcement", detail={"category": "Trading Window", "text": "Closure of trading window."},
                  source_url="https://nsearchives.nseindia.com/corporate/ARVL_tw.pdf"),
    ]  # fmt: skip
    repo.insert_corp_events(conn, events)
    stats = run.TextStats("2026-09-25")
    in_scope: dict[UUID, Company] = {arvl.id: arvl}
    pdfs = run.triage_announcements(conn, router(), in_scope, date(2026, 9, 25), stats)
    assert stats.triaged == 1 and [j.url for j in pdfs] == [events[0].source_url] and pdfs[0].via_nse
    row = conn.execute("select categories, read_pdf from announcement_triage").fetchone()
    assert row == (["order_win"], True)
    assert run.triage_announcements(conn, router(), in_scope, date(2026, 9, 25), stats) == [] and stats.triaged == 1
