"""M4-04 (split detection): a price jump is adjusted only when the share count confirms it (BRIEF §4.4)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D

from pipeline.prices.splits import adjust, split_ratio

FRIDAYS = [date(2026, 1, 2) + timedelta(weeks=i) for i in range(20)]


def closes(split_week: int | None, ratio: str = "2") -> list[tuple[date, D]]:
    after = split_week if split_week is not None else len(FRIDAYS)
    return [(d, D(100) / (D(ratio) if i >= after else 1)) for i, d in enumerate(FRIDAYS)]


QUARTERS = [date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]


def test_standard_ratios() -> None:
    assert split_ratio(D("2.02")) == D(2) and split_ratio(D("1.49")) == D("1.5") and split_ratio(D("0.1")) == D("0.1")
    assert split_ratio(D("1.8")) is None and split_ratio(D("1.1")) is None


def test_confirmed_split_adjusts_history() -> None:
    shares = list(zip(QUARTERS, (D(100), D(100), D(200)), strict=True))  # doubled by the June quarter
    a = adjust(closes(10), shares)  # the price halves in week 10 (2026-03-13)
    assert [j.week_end for j in a.confirmed] == [FRIDAYS[10]] and a.unconfirmed == []
    assert {v for v in a.adj_close.values()} == {D(50)}  # one continuous series on today's basis
    assert a.share_factor(date(2026, 3, 31)) == D(2) and a.share_factor(date(2026, 6, 30)) == D(1)


def test_unconfirmed_jump_is_flagged_not_adjusted() -> None:
    shares = list(zip(QUARTERS, (D(100), D(100), D(101)), strict=True))  # no share-count change: a crash, not a split
    a = adjust(closes(10), shares)
    assert a.confirmed == [] and [j.week_end for j in a.unconfirmed] == [FRIDAYS[10]]
    assert a.adj_close[FRIDAYS[0]] == D(100)  # never silently adjusted


def test_split_without_a_price_jump_means_prices_were_already_adjusted() -> None:
    """Stooq's history is split-adjusted: no jump, but older share counts move to today's basis."""
    shares = list(zip(QUARTERS, (D(100), D(100), D(300)), strict=True))
    a = adjust(closes(None), shares)
    assert a.confirmed == [] and a.unconfirmed == [] and a.adj_close[FRIDAYS[0]] == D(100)
    assert a.share_factor(date(2025, 12, 31)) == D(3)


def test_bonus_issue_one_for_one_and_a_consolidation() -> None:
    bonus = adjust(closes(5, "2"), list(zip(QUARTERS, (D(10), D(20), D(20)), strict=True)))
    assert len(bonus.confirmed) == 1
    merge = [(d, D(10) * (10 if i >= 5 else 1)) for i, d in enumerate(FRIDAYS)]  # 1:10 consolidation
    cons = adjust(merge, list(zip(QUARTERS, (D(1000), D(100), D(100)), strict=True)))
    assert [j.ratio for j in cons.confirmed] == [D("0.1")] and cons.adj_close[FRIDAYS[0]] == D(100)
