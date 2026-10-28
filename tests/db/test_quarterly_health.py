"""A quarterly run that fell back to an older 13F window says so (2026-10-26: it read "ok" and sec_13f stayed fresh
while ownership_q was a quarter behind SEC)."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from pipeline.db import repo
from pipeline.db.models import Company
from pipeline.us.quarterly import load

F13 = Path(__file__).resolve().parents[2] / "fixtures" / "us" / "13f"


def test_a_fallback_run_is_partial_and_sec_13f_reads_stale_until_the_newest_window_loads(
    migrated_url: str, tmp_path: Path
) -> None:
    z = tmp_path / "20241201-20250228.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for name in ("SUBMISSION.tsv", "COVERPAGE.tsv", "INFOTABLE.tsv"):
            zf.write(F13 / name, name)
    note = "13F data set 2025-03-01..2025-05-31 answers 404 at ...: using the window before it"
    with psycopg.connect(migrated_url) as c:
        try:
            repo.upsert_us_companies(c, [Company(market="us", name="Apple Inc.", cik="0000320193", in_universe=True)])
            load(c, [(z, date(2025, 2, 28))], {}, [note])
            h = {r.source: r for r in repo.source_health(c)}["sec_13f"]
            assert h.stale and h.last_error == "stale: " + note and h.last_success is not None
            load(c, [(z, date(2025, 2, 28))], {}, [])  # the newest window loaded: fresh again
            h = {r.source: r for r in repo.source_health(c)}["sec_13f"]
            assert not h.stale and h.last_error is None
            runs: Any = c.execute("select status, stats->'errors' from runs where kind = 'us_13f' order by started_at")
            assert runs.fetchall() == [("partial", [note]), ("ok", None)]
        finally:
            c.rollback()
            c.execute("delete from runs where kind = 'us_13f'")
            c.execute("delete from source_health where source = 'sec_13f'")
            c.execute("delete from companies where cik = '0000320193'")
            c.commit()
