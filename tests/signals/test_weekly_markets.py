"""`python -m pipeline.signals.weekly --markets` (overhaul PR 1): the weekly job scores the US alone while India is
paused (docs/SPEC_ISSUES.md 46); a run without it scores both markets, as before. The database is faked here;
tests/db/test_signals_pipeline.py checks that a US-only run writes no India rows."""

from __future__ import annotations

import argparse
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest

from pipeline.db import repo
from pipeline.signals import weekly


@pytest.mark.parametrize(("text", "markets"), [("us", ("us",)), ("in", ("in",)), ("in,us", ("us", "in")),
                                               (" us , us ", ("us",))])  # fmt: skip
def test_markets_are_a_subset_of_us_and_in(text: str, markets: tuple[str, ...]) -> None:
    assert weekly.markets_arg(text) == markets


@pytest.mark.parametrize("text", ["", ",", "us,uk", "US"])
def test_anything_else_is_refused(text: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        weekly.markets_arg(text)


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    """The markets main() asked run() for, and the runs row it recorded."""
    out: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    asked: list[tuple[str, ...]] = []

    @contextmanager
    def connect(url: str) -> Iterator[None]:
        yield None

    @contextmanager
    def tracked_run(conn: None, kind: str) -> Iterator[dict[str, Any]]:
        assert kind == "scores_weekly"
        stats: dict[str, Any] = {}
        yield stats
        out.append((asked[-1], stats))

    def run(conn: None, week: date, http: object, markets: Collection[str] = weekly.MARKETS) -> weekly.ScoresStats:
        asked.append(tuple(markets))
        return weekly.ScoresStats(week.isoformat(), markets=[m for m in weekly.MARKETS if m in markets])

    monkeypatch.setattr(weekly.psycopg, "connect", connect)
    monkeypatch.setattr(repo, "tracked_run", tracked_run)
    monkeypatch.setattr(weekly, "run", run)
    return out


def test_the_weekly_job_scores_the_us_alone(runs: list[tuple[tuple[str, ...], dict[str, Any]]]) -> None:
    assert weekly.main(["--week", "2026-10-30", "--markets", "us"]) == 0
    assert [(asked, row["markets"]) for asked, row in runs] == [(("us",), ["us"])]


def test_without_markets_both_are_scored(runs: list[tuple[tuple[str, ...], dict[str, Any]]]) -> None:
    assert weekly.main(["--week", "2026-10-30"]) == 0
    assert [(asked, row["markets"]) for asked, row in runs] == [(("us", "in"), ["us", "in"])]


def test_an_unknown_market_stops_before_the_database(runs: list[tuple[tuple[str, ...], dict[str, Any]]]) -> None:
    with pytest.raises(SystemExit):
        weekly.main(["--markets", "us,uk"])
    assert runs == []
