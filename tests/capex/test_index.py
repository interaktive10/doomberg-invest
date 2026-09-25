"""M5-05: the demand index and its direction on synthetic inputs (BRIEF §4.11)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D

import pytest
import yaml

from pipeline.capex.index import Panel, categories, direction, input_stat, yoy
from pipeline.settings import REPO_ROOT

CFG = yaml.safe_load((REPO_ROOT / "config" / "categories.yaml").read_text(encoding="utf-8"))
WEEK = date(2026, 9, 25)


def growing(rate_then: float, rate_now: float, switch_weeks_ago: int = 20):
    """A weekly level compounding at `rate_then` a year, and at `rate_now` for the last `switch_weeks_ago` weeks."""
    switch = WEEK - timedelta(weeks=switch_weeks_ago)

    def level(d: date) -> D:
        weeks_before = (switch - d).days / 7
        if weeks_before >= 0:
            v = 100 * (1 + rate_then) ** (-weeks_before / 52)
        else:
            v = 100 * (1 + rate_now) ** (-weeks_before / 52)
        return D(str(round(v, 6)))

    return level


def test_accelerating_input_rises_and_decelerating_falls() -> None:
    up = input_stat("x", growing(0.10, 0.60), WEEK, 156, 12)
    down = input_stat("y", growing(0.30, -0.10), WEEK, 156, 12)
    steady = input_stat("z", growing(0.20, 0.20), WEEK, 156, 12)
    assert up.z is not None and up.z > D("0.5") and up.yoy is not None and up.yoy > D("0.2")
    assert down.z is not None and down.z < D("-0.5")
    assert steady.z is None  # no spread in its YoY history: z undefined, not a signal
    assert up.history == 156


def test_category_value_is_the_mean_z_and_direction_uses_the_sigma_thresholds() -> None:
    stats = {
        "utility_large_load_gw": input_stat("utility_large_load_gw", growing(0.10, 0.60), WEEK, 156, 12),
        "lead_time_transformers": input_stat("lead_time_transformers", growing(0.30, -0.10), WEEK, 156, 12),
        "hyperscaler_capex_guidance": input_stat("hyperscaler_capex_guidance", growing(0.1, 0.6), WEEK, 156, 12),
    }
    rows = {c.category: c for c in categories(stats, CFG)}
    grid = rows["grid"]  # inputs: large load (z up), transformers (z down), switchgear (missing)
    zs = [stats["utility_large_load_gw"].z, stats["lead_time_transformers"].z]
    assert grid.value == (sum(zs, D(0)) / 2).quantize(D("0.0001"))
    assert rows["compute"].direction == "rising" and rows["compute"].input_growth is not None
    assert "lead_time_switchgear" not in grid.inputs


@pytest.mark.parametrize(("value", "expected"), [(D("0.5"), "rising"), (D("0.4999"), "flat"), (D("-0.5"), "falling"),
                                                 (None, "flat")])  # fmt: skip
def test_direction_thresholds(value: D | None, expected: str) -> None:
    assert direction(value, CFG["direction"]) == expected


def test_short_history_gives_no_z() -> None:
    def level(d: date) -> D | None:
        return D(100) if d >= WEEK - timedelta(weeks=60) else None

    s = input_stat("new", level, WEEK, 156, 12)
    assert s.z is None and s.history < 12


def test_panel_yoy_compares_the_same_companies() -> None:
    then = Panel({"MSFT": D(60), "META": D(40)})
    now = Panel({"MSFT": D(75), "META": D(50), "ORCL": D(35)})  # ORCL entering the ledger is not growth
    assert yoy(now, then) == D("0.25")
    assert yoy(D(12), D(10)) == D("0.2") and yoy(None, D(1)) is None and yoy(now, D(1)) is None
