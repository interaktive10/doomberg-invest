"""Computed reports against the database (migration 0019; pipeline/reports/winners.py): US month prices from the Lab's
stored asset, India's weekly closes from prices_w, shares through as_of, one row a week replaced when recomputed."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from pipeline.db import repo, state
from pipeline.db.models import Company, FundamentalsRow, PriceW
from pipeline.lab.prices import MonthBar, write_month_csv
from pipeline.reports import winners


def month_bars(closes: list[float]) -> list[MonthBar]:
    out, y, m = [], 2024, 12
    for c in closes:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        d = Decimal(str(c))
        out.append(MonthBar(nxt - timedelta(days=1), d, d, d))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fundamentals(cid: Any, currency: str, source: str) -> FundamentalsRow:
    return FundamentalsRow(company_id=cid, period_end=date(2024, 9, 30), fiscal_label="Q3",
                           filed_at=datetime(2024, 11, 1, tzinfo=UTC), diluted_shares=Decimal(10**9),
                           currency=currency, source=source)  # fmt: skip


def test_winners_report_reads_both_markets_and_upserts(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    repo.upsert_us_companies(conn, [Company(market="us", name=f"US {i}", cik=f"{800000 + i:010d}", ticker=f"U{i}")
                                    for i in range(7)])  # fmt: skip
    repo.upsert_in_companies(conn, [Company(market="in", name=f"IN {i}", nse_symbol=f"IN{i}", isin=f"INE00{i}A01011")
                                    for i in range(6)])  # fmt: skip
    us = {c.ticker: c.id for c in repo.companies(conn, market="us")}
    ind = {c.nse_symbol: c.id for c in repo.companies(conn, market="in")}
    repo.insert_fundamentals(conn, [fundamentals(cid, "USD", "sec_xbrl") for cid in us.values()]
                             + [fundamentals(cid, "INR", "nse_xbrl") for cid in ind.values()])  # fmt: skip
    asset = tmp_path / "us_month_prices.csv.gz"
    write_month_csv(asset, {f"U{i}": month_bars([10 + j * i / 12 for j in range(13)] + [10.0 + i] * 3)
                            for i in range(7)})  # fmt: skip
    state.put(conn, winners.LAB_ASSET, asset.read_bytes())
    weeks = [date(2024, 12, 27) + timedelta(weeks=k) for k in range(60)]
    repo.upsert_prices(conn, [PriceW(company_id=cid, week_end=d, close=Decimal(str(100 + i * k)), source="nse")
                              for i, cid in enumerate(ind.values()) for k, d in enumerate(weeks)])  # fmt: skip
    body = winners.build(conn, date(2026, 4, 10))
    by = {m["market"]: m for m in body["markets"]}
    assert [t["code"] for t in by["us"]["top"]] == ["U6", "U5", "U4", "U3", "U2"] and by["us"]["priced"] == 7
    assert by["us"]["this_year"]["through"] == "2026-03-31"
    assert len(by["in"]["top"]) == 5 and by["in"]["top"][0]["code"] == "IN5" and by["in"]["backtest"] is None
    week = date(2026, 4, 10)
    repo.upsert_report(conn, "winners", week, body)
    repo.upsert_report(conn, "winners", week, {**body, "as_of": "again"})  # recomputed: replaced, not added
    got = repo.latest_report(conn, "winners")
    assert got is not None and got[0] == week and got[1]["as_of"] == "again"
    assert conn.execute("select count(*) from reports").fetchone() == (1,)


class LibraryRouter:
    """P-08 through a fake provider: keeps the replacement theme, retires the chip one, adds a housing-parts theme."""

    def __init__(self) -> None:
        self.inputs: list[Any] = []

    def call(self, data: Any) -> Any:
        from pipeline.llm.router import Done

        self.inputs.append(data)
        return Done({"reviews": [{"slug": "vehicle-replacement", "decision": "keep", "note": "The wave is still due."},
                                 {"slug": "chip-cycle", "decision": "retire", "note": "No chip makers here."}],
                     "new": [{"title": "Home sales lift fittings", "category": "Housing & construction",
                              "driver": "HSN1F", "reading": "yoy", "lag_months": 6, "keywords": ["paint"],
                              "why": "Homes sold now get painted and fitted out within months.",
                              "wrong_if": "Paint sales stay flat."}],
                     "note": "Housing joins the library."}, "fake", "m")  # fmt: skip


def mocked_http(tmp_path: Path) -> Any:
    from pipeline.net import fred
    from pipeline.net.http import HttpClient
    from pipeline.settings import Settings

    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    for f in (Path(__file__).resolve().parents[2] / "fixtures" / "fred").glob("*.csv"):
        http.register_mock(fred.URL.format(id=f.stem), f.read_bytes())
    return http  # the other drivers aren't registered: they show as missing, the week goes on


def test_themes_library_numbers_weekly_rethink_monthly(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """The seed library gets its numbers (US vehicle sales from FRED, the tire makers' evidence and prices, a history
    check); the first run rethinks (keep, retire, a new housing theme matched by name in India's coarse sector); the
    next week carries the library with its notes and doesn't rethink again."""
    from pipeline.reports import themes

    us = [(f"T{i}", "Tires & Inner Tubes") for i in range(4)] + [
        (f"B{i}", "National Commercial Banks") for i in range(6)
    ]
    repo.upsert_us_companies(conn, [Company(market="us", name=f"Co {t}", cik=f"{600000 + i:010d}", ticker=t,
                                            industry=ind) for i, (t, ind) in enumerate(us)])  # fmt: skip
    repo.upsert_in_companies(conn, [Company(market="in", name=f"{n} Paints Ltd", nse_symbol=f"{n}PAINT",
                                            isin=f"INE00{i}P01011")
                                    for i, n in enumerate(["Asia", "Berg", "Kans"])])  # fmt: skip
    asset = tmp_path / "us_month_prices.csv.gz"
    write_month_csv(asset, {t: month_bars([20.0] * 23) for t, _ in us})  # Dec 2024 .. Oct 2026
    state.put(conn, winners.LAB_ASSET, asset.read_bytes())
    ind = {c.nse_symbol: c.id for c in repo.companies(conn, market="in")}
    weeks = [date(2025, 10, 3) + timedelta(weeks=k) for k in range(58)]
    repo.upsert_prices(conn, [PriceW(company_id=cid, week_end=d, close=Decimal(100), source="nse")
                              for cid in ind.values() for d in weeks])  # fmt: skip
    router = LibraryRouter()
    http = mocked_http(tmp_path)
    week = date(2026, 11, 6)
    body = themes.build(conn, router, http, week, date(2026, 11, 7))  # type: ignore[arg-type]
    lib = {t["slug"]: t for t in body["library"]}
    assert body["rethought"] and body["why"] == "the first rethink" and body["note"] == "Housing joins the library."
    assert "chip-cycle" not in lib and body["retired"][0]["slug"] == "chip-cycle"
    v = lib["vehicle-replacement"]
    assert v["companies"] == 4 and v["markets"] == ["us"] and v["chart"] and isinstance(v["z"], float)
    assert v["notes"][-1]["text"] == "The wave is still due." and v["status"] in (
        "building",
        "watching",
        "fading",
        "priced_in",
    )
    home = lib["home-sales-lift-fittings"]
    assert home["companies"] == 3 and home["markets"] == ["in"] and home["origin"] == "ai"
    assert any(m.startswith("NEWORDER") for m in body["missing_drivers"])  # not registered: missing, not fatal
    sent = json.loads(router.inputs[0].library_json)
    assert {x["slug"] for x in sent} >= {"vehicle-replacement", "chip-cycle"} and "company_id" not in router.inputs[
        0
    ].library_json
    repo.upsert_report(conn, "themes", week, body)
    again = themes.build(conn, router, http, week, date(2026, 11, 8))  # type: ignore[arg-type]
    assert not again["rethought"] and len(router.inputs) == 1  # a re-run of the week keeps its library and rethink
    assert {t["slug"] for t in again["library"]} == set(lib) and again["last_rethink"] == "2026-11-06"
    later = themes.build(conn, router, http, week + timedelta(days=7), date(2026, 11, 14))  # type: ignore[arg-type]
    assert not later["rethought"] and len(router.inputs) == 1 and later["last_rethink"] == "2026-11-06"
    assert {t["slug"] for t in later["library"]} == set(lib) and later["next_rethink"] == "2026-12-04"


def test_india_sectors_come_from_nse_index_lists(conn: psycopg.Connection[Any]) -> None:
    from pipeline.india import sectors

    repo.upsert_in_companies(conn, [Company(market="in", name="ABB India Ltd.", nse_symbol="ABB", isin="INE117A01022"),
                                    Company(market="in", name="Other Ltd", nse_symbol="OTHR",
                                            isin="INE999Z01011")])  # fmt: skip
    lists = sectors.parse(
        "Company Name,Industry,Symbol,Series,ISIN Code\nABB India Ltd.,Capital Goods,ABB,EQ,INE117A01022\n"
    )
    assert sectors.sectors(conn, lists) == 1 and sectors.sectors(conn, lists) == 0  # unchanged the second time
    got = {c.nse_symbol: c.sector for c in repo.companies(conn, market="in")}
    assert got == {"ABB": "Capital Goods", "OTHR": None}
