"""Recent daily closes for Winners and Themes (docs/SPEC_ISSUES.md 75: "why does it say sep 30? ... everything should be
latest"): only what is missing is fetched, stalest first, and the closes extend the month-end and week-end series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pipeline.net.twelvedata import TwelveDataDayCredits, TwelveDataNoSuchSymbol
from pipeline.reports import closes as cl

D = Decimal


def test_merge_keeps_the_latest_and_lets_a_new_close_win() -> None:
    old = [(date(2026, 10, d), D(d)) for d in range(1, 9)]
    new = [(date(2026, 10, 8), D(80)), (date(2026, 10, 9), D(9)), (date(2026, 10, 12), D(12))]
    got = cl.merge(old, new, keep=5)
    assert got == [(date(2026, 10, 6), D(6)), (date(2026, 10, 7), D(7)), (date(2026, 10, 8), D(80)),
                   (date(2026, 10, 9), D(9)), (date(2026, 10, 12), D(12))]  # fmt: skip


def test_extend_appends_only_closes_after_the_series_end() -> None:
    months = [(date(2026, 8, 31), D(10)), (date(2026, 9, 30), D(11))]
    recent = [(date(2026, 9, 29), D(99)), (date(2026, 10, 29), D(12)), (date(2026, 10, 30), D(13))]
    assert cl.extend(months, recent) == [*months, (date(2026, 10, 29), D(12)), (date(2026, 10, 30), D(13))]
    assert cl.extend([], recent) == recent and cl.extend(months, []) == months


def test_the_stalest_tickers_are_asked_first() -> None:
    recent = {"AAA": [(date(2026, 10, 30), D(1))], "BBB": [(date(2026, 10, 28), D(1))]}
    assert cl.stalest(["AAA", "BBB", "CCC", "DDD"], recent, 3) == ["CCC", "DDD", "BBB"]


@dataclass
class Asker:
    stop_after: int = 99

    def __post_init__(self) -> None:
        self.asked: list[str] = []

    def __call__(self, t: str) -> list[tuple[date, Decimal]]:
        self.asked.append(t)
        if len(self.asked) > self.stop_after:
            raise TwelveDataDayCredits("spent")
        if t == "GONE":
            raise TwelveDataNoSuchSymbol("no series")
        return [(date(2026, 10, 29), D(10)), (date(2026, 10, 30), D(11))]


def test_refresh_us_stops_on_spent_credits_and_counts_failures() -> None:
    r, stats, ask = cl.Recent(), cl.Stats(), Asker(stop_after=2)
    cl.refresh_us(ask, ["AAA", "GONE", "CCC", "DDD"], r, budget=10, minutes=60, stats=stats)
    assert ask.asked == ["AAA", "CCC", "DDD"]  # never asked: by ticker; the third finds the day spent
    assert stats.us_ok == 2 and stats.us_stopped == "the day's credits are spent" and set(r.us) == {"AAA", "CCC"}


def test_refresh_us_respects_the_budget_and_the_clock() -> None:
    r, stats, ask = cl.Recent(), cl.Stats(), Asker()
    cl.refresh_us(ask, ["A", "B", "C"], r, budget=2, minutes=60, stats=stats)
    assert ask.asked == ["A", "B"] and stats.us_ok == 2
    s1 = cl.Stats()
    cl.refresh_us(Asker(), ["GONE", "OK"], cl.Recent(), budget=5, minutes=60, stats=s1)
    assert s1.us_failed == 1 and s1.us_ok == 1
    ticks = iter([0.0, 0.0, 9999.0])
    r2, s2, ask2 = cl.Recent(), cl.Stats(), Asker()
    cl.refresh_us(ask2, ["A", "B"], r2, budget=5, minutes=1, stats=s2, clock=lambda: next(ticks))
    assert ask2.asked == ["A"] and s2.us_stopped == "past 1 minutes"


@dataclass(frozen=True)
class Row:
    symbol: str
    trade_date: date
    close: Decimal | None


def test_refresh_india_and_the_stored_form_round_trips() -> None:
    r, stats = cl.Recent(), cl.Stats()
    cl.refresh_india([Row("TARAPUMP", date(2026, 11, 2), D("812.5")), Row("ZERO", date(2026, 11, 2), D(0))],
                     date(2026, 11, 2), r, stats)  # fmt: skip
    assert r.india == {"TARAPUMP": [(date(2026, 11, 2), D("812.5"))]} and stats.india_rows == 1
    r.us["AAPL"] = [(date(2026, 10, 30), D("270.37"))]
    assert cl.Recent.from_json(r.to_json()) == r


def test_the_upcoming_friday() -> None:
    assert cl.upcoming_friday(date(2026, 11, 2)) == date(2026, 11, 6)  # Monday
    assert cl.upcoming_friday(date(2026, 11, 6)) == date(2026, 11, 6)  # Friday itself


def test_refresh_us_saves_as_it_goes() -> None:
    """A run cut off by the job's limit keeps what it fetched: a save every SAVE_EVERY answers."""
    saves: list[int] = []
    r, stats = cl.Recent(), cl.Stats()
    tickers = [f"T{i:03d}" for i in range(2 * cl.SAVE_EVERY + 5)]
    cl.refresh_us(
        Asker(), tickers, r, budget=len(tickers), minutes=60, stats=stats, save=lambda: saves.append(len(r.us))
    )
    assert saves == [cl.SAVE_EVERY, 2 * cl.SAVE_EVERY]
