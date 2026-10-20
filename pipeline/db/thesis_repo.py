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


def scored(conn: Conn, week: date) -> int:
    """How many companies have a score for the week (0: the scoring run didn't finish)."""
    row = conn.execute(_q("select count(*) from scores where week_end = %s"), (week,)).fetchone()
    return int(row[0]) if row else 0


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
    """Counterparty links of the company whose fact was published before the cutoff (the counterparty graph)."""
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


def research_entries(conn: Conn, week: date) -> list[UUID]:
    """Companies with an open manual research entry (no card yet) made in `week` or before, oldest entry first (the
    queue packs them after the shortlist)."""
    rows = _rows(conn, "select company_id, min(created_week) as first_week, min(updated_at) as first_at from theses "
                       "where author = 'manual' and state = 'research' and card_md = '' and created_week <= %s "
                       "group by company_id order by first_week, first_at, company_id", (week,))  # fmt: skip
    return [r["company_id"] for r in rows]


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
    replaced whole, kill criteria included; one Manzoor already moved on is left alone. Returns (id, written).

    A manual research entry of the company (the web app's Research button: author `manual`, no card yet, made in
    this week or before) is filled in place when the week has no generated card of the company yet: the same row
    takes the card, its author, validation and week, so its link stays the same and the next run of the same card
    updates it through the unique index like any generated card (idempotent, M6-03; docs/SPEC_ISSUES.md 35)."""
    params = {
        "c": company_id,
        "md": card_md,
        "card": Jsonb(card_json),
        "pack": Jsonb(pack),
        "a": author,
        "v": Jsonb(validation),
        "w": week,
    }
    filled = conn.execute(
        _q(
            "update theses set author = %(a)s, card_md = %(md)s, card_json = %(card)s, evidence_pack = %(pack)s, "
            "validation = %(v)s, created_week = %(w)s, updated_at = now() where id = (select e.id from theses e "
            "where e.company_id = %(c)s and e.author = 'manual' and e.state = 'research' and e.card_md = '' "
            "and e.created_week <= %(w)s order by e.created_week, e.updated_at, e.id limit 1) "
            "and not exists (select 1 from theses g where g.company_id = %(c)s and g.created_week = %(w)s "
            "and g.author in ('routine', 'fallback')) returning id"
        ),
        params,
    ).fetchone()
    row = filled
    if row is None:
        row = conn.execute(
            _q(
                "insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, "
                "created_week) values (%(c)s, 'research', %(md)s, %(card)s, %(pack)s, %(a)s, %(v)s, %(w)s) "
                "on conflict (company_id, created_week) where author in ('routine', 'fallback') do update set "
                "card_md = excluded.card_md, card_json = excluded.card_json, evidence_pack = excluded.evidence_pack, "
                "author = excluded.author, validation = excluded.validation, updated_at = now() "
                "where theses.state = 'research' returning id"
            ),
            params,
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
    """triggered_week is the week the criterion last went from not met to met: a criterion that clears and triggers
    again gets its new week, so that week's digest lists it (M6 review R1-F10)."""
    conn.execute(
        _q(
            "update kill_criteria set triggered_week = case when %(status)s = 'triggered' and status is distinct "
            "from 'triggered' then %(week)s else triggered_week end, status = %(status)s, last_value = %(value)s, "
            "last_checked = %(checked)s where id = %(id)s"
        ),  # fmt: skip
        {"status": status, "week": triggered_week, "value": value, "checked": checked, "id": criterion_id},
    )


def move_to_review(conn: Conn, thesis_id: UUID) -> None:
    conn.execute(
        _q("update theses set state = 'review', updated_at = now() where id = %s and state = any(%s)"),
        (thesis_id, list(MONITORED)),
    )


# ---------------------------------------------------------------- the digest's other inputs


def previous_scored_week(conn: Conn, week: date) -> date | None:
    row = conn.execute(_q("select max(week_end) from scores where week_end < %s"), (week,)).fetchone()
    return None if row is None else row[0]


def funnel(conn: Conn, week: date, min_evidence: Decimal, min_families: int) -> list[dict[str, Any]]:
    """The digest's funnel per market (overhaul PR 5): companies scored, the stage (Evidence >= min_evidence), the
    Candidate bucket, the week's shortlist (new candidates), and the stage names with fewer than min_families families
    (Evidence capped)."""
    return _rows(
        conn,
        "select c.market, count(*) as scored, count(*) filter (where s.evidence >= %(ev)s) as stage, "
        "count(*) filter (where s.bucket = 'candidate') as candidates, "
        "count(l.company_id) as shortlisted, "
        "count(*) filter (where s.evidence >= %(ev)s and cardinality(s.families) < %(fam)s) as one_family "
        "from scores s join companies c on c.id = s.company_id "
        "left join shortlists l on l.week_end = s.week_end and l.company_id = s.company_id where s.week_end = %(w)s "
        "group by c.market order by c.market = 'us' desc, c.market",
        {"w": week, "ev": min_evidence, "fam": min_families},
    )


def bucket_company_ids(conn: Conn, weeks: Sequence[date], buckets: Sequence[str]) -> set[UUID]:
    rows = conn.execute(_q("select distinct company_id from scores where week_end = any(%s) and bucket = any(%s)"),
                        (list(weeks), list(buckets))).fetchall()  # fmt: skip
    return {r[0] for r in rows}


def scores_of(conn: Conn, company_ids: Sequence[UUID], weeks: Sequence[date]) -> list[dict[str, Any]]:
    return _rows(conn, "select company_id, week_end, evidence, gap, families, bucket from scores "
                       "where company_id = any(%s::uuid[]) and week_end = any(%s)",
                 (list(company_ids), list(weeks)))  # fmt: skip


def fired_signals_of(conn: Conn, company_ids: Sequence[UUID], weeks: Sequence[date]) -> list[dict[str, Any]]:
    return _rows(conn, "select company_id, week_end, signal_id from signal_values where fired "
                       "and company_id = any(%s::uuid[]) and week_end = any(%s)",
                 (list(company_ids), list(weeks)))  # fmt: skip


def fired_flags_of(conn: Conn, company_ids: Sequence[UUID], weeks: Sequence[date]) -> list[dict[str, Any]]:
    """Red flags that fired (a stored row may also be `unknown`: missing inputs never fire a flag, §4.6)."""
    return _rows(conn, "select company_id, week_end, flag_id, hard from redflag_values "
                       "where inputs ->> 'status' = 'fired' and company_id = any(%s::uuid[]) and week_end = any(%s)",
                 (list(company_ids), list(weeks)))  # fmt: skip


def cards_to_decide(conn: Conn) -> list[dict[str, Any]]:
    """The digest's To do: generated cards still in research (to accept or dismiss). Company names only."""
    return _rows(conn, "select distinct c.id as company_id, c.name, c.market, c.ticker, c.nse_symbol "
                       "from theses t join companies c on c.id = t.company_id where t.state = 'research' "
                       "and t.author = any(%s) and t.card_md <> '' order by c.name", (list(GENERATED),))  # fmt: skip


def in_review(conn: Conn, week: date) -> list[dict[str, Any]]:
    """The digest's To do: theses in review (a kill criterion moved them there) or whose review date has come.
    Company names only."""
    return _rows(
        conn,
        "select distinct c.id as company_id, c.name, c.market, c.ticker, c.nse_symbol from theses t "
        "join companies c on c.id = t.company_id where t.state = 'review' "
        "or (t.state = any(%s) and t.next_review is not null and t.next_review <= %s) order by c.name",
        (list(MONITORED), week),
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
