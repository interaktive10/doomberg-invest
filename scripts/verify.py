#!/usr/bin/env python3
"""Verify harness (BRIEF §9). `verify.py --milestone m0` runs every check for M0 and all earlier milestones.

Statuses: PASS, FAIL, BLOCKED(key:NAME), BLOCKED(human:WHAT). Writes docs/VERIFY_REPORT.md.
Exits non-zero on any FAIL. BLOCKED is reported, never silently turned into PASS.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MILESTONES = ["m0", "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9"]
PYTEST = ["uv", "run", "--frozen", "pytest", "-q", "-p", "no:cacheprovider"]

Requirement = Callable[[], str | None]  # returns None when satisfied, else "key:NAME" / "human:WHAT"


@dataclass(frozen=True)
class Check:
    id: str
    milestone: str
    description: str
    command: list[str]
    requires: Requirement | None = None


@dataclass(frozen=True)
class Result:
    check: Check
    status: str
    seconds: float
    tail: str


def _needs_universe_snapshots() -> str | None:
    missing = [
        p
        for p in ("data/universe/us_tickers_exchange.json", "data/universe/nse_equity_list.csv")
        if not (ROOT / p).exists()
    ]
    if missing:
        return (
            "human:universe snapshots missing (" + ", ".join(missing) + "); run `make universe` in the "
            "doomberg-invest environment with the BRIEF §0.2 network allowlist"
        )
    return None


def _needs_database() -> str | None:
    """M1+ checks need the local PostgreSQL (cloud sessions: scripts/session_start.sh; CI: the postgres service)."""
    url = os.environ.get("DATABASE_URL", "postgresql://doom:doom@localhost:5432/doom")
    probe = ["uv", "run", "--frozen", "python", "-c", "import psycopg, sys; psycopg.connect(sys.argv[1]).close()", url]
    p = subprocess.run(probe, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        return (
            "human:PostgreSQL not reachable at DATABASE_URL, or psycopg not installed "
            "(`make setup`, then `bash scripts/session_start.sh`)"
        )
    return None


def _needs_old_repo() -> str | None:
    old = Path(os.environ.get("DOOMBERG_REPO", ROOT.parent / "doomberg"))
    if not (old / ".git").exists():
        return "human:old doomberg repo not checked out (clone read-only to ../doomberg or set DOOMBERG_REPO)"
    return None


CHECKS: list[Check] = [
    Check("M0-01", "m0", "make setup && make test green", ["bash", "-c", "uv sync --frozen -q && " + " ".join(PYTEST)]),
    Check(
        "M0-02",
        "m0",
        "make guard passes on the repo and fails on each seeded case",
        ["bash", "-c", "uv run --frozen python scripts/guard.py && " + " ".join(PYTEST) + " tests/guard/test_guard.py"],
    ),
    Check("M0-03", "m0", "hook exits 2 on an edit adding `import kiteconnect`", [*PYTEST, "tests/guard/test_hook.py"]),
    Check(
        "M0-04",
        "m0",
        "audit has every section; each claimed rule has a file:line that resolves in the old repo",
        [*PYTEST, "tests/test_audit.py", "-m", "oldrepo or not oldrepo"],
        requires=_needs_old_repo,
    ),
    Check(
        "M0-05",
        "m0",
        "US universe >= 3,000; India EQ >= 1,500; capex seed resolved or listed in UNIVERSE_ISSUES",
        [*PYTEST, "tests/test_universe.py", "-m", "snapshots"],
        requires=_needs_universe_snapshots,
    ),
    Check(
        "M0-06",
        "m0",
        "every default in BRIEF §4.6-4.8 equals the config value",
        [*PYTEST, "tests/test_config_matches_brief.py"],
    ),
    Check(
        "M0-07",
        "m0",
        "protected-path check fails without the human-approved label (synthetic diff)",
        [*PYTEST, "tests/guard/test_protected.py"],
    ),
    Check(
        "M1-01",
        "m1",
        "migrations run from zero twice (re-run is a no-op; changed or failing migrations are rejected)",
        [*PYTEST, "tests/db/test_migrate.py"],
        requires=_needs_database,
    ),
    Check(
        "M1-02",
        "m1",
        "rows filed after W are invisible to as_of(W) (tests try to cheat)",
        [*PYTEST, "tests/db/test_pit.py", "tests/db/test_repo.py"],
        requires=_needs_database,
    ),
    Check(
        "M1-03",
        "m1",
        "RLS on every table; anon/authenticated queries fail; local roles mirror Supabase",
        [*PYTEST, "tests/db/test_rls.py", "tests/db/test_display_views.py"],
        requires=_needs_database,
    ),
    Check(
        "M1-04",
        "m1",
        "projected size for 7,000 companies x 60 quarters < 400 MB (estimator test)",
        [*PYTEST, "tests/db/test_size.py", "tests/db/test_seed.py"],
        requires=_needs_database,
    ),
    Check(
        "M1-05",
        "m1",
        "guard passes on the migrations",
        ["bash", "-c", "uv run --frozen python scripts/guard.py --paths db/migrations/*.sql"],
    ),
    Check(
        "M2-01",
        "m2",
        "F-US quarterized values equal the expected CSVs (AAPL, MSFT, CAT) incl. Q4 derivation; quarterizing rules",
        [*PYTEST, "tests/us/test_fus.py", "tests/us/test_quarterize.py"],
    ),
    Check(
        "M2-02",
        "m2",
        "a restatement creates a new row; as_of returns the right version (Apple FY2017 Q2 CFO)",
        [*PYTEST, "tests/db/test_us_pipeline.py", "-k", "restatement"],
        requires=_needs_database,
    ),
    Check(
        "M2-03",
        "m2",
        "Form 4: code P only; planned via the checkbox and via a footnote; derivatives excluded (F-F4)",
        [*PYTEST, "tests/us/test_form4.py"],
    ),
    Check(
        "M2-04",
        "m2",
        "8-K 4.01 and NT detection (real EDGAR days through the daily run); spin-offs",
        [
            *PYTEST,
            "tests/us/test_events.py",
            "tests/us/test_specials.py",
            "tests/db/test_us_pipeline.py",
            "-k",
            "events or specials or daily or spinoff or weekend or outside_the_universe",
        ],
        requires=_needs_database,
    ),
    Check(
        "M2-05",
        "m2",
        "13F counts correct on F-13F; CUSIP mapping >= 90% on the sample; ownership_q written",
        [*PYTEST, "tests/us/test_thirteenf.py", "tests/db/test_us_pipeline.py", "-k", "thirteenf or 13f"],
        requires=_needs_database,
    ),
    Check(
        "M2-06",
        "m2",
        "US weekly run on fixtures < 10 min (incremental, idempotent, universe rules)",
        [
            *PYTEST,
            "tests/db/test_us_pipeline.py",
            "tests/us/test_universe_rules.py",
            "-k",
            "weekly or universe_rules or decide or sector or rules_come",
        ],
        requires=_needs_database,
    ),
]


def run_check(c: Check) -> Result:
    if c.requires is not None:
        blocked = c.requires()
        if blocked:
            return Result(c, f"BLOCKED({blocked})", 0.0, "")
    t0 = time.monotonic()
    env = {**os.environ, "MOCK_EXTERNALS": "true"}
    p = subprocess.run(c.command, cwd=ROOT, capture_output=True, text=True, env=env)
    tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-6:])
    return Result(c, "PASS" if p.returncode == 0 else "FAIL", time.monotonic() - t0, tail)


def write_report(results: list[Result], target: str) -> None:
    lines = [
        "# Verify report",
        "",
        f"Target `verify-{target}` · {datetime.now(UTC):%Y-%m-%d %H:%M UTC} · generated by `scripts/verify.py`",
        "",
        "| Check | Status | Description | Time |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.check.id} | {r.status} | {r.check.description} | {r.seconds:.1f}s |")
    fails = [r for r in results if r.status == "FAIL"]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines += [f"### {r.check.id}", "```", r.tail, "```"]
    (ROOT / "docs" / "VERIFY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--milestone", required=True, choices=MILESTONES)
    a = ap.parse_args(argv)
    upto = MILESTONES[: MILESTONES.index(a.milestone) + 1]
    results = [run_check(c) for c in CHECKS if c.milestone in upto]
    for r in results:
        print(f"{r.check.id:6} {r.status:10} {r.check.description}")
        if r.status == "FAIL" and r.tail:
            print("       " + r.tail.replace("\n", "\n       "))
    write_report(results, a.milestone)
    n_fail = sum(r.status == "FAIL" for r in results)
    n_block = sum(r.status.startswith("BLOCKED") for r in results)
    print(f"verify-{a.milestone}: {len(results) - n_fail - n_block} PASS, {n_block} BLOCKED, {n_fail} FAIL")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
