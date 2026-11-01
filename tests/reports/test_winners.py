"""Last year's winners (pipeline/reports/winners.py; docs/SPEC_ISSUES.md 64): the year's top gainers among names that
were investable, point-in-time shares, bad prints sat out, and the previous-year-winners backtest."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pipeline.db.models import Company, FundamentalsRow
from pipeline.reports import winners as w


def months(start_year: int, closes: list[float]) -> list[tuple[date, Decimal]]:
    """Month-end closes from December of start_year - 1."""
    out = []
    y, m = start_year - 1, 12
    for c in closes:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        out.append((date.fromordinal(nxt.toordinal() - 1), Decimal(str(c))))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def shares(cid: UUID, n: float, filed: date = date(2015, 1, 15)) -> FundamentalsRow:
    return FundamentalsRow(company_id=cid, period_end=date(filed.year - 1, 12, 31), fiscal_label="Q4",
                           filed_at=datetime(filed.year, filed.month, filed.day, tzinfo=UTC),
                           diluted_shares=Decimal(str(n)), currency="USD", source="sec_xbrl")  # fmt: skip


def linear(start: float, end: float, n: int = 13) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def test_the_top_gainers_are_the_investable_ones() -> None:
    ids = [uuid4() for _ in range(9)]
    big = 1e9  # shares: any of these is above $1B at $5
    series = {ids[i]: months(2020, linear(10, 10 * (1 + i / 10))) for i in range(6)}  # +0% .. +50%
    series[ids[6]] = months(2020, linear(2, 40))  # +1900% from $2: under MIN_PRICE at the start
    series[ids[7]] = months(2020, linear(10, 100))  # +900% but $1M of shares: too small at the end
    series[ids[8]] = months(2020, [10] * 6 + [60] * 7)  # one month up 500%: a bad print, sits out
    versions = {cid: [shares(cid, big, date(2019, 2, 1))] for cid in ids}
    versions[ids[7]] = [shares(ids[7], 10_000, date(2019, 2, 1))]
    picks = w.year_winners(series, versions, "us", 2020)
    assert [p.company_id for p in picks] == [ids[5], ids[4], ids[3], ids[2], ids[1]]
    assert picks[0].ret == pytest.approx(0.5) and picks[0].start == Decimal(10)


def test_shares_filed_after_the_year_end_are_not_known() -> None:
    cid = uuid4()
    series = {cid: months(2020, linear(10, 20))}
    late = {cid: [shares(cid, 1e9, date(2021, 2, 1))]}  # filed after 2020-12-31: not known when 2020 ended
    assert w.year_winners(series, late, "us", 2020) == []
    assert w.shares_at({cid: [shares(cid, 5, date(2019, 1, 1)), shares(cid, 7, date(2020, 6, 1))]},
                       datetime(2020, 12, 31, tzinfo=UTC)) == {cid: Decimal(7)}  # fmt: skip


def test_india_closes_within_ten_days_of_the_year_end() -> None:
    cid = uuid4()
    s = [(date(2023, 12, 29), Decimal(100)), (date(2024, 6, 28), Decimal(180)), (date(2024, 12, 27), Decimal(250))]
    assert w.close_at(s, date(2024, 12, 31), w.TOLERANCE_DAYS["in"]) == Decimal(250)
    assert w.close_at(s, date(2024, 12, 31), w.TOLERANCE_DAYS["us"]) is None
    row = shares(cid, 1e9, date(2023, 6, 1)).model_copy(update={"currency": "INR", "source": "nse_xbrl"})
    picks = w.year_winners({cid: s}, {cid: [row]}, "in", 2024)
    assert len(picks) == 1 and picks[0].ret == pytest.approx(1.5)
    doubled = [*s[:2], (date(2024, 7, 5), Decimal(400)), (date(2024, 12, 27), Decimal(450))]  # a week up 122%
    assert w.year_winners({cid: doubled}, {cid: [row]}, "in", 2024) == []


def test_the_backtest_buys_last_years_winners_and_compares_with_the_average() -> None:
    """60 flat names and 5 that rise 50% a year from 2016 on: from 2017 the previous year's winners are those five."""
    flat = {uuid4(): months(2015, [20.0] * 61) for _ in range(60)}
    risers = {uuid4(): months(2015, [20.0] * 13 + [20 * 1.5 ** ((i + 1) / 12) for i in range(48)]) for _ in range(5)}
    series = {**flat, **risers}
    versions = {cid: [shares(cid, 1e9, date(2014, 2, 1))] for cid in series}
    rows = w.backtest(series, versions, "us", 2017, 2019)
    assert [r["year"] for r in rows] == [2017, 2018, 2019]
    assert all(r["ret"] == pytest.approx(0.5) and r["stocks"] == 65 for r in rows)
    assert set(rows[0]["picks"]) == {str(c) for c in risers}
    s = w.summary(rows)
    assert s is not None and s["beat"] == 3 and s["cagr"] == pytest.approx(0.5) and s["growth"] == pytest.approx(3.375)
    assert s["average_cagr"] == pytest.approx(rows[0]["average"]) and w.summary([]) is None


def test_the_market_report_shows_this_year_so_far() -> None:
    ids = [uuid4() for _ in range(6)]
    series = {cid: months(2025, linear(10, 10 + i, 13) + [10 + i + 2.0] * 6) for i, cid in enumerate(ids)}
    versions = {cid: [shares(cid, 1e9, date(2024, 2, 1))] for cid in ids}
    companies = {cid: Company(id=cid, market="us", name=f"Co {i}", ticker=f"C{i}", sector="Tech")
                 for i, cid in enumerate(ids)}  # fmt: skip
    m = w.market_report("us", companies, series, versions, date(2026, 7, 10), universe=6)
    assert m["year"] == 2025 and [t["code"] for t in m["top"]] == ["C5", "C4", "C3", "C2", "C1"]
    assert m["this_year"]["through"] == "2026-06-30" and m["top"][0]["ytd"] == pytest.approx(2 / 15)
    assert m["backtest"] is None  # too few names to compare with
