"""Seed script on the committed universe snapshots (BRIEF §1.3, §8 M1 "seed scripts")."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import psycopg
import pytest

from pipeline.db import seed
from pipeline.settings import REPO_ROOT


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


def test_seed_refuses_truncated_snapshot(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """Regression: a half-downloaded snapshot seeded as-is would move thousands of companies out of the universe."""
    (tmp_path / "config").mkdir()
    for f in ("capex_seed.yaml", "weights.yaml", "universe_us.yaml", "universe_in.yaml"):
        shutil.copy(REPO_ROOT / "config" / f, tmp_path / "config" / f)
    (tmp_path / "data" / "universe").mkdir(parents=True)
    shutil.copy(seed.IN_SNAPSHOT, tmp_path / "data" / "universe" / "nse_equity_list.csv")
    truncated = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]]}
    (tmp_path / "data" / "universe" / "us_tickers_exchange.json").write_text(json.dumps(truncated), encoding="utf-8")
    seed.seed(conn)  # a good seed first, so there is a universe to lose
    before = conn.execute("select count(*) from companies where in_universe").fetchone()
    with pytest.raises(seed.SnapshotTooSmall, match="us snapshot has 1 companies"):
        seed.seed(conn, tmp_path)
    assert conn.execute("select count(*) from companies where in_universe").fetchone() == before


def test_seed_lists_only_sources_the_pipeline_reports(conn: psycopg.Connection[Any]) -> None:
    """Regression: the quarterly re-seed put back the 'stooq' row migration 0012 dropped, and 'fred' has no reader, so
    the digest and Settings listed two sources as "never succeeded" (docs/SPEC_ISSUES.md 40)."""
    seed.seed(conn)
    sources = {r[0] for r in conn.execute("select source from source_health")}
    dead = {"stooq", "fred", "yahoo", "eia", "gdelt"}  # gdelt: nothing asks it since C4 went (SPEC_ISSUES 48)
    assert sources == set(seed.SOURCES) and "twelvedata" in sources and not sources & dead


def test_migration_0014_drops_the_rows_that_never_succeed(conn: psycopg.Connection[Any]) -> None:
    conn.execute("insert into source_health (source) values ('stooq'), ('fred'), ('sec') on conflict do nothing")
    conn.execute((REPO_ROOT / "db" / "migrations" / "0014_source_health_cleanup.sql").read_text(encoding="utf-8"))
    assert {r[0] for r in conn.execute("select source from source_health")} == {"sec"}
