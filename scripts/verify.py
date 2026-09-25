#!/usr/bin/env python3
"""Verify harness (BRIEF §9). `verify.py --milestone m0` runs every check for M0 and all earlier milestones.

Statuses: PASS, FAIL, BLOCKED(key:NAME), BLOCKED(human:WHAT). Writes docs/VERIFY_REPORT.md.
Exits non-zero on any FAIL. BLOCKED is reported, never silently turned into PASS.
"""

from __future__ import annotations

import argparse
import os
import shlex
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


def _needs_f_in() -> str | None:
    """F-IN comes from NSE/BSE; if NSE blocks the fetch, Manzoor downloads the files (BRIEF Appendix fixtures)."""
    need = ("bhavcopy", "results", "shareholding", "pit/disclosures", "securities", "announcements")
    missing = [d for d in need if not any((ROOT / "fixtures" / "in" / d).glob("*.*"))]
    if missing:
        return "human:F-IN fixtures missing (" + ", ".join(missing) + "); run `fetch_fixtures.py f-in` or add the files"
    return None


def _needs_db_and_f_in() -> str | None:
    return _needs_f_in() or _needs_database()


LAB_PRICES = ROOT / ".cache" / "lab" / "d_us_txt.zip"


def _needs_lab_prices() -> str | None:
    """M8-05: the Stooq bulk daily file is downloaded by hand once (CAPTCHA) into the `lab-data-v1` release; lab.yml
    fetches it to .cache/lab/."""
    if not LAB_PRICES.exists():
        return "human:Stooq bulk file d_us_txt.zip not attached to the lab-data-v1 release (BRIEF §2.7)"
    return _needs_database()


def _needs_old_repo() -> str | None:
    old = Path(os.environ.get("DOOMBERG_REPO", ROOT.parent / "doomberg"))
    if not (old / ".git").exists():
        return "human:old doomberg repo not checked out (clone read-only to ../doomberg or set DOOMBERG_REPO)"
    return None


def _both(first: list[str], second: list[str]) -> list[str]:
    """Two pytest runs in one check (a -k filter for the DB tests must not deselect the pure ones)."""
    run = " ".join(PYTEST)
    return ["bash", "-c", f"{run} {' '.join(map(shlex.quote, first))} && {run} {' '.join(map(shlex.quote, second))}"]


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
        [*PYTEST, "tests/db/test_us_pipeline.py", "-k", "restatement or vintage"],
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
    Check(
        "M3-01",
        "m3",
        "the UDiFF bhavcopy parser works on F-IN (NSE and BSE) and tolerates unknown columns",
        [*PYTEST, "tests/india/test_parsers.py", "-k", "bhavcopy or columns"],
        requires=_needs_f_in,
    ),
    Check(
        "M3-02",
        "m3",
        "3 real results XBRL map to the expected fundamentals_q rows; half-yearly balance sheet / cash flow",
        [
            *PYTEST,
            "tests/india/test_parsers.py",
            "tests/db/test_india_pipeline.py",
            "-k",
            "kei or half_yearly or consolidated or legacy or unsafe or weekly_run",
        ],
        requires=_needs_db_and_f_in,
    ),
    Check(
        "M3-03",
        "m3",
        "shareholding and pledge % from 3 real XBRL files; written to ownership_q point-in-time",
        [*PYTEST, "tests/india/test_parsers.py", "tests/db/test_india_pipeline.py", "-k", "shareholding or weekly_run"],
        requires=_needs_db_and_f_in,
    ),
    Check(
        "M3-04",
        "m3",
        "promoter purchases detected from the PIT sample (and stored by the daily run)",
        [*PYTEST, "tests/india/test_pit.py", "tests/db/test_india_pipeline.py", "-k", "pit or promoter or daily"],
        requires=_needs_db_and_f_in,
    ),
    Check(
        "M3-05",
        "m3",
        "3 simulated 403s -> stale, then BSE fallback, then a manual CSV import produces rows",
        [
            *PYTEST,
            "tests/india/test_access.py",
            "tests/db/test_india_pipeline.py",
            "-k",
            "403 or stale or bse or manual or nothing or holiday or bhavdata",
        ],
        requires=_needs_db_and_f_in,
    ),
    Check(
        "M3-06",
        "m3",
        "<= 1 request per 3 s to NSE enforced",
        [*PYTEST, "tests/india/test_access.py", "tests/test_http.py", "-k", "rate"],
    ),
    Check(
        "M4-01",
        "m4",
        "every S1-S12 and R1-R6: a true, a false and a just-below-threshold case on F-SYNQ",
        [*PYTEST, "tests/signals/test_synq.py", "tests/signals/test_series.py"],
    ),
    Check(
        "M4-02",
        "m4",
        "signals as of W are identical whether or not later filings exist",
        [
            *PYTEST,
            "tests/db/test_signals_pipeline.py",
            "tests/db/test_pit.py",
            "-k",
            "later_filings or fundamental_versions or facts_need",
        ],
        requires=_needs_database,
    ),
    Check(
        "M4-03",
        "m4",
        "reverse DCF recovers a known g within +/-0.1 pp from a synthetic EV; monotonic; null with no root",
        [*PYTEST, "tests/signals/test_reverse_dcf.py"],
    ),
    Check(
        "M4-04",
        "m4",
        "Stooq and bhavcopy weekly ingestion; split detection needs share-count confirmation",
        _both(
            ["tests/prices", "tests/signals/test_splits.py"],
            [
                "tests/db/test_signals_pipeline.py",
                "tests/db/test_india_pipeline.py",
                "-k",
                "scoring_run or manual_price_import or india_weekly_run",
            ],
        ),  # fmt: skip
        requires=_needs_db_and_f_in,
    ),
    Check(
        "M4-05",
        "m4",
        "Evidence/Gap/bucket math, the 2-family cap, soft-flag penalties, the 12-week novelty rule; screener API",
        _both(["tests/signals/test_scores.py"], ["tests/db/test_signals_pipeline.py", "-k", "older_weeks or screen"]),
        requires=_needs_database,
    ),
    Check(
        "M4-06",
        "m4",
        "GDELT client (mock) and percentiles",
        [*PYTEST, "tests/signals/test_context.py"],
    ),
    Check(
        "M8-01",
        "m8",
        "F-LAB planted signal detected (t_nw >= 3 out of sample); noise signal |t_nw| < 2",
        [*PYTEST, "tests/lab/test_lab.py", "-k", "planted or noise"],
    ),
    Check(
        "M8-02",
        "m8",
        "leak test: moving filed_at later removes the planted effect (the panel runs the live signal code)",
        [*PYTEST, "tests/lab/test_lab.py", "-k", "filed_at or live_signal_code or event"],
    ),
    Check(
        "M8-03",
        "m8",
        "the report prints the §7 caveats verbatim",
        [*PYTEST, "tests/lab/test_report.py"],
    ),
    Check(
        "M8-04",
        "m8",
        "the proposal PR touches only config/weights.yaml and needs the label",
        [*PYTEST, "tests/lab/test_proposals.py"],
    ),
    Check(
        "M8-05",
        "m8",
        "a real run needs the Stooq bulk release asset (BLOCKED(human) until it exists)",
        ["uv", "run", "--frozen", "python", "-m", "pipeline.lab.run", "--market", "us", "--prices", str(LAB_PRICES)],
        requires=_needs_lab_prices,
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
