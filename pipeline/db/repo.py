"""Repositories: typed writes (and non-point-in-time reads) for the pipeline (BRIEF §2.3 `db/repo.py`, §8 M1).

Point-in-time tables (fundamentals_q, ownership_q, insider_events, corp_events) are written here but read only
through pipeline.db.pit.as_of(). Writes are idempotent so a re-run of a weekly job doesn't duplicate rows:
- fundamentals_q: keyed by (company, period_end, filed_at). A restatement has a later filed_at, so it's a new row
  and the old version stays (BRIEF §4.1.4). Re-ingesting the same filing overwrites that version only.
- ownership_q: keyed by (company, quarter_end, filed_at) (migration 0008, M4 review R1-F2): a revised pattern is a
  new version and as_of() picks the latest version filed by its cutoff. Re-ingesting the same filing overwrites that
  version.
- insider_events / corp_events: unique natural-key indexes (db/migrations/0002) make re-inserts no-ops.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pipeline.db.models import (
    FUNDAMENTAL_COLUMNS,
    MANUAL_OWNERSHIP,
    BenchmarkW,
    Company,
    ContextValue,
    CorpEvent,
    FilingRow,
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


_METADATA = ("sector", "industry", "sic", "fiscal_year_end")  # filled by the weekly runs, not by listings
SNAPSHOT_OUT = {"us": "not in the SEC NYSE/Nasdaq snapshot", "in": "not in the NSE EQ snapshot"}
_DECISION = ("in_universe", "excluded_reason")


def _keep_decision(col: str) -> str:
    """A re-seed doesn't undo the weekly run's universe decision (review F9: the quarterly seed re-admitted SPACs and
    funds right before the 13F step). It re-admits only a company the snapshot step had moved out (listed again)."""
    return (
        f"{col} = case when companies.excluded_reason is null or companies.excluded_reason = %(snapshot_out)s "
        f"then excluded.{col} else companies.{col} end"
    )


def upsert_us_companies(conn: Conn, companies: Sequence[Company]) -> None:
    """US companies are keyed by CIK. The listing snapshot has no SIC/sector/industry/fiscal year: a re-seed keeps
    the values the weekly run stored rather than blanking them, and keeps its universe decision."""
    if any(c.market != "us" or not c.cik for c in companies):
        raise ValueError("upsert_us_companies needs market='us' rows with a cik")
    upd = (
        ", ".join(
            f"{c} = coalesce(excluded.{c}, companies.{c})"
            if c in _METADATA
            else _keep_decision(c)
            if c in _DECISION
            else f"{c} = excluded.{c}"
            for c in _COMPANY_COLS
            if c not in ("market", "cik")
        )
        + ", updated_at = now()"
    )
    rows = [{**c.model_dump(include=set(_COMPANY_COLS)), "snapshot_out": SNAPSHOT_OUT["us"]} for c in companies]
    with conn.cursor() as cur:
        cur.executemany(_insert("companies", _COMPANY_COLS, f"on conflict (cik) do update set {upd}"), rows)


def upsert_in_companies(conn: Conn, companies: Sequence[Company]) -> None:
    """Indian companies are keyed by NSE symbol. A symbol rename keeps the ISIN, so rows are re-pointed by ISIN
    first; a face-value split keeps the symbol and changes the ISIN, which the upsert on symbol handles."""
    if any(c.market != "in" or not c.nse_symbol or not c.isin for c in companies):
        raise ValueError("upsert_in_companies needs market='in' rows with nse_symbol and isin")
    rows = [{**c.model_dump(include=set(_COMPANY_COLS)), "snapshot_out": SNAPSHOT_OUT["in"]} for c in companies]
    upd = (
        ", ".join(
            f"{c} = coalesce(excluded.{c}, companies.{c})"
            if c in _METADATA
            else _keep_decision(c)
            if c in _DECISION
            else f"{c} = excluded.{c}"
            for c in _COMPANY_COLS
            if c not in ("market", "nse_symbol")
        )
        + ", updated_at = now()"
    )
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


def set_india_universe(conn: Conn, reasons: Mapping[str, str | None]) -> int:
    """India universe status by NSE symbol: a reason (e.g. an ASM/GSM listing) takes the company out, None puts it
    back. Symbols not given are left as they are (companies missing from the securities list stay out)."""
    rows = [{"sym": k, "why": v, "u": v is None} for k, v in reasons.items()]
    with conn.cursor() as cur:
        cur.executemany(
            _q(
                "update companies set in_universe = %(u)s, excluded_reason = %(why)s, updated_at = now() "
                "where market = 'in' and nse_symbol = %(sym)s "
                "and (in_universe is distinct from %(u)s or excluded_reason is distinct from %(why)s)"
            ),
            rows,
        )
        return cur.rowcount


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


def update_us_company(
    conn: Conn,
    cik: str,
    *,
    name: str | None,
    sic: str | None,
    industry: str | None,
    sector: str | None,
    fiscal_year_end: str | None,
    in_universe: bool,
    excluded_reason: str | None,
) -> None:
    """Metadata and universe status from the weekly US run (BRIEF §1.3); name is kept when not given."""
    conn.execute(
        _q(
            "update companies set name = coalesce(%(name)s, name), sic = %(sic)s, industry = %(industry)s, "
            "sector = %(sector)s, fiscal_year_end = %(fye)s, in_universe = %(u)s, excluded_reason = %(why)s, "
            "updated_at = now() where market = 'us' and cik = %(cik)s"
        ),
        {
            "name": name,
            "sic": sic,
            "industry": industry,
            "sector": sector,
            "fye": fiscal_year_end,
            "u": in_universe,
            "why": excluded_reason,
            "cik": cik,
        },  # fmt: skip
    )


def ensure_company(conn: Conn, c: Company) -> UUID:
    """Insert a US company by CIK if missing (e.g. a spin-off registrant before it lists); return its id."""
    if c.market != "us" or not c.cik:
        raise ValueError("ensure_company needs a US company with a cik")
    row = conn.execute(
        _q(
            "insert into companies (market, name, cik, ticker, in_universe, excluded_reason) "
            "values ('us', %(name)s, %(cik)s, %(ticker)s, %(u)s, %(why)s) "
            "on conflict (cik) do update set updated_at = companies.updated_at returning id"
        ),
        {"name": c.name, "cik": c.cik, "ticker": c.ticker, "u": c.in_universe, "why": c.excluded_reason},
    ).fetchone()
    assert row is not None
    cid: UUID = row[0]
    return cid


def insert_filings(conn: Conn, rows: Sequence[FilingRow]) -> None:
    """Queue filings for text extraction; an accession already queued is left as it is."""
    cols = ("company_id", "accession_no", "form_type", "items", "filed_at", "accepted_at", "period_of_report",
            "primary_doc_url", "index_url", "status")  # fmt: skip
    with conn.cursor() as cur:
        cur.executemany(
            _insert("filings", cols, "on conflict (accession_no) do nothing"), [r.model_dump() for r in rows]
        )


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


def insert_fundamentals(conn: Conn, rows: Sequence[FundamentalsRow], fill_only: bool = False) -> None:
    """Upsert row versions by (company, period_end, filed_at). fill_only (India): a stored version is never given
    fewer values, since a null in the new row keeps the stored value (review F1 on M3)."""
    cols = [c for c in _FUND_COLS if c not in ("company_id", "period_end", "filed_at")]
    if fill_only:
        upd = ", ".join(
            f"{c} = coalesce(excluded.{c}, fundamentals_q.{c})" if c in FUNDAMENTAL_COLUMNS else f"{c} = excluded.{c}"
            for c in cols
        )
    else:
        upd = _set_excluded(cols)
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "fundamentals_q", _FUND_COLS, f"on conflict (company_id, period_end, filed_at) do update set {upd}"
            ),
            [r.model_dump() for r in rows],
        )


def prune_fundamentals(conn: Conn, company_id: UUID, keep: Sequence[tuple[date, datetime]], min_period: date) -> int:
    """Delete the company's fundamentals_q versions not in `keep` (period_end, filed_at) and quarters before
    `min_period` (migration 0004; review F10). Called right after the company's rows are rewritten. An empty `keep`
    prunes nothing: a company whose facts gave no rows keeps what it had (review R3 idea)."""
    if not keep:
        return 0
    payload = Jsonb([[p.isoformat(), t.isoformat()] for p, t in keep])
    row = conn.execute(_q("select prune_fundamentals(%s, %s, %s)"), (company_id, payload, min_period)).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


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
    """One row per company, quarter and filing time: a later filing is a new version (as_of() picks the latest one
    filed by its cutoff). For the same filing time, a full row replaces anything and a manual CSV row (promoter %
    only) replaces only a manual row, so it never replaces a full one; as_of() also prefers a full version."""
    upd = _set_excluded(c for c in _OWN_COLS if c not in ("company_id", "quarter_end", "filed_at"))
    with conn.cursor() as cur:
        cur.executemany(
            _insert(
                "ownership_q",
                _OWN_COLS,
                f"on conflict (company_id, quarter_end, filed_at) do update set {upd} "
                "where excluded.source <> %(manual)s or ownership_q.source = %(manual)s",
            ),
            [{**r.model_dump(), "manual": MANUAL_OWNERSHIP} for r in rows],
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
    "amends",
    "line",
)


def insert_insider_events(conn: Conn, rows: Sequence[InsiderEvent]) -> None:
    """Rows already stored (same company, person, date, kind, shares, value, source and line) are skipped by a
    unique index."""
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


def mark_price_split(conn: Conn, company_id: UUID, week_end: date, ratio: Decimal) -> None:
    """A split a split-adjusted source showed (pipeline.prices.splits.rebased), on its first week on the new basis."""
    conn.execute(
        _q("update prices_w set split_ratio = %s where company_id = %s and week_end = %s"),
        (ratio, company_id, week_end),
    )


def priced_at(conn: Conn, company_ids: Sequence[UUID], week: date) -> set[UUID]:
    """Companies that already have a price for `week` (a re-run of the week doesn't download them again)."""
    rows = conn.execute(
        _q("select company_id from prices_w where company_id = any(%s) and week_end = %s"), (list(company_ids), week)
    ).fetchall()
    return {r[0] for r in rows}


def benchmarks_at(conn: Conn, symbols: Sequence[str], week: date) -> set[str]:
    rows = conn.execute(
        _q("select symbol from benchmarks_w where symbol = any(%s) and week_end = %s"), (list(symbols), week)
    ).fetchall()
    return {str(r[0]) for r in rows}


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


def approve_weights_version(conn: Conn, version: str, approved_by: str) -> bool:
    """Record the approval of a proposed version (approved_by was null) once it is the one in config/weights.yaml:
    that file changes only through a PR with the human-approved label (BRIEF §4.10.5)."""
    cur = conn.execute(
        _q(
            "update weights_versions set approved_by = %s, approved_at = now() "
            "where version = %s and approved_by is null"
        ),
        (approved_by, version),
    )
    return cur.rowcount == 1


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


@contextmanager
def tracked_run(conn: Conn, kind: str, source: str | None = None) -> Iterator[dict[str, Any]]:
    """A pipeline job's `runs` row (committed at once, so a crash still leaves a record). Yields a JSON-able stats
    dict for the job to fill. On success: status ok, or partial when stats["errors"] is non-empty, plus
    source_health success; everything is committed. On an exception: the job's writes are rolled back, the run is
    marked failed with the error (and the source's last_error), and the exception propagates."""
    run_id = start_run(conn, kind)
    conn.commit()
    stats: dict[str, Any] = {}
    try:
        yield stats
    except BaseException as e:
        conn.rollback()
        if source:
            mark_source_error(conn, source, f"{type(e).__name__}: {e}", stale=False)
        finish_run(conn, run_id, "failed", stats, f"{type(e).__name__}: {e}"[:2000])
        conn.commit()
        raise
    if source:
        mark_source_success(conn, source)
    finish_run(conn, run_id, "partial" if stats.get("errors") else "ok", stats)
    conn.commit()


def record_llm_call(conn: Conn, call: LlmCall) -> None:
    cols = tuple(LlmCall.model_fields)
    conn.execute(_insert("llm_calls", cols, ""), call.model_dump())


# ---------------------------------------------------------------- weekly scoring (M4)

WEEKLY_TABLES = ("signal_values", "redflag_values", "context_values", "scores", "shortlists")


def clear_week(conn: Conn, week: date) -> None:
    """A re-run of a week replaces it (a flag that cleared must not linger from the first run)."""
    for t in WEEKLY_TABLES:
        conn.execute(_q(f"delete from {t} where week_end = %s"), (week,))  # noqa: S608 — fixed table names


def prices(conn: Conn, company_ids: Sequence[UUID], start: date, end: date) -> list[PriceW]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _q(
                "select company_id, week_end, close, adj_close, volume, source, split_ratio from prices_w "
                "where company_id = any(%s) and week_end between %s and %s order by company_id, week_end"
            ),
            (list(company_ids), start, end),
        )
        return [PriceW(**r) for r in cur.fetchall()]


def benchmark_closes(conn: Conn, symbols: Sequence[str], start: date, end: date) -> list[BenchmarkW]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _q(
                "select symbol, week_end, close from benchmarks_w where symbol = any(%s) "
                "and week_end between %s and %s order by symbol, week_end"
            ),
            (list(symbols), start, end),
        )
        return [BenchmarkW(**r) for r in cur.fetchall()]


def scores_for_week(conn: Conn, week: date) -> dict[UUID, Score]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _q(
                "select company_id, week_end, evidence, gap, families, bucket, weights_version from scores "
                "where week_end = %s"
            ),
            (week,),
        )
        return {r["company_id"]: Score(**r) for r in cur.fetchall()}


def recently_shortlisted(conn: Conn, before: date, since: date) -> set[UUID]:
    rows = conn.execute(
        _q("select distinct company_id from shortlists where week_end >= %s and week_end < %s"), (since, before)
    ).fetchall()
    return {r[0] for r in rows}


def insert_shortlist(conn: Conn, week: date, rows: Sequence[tuple[UUID, Any, Any]]) -> None:
    """rows: (company_id, evidence, gap) in rank order."""
    with conn.cursor() as cur:
        cur.executemany(
            _q("insert into shortlists (week_end, company_id, rank, evidence, gap) values (%s, %s, %s, %s, %s)"),
            [(week, cid, i + 1, ev, gap) for i, (cid, ev, gap) in enumerate(rows)],
        )


def upsert_company_metrics(conn: Conn, week: date, metrics: Mapping[UUID, Mapping[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            _q(
                "insert into company_metrics (company_id, week_end, metrics) values (%s, %s, %s) "
                "on conflict (company_id) do update set week_end = excluded.week_end, metrics = excluded.metrics"
            ),
            [(cid, week, Jsonb(dict(m))) for cid, m in metrics.items()],
        )


def recent_attention(conn: Conn, week: date, since: date) -> dict[UUID, int]:
    """The latest GDELT article count per company from C4 rows in [since, week): C4 is re-queried monthly."""
    rows = conn.execute(
        _q(
            "select distinct on (company_id) company_id, (inputs->>'articles_90d')::int from context_values "
            "where metric_id = 'C4' and week_end >= %s and week_end < %s and inputs ? 'articles_90d' "
            "order by company_id, week_end desc"
        ),
        (since, week),
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def research_company_ids(conn: Conn) -> set[UUID]:
    """Companies with a live thesis or position: priced and scored even outside the universe (BRIEF §4.4)."""
    rows = conn.execute(
        _q("select distinct company_id from theses where state in ('research', 'thesis', 'position', 'review')")
    ).fetchall()
    return {r[0] for r in rows}


def prune_scoring_history(conn: Conn, week: date, keep_from: date, none_from: date) -> dict[str, int]:
    """docs/SPEC_ISSUES.md 9: signal_values keeps every row for the latest week only; older weeks keep fired rows and
    the first unfired row after a firing streak, without their inputs (the timeline needs only fired and strength).
    Unknown red flags and 'none' scores go after the latest week / `none_from`; everything before `keep_from`
    (3 years, §2.8) goes."""
    out: dict[str, int] = {}
    out["signal_values"] = conn.execute(
        _q(
            "delete from signal_values s where s.week_end < %(w)s and not s.fired and coalesce(("
            "select p.fired from signal_values p where p.company_id = s.company_id and p.signal_id = s.signal_id "
            "and p.week_end < s.week_end order by p.week_end desc limit 1), false) = false"
        ),
        {"w": week},
    ).rowcount
    out["signal_inputs_dropped"] = conn.execute(  # the timeline needs fired/strength; inputs are for this week
        _q("update signal_values set inputs = '{}' where week_end < %s and inputs <> '{}'"), (week,)
    ).rowcount
    out["redflag_values"] = conn.execute(
        _q("delete from redflag_values where week_end < %s and inputs->>'status' = 'unknown'"), (week,)
    ).rowcount
    none = conn.execute(_q("delete from scores where week_end < %s and bucket = 'none'"), (none_from,))
    out["scores"] = none.rowcount
    for t in ("signal_values", "redflag_values", "context_values", "scores", "shortlists"):
        n = conn.execute(_q(f"delete from {t} where week_end < %s"), (keep_from,)).rowcount  # noqa: S608
        out[t] = out.get(t, 0) + n
    return out
