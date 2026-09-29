"""M5 review R1-F6 against the database: the private tables' rows exactly as the driver returns them (dict_row and
the default tuple factory), passed to the router directly or nested in every public PromptInput, raise
PrivacyViolation and send nothing (BRIEF §2.6, M5-04)."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from pipeline.llm.privacy import PrivacyViolation
from pipeline.llm.router import Router
from tests.db.conftest import new_company
from tests.llm.conftest import FakeClock, Scripted, quotas
from tests.llm.test_privacy import wrappers


def private_rows(conn: psycopg.Connection[Any]) -> list[object]:
    cid = new_company(conn)
    (tid,) = conn.execute(
        "insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, created_week) "
        "values (%s, 'position', '', '{}', '{}', 'manual', '{}', %s) returning id",
        (cid, date(2026, 9, 18)),
    ).fetchone() or (None,)
    conn.execute("insert into journal (thesis_id, entry_date, action, portfolio_pct, reason) values "
                 "(%s, %s, 'start_position', 2.5, 'private reasoning')", (tid, date(2026, 9, 21)))  # fmt: skip
    conn.execute("insert into postmortems (thesis_id, what_happened, thesis_right, lessons) values "
                 "(%s, 'private', false, 'private')", (tid,))  # fmt: skip
    rows: list[object] = []
    for table in ("journal", "postmortems"):
        rows += conn.execute(f"select * from {table}").fetchall()  # noqa: S608 (a fixed table name)
        with conn.cursor(row_factory=dict_row) as cur:
            rows += cur.execute(f"select * from {table}").fetchall()  # noqa: S608
    return rows


def test_private_rows_from_the_driver_never_reach_a_provider(conn: psycopg.Connection[Any]) -> None:
    gemini = Scripted("gemini")
    router = Router({"gemini": gemini}, quotas(["gemini"]), FakeClock())
    rows = private_rows(conn)
    assert len(rows) == 4 and any(isinstance(r, dict) for r in rows) and any(isinstance(r, tuple) for r in rows)
    for row in rows:
        for value in wrappers(row):
            with pytest.raises(PrivacyViolation):
                router.call(value)  # type: ignore[arg-type]
    assert gemini.requests == []
