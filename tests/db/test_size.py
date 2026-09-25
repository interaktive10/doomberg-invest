"""M1-04: projected size for 7,000 companies x 60 quarters < 400 MB (estimator test), plus size_guard behaviour
(BRIEF §2.8)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import psycopg

from pipeline.db import size_guard

from .conftest import new_company


def test_projection_7000_companies_60_quarters_under_400mb(conn: psycopg.Connection[Any]) -> None:
    rows = size_guard.project(conn, companies=7000, quarters=60)
    total = sum(p.projected_mb for p in rows)
    by_table = {p.table: p for p in rows}
    assert by_table["fundamentals_q"].target_rows == 588_000  # 1.4 versions per company-quarter (review F10)
    # BRIEF §2.8 expects ~150 MB for fundamentals_q with indexes (one version); a measurement far off means a broken
    # probe.
    assert 80 < by_table["fundamentals_q"].projected_mb < 400
    assert total < size_guard.LIMIT_MB, [(p.table, round(p.projected_mb, 1)) for p in rows]


def test_projection_leaves_no_rows_behind(conn: psycopg.Connection[Any]) -> None:
    size_guard.project(conn, sample_companies=10, quarters=4)
    size_guard.project_signal_values(conn)
    assert conn.execute("select count(*) from companies where name like 'Example Industrial%'").fetchone() == (0,)
    assert conn.execute("select count(*) from signal_values").fetchone() == (0,)


def test_signal_values_projection_is_reported(conn: psycopg.Connection[Any]) -> None:
    p = size_guard.project_signal_values(conn)
    assert p.target_rows == 7000 * 12 * 52 * 3
    assert p.bytes_per_row > 0  # the number itself is tracked in docs/SPEC_ISSUES.md 9


def test_prune_keeps_three_years(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    today = date(2026, 9, 26)
    for week_end in (today - timedelta(days=365 * 3 + 10), today - timedelta(days=365 * 3 - 10), today):
        conn.execute(
            "insert into signal_values (company_id, week_end, signal_id, fired, strength, inputs) "
            "values (%s, %s, 'S1', false, 0, '{}')",
            (cid, week_end),
        )
    assert size_guard.prune_signal_values(conn, today) == 1
    assert conn.execute("select count(*) from signal_values where company_id = %s", (cid,)).fetchone() == (2,)


def test_enforce_fails_above_limit(conn: psycopg.Connection[Any]) -> None:
    assert size_guard.enforce(conn, date(2026, 9, 26)).ok
    tiny = size_guard.enforce(conn, date(2026, 9, 26), limit_mb=1)
    assert not tiny.ok and tiny.database_mb > 1


def test_probe_sql_has_no_bare_percent() -> None:
    """Regression: `q % 4` in a probe query is read by psycopg as a broken placeholder once params are bound."""
    import re

    bare = re.compile(r"%(?!\([a-z_]+\)s|%)")
    assert {t: bool(bare.search(sql)) for t, sql in size_guard._SAMPLES.items()} == dict.fromkeys(
        size_guard._SAMPLES, False
    )
