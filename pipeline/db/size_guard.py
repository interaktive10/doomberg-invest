"""Storage guard for the Supabase free tier (BRIEF §2.8, §8 M1-04, M9-03). `python -m pipeline.db.size_guard`.

- `enforce()`: prune signal_values older than 3 years, then fail (exit 1) if the database is above 400 MB.
- `project()`: measure real bytes per row (heap + indexes + TOAST) on temp copies of the tables, then extrapolate
  to a target size, e.g. 7,000 companies x 60 quarters (M1-04). Temp tables vanish with the session and never
  touch real rows.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg

from pipeline.db.models import FUNDAMENTAL_COLUMNS
from pipeline.settings import Settings

MB = 1024 * 1024
LIMIT_MB = 400
SIGNAL_KEEP_YEARS = 3

Conn = psycopg.Connection[Any]


def database_bytes(conn: Conn) -> int:
    row = conn.execute("select pg_database_size(current_database())").fetchone()
    assert row is not None
    return int(row[0])


def table_bytes(conn: Conn) -> dict[str, int]:
    rows = conn.execute(
        "select c.relname, pg_total_relation_size(c.oid) from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = 'r' order by 2 desc"
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def prune_signal_values(conn: Conn, today: date, keep_years: int = SIGNAL_KEEP_YEARS) -> int:
    """Delete signal_values older than `keep_years` (the Lab keeps its own Parquet, BRIEF §2.8)."""
    cutoff = today - timedelta(days=round(365.25 * keep_years))
    cur = conn.execute("delete from signal_values where week_end < %s", (cutoff,))
    return cur.rowcount


@dataclass(frozen=True)
class SizeReport:
    database_mb: float
    limit_mb: int
    pruned_signal_rows: int
    largest: list[tuple[str, float]]

    @property
    def ok(self) -> bool:
        return self.database_mb <= self.limit_mb


def enforce(conn: Conn, today: date | None = None, limit_mb: int = LIMIT_MB) -> SizeReport:
    pruned = prune_signal_values(conn, today or datetime.now(UTC).date())
    sizes = table_bytes(conn)
    return SizeReport(
        database_mb=database_bytes(conn) / MB,
        limit_mb=limit_mb,
        pruned_signal_rows=pruned,
        largest=[(t, b / MB) for t, b in list(sizes.items())[:5]],
    )


# ---------------------------------------------------------------- projection (M1-04)


@dataclass(frozen=True)
class TableProjection:
    table: str
    sample_rows: int
    bytes_per_row: float
    target_rows: int

    @property
    def projected_mb(self) -> float:
        return self.bytes_per_row * self.target_rows / MB


_PROBE_TABLES = ("fundamentals_q", "ownership_q", "companies", "signal_values")

# Sample rows for each probe. %(n)s = sample companies (or rows), %(q)s = quarters. Every numeric column carries a
# 12-significant-digit value, the worst case for numeric storage, so real (sparser) data is smaller.
_MONEY = "(1234567890.12 + q * 1013)::numeric"
_SAMPLES: dict[str, str] = {
    "fundamentals_q": (
        "(company_id, period_end, fiscal_label, filed_at, "  # noqa: S608 (constants only; counts are bound params)
        + ", ".join(FUNDAMENTAL_COLUMNS)
        + ", currency, source) "
        "select c.id, (date '2011-03-31' + q * interval '3 months')::date, "
        "'FY' || (2011 + q / 4) || 'Q' || (q % 4 + 1), "
        "timestamptz '2011-05-01 21:05:00+00' + q * interval '3 months', "
        + ", ".join(_MONEY for _ in FUNDAMENTAL_COLUMNS)
        + ", 'USD', 'sec_xbrl' "
        "from (select gen_random_uuid() as id from generate_series(1, %(n)s)) c, generate_series(0, %(q)s - 1) q"
    ),
    "ownership_q": (
        "(company_id, quarter_end, filed_at, inst_holders, inst_pct, fii_pct, dii_pct, promoter_pct, "
        "promoter_pledged_pct, source) "
        "select c.id, (date '2011-03-31' + q * interval '3 months')::date, "
        "timestamptz '2011-05-15 00:00:00+00' + q * interval '3 months', 150 + q, 61.2345, 18.1234, 12.5678, "
        "52.3456, 4.1234, 'sec_13f' "
        "from (select gen_random_uuid() as id from generate_series(1, %(n)s)) c, generate_series(0, %(q)s - 1) q"
    ),
    "companies": (
        "(market, name, cik, ticker, isin, nse_symbol, sector, industry, sic, fiscal_year_end) "
        "select 'us', 'Example Industrial Holdings Corporation ' || i, lpad(i::text, 10, '0'), 'TCK' || i, "
        "'INE' || lpad(i::text, 9, '0'), 'SYM' || i, 'Industrials', 'Electrical Components & Equipment', '3612', "
        "'1231' from generate_series(1, %(n)s) i"
    ),
    "signal_values": (
        "(company_id, week_end, signal_id, fired, strength, inputs) "
        "select gen_random_uuid(), date '2025-01-03' + (i % 52) * 7, 'S' || (i % 12 + 1), false, 0, "
        "jsonb_build_object('q', '2025Q3', 'g_ob', 0.1834, 'g_rev', 0.0712, 'ob_cov', 1.42, 'ob_cov_ya', 1.31, "
        "'periods', jsonb_build_array('2024Q3', '2025Q3')) "
        "from generate_series(1, %(n)s) i"
    ),
}


def _measure(conn: Conn, table: str, n: int, quarters: int = 1) -> float:
    """Bytes per row of `table` (heap, TOAST and every index) measured on a temp copy with `n x quarters` rows."""
    if table not in _PROBE_TABLES:
        raise ValueError(table)
    tmp = f"_size_probe_{table}"
    conn.execute(f"drop table if exists {tmp}".encode())
    conn.execute(f"create temp table {tmp} (like {table} including defaults including indexes)".encode())
    conn.execute(f"insert into {tmp} {_SAMPLES[table]}".encode(), {"n": n, "q": quarters})
    conn.execute(f"analyze {tmp}".encode())
    row = conn.execute("select pg_total_relation_size(%s::regclass)", (tmp,)).fetchone()
    conn.execute(f"drop table {tmp}".encode())
    assert row is not None
    return int(row[0]) / (n * quarters)


def project(
    conn: Conn, companies: int = 7000, quarters: int = 60, sample_companies: int = 200
) -> list[TableProjection]:
    """Projected size of the company and quarterly tables for `companies` x `quarters` (BRIEF §2.8: one wide row
    per company-quarter)."""
    n = sample_companies * quarters
    return [
        TableProjection(
            "fundamentals_q", n, _measure(conn, "fundamentals_q", sample_companies, quarters), companies * quarters
        ),
        TableProjection(
            "ownership_q", n, _measure(conn, "ownership_q", sample_companies, quarters), companies * quarters
        ),
        TableProjection("companies", sample_companies, _measure(conn, "companies", sample_companies), companies),
    ]


def project_signal_values(conn: Conn, companies: int = 7000, weeks: int = 52 * SIGNAL_KEEP_YEARS) -> TableProjection:
    """signal_values if every company stores all 12 signals every week for the 3 kept years (BRIEF §2.8, §4.6)."""
    sample = 2000
    return TableProjection("signal_values", sample, _measure(conn, "signal_values", sample), companies * 12 * weeks)


def _fmt(p: TableProjection) -> str:
    return f"{p.table:15} {p.bytes_per_row:7.1f} B/row x {p.target_rows:>10,} rows = {p.projected_mb:8.1f} MB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--project", action="store_true", help="print the projection instead of enforcing")
    a = ap.parse_args(argv)
    url = a.database_url or Settings.from_env().database_url
    with psycopg.connect(url) as conn:
        if a.project:
            rows = project(conn)
            for p in rows:
                print(_fmt(p))
            print(f"quarterly tables total: {sum(p.projected_mb for p in rows):.1f} MB (limit {LIMIT_MB} MB)")
            print(_fmt(project_signal_values(conn)))
            conn.rollback()
            return 0
        report = enforce(conn)
        conn.commit()
    print(
        f"size_guard: {report.database_mb:.1f} MB of {report.limit_mb} MB; pruned {report.pruned_signal_rows} "
        f"signal_values rows; largest: " + ", ".join(f"{t} {mb:.1f} MB" for t, mb in report.largest)
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
