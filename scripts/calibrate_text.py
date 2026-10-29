"""Read-only text-pipeline calibration (scratch branch calibrate-text, never merged). Aggregates only: no company
names, no journal, positions or post-mortems; error strings are the providers' short messages."""

from __future__ import annotations

import os
from typing import Any

import psycopg


def show(cur: Any, title: str, sql: str) -> None:
    cur.execute(sql)
    cols = [d.name for d in cur.description]
    print(f"\n===== {title}")
    print(" | ".join(cols))
    for r in cur.fetchall():
        print(" | ".join("" if v is None else str(v) for v in r))


def main() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        show(cur, "llm calls by day, prompt and outcome (last 21 days)", """
            select created_at::date as day, prompt_id, provider, ok, count(*) as calls,
                   round(avg(latency_ms)) as avg_ms, sum(coalesce(tokens_in, 0)) as tokens_in
            from llm_calls where created_at >= now() - interval '21 days'
            group by 1, 2, 3, 4 order by 1, 2, 3, 4""")
        show(cur, "llm errors by message (last 21 days)", """
            select prompt_id, provider, left(regexp_replace(coalesce(error, ''), '[0-9a-f]{8,}', '#', 'g'), 90) as error,
                   count(*) as n, min(created_at)::date as first, max(created_at)::date as last
            from llm_calls where not ok and created_at >= now() - interval '21 days'
            group by 1, 2, 3 order by 4 desc limit 30""")
        show(cur, "text runs (last 12)", """
            select started_at, status, round(extract(epoch from finished_at - started_at) / 60, 1) as minutes,
                   (stats ->> 'scope')::int as scope, (stats ->> 'documents')::int as documents,
                   (stats ->> 'extracted')::int as extracted, (stats ->> 'deferred')::int as deferred,
                   (stats ->> 'failed')::int as failed, (stats ->> 'facts_verified')::int as verified,
                   (stats ->> 'facts_review')::int as review, stats -> 'rejected' as rejected,
                   stats ->> 'stopped' as stopped, stats -> 'scope_by_order' as scope_by_order,
                   stats -> 'read_by_order' as read_by_order
            from runs where kind = 'text' order by started_at desc limit 12""")
        show(cur, "needs_review reasons by fact type (stored since 2026-09-20)", """
            select f.fact_type, k as reason, count(*) as facts
            from facts f, jsonb_object_keys(f.verification_notes) k
            where f.verification_status = 'needs_review' and f.created_at >= '2026-09-20'
            group by 1, 2 order by 3 desc limit 40""")
        show(cur, "period labels that sent a fact to review (stored since 2026-09-20; the label only)", """
            select f.fact_type, left(f.period_label, 40) as period_label, count(*) as facts
            from facts f where f.verification_status = 'needs_review' and f.verification_notes ? 'period'
              and f.created_at >= '2026-09-20' group by 1, 2 order by 3 desc limit 30""")
        show(cur, "the 2026-10-28 15:29Z run: P-01 calls and documents", """
            select (select count(*) from llm_calls where prompt_id = 'P-01' and created_at >= '2026-10-28 15:28+00')
                     as p01_calls,
                   (select count(*) from llm_calls where prompt_id = 'P-07' and created_at >= '2026-10-28 15:28+00')
                     as p07_calls,
                   (select count(*) from llm_calls where not ok and created_at >= '2026-10-28 15:28+00') as failed,
                   (select round(avg(latency_ms)) from llm_calls where created_at >= '2026-10-28 15:28+00') as avg_ms""")
        show(cur, "documents stored since 2026-10-28 15:28Z by kind and market", """
            select c.market, d.kind, count(*) as documents, round(avg(d.text_chars)) as avg_chars,
                   sum((select count(*) from facts f where f.document_id = d.id and f.verification_status = 'verified'))
                     as verified,
                   sum((select count(*) from facts f where f.document_id = d.id and f.verification_status = 'needs_review'))
                     as review
            from documents d join companies c on c.id = d.company_id
            where d.created_at >= '2026-10-28 15:28+00' group by 1, 2 order by 1, 2""")
        show(cur, "facts stored since 2026-10-28 15:28Z by type and status (S9 types first)", """
            select f.fact_type, f.verification_status, count(*) as facts, count(distinct f.company_id) as companies,
                   count(*) filter (where f.counterparty is not null) as with_counterparty,
                   string_agg(distinct k, ',') as review_reasons
            from facts f left join lateral jsonb_object_keys(f.verification_notes) k on true
            where f.created_at >= '2026-10-28 15:28+00'
            group by 1, 2 order by (f.fact_type in ('order_win','customer_win','price_increase','new_segment',
              'governance_flag','capacity_addition','lead_time')) desc, 3 desc""")
        show(cur, "S9-type facts stored since 2026-10-28 15:00Z by market, type and status (aggregates only)", """
            select c.market, f.fact_type, f.verification_status, count(*) as facts,
                   count(distinct f.company_id) as companies,
                   count(*) filter (where f.counterparty is not null) as with_counterparty,
                   count(*) filter (where f.subject_key like '%:removed') as removed
            from facts f join companies c on c.id = f.company_id
            where f.created_at >= '2026-10-28 15:00+00'
              and f.fact_type in ('order_win','customer_win','price_increase','new_segment','governance_flag',
                                  'capacity_addition')
            group by 1, 2, 3 order by 1, 2, 3""")
        show(cur, "review reasons of S9-type facts stored since 2026-10-28 15:00Z", """
            select f.fact_type, k as reason, count(*) as facts
            from facts f, jsonb_object_keys(f.verification_notes) k
            where f.created_at >= '2026-10-28 15:00+00' and f.verification_status = 'needs_review'
              and f.fact_type in ('order_win','customer_win','price_increase','new_segment','governance_flag',
                                  'capacity_addition')
            group by 1, 2 order by 3 desc limit 30""")
        show(cur, "llm calls since 2026-10-28 15:00Z by day, prompt and outcome", """
            select created_at::date as day, prompt_id, provider, ok, count(*) as calls, round(avg(latency_ms)) as avg_ms
            from llm_calls where created_at >= '2026-10-28 15:00+00' group by 1, 2, 3, 4 order by 1, 2, 3, 4""")
        show(cur, "facts V1-KIND took out of the ledger (verification_notes.kind), by type and status", """
            select f.fact_type, f.verification_status, f.verification_notes ->> 'kind' as why, count(*) as facts,
                   count(distinct f.company_id) as companies
            from facts f where f.verification_notes ? 'kind' group by 1, 2, 3 order by 1, 2, 4 desc""")
        show(cur, "verified S9-type facts by type since 2026-10-28 15:00Z, now", """
            select f.fact_type, count(*) as facts, count(distinct f.company_id) as companies
            from facts f where f.created_at >= '2026-10-28 15:00+00' and f.verification_status = 'verified'
              and f.fact_type in ('order_win','customer_win','price_increase','new_segment','governance_flag',
                                  'capacity_addition')
            group by 1 order by 1""")
        show(cur, "India history runs: errors by kind (symbols masked)", """
            select left(regexp_replace(regexp_replace(e, '^([a-z ]+?) [A-Z0-9&_.-]+:', '\\1 #:'), '[0-9]{4,}', '#', 'g'), 110)
                     as kind, count(*) as n
            from runs r, jsonb_array_elements_text(coalesce(r.stats -> 'errors', '[]'::jsonb)) e
            where r.kind = 'in_history' and r.started_at >= '2026-10-28'
            group by 1 order by 2 desc limit 25""")
        show(cur, "S9-type verified facts since 2026-10-28 15:00Z of stage names with no thesis (the quote cut at 160)", """
            select c.ticker, f.fact_type, f.subject_key, f.value_num, f.unit, f.currency, left(f.counterparty, 30) as cp,
                   d.kind, left(regexp_replace(f.quote, '\\s+', ' ', 'g'), 160) as quote
            from facts f join companies c on c.id = f.company_id join documents d on d.id = f.document_id
            where f.created_at >= '2026-10-28 15:00+00' and f.verification_status = 'verified'
              and f.fact_type in ('order_win','customer_win','price_increase','new_segment','governance_flag')
              and not exists (select 1 from theses t where t.company_id = f.company_id)
            order by f.fact_type, c.ticker limit 80""")
        show(cur, "documents still deferred, by kind", """
            select kind, count(*) as documents, min(published_at)::date as oldest, max(published_at)::date as newest
            from documents where status = 'deferred' group by 1 order by 2 desc""")


if __name__ == "__main__":
    main()
