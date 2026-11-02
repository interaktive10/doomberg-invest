"""Themes' company lists carry each company's market cap (2026-11-02: the market-cap range on every stock list), read
from company_metrics as of its latest scored week."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.db import repo


def test_market_caps_come_from_the_latest_metrics(conn: psycopg.Connection[Any]) -> None:
    a, b, c = (uuid.uuid4() for _ in range(3))
    for cid, name in ((a, "A"), (b, "B"), (c, "C")):
        conn.execute(
            "insert into companies (id, market, name, ticker, fiscal_year_end) values (%s, 'us', %s, %s, '1231')",
            (cid, name, name),
        )
    repo.upsert_company_metrics(conn, date(2026, 10, 30), {a: {"market_cap": 5.5e9, "ev": 6e9}, b: {"ev": 1e9},
                                                           c: {"market_cap": None}})  # fmt: skip
    caps = repo.market_caps(conn)
    assert caps.get(a) == Decimal("5500000000.0") and b not in caps and c not in caps
