"""Kill criteria (BRIEF §4.9): each accepted thesis (state thesis or position) is checked after the weekly run has
written the week's fundamentals, ownership and signal rows, so every new row is seen within the week it arrives.

A criterion is checked from its check_after date on: its metric is recomputed from the point-in-time readers with the
same code that filled the pack (evidence_pack.kill_value); `changes` compares with the pack's value (baseline). When
a condition holds, the criterion is `triggered` (dated with the week), the thesis moves to `review`, and the digest
lists it under "theses needing attention". A metric that can't be computed is `unknown`, never triggered.

`python -m pipeline.thesis.kill_criteria [--week D]` (weekly.yml `publish` job, after this week's scores)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import psycopg

from pipeline.db import repo, thesis_repo
from pipeline.settings import Settings
from pipeline.signals.weekly import last_friday
from pipeline.thesis.evidence_pack import is_kill_metric, kill_inputs, kill_value
from pipeline.thesis.validate import met


@dataclass
class KillStats:
    week: str
    theses: int = 0
    checked: int = 0
    triggered: list[str] = field(default_factory=list)
    unknown: int = 0


def evaluate(conn: psycopg.Connection[Any], week: date) -> KillStats:
    stats = KillStats(week.isoformat())
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    for t in thesis_repo.monitored_theses(conn):
        company = companies.get(t["company_id"])
        if company is None:
            continue
        stats.theses += 1
        kin = kill_inputs(conn, company, week)
        newly = False
        for k in thesis_repo.criteria_of(conn, t["id"]):
            if not is_kill_metric(str(k["metric"])):
                thesis_repo.record_check(conn, k["id"], "unknown", None, week, None)
                stats.unknown += 1
                continue
            value = kill_value(str(k["metric"]).removeprefix("m:"), kin)
            if value is None:
                thesis_repo.record_check(conn, k["id"], "unknown", None, week, None)
                stats.unknown += 1
                continue
            if week < k["check_after"]:
                thesis_repo.record_check(conn, k["id"], "ok", value, week, None)
                continue
            stats.checked += 1
            hit = met(value, str(k["operator"]), k["threshold"], k["baseline"])
            if hit and k["status"] != "triggered":
                newly = True
                stats.triggered.append(f"{company.name}: {k['metric']} {k['operator']} {k['threshold']} (now {value})")
            thesis_repo.record_check(conn, k["id"], "triggered" if hit else "ok", value, week, week if hit else None)
        if newly:
            thesis_repo.move_to_review(conn, t["id"])
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=date.fromisoformat, default=last_friday(datetime.now(UTC).date()))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "kill_criteria") as tracked:
        stats = evaluate(conn, a.week)
        tracked.update(stats.__dict__)
    print(f"kill criteria {stats.week}: {stats.theses} theses, {stats.checked} checked, "
          f"{len(stats.triggered)} triggered, {stats.unknown} unknown")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
