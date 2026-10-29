"""M5 against the database: F-SYN through the text-facts pipeline (M5-02: every stored verified quote is its document's
canonical text at the stored offsets; the database refuses one that isn't), fact diffs, counterparty links, deferral
to the next day (M5-03 at the pipeline level), the daily run's queue from SEC submissions and filing indexes, and
India announcement triage (P-07). The scope on stage names (docs/SPEC_ISSUES.md 50): the queue window filtered in
SQL, stale filings skipped and back for a new thesis, theses first, submissions read only for new or indexed names,
and no P-03 call; tests/facts/test_scope.py has the rules without a database."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.types.json import Jsonb

from pipeline.db import facts_repo, repo
from pipeline.db.models import Company, CorpEvent, FilingRow
from pipeline.facts import run
from pipeline.facts.evaluate import SYN, load_truth
from pipeline.facts.process import normalize
from pipeline.llm.router import Router
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us.daily import submissions_url
from pipeline.us.events import master_index_url
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
    oracle = MultiOracle(TRUTH)
    r = Router({"gemini": oracle}, quotas(["gemini"], rpd=10_000), FakeClock())
    stats = run.TextStats("2027-08-01")
    for job in jobs(cos):
        assert run.process(conn, job, fetch, r, tmp_path, stats) == "extracted", job.url
    run.link_pending(conn, r, stats)

    # M5-02: 100% grounding on the stored verified facts
    rows = conn.execute("select f.quote, f.char_start, f.char_end, d.url from facts f join documents d "
                        "on d.id = f.document_id where f.verification_status = 'verified'").fetchall()  # fmt: skip
    assert len(rows) == 24  # all 24 planted: Aravalli's rupee order is in its own currency (SPEC_ISSUES 58)
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

    # no risk-factor diff: the 10-Qs and KYST's two 10-Ks make no P-03 call (docs/SPEC_ISSUES.md 50)
    assert not [q for q in oracle.requests if q.prompt_id not in {"P-01", "P-02"}]
    assert conn.execute("select count(*) from risk_changes").fetchone() == (0,)


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


class PartialQuote:
    """F-SYN's oracle, plus the stock-price move quoted in part ("rose 23% during the quarter") with neutral labels."""

    name = "gemini"

    def __init__(self) -> None:
        self.inner = MultiOracle(TRUTH)

    def available(self) -> bool:
        return True

    def complete(self, req: Any) -> Any:
        from pipeline.llm.providers.base import Completion

        c = self.inner.complete(req)
        if req.prompt_id != "P-01" or "rose 23% during the quarter" not in req.user:
            return c
        extra = {"fact_type": "price_increase", "subject": "price increase", "subject_key": "price_increase:quarter",
                 "value": 23, "value_low": None, "value_high": None, "unit": "percent", "currency": None,
                 "scale_word": None, "period_label": None, "as_of": None, "counterparty": None, "location": None,
                 "withdrawn": False, "quote": "rose 23% during the quarter", "confidence": 0.9}  # fmt: skip
        return Completion({**c.content, "facts": [*c.content.get("facts", []), extra]}, c.tokens_in, c.tokens_out)


def test_a_partial_price_quote_is_not_stored(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M5 review R2-F1: VOLT's 10-Q with a P-01 answer that quotes only "rose 23% during the quarter" as a price
    increase: Verify-1 reads the sentence (a stock-price move) and stores no such fact, so S9 has nothing to count."""
    cos = add_companies(conn)
    job = next(j for j in jobs(cos) if j.url.endswith("volt_10q.htm"))
    stats = run.TextStats("2026-07-30")
    router = Router({"gemini": PartialQuote()}, quotas(["gemini"], rpd=10_000), FakeClock())
    assert run.process(conn, job, fetch, router, tmp_path, stats) == "extracted"
    assert conn.execute("select count(*) from facts where value_num = 23 or fact_type = 'price_increase'"
                        ).fetchone() == (0,)  # fmt: skip
    assert conn.execute("select count(*) from facts").fetchone() == (5,) and stats.rejected.get("V1-TYPE", 0) >= 1


def test_a_10q_makes_no_p03_call(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """docs/SPEC_ISSUES.md 50: a 10-Q, and a 10-K whose risk factors changed from the year before, are read with
    P-01 alone: no P-03 request, no risk_changes row."""
    cos = add_companies(conn)
    oracle = MultiOracle(TRUTH)
    r = Router({"gemini": oracle}, quotas(["gemini"], rpd=10_000), FakeClock())
    stats = run.TextStats("2026-09-25")
    for f in ("nmbs_10q_q1.htm", "kyst_10k_2025_risk.htm", "kyst_10k_2026_risk.htm"):
        assert run.process(conn, next(j for j in jobs(cos) if j.url.endswith(f)), fetch, r, tmp_path, stats) == (
            "extracted"
        )
    assert {q.prompt_id for q in oracle.requests} == {"P-01"} and stats.deferred == 0
    assert conn.execute("select count(*) from risk_changes").fetchone() == (0,)


def test_a_document_deferred_for_its_risk_diff_is_closed_without_reading_it_again(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    """A 10-Q left `deferred` with its facts stored (P-03 was rate-limited before this change) is marked extracted
    the next time it comes up, with no P-01 request and no fact stored twice; only the scope's deferred documents
    come up."""
    cos = add_companies(conn)
    job = next(j for j in jobs(cos) if j.url.endswith("nmbs_10q_q1.htm"))
    assert run.process(conn, job, fetch, router(), tmp_path, run.TextStats("2026-09-24")) == "extracted"
    conn.execute("update documents set status = 'deferred' where url = %s", (job.url,))
    facts = conn.execute("select count(*) from facts").fetchone()
    assert facts is not None and facts[0] > 0
    nmbs, kyst = cos["NMBS"].id, cos["KYST"].id
    assert nmbs is not None and kyst is not None
    assert [d["url"] for d in facts_repo.deferred_documents(conn, [nmbs])] == [job.url]
    assert facts_repo.deferred_documents(conn, [kyst]) == []
    oracle = MultiOracle(TRUTH)
    again = Router({"gemini": oracle}, quotas(["gemini"], rpd=10_000), FakeClock())
    assert run.process(conn, job, fetch, again, tmp_path, run.TextStats("2026-09-25")) == "extracted"
    assert oracle.requests == [] and conn.execute("select count(*) from facts").fetchone() == facts
    assert facts_repo.deferred_documents(conn) == []


ARCH = "https://www.sec.gov/Archives/edgar/data/999001"


@pytest.mark.parametrize(
    ("broken", "day1"),
    [
        (f"{ARCH}/000099900126000102/0000999001-26-000102-index.htm", {"10-Q": "extracted", "8-K": "new"}),
        (f"{ARCH}/000099900126000101/nmbs-10q.htm", {"10-Q": "new", "8-K": "extracted"}),
    ],
    ids=["503-on-the-8-k-index", "503-on-the-10-q"],
)
def test_a_503_is_read_again_the_next_day(conn: psycopg.Connection[Any], tmp_path: Path, broken: str,
                                          day1: dict[str, str]) -> None:  # fmt: skip
    """M5 review R2-F4: one transient fetch error leaves the filing `new`; the next day reads it, and the run ends
    with both documents and all 6 facts (as without the error)."""
    http = nimbus(conn, tmp_path)
    http.register_error(broken, 503)
    first = run.run(conn, date(2026, 9, 25), router(), http, None, tmp_path)
    assert dict(conn.execute("select form_type, status from filings").fetchall()) == day1 and first.errors
    run.run(conn, date(2026, 9, 26), router(), http, None, tmp_path)
    assert dict(conn.execute("select form_type, status from filings").fetchall()) == {"10-Q": "extracted",
                                                                                      "8-K": "extracted"}  # fmt: skip
    kinds = {r[0] for r in conn.execute("select kind from documents").fetchall()}
    assert kinds == {"10-Q", "EX-99.1"}
    assert conn.execute("select count(*) from facts where verification_status = 'verified'").fetchone() == (6,)


def test_a_filing_that_keeps_failing_ends_as_failed() -> None:
    """R2-F4: retries are bounded: past RETRY_DAYS a filing whose documents can't be fetched is `failed`."""
    assert run.filing_status(["retry"], expired=False) == "new"
    assert run.filing_status(["retry"], expired=True) == "failed"
    assert run.filing_status(["retry", "extracted"], expired=True) == "extracted"
    assert run.filing_status(["deferred"], expired=True) == "new"  # a rate limit always waits for the next day


def submissions(cik: str) -> bytes:
    recent = {"accessionNumber": ["0000999001-26-000101", "0000999001-26-000102"], "form": ["10-Q", "8-K"],
              "filingDate": ["2026-09-10", "2026-09-15"], "reportDate": ["2026-06-30", "2026-09-15"],
              "acceptanceDateTime": ["2026-09-10T16:05:00.000Z", "2026-09-15T20:05:00.000Z"],
              "items": ["", "2.02,9.01"], "primaryDocument": ["nmbs-10q.htm", "nmbs-8k.htm"]}  # fmt: skip
    return json.dumps({"cik": cik, "name": "Nimbus Compute Corp.", "fiscalYearEnd": "0630", "tickers": ["NMBS"],
                       "filings": {"recent": recent, "files": []}}).encode()  # fmt: skip


WEEK = date(2026, 9, 18)  # the latest scored week
DAY = date(2026, 9, 25)


def us_company(conn: psycopg.Connection[Any], name: str, ticker: str, cik: str | None = None) -> UUID:
    row = conn.execute("insert into companies (market, name, cik, ticker, fiscal_year_end) values ('us', %s, %s, %s, "
                       "'0630') returning id", (name, cik, ticker)).fetchone()  # fmt: skip
    assert row is not None
    cid: UUID = row[0]
    return cid


def stage_name(conn: psycopg.Connection[Any], cid: UUID, evidence: int = 45, bucket: str = "none",
               gap: int | None = None, week: date = WEEK) -> None:  # fmt: skip
    """Evidence >= 40 in the latest scored week: the candidate stage."""
    conn.execute("insert into scores (company_id, week_end, evidence, gap, families, bucket, weights_version) values "
                 "(%s, %s, %s, %s, '{fundamentals}', %s, 'w0-equal')", (cid, week, evidence, gap, bucket))  # fmt: skip


def research_entry(conn: psycopg.Connection[Any], cid: UUID) -> None:
    conn.execute("insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, "
                 "created_week) values (%s, 'research', '', '{}', '{}', 'manual', '{}', %s)", (cid, WEEK))  # fmt: skip


def at(days_ago: int) -> datetime:
    """Accepted at 21:00 UTC, `days_ago` days before DAY."""
    return datetime(DAY.year, DAY.month, DAY.day, 21, tzinfo=UTC) - timedelta(days=days_ago)


def filing(cid: UUID, accession: str, form: str, filed: datetime, items: tuple[str, ...] = (),
           url: str = f"{BASE}/none.htm") -> FilingRow:  # fmt: skip
    return FilingRow(company_id=cid, accession_no=accession, form_type=form, items=list(items), filed_at=filed,
                     accepted_at=filed, primary_doc_url=url, index_url=f"{url}-index.htm")  # fmt: skip


def mock_http(tmp_path: Path) -> HttpClient:
    return HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))


def nimbus(conn: psycopg.Connection[Any], tmp_path: Path) -> HttpClient:
    """A stage name (Evidence 45 in the latest scored week) with a 10-Q and an 8-K (EX-99.1 press release) filed in
    the last days."""
    stage_name(conn, us_company(conn, "Nimbus Compute Corp.", "NMBS", CIKS["NMBS"]))
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
    """M5 review R1-F2: on day 1 every provider is rate-limited, so a document defers and its filing stays new; on day 2
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


def test_out_of_scope_filings_never_starve_an_in_scope_filing(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """1,200 queued filings of a company out of scope (the old capex-desk queue): 200 older than a stage name's 120
    days are skipped; the 1,000 recent ones, all newer than the stage name's, stay queued but never fill the
    1,000-row window (the scope is filtered in SQL), and the stage name's 10-Q and 8-K are read."""
    http = nimbus(conn, tmp_path)
    other = us_company(conn, "Old Desk Co", "ODC")
    rows = [filing(other, f"0000999099-26-{k:06d}", "8-K", at(500 - k) if k < 200 else at(9) + timedelta(minutes=k),
                   ("2.02", "9.01")) for k in range(1200)]  # fmt: skip
    repo.insert_filings(conn, rows)
    nmbs = conn.execute("select id from companies where ticker = 'NMBS'").fetchone()
    assert nmbs is not None
    stats = run.run(conn, DAY, router(), http, None, tmp_path)
    assert stats.skipped_filings == 200 and stats.extracted == 2 and stats.errors == [], stats
    assert (stats.scope, stats.theses, stats.stage) == (1, 0, 1)
    got = conn.execute("select company_id = %s, status, count(*) from filings group by 1, 2 order by 1, 2",
                       (other,)).fetchall()  # fmt: skip
    assert got == [(False, "extracted", 2), (True, "new", 1000), (True, "skipped", 200)]
    assert len(facts_repo.filings_by_status(conn, ["new"], [other])) == 1000  # the window is the scope's alone
    assert facts_repo.filings_by_status(conn, ["new"], [nmbs[0]]) == []


def history(cik: str) -> bytes:
    """SEC submissions with filings from 5 to 500 days before DAY (tests/facts/test_scope.py HISTORY)."""
    rows = [(500, "10-K", ""), (300, "10-K", ""), (150, "10-Q", ""), (130, "8-K", "8.01"), (60, "8-K", "7.01"),
            (20, "10-Q", ""), (15, "10-Q/A", ""), (10, "8-K", "1.01,9.01"), (5, "8-K", "2.02,9.01"),
            (3, "8-K", "5.02")]  # fmt: skip
    recent: dict[str, list[str]] = {k: [] for k in ("accessionNumber", "form", "filingDate", "reportDate",
                                                    "acceptanceDateTime", "items", "primaryDocument")}  # fmt: skip
    for k, (ago, form, items) in enumerate(rows):
        filed = DAY - timedelta(days=ago)
        recent["accessionNumber"].append(f"{cik}-26-{k:06d}")
        recent["form"].append(form)
        recent["filingDate"].append(filed.isoformat())
        recent["reportDate"].append("")
        recent["acceptanceDateTime"].append(f"{filed.isoformat()}T21:00:00.000Z")
        recent["items"].append(items)
        recent["primaryDocument"].append(f"doc{k}.htm")
    return json.dumps({"cik": cik, "name": "X", "filings": {"recent": recent, "files": []}}).encode()  # fmt: skip


def test_stage_names_queue_their_latest_report_and_releases_theses_400_days(conn: psycopg.Connection[Any],
                                                                            tmp_path: Path) -> None:  # fmt: skip
    """A stage name queues its latest 10-Q or 10-K and its 8-Ks with item 2.02, 7.01 or 8.01 of the last 120 days;
    a thesis everything of the last 400 days (10-K, 10-Q, 8-K items 1.01, 2.02, 2.03, 7.01, 8.01)."""
    s_cik, t_cik = "0000999011", "0000999012"
    s, t = us_company(conn, "Stage Co", "STG", s_cik), us_company(conn, "Thesis Co", "THS", t_cik)
    http = mock_http(tmp_path)
    for cik in (s_cik, t_cik):
        http.register_mock(submissions_url(cik), history(cik))
    cos = {c.id: c for c in repo.companies(conn) if c.id in (s, t)}
    stats = run.TextStats(DAY.isoformat())
    run.queue_us(conn, http, cos, {s: run.RANK["stage"], t: run.RANK["thesis"]}, DAY, stats)
    got = conn.execute("select company_id, form_type, items, filed_at from filings").fetchall()
    queued = {cid: sorted(((DAY - f.astimezone(UTC).date()).days, form, tuple(items))
                          for c, form, items, f in got if c == cid) for cid in (s, t)}  # fmt: skip
    assert queued[s] == [(5, "8-K", ("2.02", "9.01")), (20, "10-Q", ()), (60, "8-K", ("7.01",))]
    assert queued[t] == [(5, "8-K", ("2.02", "9.01")), (10, "8-K", ("1.01", "9.01")), (20, "10-Q", ()),
                         (60, "8-K", ("7.01",)), (130, "8-K", ("8.01",)), (150, "10-Q", ()),
                         (300, "10-K", ())]  # fmt: skip
    assert stats.queued_filings == 10 and stats.submissions == 2
    assert stats.checked == {s_cik: run.RANK["stage"], t_cik: run.RANK["thesis"]}


def test_skipped_filings_come_back_when_the_name_becomes_a_thesis(conn: psycopg.Connection[Any],
                                                                  tmp_path: Path) -> None:  # fmt: skip
    """Out of scope, a company's queued 10-Q of 200 days ago and 10-K of 450 days ago are skipped, and so are a stage
    name's agreement 8-K and its 10-K older than its latest 10-Q (its latest 10-Q and its results 8-K stay queued).
    Once the first company is a research entry, its 10-Q (within 400 days) is queued again and read first, its 10-K
    stays skipped, and a thesis's filings are never skipped."""
    x = us_company(conn, "Next Thesis Co", "NXT")
    y = us_company(conn, "Stage Co", "STG")
    stage_name(conn, y)
    x_10q = f"{ARCH}/000099902126000001/nxt-10q.htm"
    repo.insert_filings(conn, [
        filing(x, "0000999021-26-000001", "10-Q", at(200), url=x_10q),
        filing(x, "0000999021-25-000002", "10-K", at(450)),
        filing(y, "0000999022-26-000001", "10-K", at(100)),
        filing(y, "0000999022-26-000002", "10-Q", at(20)),
        filing(y, "0000999022-26-000003", "8-K", at(10), ("1.01",)),
        filing(y, "0000999022-26-000004", "8-K", at(5), ("2.02", "9.01")),
    ])  # fmt: skip

    def status() -> dict[str, str]:
        return dict(conn.execute("select accession_no, status from filings").fetchall())

    stage_since, thesis_since = at(120).replace(hour=0), at(400).replace(hour=0)
    assert facts_repo.skip_stale_filings(conn, [], stage_since, thesis_since) == (4, 0)
    assert status() == {"0000999021-26-000001": "skipped", "0000999021-25-000002": "skipped",
                        "0000999022-26-000001": "skipped", "0000999022-26-000002": "new",
                        "0000999022-26-000003": "skipped", "0000999022-26-000004": "new"}  # fmt: skip
    research_entry(conn, x)
    http = mock_http(tmp_path)
    http.register_mock(x_10q, (SYN / "nmbs_10q_q1.htm").read_bytes())
    stats = run.run(conn, DAY, router(), http, None, tmp_path, documents_per_day=1)
    assert (stats.reset_filings, stats.skipped_filings, stats.theses, stats.stage) == (1, 0, 1, 1)
    assert stats.stopped == "daily document limit (1)" and stats.extracted == 1  # the thesis's, before the stage's
    assert status()["0000999021-26-000001"] == "extracted" and status()["0000999021-25-000002"] == "skipped"
    repo.insert_filings(conn, [filing(x, "0000999021-25-000003", "10-Q", at(300))])
    assert facts_repo.skip_stale_filings(conn, [x], stage_since, thesis_since) == (0, 0)
    assert status()["0000999021-25-000003"] == "new"


def test_a_filing_back_for_a_new_thesis_gets_its_retry_days(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """PR 3 review TXT-3: a 10-Q first queued long ago, skipped, and back when its company becomes a research entry
    counts RETRY_DAYS from its return: one 503 leaves it `new` (not `failed`), and the next day reads it."""
    x = us_company(conn, "Next Thesis Co", "NXT")
    x_10q = f"{ARCH}/000099902126000001/nxt-10q.htm"
    repo.insert_filings(conn, [filing(x, "0000999021-26-000001", "10-Q", at(200), url=x_10q)])
    conn.execute("update filings set created_at = %s", (at(200),))  # queued 200 days ago, under the old scope
    assert facts_repo.skip_stale_filings(conn, [], at(120), at(400)) == (1, 0)
    research_entry(conn, x)
    http = mock_http(tmp_path)
    http.register_error(x_10q, 503)
    http.register_mock(x_10q, (SYN / "nmbs_10q_q1.htm").read_bytes())
    first = run.run(conn, DAY, router(), http, None, tmp_path)
    assert first.reset_filings == 1 and first.errors and first.extracted == 0
    assert conn.execute("select status from filings").fetchone() == ("new",)
    second = run.run(conn, DAY + timedelta(days=1), router(), http, None, tmp_path)
    assert second.extracted == 1 and conn.execute("select status from filings").fetchone() == ("extracted",)


def test_a_stage_names_old_deferred_documents_are_not_read(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """PR 3 review TXT-2: a stage name reads its 120 days alone, deferred documents included. Its 10-Q deferred 300
    days ago, and one of 110 days ago whose filing is skipped (a later 10-Q is read), make no request and stay
    deferred; a thesis's deferred 10-Q of 300 days ago is read."""
    t, s = us_company(conn, "Nimbus Compute Corp.", "NMBS"), us_company(conn, "Voltara Grid Systems", "VOLT")
    research_entry(conn, t)
    stage_name(conn, s)
    repo.insert_filings(conn, [filing(s, "0000999051-26-000001", "10-Q", at(110)),
                               filing(s, "0000999051-26-000002", "10-Q", at(30))])  # fmt: skip
    conn.execute("update filings set status = 'extracted' where accession_no = '0000999051-26-000002'")
    skipped = conn.execute("select id from filings where accession_no = '0000999051-26-000001'").fetchone()
    assert skipped is not None
    http = mock_http(tmp_path)
    docs = {"t-300": (t, at(300), None, "nmbs_10q_q1.htm"), "s-300": (s, at(300), None, "volt_10q.htm"),
            "s-110": (s, at(110), skipped[0], "volt_10q.htm")}  # fmt: skip
    for k, (cid, published, filing_id, f) in docs.items():
        http.register_mock(f"{ARCH}/{k}/{f}", (SYN / f).read_bytes())
        facts_repo.upsert_document(conn, company_id=cid, filing_id=filing_id, kind="10-Q", url=f"{ARCH}/{k}/{f}",
                                   title="Form 10-Q", published_at=published, sha256="0" * 64, raw_path="x",
                                   status="deferred")  # fmt: skip
    conn.execute("update documents set created_at = published_at")  # the stage name was last read 110 days ago: due
    oracle = MultiOracle(TRUTH)
    stats = run.run(conn, DAY, Router({"gemini": oracle}, quotas(["gemini"], rpd=10_000), FakeClock()), http, None,
                    tmp_path)  # fmt: skip
    assert (stats.theses, stats.stage, stats.skipped_filings, stats.extracted) == (1, 1, 1, 1), stats
    assert [u.rsplit("/", 2)[1] for u in http.calls] == ["t-300"]
    got = dict(conn.execute("select url, status from documents").fetchall())
    assert {u.rsplit("/", 2)[1]: st for u, st in got.items()} == {"t-300": "extracted", "s-300": "deferred",
                                                                  "s-110": "deferred"}  # fmt: skip
    p01 = [r.user for r in oracle.requests if r.prompt_id == "P-01"]
    assert p01 and all("Voltara" not in u for u in p01)


def test_theses_are_read_before_stage_names_each_newest_first(conn: psycopg.Connection[Any],
                                                              tmp_path: Path) -> None:  # fmt: skip
    """With one document a day: the thesis's newer 10-Q, then its older one, then the stage name's, although the
    stage name's was filed last."""
    t, s = us_company(conn, "Nimbus Compute Corp.", "NMBS"), us_company(conn, "Voltara Grid Systems", "VOLT")
    research_entry(conn, t)
    stage_name(conn, s)
    http = mock_http(tmp_path)
    docs = {"t-old": (t, at(60), "nmbs_10q_q1.htm"), "t-new": (t, at(20), "nmbs_10q_q2.htm"),
            "s": (s, at(1), "volt_10q.htm")}  # fmt: skip
    for k, (cid, filed, f) in enumerate(docs.values()):
        http.register_mock(f"{ARCH}/{k}/{f}", (SYN / f).read_bytes())
        repo.insert_filings(conn, [filing(cid, f"0000999041-26-{k:06d}", "10-Q", filed, url=f"{ARCH}/{k}/{f}")])
    read: list[str] = []
    for _ in docs:
        before = {r[0] for r in conn.execute("select url from documents").fetchall()}
        stats = run.run(conn, DAY, router(), http, None, tmp_path, documents_per_day=1)
        assert stats.extracted == 1, stats
        read += [u.rsplit("/", 1)[1] for u in {r[0] for r in conn.execute("select url from documents")} - before]
    assert read == ["nmbs_10q_q2.htm", "nmbs_10q_q1.htm", "volt_10q.htm"]


def test_the_stage_reads_its_boards_first_then_one_fact_from_a_candidate_excluded_last(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    """docs/SPEC_ISSUES.md 58: with one document a day, a Watch name's report first, then the name one verified S9
    fact would make a Candidate (Gap >= 50), then the rest, the Excluded name last: each place before the next,
    although the later places' filings are newer. The run records the scope and the reading by place."""
    names = {"watch": ("watch", 70, "nmbs_10q_q1.htm", 90), "one_fact": ("none", 60, "nmbs_10q_q2.htm", 60),
             "stage": ("none", 30, "volt_10q.htm", 30), "excluded": ("excluded", 95, "kyst_10q.htm", 1)}  # fmt: skip
    http = mock_http(tmp_path)
    for k, (key, (bucket, gap, f, ago)) in enumerate(names.items()):
        cid = us_company(conn, f"{key} Co", key.upper()[:4])
        stage_name(conn, cid, bucket=bucket, gap=gap)
        http.register_mock(f"{ARCH}/{k}/{f}", (SYN / f).read_bytes())
        repo.insert_filings(conn, [filing(cid, f"0000999051-26-{k:06d}", "10-Q", at(ago), url=f"{ARCH}/{k}/{f}")])
    read: list[str] = []
    stats = None
    for _ in names:
        before = {r[0] for r in conn.execute("select url from documents").fetchall()}
        stats = run.run(conn, DAY, router(), http, None, tmp_path, documents_per_day=1)
        assert stats.extracted == 1, stats
        read += [u.rsplit("/", 1)[1] for u in {r[0] for r in conn.execute("select url from documents")} - before]
    assert read == ["nmbs_10q_q1.htm", "nmbs_10q_q2.htm", "volt_10q.htm", "kyst_10q.htm"]
    assert stats is not None and stats.read_by_order == {"excluded": 1}


def test_each_market_reads_its_own_latest_scored_week(conn: psycopg.Connection[Any]) -> None:
    """docs/SPEC_ISSUES.md 58: a market scored alone (the US re-scored on Monday) doesn't drop the other's stage
    names, as the single latest week did; an older week of the same market isn't read."""
    us = us_company(conn, "Nimbus Compute Corp.", "NMBS")
    row = conn.execute("insert into companies (market, name, nse_symbol, isin, fiscal_year_end) values ('in', "
                       "'Aravalli Cables Limited', 'ARVL', 'INE000A01010', '0331') returning id"
                       ).fetchone()  # fmt: skip
    assert row is not None
    india = row[0]
    stage_name(conn, us, week=WEEK - timedelta(days=7), bucket="watch", gap=70)  # last week's: not read
    stage_name(conn, us, evidence=30, week=WEEK)  # this week the US name is out of the stage
    stage_name(conn, india, week=WEEK - timedelta(days=7), bucket="watch", gap=80)  # India's latest week
    got = facts_repo.stage_names(conn, run.STAGE_MIN_EVIDENCE)
    assert [(s.company_id, s.bucket, s.gap) for s in got] == [(india, "watch", 80)]
    assert run.scope(conn, DAY, []) == {india: run.ORDER.index("board")}


def empty_submissions(cik: str) -> bytes:
    return json.dumps({"cik": cik, "name": "X", "filings": {"recent": {"accessionNumber": []}, "files": []}}).encode()


@pytest.mark.parametrize(
    ("index_ok", "sec_cut_off", "fetched"),
    [(True, None, "BC"), (False, None, "ABC"), (True, "failed", "ABC"), (True, "running", "ABC")],
    ids=["indexed", "index-unreadable", "sec-step-failed", "sec-step-cut-off"],
)
def test_submissions_are_read_only_for_new_or_indexed_names(conn: psycopg.Connection[Any], tmp_path: Path,
                                                            index_ok: bool, sec_cut_off: str | None,
                                                            fetched: str) -> None:  # fmt: skip
    """Three stage names: A is in the last text run's record, B is new to the scope, and C is in the record and filed
    an 8-K on a day whose EDGAR index the SEC step read since (A's Form 4 that day is no text filing): only B's and
    C's submissions are read. When that index can't be read, every name's are. So too when an SEC step between the
    two text runs failed or was cut off by the job's timeout (PR 3 review TXT-1): the days it committed moved its
    cursor on, but its runs row has no `days`, so a filing of those days would never be queued."""
    ciks = {"A": "0000999031", "B": "0000999032", "C": "0000999033"}
    for k, cik in ciks.items():
        stage_name(conn, us_company(conn, f"{k} Co", k, cik))
    runs = "insert into runs (kind, started_at, finished_at, status, stats) values (%s, %s, %s, %s, %s)"
    conn.execute(runs, ("text", "2026-09-24 01:20+00", "2026-09-24 01:30+00", "ok",
                        Jsonb({"checked": {ciks["A"]: 1, ciks["C"]: 1}})))  # fmt: skip
    if sec_cut_off is not None:  # the catch-up of 2026-09-24 13:00 read a day, then raised or hit the timeout
        conn.execute(runs, ("us_daily", "2026-09-24 13:00+00", "2026-09-24 13:20+00" if sec_cut_off == "failed"
                            else None, sec_cut_off, Jsonb({})))  # fmt: skip
    conn.execute(runs, ("us_daily", "2026-09-25 01:14+00", "2026-09-25 01:16+00", "ok",
                        Jsonb({"days": [{"day": "listings as of 2026-09-25", "index_rows": 0},
                                        {"day": "2026-09-24", "index_rows": 2}]})))  # fmt: skip
    index = ("CIK|Company Name|Form Type|Date Filed|File Name\n" + "-" * 80 + "\n"
             "999033|C CO|8-K|20260924|edgar/data/999033/0000999033-26-000001.txt\n"
             "999031|A CO|4|20260924|edgar/data/999031/0000999031-26-000002.txt\n")  # fmt: skip
    http = mock_http(tmp_path)
    if index_ok:
        http.register_mock(master_index_url(date(2026, 9, 24)), index.encode())
    else:
        http.register_error(master_index_url(date(2026, 9, 24)), 403)
    for k in fetched:
        http.register_mock(submissions_url(ciks[k]), empty_submissions(ciks[k]))
    stats = run.run(conn, DAY, router(), http, None, tmp_path)
    assert [u for u in http.calls if "/submissions/" in u] == [submissions_url(ciks[k]) for k in fetched]
    # no daily index is read after a failed or cut-off SEC step, so none is counted (integration review db-DB-1)
    assert stats.submissions == len(fetched) and stats.indexed == (1 if index_ok and sec_cut_off is None else 0)
    assert stats.checked == dict.fromkeys(ciks.values(), run.RANK["stage"])
    assert bool(stats.errors) is (fetched == "ABC")  # the unreadable index, or the SEC step's failure, is logged
    after = datetime(2026, 9, 24, 1, 20, tzinfo=UTC)
    assert (facts_repo.sec_days_since(conn, after) is None) is (sec_cut_off is not None)


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
    again = run.triage_announcements(conn, router(), in_scope, date(2026, 9, 25), stats)
    # not triaged again; its PDF is offered until it has been read (run() drops URLs already read; M5 review R2-F4)
    assert [j.url for j in again] == [events[0].source_url] and stats.triaged == 1


class RupeesWithoutCurrency:
    """F-SYN's oracle, but its P-01 answers leave `currency` null for rupee amounts (P-01's schema allows it)."""

    name = "gemini"

    def __init__(self) -> None:
        self.inner = MultiOracle(TRUTH)

    def available(self) -> bool:
        return True

    def complete(self, req: Any) -> Any:
        from pipeline.llm.providers.base import Completion

        c = self.inner.complete(req)
        if req.prompt_id != "P-01":
            return c
        facts = [{**f, "currency": None} if f.get("currency") == "INR" else f for f in c.content.get("facts", [])]
        return Completion({**c.content, "facts": facts}, c.tokens_in, c.tokens_out)


def test_an_indian_rupee_order_without_a_currency_is_verified_as_rupees(conn: psycopg.Connection[Any],
                                                                       tmp_path: Path) -> None:  # fmt: skip
    """M5 review R3-F1 and docs/SPEC_ISSUES.md 31 option b (58): ARVL's Rs 371 crore order, answered with no currency,
    is stored as rupees, never as $3.7B: the quote's currency decides, and an Indian company's own currency is
    verified. Its diff reads in crore and ARVL's S9 fires (the same order at a US filer waits for review:
    tests/facts/test_verify.py)."""
    from pipeline.signals import weekly

    cos = add_companies(conn)
    job = next(j for j in jobs(cos) if j.url.endswith("arvl_pr_order.htm"))
    r = Router({"gemini": RupeesWithoutCurrency()}, quotas(["gemini"], rpd=10_000), FakeClock())
    assert run.process(conn, job, fetch, r, tmp_path, run.TextStats("2026-09-18")) == "extracted"
    row = conn.execute("select verification_status, currency, unit, value_num from facts where fact_type = "
                       "'order_win'").fetchone()  # fmt: skip
    assert row == ("verified", "INR", "usd", 3710000000)
    notes = conn.execute("select computed_note from diffs where subject_key like 'order_win:%'").fetchall()
    assert notes == [("new: ₹371 cr",)]
    weekly.run(conn, date(2026, 9, 25), http=None)
    s9 = conn.execute("select v.fired, v.inputs from signal_values v join companies c on c.id = v.company_id where "
                      "c.nse_symbol = 'ARVL' and v.week_end = '2026-09-25' and v.signal_id = 'S9'"
                      ).fetchone()  # fmt: skip
    assert s9 is not None and s9[0] is True and s9[1]["count"] == 1


DATED_EPS_OLD = "Diluted earnings per share were $1.87, up 14% from a year ago."
DATED_EPS_NEW = (
    "Diluted earnings per share were $1.87 for the quarter ended September 30, 2026, up 14% from a year ago."
)


class EpsPart:
    """F-SYN's oracle, plus the EPS move quoted in part ("up 14% from a year ago") as a price increase."""

    name = "gemini"

    def __init__(self) -> None:
        self.inner = MultiOracle(TRUTH)

    def available(self) -> bool:
        return True

    def complete(self, req: Any) -> Any:
        from pipeline.llm.providers.base import Completion

        c = self.inner.complete(req)
        if req.prompt_id != "P-01" or "up 14% from a year ago" not in req.user:
            return c
        extra = {"fact_type": "price_increase", "subject": "increase", "subject_key": "price_increase:year",
                 "value": 14, "value_low": None, "value_high": None, "unit": "percent", "currency": None,
                 "scale_word": None, "period_label": None, "as_of": None, "counterparty": None, "location": None,
                 "withdrawn": False, "quote": "up 14% from a year ago", "confidence": 0.9}  # fmt: skip
        return Completion({**c.content, "facts": [*c.content.get("facts", []), extra]}, c.tokens_in, c.tokens_out)


def test_a_dated_eps_sentence_stores_no_price_increase(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M5 review R3 (R2-F1): the 10-Q's EPS sentence written with its period's date ("..., 2026, up 14% from a year
    ago") and quoted in part stores no price_increase fact."""

    def dated(job: run.DocJob) -> bytes:
        return fetch(job).replace(DATED_EPS_OLD.encode(), DATED_EPS_NEW.encode())

    cos = add_companies(conn)
    job = next(j for j in jobs(cos) if j.url.endswith("nmbs_10q_q1.htm"))
    assert DATED_EPS_NEW.encode() in dated(job)
    r = Router({"gemini": EpsPart()}, quotas(["gemini"], rpd=10_000), FakeClock())
    stats = run.TextStats("2026-10-28")
    assert run.process(conn, job, dated, r, tmp_path, stats) == "extracted"
    assert conn.execute("select count(*) from facts where fact_type = 'price_increase'").fetchone() == (0,)
    assert stats.rejected.get("V1-TYPE", 0) >= 1


class FlakyNse:
    def __init__(self) -> None:
        self.down = True
        self.calls: list[str] = []

    def get(self, url: str) -> bytes:
        from pipeline.net.nse import NseBlocked

        self.calls.append(url)
        if self.down:
            raise NseBlocked("403 three times")
        return (SYN / "nmbs_investor_day.pdf").read_bytes()


def test_an_announcement_pdf_is_fetched_again_after_the_weekend(conn: psycopg.Connection[Any],
                                                                 tmp_path: Path) -> None:  # fmt: skip
    """M5 review R3 (R2-F4, India): a Friday announcement triaged read_pdf on Saturday, whose PDF fetch fails, is
    read on Tuesday (daily.yml doesn't run on Sunday or Monday); a PDF triaged more than RETRY_DAYS ago isn't offered
    again. Aravalli is a research entry, so it is in the text run's scope."""
    conn.execute("insert into companies (market, name, nse_symbol, isin, fiscal_year_end, capex_desk) values "
                 "('in', 'Aravalli Cables Limited', 'ARVL', 'INE000A01010', '0331', true)")  # fmt: skip
    arvl = next(c for c in repo.companies(conn) if c.nse_symbol == "ARVL")
    assert arvl.id is not None
    research_entry(conn, arvl.id)
    pdf = "https://nsearchives.nseindia.com/corporate/ARVL_18092026.pdf"
    repo.insert_corp_events(conn, [CorpEvent(
        company_id=arvl.id, event_date=date(2026, 9, 18), filed_at=datetime(2026, 9, 18, 12, tzinfo=UTC),
        kind="announcement", detail={"category": "Award of Order", "text": "Order for HV cables."}, source_url=pdf,
    )])  # fmt: skip
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    nse = FlakyNse()
    run.run(conn, date(2026, 9, 19), router(), http, nse, tmp_path)  # type: ignore[arg-type]
    assert nse.calls == [pdf] and conn.execute("select count(*) from documents").fetchone() == (0,)
    nse.down = False
    run.run(conn, date(2026, 9, 22), router(), http, nse, tmp_path)  # type: ignore[arg-type]
    assert conn.execute("select kind, url from documents").fetchall() == [("press_release", pdf)]
    stats = run.TextStats("x")
    assert [j.url for j in run.triage_announcements(conn, router(), {arvl.id: arvl}, date(2026, 9, 22), stats)] == [pdf]
    conn.execute("update announcement_triage set created_at = '2026-09-01 00:00+00'")  # triaged > RETRY_DAYS ago
    assert run.triage_announcements(conn, router(), {arvl.id: arvl}, date(2026, 9, 22), run.TextStats("x")) == []


def test_stored_facts_are_checked_again_with_v1_kind(conn: psycopg.Connection[Any]) -> None:
    """docs/SPEC_ISSUES.md 61: facts stored before V1-KIND are checked on their stored quotes by the text run. A deal
    leaves the ledger (`failed`) with its link, which another verified fact of the same counterparty carries instead;
    a quote that doesn't show its type goes to review; the rest stay verified, and the next run changes nothing."""
    from tests.db.conftest import new_company

    cid = new_company(conn, name="Acme")
    doc = conn.execute("insert into documents (company_id, kind, url, published_at, sha256, raw_path) values "
                       "(%s, 'EX-99.1', 'https://e.org/k', '2026-10-28', 'x', 'x') returning id",
                       (cid,)).fetchone()  # fmt: skip
    entity = conn.execute("insert into entities (name, normalized, kind) values ('Nimbus Compute', 'nimbus compute', "
                          "'company') returning id").fetchone()  # fmt: skip
    assert doc is not None and entity is not None

    def fact(fact_type: str, key: str, quote: str, linked: bool = False) -> UUID:
        row = conn.execute(
            "insert into facts (company_id, document_id, fact_type, subject, subject_key, unit, as_of, quote, "
            "char_start, char_end, extraction_model, confidence, verification_status, counterparty, "
            "counterparty_entity_id) values (%s, %s, %s, 'x', %s, 'other', '2026-10-28', %s, 0, %s, 'm', 0.9, "
            "'verified', %s, %s) returning id",
            (cid, doc[0], fact_type, key, quote, len(quote), "Nimbus Compute" if linked else None,
             entity[0] if linked else None),
        ).fetchone()  # fmt: skip
        assert row is not None
        return UUID(str(row[0]))

    deal = fact("order_win", "order_win:nimbus", "We agreed to acquire Nimbus Compute for $340 million.", linked=True)
    order = fact("order_win", "order_win:nimbus_cooling", "Acme received an order from Nimbus Compute.", linked=True)
    conn.execute("insert into links (from_company_id, to_entity_id, relation, fact_id) values (%s, %s, 'customer', %s)",
                 (cid, entity[0], deal))  # fmt: skip
    orderless = fact("order_win", "order_win:sm6", "Standard Missile 6 with a total value of up to $24.4 billion.")
    cao = fact("governance_flag", "governance:auditor_change:added", "Our Chief Accounting Officer resigned.")
    weak = fact("governance_flag", "governance:material_weakness:added", "Our controls were not effective.")
    segments = fact("new_segment", "new_segment:x", "We have three businesses, each a single operating segment.")
    president = fact("customer_win", "customer_win:x", "The addition of Paul Taylor as President strengthens our team.")
    customers = fact("customer_win", "customer_win:y", "We welcomed new customers including KPMG LLP.")
    link = fact("supply_link", "link:x", "We agreed to acquire a stake in Nimbus Compute.")  # not a type S9 counts

    assert run.recheck_stored(conn) == {"order_win": 2, "governance_flag": 1, "new_segment": 1, "customer_win": 1}
    status = dict(conn.execute("select id, verification_status from facts where company_id = %s", (cid,)).fetchall())
    assert {k: status[k] for k in (deal, orderless, cao, segments, president)} == {
        deal: "failed", orderless: "needs_review", cao: "needs_review", segments: "needs_review",
        president: "needs_review"}  # fmt: skip
    assert {status[k] for k in (order, weak, link, customers)} == {"verified"}
    notes = conn.execute("select verification_notes from facts where id = %s", (deal,)).fetchone()
    assert notes is not None and notes[0]["kind"].startswith("an acquisition")
    assert conn.execute("select fact_id from links where from_company_id = %s", (cid,)).fetchall() == [(order,)]
    assert run.recheck_stored(conn) == {}
