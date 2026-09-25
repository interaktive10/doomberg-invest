"""The weekly thesis queue (BRIEF §4.9 step 1): the week's shortlist (at most 10 new candidates) as evidence packs in
data/thesis_queue/{YYYY}-W{WW}.json, which weekly.yml commits to main for the routine (Appendix G).

`python -m pipeline.thesis.queue [--week D]`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg

from pipeline.db import repo, thesis_repo
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals.weekly import last_friday
from pipeline.thesis.evidence_pack import build, to_json, week_label

MAX_PACKS = 10


def build_queue(conn: psycopg.Connection[Any], week: date, limit: int = MAX_PACKS) -> dict[str, Any]:
    """The queue document: the shortlist in rank order, one pack each (no timestamps, so a re-run of the same data
    writes the same bytes)."""
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    rows = [r for r in thesis_repo.shortlist(conn, week) if r["company_id"] in companies][:limit]
    packs = [to_json(build(conn, companies[r["company_id"]], week)) for r in rows]
    return {"week": week_label(week), "week_end": week.isoformat(), "packs": packs}


def write(doc: dict[str, Any], root: Path = REPO_ROOT) -> Path:
    path = root / "data" / "thesis_queue" / f"{doc['week']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--week", type=date.fromisoformat, default=last_friday(datetime.now(UTC).date()))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn:
        doc = build_queue(conn, a.week)
    path = write(doc)
    print(f"thesis queue {doc['week']}: {len(doc['packs'])} packs -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
