"""Seed script on the committed universe snapshots (BRIEF §1.3, §8 M1 "seed scripts")."""

from __future__ import annotations

from typing import Any

import psycopg

from pipeline.db import seed


def test_seed_from_snapshots_is_idempotent(conn: psycopg.Connection[Any]) -> None:
    first = seed.seed(conn)
    assert first.us >= 3000 and first.india >= 1500  # the M0-05 floors
    assert first.us_capex == 61  # every US capex ticker resolved (docs/UNIVERSE_ISSUES.md)
    assert first.in_capex == 38  # verified India symbols; E2E, STLTECH, HFCL are BE series
    assert first.weights_inserted
    counts = conn.execute("select market, count(*) from companies group by market order by market").fetchall()
    second = seed.seed(conn)
    assert second.us_left_universe == 0 and second.in_left_universe == 0 and not second.weights_inserted
    assert conn.execute("select market, count(*) from companies group by market order by market").fetchall() == counts
    assert conn.execute("select count(*) from source_health").fetchone() == (len(seed.SOURCES),)


def test_company_missing_from_snapshot_leaves_universe(conn: psycopg.Connection[Any]) -> None:
    conn.execute("insert into companies (market, name, cik) values ('us', 'Gone Inc', '9999999999')")
    seed.seed(conn)
    assert conn.execute("select in_universe, excluded_reason from companies where cik = '9999999999'").fetchone() == (
        False,
        "not in the SEC NYSE/Nasdaq snapshot",
    )
