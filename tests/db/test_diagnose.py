"""pipeline/db/diagnose.py against the database: the candidate stage's rows with their families, context scores and
market caps, and why the priced ones that aren't candidates aren't (the first live runs, 2026-10-07, scored 391
priced companies into no bucket at all); and the last text run's line with its stop reason (docs/SPEC_ISSUES.md 50)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from pipeline.db import repo
from pipeline.db.diagnose import last_run, last_text_run, report, stage_rows, text_run
from pipeline.db.models import ContextValue, Score
from pipeline.signals.weekly import Configs
from tests.db.conftest import new_company

WEEK = date(2026, 10, 2)


def score(cid: Any, evidence: str, gap: str | None, families: list[str], bucket: str) -> Score:
    return Score(company_id=cid, week_end=WEEK, evidence=Decimal(evidence), gap=None if gap is None else Decimal(gap),
                 families=families, bucket=bucket, weights_version="w0-equal")  # fmt: skip


def context(cid: Any, scores: dict[str, float | None]) -> list[ContextValue]:
    return [ContextValue(company_id=cid, week_end=WEEK, metric_id=m, value=None, pct=None, inputs={"score": s})
            for m, s in scores.items()]  # fmt: skip


def test_the_stage_and_why_priced_companies_are_not_candidates(conn: psycopg.Connection[Any]) -> None:
    one, two, small, unpriced, weak = (new_company(conn, name=n) for n in ("One", "Two", "Small", "Unpriced", "Weak"))
    repo.upsert_scores(conn, [
        score(one, "55", "62.5", ["fundamentals"], "none"),
        score(two, "70", "61", ["fundamentals", "behavior"], "candidate"),
        score(small, "70", "61", ["fundamentals", "behavior"], "none"),
        score(unpriced, "50", None, ["fundamentals"], "none"),
        score(weak, "20", None, [], "none"),
    ])  # fmt: skip
    repo.upsert_context_values(conn, context(one, {"C1": 70, "C2": None, "C3": 55})
                               + context(two, {"C1": 61, "C2": None, "C3": 61})
                               + context(small, {"C1": 61, "C2": None, "C3": 61}))  # fmt: skip
    repo.upsert_company_metrics(conn, WEEK, {one: {"market_cap": 2.5e9}, two: {"market_cap": 9e9},
                                             small: {"market_cap": 1e8}})  # fmt: skip
    rows = stage_rows(conn, WEEK, Decimal(40))
    assert [r.evidence for r in rows] == [Decimal(70), Decimal(70), Decimal(55), Decimal(50)]  # weak is off-stage
    assert {r.symbol: len(r.families) for r in rows}["Two"] == 2
    assert {r.symbol: dict(r.context) for r in rows}["One"] == {"C1": 70, "C2": None, "C3": 55}
    cfgs = Configs.load()
    text = "\n".join(report(rows, cfgs.universe, cfgs.signals["scores"]["buckets"]))
    assert "us: stage 4, priced 3" in text
    assert "families contributing: {'fundamentals': 4, 'behavior': 2}" in text
    assert "context known {'C1': 3, 'C2': 0, 'C3': 3}, Gap 3, market cap 3, above the floor 2" in text
    assert ("priced but 'none': {'market cap below the floor': 1, "
            "'one signal family (Evidence capped at 55; early needs 2)': 1}") in text  # fmt: skip
    assert "Two          E=70.0 fam=fundamentals+behavior Gap=61.0 C1=61 C2=- C3=61 mcap=9,000 candidate" in text


def test_the_last_scoring_runs_errors_by_source(conn: psycopg.Connection[Any]) -> None:
    """The last finished run's errors grouped by source: a source that failed shows where the stage's gaps come
    from."""
    errors = [
        "twelvedata PWR: TwelveDataUnavailable: You have run out of API credits",
        "benchmark XLI: x: y",
        "twelvedata JBL: TwelveDataUnavailable: timeout",
        "twelvedata CAT: TwelveDataUnavailable: timeout",
        "twelvedata ACME: z",
    ]
    finished = "('scores_weekly', '2026-10-07 16:01+00', '2026-10-07 16:57+00', 'partial', %s)"
    conn.execute(f"insert into runs (kind, started_at, finished_at, status, stats) values {finished}",
                 (Jsonb({"errors": errors}),))  # fmt: skip
    running = "('scores_weekly', '2026-10-07 17:30+00', 'running')"  # still going: not the last finished run
    conn.execute(f"insert into runs (kind, started_at, status) values {running}")
    assert last_run(conn) == [
        "last scoring run 2026-10-07 16:01Z: partial, 5 errors",
        "  twelvedata: 4",
        "    twelvedata PWR: TwelveDataUnavailable: You have run out of API credits",
        "    twelvedata JBL: TwelveDataUnavailable: timeout",
        "    twelvedata CAT: TwelveDataUnavailable: timeout",
        "  benchmark: 1",
        "    benchmark XLI: x: y",
    ]


def test_the_text_runs_line_says_what_it_read_and_why_it_stopped() -> None:
    started = datetime(2026, 11, 3, 1, 20, tzinfo=UTC)
    stats = {"scope": 312, "theses": 6, "stage": 306, "submissions": 14, "indexed": 9, "queued_filings": 11,
             "skipped_filings": 3, "extracted": 38, "deferred": 2, "failed": 0, "facts_verified": 25,
             "stopped": "daily document limit (40)", "checked": {"0000999001": 1}}  # fmt: skip
    assert text_run(started, "ok", stats) == (
        "last text run 2026-11-03 01:20Z: ok, scope 312 (theses 6, stage names 306), submissions read for 14 (9 in "
        "the EDGAR index), 11 filings queued, 3 skipped, 38 documents extracted, 2 deferred, 0 failed, 25 verified "
        "facts; stopped: daily document limit (40)"
    )
    assert text_run(started, "ok", {"scope": 1}).endswith("stopped: queue empty")  # an older row: missing keys are 0
    assert text_run(started, "ok", {"skipped": "quotas not set"}) == (
        "last text run 2026-11-03 01:20Z: ok, skipped (quotas not set)"
    )
    assert text_run(started, "failed", {}, "OperationalError: x") == (
        "last text run 2026-11-03 01:20Z: failed (OperationalError: x)"
    )


def test_the_last_finished_text_run(conn: psycopg.Connection[Any]) -> None:
    assert last_text_run(conn) == ["last text run: none"]
    finished = "('text', '2026-11-03 01:20+00', '2026-11-03 01:29+00', 'partial', %s)"
    conn.execute(f"insert into runs (kind, started_at, finished_at, status, stats) values {finished}",
                 (Jsonb({"scope": 2, "theses": 1, "stage": 1, "extracted": 3, "stopped": "time budget (6 min)",
                         "errors": ["fetch x: HTTPStatusError"]}),))  # fmt: skip
    conn.execute("insert into runs (kind, started_at, status) values ('text', '2026-11-04 01:20+00', 'running')")
    (line,) = last_text_run(conn)
    assert line.startswith("last text run 2026-11-03 01:20Z: partial, scope 2 (theses 1, stage names 1)")
    assert "3 documents extracted" in line and line.endswith("stopped: time budget (6 min)")
