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
    # Watch has a US and an India name (SPEC_ISSUES 56)
    assert buckets == {"Echo Grid Corp.": "candidate", "Kappa Cables Ltd": "candidate", "Delta Power Inc.": "early",
                       "Omega Systems Inc.": "priced_in", "Sigma Holdings Inc.": "excluded",
                       "Lumen Water Co.": "watch", "Tara Pumps Ltd": "watch"}  # fmt: skip
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
    # M7 review R1-F1: a thesis a kill criterion moved to Review, with no fundamentals (so no new quarter)
    omega = conn.execute("select t.state, k.status from theses t join kill_criteria k on k.thesis_id = t.id "
                         "where t.id = %s", (seed.OMEGA_THESIS,)).fetchone()  # fmt: skip
    assert omega == ("review", "triggered")
    assert conn.execute("select count(*) from fundamentals_q where company_id = %s", (seed.OMEGA,)).fetchone() == (0,)
    # M7 review R1-F11: a closed thesis with journal entries and a post-mortem, and ECHO's ownership/insider/events
    assert conn.execute("select count(*) from journal where thesis_id = %s", (seed.SIGMA_THESIS,)).fetchone() == (2,)
    assert conn.execute("select count(*) from postmortems").fetchone() == (1,)
    for view in ("ownership_display_v", "insider_events_display_v", "corp_events_display_v"):
        found = conn.execute(f"select count(*) > 0 from {view} where company_id = %s", (seed.ECHO,)).fetchone()
        assert found == (True,), view
    # M7 review R1-F5: ECHO's chart series is what the weekly run computes from its quarters
    points = conn.execute("select points from company_series where company_id = %s", (seed.ECHO,)).fetchone()
    assert points is not None and points[0] == seed.echo_series() and points[0][-1]["period_end"] == "2026-06-30"
    assert points[0][-1]["revenue_ttm"] == 4.52e9  # 1.04 + 1.10 + 1.16 + 1.22 billion


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


def test_one_open_review_without_a_quarter(conn: psycopg.Connection[Any]) -> None:
    """M7 review R1-F1: a thesis a kill criterion moved to Review gets one open review with no quarter (the page's
    insert ignores the unique violation when another render made it first); decided ones don't count."""
    seed = seed_module()
    seed.seed(conn)
    conn.execute("insert into reviews (thesis_id, period_end) values (%s, null)", (seed.ECHO_THESIS,))
    with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
        conn.execute("insert into reviews (thesis_id, period_end) values (%s, null)", (seed.ECHO_THESIS,))
    conn.execute("update reviews set verdict = 'intact' where thesis_id = %s", (seed.ECHO_THESIS,))
    conn.execute("insert into reviews (thesis_id, period_end) values (%s, null)", (seed.ECHO_THESIS,))


def test_llm_use_is_counted_in_the_database(conn: psycopg.Connection[Any]) -> None:
    """M7 review R1-F6: Settings reads llm_use_7d, which counts every call in the database (PostgREST would return at
    most max_rows rows). The digest no longer has an LLM table (overhaul PR 5)."""
    conn.execute(
        "insert into llm_calls (prompt_id, provider, model, ok, tokens_in, tokens_out, error, created_at) "
        "select 'P-01', 'gemini', 'm', i % 10 <> 0, 100, 20, case when i % 10 = 0 then 'gemini: 429' end, "
        "now() - interval '1 hour' from generate_series(1, 1500) i"
    )
    conn.execute("insert into llm_calls (prompt_id, provider, model, ok, created_at) values "
                 "('P-01', 'groq', 'm', true, now() - interval '8 days')")  # fmt: skip
    rows = conn.execute("select provider, calls, ok, rate_limited, tokens_in, tokens_out from llm_use_7d").fetchall()
    assert rows == [("gemini", 1500, 1350, 150, 150000, 30000)]


def test_company_series_keeps_the_newest_week(conn: psycopg.Connection[Any]) -> None:
    """M7 review R1-F5: the weekly run replaces a company's chart series; a replay of an older week doesn't."""
    from datetime import date

    from pipeline.db import repo

    seed = seed_module()
    seed.seed(conn)
    repo.upsert_company_series(conn, date(2026, 9, 25), {seed.ECHO: [{"period_end": "2026-06-30", "roic": 0.12}]})
    repo.upsert_company_series(conn, date(2026, 9, 11), {seed.ECHO: [{"period_end": "2026-03-31", "roic": 0.1}]})
    row = conn.execute("select week_end::text, points from company_series where company_id = %s", (seed.ECHO,))
    assert row.fetchone() == ("2026-09-25", [{"period_end": "2026-06-30", "roic": 0.12}])
