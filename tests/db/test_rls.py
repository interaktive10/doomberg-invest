"""M1-03: RLS on every table; queries as anon (and authenticated) fail; local roles mirror Supabase (BRIEF §3)."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

API_ROLES = ("anon", "authenticated")


def relations(conn: psycopg.Connection[Any], kinds: tuple[str, ...]) -> list[str]:
    rows = conn.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = any(%s) order by 1",
        (list(kinds),),
    ).fetchall()
    return [str(r[0]) for r in rows]


def test_supabase_roles_exist(conn: psycopg.Connection[Any]) -> None:
    rows = dict(
        conn.execute(
            "select rolname, rolbypassrls from pg_roles where rolname in ('anon', 'authenticated', 'service_role')"
        ).fetchall()
    )
    assert rows == {"anon": False, "authenticated": False, "service_role": True}


def test_every_table_has_rls_and_no_policies(conn: psycopg.Connection[Any]) -> None:
    no_rls = conn.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity"
    ).fetchall()
    assert no_rls == []
    assert conn.execute("select count(*) from pg_policies where schemaname = 'public'").fetchone() == (0,)
    assert len(relations(conn, ("r",))) >= 29  # 20 (§3) + 8 (F.2) + schema_migrations


@pytest.mark.parametrize("role", API_ROLES)
def test_api_roles_cannot_read_any_table_or_view(conn: psycopg.Connection[Any], role: str) -> None:
    names = relations(conn, ("r", "v"))
    assert "fundamentals_display_v" in names and "journal" in names
    for name in names:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
            conn.execute(f"set local role {role}".encode())
            conn.execute(f"select * from {name} limit 1".encode())


@pytest.mark.parametrize("role", API_ROLES)
def test_api_roles_cannot_write(conn: psycopg.Connection[Any], role: str) -> None:
    for stmt in (
        "insert into journal (entry_date, action, reason) values (current_date, 'note', 'x')",
        "insert into companies (market, name) values ('us', 'x')",
        "delete from theses",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
            conn.execute(f"set local role {role}".encode())
            conn.execute(stmt.encode())


def test_service_role_reads_views(conn: psycopg.Connection[Any]) -> None:
    with conn.transaction():
        conn.execute("set local role service_role")
        for v in relations(conn, ("v",)):
            conn.execute(f"select * from {v} limit 1".encode())


def test_tables_added_later_stay_closed_to_api_roles(conn: psycopg.Connection[Any]) -> None:
    """Default privileges: a table a later migration creates is readable by service_role (as on Supabase) and not
    by anon/authenticated, even before that migration remembers to enable RLS."""
    conn.execute("create table t_added_later (id int)")
    with conn.transaction():
        conn.execute("set local role service_role")
        conn.execute("select * from t_added_later")
    for role in API_ROLES:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
            conn.execute(f"set local role {role}".encode())
            conn.execute("select * from t_added_later")
