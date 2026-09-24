"""Display views for the web (docs/SPEC_ISSUES.md 6): security_invoker, never read by pipeline code."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[2]
VIEWS = ("fundamentals_display_v", "ownership_display_v", "insider_events_display_v", "corp_events_display_v")


def test_views_run_with_caller_rights(conn: psycopg.Connection[Any]) -> None:
    rows = dict(
        conn.execute(
            "select c.relname, c.reloptions from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind = 'v'"
        ).fetchall()
    )
    assert set(rows) == set(VIEWS)
    for name, opts in rows.items():
        assert opts and "security_invoker=true" in opts, name


def test_pipeline_never_reads_display_views() -> None:
    """Computation must go through as_of(); a display view has no cutoff and would leak later filings."""
    pattern = re.compile(r"_display_v\b")
    offenders = [
        f"{p.relative_to(ROOT)}:{i}"
        for base in ("pipeline", "scripts")
        for p in (ROOT / base).rglob("*.py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
