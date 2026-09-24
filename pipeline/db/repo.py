"""Repositories: typed writes (and non-point-in-time reads) for the pipeline (BRIEF §2.3 `db/repo.py`, §8 M1).

Point-in-time tables (fundamentals_q, ownership_q, insider_events, corp_events) are written here but read only
through pipeline.db.pit.as_of(). Writes are idempotent so a re-run of a weekly job doesn't duplicate rows:
- fundamentals_q: keyed by (company, period_end, filed_at). A restatement has a later filed_at, so it's a new row
  and the old version stays (BRIEF §4.1.4). Re-ingesting the same filing overwrites that version only.
- ownership_q: keyed by (company, quarter_end) as §3 defines it. A revision replaces the row only when it's filed
  later; as_of() before the revision then sees no row for that quarter (a gap, never a look-ahead).
- insider_events / corp_events: unique natural-key indexes (db/migrations/0002) make re-inserts no-ops.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pipeline.db.models import (
    FUNDAMENTAL_COLUMNS,
    BenchmarkW,
    Company,
    ContextValue,
    CorpEvent,
    FundamentalsRow,
    InsiderEvent,
    LabResult,
    LlmCall,
    OwnershipRow,
    PriceW,
    RedflagValue,
    Score,
    SignalValue,
    SourceHealth,
    WeightsVersion,
)

Conn = psycopg.Connection[Any]

_COMPANY_COLS = (
    "market",
    "name",
    "cik",
    "ticker",
    "isin",
    "nse_symbol",
    "bse_code",
    "sector",
    "industry",
    "sic",
    "fiscal_year_end",
    "in_universe",
    "capex_desk",
    "excluded_reason",
)


def _q(sql: str) -> bytes:
    return sql.encode("utf-8")


def _insert(table: str, cols: Sequence[str], conflict: str) -> bytes:
    placeholders = ", ".join(f"%({c})s" for c in cols)
    return _q(f"insert into {table} ({', '.join(cols)}) values ({placeholders}) {conflict}")  # noqa: S608


def _set_excluded(cols: Iterable[str]) -> str:
    return ", ".join(f"{c} = excluded.{c}" for c in cols)


# ---------------------------------------------------------------- companies


def upsert_us_companies(conn: Conn, companies: Sequence[Company]) -> None:
    """US companies are keyed by CIK."""
    if any(c.market != "us" or not c.cik for c in companies):
        raise ValueError("upsert_us_companies needs market='us' rows with a cik")
    upd = _set_excluded(c for c in _COMPANY_COLS if c not in ("market", "cik")) + ", updated_at = now()"
    with conn.cursor() as cur:
        cur.executemany(
            _insert("companies", _COMPANY_COLS, f"on conflict (cik) do update set {upd}"),
            [c.model_dump(include=set(_COMPANY_COLS)) for c in companies],
        )


def upsert_in_companies(conn: Conn, companies: Sequence[Company]) -> None:
    """Indian companies are keyed by NSE symbol. A symbol rename keeps the ISIN, so rows are re-pointed by ISIN
    first; a face-value split keeps the symbol and changes the ISIN, which the upsert on symbol handles."""
    if any(c.market != "in" or not c.nse_symbol or not c.isin for c in companies):
        raise ValueError("upsert_in_companies needs market='in' rows with nse_symbol and isin")
    rows = [c.model_dump(include=set(_COMPANY_COLS)) for c in companies]
    upd = _set_excluded(c for c in _COMPANY_COLS if c not in ("market", "nse_symbol")) + ", updated_at = now()"
    with conn.cursor() as cur:
        cur.executemany(
            _q(
                "update companies set nse_symbol = %(nse_symbol)s, updated_at = now() "
                "where market = 'in' and isin = %(isin)s and nse_symbol is distinct from %(nse_symbol)s "
                "and not exists (select 1 from companies c2 where c2.nse_symbol = %(nse_symbol)s)"
            ),
            rows,
        )
        cur.executemany(_insert("companies", _COMPANY_COLS, f"on conflict (nse_symbol) do update set {upd}"), rows)


def mark_missing_out_of_universe(conn: Conn, market: str, present_keys: Sequence[str], reason: str) -> int:
    """Companies of `market` whose key (cik for US, nse_symbol for India) isn't in the snapshot leave the universe.
    An empty key list would move every company out, so it's refused (a truncated download, not a real universe)."""
    key = {"us": "cik", "in": "nse_symbol"}[market]
    if not present_keys:
        raise ValueError(f"empty {market} snapshot: refusing to move every company out of the universe")
    cur = conn.execute(
        _q(
            f"update companies set in_universe = false, excluded_reason = %(reason)s, updated_at = now() "  # noqa: S608
            f"where market = %(market)s and in_universe and not ({key} = any(%(keys)s))"
        ),
        {"reason": reason, "market": market, "keys": list(present_keys)},
    )
    return cur.rowcount


def companies(conn: Conn, market: str | None = None, in_universe: bool | None = None) -> list[Company]:
    cols = ", ".join(("id", *_COMPANY_COLS))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _q(
                f"select {cols} from companies where (%(m)s::text is null or market = %(m)s) "  # noqa: S608
                "and (%(u)s::boolean is null or in_universe = %(u)s) order by market, name"
            ),
            {"m": market, "u": in_universe},
        )
        return [Company(**r) for r in cur.fetchall()]


def company_ids_by(conn: Conn, key: str) -> dict[str, UUID]:
    """Map cik / nse_symbol / isin / ticker -> company id."""
    if key not in ("cik", "nse_symbol", "isin", "ticker"):
        raise ValueError(key)
    rows = conn.execute(_q(f"select {key}, id from companies where {key} is not null")).fetchall()  # noqa: S608
    return {str(k): v for k, v in rows}


# ---------------------------------------------------------------- point-in-time tables (write only)

_FUND_COLS = ("company_id", "period_end", "fiscal_label", "filed_at", *FUNDAMENTAL_COLUMNS, "currency", "source")


def insert_fundamentals(conn: Conn, rows: Sequence[FundamentalsRow]) -> None:
    upd = _set_excluded(c for c in _FUND_COLS if c not in ("company_id", "period_end", "filed_at"))
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "fundamentals_q", _FUND_COLS, f"on conflict (company_id, period_end, filed_at) do update set {upd}"
            ),
            [r.model_dump() for r in rows],
        )


_OWN_COLS = (
    "company_id",
    "quarter_end",
    "filed_at",
    "inst_holders",
    "inst_pct",
    "fii_pct",
    "dii_pct",
    "promoter_pct",
    "promoter_pledged_pct",
    "source",
)


def upsert_ownership(conn: Conn, rows: Sequence[OwnershipRow]) -> None:
    upd = _set_excluded(c for c in _OWN_COLS if c not in ("company_id", "quarter_end"))
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "ownership_q",
                _OWN_COLS,
                f"on conflict (company_id, quarter_end) do update set {upd} "
                "where excluded.filed_at > ownership_q.filed_at",
            ),
            [r.model_dump() for r in rows],
        )


_INSIDER_COLS = (
    "company_id",
    "event_date",
    "filed_at",
    "person",
    "role",
    "kind",
    "shares",
    "value",
    "currency",
    "planned",
    "source_url",
)


def insert_insider_events(conn: Conn, rows: Sequence[InsiderEvent]) -> None:
    """Rows already stored (same company, person, date, kind, shares, value, source) are skipped by a unique
    index."""
    with conn.cursor() as cur:
        cur.executemany(
            _insert("insider_events", _INSIDER_COLS, "on conflict do nothing"),
            [r.model_dump(include=set(_INSIDER_COLS)) for r in rows],
        )


_CORP_COLS = ("company_id", "event_date", "filed_at", "kind", "detail", "source_url")


def insert_corp_events(conn: Conn, rows: Sequence[CorpEvent]) -> None:
    """Rows already stored (same company, kind, date, source) are skipped by a unique index."""
    with conn.cursor() as cur:
        cur.executemany(
            _insert("corp_events", _CORP_COLS, "on conflict do nothing"),
            _jsonb_rows(rows, ["detail"], include=_CORP_COLS),
        )


# ---------------------------------------------------------------- prices


def upsert_prices(conn: Conn, rows: Sequence[PriceW]) -> None:
    cols = ("company_id", "week_end", "close", "adj_close", "volume", "source")
    with conn.cursor() as cur:
        cur.executemany(
            _insert("prices_w", cols, f"on conflict (company_id, week_end) do update set {_set_excluded(cols[2:])}"),
            [r.model_dump() for r in rows],
        )


def upsert_benchmarks(conn: Conn, rows: Sequence[BenchmarkW]) -> None:
    cols = ("symbol", "week_end", "close")
    with conn.cursor() as cur:
        cur.executemany(
            _insert("benchmarks_w", cols, "on conflict (symbol, week_end) do update set close = excluded.close"),
            [r.model_dump() for r in rows],
        )


# ---------------------------------------------------------------- weekly outputs


def _jsonb_rows(
    rows: Sequence[Any], json_cols: Sequence[str], include: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        d = r.model_dump(include=None if include is None else set(include))
        for c in json_cols:
            d[c] = Jsonb(d[c])
        out.append(d)
    return out


def upsert_signal_values(conn: Conn, rows: Sequence[SignalValue]) -> None:
    cols = ("company_id", "week_end", "signal_id", "fired", "strength", "inputs")
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "signal_values",
                cols,
                f"on conflict (company_id, week_end, signal_id) do update set {_set_excluded(cols[3:])}",
            ),
            _jsonb_rows(rows, ["inputs"]),
        )


def upsert_redflag_values(conn: Conn, rows: Sequence[RedflagValue]) -> None:
    cols = ("company_id", "week_end", "flag_id", "hard", "inputs")
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "redflag_values",
                cols,
                f"on conflict (company_id, week_end, flag_id) do update set {_set_excluded(cols[3:])}",
            ),
            _jsonb_rows(rows, ["inputs"]),
        )


def upsert_context_values(conn: Conn, rows: Sequence[ContextValue]) -> None:
    cols = ("company_id", "week_end", "metric_id", "value", "pct", "inputs")
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "context_values",
                cols,
                f"on conflict (company_id, week_end, metric_id) do update set {_set_excluded(cols[3:])}",
            ),
            _jsonb_rows(rows, ["inputs"]),
        )


def upsert_scores(conn: Conn, rows: Sequence[Score]) -> None:
    cols = ("company_id", "week_end", "evidence", "gap", "families", "bucket", "weights_version")
    with conn.cursor() as cur:
        cur.executemany(
            _insert("scores", cols, f"on conflict (company_id, week_end) do update set {_set_excluded(cols[2:])}"),
            [r.model_dump() for r in rows],
        )


# ---------------------------------------------------------------- weights, lab


def insert_weights_version(conn: Conn, w: WeightsVersion) -> bool:
    """Weights versions are immutable once written; returns False if the version already exists."""
    d = w.model_dump()
    d["weights"] = Jsonb(d["weights"])
    cur = conn.execute(
        _insert(
            "weights_versions",
            ("version", "weights", "reason", "approved_by", "approved_at"),
            "on conflict (version) do nothing",
        ),
        d,
    )
    return cur.rowcount == 1


def insert_lab_results(conn: Conn, rows: Sequence[LabResult]) -> None:
    cols = tuple(LabResult.model_fields)
    with conn.cursor() as cur:
        cur.executemany(_insert("lab_results", cols, ""), [r.model_dump() for r in rows])


# ---------------------------------------------------------------- operations


def ensure_sources(conn: Conn, sources: Iterable[str]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            _q("insert into source_health (source) values (%(s)s) on conflict (source) do nothing"),
            [{"s": s} for s in sources],
        )


def mark_source_success(conn: Conn, source: str, at: datetime | None = None) -> None:
    conn.execute(
        _q(
            "insert into source_health (source, last_success, last_error, stale) values (%(s)s, %(t)s, null, false) "
            "on conflict (source) do update set last_success = excluded.last_success, last_error = null, stale = false"
        ),
        {"s": source, "t": at or datetime.now(UTC)},
    )


def mark_source_error(conn: Conn, source: str, error: str, stale: bool) -> None:
    conn.execute(
        _q(
            "insert into source_health (source, last_error, stale) values (%(s)s, %(e)s, %(st)s) "
            "on conflict (source) do update set last_error = excluded.last_error, stale = excluded.stale"
        ),
        {"s": source, "e": error[:2000], "st": stale},
    )


def source_health(conn: Conn) -> list[SourceHealth]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_q("select source, last_success, last_error, stale from source_health order by source"))
        return [SourceHealth(**r) for r in cur.fetchall()]


def start_run(conn: Conn, kind: str) -> UUID:
    row = conn.execute(_q("insert into runs (kind) values (%(k)s) returning id"), {"k": kind}).fetchone()
    assert row is not None
    run_id: UUID = row[0]
    return run_id


def finish_run(conn: Conn, run_id: UUID, status: str, stats: dict[str, Any], error: str | None = None) -> None:
    if status not in ("ok", "failed", "partial"):
        raise ValueError(status)
    conn.execute(
        _q("update runs set finished_at = now(), status = %(st)s, stats = %(stats)s, error = %(e)s where id = %(id)s"),
        {"st": status, "stats": Jsonb(stats), "e": error, "id": run_id},
    )


def record_llm_call(conn: Conn, call: LlmCall) -> None:
    cols = tuple(LlmCall.model_fields)
    conn.execute(_insert("llm_calls", cols, ""), call.model_dump())
