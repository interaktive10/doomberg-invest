"""The US daily catch-up without its state file (pipeline/us/daily.py; overhaul PR 1, "EDGAR cursor recovery"). The
Actions cache that holds daily_state.json is evicted after 7 days unused, as during the October 2026 Actions outage,
so the run resumes from the latest us_daily runs row instead of reading only the latest few days. The database and
each day's reading are faked here; tests/db/test_us_pipeline.py runs the catch-up and the runs query on a database."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipeline.db import repo
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.us import daily
from pipeline.us.events import quarter_listing_url, quarters_between

TODAY = date(2026, 11, 3)  # the first daily after the billing reset: SEC's last index then is Monday 2026-11-02
CALENDAR = [date(2026, 9, 1) + timedelta(days=n) for n in range(63)]
PUBLISHED = [d for d in CALENDAR if d.weekday() < 5]  # 2026-09-01 .. 2026-11-02, holidays aside


class Conn:
    """run_catch_up commits each day in its own transaction; nothing else reaches the database here."""

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield


def weekdays(first: date, last: date) -> list[date]:
    return [d for d in PUBLISHED if first <= d <= last]


def sec(tmp_path: Path) -> HttpClient:
    """SEC's daily-index listings (index.json) for 2026 Q3 and Q4."""
    client = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    for q in quarters_between(PUBLISHED[0], TODAY):
        days = [d for d in PUBLISHED if quarters_between(d, d) == [q]]
        items = [{"name": f"master.{d:%Y%m%d}.idx", "type": "file"} for d in days]
        client.register_mock(quarter_listing_url(q), json.dumps({"directory": {"item": items}}).encode())
    return client


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> list[date]:
    """The days the catch-up read (each with nothing in it)."""
    out: list[date] = []

    def run_daily(conn: Conn, client: HttpClient, day: date, state_path: Path | None = None) -> daily.DailyStats:
        out.append(day)
        return daily.DailyStats(day.isoformat())

    monkeypatch.setattr(daily, "run_daily", run_daily)
    return out


def runs_row(monkeypatch: pytest.MonkeyPatch, days: Sequence[dict[str, Any]]) -> list[str]:
    """The latest us_daily runs row's days (repo.latest_run_days); returns the kinds asked for."""
    kinds: list[str] = []

    def latest_run_days(conn: Conn, kind: str) -> list[dict[str, Any]]:
        kinds.append(kind)
        return list(days)

    monkeypatch.setattr(repo, "latest_run_days", latest_run_days)
    return kinds


def catch_up(tmp_path: Path) -> list[daily.DailyStats]:
    conn: Any = Conn()
    return daily.run_catch_up(conn, sec(tmp_path), TODAY, tmp_path / "pending.json", tmp_path / "day.json")


def test_a_missing_cursor_resumes_from_the_newest_day_of_the_latest_runs_row(
    monkeypatch: pytest.MonkeyPatch, read: list[date], tmp_path: Path
) -> None:
    """The last daily before the outage (Saturday 2026-10-17) read Thursday's and Friday's indexes."""
    kinds = runs_row(monkeypatch, [{"day": "2026-10-15", "retry": 0}, {"day": "2026-10-16", "retry": 0}])
    stats = catch_up(tmp_path)
    assert kinds == ["us_daily"]
    assert read == weekdays(date(2026, 10, 19), date(2026, 11, 2)) and len(read) == 11
    assert [s.day for s in stats] == [d.isoformat() for d in read]
    assert daily.load_last_day(tmp_path / "day.json") == date(2026, 11, 2)  # the state file is back


def test_without_a_runs_row_it_reads_the_latest_days_as_before(
    monkeypatch: pytest.MonkeyPatch, read: list[date], tmp_path: Path
) -> None:
    runs_row(monkeypatch, [])
    catch_up(tmp_path)
    assert read == [date(2026, 10, 29), date(2026, 10, 30), date(2026, 11, 2)]  # a first run: the latest 3
    assert daily.load_last_day(tmp_path / "day.json") == date(2026, 11, 2)


def test_a_state_file_is_still_the_cursor(monkeypatch: pytest.MonkeyPatch, read: list[date], tmp_path: Path) -> None:
    kinds = runs_row(monkeypatch, [{"day": "2026-10-01", "retry": 0}])
    daily.save_last_day(tmp_path / "day.json", date(2026, 10, 29))
    catch_up(tmp_path)
    assert kinds == [] and read == [date(2026, 10, 30), date(2026, 11, 2)]


def test_a_day_still_being_retried_is_read_again(
    monkeypatch: pytest.MonkeyPatch, read: list[date], tmp_path: Path
) -> None:
    """The lost state file held the cursor before Thursday's failed downloads (review R2-F5)."""
    runs_row(monkeypatch, [{"day": "listings as of 2026-10-17", "errors": ["x"], "retry": 0},
                           {"day": "2026-10-15", "retry": 2}, {"day": "2026-10-16", "retry": 0}])  # fmt: skip
    catch_up(tmp_path)
    assert read == weekdays(date(2026, 10, 15), date(2026, 11, 2))


def test_the_catch_up_goes_back_at_most_catch_up_days(
    monkeypatch: pytest.MonkeyPatch, read: list[date], tmp_path: Path
) -> None:
    """A runs row older than CATCH_UP_DAYS: the days before that are logged for the backfill, not read."""
    runs_row(monkeypatch, [{"day": "2026-09-04", "retry": 0}])
    stats = catch_up(tmp_path)
    floor = TODAY - timedelta(days=daily.CATCH_UP_DAYS)
    assert read == weekdays(floor + timedelta(days=1), date(2026, 11, 2)) and read[0] == date(2026, 10, 5)
    assert stats[0].day == "cursor as of 2026-11-03" and "pipeline.us.backfill" in stats[0].errors[0]
    assert "2026-09-04" in stats[0].errors[0]


def test_resume_day_reads_only_days() -> None:
    assert daily.resume_day([]) is None
    assert daily.resume_day([{"day": "listings as of 2026-10-17", "retry": 0}]) is None
    assert daily.resume_day([{"day": "2026-10-16"}, {"day": "2026-10-15", "retry": 0}]) == date(2026, 10, 16)
    assert daily.resume_day([{"day": "2026-10-15", "retry": 0}, {"day": "2026-10-16", "retry": 1},
                             {"day": "2026-10-19", "retry": 1}]) == date(2026, 10, 15)  # fmt: skip


def test_a_one_day_run_records_its_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--date reads one day and leaves the cursor alone, so its runs row is no cursor to resume from either: it names
    the date, and repo.latest_run_days passes it over. A catch-up run records date null."""
    rows: list[dict[str, Any]] = []

    @contextmanager
    def connect(url: str) -> Iterator[Conn]:
        yield Conn()

    @contextmanager
    def tracked_run(conn: Conn, kind: str, source: str | None = None) -> Iterator[dict[str, Any]]:
        stats: dict[str, Any] = {}
        yield stats
        rows.append(stats)

    def run_daily(conn: Conn, client: HttpClient, day: date, state_path: Path | None = None) -> daily.DailyStats:
        return daily.DailyStats(day.isoformat())

    monkeypatch.setattr(daily.psycopg, "connect", connect)
    monkeypatch.setattr(repo, "tracked_run", tracked_run)
    monkeypatch.setattr(daily, "run_daily", run_daily)
    monkeypatch.setattr(daily, "run_catch_up", lambda *a: [])
    monkeypatch.setenv("DOOM_CACHE_DIR", str(tmp_path))
    assert daily.main(["--date", "2026-10-16", "--rescan-days", "0"]) == 0
    assert daily.main(["--rescan-days", "0"]) == 0
    assert [(r["date"], [d["day"] for d in r["days"]]) for r in rows] == [("2026-10-16", ["2026-10-16"]), (None, [])]
