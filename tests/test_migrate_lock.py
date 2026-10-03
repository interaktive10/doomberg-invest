"""pipeline/db/migrate.py serialises concurrent runners with a transaction-scoped advisory lock. The scheduled
weekly run of 2026-10-03 failed in its us job's migrate step: "tuple concurrently updated" on "revoke all on
schema_migrations", because the india job's runner revoked at the same moment and the second revoke ran in a
transaction without the lock. No database: a fake connection records which transaction holds the lock."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pipeline.db import migrate


class Recorder:
    """Enough of a psycopg connection for migrate.apply: nested transactions, execute, fetchall."""

    def __init__(self) -> None:
        self.depth = 0
        self.locked = False  # the outermost transaction took the advisory lock
        self.statements: list[tuple[str, bool]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.depth == 0:
            self.locked = False  # a transaction-scoped lock ends with its transaction
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def execute(self, sql: str | bytes, params: Any = None) -> Any:
        text = sql.decode() if isinstance(sql, bytes) else sql
        if "pg_advisory_xact_lock" in text:
            self.locked = True
        self.statements.append((text, self.locked and self.depth > 0))
        return SimpleNamespace(fetchall=lambda: [])


def test_every_revoke_runs_under_the_lock(tmp_path: Path) -> None:
    conn = Recorder()
    migrate.apply(conn, tmp_path)  # type: ignore[arg-type]
    revokes = [locked for sql, locked in conn.statements if "revoke all on schema_migrations" in sql]
    assert len(revokes) == 2 and all(revokes)
