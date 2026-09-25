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
    assert s.invested_capital() == D(500)  # 100 - 1000 floored at 0.05 x 10000; no debt concept anywhere: none
    assert s.net_debt() == D(-1000)  # the same rule for leverage: net cash
    none = Series([q(ENDS[0], equity=None, cash="1", total_assets="10")], "us")
    assert none.invested_capital() is None


def test_unreported_debt_is_the_last_reported_figure_never_zero() -> None:
    """M4 review R1-F1: CAT and ORCL tag debt only in 10-Ks. A 10-Q quarter without a debt figure reads the last one
    reported within a year; IC, net debt and EV use it (ORCL's IC isn't $30B instead of $160B)."""
    from pipeline.signals import context

    base = {"equity": "100", "cash": "50", "total_assets": "1000", "revenue": "100", "op_income": "20"}
    rows = [q(e, **base, total_debt="500" if i == 1 else None) for i, e in enumerate(ENDS)]  # the 10-K is lag 3
    s = Series(rows, "us")
    assert s.debt(0) == D(500) and s.invested_capital(0) == D(550) and s.net_debt(0) == D(450)
    ev, _, _ = context.multiples(s, D(1000))
    assert ev == D(1450)  # 1000 + 500 - 50, not 1000 - 50
    stale = Series([q(date(2022, 3, 31), **base, total_debt="500"), *[q(e, **base) for e in ENDS]], "us")
    assert stale.debt(0) is None and stale.invested_capital(0) is None  # reported, but not within a year
    assert context.multiples(stale, D(1000)) == (None, None, None)
    never = Series([q(e, **base) for e in ENDS], "us")
    assert never.debt(0) == D(0) and context.multiples(never, D(1000))[0] == D(950)  # no borrowings: no debt


def test_year_back_comparisons_need_a_year_back() -> None:
    """M4 review R1-F8: with a quarter missing, the row four back is 15 months back: no YoY."""
    ends = [date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31),  # 2025-06-30 missing
            date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]  # fmt: skip
    s = Series([q(e, revenue="100" if e < date(2025, 9, 30) else "200", receivables="10") for e in ends], "us")
    assert not s.year_back_ok(0) and s.ttm_yoy("revenue") is None and s.quarterly_yoy("revenue") is None
    assert Series([q(e, revenue="100") for e in ENDS], "us").year_back_ok(0)  # 2026-03-31 vs 2025-03-31


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
