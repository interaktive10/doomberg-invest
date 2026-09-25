"""India pipeline against the database (BRIEF §4.3, §8 M3-02..M3-05): the weekly run on F-IN served by mocks
(universe, prices, results -> fundamentals_q, shareholding -> ownership_q), the stale/BSE/manual price chain with
source_health, and the daily run (announcements, promoter trades)."""

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
from pipeline.db.models import Company
from pipeline.db.pit import as_of
from pipeline.india import bhavcopy
from pipeline.india.daily import run_daily
from pipeline.india.results_xbrl import LISTING_API, listing_path
from pipeline.india.securities import NSE_EQUITY_LIST_URL
from pipeline.india.weekly import SHP_API, mark_sources, run_weekly
from pipeline.net.bse import BseClient
from pipeline.net.bse import bhavcopy_url as bse_url
from pipeline.net.http import HttpClient, RateLimiter
from pipeline.net.nse import NSE_API, NseClient
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
    http.register_mock(f"{NSE_API}/{listing_path(DAY - timedelta(days=10), DAY, 1)}", kei_listing())
    capex = yaml.safe_load((FIN.parents[1] / "config" / "capex_seed.yaml").read_text(encoding="utf-8"))["india"]
    for e in (e for e in capex if e.get("nse")):  # filing histories for the backfill (capex desk first)
        empty = json.dumps({"data": [], "totalCount": 0}).encode()
        http.register_mock(f"{NSE_API}/{LISTING_API}&symbol={e['nse']}", kei_listing() if e["nse"] == "KEI" else empty)
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
    # universe: EQ list in, ASM/GSM out
    bhageria = company(conn, "BHAGERIA")
    assert not bhageria.in_universe and (bhageria.excluded_reason or "").startswith("surveillance: ")
    kei = company(conn, "KEI")
    assert kei.in_universe and kei.capex_desk and kei.id is not None
    # prices: NSE bhavcopy closes for universe companies
    universe = {c.nse_symbol for c in repo.companies(conn, market="in", in_universe=True)}
    traded = {
        r.symbol
        for r in bhavcopy.parse((FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()).rows
    }
    assert (stats.price_source, stats.price_day) == ("NSE", "2026-06-05") and stats.prices == len(universe & traded)
    assert len(universe) == 2317 - 188 and stats.prices > 2000
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
    from pipeline.india import announcements, pit

    http.register_mock(f"{NSE_API}/{announcements.api_path(day, day)}",
                       (FIN / "announcements" / "announcements.json").read_bytes())  # fmt: skip
    http.register_mock(f"{NSE_API}/{pit.API_PATH}", json.dumps({"data": rows}).encode())
    for r in rows:
        http.register_mock(
            r["xmlFileName"], (FIN / "pit" / "disclosures" / r["xmlFileName"].rsplit("/", 1)[-1]).read_bytes()
        )
    stats = run_daily(conn, nse, day, tmp_path / "daily.json", lookback_days=200)
    assert (stats.announcements, stats.pit_fetched, stats.errors) == (1, len(rows), [])  # NITCO is the one we hold
    events = as_of(day).insider_events(conn)
    kinds = sorted((e.kind, e.person) for e in events)
    assert ("promoter_buy", "NAVIN CHAND SUCHANTI") in kinds and sum(k == "promoter_buy" for k, _ in kinds) == 6
    assert sum(k == "promoter_sell" for k, _ in kinds) == 4 and all(e.currency == "INR" for e in events)
    sinclair = next(e for e in events if e.person == "NAVIN CHAND SUCHANTI")
    assert sinclair.filed_at == datetime(2026, 9, 25, 7, 50, 13, tzinfo=UTC) and sinclair.value == Decimal(1417187)
    assert as_of(datetime(2026, 9, 25, 7, 50, 12, tzinfo=UTC)).insider_events(conn, [sinclair.company_id]) == []
    nitco = as_of(day).corp_events(conn)
    assert [(e.kind, e.detail["category"]) for e in nitco] == [("announcement", "Trading Window")]
    again = run_daily(conn, nse, day, tmp_path / "daily.json", lookback_days=200)  # disclosures already read
    assert again.pit_fetched == 0 and len(as_of(day).insider_events(conn)) == len(events)
