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


class ThemeRouter:
    """P-08 through a fake provider: names Grid with its first two pieces of evidence."""

    def __init__(self) -> None:
        self.inputs: list[Any] = []

    def call(self, data: Any) -> Any:
        from pipeline.llm.router import Done

        self.inputs.append(data)
        ev = [e["id"] for c in json.loads(data.industries_json) if c["industry"] == "Grid" for e in c["evidence"]][:2]
        return Done({"themes": [{"market": "us", "industry": "Grid", "title": "Grid demand builds quietly",
                                 "why": "Most grid companies grow faster while prices barely moved.",
                                 "wrong_if": "growth slows", "confidence": "medium", "evidence": ev}],
                     "reviews": [], "note": "First call."}, "fake", "m")  # fmt: skip


def test_themes_report_names_the_quiet_industry_and_remembers_it(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Grid: revenue accelerating at 5 of 6 companies, prices flat; Chips: no evidence, prices up. P-08 reads Grid
    alone; its theme is stored with each company's price, and next week's run hands it back as an earlier call."""
    from pipeline.reports import themes

    names = [(f"G{i}", "Grid") for i in range(6)] + [(f"C{i}", "Chips") for i in range(6)]
    repo.upsert_us_companies(conn, [Company(market="us", name=f"Co {t}", cik=f"{700000 + i:010d}", ticker=t,
                                            industry=ind) for i, (t, ind) in enumerate(names)])  # fmt: skip
    ids = {c.ticker: c.id for c in repo.companies(conn, market="us")}
    rows = []
    for t, _ in names:
        speed = t.startswith("G") and t != "G5"
        revs = [100] * 6 + ([110, 130, 150] if speed else [100] * 3)
        for q, rev in enumerate(revs):
            y, m = 2024 + q // 4, 3 * (q % 4) + 3
            rows.append(FundamentalsRow(company_id=ids[t], period_end=date(y, m, 28), fiscal_label=f"Q{q % 4 + 1}",
                                        filed_at=datetime(y, m, 28, tzinfo=UTC) + timedelta(days=30),
                                        revenue=Decimal(rev), currency="USD", source="sec_xbrl"))  # fmt: skip
    repo.insert_fundamentals(conn, rows)
    asset = tmp_path / "us_month_prices.csv.gz"
    bars = {}
    for t, _ in names:
        up = t.startswith("C")
        bars[t] = month_bars([20.0 + (j * 1.5 if up else 0) for j in range(22)])  # Dec 2024 .. Sep 2026
    write_month_csv(asset, bars)
    state.put(conn, winners.LAB_ASSET, asset.read_bytes())
    week = date(2026, 10, 23)
    router = ThemeRouter()
    body = themes.build(conn, router, week, date(2026, 10, 25))  # type: ignore[arg-type]
    assert body["answered"] and body["candidates"] == 1 and [x["industry"] for x in body["themes"]] == ["Grid"]
    assert all(e["price"] == 20.0 for e in body["themes"][0]["evidence"]) and body["themes"][0]["early"]
    sent = json.loads(router.inputs[0].industries_json)
    assert [c["industry"] for c in sent] == ["Grid"] and "company_id" not in json.dumps(sent)
    repo.upsert_report(conn, "themes", week, body)
    later = themes.build(conn, router, week + timedelta(days=7), date(2026, 11, 1))  # type: ignore[arg-type]
    assert later["scorecard"][0]["industry"] == "Grid" and later["scorecard"][0]["since"] == 0.0
    assert json.loads(router.inputs[1].calls_json)[0]["title"] == "Grid demand builds quietly"
