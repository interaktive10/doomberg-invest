"""Repositories for the thesis engine and the weekly digest (M6; BRIEF §4.9, §4.12, migration 0010).

Reads of the weekly outputs (scores, signal_values, redflag_values, context_values, shortlists) and of the text
facts are keyed by the week; the facts a pack cites are the verified ones whose document was published before the
week's cutoff (the pipeline.db.pit rule). Point-in-time tables (fundamentals_q, ownership_q, insider_events,
corp_events) are read through pipeline.db.pit only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pipeline.db.models import ContextValue, RedflagValue, Score, SignalValue

Conn = psycopg.Connection[Any]
GENERATED = ("routine", "fallback")
MONITORED = ("thesis", "position")  # states whose kill criteria are evaluated (§1.8: monitoring starts at Thesis)


def _q(sql: str) -> bytes:
    return sql.encode("utf-8")


def _rows(conn: Conn, sql: str, params: Sequence[Any] | dict[str, Any]) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_q(sql), params)
        return list(cur.fetchall())


# ---------------------------------------------------------------- the week's outputs


def shortlist(conn: Conn, week: date) -> list[dict[str, Any]]:
    return _rows(conn, "select company_id, rank, evidence, gap from shortlists where week_end = %s order by rank",
                 (week,))  # fmt: skip


def week_score(conn: Conn, company_id: UUID, week: date) -> Score | None:
    rows = _rows(conn, "select company_id, week_end, evidence, gap, families, bucket, weights_version from scores "
                       "where company_id = %s and week_end = %s", (company_id, week))  # fmt: skip
    return Score(**rows[0]) if rows else None


def week_signals(conn: Conn, company_id: UUID, week: date) -> list[SignalValue]:
    rows = _rows(conn, "select company_id, week_end, signal_id, fired, strength, inputs from signal_values "
                       "where company_id = %s and week_end = %s order by signal_id", (company_id, week))  # fmt: skip
    return [SignalValue(**r) for r in rows]


def week_flags(conn: Conn, company_id: UUID, week: date) -> list[RedflagValue]:
    rows = _rows(conn, "select company_id, week_end, flag_id, hard, inputs from redflag_values "
                       "where company_id = %s and week_end = %s order by flag_id", (company_id, week))  # fmt: skip
    return [RedflagValue(**r) for r in rows]


def week_context(conn: Conn, company_id: UUID, week: date) -> list[ContextValue]:
    rows = _rows(conn, "select company_id, week_end, metric_id, value, pct, inputs from context_values "
                       "where company_id = %s and week_end = %s order by metric_id", (company_id, week))  # fmt: skip
    return [ContextValue(**r) for r in rows]


def latest_signals(conn: Conn, company_id: UUID, until: date) -> tuple[date | None, list[SignalValue]]:
    """The company's signal rows of its latest scored week on or before `until` (kill criteria on signals)."""
    rows = _rows(conn, "select max(week_end) as w from scores where company_id = %s and week_end <= %s",
                 (company_id, until))  # fmt: skip
    week = rows[0]["w"] if rows else None
    return (week, week_signals(conn, company_id, week)) if week is not None else (None, [])


# ---------------------------------------------------------------- facts and links as of a cutoff


def pack_facts(conn: Conn, company_id: UUID, cutoff: datetime, limit: int) -> list[dict[str, Any]]:
    """The newest verified facts whose document was published before the cutoff (the pit.AsOf.facts rule)."""
    return _rows(
        conn,
        "select f.id, f.fact_type, f.subject, f.subject_key, f.value_num, f.value_low, f.value_high, f.unit, "
        "f.currency, f.period_label, f.period_end, f.as_of, f.counterparty, f.quote, d.url, d.kind, d.published_at "
        "from facts f join documents d on d.id = f.document_id where f.company_id = %s "
        "and f.verification_status = 'verified' and d.published_at < %s "
        "order by d.published_at desc, f.as_of desc, f.id limit %s",
        (company_id, cutoff, limit),
    )


def pack_links(conn: Conn, company_id: UUID, cutoff: datetime) -> list[dict[str, Any]]:
    """Counterparty links of the company whose fact was published before the cutoff (the Capex Desk graph)."""
    return _rows(
        conn,
        "select e.name as entity, e.kind as entity_kind, l.relation, l.fact_id from links l "
        "join entities e on e.id = l.to_entity_id join facts f on f.id = l.fact_id "
        "join documents d on d.id = f.document_id where l.from_company_id = %s and d.published_at < %s "
        "order by e.name, l.relation",
        (company_id, cutoff),
    )


def confirmed_categories(conn: Conn, company_id: UUID) -> list[str]:
    rows = _rows(conn, "select category from capex_memberships where company_id = %s and status = 'confirmed' "
                       "order by category", (company_id,))  # fmt: skip
    return [str(r["category"]) for r in rows]


# ---------------------------------------------------------------- theses and kill criteria


def generated_theses(conn: Conn, week: date) -> list[dict[str, Any]]:
    return _rows(conn, "select id, company_id, state, author from theses where created_week = %s "
                       "and author = any(%s) order by company_id", (week, list(GENERATED)))  # fmt: skip


def upsert_generated_thesis(
    conn: Conn,
    company_id: UUID,
    week: date,
    author: str,
    card_md: str,
    card_json: dict[str, Any],
    pack: dict[str, Any],
    validation: dict[str, Any],
    criteria: Sequence[dict[str, Any]],
) -> tuple[UUID, bool]:
    """One generated card per company and week (migration 0010's unique index). A card still in `research` is
    replaced whole, kill criteria included; one Manzoor already moved on is left alone. Returns (id, written)."""
    row = conn.execute(
        _q(
            "insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, "
            "created_week) values (%(c)s, 'research', %(md)s, %(card)s, %(pack)s, %(a)s, %(v)s, %(w)s) "
            "on conflict (company_id, created_week) where author in ('routine', 'fallback') do update set "
            "card_md = excluded.card_md, card_json = excluded.card_json, evidence_pack = excluded.evidence_pack, "
            "author = excluded.author, validation = excluded.validation, updated_at = now() "
            "where theses.state = 'research' returning id"
        ),
        {
            "c": company_id,
            "md": card_md,
            "card": Jsonb(card_json),
            "pack": Jsonb(pack),
            "a": author,
            "v": Jsonb(validation),
            "w": week,
        },  # fmt: skip
    ).fetchone()
    if row is None:
        existing = conn.execute(
            _q("select id from theses where company_id = %s and created_week = %s and author = any(%s)"),
            (company_id, week, list(GENERATED)),
        ).fetchone()
        assert existing is not None
        return existing[0], False
    thesis_id: UUID = row[0]
    conn.execute(_q("delete from kill_criteria where thesis_id = %s"), (thesis_id,))
    with conn.cursor() as cur:
        cur.executemany(
            _q(
                "insert into kill_criteria (thesis_id, metric, operator, threshold, check_after, baseline, why) "
                "values (%(t)s, %(metric)s, %(operator)s, %(threshold)s, %(check_after)s, %(baseline)s, %(why)s)"
            ),
            [{"t": thesis_id, **k} for k in criteria],
        )
    return thesis_id, True


def monitored_theses(conn: Conn) -> list[dict[str, Any]]:
    return _rows(conn, "select t.id, t.company_id, t.state, c.market, c.name from theses t "
                       "join companies c on c.id = t.company_id where t.state = any(%s) order by c.name",
                 (list(MONITORED),))  # fmt: skip


def criteria_of(conn: Conn, thesis_id: UUID) -> list[dict[str, Any]]:
    return _rows(conn, "select id, metric, operator, threshold, check_after, status, last_value, last_checked, "
                       "baseline, triggered_week from kill_criteria where thesis_id = %s order by metric, id",
                 (thesis_id,))  # fmt: skip


def record_check(
    conn: Conn, criterion_id: UUID, status: str, value: Decimal | None, checked: date, triggered_week: date | None
) -> None:
    conn.execute(
        _q(
            "update kill_criteria set status = %s, last_value = %s, last_checked = %s, "
            "triggered_week = coalesce(triggered_week, %s) where id = %s"
        ),  # fmt: skip
        (status, value, checked, triggered_week, criterion_id),
    )


def move_to_review(conn: Conn, thesis_id: UUID) -> None:
    conn.execute(
        _q("update theses set state = 'review', updated_at = now() where id = %s and state = any(%s)"),
        (thesis_id, list(MONITORED)),
    )


def triggered_in_week(conn: Conn, week: date) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select t.id as thesis_id, c.id as company_id, c.name, c.market, c.ticker, c.nse_symbol, k.metric, "
        "k.operator, k.threshold, k.last_value from kill_criteria k join theses t on t.id = k.thesis_id "
        "join companies c on c.id = t.company_id where k.triggered_week = %s order by c.name, k.metric",
        (week,),
    )


def reviews_due(conn: Conn, week: date) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select t.id as thesis_id, c.id as company_id, c.name, c.market, c.ticker, c.nse_symbol, t.state, "
        "t.next_review from theses t join companies c on c.id = t.company_id "
        "where (t.state = 'review') or (t.state = any(%s) and t.next_review is not null and t.next_review <= %s) "
        "order by c.name",
        (list(MONITORED), week),
    )


# ---------------------------------------------------------------- the digest's other inputs


def capex_brief(conn: Conn, week: date) -> str | None:
    rows = _rows(conn, "select body_md from capex_briefs where week_end = %s", (week,))
    return str(rows[0]["body_md"]) if rows else None


def llm_use(conn: Conn, since: datetime, until: datetime) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select provider, count(*) as calls, count(*) filter (where ok) as ok, "
        "count(*) filter (where not ok and error like '%%: 429%%') as rate_limited, "  # RateLimited: '<provider>: 429'
        "coalesce(sum(tokens_in), 0) as tokens_in, coalesce(sum(tokens_out), 0) as tokens_out "
        "from llm_calls where created_at >= %s and created_at < %s group by provider order by provider",
        (since, until),
    )


def lab_runs(conn: Conn, since: datetime, until: datetime) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select signal_id, market, horizon_m, period, n, excess_mean, t_nw, run_at from lab_results "
        "where run_at >= %s and run_at < %s order by signal_id, horizon_m, period",
        (since, until),
    )


def upsert_digest(conn: Conn, week: date, title: str, body_md: str, issue_number: int | None) -> None:
    conn.execute(
        _q(
            "insert into digests (week_end, title, body_md, issue_number) values (%s, %s, %s, %s) "
            "on conflict (week_end) do update set title = excluded.title, body_md = excluded.body_md, "
            "issue_number = coalesce(excluded.issue_number, digests.issue_number), updated_at = now()"
        ),
        (week, title, body_md, issue_number),
    )
