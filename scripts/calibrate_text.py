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
                   stats ->> 'stopped' as stopped
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
        show(cur, "documents still deferred, by kind", """
            select kind, count(*) as documents, min(published_at)::date as oldest, max(published_at)::date as newest
            from documents where status = 'deferred' group by 1 order by 2 desc""")


if __name__ == "__main__":
    main()
