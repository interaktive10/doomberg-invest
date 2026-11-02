"""Winners and Themes read the latest daily closes after the stored week-ends (docs/SPEC_ISSUES.md 75)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.db import repo
from pipeline.db.models import PriceW
from pipeline.reports import closes, winners


def test_indias_series_gain_the_recent_closes(conn: psycopg.Connection[Any]) -> None:
    cid = uuid.uuid4()
    conn.execute("insert into companies (id, market, name, nse_symbol, fiscal_year_end) values (%s, 'in', 'Tara', "
                 "'TARAPUMP', '0331')", (cid,))  # fmt: skip
    repo.upsert_prices(conn, [PriceW(company_id=cid, week_end=date(2026, 10, 30), close=Decimal(800), source="NSE")])
    assert winners.india_series(conn, [cid], date(2026, 11, 3)) == {cid: [(date(2026, 10, 30), Decimal(800))]}
    recent = closes.Recent(india={"TARAPUMP": [(date(2026, 10, 30), Decimal(1)), (date(2026, 11, 2), Decimal(812))]})
    closes.save(conn, recent)
    got = winners.india_series(conn, [cid], date(2026, 11, 3))[cid]
    assert got == [
        (date(2026, 10, 30), Decimal(800)),
        (date(2026, 11, 2), Decimal(812)),
    ]  # the week-end's own close stays
