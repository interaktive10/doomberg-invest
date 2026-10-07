"""pipeline/db/diagnose.py against the database: the candidate stage's rows with their families, context scores and
market caps, and why the priced ones that aren't candidates aren't (the first live runs, 2026-10-07, scored 391
priced companies into no bucket at all)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.db import repo
from pipeline.db.diagnose import report, stage_rows
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
    repo.upsert_context_values(conn, context(one, {"C1": 70, "C2": None, "C3": 55, "C4": None})
                               + context(two, {"C1": 61, "C2": None, "C3": 61, "C4": None})
                               + context(small, {"C1": 61, "C2": None, "C3": 61, "C4": None}))  # fmt: skip
    repo.upsert_company_metrics(conn, WEEK, {one: {"market_cap": 2.5e9}, two: {"market_cap": 9e9},
                                             small: {"market_cap": 1e8}})  # fmt: skip
    rows = stage_rows(conn, WEEK, Decimal(40))
    assert [r.evidence for r in rows] == [Decimal(70), Decimal(70), Decimal(55), Decimal(50)]  # weak is off-stage
    assert {r.symbol: len(r.families) for r in rows}["Two"] == 2
    assert {r.symbol: dict(r.context) for r in rows}["One"] == {"C1": 70, "C2": None, "C3": 55, "C4": None}
    cfgs = Configs.load()
    text = "\n".join(report(rows, cfgs.universe, cfgs.signals["scores"]["buckets"]))
    assert "us: stage 4, priced 3" in text
    assert "families contributing: {'fundamentals': 4, 'behavior': 2}" in text
    assert "context known {'C1': 3, 'C2': 0, 'C3': 3, 'C4': 0}, Gap 3, market cap 3, above the floor 2" in text
    assert ("priced but 'none': {'market cap below the floor': 1, "
            "'one signal family (Evidence capped at 55; early needs 2)': 1}") in text  # fmt: skip
    assert "Two          E=70.0 fam=fundamentals+behavior Gap=61.0 C1=61 C2=- C3=61 C4=- mcap=9,000 candidate" in text
