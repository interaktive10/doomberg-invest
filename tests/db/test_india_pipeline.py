"""India pipeline against the database (BRIEF §4.3, §8 M3-02..M3-05): the weekly run on F-IN served by mocks
(universe, prices, results -> fundamentals_q, shareholding -> ownership_q), the stale/BSE/manual price chain with
source_health, the daily run (announcements, promoter trades), catch-up after a blocked week (review F3), and what
a stale NSE still gives from the pages' CSVs (review F4)."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import Company, FundamentalsRow, OwnershipRow
from pipeline.db.pit import as_of
from pipeline.india import announcements, bhavcopy, pit
from pipeline.india.daily import DailyState, mark_source, run_daily
from pipeline.india.results_xbrl import company_listing_path, listing_path, load_ind_as_map
from pipeline.india.securities import NSE_EQUITY_LIST_URL
from pipeline.india.weekly import SHP_API, IndiaWeeklyStats, State, ingest_filings, mark_sources, run_weekly
from pipeline.net.bse import BseClient
from pipeline.net.bse import bhavcopy_url as bse_url
from pipeline.net.http import HttpClient, RateLimiter
from pipeline.net.nse import NSE_API, NseClient
from pipeline.prices.benchmarks import index_close_url
from pipeline.settings import Settings

FIN = Path(__file__).resolve().parents[2] / "fixtures" / "in"
DAY = date(2026, 6, 5)
KEI_FILES = {  # the listing seq ids we hold XBRL files for
    "1549479": "KEI_FY2026Q2_consolidated.xml", "1607504": "KEI_FY2026Q3_consolidated.xml",
    "1607503": "KEI_FY2026Q3_standalone.xml", "1663459": "KEI_FY2026Q4_consolidated.xml",
    "1707263": "KEI_FY2027Q1_standalone.xml", "1707294": "KEI_FY2027Q1_standalone_revision.xml",
}  # fmt: skip


def clients(tmp_path: Path) -> tuple[HttpClient, NseClient, BseClient]:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path / "cache"),
                      limiter=RateLimiter(sleep=lambda s: None))  # fmt: skip
    return http, NseClient(http, sleep=lambda s: None), BseClient(http, sleep=lambda s: None)


def kei_listing() -> bytes:
    doc = json.loads((FIN / "results" / "index_KEI.json").read_text(encoding="utf-8"))
    rows = [r for r in doc["data"] if r["xbrl"].rsplit("_", 3)[-3] in KEI_FILES]
    return json.dumps({"data": rows, "totalCount": len(rows), "size": 50, "page": 0}).encode()


def weekly_mocks(http: HttpClient) -> None:
    http.register_mock(NSE_EQUITY_LIST_URL, (FIN / "securities" / "EQUITY_L.csv").read_bytes())
    http.register_mock(f"{NSE_API}/reportASM", (FIN / "securities" / "asm.json").read_bytes())
    http.register_mock(f"{NSE_API}/reportGSM", (FIN / "securities" / "gsm.json").read_bytes())
    http.register_mock(bse_url(DAY), (FIN / "bhavcopy" / "BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV").read_bytes())
    http.register_mock(
        bhavcopy.nse_url(DAY), (FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()
    )
    http.register_mock(index_close_url(DAY), (FIN / "indices" / "ind_close_all_05062026.csv").read_bytes())
    http.register_mock(f"{NSE_API}/{listing_path(DAY - timedelta(days=10), DAY, 1)}", kei_listing())
    empty = json.dumps({"data": [], "totalCount": 0}).encode()
    http.register_mock(f"{NSE_API}/{listing_path(DAY - timedelta(days=1), DAY, 1)}", empty)  # the next run's window
    capex = yaml.safe_load((FIN.parents[1] / "config" / "capex_seed.yaml").read_text(encoding="utf-8"))["india"]
    for e in (e for e in capex if e.get("nse")):  # filing histories for the backfill (capex desk first)
        empty = json.dumps({"data": [], "totalCount": 0}).encode()
        http.register_mock(f"{NSE_API}/{company_listing_path(e['nse'])}", kei_listing() if e["nse"] == "KEI" else empty)
    for r in json.loads(kei_listing())["data"]:
        http.register_mock(r["xbrl"], (FIN / "results" / KEI_FILES[r["xbrl"].rsplit("_", 3)[-3]]).read_bytes())
    http.register_mock(f"{NSE_API}/{SHP_API}", (FIN / "shareholding" / "index.json").read_bytes())
    for r in json.loads((FIN / "shareholding" / "index.json").read_text(encoding="utf-8")):
        http.register_mock(r["xbrl"], (FIN / "shareholding" / f"SHP_{r['symbol']}_2026-06-30.xml").read_bytes())


def company(conn: psycopg.Connection[Any], symbol: str) -> Company:
    return next(c for c in repo.companies(conn, market="in") if c.nse_symbol == symbol)


def test_india_weekly_run(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    http, nse, bse = clients(tmp_path)
    weekly_mocks(http)
    stats = run_weekly(conn, nse, bse, DAY, tmp_path / "state.json", imports=tmp_path / "imports", backfill=1)
    assert (stats.eq_companies, stats.surveillance, stats.errors, stats.nse_stale) == (2317, 188, [], False)
    assert stats.backfill_companies == 1  # one capex-desk company's history queued; nothing is fetched twice
    assert stats.listings_ok and stats.deferred == 0
    # universe: EQ list in, ASM/GSM out
    bhageria = company(conn, "BHAGERIA")
    assert not bhageria.in_universe and (bhageria.excluded_reason or "").startswith("surveillance: ")
    kei = company(conn, "KEI")
    assert kei.in_universe and kei.capex_desk and kei.id is not None
    # prices: NSE bhavcopy closes for every EQ company, ASM/GSM ones included (review F7: in_universe decides
    # scoring only)
    listed = [c for c in repo.companies(conn, market="in") if c.excluded_reason != repo.SNAPSHOT_OUT["in"]]
    symbols, by_isin = {c.nse_symbol for c in listed}, {c.isin: c.nse_symbol for c in listed}
    rows = bhavcopy.parse((FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()).rows
    priced = {r.symbol if r.symbol in symbols else by_isin.get(r.isin) for r in rows} - {None}
    assert (stats.price_source, stats.price_day) == ("NSE", "2026-06-05") and stats.prices == len(priced) == 1956
    assert len(repo.companies(conn, market="in", in_universe=True)) == 2317 - 188
    got = conn.execute("select close from prices_w where company_id = %s and week_end = %s", (bhageria.id, DAY))
    assert got.fetchone() == (next(r.close for r in rows if r.symbol == "BHAGERIA"),)  # on the ASM list, priced
    # benchmarks (M4): NIFTY 50 / NIFTY 500 for the bhavcopy's trading day, keyed by the week's Friday
    marks = conn.execute("select symbol, week_end, close from benchmarks_w order by symbol").fetchall()
    assert marks == [("NIFTY 50", DAY, Decimal("23366.7")), ("NIFTY 500", DAY, Decimal("22465.35"))]
    # a symbol renamed between the securities list and the bhavcopy keeps its ISIN: matched by ISIN
    aeroplane = company(conn, "AEROPLANE")
    renamed = conn.execute("select close from prices_w where company_id = %s and week_end = %s", (aeroplane.id, DAY))
    assert renamed.fetchone() == (next(r.close for r in rows if r.symbol == "AMIRCHAND"),)
    close = conn.execute("select close, source from prices_w where company_id = %s and week_end = %s", (kei.id, DAY))
    assert close.fetchone() == (Decimal("5335.50"), "nse_bhavcopy")
    # results -> fundamentals_q (M3-02): the expected rows, visible only once filed
    assert (stats.results_listed, stats.results_fetched) == (5, 5)  # standalone Q3 dropped: consolidated exists
    with (FIN / "results" / "expected_KEI.csv").open(encoding="utf-8") as fh:
        expected = list(csv.DictReader(fh))
    rows = {r.period_end: r for r in as_of(date(2026, 9, 1)).fundamentals(conn, [kei.id])}
    for e in expected:
        r = rows[date.fromisoformat(e["period_end"])]
        assert r.fiscal_label == e["fiscal_label"] and r.filed_at == datetime.fromisoformat(e["filed_at"])
        for col in ("revenue", "op_income", "net_income", "cfo", "capex", "total_assets", "total_debt", "equity",
                    "shares_outstanding"):  # fmt: skip
            assert getattr(r, col) == (Decimal(e[col]) if e[col] else None), (e["fiscal_label"], col)
        assert r.currency == "INR" and r.source == "nse_xbrl"
    assert date(2026, 3, 31) not in {r.period_end for r in as_of(date(2026, 5, 3)).fundamentals(conn, [kei.id])}
    assert rows[date(2026, 6, 30)].fiscal_label == "FY2027Q1"  # standalone (no consolidated filing in the sample)
    # shareholding -> ownership_q (M3-03), visible from the broadcast time
    own = {o.company_id: o for o in as_of(date(2026, 7, 21)).ownership(conn)}
    assert own[kei.id].promoter_pct == Decimal("35.0000") and own[kei.id].fii_pct == Decimal("27.3200")
    jp = company(conn, "JPPOWER")
    assert own[jp.id].promoter_pledged_pct == Decimal("72.9900")
    assert company(conn, "JSWSTEEL").id not in {o.company_id for o in as_of(date(2026, 7, 20)).ownership(conn)}
    # a second run re-reads nothing and changes nothing
    again = run_weekly(conn, nse, bse, DAY, tmp_path / "state.json", imports=tmp_path / "imports", backfill=1)
    assert (again.results_fetched, again.shp_fetched) == (0, 0)
    assert again.backfill_companies == 1  # the next capex-desk company's history; the first one isn't asked twice


def test_three_403s_then_bse_then_manual_import(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M3-05: NSE blocked 3 times -> source_health 'nse' stale -> BSE prices; BSE down too -> manual CSV import."""
    repo.upsert_in_companies(
        conn,
        [
            Company(market="in", name="KEI Industries", isin="INE878B01027", nse_symbol="KEI"),
            Company(market="in", name="ABB India", isin="INE117A01022", nse_symbol="ABB"),
        ],
    )
    http, nse, bse = clients(tmp_path)
    http.register_error(NSE_EQUITY_LIST_URL, 403, times=3)  # the run's first NSE request is blocked three times
    http.register_mock(bse_url(DAY), (FIN / "bhavcopy" / "BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV").read_bytes())
    stats = run_weekly(conn, nse, bse, DAY, None, imports=tmp_path / "imports")
    mark_sources(conn, stats, nse)
    assert stats.nse_stale and (stats.price_source, stats.prices) == ("BSE", 2)
    health = conn.execute("select stale, last_error from source_health where source = 'nse'").fetchone()
    assert health is not None and health[0] is True and "403" in health[1]
    kei = company(conn, "KEI")
    got = conn.execute("select close, source from prices_w where company_id = %s and week_end = %s", (kei.id, DAY))
    assert got.fetchone() == (Decimal("5336.10"), "bse_bhavcopy")  # BSE's close, matched by ISIN

    http2, nse2, bse2 = clients(tmp_path / "second")
    http2.register_error(NSE_EQUITY_LIST_URL, 403, times=3)
    http2.register_error(bse_url(DAY), 503, times=3)
    imports = tmp_path / "imports"
    imports.mkdir()
    zip_raw = (FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(zip_raw)) as z:
        (imports / "nse_bhavcopy_20260605.csv").write_bytes(z.read(z.namelist()[0]))
    stats = run_weekly(conn, nse2, bse2, DAY, None, imports=imports)
    assert (stats.price_source, stats.prices) == ("manual", 2)
    got = conn.execute("select close, source from prices_w where company_id = %s and week_end = %s", (kei.id, DAY))
    assert got.fetchone() == (Decimal("5335.50"), "manual_bhavcopy")


def test_india_daily_run(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    sample = {p.name for p in (FIN / "pit" / "disclosures").glob("*.xml")}
    index = json.loads((FIN / "pit" / "pit.json").read_text(encoding="utf-8"))
    rows = [r for r in index["data"] if r["xmlFileName"].rsplit("/", 1)[-1] in sample]
    symbols = sorted({r["symbol"] for r in rows} | {"NITCO"})
    repo.upsert_in_companies(conn, [Company(market="in", name=s, isin=f"INE{i:09d}", nse_symbol=s)
                                    for i, s in enumerate(symbols)])  # fmt: skip
    http, nse, _ = clients(tmp_path)
    day = date(2026, 9, 25)
    for d in (day - timedelta(days=2), day - timedelta(days=1)):  # a first run reads the last 3 days
        http.register_mock(f"{NSE_API}/{announcements.api_path(d, d)}", b"[]")
    http.register_mock(f"{NSE_API}/{announcements.api_path(day, day)}",
                       (FIN / "announcements" / "announcements.json").read_bytes())  # fmt: skip
    http.register_mock(f"{NSE_API}/{pit.API_PATH}", json.dumps({"data": rows}).encode())
    for r in rows:
        http.register_mock(
            r["xmlFileName"], (FIN / "pit" / "disclosures" / r["xmlFileName"].rsplit("/", 1)[-1]).read_bytes()
        )
    stats = run_daily(conn, nse, day, tmp_path / "daily.json", lookback_days=200)
    assert (stats.announcements, stats.pit_fetched, stats.errors) == (1, len(rows), [])  # NITCO is the one we hold
    assert stats.announcement_days == ["2026-09-23", "2026-09-24", "2026-09-25"] and stats.listings_ok
    events = as_of(day).insider_events(conn)
    kinds = sorted((e.kind, e.person) for e in events)
    assert ("promoter_buy", "NAVIN CHAND SUCHANTI") in kinds and sum(k == "promoter_buy" for k, _ in kinds) == 7
    assert sum(k == "promoter_sell" for k, _ in kinds) == 4 and all(e.currency == "INR" for e in events)
    # review F5: CSLFINANCE's two equal same-day purchases (two lines of one disclosure) are both stored
    csl = [e for e in events if e.person == "Rohit Gupta HUF"]
    assert (len(csl), sum(e.shares or 0 for e in csl), sum(e.value or 0 for e in csl)) == (2, 10000, 2400000)
    sinclair = next(e for e in events if e.person == "NAVIN CHAND SUCHANTI")
    assert sinclair.filed_at == datetime(2026, 9, 25, 7, 50, 13, tzinfo=UTC) and sinclair.value == Decimal(1417187)
    assert as_of(datetime(2026, 9, 25, 7, 50, 12, tzinfo=UTC)).insider_events(conn, [sinclair.company_id]) == []
    nitco = as_of(day).corp_events(conn)
    assert [(e.kind, e.detail["category"]) for e in nitco] == [("announcement", "Trading Window")]
    again = run_daily(conn, nse, day, tmp_path / "daily.json", lookback_days=200)  # disclosures already read
    assert again.pit_fetched == 0 and len(as_of(day).insider_events(conn)) == len(events)


def test_reseed_keeps_the_india_surveillance_exclusion(conn: psycopg.Connection[Any]) -> None:
    """M2 review F9, same rule for India: the quarterly re-seed doesn't let an ASM/GSM company back in; the weekly
    run's next surveillance check decides."""
    from pipeline.db import seed

    seed.seed(conn)
    assert repo.set_india_universe(conn, {"BHAGERIA": "surveillance: ASM long-term stage 1"}) == 1
    seed.seed(conn)
    b = company(conn, "BHAGERIA")
    assert (b.in_universe, b.excluded_reason) == (False, "surveillance: ASM long-term stage 1")


# ---------------------------------------------------------------- review F3: catch-up


def announcements_on(d: date) -> bytes:
    """The fixture's announcements, as if disseminated on day `d` (IST)."""
    rows = json.loads((FIN / "announcements" / "announcements.json").read_text(encoding="utf-8"))
    for r in rows:
        for k in ("an_dt", "exchdisstime"):
            if r.get(k):
                r[k] = f"{d:%d-%b-%Y}{r[k][11:]}"
    return json.dumps(rows).encode()


def nitco(conn: psycopg.Connection[Any]) -> None:
    repo.upsert_in_companies(
        conn, [Company(market="in", name="Nitco Limited", isin="INE858F01012", nse_symbol="NITCO")]
    )


def test_daily_catch_up_reads_the_weekend(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Review F3: the Tuesday run (for Monday) reads Saturday, Sunday and Monday, one request a day."""
    nitco(conn)
    DailyState(announcements_to="2026-09-18", pit_from="2026-09-18").save(tmp_path / "daily.json", date(2026, 9, 21))
    http, nse, _ = clients(tmp_path)
    days = [date(2026, 9, 19), date(2026, 9, 20), date(2026, 9, 21)]
    for d in days:
        http.register_mock(f"{NSE_API}/{announcements.api_path(d, d)}", announcements_on(d))
    http.register_mock(f"{NSE_API}/{pit.API_PATH}", json.dumps({"data": []}).encode())
    stats = run_daily(conn, nse, days[-1], tmp_path / "daily.json", imports=tmp_path / "imports")
    assert stats.announcement_days == [d.isoformat() for d in days] and stats.announcements == 3 and stats.listings_ok
    assert sorted(e.event_date for e in as_of(days[-1]).corp_events(conn)) == days
    assert DailyState.load(tmp_path / "daily.json").announcements_to == "2026-09-21"


def test_daily_catch_up_rereads_a_failed_day(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """A day whose request fails stops the run there; the next run starts from it."""
    nitco(conn)
    DailyState(announcements_to="2026-09-18").save(tmp_path / "daily.json", date(2026, 9, 21))
    http, nse, _ = clients(tmp_path)
    sat, sun, mon = date(2026, 9, 19), date(2026, 9, 20), date(2026, 9, 21)
    http.register_mock(f"{NSE_API}/{announcements.api_path(sat, sat)}", announcements_on(sat))
    http.register_error(f"{NSE_API}/{announcements.api_path(sun, sun)}", 503, times=4)
    http.register_mock(f"{NSE_API}/{pit.API_PATH}", json.dumps({"data": []}).encode())
    stats = run_daily(conn, nse, mon, tmp_path / "daily.json", imports=tmp_path / "imports")
    assert stats.announcement_days == ["2026-09-19"] and not stats.listings_ok
    assert DailyState.load(tmp_path / "daily.json").announcements_to == "2026-09-19"
    mark_source(conn, stats, nse)  # an error without a success: the SLA banner shows if this lasts
    health = conn.execute("select stale, last_error, last_success from source_health where source = 'nse'").fetchone()
    assert health is not None and health[0] is False and "announcements 2026-09-20" in health[1] and health[2] is None
    http2, nse2, _ = clients(tmp_path / "next")
    for d in (sun, mon):
        http2.register_mock(f"{NSE_API}/{announcements.api_path(d, d)}", announcements_on(d))
    http2.register_mock(f"{NSE_API}/{pit.API_PATH}", json.dumps({"data": []}).encode())
    again = run_daily(conn, nse2, mon, tmp_path / "daily.json", imports=tmp_path / "imports")
    assert again.announcement_days == ["2026-09-20", "2026-09-21"] and again.listings_ok
    assert sorted(e.event_date for e in as_of(mon).corp_events(conn)) == [sat, sun, mon]


def test_announcements_from_catches_up_past_the_14_day_limit(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """India restart (docs/SPEC_ISSUES.md 55): after a pause longer than 14 days, `--announcements-from` reads every day
    from the given one, whatever the cursor; without it the run starts 14 days back and says so."""
    nitco(conn)
    DailyState(announcements_to="2026-08-01").save(tmp_path / "daily.json", date(2026, 9, 21))
    http, nse, _ = clients(tmp_path)
    days = [date(2026, 9, 1) + timedelta(days=n) for n in range(21)]
    for d in days:
        http.register_mock(f"{NSE_API}/{announcements.api_path(d, d)}", announcements_on(d))
    http.register_mock(f"{NSE_API}/{pit.API_PATH}", json.dumps({"data": []}).encode())
    stats = run_daily(conn, nse, days[-1], tmp_path / "daily.json", imports=tmp_path / "imports",
                      announcements_from=days[0])  # fmt: skip
    assert stats.announcement_days == [d.isoformat() for d in days] and stats.listings_ok and not stats.errors
    capped = run_daily(conn, nse, days[-1], tmp_path / "daily0.json", imports=tmp_path / "imports")
    assert capped.announcement_days[0] == (days[-1] - timedelta(days=2)).isoformat()  # no cursor: the last 3 days
    DailyState(announcements_to="2026-08-01").save(tmp_path / "daily1.json", days[-1])
    limited = run_daily(conn, nse, days[-1], tmp_path / "daily1.json", imports=tmp_path / "imports")
    assert limited.announcement_days[0] == (days[-1] - timedelta(days=13)).isoformat()
    assert any("14-day limit" in e for e in limited.errors)


def kei_row(seq: str, quarter: str, created: str, name: str) -> dict[str, Any]:
    url = f"https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_{seq}_01012026000000_WEB.xml"
    basis = name.split("_")[2].split(".")[0].title()  # KEI_FY2026Q4_consolidated.xml -> Consolidated
    return {"seq_Id": seq, "symbol": "KEI", "qe_Date": quarter, "consolidated": basis, "type_Sub": "Original",
            "creation_Date": created, "xbrl": url}  # fmt: skip


def test_catch_up_after_a_stale_week_lists_the_missed_results(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Review F3 (and F4 for results): week 1 lists fine; week 2's listing is blocked (NSE stale), so its cursor
    stays; week 3 lists from week 1's cursor, so a filing broadcast on the Saturday after week 1 is read."""
    repo.upsert_in_companies(conn, [Company(market="in", name="KEI Industries", isin="INE878B01027", nse_symbol="KEI")])
    kei = company(conn, "KEI")
    f1, f2, f3 = date(2026, 5, 8), date(2026, 5, 15), date(2026, 5, 22)
    q4 = kei_row("1663459", "31-MAR-2026", "04-May-2026 21:20:25", "KEI_FY2026Q4_consolidated.xml")
    late = kei_row("1607503", "31-DEC-2025", "09-May-2026 11:00:00", "KEI_FY2026Q3_standalone.xml")
    state_path, ind_as = tmp_path / "state.json", load_ind_as_map()

    def week(friday: date, http: HttpClient, nse: NseClient) -> IndiaWeeklyStats:
        http.register_mock(f"{NSE_API}/{SHP_API}", b"[]")
        state, stats = State.load(state_path), IndiaWeeklyStats(friday.isoformat())
        ingest_filings(conn, nse, state, friday, [kei], [], stats, ind_as, backfill=0, imports=tmp_path / "imports")
        state.save(state_path)
        return stats

    http, nse, _ = clients(tmp_path / "w1")
    http.register_mock(f"{NSE_API}/{listing_path(f1 - timedelta(days=10), f1, 1)}",
                       json.dumps({"data": [q4], "totalCount": 1}).encode())  # fmt: skip
    http.register_mock(q4["xbrl"], (FIN / "results" / "KEI_FY2026Q4_consolidated.xml").read_bytes())
    s1 = week(f1, http, nse)
    assert (s1.results_fetched, s1.listings_ok, State.load(state_path).results_listed_to) == (1, True, "2026-05-08")
    http, nse, _ = clients(tmp_path / "w2")
    http.register_error(f"{NSE_API}/{listing_path(f1 - timedelta(days=1), f2, 1)}", 403, times=3)
    s2 = week(f2, http, nse)
    assert nse.stale and not s2.listings_ok and State.load(state_path).results_listed_to == "2026-05-08"
    mark_sources(conn, s2, nse)
    health = conn.execute("select stale from source_health where source = 'nse'").fetchone()
    assert health == (True,)
    http, nse, _ = clients(tmp_path / "w3")
    window = f"{NSE_API}/{listing_path(f1 - timedelta(days=1), f3, 1)}"  # from week 1's cursor, not f3 - 10 days
    http.register_mock(window, json.dumps({"data": [q4, late], "totalCount": 2}).encode())
    http.register_mock(late["xbrl"], (FIN / "results" / "KEI_FY2026Q3_standalone.xml").read_bytes())
    s3 = week(f3, http, nse)
    assert window in http.calls and s3.results_fetched == 1 and s3.listings_ok  # q4 was read in week 1
    assert State.load(state_path).results_listed_to == "2026-05-22"
    q3 = next(r for r in as_of(f3).fundamentals(conn, [kei.id]) if r.period_end == date(2025, 12, 31))
    assert q3.filed_at == datetime(2026, 5, 9, 5, 30, tzinfo=UTC)  # 11:00 IST on the Saturday after week 1


# ---------------------------------------------------------------- review F4: a stale NSE and the pages' CSVs


def test_stale_nse_announcements_come_from_the_manual_csv(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """NSE stale (3 x 403): the day's announcements come from the page's CSV in imports/ and the cursor moves."""
    csv_path = FIN / "announcements" / "announcements_2026-09-19.csv"
    symbols = sorted({r["SYMBOL"] for r in csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig")))})[:40]
    repo.upsert_in_companies(conn, [Company(market="in", name=s, isin=f"INE{i:09d}", nse_symbol=s)
                                    for i, s in enumerate(symbols)])  # fmt: skip
    imports = tmp_path / "imports"
    imports.mkdir()
    (imports / csv_path.name).write_bytes(csv_path.read_bytes())
    sat = date(2026, 9, 19)
    DailyState(announcements_to="2026-09-18").save(tmp_path / "daily.json", sat)
    http, nse, _ = clients(tmp_path)
    http.register_error(f"{NSE_API}/{announcements.api_path(sat, sat)}", 403, times=3)
    stats = run_daily(conn, nse, sat, tmp_path / "daily.json", imports=imports)
    assert nse.stale and stats.announcement_days == ["2026-09-19 (manual)"]
    rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"))))
    expected = sum(r["SYMBOL"] in symbols for r in rows)
    events = as_of(datetime(2026, 9, 20, tzinfo=UTC)).corp_events(conn)
    assert stats.announcements == len(events) == expected > 0
    assert all(
        e.kind == "announcement" and e.source_url.startswith("https://nsearchives.nseindia.com/") for e in events
    )
    assert DailyState.load(tmp_path / "daily.json").announcements_to == "2026-09-19"


def test_stale_nse_shareholding_from_the_manual_csv_then_the_full_row(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    """NSE stale: the shareholding page's CSV gives the promoter % (matched by name) and queues each pattern's XBRL;
    the next run reads the XBRL and its full row replaces the CSV's (same filing, same filed_at)."""
    repo.upsert_in_companies(conn, [
        Company(market="in", name="KEI Industries Limited", isin="INE878B01027", nse_symbol="KEI"),
        Company(market="in", name="JSW Steel Limited", isin="INE019A01038", nse_symbol="JSWSTEEL"),
        Company(market="in", name="Jaiprakash Power Ventures Limited", isin="INE351F01018", nse_symbol="JPPOWER"),
    ])  # fmt: skip
    companies = repo.companies(conn, market="in")
    imports = tmp_path / "imports"
    imports.mkdir()
    (imports / "shareholding.csv").write_bytes((FIN / "shareholding" / "shareholding_page.csv").read_bytes())
    state_path, friday = tmp_path / "state.json", date(2026, 7, 24)
    http, nse, _ = clients(tmp_path / "w1")
    http.register_error(f"{NSE_API}/{listing_path(friday - timedelta(days=10), friday, 1)}", 403, times=3)
    state, stats = State(), IndiaWeeklyStats(friday.isoformat())
    ingest_filings(conn, nse, state, friday, companies, [], stats, {}, imports=imports)
    state.save(state_path)
    assert nse.stale and stats.ownership_manual == 3 and len(state.shp_queue) == 3
    kei = company(conn, "KEI")
    own = {o.company_id: o for o in as_of(date(2026, 7, 21)).ownership(conn)}
    partial = own[kei.id]
    assert (partial.promoter_pct, partial.fii_pct, partial.source) == (Decimal("35.0000"), None, "manual_csv")
    http, nse, _ = clients(tmp_path / "w2")
    empty = json.dumps({"data": [], "totalCount": 0}).encode()
    http.register_mock(
        f"{NSE_API}/{listing_path(friday + timedelta(days=7) - timedelta(days=10), friday + timedelta(days=7), 1)}",
        empty,
    )
    http.register_mock(f"{NSE_API}/{SHP_API}", b"[]")  # the listing moved on: the queued XBRLs are read anyway
    for r in json.loads((FIN / "shareholding" / "index.json").read_text(encoding="utf-8")):
        http.register_mock(r["xbrl"], (FIN / "shareholding" / f"SHP_{r['symbol']}_2026-06-30.xml").read_bytes())
    state, stats = State.load(state_path), IndiaWeeklyStats("2026-07-31")
    ingest_filings(conn, nse, state, friday + timedelta(days=7), companies, [], stats, {}, imports=imports)
    assert stats.shp_fetched == 3 and state.shp_queue == [] and stats.ownership_manual == 0
    own = {o.company_id: o for o in as_of(date(2026, 7, 21)).ownership(conn)}
    full = own[kei.id]
    assert (full.promoter_pct, full.fii_pct, full.source) == (Decimal("35.0000"), Decimal("27.3200"), "nse_shp")


def test_manual_ownership_never_replaces_a_full_row(conn: psycopg.Connection[Any]) -> None:
    repo.upsert_in_companies(conn, [Company(market="in", name="KEI", isin="INE878B01027", nse_symbol="KEI")])
    cid = company(conn, "KEI").id
    assert cid is not None
    t = datetime(2026, 7, 20, 9, 48, 41, tzinfo=UTC)
    full = OwnershipRow(company_id=cid, quarter_end=date(2026, 6, 30), filed_at=t, promoter_pct=Decimal("35.0000"),
                        fii_pct=Decimal("27.3200"), source="nse_shp")  # fmt: skip
    manual = OwnershipRow(company_id=cid, quarter_end=date(2026, 6, 30), filed_at=t, promoter_pct=Decimal("35.0000"),
                          source="manual_csv")  # fmt: skip
    repo.upsert_ownership(conn, [full])
    repo.upsert_ownership(conn, [manual, manual.model_copy(update={"filed_at": t + timedelta(days=1)})])
    same = conn.execute("select fii_pct, source from ownership_q where company_id = %s and filed_at = %s", (cid, t))
    assert same.fetchall() == [(Decimal("27.3200"), "nse_shp")]  # the same filing: the full row stays
    seen = as_of(date(2026, 7, 24)).ownership(conn, [cid])  # a later manual version: as_of() still reads the full row
    assert [(o.fii_pct, o.source) for o in seen] == [(Decimal("27.3200"), "nse_shp")]


def test_india_upsert_keeps_h2_values(conn: psycopg.Connection[Any]) -> None:
    """Review F1: India's fill-only upsert never gives a stored version fewer values; the US upsert still replaces
    a version whole (quarterize rewrites a company's rows exactly)."""
    repo.upsert_in_companies(conn, [Company(market="in", name="KEI", isin="INE878B01027", nse_symbol="KEI")])
    cid = company(conn, "KEI").id
    assert cid is not None
    t = datetime(2026, 5, 4, 15, 50, 25, tzinfo=UTC)
    base = {"company_id": cid, "period_end": date(2026, 3, 31), "fiscal_label": "FY2026Q4", "filed_at": t,
            "currency": "INR", "source": "nse_xbrl"}  # fmt: skip
    first = FundamentalsRow.model_validate({**base, "cfo": Decimal(4570550000), "revenue": Decimal(1)})
    repo.insert_fundamentals(conn, [first], fill_only=True)
    repo.insert_fundamentals(conn, [FundamentalsRow.model_validate({**base, "revenue": Decimal(2)})], fill_only=True)
    [row] = [r for r in as_of(date(2026, 6, 1)).fundamentals(conn, [cid]) if r.period_end == date(2026, 3, 31)]
    assert (row.cfo, row.revenue) == (Decimal(4570550000), Decimal(2))  # the null kept cfo; a value still updates
    repo.insert_fundamentals(conn, [FundamentalsRow.model_validate({**base, "revenue": Decimal(3)})])
    [row] = [r for r in as_of(date(2026, 6, 1)).fundamentals(conn, [cid]) if r.period_end == date(2026, 3, 31)]
    assert (row.cfo, row.revenue) == (None, Decimal(3))
