"""Apply db/migrations/*.sql in order (BRIEF §3, §8 M1-01). `python -m pipeline.db.migrate`.

- Each file runs once, recorded in `schema_migrations` with a sha256. All pending files apply in one transaction
  (a savepoint each): a failure leaves the database as it was.
- Re-running is a no-op. An applied file whose content changed is an error: write a new migration instead.
- An advisory lock serialises concurrent runners (one pipeline run at a time, BRIEF §2.5).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from pipeline.settings import REPO_ROOT, Settings

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
_LOCK_KEY = 0x646F6F6D  # "doom"

# Bookkeeping only; the application schema lives in db/migrations. RLS + revoke keep it off Supabase's API roles.
_BOOTSTRAP = """
create table if not exists schema_migrations (
  version text primary key, name text not null, sha256 text not null,
  applied_at timestamptz not null default now());
alter table schema_migrations enable row level security;
"""
_REVOKE_API_ROLES = """
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on schema_migrations from anon, authenticated;
  end if;
end $$;
"""


class MigrationChanged(RuntimeError):
    """An already-applied migration file no longer matches its recorded checksum."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    out: list[Migration] = []
    for p in sorted(directory.glob("*.sql")):
        version, _, name = p.stem.partition("_")
        if not version.isdigit():
            raise ValueError(f"migration file must start with a number: {p.name}")
        out.append(Migration(version, name, p.read_text(encoding="utf-8")))
    versions = [m.version for m in out]
    if len(set(versions)) != len(versions):
        raise ValueError(f"duplicate migration versions: {versions}")
    return out


def apply(conn: psycopg.Connection[Any], directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; return the versions applied (empty when up to date)."""
    migrations = discover(directory)
    applied_now: list[str] = []
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        conn.execute(_BOOTSTRAP)
        conn.execute(_REVOKE_API_ROLES)
        done = {str(v): str(h) for v, h in conn.execute("select version, sha256 from schema_migrations").fetchall()}
        for m in migrations:
            if m.version in done:
                if done[m.version] != m.sha256:
                    raise MigrationChanged(f"{m.version}_{m.name}.sql changed after it was applied")
                continue
            with conn.transaction():
                conn.execute(m.sql.encode("utf-8"))
                conn.execute(
                    "insert into schema_migrations (version, name, sha256) values (%s, %s, %s)",
                    (m.version, m.name, m.sha256),
                )
            applied_now.append(m.version)
    # 0002 creates the API roles; revoke on the bookkeeping table once they exist.
    with conn.transaction():
        conn.execute(_REVOKE_API_ROLES)
    return applied_now


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", default=None)
    a = ap.parse_args(argv)
    url = a.database_url or Settings.from_env().database_url
    with psycopg.connect(url, autocommit=True) as conn:
        done = apply(conn)
    print(f"migrate: applied {', '.join(done) if done else 'nothing (up to date)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
