"""The Actions minutes meter (overhaul PR 3; docs/SPEC_ISSUES.md 50, 51). The account's private repositories share
GitHub's free 2,000 minutes a billing cycle; going over stops every workflow until the cycle resets (October 2026). No
spending limit is ever raised and no card is added (CLAUDE.md: $0 running cost), so the meter keeps the heavy jobs
inside the free minutes.

- Used: this repository's billed minutes since the cycle started (config/quotas.yaml `actions.cycle_day`), from the
  GitHub REST API with the workflow's GITHUB_TOKEN: each job of each run (every attempt) from its start to its end,
  rounded up to a whole minute as GitHub bills it. A job that never started (blocked, or still queued) or hasn't ended
  counts 0. Other repositories' minutes are `actions.other_repos`, copied by hand from github.com/settings/billing.
- Projected: used plus the cycle's remaining scheduled runs (the crons in .github/workflows/*.yml, UTC) at their
  typical cost (`actions.typical`). The Lab download (lab-prices.yml) is gated, so its typical cost is 0; the digest
  adds the runs it still needs instead (its pending tickers at `max_credits` a run, at most its cron's remaining runs)
  at `actions.download_run` each (PR 3 review spec-F2). The gate leaves them out: each of those runs asks for itself.
- `python -m pipeline.digest.minutes gate --need N` (lab-prices.yml and lab.yml, first step; the job needs
  `permissions: actions: read`): the run is allowed when used + N + `actions.reserve` + the scheduled runs stays at or
  below `actions.gate_max`. It prints one line, writes allowed=true|false to $GITHUB_OUTPUT and exits 0 either way: a
  refusal is a notice, not a failure. A meter that can't read the runs refuses.
- The weekly digest's line (pipeline/digest/weekly.py): 'Actions: N of 2,000 this cycle, projected M', with a warning
  above `actions.warn_above`.

`MockRuns` is the mock (MOCK_EXTERNALS=true, tests): it holds runs and their jobs in memory."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import yaml

from pipeline.net.http import HttpClient
from pipeline.settings import REPO_ROOT, Settings

API = "https://api.github.com"


class MeterUnavailable(Exception):
    """This repository's runs can't be read (no token or repository name outside Actions)."""


@dataclass(frozen=True)
class Budget:
    """config/quotas.yaml `actions`."""

    included: int  # the free minutes of a billing cycle
    cycle_day: int  # the day of the month the cycle resets (the month's last day when the month is shorter)
    other_repos: int  # minutes the account's other private repositories used this cycle
    gate_max: int  # the gate allows a run while the projection with it stays at or below this
    reserve: int  # minutes no schedule shows (CI, thesis-ingest, a re-run), held back by the gate
    warn_above: int  # the digest warns above this projection
    typical: Mapping[str, int] = field(default_factory=dict)  # workflow file -> billed minutes of a scheduled run
    download_run: int = 0  # billed minutes of one Lab download run (lab-prices.yml), for the digest's projection

    @classmethod
    def from_doc(cls, doc: Mapping[str, Any]) -> Budget:
        a = doc["actions"]
        budget = cls(
            included=int(a["included"]),
            cycle_day=int(a["cycle_day"]),
            other_repos=int(a.get("other_repos") or 0),
            gate_max=int(a["gate_max"]),
            reserve=int(a["reserve"]),
            warn_above=int(a["warn_above"]),
            typical={str(k): int(v) for k, v in (a.get("typical") or {}).items()},
            download_run=int(a.get("download_run") or 0),
        )
        if not 1 <= budget.cycle_day <= 31:
            raise ValueError(f"config/quotas.yaml actions.cycle_day must be 1-31, not {budget.cycle_day}")
        return budget

    @classmethod
    def load(cls, root: Path = REPO_ROOT) -> Budget:
        return cls.from_doc(yaml.safe_load((root / "config" / "quotas.yaml").read_text(encoding="utf-8")))


def _next_month(y: int, m: int) -> tuple[int, int]:
    return (y, m + 1) if m < 12 else (y + 1, 1)


def _on(y: int, m: int, cycle_day: int) -> date:
    return date(y, m, min(cycle_day, monthrange(y, m)[1]))


def cycle(today: date, cycle_day: int) -> tuple[date, date]:
    """The billing cycle holding `today`, as [start, end): both on cycle_day (a short month's last day)."""
    start = _on(today.year, today.month, cycle_day)
    if start > today:  # this month's reset is still ahead: the cycle began last month
        y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        start = _on(y, m, cycle_day)
    return start, _on(*_next_month(start.year, start.month), cycle_day)


def job_minutes(job: Mapping[str, Any]) -> int:
    """A job's billed minutes: from its start to its end, rounded up. 0 for a job that never started (blocked) or
    hasn't ended; a skipped job starts and ends at once."""
    started, completed = job.get("started_at"), job.get("completed_at")
    if job.get("status") != "completed" or not started or not completed:
        return 0
    seconds = (_ts(completed) - _ts(started)).total_seconds()
    return max(0, math.ceil(seconds / 60))


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------- the cycle's remaining scheduled runs


def _field(spec: str, lo: int, hi: int) -> frozenset[int]:
    """One cron field: *, n, a-b, lists of those, each with an optional /step."""
    out: set[int] = set()
    for part in spec.split(","):
        rng, _, step = part.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(x) for x in rng.split("-", 1))
        else:
            a = int(rng)
            b = hi if step else a
        if a < lo or b > hi:
            raise ValueError(f"cron field {spec!r} is outside {lo}-{hi}")
        out.update(range(a, b + 1, int(step or 1)))
    return frozenset(out)


def fires(cron: str, start: datetime, end: datetime) -> int:
    """How many times a GitHub cron (UTC) fires in [start, end). As in cron, a day matches its day of month OR its
    day of week when both are restricted."""
    minute, hour, dom, month, dow = cron.split()
    minutes, hours = sorted(_field(minute, 0, 59)), sorted(_field(hour, 0, 23))
    doms, months = _field(dom, 1, 31), _field(month, 1, 12)
    dows = frozenset(d % 7 for d in _field(dow, 0, 7))  # 0 and 7 are Sunday
    either = not dom.startswith("*") and not dow.startswith("*")
    n, day = 0, start.date()
    while day <= end.date():
        on_dom, on_dow = day.day in doms, (day.weekday() + 1) % 7 in dows
        if day.month in months and ((on_dom or on_dow) if either else (on_dom and on_dow)):
            for h in hours:
                for m in minutes:
                    if start <= datetime.combine(day, time(h, m), tzinfo=UTC) < end:
                        n += 1
        day += timedelta(days=1)
    return n


def scheduled_runs(start: datetime, end: datetime, root: Path = REPO_ROOT) -> dict[str, int]:
    """Workflow file -> how many scheduled runs it has in [start, end)."""
    out: dict[str, int] = {}
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        on = doc.get(True, doc.get("on"))  # yaml reads the `on:` key as True
        crons = [str(s["cron"]) for s in (on.get("schedule") or [])] if isinstance(on, dict) else []
        if crons:
            out[wf.name] = sum(fires(c, start, end) for c in crons)
    return out


def scheduled_minutes(runs: Mapping[str, int], typical: Mapping[str, int]) -> int:
    """The remaining scheduled runs at their typical cost (a workflow missing from the table costs 0: the gated ones,
    which ask for their own minutes)."""
    return sum(n * typical.get(name, 0) for name, n in runs.items())


DOWNLOAD = "lab-prices.yml"


def download_minutes(runs_left: int, pending: int, per_run: int, run_minutes: int) -> int:
    """The Lab download's remaining runs at `run_minutes` each: as many as its `pending` tickers need at `per_run`
    tickers a run (config/lab.yaml prices.max_credits), at most the `runs_left` its cron has this cycle."""
    if pending <= 0 or per_run <= 0:
        return 0
    return min(runs_left, math.ceil(pending / per_run)) * run_minutes


# ---------------------------------------------------------------- this repository's runs


class Runs(Protocol):
    def run_ids(self, since: date) -> list[int]: ...
    def jobs(self, run_id: int) -> list[dict[str, Any]]: ...


@dataclass
class GitHubRuns:
    """GET /repos/{repo}/actions/runs and /runs/{id}/jobs (filter=all: every attempt's jobs), paged."""

    http: HttpClient
    repo: str  # owner/name (GITHUB_REPOSITORY)
    token: str
    per_page: int = 100

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}  # fmt: skip

    def _pages(self, url: str, key: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            body = json.loads(self.http.get_bytes(f"{url}&per_page={self.per_page}&page={page}",
                                                  headers=self._headers()))  # fmt: skip
            items = list(body.get(key) or [])
            out += items
            if len(items) < self.per_page or len(out) >= int(body.get("total_count") or 0):
                return out
            page += 1

    def run_ids(self, since: date) -> list[int]:
        created = quote(f">={since.isoformat()}")
        url = f"{API}/repos/{self.repo}/actions/runs?created={created}&exclude_pull_requests=true"
        return [int(r["id"]) for r in self._pages(url, "workflow_runs")]

    def jobs(self, run_id: int) -> list[dict[str, Any]]:
        return self._pages(f"{API}/repos/{self.repo}/actions/runs/{run_id}/jobs?filter=all", "jobs")


@dataclass
class MockRuns:
    runs: dict[int, list[dict[str, Any]]] = field(default_factory=dict)  # run id -> its jobs
    created: dict[int, date] = field(default_factory=dict)  # run id -> its day (default: inside any cycle)

    def run_ids(self, since: date) -> list[int]:
        return [i for i in self.runs if self.created.get(i, since) >= since]

    def jobs(self, run_id: int) -> list[dict[str, Any]]:
        return self.runs[run_id]


def runs_client(settings: Settings, http: HttpClient, env: Mapping[str, str]) -> Runs:
    if settings.mock_externals:
        return MockRuns()
    token, repo_name = env.get("GITHUB_TOKEN"), env.get("GITHUB_REPOSITORY")
    if not token or not repo_name:
        raise MeterUnavailable("GITHUB_TOKEN and GITHUB_REPOSITORY are set only inside Actions")
    return GitHubRuns(http, repo_name, token)


# ---------------------------------------------------------------- the meter


@dataclass(frozen=True)
class Meter:
    budget: Budget
    start: date  # the billing cycle, [start, end)
    end: date
    here: int  # this repository's billed minutes this cycle
    scheduled: int  # the cycle's remaining scheduled runs at their typical cost
    download: int = 0  # the Lab download's remaining runs (download_minutes); the digest's projection only

    @property
    def used(self) -> int:
        return self.here + self.budget.other_repos

    def projected(self, need: int = 0, reserve: int = 0) -> int:
        return self.used + need + reserve + self.scheduled + self.download


def measure(runs: Runs, budget: Budget, now: datetime, root: Path = REPO_ROOT, download_pending: int = 0,
            tickers_per_run: int = 0) -> Meter:  # fmt: skip
    """`download_pending`, `tickers_per_run`: the Lab download's pending tickers and a run's share of them (the
    digest passes them; the gate doesn't, so they count 0 there)."""
    start, end = cycle(now.date(), budget.cycle_day)
    here = sum(job_minutes(j) for run_id in runs.run_ids(start) for j in runs.jobs(run_id))
    until = datetime.combine(end, time(0), tzinfo=UTC)
    fires_left = scheduled_runs(now, until, root)
    download = download_minutes(fires_left.get(DOWNLOAD, 0), download_pending, tickers_per_run, budget.download_run)
    return Meter(budget, start, end, here, scheduled_minutes(fires_left, budget.typical), download)


def gate(meter: Meter, need: int) -> tuple[bool, str]:
    """Allowed when used + this run + the reserve + the remaining scheduled runs stays at or below gate_max; the line
    the workflow prints (a notice when refused)."""
    b = meter.budget
    projected = meter.projected(need, b.reserve)
    ok = projected <= b.gate_max
    verdict = "<= {:,}: allowed" if ok else "> {:,}: refused, the run is skipped"
    line = (f"Actions minutes: {meter.used:,} used this cycle (since {meter.start}; {b.other_repos:,} of them in other "
            f"repos) + {need:,} this run + {b.reserve:,} reserve + {meter.scheduled:,} scheduled until {meter.end} = "
            f"{projected:,} {verdict.format(b.gate_max)}")  # fmt: skip
    return ok, line if ok else f"::notice::{line}"


def digest_line(meter: Meter) -> str:
    """'Actions: N of 2,000 this cycle, projected M', and a warning above warn_above."""
    b = meter.budget
    projected = meter.projected()
    line = f"Actions: {meter.used:,} of {b.included:,} this cycle, projected {projected:,}."
    if projected > b.warn_above:
        line += (f" **Warning:** that is above {b.warn_above:,}; at {b.included:,} every workflow stops until the "
                 f"cycle resets on {meter.end}, so switch off other repositories' workflows "
                 "(github.com/settings/billing).")  # fmt: skip
    return line


def digest_lines(settings: Settings, http: HttpClient, now: datetime | None = None,
                 env: Mapping[str, str] | None = None, root: Path = REPO_ROOT, download_pending: int = 0,
                 tickers_per_run: int = 0) -> list[str]:  # fmt: skip
    """The digest's line, the Lab download's remaining runs projected (pipeline/lab/price_history.pending_tickers);
    the digest goes out also when the runs can't be read, saying so."""
    try:
        runs = runs_client(settings, http, os.environ if env is None else env)
        meter = measure(runs, Budget.load(root), now or datetime.now(UTC), root, download_pending, tickers_per_run)
    except Exception as e:  # noqa: BLE001 — httpx errors and the like: the digest still goes out
        return [f"Actions: minutes not read this week ({type(e).__name__}: {e})."]
    return [digest_line(meter)]


def github_output(path: str | None, allowed: bool) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"allowed={'true' if allowed else 'false'}\n")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("gate", help="allow a run of up to --need minutes, or refuse it (exit 0 either way)")
    g.add_argument("--need", type=int, required=True, help="the job's whole limit (its timeout-minutes)")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    try:
        meter = measure(runs_client(settings, HttpClient(settings), os.environ), Budget.load(), datetime.now(UTC))
        allowed, line = gate(meter, a.need)
    except Exception as e:  # noqa: BLE001 — a gate that can't count refuses, as a notice
        allowed = False
        line = f"::notice::Actions minutes gate: can't read this repository's runs ({type(e).__name__}: {e}): refused"
    print(line)
    github_output(os.environ.get("GITHUB_OUTPUT"), allowed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
