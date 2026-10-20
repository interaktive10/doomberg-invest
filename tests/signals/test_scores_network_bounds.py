"""The scores job's network stages are bounded (pipeline/signals/weekly.py). The first live run (2026-09-29) spent
the job's 40 minutes without finishing: the price source (Stooq then, Yahoo since 2026-10) kept being asked when
every request failed, while each request waits for the site's rate limit (1-2 s) and up to its timeout. (GDELT, the
other network stage then, went with C4: docs/SPEC_ISSUES.md 48.)"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from pipeline.db.models import Company
from pipeline.net.http import HttpClient
from pipeline.net.yahoo import HOSTS, YahooClient, chart_url, yahoo_symbol
from pipeline.settings import Settings
from pipeline.signals import weekly

FIX = Path(__file__).resolve().parents[2] / "fixtures"
WEEK = date(2026, 9, 25)
NO_DB: Any = None  # the repo calls these stages make are replaced below
N = weekly.MAX_FAILURES_IN_A_ROW


def mock_http(tmp_path: Path) -> HttpClient:
    return HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))


def us_companies(n: int) -> list[Company]:
    return [Company(id=uuid4(), market="us", name=f"Company {i:02d} Inc", ticker=f"TK{i:02d}") for i in range(n)]


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    rows: list[Any] = []
    monkeypatch.setattr(weekly.repo, "priced_at", lambda conn, ids, week: set())
    monkeypatch.setattr(weekly.repo, "prices", lambda conn, ids, start, end: [])
    monkeypatch.setattr(weekly.repo, "upsert_prices", lambda conn, new: rows.extend(new))
    return rows


def test_yahoo_is_not_asked_again_after_failures_in_a_row_but_manual_imports_still_count(
    tmp_path: Path, written: list[Any]
) -> None:
    http, cos = mock_http(tmp_path), us_companies(12)
    for c in cos:
        assert c.ticker
        for host in HOSTS:  # "Too Many Requests" from both
            http.register_error(chart_url(yahoo_symbol(c.ticker), host), 429)
    imports = tmp_path / "imports"
    imports.mkdir()
    late = cos[N + 4]  # after the run of failures
    assert late.ticker
    (imports / f"{late.ticker.upper()}.csv").write_bytes((FIX / "px" / "aapl.us_w.csv").read_bytes())
    stats = weekly.ScoresStats(WEEK.isoformat())
    weekly.ingest_us_prices(NO_DB, YahooClient(http), cos, WEEK, imports, stats, 10)
    assert len(http.calls) == N * len(HOSTS)
    counts = (stats.prices_ok, stats.prices_failed, stats.prices_imported, stats.prices_not_asked)
    assert counts == (0, N, 1, 12 - N - 1)
    assert written and {r.company_id for r in written} == {late.id} and {r.source for r in written} == {"manual"}


def test_symbols_yahoo_does_not_know_do_not_stop_the_stage(tmp_path: Path, written: list[Any]) -> None:
    """A 404 ("No data found, symbol may be delisted") is an answer: the site is up, so it never counts toward the
    failures in a row that stop the stage."""
    http, cos = mock_http(tmp_path), us_companies(3 * N)
    for i, c in enumerate(cos):
        assert c.ticker
        if i == len(cos) - 1:
            http.register_mock(chart_url(c.ticker), (FIX / "px" / "yahoo" / "PWR.json").read_bytes())
        else:
            http.register_error(chart_url(c.ticker), 404)
    stats = weekly.ScoresStats(WEEK.isoformat())
    weekly.ingest_us_prices(NO_DB, YahooClient(http), cos, WEEK, tmp_path, stats, 10)
    assert len(http.calls) == 3 * N
    assert (stats.prices_ok, stats.prices_failed, stats.prices_not_asked) == (1, 3 * N - 1, 0)
    assert {r.source for r in written} == {"yahoo"} and {r.company_id for r in written} == {cos[-1].id}
