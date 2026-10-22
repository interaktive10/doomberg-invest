"""The Actions minutes meter (overhaul PR 3, pipeline/digest/minutes.py): billed minutes per job, the billing cycle,
other repos, the projection from the workflows' crons, the gate lab-prices.yml and lab.yml run first, and the digest's
line. Offline: GitHub's answers are fixtures/github (HttpClient mock mode) or MockRuns."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from pipeline.digest import minutes
from pipeline.digest.minutes import API, Budget, GitHubRuns, Meter, MockRuns
from pipeline.net.http import HttpClient
from pipeline.settings import REPO_ROOT, Settings

FIX = REPO_ROOT / "fixtures" / "github"
BUDGET = Budget(included=2000, cycle_day=1, other_repos=0, gate_max=1900, reserve=180, warn_above=1600,
                typical={"daily.yml": 10, "weekly.yml": 60, "thesis-fallback.yml": 2, "lab-prices.yml": 0})  # fmt: skip


def job(seconds: int | None) -> dict[str, Any]:
    """A completed job that ran `seconds`, or (None) one that never started."""
    start = datetime(2026, 11, 3, 1, tzinfo=UTC)
    end = start + timedelta(seconds=seconds or 0)
    return {"status": "completed", "started_at": None if seconds is None else f"{start:%Y-%m-%dT%H:%M:%SZ}",
            "completed_at": f"{end:%Y-%m-%dT%H:%M:%SZ}"}  # fmt: skip


@pytest.fixture(autouse=True)
def _mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_EXTERNALS", "true")


# ---------------------------------------------------------------- billed minutes


@pytest.mark.parametrize(("seconds", "billed"), [(61, 2), (60, 1), (59, 1), (1, 1), (0, 0), (3601, 61)])
def test_each_job_is_rounded_up_to_a_whole_minute(seconds: int, billed: int) -> None:
    assert minutes.job_minutes(job(seconds)) == billed


def test_a_job_that_never_started_or_has_not_ended_counts_zero() -> None:
    assert minutes.job_minutes(job(None)) == 0  # blocked: no started_at (the 2026-10-20 daily run)
    assert minutes.job_minutes({"status": "queued", "started_at": None, "completed_at": None}) == 0
    running = {"status": "in_progress", "started_at": "2026-11-03T01:00:00Z", "completed_at": None}
    assert minutes.job_minutes(running) == 0


def test_the_real_client_pages_runs_and_every_attempts_jobs(tmp_path: Path) -> None:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    base = f"{API}/repos/o/r/actions/runs"
    urls = {
        f"{API}/repos/o/r": "repo_private.json",
        f"{base}?created=%3E%3D2026-11-01&exclude_pull_requests=true&per_page=2&page=1": "runs_page1.json",
        f"{base}?created=%3E%3D2026-11-01&exclude_pull_requests=true&per_page=2&page=2": "runs_page2.json",
        f"{base}/101/jobs?filter=all&per_page=2&page=1": "jobs_101_page1.json",
        f"{base}/101/jobs?filter=all&per_page=2&page=2": "jobs_101_page2.json",
        f"{base}/102/jobs?filter=all&per_page=2&page=1": "jobs_102.json",
        f"{base}/103/jobs?filter=all&per_page=2&page=1": "jobs_103.json",
    }
    for url, name in urls.items():
        http.register_mock(url, (FIX / name).read_bytes())
    gh = GitHubRuns(http, "o/r", "t0ken", per_page=2)
    meter = minutes.measure(gh, BUDGET, datetime(2026, 11, 8, 12, tzinfo=UTC), REPO_ROOT)
    assert meter.here == 2 + 1 + 0 + 2 + 0 + 11 and meter.start == date(2026, 11, 1) and not meter.public
    assert http.calls == list(urls)  # each page once; no page past total_count
    assert gh._headers()["Authorization"] == "Bearer t0ken"


# ---------------------------------------------------------------- the billing cycle and other repos


@pytest.mark.parametrize(
    ("today", "cycle_day", "start", "end"),
    [
        (date(2026, 11, 15), 1, date(2026, 11, 1), date(2026, 12, 1)),
        (date(2026, 11, 1), 1, date(2026, 11, 1), date(2026, 12, 1)),  # the reset day opens a cycle
        (date(2026, 10, 31), 1, date(2026, 10, 1), date(2026, 11, 1)),
        (date(2026, 11, 5), 20, date(2026, 10, 20), date(2026, 11, 20)),  # cycle_day later than today's day
        (date(2026, 11, 20), 20, date(2026, 11, 20), date(2026, 12, 20)),
        (date(2027, 1, 5), 20, date(2026, 12, 20), date(2027, 1, 20)),  # across the year
        (date(2026, 12, 25), 20, date(2026, 12, 20), date(2027, 1, 20)),
        (date(2027, 2, 28), 31, date(2027, 2, 28), date(2027, 3, 31)),  # a short month resets on its last day
        (date(2027, 3, 1), 31, date(2027, 2, 28), date(2027, 3, 31)),
    ],
)  # fmt: skip
def test_the_cycle_runs_from_one_reset_day_to_the_next(today: date, cycle_day: int, start: date, end: date) -> None:
    assert minutes.cycle(today, cycle_day) == (start, end)


def test_only_the_cycles_runs_count_and_other_repos_are_added(tmp_path: Path) -> None:
    runs = MockRuns(runs={1: [job(61)], 2: [job(600)], 3: [job(59)]},
                    created={1: date(2026, 10, 19), 2: date(2026, 10, 20), 3: date(2026, 11, 2)})  # fmt: skip
    budget = replace(BUDGET, cycle_day=20, other_repos=35)
    meter = minutes.measure(runs, budget, datetime(2026, 11, 5, 9, tzinfo=UTC), tmp_path)
    assert (meter.start, meter.end) == (date(2026, 10, 20), date(2026, 11, 20))
    assert meter.here == 10 + 1 and meter.used == 11 + 35  # run 1 is the last cycle's


def test_cycle_day_is_checked() -> None:
    doc = {"actions": {"included": 2000, "cycle_day": 0, "gate_max": 1900, "reserve": 180, "warn_above": 1600}}
    with pytest.raises(ValueError, match="cycle_day"):
        Budget.from_doc(doc)


# ---------------------------------------------------------------- the projection


def workflows(root: Path, crons: dict[str, list[str]]) -> Path:
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True)
    for name, cs in crons.items():
        on: dict[str, Any] = {"workflow_dispatch": None, **({"schedule": [{"cron": c} for c in cs]} if cs else {})}
        (wf / name).write_text(yaml.safe_dump({"name": name, "on": on, "jobs": {}}), encoding="utf-8")
    return root


REPO_CRONS = {
    "daily.yml": ["13 1 * * 2-6"],
    "weekly.yml": ["7 2 * * 6"],
    "quarterly.yml": ["0 3 20 1,4,7,10 *"],
    "thesis-fallback.yml": ["0 6 * * 1"],
    "lab-prices.yml": ["7 10 * 11,12 0-4"],
    "lab.yml": [],
}


def test_the_crons_fire_on_their_days_in_a_month() -> None:
    """November 2026 starts on a Sunday: 20 days Tuesday-Saturday, 4 Saturdays, 5 Mondays, 22 days Sunday-Thursday."""
    nov, dec = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)
    counts = [minutes.fires(c[0], nov, dec) for c in REPO_CRONS.values() if c]
    assert counts == [20, 4, 0, 5, 22]
    assert minutes.fires("0 3 20 1,4,7,10 *", datetime(2026, 10, 1, tzinfo=UTC), nov) == 1
    assert minutes.fires("7 10 * 11,12 0-4", datetime(2026, 10, 1, tzinfo=UTC), nov) == 0
    assert minutes.fires("0 0 1 * 1", nov, dec) == 1 + 5  # day 1 OR a Monday, as cron reads both
    assert minutes.fires("*/15 0 * * *", nov, datetime(2026, 11, 2, tzinfo=UTC)) == 4
    assert minutes.fires("0 0 * * 7", nov, dec) == 5  # 7 is Sunday too


def test_the_projection_adds_the_cycles_remaining_scheduled_runs(tmp_path: Path) -> None:
    """From Tuesday 2026-11-17 noon to the reset on Dec 1: daily Wed 18 - Sat 21 and Tue 24 - Sat 28 (9), weekly on
    the 21st and 28th (2), thesis-fallback on the 23rd and 30th (2); lab-prices is gated, so it costs 0 here, and a
    workflow missing from the table (quarterly: none left anyway) costs 0."""
    root = workflows(tmp_path, REPO_CRONS)
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    runs = minutes.scheduled_runs(now, datetime(2026, 12, 1, tzinfo=UTC), root)
    assert runs == {"daily.yml": 9, "weekly.yml": 2, "quarterly.yml": 0, "thesis-fallback.yml": 2,
                    "lab-prices.yml": 9}  # fmt: skip
    meter = minutes.measure(MockRuns(runs={1: [job(600)]}), BUDGET, now, root)
    assert meter.scheduled == 9 * 10 + 2 * 60 + 2 * 2 and meter.projected() == 10 + 214
    assert meter.projected(120, 180) == 10 + 120 + 180 + 214


def test_the_digest_projects_the_runs_the_lab_download_still_needs(tmp_path: Path) -> None:
    """PR 3 review spec-F2: lab-prices.yml costs 0 in the schedule (each run is gated for its own 120 minutes), so the
    digest adds the runs the download still needs: its pending tickers at 650 a run, at most the 9 its cron has left
    from 2026-11-17 to the reset, at 95 minutes each; none once it is done. The gate leaves them out."""
    root = workflows(tmp_path, REPO_CRONS)
    now = datetime(2026, 11, 17, 12, tzinfo=UTC)
    budget = replace(BUDGET, download_run=95)
    base = minutes.measure(MockRuns(runs={1: [job(600)]}), budget, now, root)
    assert base.download == 0 and base.projected() == 10 + 214  # the gate's meter: no download runs
    for pending, runs in ((1500, 3), (650, 1), (100_000, 9), (0, 0)):
        m = minutes.measure(MockRuns(runs={1: [job(600)]}), budget, now, root, pending, 650)
        assert m.download == runs * 95 and m.projected() == 10 + 214 + runs * 95, pending
    line = minutes.digest_line(minutes.measure(MockRuns(runs={1: [job(600)]}), budget, now, root, 5200, 650))
    assert line == "Actions: 10 of 2,000 this cycle, projected 984."  # 10 + 214 + 8 runs (5,200 / 650) x 95
    january = datetime(2027, 1, 1, tzinfo=UTC)  # a cycle with no lab-prices runs left: nothing projected
    assert minutes.measure(MockRuns(), budget, january, root, 5200, 650).download == 0
    assert minutes.download_minutes(5, 1300, 650, 95) == 2 * 95 and minutes.download_minutes(5, 1301, 650, 95) == 285


def test_a_run_that_fires_now_is_still_ahead(tmp_path: Path) -> None:
    root = workflows(tmp_path, {"daily.yml": ["13 1 * * 2-6"]})
    now = datetime(2026, 11, 28, 1, 13, tzinfo=UTC)  # the cycle's last daily run, a Saturday
    assert minutes.scheduled_runs(now, datetime(2026, 12, 1, tzinfo=UTC), root) == {"daily.yml": 1}


def test_every_scheduled_workflow_has_a_typical_cost() -> None:
    """The repository's config: each workflow with a cron is in actions.typical (lab-prices at 0: it is gated), and
    the gate's numbers are the plan's (1,900 with 180 held back; the digest warns above 1,600)."""
    budget = Budget.load()
    nov = datetime(2026, 11, 1, tzinfo=UTC)
    scheduled = minutes.scheduled_runs(nov, datetime(2027, 11, 1, tzinfo=UTC))
    assert set(scheduled) == set(budget.typical) and budget.typical["lab-prices.yml"] == 0
    assert budget.download_run == 95  # the digest's projection of the download's remaining runs
    assert (budget.included, budget.gate_max, budget.reserve, budget.warn_above) == (2000, 1900, 180, 1600)


# ---------------------------------------------------------------- the gate


def meter(here: int, scheduled: int = 0, other: int = 0) -> Meter:
    budget = replace(BUDGET, other_repos=other)
    return Meter(budget, date(2026, 11, 1), date(2026, 12, 1), here, scheduled)


def test_the_gate_allows_up_to_1900_and_refuses_above() -> None:
    ok, line = minutes.gate(meter(1000, 400, other=100), 120)  # 1100 + 120 + 180 + 400 = 1800
    assert ok and line.startswith("Actions minutes: 1,100 used") and line.endswith("= 1,800 <= 1,900: allowed")
    assert minutes.gate(meter(1100, 400, other=100), 120)[0]  # exactly 1,900
    ok, line = minutes.gate(meter(1101, 400, other=100), 120)
    assert not ok and line.startswith("::notice::") and "= 1,901 > 1,900: refused" in line


def gate_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runs: minutes.Runs | Exception,
             capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:  # fmt: skip
    out = tmp_path / "github_output"
    out.write_text("earlier=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    def client(*_: Any) -> minutes.Runs:
        if isinstance(runs, Exception):
            raise runs
        return runs

    monkeypatch.setattr(minutes, "runs_client", client)
    code = minutes.main(["gate", "--need", "120"])
    return code, out.read_text(encoding="utf-8"), capsys.readouterr().out


def test_the_gate_writes_allowed_and_exits_0(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    code, output, printed = gate_run(monkeypatch, tmp_path, MockRuns(runs={1: [job(600)]}), capsys)
    assert code == 0 and output == "earlier=1\nallowed=true\n"
    b = Budget.load()  # the real config: the other repos' daily rate counts too
    assert printed.count("\n") == 1 and printed.startswith("Actions minutes: ") and "allowed" in printed
    assert " used this cycle (since " in printed and "other repos ahead" in printed and b.other_repos_per_day > 0


def test_a_refused_gate_is_a_notice_and_exits_0(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    code, output, printed = gate_run(monkeypatch, tmp_path, MockRuns(runs={1: [job(1700 * 60)]}), capsys)
    assert code == 0 and output == "earlier=1\nallowed=false\n"
    assert printed.count("\n") == 1 and printed.startswith("::notice::Actions minutes: ") and "refused" in printed


def test_a_gate_that_cannot_read_the_runs_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    code, output, printed = gate_run(monkeypatch, tmp_path, minutes.MeterUnavailable("no token"), capsys)
    assert code == 0 and output.endswith("allowed=false\n")
    assert printed.startswith("::notice::Actions minutes gate: can't read") and "no token" in printed


def test_outside_actions_there_is_no_token(tmp_path: Path) -> None:
    settings = Settings(database_url="x", mock_externals=False, sec_user_agent="t", cache_dir=tmp_path)
    with pytest.raises(minutes.MeterUnavailable):
        minutes.runs_client(settings, HttpClient(settings), {"GITHUB_REPOSITORY": "o/r"})
    assert isinstance(minutes.runs_client(settings, HttpClient(settings), {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY":
                                                                          "o/r"}), GitHubRuns)  # fmt: skip
    mock = Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path)
    assert isinstance(minutes.runs_client(mock, HttpClient(mock), {}), MockRuns)


# ---------------------------------------------------------------- the digest's line


def test_the_digest_line_and_its_warning_above_1600() -> None:
    assert minutes.digest_line(meter(812, 528)) == "Actions: 812 of 2,000 this cycle, projected 1,340."
    assert minutes.digest_line(meter(1000, 500, other=100)) == "Actions: 1,100 of 2,000 this cycle, projected 1,600."
    line = minutes.digest_line(meter(1000, 501, other=100))
    assert line.startswith("Actions: 1,100 of 2,000 this cycle, projected 1,601. **Warning:** that is above 1,600")
    assert "2026-12-01" in line
    assert "**Warning:**" in minutes.digest_line(meter(1700))  # used alone above 1,600


def test_the_digest_says_when_the_minutes_cannot_be_read(tmp_path: Path) -> None:
    settings = Settings(database_url="x", mock_externals=False, sec_user_agent="t", cache_dir=tmp_path)
    assert minutes.digest_lines(settings, HttpClient(settings), env={}) == [
        "Actions: minutes not read this week (MeterUnavailable: GITHUB_TOKEN and GITHUB_REPOSITORY are set only "
        "inside Actions)."
    ]
    mock = Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path)
    [line] = minutes.digest_lines(mock, HttpClient(mock), datetime(2026, 11, 17, 12, tzinfo=UTC), env={})
    b = Budget.load()  # no runs here: only the other repos, 16 days into the cycle at their daily rate
    assert line.startswith(f"Actions: {b.other_repos + 16 * b.other_repos_per_day:,} of 2,000 this cycle, projected ")


def test_the_fixtures_are_valid_json() -> None:
    for f in FIX.glob("*.json"):
        json.loads(f.read_text(encoding="utf-8"))


def test_other_repos_are_budgeted_per_day_of_the_cycle(tmp_path: Path) -> None:
    """The token reads only this repository: the others are budgeted at a daily rate, the days so far as used and the
    rest of the cycle in the projection (Oct 2026: the others' 670 minutes put the account over 2,000)."""
    budget = replace(BUDGET, other_repos=5, other_repos_per_day=31)
    meter = minutes.measure(MockRuns(runs={1: [job(600)]}), budget, datetime(2026, 11, 11, 9, tzinfo=UTC), tmp_path)
    assert (meter.others_so_far, meter.others_ahead) == (31 * 10, 31 * 20)
    assert meter.used == 10 + 5 + 310 and meter.projected() == meter.used + 620
    ok, line = minutes.gate(meter, 120)
    assert "315 of them in other repos) + 620 other repos ahead" in line
    assert minutes.Budget.load().other_repos_per_day == 31


def test_the_digest_projects_no_more_download_runs_than_the_gate_admits() -> None:
    """Integration review runtime-X2: 5,200 pending tickers are 8 runs, but the projection counts only the runs the
    gate (gate_max 1,900, reserve 180, need 120 a run) can still admit this cycle (the repo's own crons)."""
    budget = replace(BUDGET, download_run=95)
    now = datetime(2026, 11, 2, 9, tzinfo=UTC)
    quiet = minutes.measure(MockRuns(), budget, now, download_pending=5200, tickers_per_run=650)
    busy = minutes.measure(MockRuns(runs={1: [job(1300 * 60)]}), budget, now, download_pending=5200,
                           tickers_per_run=650)  # fmt: skip
    assert minutes.admitted_runs(budget, 0) == (1900 - 180 - 120) // 95 + 1
    assert minutes.admitted_runs(budget, 1900 - 180 - 119) == 0 and minutes.admitted_runs(budget, 1900 - 180 - 120) == 1
    assert quiet.download == 8 * 95  # room for every run: nothing capped
    assert busy.download == minutes.admitted_runs(budget, 1300 + busy.scheduled) * 95 < 8 * 95
    assert busy.projected() <= 1900 - 180 + 95  # at most one run's actual minutes past the gate's own line


# ---------------------------------------------------------------- a public repository


def test_a_public_repositorys_runs_are_free(tmp_path: Path) -> None:
    """GitHub bills only private repositories' minutes: while this one is public its own runs, crons and downloads
    count 0, the gate allows and the digest says so; the other repositories still count (they stay private)."""
    budget = replace(BUDGET, other_repos_per_day=31, download_run=95)
    root = workflows(tmp_path, REPO_CRONS)
    now = datetime(2026, 11, 11, 9, tzinfo=UTC)
    heavy = {1: [job(1800 * 60)]}  # over the gate on its own
    private = minutes.measure(MockRuns(runs=heavy), budget, now, root, download_pending=5200, tickers_per_run=650)
    public = minutes.measure(MockRuns(runs=heavy, is_public=True), budget, now, root, download_pending=5200,
                             tickers_per_run=650)  # fmt: skip
    assert not minutes.gate(private, 120)[0] and private.scheduled > 0
    assert public.public and (public.here, public.scheduled, public.download) == (0, 0, 0)
    assert public.others == 31 * 10
    assert minutes.gate(public, 120) == (
        True,
        "Actions minutes: this repository is public, so its runs are free: allowed",
    )
    assert minutes.digest_line(public) == (
        "Actions: free while this repository is public; the other repositories used about 310 of 2,000 this cycle."
    )


def test_the_real_client_reads_the_repositorys_visibility(tmp_path: Path) -> None:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    http.register_mock(f"{API}/repos/o/r", (FIX / "repo_public.json").read_bytes())
    meter = minutes.measure(GitHubRuns(http, "o/r", "t"), BUDGET, datetime(2026, 11, 8, 12, tzinfo=UTC), tmp_path)
    assert meter.public and meter.here == 0
    assert http.calls == [f"{API}/repos/o/r"]  # a public repository's runs aren't read at all
    http.register_mock(f"{API}/repos/o/r", (FIX / "repo_private.json").read_bytes())
    assert GitHubRuns(http, "o/r", "t").public() is False


def test_a_public_repositorys_gate_writes_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    runs = MockRuns(runs={1: [job(1900 * 60)]}, is_public=True)
    code, output, printed = gate_run(monkeypatch, tmp_path, runs, capsys)
    assert code == 0 and output == "earlier=1\nallowed=true\n"
    assert printed == "Actions minutes: this repository is public, so its runs are free: allowed\n"
