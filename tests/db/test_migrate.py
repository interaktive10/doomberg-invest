"""M1-01: migrations run from zero twice (BRIEF §8 M1)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import psycopg
import pytest

from pipeline.db import migrate

from .conftest import fresh_database

ALL_VERSIONS = [m.version for m in migrate.discover()]


def schema_signature(conn: psycopg.Connection[Any]) -> list[tuple[Any, ...]]:
    cols = conn.execute(
        "select table_name, column_name, data_type, is_nullable, coalesce(column_default, '') "
        "from information_schema.columns where table_schema = 'public' order by 1, 2"
    ).fetchall()
    idx = conn.execute(
        "select tablename, indexdef from pg_indexes where schemaname = 'public' order by 1, 2"
    ).fetchall()
    cons = conn.execute(
        "select conrelid::regclass::text, pg_get_constraintdef(oid) from pg_constraint "
        "where connamespace = 'public'::regnamespace order by 1, 2"
    ).fetchall()
    return [*cols, *idx, *cons]


def test_migrations_run_from_zero_twice() -> None:
    signatures = []
    for _ in range(2):
        with fresh_database() as url, psycopg.connect(url, autocommit=True) as c:
            assert migrate.apply(c) == ALL_VERSIONS
            assert migrate.apply(c) == []  # re-run is a no-op
            signatures.append(schema_signature(c))
    assert signatures[0] == signatures[1]
    tables = {r[0] for r in signatures[0]}
    for t in ("companies", "fundamentals_q", "facts", "links", "signal_values", "journal", "schema_migrations"):
        assert t in tables


def test_changed_migration_is_rejected(tmp_path: Path) -> None:
    for f in migrate.MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(f, tmp_path / f.name)
    with fresh_database() as url, psycopg.connect(url, autocommit=True) as c:
        migrate.apply(c, tmp_path)
        first = sorted(tmp_path.glob("*.sql"))[0]
        first.write_text(first.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")
        with pytest.raises(migrate.MigrationChanged):
            migrate.apply(c, tmp_path)


def test_failed_migration_leaves_database_unchanged(tmp_path: Path) -> None:
    (tmp_path / "0001_ok.sql").write_text("create table t_ok (id int);", encoding="utf-8")
    (tmp_path / "0002_bad.sql").write_text("create table t_bad (id int); select no_such_function();", encoding="utf-8")
    with fresh_database() as url, psycopg.connect(url, autocommit=True) as c:
        with pytest.raises(psycopg.errors.UndefinedFunction):
            migrate.apply(c, tmp_path)
        assert c.execute("select to_regclass('t_ok'), to_regclass('t_bad')").fetchone() == (None, None)


def test_versions_must_be_numbered(tmp_path: Path) -> None:
    (tmp_path / "init.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="must start with a number"):
        migrate.discover(tmp_path)
