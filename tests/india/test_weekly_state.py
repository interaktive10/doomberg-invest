"""The India weekly run's state and download budget, without a database (review F1, F2, F3 and F9 on M3; the
repository writers are recorded instead):
- results: the state keeps whole financial years, and a run writes only the years its new filings touched, so a
  stored Q4 row never loses its H2 cash flow (F1);
- shareholding gets its share of the downloads and a queue while the history backfill runs (F2);
- the results listing is read page by page up to the total count (F3);
- a run stops at its deadline, or when NSE keeps failing, and keeps the prices it committed first (F9)."""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from pipeline.db.models import Company
from pipeline.india import bhavcopy, weekly
from pipeline.india.results_xbrl import LISTING_API, ResultsListing, listing_path, load_ind_as_map, parse_results
from pipeline.india.securities import NSE_EQUITY_LIST_URL, parse_equity_list
from pipeline.india.shareholding import parse_shareholding
from pipeline.india.weekly import SHP_API, IndiaWeeklyStats, State
from pipeline.net.bse import BseClient
from pipeline.net.bse import bhavcopy_url as bse_url
from pipeline.net.http import HttpClient, RateLimiter
from pipeline.net.nse import NSE_API, NseClient
from pipeline.prices.benchmarks import index_close_url
from pipeline.settings import Settings

FIN = Path(__file__).resolve().parents[2] / "fixtures" / "in"
RESULTS = FIN / "results"
ARCHIVE = "https://nsearchives.nseindia.com/corporate/xbrl"
DAY = date(2026, 6, 5)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


@dataclass
class FakeConn:
    """Records the order of commits and writes (a transaction block that exits cleanly is a commit)."""

    log: list[str] = field(default_factory=list)

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        yield
        self.log.append("commit")


@dataclass
class Written:
    fundamentals: list[Any] = field(default_factory=list)
    ownership: list[Any] = field(default_factory=list)
    insider: list[Any] = field(default_factory=list)
    prices: list[Any] = field(default_factory=list)


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> Written:
    w = Written()
    monkeypatch.setattr(
        weekly.repo,
        "insert_fundamentals",
        lambda conn, rows, fill_only=False: w.fundamentals.extend((r, fill_only) for r in rows),
    )
    monkeypatch.setattr(weekly.repo, "upsert_ownership", lambda conn, rows: w.ownership.extend(rows))
    monkeypatch.setattr(weekly.repo, "insert_insider_events", lambda conn, rows: w.insider.extend(rows))
    return w  # fmt: skip


def clients(tmp_path: Path, clock: Clock | None = None) -> tuple[HttpClient, NseClient]:
    c = clock or Clock()
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path),
                      limiter=RateLimiter(clock=c, sleep=c.sleep))  # fmt: skip
    return http, NseClient(http, clock=c, sleep=c.sleep)


def company(symbol: str, name: str = "", capex: bool = False, isin: str | None = None) -> Company:
    return Company(id=uuid4(), market="in", name=name or symbol, nse_symbol=symbol, capex_desk=capex, isin=isin)


# ---------------------------------------------------------------- F1: H2 cash flow survives later filings


def shifted(raw: bytes, years: int) -> bytes:
    """The same filing `years` later (every date moved), filed as consolidated."""
    text = raw.decode()
    for y in range(2030, 2020, -1):
        text = re.sub(rf"(?<!\d){y}-(\d\d)-(\d\d)", rf"{y + years}-\1-\2", text)
    return text.replace(">Standalone<", ">Consolidated<").encode()


BASE = [
    ("KEI_FY2026Q2_consolidated.xml", date(2025, 9, 30), datetime(2025, 10, 15, 14, 29, 16, tzinfo=UTC)),
    ("KEI_FY2026Q3_consolidated.xml", date(2025, 12, 31), datetime(2026, 1, 21, 12, 55, 31, tzinfo=UTC)),
    ("KEI_FY2026Q4_consolidated.xml", date(2026, 3, 31), datetime(2026, 5, 4, 15, 50, 25, tzinfo=UTC)),
    ("KEI_FY2027Q1_standalone.xml", date(2026, 6, 30), datetime(2026, 8, 3, 15, 18, 35, tzinfo=UTC)),
]
TEN = [(f, pe, fa, 0) for f, pe, fa in BASE] + [
    (f, pe.replace(year=pe.year + k), fa + timedelta(days=365 * k), k) for k in (1, 2) for f, pe, fa in BASE
][:6]
Q4_KEY = (date(2026, 3, 31), datetime(2026, 5, 4, 15, 50, 25, tzinfo=UTC))


def run_ten_weeks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: Written) -> list[dict[str, Any]]:
    """One new KEI filing a week through the run's results steps (listing, download, rows)."""
    http, nse = clients(tmp_path)
    http.register_mock(f"{NSE_API}/{SHP_API}", b"[]")
    kei, state, ind_as = company("KEI", capex=True), State(), load_ind_as_map()
    table: dict[tuple[date, datetime], dict[str, Any]] = {}  # fundamentals_q with the fill-only upsert
    stores = []
    for n, (name, period_end, filed_at, years) in enumerate(TEN, 1):
        url = f"{ARCHIVE}/SIM_{n}_WEB.xml"
        raw = (RESULTS / name).read_bytes()
        http.register_mock(url, shifted(raw, years) if years else raw)
        listing = [ResultsListing(str(n), "KEI", period_end, "consolidated", False, filed_at, url)]
        monkeypatch.setattr(weekly, "list_results", lambda nse_, a, b, rows=listing: (rows, None))
        stats = IndiaWeeklyStats(filed_at.date().isoformat())
        start = len(written.fundamentals)
        weekly.ingest_filings(FakeConn(), nse, state, filed_at.date(), [kei], [], stats, ind_as, backfill=0)
        assert stats.errors == [] and stats.results_fetched == 1
        for row, fill_only in written.fundamentals[start:]:
            assert fill_only
            old = table.setdefault((row.period_end, row.filed_at), {})
            old.update({k: v for k, v in row.model_dump().items() if v is not None or k not in old})
        stores.append({"week": n, "years": sorted({s["fy_start"] for s in state.results_store["KEI"]})})
    return [table.get(Q4_KEY, {}), *stores]


def test_keeps_h2_cash_flow_through_ten_successive_filings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """Review F1: KEI's FY2026 Q4 row (H2 = FY - H1) keeps cfo and capex while later years arrive; no write of that
    version ever carries fewer values."""
    q4, *stores = run_ten_weeks(tmp_path, monkeypatch, written)
    assert q4["cfo"] == Decimal(4570550000) and q4["capex"] == Decimal(3726350000)
    versions = [r for r, _ in written.fundamentals if (r.period_end, r.filed_at) == Q4_KEY]
    assert versions and all(r.cfo == Decimal(4570550000) for r in versions)
    assert len(versions) == 1  # written in week 3 only: later weeks touch later financial years
    assert stores[-1]["years"] == ["2025-04-01", "2026-04-01", "2027-04-01"]  # three whole years kept


def test_an_evicted_year_is_never_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: Written) -> None:
    """With one year kept, FY2026's filings leave the store when FY2027 arrives; its rows are not rebuilt without
    their H1."""
    monkeypatch.setattr(weekly, "KEEP_YEARS", 1)
    q4, *stores = run_ten_weeks(tmp_path, monkeypatch, written)
    assert q4["cfo"] == Decimal(4570550000)
    assert all(r.cfo is not None for r, _ in written.fundamentals if (r.period_end, r.filed_at) == Q4_KEY)
    assert stores[-1]["years"] == ["2027-04-01"]


def test_keep_years_keeps_whole_years() -> None:
    filings = [{"fy_start": f"20{y}-04-01", "filed_at": f"20{y}-{m:02d}-01T00:00:00+00:00"}
               for y in (24, 25, 26, 27) for m in (8, 11)]  # fmt: skip
    kept = weekly.keep_years(filings, 2)
    assert [f["fy_start"] for f in kept] == ["2026-04-01"] * 2 + ["2027-04-01"] * 2


# ---------------------------------------------------------------- F2: the download budget


def test_allocate_gives_each_stream_its_share_and_moves_what_is_not_needed() -> None:
    assert weekly.allocate(600, {"results": 100, "shareholding": 2100, "backfill": 420}) == {
        "results": 100, "shareholding": 350, "backfill": 150}  # fmt: skip
    assert weekly.allocate(600, {"results": 900, "shareholding": 0, "backfill": 900}) == {
        "results": 450, "shareholding": 0, "backfill": 150}  # fmt: skip
    assert weekly.allocate(600, {"results": 10, "shareholding": 20, "backfill": 30}) == {
        "results": 10, "shareholding": 20, "backfill": 30}  # fmt: skip


def test_shareholding_budget_writes_every_pattern_while_the_backfill_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """Review F2, with the production defaults: 2,100 companies, 7-filing histories, 100 new results a week and
    2,100 listed patterns. Every pattern is written within 6 weeks, and every new result is read each week."""
    kei_q2 = parse_results((RESULTS / "KEI_FY2026Q2_consolidated.xml").read_bytes(), load_ind_as_map())
    kei_shp = parse_shareholding((FIN / "shareholding" / "SHP_KEI_2026-06-30.xml").read_bytes())
    monkeypatch.setattr(weekly, "parse_results", lambda raw, m: kei_q2)  # the budget is under test, not parsing
    monkeypatch.setattr(weekly, "parse_shareholding", lambda raw: kei_shp)
    http, nse = clients(tmp_path)
    universe = [company(f"S{i:04d}") for i in range(2100)]
    seq = iter(range(10_000_000, 99_999_999))

    def listing_row(symbol: str, quarter: str) -> dict[str, str]:
        url = f"{ARCHIVE}/INTEGRATED_FILING_INDAS_{next(seq)}_WEB.xml"
        http.register_mock(url, b"<xbrl/>")
        return {"seq_Id": url.split("_")[-2], "symbol": symbol, "qe_Date": quarter, "consolidated": "Consolidated",
                "type_Sub": "Original", "creation_Date": "15-Oct-2025 19:59:16", "xbrl": url}  # fmt: skip

    quarters = ("31-MAR-2025", "30-JUN-2025", "30-SEP-2025", "31-DEC-2025", "31-MAR-2026", "30-JUN-2026", "30-SEP-2026")
    for c in universe:
        rows = [listing_row(str(c.nse_symbol), q) for q in quarters]
        http.register_mock(f"{NSE_API}/{LISTING_API}&symbol={c.nse_symbol}",
                           json.dumps({"data": rows, "totalCount": 7}).encode())  # fmt: skip
    patterns = []
    for i, c in enumerate(universe):
        url = f"{ARCHIVE}/SHP_{i}_WEB.xml"
        http.register_mock(url, b"<xbrl/>")
        patterns.append({"symbol": c.nse_symbol, "date": "30-JUN-2026", "broadcastDate": "20-JUL-2026 15:18:41",
                         "xbrl": url, "recordId": f"r{i}"})  # fmt: skip
    http.register_mock(f"{NSE_API}/{SHP_API}", json.dumps(patterns).encode())
    state, order = State(), [str(c.nse_symbol) for c in universe]
    for week in range(1, 7):
        friday = date(2026, 10, 2) + timedelta(days=7 * (week - 1))
        new = [ResultsListing(str(next(seq)), str(universe[(week * 100 + k) % 2100].nse_symbol), date(2026, 9, 30),
                              "consolidated", False, datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=7 * week),
                              f"{ARCHIVE}/NEW_{week}_{k}_WEB.xml") for k in range(100)]  # fmt: skip
        for x in new:
            http.register_mock(x.xbrl_url, b"<xbrl/>")
        monkeypatch.setattr(weekly, "list_results", lambda nse_, a, b, rows=new: (rows, None))
        stats = IndiaWeeklyStats(friday.isoformat())
        weekly.ingest_filings(FakeConn(), nse, state, friday, universe, order, stats, {})
        assert stats.budget == {"results": 100, "shareholding": 350, "backfill": 150}, week
        assert stats.results_fetched == 250 and stats.shp_fetched == 350
    assert len({(o.company_id, o.quarter_end) for o in written.ownership}) == 2100
    assert state.shp_queue == []


def test_unread_patterns_wait_in_the_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: Written) -> None:
    """A pattern not downloaded this week stays queued, also after the listing moves to the next quarter."""
    monkeypatch.setattr(weekly, "list_results", lambda nse_, a, b: ([], None))
    http, nse = clients(tmp_path)
    kei = company("KEI")
    url = f"{ARCHIVE}/SHP_1696739_20072026031837_WEB.xml"
    listing = [{"symbol": "KEI", "date": "30-JUN-2026", "broadcastDate": "20-JUL-2026 15:18:41", "xbrl": url,
                "recordId": "212205"}]  # fmt: skip
    http.register_mock(f"{NSE_API}/{SHP_API}", json.dumps(listing).encode())
    http.register_mock(url, (FIN / "shareholding" / "SHP_KEI_2026-06-30.xml").read_bytes())
    state = State()
    stats = IndiaWeeklyStats("2026-07-24")
    weekly.ingest_filings(FakeConn(), nse, state, date(2026, 7, 24), [kei], [], stats, {}, max_fetch=0, backfill=0)
    assert [q["xbrl_url"] for q in state.shp_queue] == [url] and written.ownership == []
    http.register_mock(f"{NSE_API}/{SHP_API}", b"[]")  # next week: the listing shows another quarter
    stats = IndiaWeeklyStats("2026-07-31")
    weekly.ingest_filings(FakeConn(), nse, state, date(2026, 7, 31), [kei], [], stats, {}, backfill=0)
    assert stats.shp_fetched == 1 and [o.promoter_pct for o in written.ownership] == [Decimal("35.0000")]
    assert state.shp_queue == []


# ---------------------------------------------------------------- F3: every page of the listing


def listing_page(page: int, total: int, size: int = 50) -> bytes:
    first = (page - 1) * size
    rows = [{"seq_Id": str(n), "symbol": f"S{n}", "qe_Date": "30-JUN-2026", "consolidated": "Consolidated",
             "type_Sub": "Original", "creation_Date": "05-Aug-2026 10:00:00",
             "xbrl": f"{ARCHIVE}/INTEGRATED_FILING_INDAS_{n}_WEB.xml"}
            for n in range(first, first + max(0, min(size, total - first)))]  # fmt: skip
    return json.dumps({"data": rows, "totalCount": total, "page": page - 1, "size": size}).encode()


def test_a_2602_row_window_is_read_in_full(tmp_path: Path) -> None:
    http, nse = clients(tmp_path)
    a, b = date(2026, 8, 5), date(2026, 8, 14)
    for page in range(1, 54):
        http.register_mock(f"{NSE_API}/{listing_path(a, b, page)}", listing_page(page, 2602))
    rows, error = weekly.list_results(nse, a, b)
    assert error is None and len(rows) == 2602 and len({r.seq_id for r in rows}) == 2602


def test_a_short_listing_is_incomplete_and_the_cursor_stays(tmp_path: Path) -> None:
    http, nse = clients(tmp_path)
    friday = date(2026, 8, 14)
    state = State(results_listed_to="2026-08-07")
    a = date(2026, 8, 6)  # the day after the cursor, less the 2-day overlap
    http.register_mock(f"{NSE_API}/{listing_path(a, friday, 1)}", listing_page(1, 120))
    http.register_mock(f"{NSE_API}/{listing_path(a, friday, 2)}", listing_page(2, 120))
    http.register_mock(f"{NSE_API}/{listing_path(a, friday, 3)}", json.dumps({"data": [], "totalCount": 120}).encode())
    stats = IndiaWeeklyStats(friday.isoformat())
    ids = {f"S{i}": uuid4() for i in range(120)}
    assert not weekly.queue_results(nse, state, friday, ids, stats)
    assert state.results_listed_to == "2026-08-07" and len(state.results_queue) == 100  # what was read is queued
    assert stats.errors == ["results listing 2026-08-06..2026-08-14: page 3 is empty after 100 of 120 rows"]


def test_an_empty_window_is_complete(tmp_path: Path) -> None:
    http, nse = clients(tmp_path)
    friday = date(2026, 8, 14)
    http.register_mock(f"{NSE_API}/{listing_path(friday - timedelta(days=10), friday, 1)}",
                       json.dumps({"data": [], "totalCount": 0}).encode())  # fmt: skip
    state = State()
    assert weekly.queue_results(nse, state, friday, {}, IndiaWeeklyStats(friday.isoformat()))
    assert state.results_listed_to == "2026-08-14"


# ---------------------------------------------------------------- F9: deadline, failures, prices first


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch, written: Written) -> Written:
    """The universe and price writers as well: the whole run without a database."""
    securities = parse_equity_list((FIN / "securities" / "EQUITY_L.csv").read_bytes())
    listed = [company(s.symbol, s.name, isin=s.isin) for s in securities]

    def upsert_prices(conn: FakeConn, rows: list[Any]) -> None:
        conn.log.append("prices")
        written.prices.extend(rows)

    monkeypatch.setattr(weekly.repo, "companies", lambda conn, market=None, in_universe=None: listed)
    monkeypatch.setattr(weekly.repo, "upsert_in_companies", lambda conn, rows: None)
    monkeypatch.setattr(weekly.repo, "mark_missing_out_of_universe", lambda conn, market, keys, reason: 0)
    monkeypatch.setattr(weekly.repo, "set_india_universe", lambda conn, reasons: 0)
    monkeypatch.setattr(weekly.repo, "upsert_prices", upsert_prices)
    monkeypatch.setattr(weekly.repo, "upsert_benchmarks", lambda conn, rows: None)  # M4's NIFTY closes
    return written


def week_mocks(http: HttpClient) -> None:
    http.register_mock(NSE_EQUITY_LIST_URL, (FIN / "securities" / "EQUITY_L.csv").read_bytes())
    http.register_mock(f"{NSE_API}/reportASM", (FIN / "securities" / "asm.json").read_bytes())
    http.register_mock(f"{NSE_API}/reportGSM", (FIN / "securities" / "gsm.json").read_bytes())
    http.register_mock(bse_url(DAY), (FIN / "bhavcopy" / "BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV").read_bytes())
    http.register_mock(bhavcopy.nse_url(DAY),
                       (FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes())  # fmt: skip
    http.register_mock(index_close_url(DAY), (FIN / "indices" / "ind_close_all_05062026.csv").read_bytes())
    empty = json.dumps({"data": [], "totalCount": 0}).encode()
    http.register_mock(f"{NSE_API}/{listing_path(DAY - timedelta(days=10), DAY, 1)}", empty)
    http.register_mock(f"{NSE_API}/{SHP_API}", b"[]")


def queued_state(path: Path, n: int = 200) -> list[str]:
    urls = [f"{ARCHIVE}/INTEGRATED_FILING_INDAS_{9_000_000 + i}_WEB.xml" for i in range(n)]
    queue = [{"seq_id": str(9_000_000 + i), "symbol": "KEI", "period_end": "2026-03-31", "basis": "consolidated",
              "revision": False, "filed_at": f"2026-05-04T15:{i // 60:02d}:{i % 60:02d}+00:00", "xbrl_url": u,
              "backfill": False} for i, u in enumerate(urls)]  # fmt: skip
    State(results_queue=queue).save(path)
    return urls


def test_deadline_stops_downloads_and_keeps_the_prices(tmp_path: Path, fake_db: Written) -> None:
    """Review F9: on a fake clock, 200 queued XBRLs that take 30 s each; the run stops at its 10-minute budget,
    leaves the rest queued, and its prices were committed before the first XBRL request."""
    clock = Clock()
    http, nse = clients(tmp_path, clock)
    week_mocks(http)
    urls = queued_state(tmp_path / "state.json")
    raw = (RESULTS / "KEI_FY2026Q4_consolidated.xml").read_bytes()
    for u in urls:
        http.register_mock(u, raw)
    real_mock, order = http._mock, []

    def slow(url: str, host: str) -> bytes:
        if url in urls:
            order.append("xbrl")
            clock.t += 30.0
        return real_mock(url, host)

    http._mock = slow  # type: ignore[method-assign]
    nse.deadline = clock() + 600
    conn = FakeConn()
    stats = weekly.run_weekly(conn, nse, BseClient(http, sleep=clock.sleep), DAY, tmp_path / "state.json",  # type: ignore[arg-type]
                              imports=tmp_path / "imports", backfill=0)  # fmt: skip
    assert clock.t < 600 + 30 + 3  # stopped at the deadline (at most one request past it)
    assert 15 <= stats.results_fetched <= 20 and stats.deferred == 200 - stats.results_fetched
    assert len(State.load(tmp_path / "state.json").results_queue) == stats.deferred
    assert conn.log[:2] == ["prices", "commit"] and stats.prices == len(fake_db.prices) == 1956
    assert not stats.nse_stale  # out of time is not NSE's fault


def test_failures_of_any_kind_make_nse_stale_and_the_run_ends(tmp_path: Path, fake_db: Written) -> None:
    """Review F9: 200 queued XBRLs answering 503 no longer take 45 s each: 3 URLs that fail after their retries make
    NSE stale, the rest stay queued, and the week's prices are kept."""
    clock = Clock()
    http, nse = clients(tmp_path, clock)
    week_mocks(http)
    for u in queued_state(tmp_path / "state.json"):
        http.register_error(u, 503, times=4)
    conn = FakeConn()
    stats = weekly.run_weekly(conn, nse, BseClient(http, sleep=clock.sleep), DAY, tmp_path / "state.json",  # type: ignore[arg-type]
                              imports=tmp_path / "imports", backfill=0)  # fmt: skip
    assert stats.nse_stale and stats.results_fetched == 0 and stats.deferred == 200
    assert clock.t < 3 * 60  # three failed URLs (6 + 12 + 24 s of backoff each), not 200
    assert conn.log[:2] == ["prices", "commit"] and stats.prices == 1956
