"""M4-06: the percentile context scores C1 and C3 (BRIEF §4.7; C4 and its GDELT client are gone, SPEC_ISSUES 48)."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

from pipeline.db import seed
from pipeline.db.models import SourceHealth
from pipeline.digest import weekly as digest
from pipeline.net.http import ALLOWED_HOSTS
from pipeline.settings import REPO_ROOT
from pipeline.signals import context, weekly
from pipeline.signals.context import c1, c3, percentile_rank, return_52w


def test_percentile_rank_counts_ties_as_half() -> None:
    pop = [D(v) for v in (1, 2, 3, 4)]
    assert percentile_rank(D(1), pop) == D("12.5") and percentile_rank(D(4), pop) == D("87.5")
    assert percentile_rank(D(5), pop) == D(100) and percentile_rank(D(0), pop) == D(0)


def test_c3_flags_names_that_already_ran() -> None:
    pop = [D(x) / 100 for x in range(-20, 80)]  # 100 returns from -20% to +79%
    ran = c3(D("0.79"), pop, D(90), 30)
    assert ran.inputs["already_ran"] and ran.score is not None and ran.score < 10
    early = c3(D("-0.10"), pop, D(90), 30)
    assert not early.inputs["already_ran"] and early.score is not None and early.score > 80


def test_c3_needs_a_comparison_group_of_30() -> None:
    """SPEC_ISSUES 48: a percentile within a handful of names says little."""
    assert c3(D("0.01"), [D(x) / 100 for x in range(-2, 3)], D(90), 30).inputs == {
        "missing": ["population"], "return_52w": 0.01, "population": 5, "min_population": 30}  # fmt: skip
    assert c3(D("0.01"), [D(x) / 100 for x in range(-14, 15)], D(90), 30).score is None  # 29 returns
    got = c3(D("0.01"), [D(x) / 100 for x in range(-15, 15)], D(90), 30)  # 30 returns, -15% to +14%
    assert got.score == D(45) and got.inputs["population"] == 30  # 16 below, 1 tie: pct 55


def test_c1_needs_a_year_and_scores_cheap_vs_own_history() -> None:
    weeks = [date(2025, 1, 3) + timedelta(weeks=i) for i in range(60)]
    rich = [(w, D(3 + i % 7), D(20 + i % 11)) for i, w in enumerate(weeks)]
    cheap = [*rich[:-1], (weeks[-1], D("2.5"), D(19))]  # cheaper than every past week on both multiples
    assert c1(cheap).score is not None and c1(cheap).score > 95  # type: ignore[operator]
    assert c1(rich[:30]).score is None  # < 52 weeks of history
    only_sales = [(w, s, None) for w, s, _ in cheap]  # EBIT <= 0 all along: EV/Sales alone
    assert c1(only_sales).score == c1(only_sales).score and c1(only_sales).inputs.get("pct_ev_ebit") is None


def test_return_52w() -> None:
    week = date(2026, 9, 18)
    closes = [(week - timedelta(weeks=52), D(100)), (week - timedelta(weeks=1), D(120)), (week, D(125))]
    assert return_52w(closes, week) == D("0.25")
    assert return_52w(closes[1:], week) is None  # no close a year back


def test_gdelt_is_gone_end_to_end() -> None:
    """SPEC_ISSUES 48: no client, no allowlisted host, no seeded health row, no fixtures and no SLA. The old
    source_health row stays (no migration) and stops being updated; without an SLA it never reads as late, so the
    digest's stale banner doesn't name it, nor the app's, whose web/lib/staleness.ts is pinned to the same file (PR 2
    review deletion-F1)."""
    assert importlib.util.find_spec("pipeline.net.gdelt") is None
    assert not any("gdelt" in host for host in ALLOWED_HOSTS) and "gdelt" not in seed.SOURCES
    assert not (REPO_ROOT / "fixtures" / "gdelt").exists() and not hasattr(context, "c4")
    assert not hasattr(weekly, "attention") and not hasattr(weekly, "mark_gdelt")
    sla, now = digest.sla_days(), datetime(2026, 11, 7, 3, tzinfo=UTC)
    gdelt = SourceHealth(source="gdelt", last_success=datetime(2026, 10, 10, 2, tzinfo=UTC))  # not stale
    assert "gdelt" not in sla and digest.banner([gdelt], now, sla) == []
    assert digest.health([gdelt], now, sla)[-1] == "| gdelt | 2026-10-10 02:00Z | ok |"
