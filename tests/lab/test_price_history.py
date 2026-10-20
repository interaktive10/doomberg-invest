"""The Lab's price history from Twelve Data (pipeline/lab/price_history.py, docs/SPEC_ISSUES.md 51), on a stand-in for
the client with a fake clock: the probe, the resumable state, the per-ticker outcomes, the stops and the runs row."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest

from pipeline.lab import price_history as ph
from pipeline.lab import run
from pipeline.lab.prices import DownloadState, MonthBar, TickerState, read_prices
from pipeline.net.twelvedata import (
    Close,
    TwelveDataDayCredits,
    TwelveDataNoSuchSymbol,
    TwelveDataUnavailable,
    parse_closes,
)

TD = Path(__file__).resolve().parents[2] / "fixtures" / "px" / "twelvedata"
CLOSES = parse_closes((TD / "daily_AAPL.json").read_bytes())  # 2010-01-04 .. 2026-10-16
TODAY = date(2026, 10, 20)
REACH = date(2010, 1, 31)  # config/lab.yaml start
Answer = list[Close] | Exception


@dataclass
class Fake:
    """Answers per (interval, ticker) or per ticker, in order, the last one repeated (CLOSES when none is given);
    every request advances the clock by `step` seconds (the HTTP client's 8 s between Twelve Data requests)."""

    answers: dict[Any, list[Answer]] = field(default_factory=dict)
    step: float = 8.0
    now: float = 0.0
    asked: list[tuple[str, str]] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def _ask(self, interval: str, ticker: str) -> list[Close]:
        self.asked.append((interval, ticker))
        self.now += self.step
        seq = self.answers.get((interval, ticker)) or self.answers.get(ticker) or [CLOSES]
        answer = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def daily(self, ticker: str) -> list[Close]:
        return self._ask("1day", ticker)

    def monthly(self, ticker: str) -> list[Close]:
        return self._ask("1month", ticker)

    def tickers(self) -> list[str]:
        return [t for _, t in self.asked]


def go(fake: Fake, tickers: list[str], tmp: Path, limits: ph.Limits | None = None) -> ph.Outcome:
    return ph.download(fake, tickers, tmp / "state.json", tmp / "prices.csv.gz", TODAY, REACH, "AAPL",
                       limits or ph.Limits(), fake.clock)  # fmt: skip


def state(tmp: Path) -> DownloadState:
    s = DownloadState.load(tmp / "state.json")
    assert s is not None
    return s


def test_the_month_end_close_and_the_current_month_dropped(tmp_path: Path) -> None:
    """Each month's bar is its last close, with its highest and lowest close; October 2026 isn't over on the 20th."""
    out = go(Fake(), ["AAPL"], tmp_path)
    assert out.state.status == "complete" and out.state.interval == "1day" and out.credits == 2  # probe + AAPL
    bars = read_prices(tmp_path / "prices.csv.gz")["AAPL"]
    assert [b.month_end for b in bars] == [date(2010, 1, 31), date(2010, 2, 28), date(2026, 9, 30)]
    assert bars[0] == MonthBar(date(2010, 1, 31), D("6.8593"), D("7.6432"), D("6.8593"))
    assert bars[-1] == MonthBar(date(2026, 9, 30), D("241.05"), D("241.05"), D("229.4"))


def test_the_limits_are_config_labs() -> None:
    """lab-prices.yml's job limit is 120 minutes and the free plan's day 800 credits."""
    assert ph.Limits.of(run.lab_config()["prices"]) == ph.Limits(90, 650, 3, 50) == ph.Limits()


def test_a_run_resumes_within_its_credits(tmp_path: Path) -> None:
    tickers = [f"T{i:02d}" for i in range(10)]
    fake = Fake()
    first = go(fake, tickers, tmp_path, ph.Limits(max_credits=4))
    assert first.stopped == "credits" and first.credits == 4 and state(tmp_path).status == "partial"
    assert fake.asked == [("1day", "AAPL"), ("1day", "T00"), ("1day", "T01"), ("1day", "T02")]
    assert run.blocked_reason(tmp_path / "prices.csv.gz", state(tmp_path), run.lab_config()) == (
        "the Twelve Data download has 3 of 10 tickers; lab-prices.yml resumes it Sunday to Thursday and starts the "
        "Lab once every ticker is done")  # fmt: skip
    fake.asked.clear()
    second = go(fake, tickers, tmp_path, ph.Limits(max_credits=4))  # the probe isn't asked again
    assert fake.tickers() == ["T03", "T04", "T05", "T06"] and second.state.status == "partial"
    fake.asked.clear()
    third = go(fake, tickers, tmp_path, ph.Limits(max_credits=4))
    assert fake.tickers() == ["T07", "T08", "T09"] and third.state.status == "complete" and third.stopped is None
    assert sorted(read_prices(tmp_path / "prices.csv.gz")) == tickers
    assert run.blocked_reason(tmp_path / "prices.csv.gz", state(tmp_path), run.lab_config()) is None


def test_no_such_symbol_is_never_asked_again(tmp_path: Path) -> None:
    fake = Fake({"GONE": [TwelveDataNoSuchSymbol("404: **symbol** not found: GONE")]})
    out = go(fake, ["GONE", "OK"], tmp_path)
    assert fake.tickers().count("GONE") == 1 and out.state.status == "complete"
    assert out.state.tickers["GONE"] == TickerState("no_such_symbol", 0, "404: **symbol** not found: GONE")
    fake.asked.clear()
    go(fake, ["GONE", "OK"], tmp_path)
    assert fake.asked == [] and "GONE" not in read_prices(tmp_path / "prices.csv.gz")


def test_a_ticker_is_an_error_after_three_failed_attempts(tmp_path: Path) -> None:
    """Attempts are kept across runs; a failed ticker is asked again after the ones not yet asked."""
    fake = Fake({"BAD": [TwelveDataUnavailable("502: bad gateway")]})
    go(fake, ["BAD", "B", "C"], tmp_path, ph.Limits(max_credits=3))  # the probe, then by ticker
    assert fake.tickers() == ["AAPL", "B", "BAD"]
    assert state(tmp_path).tickers["BAD"] == TickerState("pending", 1, "502: bad gateway")
    fake.asked.clear()
    second = go(fake, ["BAD", "B", "C"], tmp_path, ph.Limits(max_credits=2))
    assert fake.tickers() == ["C", "BAD"] and second.state.tickers["BAD"].attempts == 2
    assert second.state.status == "partial"  # BAD has one attempt left
    fake.asked.clear()
    third = go(fake, ["BAD", "B", "C"], tmp_path)
    assert fake.tickers() == ["BAD"] and third.state.tickers["BAD"] == TickerState("error", 3, "502: bad gateway")
    assert third.state.status == "complete"
    fake.asked.clear()
    go(fake, ["BAD", "B", "C"], tmp_path)
    assert fake.asked == []


def test_the_day_credit_stop_saves(tmp_path: Path) -> None:
    """Twelve Data's "run out of API credits for the day": the run saves what it has and stops; the ticker it was
    asking counts no attempt and is the next run's first."""
    spent = TwelveDataDayCredits("429: You have run out of API credits for the day.")
    fake = Fake({"D": [spent, CLOSES]})
    tickers = ["A", "B", "C", "D", "E"]
    out = go(fake, tickers, tmp_path)
    assert out.stopped == "day_credits" and fake.tickers() == ["AAPL", "A", "B", "C", "D"] and out.credits == 4
    saved = state(tmp_path)
    assert saved.status == "partial" and saved.tickers["D"] == TickerState() and saved.count("ok") == 3
    assert sorted(read_prices(tmp_path / "prices.csv.gz")) == ["A", "B", "C"]
    fake.asked.clear()
    assert go(fake, tickers, tmp_path).state.status == "complete" and fake.tickers() == ["D", "E"]


def test_a_spent_day_during_the_probe_saves_and_probes_again(tmp_path: Path) -> None:
    fake = Fake({("1day", "AAPL"): [TwelveDataDayCredits("429: ... for the day"), CLOSES]})
    out = go(fake, ["A"], tmp_path)
    assert out.stopped == "day_credits" and state(tmp_path).interval is None and state(tmp_path).status == "pending"
    assert go(fake, ["A"], tmp_path).state.status == "complete"


def test_the_probe_falls_back_to_monthly_then_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    late = [(date(2015, 1, 2), D(100)), (date(2026, 10, 16), D(250))]
    monthly = [(date(2005, 1, 1), D(5)), (date(2026, 9, 1), D(240)), (date(2026, 10, 1), D(252))]
    fake = Fake({("1day", "AAPL"): [late], ("1month", "AAPL"): [monthly], "X": [monthly]})
    out = go(fake, ["X"], tmp_path / "fallback")
    assert out.state.interval == "1month" and out.state.status == "complete"
    assert fake.asked == [("1day", "AAPL"), ("1month", "AAPL"), ("1month", "X")]
    bars = read_prices(tmp_path / "fallback" / "prices.csv.gz")["X"]
    assert [b.month_end for b in bars] == [date(2005, 1, 31), date(2026, 9, 30)]  # October dropped
    assert bars[-1] == MonthBar(date(2026, 9, 30), D(240), D(240), D(240))  # one close a month

    fake = Fake({("1day", "AAPL"): [late], ("1month", "AAPL"): [TwelveDataNoSuchSymbol("404")]})
    out = go(fake, ["X"], tmp_path / "blocked")
    reason = ("AAPL's daily series starts 2015-01-02 and its monthly series nowhere; the Lab needs prices from "
              "2010-01-31 (config/lab.yaml start)")  # fmt: skip
    assert out.state.status == "blocked" and out.state.reason == reason and out.credits == 2
    assert fake.tickers() == ["AAPL", "AAPL"] and not (tmp_path / "blocked" / "prices.csv.gz").exists()
    cfg = run.lab_config()
    text = run.blocked_reason(tmp_path / "blocked" / "prices.csv.gz", out.state, cfg)
    assert text == f"the Twelve Data download is blocked: {reason}"
    rows: list[tuple[Any, ...]] = []
    monkeypatch.setattr(ph.repo, "finish_run", lambda *a: rows.append(a))
    ph.finish(None, "run-1", out, tmp_path / "blocked" / "prices.csv.gz", cfg)  # type: ignore[arg-type]
    (_, run_id, status, stats, error), = rows  # fmt: skip
    assert (run_id, status, error) == ("run-1", "failed", text) and stats["status"] == "blocked"
    # blocked is not sticky: a later run probes again
    fake = Fake()
    assert go(fake, ["X"], tmp_path / "blocked").state.status == "complete" and fake.tickers() == ["AAPL", "X"]


@pytest.mark.parametrize(("step", "stopped", "credits"), [(8.0, "credits", 650), (10.0, "minutes", 540)])
def test_a_run_stops_at_90_minutes_or_650_credits(tmp_path: Path, step: float, stopped: str, credits: int) -> None:
    """At Twelve Data's 8 s a request, 650 credits take 87 minutes; anything slower meets the 90 minutes first. The
    state and the prices are saved every 50 tickers."""
    tickers = [f"T{i:04d}" for i in range(1000)]
    fake = Fake(step=step)
    out = go(fake, tickers, tmp_path)
    assert out.stopped == stopped and out.credits == credits == len(fake.asked)
    assert out.state.status == "partial" and out.state.settled() == credits - 1  # the probe's credit
    assert out.saved[:3] == [50, 100, 150] and out.saved[-1] == credits - 1
    assert len(read_prices(tmp_path / "prices.csv.gz")) == credits - 1


def test_failures_in_a_row_stop_the_run(tmp_path: Path) -> None:
    """A bad key or an outage fails every request: the run stops after five instead of billing 90 minutes."""
    fake = Fake({f"T{i}": [TwelveDataUnavailable("401: **apikey** is incorrect")] for i in range(8)})
    out = go(fake, [f"T{i}" for i in range(8)], tmp_path)
    assert out.stopped == "failures" and fake.tickers() == ["AAPL", "T0", "T1", "T2", "T3", "T4"]
    assert out.state.count("pending") == 8 and out.state.count("error") == 0


def test_complete_only_when_every_ticker_was_attempted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ticker with attempts left keeps the download partial; a ticker new to the Lab's list (a company added since)
    makes a complete download partial again. Only a complete one writes complete=true for lab-prices.yml."""
    fake = Fake({"B": [TwelveDataUnavailable("502"), CLOSES]})
    out = go(fake, ["A", "B"], tmp_path, ph.Limits(max_credits=3))
    assert out.state.status == "partial" and out.state.tickers["B"].attempts == 1
    assert go(fake, ["A", "B"], tmp_path).state.status == "complete"
    fake.asked.clear()
    assert go(fake, ["A", "B", "C"], tmp_path, ph.Limits(max_credits=0)).state.status == "partial"
    assert fake.asked == []
    assert go(fake, ["A", "B", "C"], tmp_path).state.status == "complete" and fake.tickers() == ["C"]
    out_file = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    ph.github_output(complete=True, blocked=False)
    assert out_file.read_text(encoding="utf-8") == "complete=true\nblocked=false\n"


def test_the_runs_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ok when complete, partial while tickers remain, with the progress in stats and no text."""
    rows: list[tuple[Any, ...]] = []
    monkeypatch.setattr(ph.repo, "finish_run", lambda *a: rows.append(a))
    for status, expected in (("complete", "ok"), ("partial", "partial")):
        s = DownloadState("1day", status, None, {"A": TickerState("ok"), "B": TickerState("pending", 1)})
        ph.finish(None, "r", ph.Outcome(s, credits=7, stopped="credits"), tmp_path / "p.csv.gz",  # type: ignore[arg-type]
                  run.lab_config())  # fmt: skip
        _, _, got, stats, error = rows.pop()
        assert (got, error) == (expected, None)
        assert stats == {"status": status, "interval": "1day", "tickers": 2, "ok": 1, "no_such_symbol": 0,
                         "error": 0, "pending": 1, "credits": 7, "stopped": "credits"}  # fmt: skip
