"""The India history loader (pipeline/india/history.py, docs/SPEC_ISSUES.md 55 part 2) against the database, on F-IN
served by mocks: a holiday week and a stored week of prices, then KEI's results history from NSE's legacy listing
(FY2023 Q3, FY2024 Q2 and Q4, FY2025 Q2) and its integrated filings (FY2025 Q4 on) -> fundamentals_q with the H2 cash
flows,
its shareholding from March 2026, the state kept in the database, a run cut short that resumes without reading a
file twice, and a company that keeps failing left to the weekly run."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import psycopg
import pytest

from pipeline.db import repo
from pipeline.db import state as db_state
from pipeline.db.models import Company, PriceW
from pipeline.db.pit import as_of
from pipeline.india import bhavcopy, history
from pipeline.india.results_xbrl import company_listing_path, legacy_listing_path
from pipeline.india.weekly import SHP_API, State
from pipeline.net.bse import BseClient
from pipeline.net.bse import bhavcopy_url as bse_url
from pipeline.net.http import HttpClient, RateLimiter
from pipeline.net.nse import NSE_API, NseClient
from pipeline.prices.benchmarks import index_close_url
from pipeline.settings import Settings

FIN = Path(__file__).resolve().parents[2] / "fixtures" / "in"
DAY = date(2026, 6, 5)  # the bhavcopy F-IN holds
TODAY = date(2026, 6, 8)  # a Monday: the two weeks before it are 2026-06-05 and 2026-05-29 (a holiday week here)
INTEGRATED = {  # the integrated-filing XBRLs F-IN holds for KEI, by the file number in their names
    "1432738": "KEI_FY2025Q4_consolidated.xml", "1549479": "KEI_FY2026Q2_consolidated.xml",
    "1607504": "KEI_FY2026Q3_consolidated.xml", "1607503": "KEI_FY2026Q3_standalone.xml",
    "1663459": "KEI_FY2026Q4_consolidated.xml", "1707263": "KEI_FY2027Q1_standalone.xml",
    "1707294": "KEI_FY2027Q1_standalone_revision.xml",
}  # fmt: skip
LEGACY = {  # KEI's legacy quarters F-IN holds (consolidated; the listing's standalone twins are never read)
    "31-Dec-2022": "legacy_KEI_FY2023Q3_consolidated.xml", "30-Sep-2023": "legacy_KEI_FY2024Q2_consolidated.xml",
    "31-Mar-2024": "legacy_KEI_FY2024Q4_consolidated.xml", "30-Sep-2024": "legacy_KEI_FY2025Q2_consolidated.xml",
}  # fmt: skip
EMPTY = json.dumps({"data": [], "totalCount": 0}).encode()


def clients(tmp_path: Path) -> tuple[HttpClient, NseClient, BseClient]:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path / "cache"),
                      limiter=RateLimiter(sleep=lambda s: None))  # fmt: skip
    return http, NseClient(http, sleep=lambda s: None), BseClient(http, sleep=lambda s: None)


def number(url: str) -> str:
    return url.rsplit("_", 3)[-3]


def mocks(http: HttpClient) -> None:
    """Prices for DAY; every weekday of the week before is a holiday (BSE answers its home page); KEI's three listings
    (only rows whose files we hold, plus rows the loader must never ask for: legacy quarters before HISTORY_FROM, the
    legacy standalone twins, shareholding before SHP_FROM) and files; NOTRADED has no filings at all."""
    http.register_mock(bse_url(DAY), (FIN / "bhavcopy" / "BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV").read_bytes())
    http.register_mock(
        bhavcopy.nse_url(DAY), (FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()
    )
    http.register_mock(index_close_url(DAY), (FIN / "indices" / "ind_close_all_05062026.csv").read_bytes())
    for d in bhavcopy.week_days_back(DAY - timedelta(weeks=1)):
        http.register_mock(bse_url(d), b"<!DOCTYPE html><html><head><title>BSE</title></head></html>")
    doc = json.loads((FIN / "results" / "index_KEI.json").read_text(encoding="utf-8"))
    rows = [r for r in doc["data"] if number(r["xbrl"]) in INTEGRATED]
    http.register_mock(f"{NSE_API}/{company_listing_path('KEI')}",
                       json.dumps({"data": rows, "totalCount": len(rows)}).encode())  # fmt: skip
    for r in rows:
        http.register_mock(r["xbrl"], (FIN / "results" / INTEGRATED[number(r["xbrl"])]).read_bytes())
    old = json.loads((FIN / "results" / "legacy_index_KEI.json").read_text(encoding="utf-8"))
    keep = [r for r in old if r["toDate"] in LEGACY or r["toDate"] == "31-Mar-2022" or not r["exchdisstime"]]
    assert any(r["toDate"] == "31-Mar-2022" for r in keep)  # before HISTORY_FROM: never asked for
    http.register_mock(f"{NSE_API}/{legacy_listing_path('KEI')}", json.dumps(keep).encode())
    for r in old:
        if r["toDate"] in LEGACY and r["consolidated"] == "Consolidated":
            http.register_mock(r["xbrl"], (FIN / "results" / LEGACY[r["toDate"]]).read_bytes())
    shp = json.loads((FIN / "shareholding" / "index_KEI.json").read_text(encoding="utf-8"))
    listed = [r for r in shp if r["date"] in ("30-JUN-2026", "31-DEC-2025")]  # December: before SHP_FROM
    http.register_mock(f"{NSE_API}/{SHP_API}&symbol=KEI", json.dumps(listed).encode())
    http.register_mock(next(r["xbrl"] for r in shp if r["date"] == "30-JUN-2026"),
                       (FIN / "shareholding" / "SHP_KEI_2026-06-30.xml").read_bytes())  # fmt: skip
    http.register_mock(f"{NSE_API}/{company_listing_path('NOTRADED')}", EMPTY)
    http.register_mock(f"{NSE_API}/{legacy_listing_path('NOTRADED')}", b"[]")
    http.register_mock(f"{NSE_API}/{SHP_API}&symbol=NOTRADED", b"[]")


def companies(conn: psycopg.Connection[Any]) -> dict[str, Company]:
    repo.upsert_in_companies(conn, [
        Company(market="in", name="KEI Industries", isin="INE878B01027", nse_symbol="KEI"),
        Company(market="in", name="Not Traded", isin="INE000X01019", nse_symbol="NOTRADED"),
    ])  # fmt: skip
    return {c.nse_symbol or "": c for c in repo.companies(conn, market="in")}


def run(conn: psycopg.Connection[Any], tmp_path: Path, http_dir: str, **kw: Any) -> tuple[history.HistoryStats, State]:
    http, nse, bse = clients(tmp_path / http_dir)
    mocks(http)
    for url, status, times in kw.pop("errors", ()):
        http.register_error(url, status, times=times)
    path = tmp_path / "state.json"
    weeks = kw.pop("price_weeks", 2)
    stats = history.run_history(conn, nse, bse, TODAY, path, history.saver(conn, path, commit=lambda: None),
                                price_weeks=weeks, imports=tmp_path / "imports", commit=lambda: None, **kw)  # fmt: skip
    return stats, State.load(path)


def test_history_loads_prices_then_each_company(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    c = companies(conn)
    kei = c["KEI"]
    assert kei.id is not None
    stats, state = run(conn, tmp_path, "first")
    # prices: the stored-to-be week, and a week with no trading day at all (recorded, so never asked again)
    assert (stats.price_weeks_stored, stats.price_weeks_left) == (1, 0)
    assert any(e.startswith("prices 2026-05-29: no bhavcopy for the week") for e in stats.errors)
    assert state.history_prices == {"2026-06-05", "2026-05-29"}
    got = conn.execute("select close, source from prices_w where company_id = %s and week_end = %s", (kei.id, DAY))
    assert got.fetchone() == (D("5335.50"), "nse_bhavcopy")
    # KEI first (the most traded), then NOTRADED (no prices, no filings): both done, so the history is complete
    assert (stats.companies_done, stats.companies_left, stats.complete) == (2, 0, True)
    assert state.history_done == {"KEI", "NOTRADED"} and {"KEI", "NOTRADED"} <= state.backfilled
    # 4 legacy filings + 6 integrated (FY2026 Q3's standalone is dropped: its consolidated filing exists)
    assert (stats.results_fetched, stats.shp_fetched, stats.ownership_rows) == (10, 1, 1)
    rows = {r.period_end: r for r in as_of(date(2026, 9, 1)).fundamentals(conn, [kei.id])}
    q3 = rows[date(2022, 12, 31)]  # a file whose contexts were never defined, read from its own dates
    assert (q3.fiscal_label, q3.revenue, q3.cfo) == ("FY2023Q3", D("17843150000.00"), None)
    q2 = rows[date(2023, 9, 30)]
    assert (q2.fiscal_label, q2.filed_at) == ("FY2024Q2", datetime(2023, 11, 1, 11, 20, 2, tzinfo=UTC))
    assert (q2.revenue, q2.cfo, q2.capex) == (D("19465750000.00"), D("1149610000.00"), D("2205970000.00"))
    fy24 = rows[date(2024, 3, 31)]  # H2 = the legacy year - the legacy half year
    assert (fy24.fiscal_label, fy24.cfo, fy24.capex) == ("FY2024Q4", D("4955420000.00"), D("347870000.00"))
    assert rows[date(2024, 9, 30)].cfo == D("-3075560000.00")
    fy25 = rows[date(2025, 3, 31)]  # H2 = the integrated year - the legacy half year
    assert (fy25.fiscal_label, fy25.cfo, fy25.capex) == ("FY2025Q4", D("2753430000.00"), D("3802460000.00"))
    assert rows[date(2026, 3, 31)].fiscal_label == "FY2026Q4" and rows[date(2026, 6, 30)].source == "nse_xbrl"
    assert date(2024, 3, 31) not in {r.period_end for r in as_of(date(2024, 5, 2)).fundamentals(conn, [kei.id])}
    assert date(2024, 3, 31) in {r.period_end for r in as_of(date(2024, 5, 4)).fundamentals(conn, [kei.id])}
    own = {o.company_id: o for o in as_of(date(2026, 7, 21)).ownership(conn)}
    assert own[kei.id].promoter_pct == D("35.0000") and own[kei.id].quarter_end == date(2026, 6, 30)
    # once done, KEI's store is back to the weekly run's 3 financial years; the state is in the database
    assert {s["fy_start"] for s in state.results_store["KEI"]} == {"2024-04-01", "2025-04-01", "2026-04-01"}
    stored = db_state.get(conn, history.STATE_NAME)
    assert stored is not None and stored.body == (tmp_path / "state.json").read_bytes()
    # a second run reads nothing again
    again, _ = run(conn, tmp_path, "second")
    assert (again.price_weeks_stored, again.results_fetched, again.shp_fetched, again.companies_done) == (0, 0, 0, 0)
    assert again.complete


def test_a_run_cut_short_resumes_without_reading_a_file_twice(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """NSE blocks KEI's FY2025 Q4 filing three times after answering the run's other requests: NSE is stale, the run
    stops after the four legacy filings, KEI counts a try (it goes to the back of the queue) and NOTRADED isn't
    tried. The next run reads NOTRADED, then the six files KEI has left; FY2025's H2 cash flow takes the half year the
    first run stored."""
    c = companies(conn)
    kei = c["KEI"]
    assert kei.id is not None
    doc = json.loads((FIN / "results" / "index_KEI.json").read_text(encoding="utf-8"))
    fy25q4 = next(r["xbrl"] for r in doc["data"] if number(r["xbrl"]) == "1432738")
    first, state = run(conn, tmp_path, "first", errors=[(fy25q4, 403, 3)])
    assert first.nse_stale and (first.results_fetched, first.companies_done, first.complete) == (4, 0, False)
    assert first.companies_left == 2 and state.history_tries == {"KEI": 1} and state.history_done == set()
    fy24 = {r.period_end: r for r in as_of(date(2026, 9, 1)).fundamentals(conn, [kei.id])}[date(2024, 3, 31)]
    assert fy24.cfo == D("4955420000.00")  # the years read before the block are written
    second, state = run(conn, tmp_path, "second")
    assert (second.results_fetched, second.companies_done, second.complete) == (6, 2, True)
    assert state.history_tries == {}
    rows = {r.period_end: r for r in as_of(date(2026, 9, 1)).fundamentals(conn, [kei.id])}
    assert rows[date(2025, 3, 31)].cfo == D("2753430000.00")


def test_a_company_that_keeps_failing_is_left_to_the_weekly_run(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """NOTRADED's legacy listing answers 404 three runs running (NSE itself fine): after MAX_TRIES it is left to the
    weekly run's own history queue (not in `backfilled`), and the history is complete without it."""
    companies(conn)
    url = f"{NSE_API}/{legacy_listing_path('NOTRADED')}"
    for n in range(1, history.MAX_TRIES + 1):
        stats, state = run(conn, tmp_path, f"run{n}", errors=[(url, 404, 1)])
        assert state.history_tries == {"NOTRADED": n} and not stats.nse_stale
    assert (stats.companies_left, stats.companies_given_up, stats.complete) == (0, 1, True)
    assert "NOTRADED" not in state.backfilled and "NOTRADED" not in state.history_done
    assert any("left to the weekly run" in e for e in stats.errors)


def test_nse_refusing_everything_is_not_a_companys_failure(
    conn: psycopg.Connection[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NSE refuses the run's first request (KEI's listing) three times: stale, with nothing answered this run, so no
    company counts a try; nor does a company the clock stopped."""
    companies(conn)
    url = f"{NSE_API}/{company_listing_path('KEI')}"
    stats, state = run(conn, tmp_path, "blocked", price_weeks=0, errors=[(url, 403, 3)])
    assert stats.nse_stale and stats.companies_done == 0 and state.history_tries == {}

    def out_of_time(conn: Any, nse: NseClient, *args: Any) -> bool:
        nse.deadline = nse.clock() - 1  # the time budget ran out while the company was read
        return False

    monkeypatch.setattr(history, "load_company", out_of_time)
    late, state = run(conn, tmp_path, "late", price_weeks=0)
    assert (late.companies_done, late.companies_left) == (0, 2) and state.history_tries == {}


def test_order_research_first_then_the_most_traded() -> None:
    def co(symbol: str, in_universe: bool = True) -> Company:
        return Company(id=uuid.uuid4(), market="in", name=symbol, nse_symbol=symbol, isin=f"IN{symbol}",
                       in_universe=in_universe)  # fmt: skip

    a, b, c, d, gsm = co("AAA"), co("BBB"), co("CCC"), co("DDD", in_universe=False), co("ASM", in_universe=False)
    assert a.id and b.id and c.id and d.id
    turnover = {a.id: D(5), b.id: D(9), c.id: D(9)}
    got = history.ordered([a, b, c, d, gsm], {d.id}, turnover)
    assert [x.nse_symbol for x in got] == ["DDD", "BBB", "CCC", "AAA"]  # research (outside the universe), then value
    assert [x.nse_symbol for x in history.ordered([a, b, c], set(), turnover, {"AAA"})] == ["AAA"]
    again = history.ordered([a, b, c, d], {d.id}, turnover, tries={"BBB": 1, "DDD": 2})
    assert [x.nse_symbol for x in again] == ["DDD", "CCC", "AAA", "BBB"]  # a failed company goes to the back


def test_the_workflow_reads_complete_and_stale(tmp_path: Path) -> None:
    out = tmp_path / "github_output"
    history.github_output(str(out), history.HistoryStats(complete=False, nse_stale=True))
    history.github_output(None, history.HistoryStats())  # outside Actions: nothing
    assert out.read_text(encoding="utf-8") == "complete=false\nstale=true\n"


def test_the_weeks_are_the_fridays_before_today() -> None:
    assert history.fridays(TODAY, 2) == [DAY, date(2026, 5, 29)]
    assert history.fridays(DAY, 1) == [date(2026, 5, 29)]  # a Friday's own week is the weekly run's


def test_turnover_is_the_mean_traded_value_of_the_last_weeks(conn: psycopg.Connection[Any]) -> None:
    c = companies(conn)
    kei, nt = c["KEI"].id, c["NOTRADED"].id
    assert kei is not None and nt is not None
    weeks = [DAY - timedelta(weeks=k) for k in range(6)]
    repo.upsert_prices(conn, [PriceW(company_id=kei, week_end=w, close=D(10), adj_close=D(10), volume=D(100 * (k + 1)),
                                     source="nse_bhavcopy") for k, w in enumerate(weeks)])  # fmt: skip
    repo.upsert_prices(conn, [PriceW(company_id=nt, week_end=DAY, close=D(1), adj_close=D(1), volume=None,
                                     source="nse_bhavcopy")])  # fmt: skip
    got = repo.latest_turnover(conn, "in")
    assert got[kei] == D(2500) and got[nt] == D(0)  # (1000 + 2000 + 3000 + 4000) / 4 over the last 4 weeks
    assert repo.price_week_counts(conn, "in", weeks[-1], DAY) == {w: (2 if w == DAY else 1) for w in weeks}
