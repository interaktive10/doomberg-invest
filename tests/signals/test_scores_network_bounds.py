"""The scores job's network stages are bounded (pipeline/signals/weekly.py). The first live run (2026-09-29) spent
the job's 40 minutes without finishing: a GDELT failure didn't use up the query budget, and neither GDELT nor Stooq
stopped being asked when every request failed, while each request waits for the site's rate limit (GDELT 5 s, Stooq
2 s) and up to its timeout."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from pipeline.db.models import Company
from pipeline.net.gdelt import build_query, timeline_url
from pipeline.net.http import HttpClient
from pipeline.net.stooq import StooqClient, csv_url, stooq_symbol
from pipeline.settings import Settings
from pipeline.signals import weekly

FIX = Path(__file__).resolve().parents[2] / "fixtures"
WEEK = date(2026, 9, 25)
NO_DB: Any = None  # the repo calls these stages make are replaced below
THROTTLED = (FIX / "gdelt" / "rate_limit.txt").read_bytes()  # GDELT's "Please limit requests..." (HTTP 200)
NO_ARTICLES = (FIX / "gdelt" / "empty.json").read_bytes()
DAILY_LIMIT = (FIX / "px" / "limit.txt").read_bytes()  # Stooq's "Exceeded the daily hits limit"
N = weekly.MAX_FAILURES_IN_A_ROW


def mock_http(tmp_path: Path) -> HttpClient:
    return HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))


def us_companies(n: int) -> list[Company]:
    return [Company(id=uuid4(), market="us", name=f"Company {i:02d} Inc", ticker=f"TK{i:02d}") for i in range(n)]


def gdelt(http: HttpClient, companies: list[Company], answers: list[bytes]) -> None:
    for c, body in zip(companies, answers, strict=True):
        http.register_mock(timeline_url(build_query(c.name, c.ticker, "us")), body)


@pytest.fixture
def nothing_to_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(weekly.repo, "recent_attention", lambda conn, week, since: {})


def test_failed_gdelt_queries_use_up_the_budget(tmp_path: Path, nothing_to_reuse: None) -> None:
    http, cos = mock_http(tmp_path), us_companies(10)
    gdelt(http, cos, [THROTTLED if i % 2 else NO_ARTICLES for i in range(10)])
    stats = weekly.ScoresStats(WEEK.isoformat())
    counts = weekly.attention(NO_DB, WEEK, cos, http, 6, stats)
    assert len(http.calls) == 6
    assert (stats.gdelt_queried, stats.gdelt_failed, stats.gdelt_not_asked) == (3, 3, 4)
    assert set(counts) == {cos[0].id, cos[2].id, cos[4].id}


def test_gdelt_is_not_asked_again_after_failures_in_a_row(tmp_path: Path, nothing_to_reuse: None) -> None:
    http, cos = mock_http(tmp_path), us_companies(40)
    gdelt(http, cos, [THROTTLED] * 40)
    stats = weekly.ScoresStats(WEEK.isoformat())
    assert weekly.attention(NO_DB, WEEK, cos, http, 100, stats) == {}
    assert len(http.calls) == N and (stats.gdelt_failed, stats.gdelt_not_asked) == (N, 40 - N)


def test_a_gdelt_answer_ends_a_run_of_failures(tmp_path: Path, nothing_to_reuse: None) -> None:
    http, cos = mock_http(tmp_path), us_companies(3 * N)
    gdelt(http, cos, ([THROTTLED] * (N - 1) + [NO_ARTICLES]) * 3)
    stats = weekly.ScoresStats(WEEK.isoformat())
    weekly.attention(NO_DB, WEEK, cos, http, 100, stats)
    assert len(http.calls) == 3 * N and (stats.gdelt_queried, stats.gdelt_not_asked) == (3, 0)


def test_stooq_is_not_asked_again_after_failures_in_a_row_but_manual_imports_still_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[Any] = []
    monkeypatch.setattr(weekly.repo, "priced_at", lambda conn, ids, week: set())
    monkeypatch.setattr(weekly.repo, "prices", lambda conn, ids, start, end: [])
    monkeypatch.setattr(weekly.repo, "upsert_prices", lambda conn, rows: written.extend(rows))
    http, cos = mock_http(tmp_path), us_companies(12)
    for c in cos:
        assert c.ticker
        http.register_mock(csv_url(stooq_symbol(c.ticker)), DAILY_LIMIT)
    imports = tmp_path / "imports"
    imports.mkdir()
    late = cos[N + 4]  # after the run of failures
    assert late.ticker
    (imports / f"{late.ticker.upper()}.csv").write_bytes((FIX / "px" / "aapl.us_w.csv").read_bytes())
    stats = weekly.ScoresStats(WEEK.isoformat())
    weekly.ingest_us_prices(NO_DB, StooqClient(http), cos, WEEK, imports, stats, 10)
    assert len(http.calls) == N
    assert (stats.stooq_ok, stats.stooq_failed, stats.stooq_imported, stats.stooq_not_asked) == (0, N, 1, 12 - N - 1)
    assert written and {r.company_id for r in written} == {late.id}
