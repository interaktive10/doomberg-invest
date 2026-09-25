"""Storage guard for the Supabase free tier (BRIEF §2.8, §8 M1-04, M9-03). `python -m pipeline.db.size_guard`.

- `enforce()`: prune signal_values older than 3 years and NSE announcements older than 120 days, then fail (exit 1)
  if the database is above 400 MB.
- `project()`: measure real bytes per row (heap + indexes + TOAST) on temp copies of the tables, then extrapolate
  to a target size, e.g. 7,000 companies x 60 quarters (M1-04). Temp tables vanish with the session and never
  touch real rows. `project_corp_events()`: the announcements kept at the measured daily rate (review F8 on M3).
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
ANNOUNCEMENT_KEEP_DAYS = 120  # NSE announcements: P-07 triage input and the last quarter's evidence (M5, M6)
ANNOUNCEMENTS_PER_DAY = 650  # every EQ company: ~800 a weekday, ~170 a weekend day (live NSE counts, 2026-09)
FUNDAMENTAL_VERSIONS = 1.45  # rows per company-quarter: restatement versions (F-US measures 1.418; R2-F1)

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


def prune_announcements(conn: Conn, today: date, keep_days: int = ANNOUNCEMENT_KEEP_DAYS) -> int:
    """Delete announcement events older than `keep_days` (migration 0006's function: only pit.py names the table in
    a query)."""
    row = conn.execute("select prune_announcements(%s)", (today - timedelta(days=keep_days),)).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


@dataclass(frozen=True)
class SizeReport:
    database_mb: float
    limit_mb: int
    pruned_signal_rows: int
    largest: list[tuple[str, float]]
    pruned_announcements: int = 0

    @property
    def ok(self) -> bool:
        return self.database_mb <= self.limit_mb


def enforce(conn: Conn, today: date | None = None, limit_mb: int = LIMIT_MB) -> SizeReport:
    day = today or datetime.now(UTC).date()
    pruned = prune_signal_values(conn, day)
    announcements = prune_announcements(conn, day)
    sizes = table_bytes(conn)
    return SizeReport(
        database_mb=database_bytes(conn) / MB,
        limit_mb=limit_mb,
        pruned_signal_rows=pruned,
        largest=[(t, b / MB) for t, b in list(sizes.items())[:5]],
        pruned_announcements=announcements,
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


_PROBE_TABLES = ("fundamentals_q", "ownership_q", "companies", "signal_values", "corp_events")

# Sample rows for each probe. %(n)s = sample companies (or rows), %(q)s = quarters. Every numeric column carries a
# 12-significant-digit value, the worst case for numeric storage, so real (sparser) data is smaller.
_MONEY = "(1234567890.12 + q * 1013)::numeric"
_SAMPLES: dict[str, str] = {
    "fundamentals_q": (
        "(company_id, period_end, fiscal_label, filed_at, "  # noqa: S608 (constants only; counts are bound params)
        + ", ".join(FUNDAMENTAL_COLUMNS)
        + ", currency, source) "
        "select c.id, (date '2011-03-31' + q * interval '3 months')::date, "
        "'FY' || (2011 + q / 4) || 'Q' || (mod(q, 4) + 1), "
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
        "select gen_random_uuid(), date '2025-01-03' + mod(i, 52) * 7, 'S' || (mod(i, 12) + 1), false, 0, "
        "jsonb_build_object('q', '2025Q3', 'g_ob', 0.1834, 'g_rev', 0.0712, 'ob_cov', 1.42, 'ob_cov_ya', 1.31, "
        "'periods', jsonb_build_array('2024Q3', '2025Q3')) "
        "from generate_series(1, %(n)s) i"
    ),
    # An NSE announcement as the daily run stores it; the text is longer than the live average (137 characters).
    "corp_events": (
        "(company_id, event_date, filed_at, kind, detail, source_url) "
        "select gen_random_uuid(), date '2026-01-01' + mod(i, 120), "
        "timestamptz '2026-01-01 08:00:00+00' + mod(i, 120) * interval '1 day', 'announcement', "
        "jsonb_build_object('category', 'Analysts/Institutional Investor Meet/Con. Call Updates', 'text', "
        "'Example Industrial Holdings Limited has informed the Exchange about the schedule of an analyst meet on "
        "September 22, 2026 and the earnings call for the quarter ended June 30, 2026.', 'seq_id', "
        "(106000000 + i)::text, 'has_xbrl', false), "
        "'https://nsearchives.nseindia.com/corporate/EXAMPLEIND_' || lpad(i::text, 8, '0') || "
        "'_19092026231951_Intimation.pdf' "
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
    conn: Conn,
    companies: int = 7000,
    quarters: int = 60,
    sample_companies: int = 200,
    versions: float = FUNDAMENTAL_VERSIONS,
) -> list[TableProjection]:
    """Projected size of the company and quarterly tables for `companies` x `quarters` (BRIEF §2.8: one wide row
    per company-quarter, times the restatement versions kept for point-in-time reads)."""
    n = sample_companies * quarters
    return [
        TableProjection(
            "fundamentals_q",
            n,
            _measure(conn, "fundamentals_q", sample_companies, quarters),
            round(companies * quarters * versions),
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


def project_corp_events(
    conn: Conn, per_day: int = ANNOUNCEMENTS_PER_DAY, keep_days: int = ANNOUNCEMENT_KEEP_DAYS
) -> TableProjection:
    """corp_events at steady state: `keep_days` of India announcements at `per_day` (US events are a few a day)."""
    sample = 5000
    return TableProjection("corp_events", sample, _measure(conn, "corp_events", sample), per_day * keep_days)


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
            rows = [*project(conn), project_corp_events(conn)]
            for p in rows:
                print(_fmt(p))
            total = sum(p.projected_mb for p in rows)
            print(f"quarterly tables + announcements total: {total:.1f} MB (limit {LIMIT_MB} MB)")
            print(_fmt(project_signal_values(conn)))
            conn.rollback()
            return 0
        report = enforce(conn)
        conn.commit()
    print(
        f"size_guard: {report.database_mb:.1f} MB of {report.limit_mb} MB; pruned {report.pruned_signal_rows} "
        f"signal_values rows and {report.pruned_announcements} announcements; largest: "
        + ", ".join(f"{t} {mb:.1f} MB" for t, mb in report.largest)
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
