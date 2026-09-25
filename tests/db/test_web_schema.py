"""M7: migration 0011 (what the web app writes beyond §3) and the e2e seed (scripts/seed_e2e.py), which the web job's
Playwright suite runs against; this keeps the seed valid whenever the schema changes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]


def seed_module() -> Any:
    spec = importlib.util.spec_from_file_location("seed_e2e", ROOT / "scripts" / "seed_e2e.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_e2e_seed_fits_the_schema_and_feeds_every_screen(conn: psycopg.Connection[Any]) -> None:
    seed = seed_module()
    seed.seed(conn)
    buckets = dict(conn.execute("select name, bucket from screen('{}')").fetchall())
    assert buckets == {"Echo Grid Corp.": "candidate", "Kappa Cables Ltd": "candidate", "Delta Power Inc.": "early",
                       "Omega Systems Inc.": "priced_in", "Sigma Holdings Inc.": "excluded"}  # fmt: skip
    assert conn.execute(
        "select count(*) from fundamentals_display_v where company_id = %s", (seed.ECHO,)
    ).fetchone() == (8,)
    pack_quarter = conn.execute("select evidence_pack->'metrics'->0->>'period_end' from theses where id = %s",
                                (seed.ECHO_THESIS,)).fetchone()  # fmt: skip
    latest = conn.execute("select max(period_end)::text from fundamentals_display_v where company_id = %s",
                          (seed.ECHO,)).fetchone()  # fmt: skip
    assert pack_quarter is not None and latest is not None and latest[0] > pack_quarter[0]  # a review is due
    assert conn.execute("select count(*) from capex_memberships where status = 'proposed'").fetchone() == (1,)
    assert conn.execute("select value from app_settings where key = 'position_min_thesis_weeks'").fetchone() == (4,)


def test_a_dismissal_needs_a_reason(conn: psycopg.Connection[Any]) -> None:
    seed_module().seed(conn)
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute("insert into candidate_actions (company_id, week_end, action, reason) values "
                     "('00000000-0000-4000-8000-0000000000e2', '2026-09-18', 'dismiss', '  ')")  # fmt: skip
    conn.execute("insert into candidate_actions (company_id, week_end, action) values "
                 "('00000000-0000-4000-8000-0000000000e3', '2026-09-18', 'research')")  # fmt: skip


def test_one_review_per_thesis_and_quarter(conn: psycopg.Connection[Any]) -> None:
    seed = seed_module()
    seed.seed(conn)
    conn.execute("insert into reviews (thesis_id, period_end) values (%s, '2026-06-30')", (seed.ECHO_THESIS,))
    with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
        conn.execute("insert into reviews (thesis_id, period_end) values (%s, '2026-06-30')", (seed.ECHO_THESIS,))
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute("update reviews set verdict = 'great' where thesis_id = %s", (seed.ECHO_THESIS,))
