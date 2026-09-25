"""Point-in-time reads (BRIEF §3 "Point-in-time rule", §4.1.4, §8 M1-02). PROTECTED (BRIEF Appendix D).

The only module allowed to read fundamentals_q, ownership_q, insider_events and corp_events (guard pit_rule).
Every read goes through `as_of(W)`: rows whose `filed_at` is after the cutoff do not exist for the caller.

    snap = as_of(date(2025, 3, 28))           # week ending Friday 2025-03-28
    rows = snap.fundamentals(conn)            # latest version of each company-quarter filed by the cutoff

Cutoff rules:
- a `date` W means "the end of W in UTC": rows with filed_at < W+1 day 00:00 UTC are visible;
- a timezone-aware `datetime` T means "the instant T": rows with filed_at <= T are visible;
- anything else (naive datetimes, strings) is rejected, so a caller can't widen the window by accident.
There is no option to skip the filter. The Signal Lab (M8) uses `select_as_of` on its own panel with the same rule.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from pipeline.db.models import FUNDAMENTAL_COLUMNS, CorpEvent, FactRow, FundamentalsRow, InsiderEvent, OwnershipRow

_FUNDAMENTALS_COLS = ", ".join(
    ("company_id", "period_end", "fiscal_label", "filed_at", *FUNDAMENTAL_COLUMNS, "currency", "source")
)


def cutoff_for(w: date | datetime) -> datetime:
    """Exclusive upper bound on filed_at for a week end (date) or an instant (aware datetime)."""
    if isinstance(w, datetime):  # check first: datetime is a subclass of date
        if w.tzinfo is None or w.utcoffset() is None:
            raise ValueError("as_of needs a timezone-aware datetime (naive times are ambiguous)")
        return w.astimezone(UTC) + timedelta(microseconds=1)
    if isinstance(w, date):
        return datetime.combine(w + timedelta(days=1), time(0, 0), tzinfo=UTC)
    raise TypeError(f"as_of takes a date or an aware datetime, not {type(w).__name__}")


def select_as_of[T](
    rows: Iterable[T], cutoff: datetime, key: Callable[[T], Hashable], filed_at: Callable[[T], datetime]
) -> list[T]:
    """Pure-Python form of the rule: drop rows filed at/after `cutoff`, keep the latest version per key."""
    best: dict[Hashable, T] = {}
    for r in rows:
        f = filed_at(r)
        if f >= cutoff:
            continue
        k = key(r)
        if k not in best or filed_at(best[k]) < f:
            best[k] = r
    return list(best.values())


@dataclass(frozen=True)
class AsOf:
    """A point-in-time view. Build it with as_of(); the cutoff can't be changed afterwards."""

    cutoff: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.cutoff, datetime) or self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("AsOf.cutoff must be a timezone-aware datetime; build it with as_of()")

    def fundamentals(
        self, conn: psycopg.Connection[Any], company_ids: Sequence[UUID] | None = None
    ) -> list[FundamentalsRow]:
        """Latest version of every company-quarter filed before the cutoff."""
        sql = (
            f"select distinct on (company_id, period_end) {_FUNDAMENTALS_COLS} from fundamentals_q "  # noqa: S608
            "where filed_at < %(cutoff)s and (%(ids)s::uuid[] is null or company_id = any(%(ids)s::uuid[])) "
            "order by company_id, period_end, filed_at desc"
        )
        return [FundamentalsRow(**r) for r in self._fetch(conn, sql, company_ids)]

    def fundamental_versions(
        self, conn: psycopg.Connection[Any], company_ids: Sequence[UUID] | None = None
    ) -> list[FundamentalsRow]:
        """Every version of every company-quarter filed before the cutoff, oldest filing first. For histories that
        must themselves be point-in-time (C1's weekly multiples, BRIEF §4.7): the version current at an earlier
        week is select_as_of() over these rows with that week's cutoff."""
        sql = (
            f"select {_FUNDAMENTALS_COLS} from fundamentals_q "  # noqa: S608
            "where filed_at < %(cutoff)s and (%(ids)s::uuid[] is null or company_id = any(%(ids)s::uuid[])) "
            "order by company_id, period_end, filed_at"
        )
        return [FundamentalsRow(**r) for r in self._fetch(conn, sql, company_ids)]

    def facts(
        self, conn: psycopg.Connection[Any], company_ids: Sequence[UUID] | None = None, since: date | None = None
    ) -> list[FactRow]:
        """Verified text facts (Appendix F) whose document was published before the cutoff; `since` bounds as_of."""
        sql = (
            "select f.company_id, f.fact_type, f.subject, f.subject_key, f.value_num, f.unit, f.period_end, f.as_of, "
            "f.counterparty, d.published_at from facts f join documents d on d.id = f.document_id "
            "where d.published_at < %(cutoff)s and f.verification_status = 'verified' "
            "and (%(ids)s::uuid[] is null or f.company_id = any(%(ids)s::uuid[])) "
            "and (%(since)s::date is null or f.as_of >= %(since)s::date) "
            "order by f.company_id, f.as_of"
        )
        return [FactRow(**r) for r in self._fetch(conn, sql, company_ids, since)]

    def ownership(self, conn: psycopg.Connection[Any], company_ids: Sequence[UUID] | None = None) -> list[OwnershipRow]:
        sql = (
            "select company_id, quarter_end, filed_at, inst_holders, inst_pct, fii_pct, dii_pct, promoter_pct, "
            "promoter_pledged_pct, source from ownership_q "
            "where filed_at < %(cutoff)s and (%(ids)s::uuid[] is null or company_id = any(%(ids)s::uuid[])) "
            "order by company_id, quarter_end"
        )
        return [OwnershipRow(**r) for r in self._fetch(conn, sql, company_ids)]

    def insider_events(
        self, conn: psycopg.Connection[Any], company_ids: Sequence[UUID] | None = None, since: date | None = None
    ) -> list[InsiderEvent]:
        sql = (
            "select id, company_id, event_date, filed_at, person, role, kind, shares, value, currency, planned, "
            "source_url from insider_events "
            "where filed_at < %(cutoff)s and (%(ids)s::uuid[] is null or company_id = any(%(ids)s::uuid[])) "
            "and (%(since)s::date is null or event_date >= %(since)s::date) "
            "order by company_id, event_date, filed_at"
        )
        return [InsiderEvent(**r) for r in self._fetch(conn, sql, company_ids, since)]

    def corp_events(
        self, conn: psycopg.Connection[Any], company_ids: Sequence[UUID] | None = None, since: date | None = None
    ) -> list[CorpEvent]:
        sql = (
            "select id, company_id, event_date, filed_at, kind, detail, source_url from corp_events "
            "where filed_at < %(cutoff)s and (%(ids)s::uuid[] is null or company_id = any(%(ids)s::uuid[])) "
            "and (%(since)s::date is null or event_date >= %(since)s::date) "
            "order by company_id, event_date, filed_at"
        )
        return [CorpEvent(**r) for r in self._fetch(conn, sql, company_ids, since)]

    def _fetch(
        self,
        conn: psycopg.Connection[Any],
        sql: str,
        company_ids: Sequence[UUID] | None,
        since: date | None = None,
    ) -> list[dict[str, Any]]:
        ids = None if company_ids is None else [UUID(str(c)) for c in company_ids]  # rejects non-UUID input
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql.encode("utf-8"), {"cutoff": self.cutoff, "ids": ids, "since": since})
            return list(cur.fetchall())


def as_of(w: date | datetime) -> AsOf:
    """The one entry point for point-in-time reads (BRIEF §3)."""
    return AsOf(cutoff_for(w))
