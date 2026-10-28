"""US quarterly run (BRIEF §2.1 "quarterly", §2.5 quarterly.yml): 13F holder counts -> ownership_q.

`python -m pipeline.us.quarterly --windows 1` downloads the latest published 13F data set and writes
ownership_q.inst_holders for universe companies (thirteenf.py does the counting and CUSIP mapping). `--windows 3`
backfills the two windows before it (S8 needs holder growth over 2 quarters); `--zip` reads a local file instead.
The universe rebuild runs in every weekly run (weekly.py); the Lab has no quarterly re-run (SPEC_ISSUES 51).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import OwnershipRow
from pipeline.net.http import HttpClient
from pipeline.settings import REPO_ROOT, Settings
from pipeline.us.thirteenf import (
    DataSet,
    company_holder_counts,
    dataset_urls,
    holders_by_cusip,
    issuer_names,
    main_period,
    map_cusips,
    read_dataset_zip,
    windows_before,
)


def load_overrides(root: Path = REPO_ROOT) -> dict[str, str]:
    cfg = yaml.safe_load((root / "config" / "cusip_overrides.yaml").read_text(encoding="utf-8")) or {}
    return {str(k).strip().upper(): str(v).strip().zfill(10) for k, v in (cfg.get("overrides") or {}).items()}


@dataclass
class Run13FStats:
    period: str = ""
    filings: int = 0
    cusips: int = 0
    mapped_cusips: int = 0
    companies: int = 0
    unmapped: int = 0
    unmapped_top: list[str] = field(default_factory=list)  # "CUSIP ISSUER (holders)", most held first


def run_13f(conn: psycopg.Connection[Any], ds: DataSet, overrides: Mapping[str, str] | None = None) -> Run13FStats:
    """Holder counts for the data set's main period -> ownership_q (universe companies only)."""
    period = main_period(ds)
    holders = holders_by_cusip(ds, period)
    names = {c: n for c, n in issuer_names(ds).items() if c in holders}
    companies = [c for c in repo.companies(conn, market="us", in_universe=True) if c.cik and c.id is not None]
    mapping = map_cusips(names, {c.cik: c.name for c in companies if c.cik}, overrides)
    ids = {c.cik: c.id for c in companies}
    counts = company_holder_counts(holders, mapping)
    rows = [
        OwnershipRow(company_id=cid, quarter_end=period, filed_at=ds.available_at, inst_holders=n, source="sec_13f")
        for cik, n in sorted(counts.items())
        if (cid := ids.get(cik)) is not None
    ]
    repo.upsert_ownership(conn, rows)
    top = sorted(mapping.unmapped.items(), key=lambda kv: -len(holders.get(kv[0], ())))
    return Run13FStats(
        period=period.isoformat(),
        filings=len(ds.filings),
        cusips=len(holders),
        mapped_cusips=len(mapping.cusip_to_cik),
        companies=len(rows),
        unmapped=len(mapping.unmapped),
        unmapped_top=[f"{c} {n} ({len(holders.get(c, ()))})" for c, n in top[:50]],
    )


SPARE_WINDOWS = 2  # how many of the newest windows may still be unpublished before a run fails


def download_first(download: Callable[[str, Path], Path], urls: list[str], dest: Path) -> httpx.HTTPStatusError | None:
    """Download the first of `urls` that exists into `dest`: None when one did, else the last 404. Any other error
    raises (a 403 is SEC refusing us, not a missing file)."""
    last: httpx.HTTPStatusError | None = None
    for url in urls:
        try:
            download(url, dest)
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
            last = e
    return last


def fetch_windows(
    download: Callable[[str, Path], Path], cache: Path, today: date, n: int, notes: list[str] | None = None
) -> list[tuple[Path, date]]:
    """The `n` newest 13F data sets SEC has published, oldest first, each with its window's last filing date (downloaded
    into `cache` unless already there), each tried at every SEC directory (thirteenf.dataset_urls). A window is assumed
    out PUBLISH_LAG_DAYS after it closes, but SEC can take longer, so while the newest windows answer 404 everywhere the
    run falls back to the ones before them and says so in `notes` (load() then marks sec_13f stale); a 404 after a
    published window is an error (a real gap, not a late release)."""
    out: list[tuple[Path, date]] = []
    for start, end in windows_before(today, n + SPARE_WINDOWS):
        if len(out) == n:
            break
        dest = cache / f"{start:%Y%m%d}-{end:%Y%m%d}.zip"
        if not dest.exists():
            urls = dataset_urls(start, end)
            missing = download_first(download, urls, dest)
            if missing is not None:
                if out:
                    raise missing
                note = f"13F data set {start}..{end} answers 404 at {' and '.join(urls)}: using the window before it"
                print(f"::warning::{note}")
                if notes is not None:
                    notes.append(note)
                continue
        out.append((dest, end))
    if len(out) < n:
        raise RuntimeError(f"only {len(out)} of the {n} newest 13F data sets are published")
    return out[::-1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--windows", type=int, default=1, help="how many of the latest published windows to load")
    ap.add_argument("--zip", type=Path, help="a local data set zip instead of downloading")
    ap.add_argument("--filed-through", type=date.fromisoformat, help="with --zip: the window's last filing date")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    client = HttpClient(settings)
    today = datetime.now(UTC).date()
    jobs: list[tuple[Path, date]] = []
    notes: list[str] = []  # newest windows SEC didn't serve: the run is partial and sec_13f reads stale
    if a.zip:
        if a.filed_through is None:
            ap.error("--zip needs --filed-through")
        jobs.append((a.zip, a.filed_through))
    else:
        jobs.extend(fetch_windows(client.download, settings.cache_dir / "us" / "13f", today, a.windows, notes))
    with psycopg.connect(settings.database_url) as conn:
        load(conn, jobs, load_overrides(), notes)
    return 0


def load(
    conn: psycopg.Connection[Any], jobs: list[tuple[Path, date]], overrides: Mapping[str, str], notes: list[str]
) -> None:
    """The us_13f run over the downloaded data sets. With `notes` (a newest window SEC didn't serve) the run is partial
    and sec_13f is stale until a later run loads the newest window: Home's and the digest's banner show it."""
    with repo.tracked_run(conn, "us_13f", "sec_13f") as run:
        run["windows"] = []
        if notes:
            run["errors"] = list(notes)
        for path, filed_through in jobs:
            stats = run_13f(conn, read_dataset_zip(path, filed_through), overrides)
            run["windows"].append(stats.__dict__)
            print(f"13F {stats.period}: {stats.companies} companies, {stats.unmapped} unmapped CUSIPs")
    if notes:  # after tracked_run's success mark, which clears stale
        repo.mark_source_error(conn, "sec_13f", "stale: " + notes[0], stale=True)
        conn.commit()


if __name__ == "__main__":
    sys.exit(main())
