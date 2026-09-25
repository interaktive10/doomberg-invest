"""Database fixtures. Tests run against a throwaway database on the local PostgreSQL (cloud sessions: started by
scripts/session_start.sh; CI: the postgres service in .github/workflows/ci.yml). Offline: no network."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from pipeline.db import migrate
from pipeline.settings import DEFAULT_DATABASE_URL

ADMIN_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def url_for(dbname: str) -> str:
    return make_conninfo(**{**conninfo_to_dict(ADMIN_URL), "dbname": dbname})


@contextmanager
def fresh_database() -> Iterator[str]:
    """An empty database, dropped afterwards."""
    name = f"doom_t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"create database {name}".encode())
    try:
        yield url_for(name)
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f"drop database if exists {name} with (force)".encode())


@pytest.fixture(scope="session")
def migrated_url() -> Iterator[str]:
    with fresh_database() as url:
        with psycopg.connect(url, autocommit=True) as c:
            migrate.apply(c)
        yield url


@pytest.fixture
def conn(migrated_url: str) -> Iterator[psycopg.Connection[Any]]:
    """A connection inside a transaction that is rolled back after the test."""
    with psycopg.connect(migrated_url) as c:
        # Open the outer transaction now, so code under test that uses conn.transaction() gets a savepoint
        # (rolled back below) instead of a BEGIN/COMMIT of its own.
        c.execute("select 1")
        try:
            yield c
        finally:
            c.rollback()


def new_company(conn: psycopg.Connection[Any], market: str = "us", name: str = "Test Co") -> uuid.UUID:
    key = uuid.uuid4().hex[:10]
    row = conn.execute(
        "insert into companies (market, name, cik, nse_symbol, isin) values (%s, %s, %s, %s, %s) returning id",
        (
            market,
            name,
            key if market == "us" else None,
            key if market == "in" else None,
            "IN" + key if market == "in" else None,
        ),
    ).fetchone()
    assert row is not None
    cid: uuid.UUID = row[0]
    return cid
