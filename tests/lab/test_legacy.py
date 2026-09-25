"""Legacy Doomberg rules L1-L6 (BRIEF §4.10.4, docs/DOOMBERG_AUDIT.md §5): each threshold on both sides."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from pipeline.lab import legacy_doomberg as legacy

BASE = legacy.LegacyInputs(market="us", ret_12m=0.10, drawdown=-0.20, above_low=0.30, fcf_ttm=D(5), net_debt=D(10),
                           net_debt_year_ago=D(20), pe=12.0, revenue_yoy=D("0.05"), market_cap=1e9)  # fmt: skip
CROSS = legacy.LegacyCross(pe_tercile_max=15.0, ret_top_decile_min=0.50)


def fired(**kw: object) -> dict[str, bool]:
    return legacy.evaluate(replace(BASE, **kw), CROSS)  # type: ignore[arg-type]


@pytest.mark.parametrize(("ret", "want"), [(0.80, True), (0.8001, False), (-0.92, False), (-0.9199, True)])
def test_l1_not_ripped_not_broken(ret: float, want: bool) -> None:
    assert fired(ret_12m=ret)["L1"] is want


L2_CASES = [(-0.70, D(1), D(10), True), (-0.95, D(1), D(10), True), (-0.69, D(1), D(10), False),
            (-0.96, D(1), D(10), False), (-0.80, D(0), D(10), False), (-0.80, D(1), D(20), False)]  # fmt: skip


@pytest.mark.parametrize(("dd", "fcf", "nd", "want"), L2_CASES)
def test_l2_wreckage_survivor(dd: float, fcf: D, nd: D, want: bool) -> None:
    assert fired(drawdown=dd, fcf_ttm=fcf, net_debt=nd)["L2"] is want


def test_l3_cheap_and_growing() -> None:
    assert fired(pe=15.0)["L3"] and not fired(pe=15.01)["L3"]
    assert not fired(revenue_yoy=D(0))["L3"] and not fired(pe=None)["L3"]


def test_l4_near_the_low_with_fcf() -> None:
    assert (
        fired(above_low=0.10)["L4"]
        and not fired(above_low=0.1001)["L4"]
        and not fired(above_low=0.05, fcf_ttm=D(-1))["L4"]
    )


def test_l5_small_cap_momentum() -> None:
    assert fired(market_cap=1.99e9, ret_12m=0.50)["L5"] and not fired(market_cap=2e9, ret_12m=0.50)["L5"]
    assert not fired(market_cap=1e9, ret_12m=0.49)["L5"]


def test_l6_size_band() -> None:
    assert fired(market_cap=250e6)["L6"] and fired(market_cap=35e9)["L6"]
    assert not fired(market_cap=249e6)["L6"] and not fired(market_cap=36e9)["L6"]
    assert fired(market="in", market_cap=50_000e7)["L6"] and not fired(market="in", market_cap=50_001e7)["L6"]


def test_missing_inputs_do_not_fire() -> None:
    empty = legacy.LegacyInputs("us", None, None, None, None, None, None, None, None, None)
    assert not any(legacy.evaluate(empty, legacy.LegacyCross(None, None)).values())


def test_cross_section_thresholds() -> None:
    xs = [replace(BASE, pe=float(p), ret_12m=r / 10) for p, r in zip(range(1, 10), range(10), strict=False)]
    cross = legacy.cross_section([*xs, replace(BASE, pe=-5.0)])  # a negative P/E doesn't count
    # P/Es 1..9 (the -5 is out): the tercile bound is 1 + 8/3. Returns 0.0-0.8 plus the extra row's 0.1: the 90th
    # percentile interpolates between 0.7 and 0.8
    assert cross.pe_tercile_max == pytest.approx(1 + 8 / 3) and cross.ret_top_decile_min == pytest.approx(0.71)
