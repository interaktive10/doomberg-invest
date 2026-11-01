"""Themes' demand drivers (pipeline/reports/drivers.py, pipeline/net/fred.py; docs/SPEC_ISSUES.md 68): one way to read
every series, scored against its own history."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pipeline.net import fred
from pipeline.reports import drivers as dv

ROOT = Path(__file__).resolve().parents[2]


def monthly(values: list[float], start: int = 2000) -> list[tuple[date, float]]:
    return [(date(start + i // 12, i % 12 + 1, 1), v) for i, v in enumerate(values)]


def test_fred_csv_parses_to_monthly_points_and_skips_gaps() -> None:
    pts = fred.parse("observation_date,X\n2026-01-01,10\n2026-01-15,12\n2026-02-01,.\n2026-03-01,7\n")
    assert pts == [(date(2026, 1, 1), 11.0), (date(2026, 3, 1), 7.0)]
    real = fred.parse((ROOT / "fixtures" / "fred" / "TOTALSA.csv").read_text())
    assert len(real) > 400 and real[0][0] == date(1976, 1, 1) and all(5 < v < 25 for _, v in real)


def test_readings_compare_the_right_months() -> None:
    flat = [100.0] * 150
    assert dv.reading(flat, 149, "yoy") == 0.0 and dv.reading(flat, 13, "yoy") is None
    jump = [100.0] * 140 + [120.0] * 10
    assert dv.reading(jump, 149, "yoy") == pytest.approx(0.2)
    # a wave 48 months back: 12 strong months ending 48 months before the last
    wave = [100.0] * 200 + [150.0] * 12 + [100.0] * 48
    assert dv.reading(wave, len(wave) - 1, "cohort", 48) == pytest.approx(0.5)
    assert (dv.reading(wave, len(wave) - 1, "cohort", 24) or 0) < 0  # 24 months back: the wave is in the baseline
    with pytest.raises(ValueError):
        dv.reading(flat, 149, "weekly")


def test_z_scores_rank_a_reading_against_its_history_and_inverse_flips_it() -> None:
    values = [100 + (i % 12) for i in range(300)] + [160.0] * 3  # a sharp rise on a seasonal series
    z = dv.latest_z(monthly(values), "yoy")
    assert z is not None and z > 3
    assert dv.latest_z(monthly(values), "yoy", inverse=True) == -z
    assert dv.latest_z(monthly([100.0] * 50), "yoy") is None  # not enough history
    assert [dv.words(x) for x in (1.2, 0.6, 0.0, -0.7, -1.5, None)] == [
        "well above normal",
        "above normal",
        "about normal",
        "below normal",
        "well below normal",
        "not enough history",
    ]


def test_the_history_check_counts_tailwind_years() -> None:
    # the driver jumps every other year's November; the group beats the market exactly in the year after a jump
    values = []
    for y in range(2000, 2026):
        values += [100.0 + (30.0 if y % 2 == 1 and m >= 9 else 0.0) for m in range(12)]
    pts = monthly(values)
    excess = {y: (0.1 if (y - 1) % 2 == 1 else -0.05) for y in range(2012, 2026)}
    h = dv.history_check(pts, "yoy", 0, False, excess)
    assert h is not None and h["tail_years"] >= 5 and h["tail_beat"] == h["tail_years"] and h["tail_excess"] == 0.1
    assert dv.history_check(pts, "yoy", 0, False, {2020: 0.1}) is None  # too few years


def test_every_configured_driver_has_a_name_and_the_summary_reads_real_data() -> None:
    drv = dv.load(ROOT)
    assert len(drv) >= 20 and drv["MORTGAGE30US"].inverse and not drv["TOTALSA"].inverse
    s = dv.summary(fred.parse((ROOT / "fixtures" / "fred" / "TOTALSA.csv").read_text()), drv["TOTALSA"])
    assert (
        s["latest"] is not None
        and isinstance(s["yoy_z"], float)
        and set(s["cohort_z"]) == {"24", "36", "48", "60", "84"}
    )
