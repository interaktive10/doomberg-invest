"""Quarterizing rules on synthetic facts (BRIEF §4.1.3-§4.1.5)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D

from pipeline.us.companyfacts import Fact
from pipeline.us.quarterize import quarterize, rounding_equal

T0 = datetime(2024, 5, 1, tzinfo=UTC)  # Q1 10-Q
T1 = datetime(2024, 8, 1, tzinfo=UTC)  # Q2 10-Q
T2 = datetime(2024, 11, 1, tzinfo=UTC)  # Q3 10-Q
T3 = datetime(2025, 2, 20, tzinfo=UTC)  # 10-K
T4 = datetime(2025, 5, 1, tzinfo=UTC)  # next Q1 10-Q (restates last year's Q1 comparative)
FY = (date(2024, 1, 1), date(2024, 12, 31))
Q = [(date(2024, 1, 1), date(2024, 3, 31)), (date(2024, 4, 1), date(2024, 6, 30)),
     (date(2024, 7, 1), date(2024, 9, 30)), (date(2024, 10, 1), date(2024, 12, 31))]  # fmt: skip
ACC = {T0: "a0", T1: "a1", T2: "a2", T3: "a3", T4: "a4"}
FORM = {T0: "10-Q", T1: "10-Q", T2: "10-Q", T3: "10-K", T4: "10-Q"}
REPORT = {"a0": Q[0][1], "a1": Q[1][1], "a2": Q[2][1], "a3": FY[1], "a4": date(2025, 3, 31)}


def fact(col: str, start: date | None, end: date, val: int | str, t: datetime, rank: int = 0, part: int = 0) -> Fact:
    return Fact(col, rank, part, start, end, D(str(val)), ACC[t], FORM[t], 2024, "FY" if FORM[t] == "10-K" else "Q1", t)


def base_year(col: str = "revenue", q: tuple[int, int, int] = (100, 110, 120), fy: int = 460) -> list[Fact]:
    """Quarters from 3-month values, then the 10-K's FY value (Q4 = 460 - 330 = 130)."""
    return [fact(col, *Q[0], q[0], T0), fact(col, *Q[1], q[1], T1), fact(col, *Q[2], q[2], T2), fact(col, *FY, fy, T3)]


def latest(rows):
    return {r.period_end: r for r in rows}


def year_end_assets(t: datetime = T3) -> Fact:
    """A balance-sheet value at FY end, so the Q4 row exists even when every flow in it is nulled."""
    return fact("total_assets", None, FY[1], 1000, t)


def test_q4_is_fy_minus_q1_q2_q3() -> None:
    rows, issues = quarterize(base_year(), REPORT)
    lat = latest(rows)
    assert [lat[q[1]].values["revenue"] for q in Q] == [D(100), D(110), D(120), D(130)]
    assert lat[Q[3][1]].filed_at == T3 and lat[Q[3][1]].fiscal_label == "FY2024Q4"
    assert issues == []


def test_ytd_values_are_differenced() -> None:
    cfo = [fact("cfo", *Q[0], 50, T0), fact("cfo", FY[0], Q[1][1], 130, T1), fact("cfo", FY[0], Q[2][1], 200, T2),
           fact("cfo", *FY, 290, T3)]  # fmt: skip
    lat = latest(quarterize(cfo, REPORT)[0])
    assert [lat[q[1]].values["cfo"] for q in Q] == [D(50), D(80), D(70), D(90)]


def test_instants_taken_as_reported() -> None:
    facts = [*base_year(), fact("total_assets", None, Q[1][1], 999, T1), fact("total_assets", None, FY[1], 1001, T3)]
    lat = latest(quarterize(facts, REPORT)[0])
    assert lat[Q[1][1]].values["total_assets"] == D(999) and lat[FY[1]].values["total_assets"] == D(1001)
    assert lat[Q[0][1]].values["total_assets"] is None


def test_values_are_point_in_time() -> None:
    """A row filed at T0 cannot contain anything accepted later."""
    rows, _ = quarterize(base_year(), REPORT)
    first = [r for r in rows if r.period_end == Q[0][1]][0]
    assert first.filed_at == T0 and first.values["revenue"] == D(100)
    assert not any(r.period_end == Q[3][1] and r.filed_at < T3 for r in rows)


def test_restatement_adds_a_row_and_keeps_the_old_one() -> None:
    facts = [*base_year(), fact("revenue", *Q[0], 105, T4)]  # next year's 10-Q restates the Q1 comparative
    rows, _ = quarterize(facts, REPORT)
    q1 = [r for r in rows if r.period_end == Q[0][1]]
    assert [(r.filed_at, r.values["revenue"]) for r in q1] == [(T0, D(100)), (T4, D(105))]
    q4 = [r for r in rows if r.period_end == Q[3][1]]
    assert [(r.filed_at, r.values["revenue"]) for r in q4] == [(T3, D(130)), (T4, D(125))]  # derived Q4 follows


def test_rounding_only_change_is_not_a_restatement() -> None:
    facts = [*base_year(), fact("total_debt", None, Q[0][1], 105103000000, T0),
             fact("total_debt", None, Q[0][1], 105100000000, T1)]  # fmt: skip
    rows, _ = quarterize(facts, REPORT)
    assert [r.values["total_debt"] for r in rows if r.period_end == Q[0][1]] == [D(105103000000)]
    assert rounding_equal(D(29068000), D(29000000)) and not rounding_equal(D(12000000), D(11000000))


def test_q4_sanity_check_nulls_outliers() -> None:
    rows, issues = quarterize([*base_year(q=(10, 10, 10), fy=500), year_end_assets()], REPORT)  # 470 > 3 x 10
    assert latest(rows)[Q[3][1]].values["revenue"] is None
    assert [(i.period_end, i.column) for i in issues] == [(Q[3][1], "revenue")]


def test_negative_revenue_and_nonpositive_shares_are_nulled() -> None:
    facts = [fact("revenue", *Q[0], -5, T0), fact("diluted_shares", *Q[0], 0, T0), fact("op_income", *Q[0], 3, T0)]
    rows, issues = quarterize(facts, REPORT)
    vals = latest(rows)[Q[0][1]].values
    assert vals["revenue"] is None and vals["diluted_shares"] is None and vals["op_income"] == D(3)
    assert {i.column for i in issues} == {"revenue", "diluted_shares"}


def test_diluted_shares_q4_average_and_split_guard() -> None:
    ok = base_year("diluted_shares", q=(100, 100, 100), fy=100)
    assert latest(quarterize(ok, REPORT)[0])[Q[3][1]].values["diluted_shares"] == D(100)  # 4 x 100 - 300
    mixed = [*base_year("diluted_shares", q=(10, 100, 100), fy=100), year_end_assets()]  # Q1 pre-split basis
    rows, issues = quarterize(mixed, REPORT)
    assert latest(rows)[Q[3][1]].values["diluted_shares"] is None
    assert "different bases" in issues[0].reason


def test_concept_fallback_is_per_period() -> None:
    facts = [fact("revenue", *Q[0], 100, T0, rank=2), fact("revenue", *Q[1], 110, T1, rank=0)]
    lat = latest(quarterize(facts, REPORT)[0])
    assert lat[Q[0][1]].values["revenue"] == D(100) and lat[Q[1][1]].values["revenue"] == D(110)


def test_summed_alternative_needs_its_first_part() -> None:
    e = Q[0][1]
    facts = [
        *base_year(),
        fact("total_debt", None, e, 70, T0, rank=3, part=0),
        fact("total_debt", None, e, 10, T0, rank=3, part=1),
        fact("total_debt", None, e, 5, T0, rank=0, part=1),
    ]  # rank 0 has only an optional part: skipped
    assert latest(quarterize(facts, REPORT)[0])[e].values["total_debt"] == D(80)
