"""US weekly run (BRIEF §2.1 "weekly", §4.1, §1.3): companyfacts + submissions -> fundamentals_q + universe status.
`python -m pipeline.us.weekly --companyfacts companyfacts.zip --submissions submissions.zip`.

Incremental (BRIEF §4.1.1): a state file keeps each company's companyfacts sha256 and TTM revenue; unchanged
companies are not re-quarterized. The state is versioned by the xbrl_map and QUARTERIZE_VERSION, so a change to
either re-quarterizes everyone; after a database restore, run with --force. The bulk files stay on the runner, never
in the database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import yaml

from pipeline.db import repo
from pipeline.net.http import HttpClient
from pipeline.settings import REPO_ROOT, Settings
from pipeline.us.companyfacts import Alternative
from pipeline.us.fundamentals import load_xbrl_map, quarterize_company, write_company
from pipeline.us.submissions import parse_submissions
from pipeline.us.universe import UniverseRules, decide, sector_for_sic

QUARTERIZE_VERSION = "1"  # bump when quarterize.py / companyfacts.py change what they produce


def state_version(xbrl_map: Mapping[str, Sequence[Alternative]]) -> str:
    blob = json.dumps(xbrl_map, sort_keys=True, default=str) + QUARTERIZE_VERSION
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


class JsonSource:
    """Members of a bulk zip (companyfacts.zip, submissions.zip) or a directory of the same JSON files."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip = zipfile.ZipFile(path) if path.is_file() else None
        names = self._zip.namelist() if self._zip else [p.name for p in path.glob("*.json")]
        self._names = set(names)

    def read(self, name: str) -> bytes | None:
        if name not in self._names:
            return None
        return self._zip.read(name) if self._zip else (self.path / name).read_bytes()

    def pages(self, cik: str) -> list[bytes]:
        prefix = f"CIK{cik}-submissions-"
        return [b for n in sorted(self._names) if n.startswith(prefix) and (b := self.read(n)) is not None]


@dataclass
class WeeklyStats:
    companies: int = 0
    quarterized: int = 0
    unchanged: int = 0
    no_companyfacts: int = 0
    no_submissions: int = 0
    rows: int = 0
    issues: int = 0
    in_universe: int = 0
    out_of_universe: int = 0
    issue_samples: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # one bad company never stops the run
    seconds: float = 0.0


def run_weekly(
    conn: psycopg.Connection[Any],
    companyfacts: JsonSource,
    submissions: JsonSource,
    today: date,
    state_path: Path | None = None,
    force: bool = False,
    root: Path = REPO_ROOT,
) -> WeeklyStats:
    t0 = time.monotonic()
    stats = WeeklyStats()
    xbrl_map = load_xbrl_map(root)
    version = state_version(xbrl_map)
    rules = UniverseRules.load(root)
    sectors = yaml.safe_load((root / "config" / "sectors.yaml").read_text(encoding="utf-8"))["us_sic_ranges"]
    state: dict[str, dict[str, str]] = {}
    if state_path is not None and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    for company in repo.companies(conn, market="us"):
        if not company.cik or company.id is None:
            continue
        stats.companies += 1
        try:
            with conn.transaction():  # a savepoint: a failing company leaves no partial rows
                prev = state.get(company.cik, {})
                redo = force or prev.get("v") != version
                done = _one_company(conn, company.cik, company.id, companyfacts, submissions, today, prev, redo,
                                    stats, xbrl_map, rules, sectors)  # fmt: skip
        except Exception as e:  # noqa: BLE001 — logged in the run's stats; the run is marked partial
            stats.errors.append(f"{company.cik}: {type(e).__name__}: {e}"[:300])
            continue
        if done is not None:  # only once its rows are written, so a failed company is retried next week
            state[company.cik] = {**done, "v": version}
    if state_path is not None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    stats.issue_samples = stats.issue_samples[:20]
    stats.errors = stats.errors[:50]
    stats.seconds = round(time.monotonic() - t0, 2)
    return stats


def _one_company(
    conn: psycopg.Connection[Any],
    cik: str,
    company_id: UUID,
    companyfacts: JsonSource,
    submissions: JsonSource,
    today: date,
    prev: dict[str, str],
    force: bool,
    stats: WeeklyStats,
    xbrl_map: Mapping[str, Sequence[Alternative]],
    rules: UniverseRules,
    sectors: dict[str, list[list[int]]],
) -> dict[str, str] | None:
    """Quarterize one company if its companyfacts changed and re-decide its universe status. Returns its new state
    entry (sha256, TTM revenue) when it was quarterized."""
    raw_sub = submissions.read(f"CIK{cik}.json")
    if raw_sub is None:
        stats.no_submissions += 1
        return None
    subs = parse_submissions(json.loads(raw_sub), [json.loads(p) for p in submissions.pages(cik)])
    raw_cf = companyfacts.read(f"CIK{cik}.json")
    ttm: Decimal | None = None
    done: dict[str, str] | None = None
    if raw_cf is None:
        stats.no_companyfacts += 1
    else:
        digest = hashlib.sha256(raw_cf).hexdigest()
        if not force and prev.get("sha256") == digest:
            stats.unchanged += 1
            ttm = Decimal(prev["ttm_revenue"]) if prev.get("ttm_revenue") else None
        else:
            result = quarterize_company(json.loads(raw_cf), subs, xbrl_map, today)
            stats.rows += write_company(conn, company_id, result)
            stats.quarterized += 1
            stats.issues += len(result.issues)
            stats.issue_samples += [f"{cik} {i.period_end} {i.column}: {i.reason}" for i in result.issues][:2]
            ttm = result.ttm_revenue()
            done = {"sha256": digest, "ttm_revenue": str(ttm) if ttm is not None else ""}
    decision = decide(subs, ttm, rules, today)
    repo.update_us_company(
        conn,
        cik,
        name=subs.name or None,
        sic=subs.sic,
        industry=subs.sic_description,
        sector=sector_for_sic(subs.sic, sectors),
        fiscal_year_end=subs.fiscal_year_end,
        in_universe=decision.in_universe,
        excluded_reason=decision.reason,
    )
    stats.in_universe += decision.in_universe
    stats.out_of_universe += not decision.in_universe
    return done


BULK = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--companyfacts", type=Path, help="companyfacts.zip or a directory (default: download it)")
    ap.add_argument("--submissions", type=Path, help="submissions.zip or a directory (default: download it)")
    ap.add_argument("--force", action="store_true", help="re-quarterize every company")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    client = HttpClient(settings)
    bulk = settings.cache_dir / "us" / "bulk"
    companyfacts = a.companyfacts or client.download(f"{BULK}/companyfacts.zip", bulk / "companyfacts.zip")
    submissions = a.submissions or client.download(f"{BULK}/submissions.zip", bulk / "submissions.zip")
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "us_weekly", "sec") as run:
        stats = run_weekly(
            conn,
            JsonSource(companyfacts),
            JsonSource(submissions),
            datetime.now(UTC).date(),
            settings.cache_dir / "us" / "companyfacts_state.json",
            force=a.force,
        )
        run.update(stats.__dict__)
    print(f"us weekly: {stats.quarterized} quarterized, {stats.unchanged} unchanged, {stats.rows} rows, "
          f"{stats.in_universe} in universe, {len(stats.errors)} errors, {stats.seconds}s")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
