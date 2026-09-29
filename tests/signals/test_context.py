"""M4-06: the GDELT client (mocked) and the percentile context scores C1, C3, C4 (BRIEF §4.7)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from pipeline.net.gdelt import GdeltClient, GdeltError, build_query, parse_count, short_name, timeline_url
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.signals.context import c1, c3, c4, percentile_rank, return_52w

GD = Path(__file__).resolve().parents[2] / "fixtures" / "gdelt"


def test_short_names_and_queries() -> None:
    assert short_name("Quanta Services, Inc.") == "Quanta Services"
    assert short_name("KEI Industries Limited") == "KEI Industries"
    assert short_name("Caterpillar Inc") == "Caterpillar"
    assert build_query("Quanta Services, Inc.", "PWR", "us") == '"Quanta Services" (PWR OR Inc)'
    assert build_query("KEI Industries Limited", "KEI", "in") == '"KEI Industries" (KEI OR Ltd)'
    assert build_query("General Electric Company", "GE", "us") == '"General Electric" Inc'  # 2-letter tickers dropped


def test_count_sums_the_timeline() -> None:
    assert parse_count((GD / "timeline_pwr.json").read_bytes()) == 180
    assert parse_count((GD / "empty.json").read_bytes()) == 0
    for name in ("too_short.txt", "rate_limit.txt"):
        with pytest.raises(GdeltError):
            parse_count((GD / name).read_bytes())


def test_client_uses_the_mock(tmp_path: Path) -> None:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    url = timeline_url(build_query("Quanta Services, Inc.", "PWR", "us"))
    assert url.startswith("https://api.gdeltproject.org/api/v2/doc/doc?query=") and "timespan=90d" in url
    http.register_mock(url, (GD / "timeline_pwr.json").read_bytes())
    assert GdeltClient(http).article_count("Quanta Services, Inc.", "PWR", "us") == 180


def test_percentile_rank_counts_ties_as_half() -> None:
    pop = [D(v) for v in (1, 2, 3, 4)]
    assert percentile_rank(D(1), pop) == D("12.5") and percentile_rank(D(4), pop) == D("87.5")
    assert percentile_rank(D(5), pop) == D(100) and percentile_rank(D(0), pop) == D(0)


def test_c4_is_inverse_attention() -> None:
    counts = [5, 10, 50, 500]
    quiet, loud = c4(5, counts), c4(500, counts)
    assert quiet.score == D("87.5") and loud.score == D("12.5")
    assert c4(None, counts).score is None


def test_c3_flags_names_that_already_ran() -> None:
    pop = [D(x) / 100 for x in range(-20, 80)]  # 100 returns from -20% to +79%
    ran = c3(D("0.79"), pop, D(90))
    assert ran.inputs["already_ran"] and ran.score is not None and ran.score < 10
    early = c3(D("-0.10"), pop, D(90))
    assert not early.inputs["already_ran"] and early.score is not None and early.score > 80


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
