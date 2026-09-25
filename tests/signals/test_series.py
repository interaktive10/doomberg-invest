"""Shared definitions of BRIEF §4.6 (pipeline/signals/series.py): TTM, India half-yearly items, tax, IC, ROIC."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from pipeline.signals.series import Quarter, Series

ENDS = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31)]


def q(end: date, **v: str | None) -> Quarter:
    return Quarter(end, {k: None if x is None else D(x) for k, x in v.items()})


def test_ttm_needs_four_consecutive_quarters() -> None:
    s = Series([q(e, revenue="100") for e in ENDS], "us")
    assert s.ttm("revenue") == D(400) and s.ttm("revenue", 1) == D(400) and s.ttm("revenue", 2) is None
    gap = Series([q(e, revenue="100") for e in (ENDS[0], ENDS[1], ENDS[3], ENDS[4], date(2026, 6, 30))], "us")
    assert gap.ttm("revenue", 1) is None  # 2025-09-30 is missing: the window spans a year and a quarter
    hole = Series([q(e, revenue=None if e == ENDS[2] else "100") for e in ENDS], "us")
    assert hole.ttm("revenue") is None  # a null quarter makes the US TTM unknown


def test_india_half_yearly_flows_and_points() -> None:
    """Q2 row = H1 cash flow, Q4 row = H2; balance sheet on those rows only (M3)."""
    rows = [
        q(date(2025, 6, 30), cfo=None, cash=None),  # Q1 FY26
        q(date(2025, 9, 30), cfo="60", cash="500"),  # Q2: H1
        q(date(2025, 12, 31), cfo=None, cash=None),  # Q3
        q(date(2026, 3, 31), cfo="90", cash="700"),  # Q4: H2
        q(date(2026, 6, 30), cfo=None, cash=None),  # Q1 FY27
    ]
    s = Series(rows, "in")
    assert s.ttm("cfo", 0) == D(150) and s.ttm("cfo", 1) == D(150)  # H1 + H2 in both windows
    assert s.point("cash", 0) == D(700) and s.point("cash", 1) == D(700) and s.point("cash", 2) == D(500)
    us = Series(rows, "us")
    assert us.ttm("cfo", 0) is None and us.point("cash", 0) is None  # no half-year rule outside India


def test_tax_rate_clip_and_default() -> None:
    s = Series([q(e, pretax_income="100", tax_expense="50") for e in ENDS], "us")
    assert s.tax_rate() == D("0.35")
    low = Series([q(e, pretax_income="100", tax_expense="1") for e in ENDS], "us")
    assert low.tax_rate() == D("0.10")
    loss = Series([q(e, pretax_income="-10", tax_expense="1") for e in ENDS], "in")
    assert loss.tax_rate() == D("0.25")  # pretax <= 0: the market default (IN 0.25, US 0.21)


def test_invested_capital_floor_and_missing_debt() -> None:
    s = Series([q(ENDS[0], equity="100", cash="1000", total_assets="10000", total_debt=None)], "us")
    assert s.invested_capital() == D(500)  # 100 - 1000 floored at 0.05 x 10000; no debt concept counts as none
    assert s.net_debt() is None  # but leverage rules need a real debt figure
    none = Series([q(ENDS[0], equity=None, cash="1", total_assets="10")], "us")
    assert none.invested_capital() is None


def test_roic_uses_mean_ic_over_four_quarters() -> None:
    rows = [q(e, op_income="25", pretax_income="25", tax_expense="5", equity=str(900 + 100 * i), cash="0",
              total_debt="0", total_assets="2000") for i, e in enumerate(ENDS)]  # fmt: skip
    s = Series(rows, "us")
    assert s.nopat() == D(80)  # 100 x (1 - 0.20)
    assert s.roic() == D(80) / D(1150)  # mean of 1000, 1100, 1200, 1300


def test_quarterly_yoy_needs_the_same_quarter_a_year_back() -> None:
    s = Series([q(e, revenue=str(100 + 10 * i)) for i, e in enumerate(ENDS)], "us")
    assert s.quarterly_yoy("revenue") == D("0.4")  # 140 vs 100
    assert s.quarterly_yoy("revenue", 1) is None
