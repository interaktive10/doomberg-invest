"""Durable pipeline state (pipeline/db/state.py, migration 0017; docs/SPEC_ISSUES.md 55): the India state files and the
Lab's Twelve Data download live in the database, not the 7-day Actions cache or a public release."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import psycopg
import pytest

from pipeline.db import state


def test_put_then_get_round_trips_gzipped(conn: psycopg.Connection[Any]) -> None:
    body = b'{"results_queue": []}' * 1000
    state.put(conn, "in_weekly", body)
    stored = state.get(conn, "in_weekly")
    assert stored is not None and stored.body == body
    raw, size = conn.execute("select body, bytes from pipeline_state where name = 'in_weekly'").fetchone() or (b"", 0)
    assert size == len(body) and gzip.decompress(bytes(raw)) == body and len(bytes(raw)) < len(body) // 10
    state.put(conn, "in_weekly", b"newer")  # a later save replaces the copy
    assert (state.get(conn, "in_weekly") or state.Stored(b"", stored.saved_at)).body == b"newer"
    assert state.get(conn, "nothing_yet") is None


def test_files_restore_and_a_missing_name_leaves_the_path_alone(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    prices, st = tmp_path / "lab" / "us_month_prices.csv.gz", tmp_path / "lab" / "us_prices_state.json"
    prices.parent.mkdir()
    prices.write_bytes(gzip.compress(b"ticker,month,close\n"))
    st.write_text('{"done": ["AAA"]}', encoding="utf-8")
    lines = state.put_files(conn, [("lab_us_month_prices", prices), ("lab_us_prices_state", st),
                                   ("absent", tmp_path / "nope.json")])  # fmt: skip
    assert lines[2].startswith("state absent:") and "nothing stored" in lines[2]
    out = tmp_path / "restore"
    got = state.get_files(conn, [("lab_us_month_prices", out / "p.csv.gz"), ("lab_us_prices_state", out / "s.json"),
                                 ("absent", out / "kept.json")])  # fmt: skip
    assert (out / "p.csv.gz").read_bytes() == prices.read_bytes()
    assert (out / "s.json").read_text(encoding="utf-8") == '{"done": ["AAA"]}'
    assert not (out / "kept.json").exists() and "nothing stored yet" in got[2]


def test_names_are_checked(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(ValueError, match="NAME=PATH"):
        state.pairs(["in_weekly"])
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        state.put(conn, "In Weekly!", b"x")


def test_the_table_is_service_role_only(conn: psycopg.Connection[Any]) -> None:
    rls = conn.execute("select relrowsecurity from pg_class where relname = 'pipeline_state'").fetchone()
    assert rls == (True,)
