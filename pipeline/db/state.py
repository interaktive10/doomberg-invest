"""Durable pipeline state (docs/SPEC_ISSUES.md 55; migration 0017). `python -m pipeline.db.state get|put NAME=PATH ...`.

The India jobs' state files and the Signal Lab's Twelve Data download are kept in the database, gzipped, one row per
name: the Actions cache evicts an entry after 7 days unused (India's state was lost that way in the pause) and a
release asset of a public repository is public (BRIEF §1.2.6: free data is for personal use, never redistributed).

- `get NAME=PATH ...`: writes each stored body to its PATH (parents created). A name with nothing stored yet leaves its
  PATH alone and is reported, not an error: a first run starts from an empty state.
- `put NAME=PATH ...`: stores every PATH in one transaction, so files saved together (the Lab's prices and the state
  that says which of them are complete) never get out of step. A missing PATH is skipped and reported.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from pipeline.settings import Settings

Conn = psycopg.Connection[Any]


@dataclass(frozen=True)
class Stored:
    body: bytes  # as written (un-gzipped)
    saved_at: datetime


def put(conn: Conn, name: str, body: bytes) -> None:
    """Store `body` under `name` (gzipped), replacing an earlier copy. The caller commits."""
    conn.execute(
        b"insert into pipeline_state (name, body, bytes, saved_at) values (%(n)s, %(b)s, %(s)s, now()) "
        b"on conflict (name) do update set body = excluded.body, bytes = excluded.bytes, saved_at = excluded.saved_at",
        {"n": name, "b": gzip.compress(body, compresslevel=6, mtime=0), "s": len(body)},
    )


def get(conn: Conn, name: str) -> Stored | None:
    row = conn.execute(b"select body, saved_at from pipeline_state where name = %s", (name,)).fetchone()
    if row is None:
        return None
    return Stored(gzip.decompress(bytes(row[0])), row[1])


def pairs(items: Sequence[str]) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for item in items:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            raise ValueError(f"expected NAME=PATH, got {item!r}")
        out.append((name, Path(path)))
    return out


def get_files(conn: Conn, items: Sequence[tuple[str, Path]]) -> list[str]:
    """Restore each stored name to its path; the lines to print."""
    lines: list[str] = []
    for name, path in items:
        stored = get(conn, name)
        if stored is None:
            lines.append(f"state {name}: nothing stored yet ({path} left as it is)")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(stored.body)
        lines.append(f"state {name}: {len(stored.body):,} bytes saved {stored.saved_at:%Y-%m-%d %H:%M} UTC -> {path}")
    return lines


def put_files(conn: Conn, items: Sequence[tuple[str, Path]]) -> list[str]:
    """Store every existing path, all in one transaction; the lines to print."""
    lines: list[str] = []
    with conn.transaction():
        for name, path in items:
            if not path.exists():
                lines.append(f"state {name}: {path} doesn't exist, nothing stored")
                continue
            body = path.read_bytes()
            put(conn, name, body)
            lines.append(f"state {name}: stored {len(body):,} bytes from {path}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("get", "put"))
    ap.add_argument("items", nargs="+", metavar="NAME=PATH")
    a = ap.parse_args(argv)
    items = pairs(a.items)
    with psycopg.connect(Settings.from_env().database_url) as conn:
        lines = get_files(conn, items) if a.command == "get" else put_files(conn, items)
        conn.commit()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
