"""The Themes screen's "Rethink now" (docs/SPEC_ISSUES.md 76): the web app stores a request in app_settings;
research.yml runs the rethink when one is there, at most once a day."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from pipeline.db import repo
from pipeline.reports import themes


def request(conn: psycopg.Connection[Any]) -> None:
    conn.execute("insert into app_settings (key, value) values (%s, %s) on conflict (key) do update set value = "
                 "excluded.value", (themes.REQUEST, Jsonb({"at": "2026-11-02T17:00:00Z"})))  # fmt: skip


def test_no_request_no_rethink(conn: psycopg.Connection[Any]) -> None:
    assert themes.rethink_requested(conn, date(2026, 11, 2)) == (False, "no rethink requested")


def test_a_request_runs_unless_the_library_was_rethought_today(conn: psycopg.Connection[Any]) -> None:
    request(conn)
    repo.upsert_report(conn, "themes", date(2026, 10, 30), {"last_rethink": "2026-10-31", "library": []})
    assert themes.rethink_requested(conn, date(2026, 11, 2)) == (True, "requested on the Themes screen")
    repo.upsert_report(conn, "themes", date(2026, 10, 30), {"last_rethink": "2026-11-02", "library": []})
    go, why = themes.rethink_requested(conn, date(2026, 11, 2))
    assert not go and "already rethought today" in why
    assert repo.app_setting(conn, themes.REQUEST) is None  # dropped, not kept for tomorrow
