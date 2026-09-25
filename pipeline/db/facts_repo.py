"""Repositories for the text facts and the Capex Desk (M5; BRIEF §4.5, §4.11, Appendix F.2, migration 0009).

None of these tables is a point-in-time table of the guard's pit_rule; facts are read point in time for signals
through pit.AsOf.facts (the document's publication time). Announcements are read through pit.AsOf.corp_events.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pipeline.db.models import LlmCall
from pipeline.facts.diff import Diff
from pipeline.facts.verify1 import Candidate
from pipeline.llm.providers.base import Provider
from pipeline.llm.quotas import Quotas
from pipeline.llm.router import CallRecord, Router

Conn = psycopg.Connection[Any]


def _q(sql: str) -> bytes:
    return sql.encode("utf-8")


def _rows(conn: Conn, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_q(sql), params)
        return list(cur.fetchall())


# ---------------------------------------------------------------- LLM usage


def llm_usage(conn: Conn, day: date) -> dict[str, tuple[int, int]]:
    """provider -> (requests, tokens) logged since the start of `day` (UTC), so every run shares the day's quota."""
    start = datetime.combine(day, time.min, UTC)
    sql = ("select provider, count(*) as n, coalesce(sum(coalesce(tokens_in, 0) + coalesce(tokens_out, 0)), 0) as t "
           "from llm_calls where created_at >= %s and created_at < %s group by provider")  # fmt: skip
    rows = _rows(conn, sql, (start, start + timedelta(days=1)))
    return {r["provider"]: (int(r["n"]), int(r["t"])) for r in rows}


def logged_router(conn: Conn, providers: Mapping[str, Provider], quotas: Quotas, day: date) -> Router:
    """A Router whose calls land in llm_calls (the digest's "LLM quota use") and whose day starts from what earlier
    runs spent (BRIEF §2.6 daily budgets; M6 review R1-F9)."""

    def log(r: CallRecord) -> None:
        record_llm_calls(conn, [LlmCall(**asdict(r))])

    return Router(providers, quotas, log=log, used_today=llm_usage(conn, day))


def record_llm_calls(conn: Conn, calls: Iterable[LlmCall]) -> None:
    cols = tuple(LlmCall.model_fields)
    rows = [c.model_dump() for c in calls]
    if rows:
        with conn.cursor() as cur:
            values = ", ".join(f"%({c})s" for c in cols)
            cur.executemany(_q(f"insert into llm_calls ({', '.join(cols)}) values ({values})"), rows)  # noqa: S608


# ---------------------------------------------------------------- filings and documents


def queued_accessions(conn: Conn, accessions: Sequence[str]) -> set[str]:
    rows = _rows(conn, "select accession_no from filings where accession_no = any(%s)", (list(accessions),))
    return {r["accession_no"] for r in rows}


def filings_by_status(conn: Conn, statuses: Sequence[str], limit: int = 1000) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select f.id, f.company_id, f.accession_no, f.form_type, f.items, f.filed_at, f.period_of_report, "
        "f.primary_doc_url, f.index_url, f.status from filings f where f.status = any(%s) "
        "order by f.filed_at limit %s",
        (list(statuses), limit),
    )


def set_filing_status(conn: Conn, filing_id: UUID, status: str) -> None:
    conn.execute(_q("update filings set status = %s where id = %s"), (status, filing_id))


def upsert_document(
    conn: Conn, *, company_id: UUID, kind: str, url: str, published_at: datetime, sha256: str, raw_path: str,
    filing_id: UUID | None = None, title: str | None = None, text_chars: int | None = None,
    section_map: Sequence[Mapping[str, Any]] = (), page_map: Sequence[Mapping[str, Any]] = (), status: str = "fetched",
) -> UUID:  # fmt: skip
    row = conn.execute(
        _q(
            "insert into documents (company_id, filing_id, kind, url, title, published_at, sha256, raw_path, "
            "text_chars, section_map, page_map, status) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict (url) do update set sha256 = excluded.sha256, raw_path = excluded.raw_path, "
            "text_chars = excluded.text_chars, section_map = excluded.section_map, page_map = excluded.page_map, "
            "status = excluded.status returning id"
        ),
        (
            company_id,
            filing_id,
            kind,
            url,
            title,
            published_at,
            sha256,
            raw_path,
            text_chars,
            Jsonb(list(section_map)),
            Jsonb(list(page_map)),
            status,
        ),  # fmt: skip
    ).fetchone()
    assert row is not None
    doc_id: UUID = row[0]
    return doc_id


def set_document_status(conn: Conn, document_id: UUID, status: str) -> None:
    conn.execute(_q("update documents set status = %s where id = %s"), (status, document_id))


def document_status(conn: Conn, urls: Sequence[str]) -> dict[str, tuple[UUID, str]]:
    rows = _rows(conn, "select id, url, status from documents where url = any(%s)", (list(urls),))
    return {r["url"]: (r["id"], r["status"]) for r in rows}


def deferred_documents(conn: Conn, limit: int = 1000) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select d.id, d.company_id, d.filing_id, d.kind, d.url, d.title, d.published_at from documents d "
        "where d.status = 'deferred' order by d.published_at limit %s",
        (limit,),
    )


def previous_document(conn: Conn, company_id: UUID, kind: str, before: datetime) -> dict[str, Any] | None:
    rows = _rows(
        conn,
        "select id, url, kind, published_at from documents where company_id = %s and kind = %s and published_at < %s "
        "order by published_at desc limit 1",
        (company_id, kind, before),
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------- facts, diffs, links

_FACT_COLS = ("fact_type", "subject", "subject_key", "value_num", "value_low", "value_high", "unit", "currency",
              "scale_word", "period_label", "period_start", "period_end", "as_of", "counterparty", "location", "quote",
              "char_start", "char_end", "section", "page", "xbrl_concept", "xbrl_check", "confidence",
              "verification_status", "withdrawn")  # fmt: skip


def insert_facts(conn: Conn, company_id: UUID, document_id: UUID, facts: Sequence[tuple[Candidate, str]]) -> list[UUID]:
    """Insert a document's facts (verified and needs_review). Returns their ids in order."""
    ids: list[UUID] = []
    cols = ("company_id", "document_id", *_FACT_COLS, "extraction_model", "verification_notes")
    sql = _q(f"insert into facts ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) returning id")  # noqa: S608
    for c, model in facts:
        vals = [company_id, document_id, *(getattr(c, k) for k in _FACT_COLS), model, Jsonb(c.verification_notes)]
        row = conn.execute(sql, vals).fetchone()
        assert row is not None
        ids.append(row[0])
    return ids


@dataclass(frozen=True)
class StoredFact:
    id: UUID
    company_id: UUID
    subject_key: str
    value_num: Decimal | None
    value_low: Decimal | None
    value_high: Decimal | None
    unit: str
    as_of: date


def prior_verified(
    conn: Conn, company_id: UUID, subject_key: str, as_of: date, exclude: Sequence[UUID]
) -> StoredFact | None:
    """The latest verified fact of the same company and key before (or on) `as_of`, other than `exclude`."""
    rows = _rows(
        conn,
        "select f.id, f.company_id, f.subject_key, f.value_num, f.value_low, f.value_high, f.unit, f.as_of "
        "from facts f join documents d on d.id = f.document_id where f.company_id = %s and f.subject_key = %s "
        "and f.verification_status = 'verified' and f.as_of <= %s and not (f.id = any(%s)) "
        "order by f.as_of desc, d.published_at desc, f.created_at desc limit 1",
        (company_id, subject_key, as_of, list(exclude)),
    )
    return StoredFact(**rows[0]) if rows else None


def insert_diff(conn: Conn, company_id: UUID, subject_key: str, prev_id: UUID | None, new_id: UUID, d: Diff) -> None:
    conn.execute(
        _q("insert into diffs (company_id, subject_key, prev_fact_id, new_fact_id, change_kind, delta_abs, delta_pct, "
           "computed_note) values (%s, %s, %s, %s, %s, %s, %s, %s)"),
        (company_id, subject_key, prev_id, new_id, d.change_kind, d.delta_abs, d.delta_pct, d.computed_note),
    )  # fmt: skip
    if prev_id is not None:
        conn.execute(
            _q("update facts set superseded_by = %s where id = %s and superseded_by is null"), (new_id, prev_id)
        )


def unlinked_facts(conn: Conn, limit: int = 200) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select id, company_id, fact_type, counterparty from facts where verification_status = 'verified' "
        "and counterparty is not null and counterparty_entity_id is null order by created_at limit %s",
        (limit,),
    )


def entity_pool(conn: Conn) -> list[dict[str, Any]]:
    """Link candidates: US companies (the SEC company list the universe was seeded from) and existing entities."""
    return _rows(
        conn,
        "select 'c:' || id::text as id, name, cik from companies where market = 'us' "
        "union all select 'e:' || id::text, name, cik from entities",
    )


def upsert_entity(conn: Conn, name: str, normalized: str, kind: str, cik: str | None = None) -> UUID:
    row = conn.execute(
        _q("insert into entities (name, normalized, cik, kind) values (%s, %s, %s, %s) on conflict (normalized) "
           "do update set cik = coalesce(entities.cik, excluded.cik) returning id"),
        (name, normalized, cik, kind),
    ).fetchone()  # fmt: skip
    assert row is not None
    eid: UUID = row[0]
    return eid


def link_fact(conn: Conn, fact_id: UUID, company_id: UUID, entity_id: UUID, relation: str | None) -> None:
    conn.execute(_q("update facts set counterparty_entity_id = %s where id = %s"), (entity_id, fact_id))
    if relation is not None:
        conn.execute(
            _q("insert into links (from_company_id, to_entity_id, relation, fact_id) values (%s, %s, %s, %s) "
               "on conflict (from_company_id, to_entity_id, relation) do nothing"),
            (company_id, entity_id, relation, fact_id),
        )  # fmt: skip


def insert_risk_changes(conn: Conn, rows: Sequence[Mapping[str, Any]]) -> None:
    for r in rows:
        conn.execute(
            _q("insert into risk_changes (company_id, from_document_id, to_document_id, change_kind, text_before, "
               "text_after, similarity, topic_tags, char_start, char_end) values (%(company_id)s, "
               "%(from_document_id)s, %(to_document_id)s, %(change_kind)s, %(text_before)s, %(text_after)s, "
               "%(similarity)s, %(topic_tags)s, %(char_start)s, %(char_end)s)"),
            dict(r),
        )  # fmt: skip


# ---------------------------------------------------------------- India announcement triage (P-07)


def triaged(conn: Conn, event_ids: Sequence[UUID]) -> set[UUID]:
    rows = _rows(conn, "select event_id from announcement_triage where event_id = any(%s)", (list(event_ids),))
    return {r["event_id"] for r in rows}


def insert_triage(conn: Conn, event_id: UUID, company_id: UUID, categories: Sequence[str], read_pdf: bool,
                  model: str) -> None:  # fmt: skip
    conn.execute(
        _q("insert into announcement_triage (event_id, company_id, categories, read_pdf, model) values "
           "(%s, %s, %s, %s, %s) on conflict (event_id) do nothing"),
        (event_id, company_id, list(categories), read_pdf, model),
    )  # fmt: skip


def pdfs_to_read(conn: Conn, limit: int = 100) -> list[dict[str, Any]]:
    """Triaged announcements flagged read_pdf with no document yet (the URL comes from the event, read by the caller
    through pit)."""
    return _rows(conn, "select event_id, company_id, categories from announcement_triage where read_pdf "
                       "order by created_at limit %s", (limit,))  # fmt: skip


# ---------------------------------------------------------------- Capex Desk (§4.11)


def propose_membership(
    conn: Conn, company_id: UUID, category: str, source: str, evidence: str, quote: str | None = None,
    document_id: UUID | None = None, span: tuple[int, int] | None = None, confidence: Decimal | None = None,
) -> bool:  # fmt: skip
    """A new proposal (True), or refresh the evidence of one still proposed. Decided rows are never touched."""
    row = conn.execute(
        _q(
            "insert into capex_memberships (company_id, category, source, evidence, quote, document_id, char_start, "
            "char_end, confidence) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict (company_id, category) do "
            "update set evidence = excluded.evidence, quote = excluded.quote, document_id = excluded.document_id, "
            "char_start = excluded.char_start, char_end = excluded.char_end, confidence = excluded.confidence "
            "where capex_memberships.status = 'proposed' returning (xmax = 0) as inserted"
        ),
        (
            company_id,
            category,
            source,
            evidence,
            quote,
            document_id,
            span[0] if span else None,
            span[1] if span else None,
            confidence,
        ),  # fmt: skip
    ).fetchone()
    return bool(row and row[0])


def decide_membership(conn: Conn, company_id: UUID, category: str, status: str, reason: str | None = None,
                      at: datetime | None = None) -> None:  # fmt: skip
    """Manzoor's confirmation or rejection (the web app calls this through its server action; a rejection needs a
    reason, enforced by the table). decided_at is now unless `at` is given; S11 counts a confirmation from the week
    it was made (desk.load_views)."""
    conn.execute(
        _q("update capex_memberships set status = %s, decided_at = coalesce(%s, now()), decision_reason = %s "
           "where company_id = %s and category = %s"),
        (status, at, reason, company_id, category),
    )  # fmt: skip


def memberships(conn: Conn, status: str | None = None) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select company_id, category, source, status, evidence, quote, document_id, proposed_at, decided_at "
        "from capex_memberships where (%s::text is null or status = %s) order by company_id, category",
        (status, status),
    )


def upsert_capex_inputs(conn: Conn, week: date, values: Mapping[str, tuple[Decimal | None, Mapping[str, Any]]]) -> None:
    for input_id, (value, detail) in values.items():
        conn.execute(
            _q("insert into capex_inputs (input_id, week_end, value, detail) values (%s, %s, %s, %s) "
               "on conflict (input_id, week_end) do update set value = excluded.value, detail = excluded.detail"),
            (input_id, week, value, Jsonb(dict(detail))),
        )  # fmt: skip


def capex_input_history(conn: Conn, input_id: str, since: date, until: date) -> list[tuple[date, Decimal]]:
    rows = _rows(conn, "select week_end, value from capex_inputs where input_id = %s and week_end between %s and %s "
                       "and value is not null order by week_end", (input_id, since, until))  # fmt: skip
    return [(r["week_end"], r["value"]) for r in rows]


def upsert_capex_index(conn: Conn, week: date, rows: Sequence[Mapping[str, Any]]) -> None:
    for r in rows:
        conn.execute(
            _q("insert into capex_index (category, week_end, value, direction, input_growth, inputs) values "
               "(%s, %s, %s, %s, %s, %s) on conflict (category, week_end) do update set value = excluded.value, "
               "direction = excluded.direction, input_growth = excluded.input_growth, inputs = excluded.inputs"),
            (r["category"], week, r["value"], r["direction"], r["input_growth"], Jsonb(dict(r["inputs"]))),
        )  # fmt: skip


def capex_index(conn: Conn, week: date) -> list[dict[str, Any]]:
    """The latest index row per category on or before `week`."""
    return _rows(
        conn,
        "select distinct on (category) category, week_end, value, direction, input_growth, inputs from capex_index "
        "where week_end <= %s order by category, week_end desc",
        (week,),
    )


def upsert_capex_brief(conn: Conn, week: date, body: str) -> None:
    conn.execute(
        _q("insert into capex_briefs (week_end, body_md) values (%s, %s) on conflict (week_end) do update set "
           "body_md = excluded.body_md, created_at = now()"),
        (week, body),
    )  # fmt: skip


def links(conn: Conn) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select l.from_company_id, l.to_entity_id, l.relation, l.first_seen_at, e.name as entity_name, e.cik as "
        "entity_cik from links l join entities e on e.id = l.to_entity_id",
    )


# ---------------------------------------------------------------- scope (§4.5) and the brief's queries


def latest_scored_week(conn: Conn) -> date | None:
    row = conn.execute(_q("select max(week_end) from scores")).fetchone()
    return None if row is None else row[0]


def text_shortlist(conn: Conn, week: date, limit: int) -> list[UUID]:
    """§4.5 scope 2: the top companies by Evidence in `week` that have no text document yet."""
    rows = _rows(
        conn,
        "select s.company_id from scores s where s.week_end = %s and s.evidence > 0 and not exists "
        "(select 1 from documents d where d.company_id = s.company_id) order by s.evidence desc, s.company_id limit %s",
        (week, limit),
    )
    return [r["company_id"] for r in rows]


def ledger_companies(conn: Conn) -> set[UUID]:
    """Companies with at least one verified text fact (the Capex Desk ledger)."""
    return {
        r["company_id"]
        for r in _rows(conn, "select distinct company_id from facts where verification_status = 'verified'")
    }


def p06_recent(conn: Conn, since: date) -> set[UUID]:
    """Companies P-06 read since `since` (their profile document)."""
    rows = _rows(
        conn,
        "select distinct company_id from documents where url like 'nse-profile:%%' and published_at >= %s",
        (since,),
    )
    return {r["company_id"] for r in rows}


def export_quotes(conn: Conn, company_ids: Sequence[UUID], cutoff: datetime) -> dict[UUID, dict[UUID, str]]:
    """company -> {fact id: quote} of verified export_exposure facts published before the cutoff."""
    rows = _rows(
        conn,
        "select f.id, f.company_id, f.quote from facts f join documents d on d.id = f.document_id "
        "where f.company_id = any(%s) and f.fact_type = 'export_exposure' and f.verification_status = 'verified' "
        "and d.published_at < %s",
        (list(company_ids), cutoff),
    )
    out: dict[UUID, dict[UUID, str]] = {}
    for r in rows:
        out.setdefault(r["company_id"], {})[r["id"]] = r["quote"]
    return out


def new_diffs(conn: Conn, since: datetime) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select c.name as company, f.fact_type, x.subject_key, x.computed_note, x.change_kind, x.delta_pct, "
        "f.value_num, f.quote, d.url from diffs x join facts f on f.id = x.new_fact_id "
        "join documents d on d.id = f.document_id join companies c on c.id = x.company_id "
        "where x.created_at >= %s and x.change_kind <> 'reaffirmed' order by x.created_at",
        (since,),
    )


def new_links(conn: Conn, since: datetime) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select c.name as company, e.name as entity, l.relation from links l join companies c on c.id = "
        "l.from_company_id join entities e on e.id = l.to_entity_id where l.first_seen_at >= %s order by c.name",
        (since,),
    )


def new_memberships(conn: Conn, since: datetime, source: str) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select c.name as company, m.category, m.quote from capex_memberships m join companies c on c.id = "
        "m.company_id where m.source = %s and m.proposed_at >= %s order by c.name, m.category",
        (source, since),
    )


def fired_signal(conn: Conn, week: date, signal_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "select c.name as company, v.inputs from signal_values v join companies c on c.id = v.company_id "
        "where v.week_end = %s and v.signal_id = %s and v.fired order by c.name",
        (week, signal_id),
    )
