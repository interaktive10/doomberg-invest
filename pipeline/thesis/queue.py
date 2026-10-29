"""The weekly thesis queue (BRIEF §4.9 step 1): the week's shortlist (at most 10 new candidates) as evidence packs in
data/thesis_queue/{YYYY}-W{WW}.json, sealed to data/thesis_queue/{YYYY}-W{WW}.sealed, which weekly.yml commits to main
for the routine (Appendix G). The repository is public, so the plaintext stays on the runner (pipeline/thesis/vault.py;
docs/SPEC_ISSUES.md 60); without THESIS_VAULT_KEY nothing is committed and the fallback writes the week's cards. After
the shortlist, within the same MAX_PACKS, come the open manual research entries (the web app's Research button: a
thesis in `research` by `manual` with no card yet), oldest first; ingest fills each entry in place with its card
(pipeline/db/thesis_repo.upsert_generated_thesis; docs/SPEC_ISSUES.md 35). An entry that doesn't fit waits for the
next week.

`python -m pipeline.thesis.queue [--week D]`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import repo, thesis_repo
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals.weekly import last_friday
from pipeline.thesis import vault
from pipeline.thesis.evidence_pack import build, to_json, week_label

MAX_PACKS = 10
NO_KEY = ("::notice::THESIS_VAULT_KEY is not set, so no queue is committed (the repository is public; BRIEF §2.4): "
          "Monday's fallback writes the week's cards from the database")  # fmt: skip


def order(shortlist: Sequence[UUID], research: Sequence[UUID], limit: int = MAX_PACKS) -> list[UUID]:
    """The companies to pack: the shortlist in rank order, then the research entries (oldest first) that aren't on it,
    at most `limit` in all."""
    out: list[UUID] = []
    for cid in [*shortlist, *research]:
        if cid not in out:
            out.append(cid)
    return out[:limit]


def build_queue(conn: psycopg.Connection[Any], week: date, limit: int = MAX_PACKS) -> dict[str, Any]:
    """The queue document: the shortlist in rank order, then the research entries, one pack each (no timestamps, so a
    re-run of the same data writes the same bytes)."""
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    shortlist = [r["company_id"] for r in thesis_repo.shortlist(conn, week) if r["company_id"] in companies]
    research = [cid for cid in thesis_repo.research_entries(conn, week) if cid in companies]
    packs = [to_json(build(conn, companies[cid], week)) for cid in order(shortlist, research, limit)]
    return {"week": week_label(week), "week_end": week.isoformat(), "packs": packs}


def write(doc: dict[str, Any], root: Path = REPO_ROOT) -> Path:
    path = root / "data" / "thesis_queue" / f"{doc['week']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def publish(doc: dict[str, Any], secret: str | None, root: Path = REPO_ROOT) -> list[str]:
    """The working copy, and with the key the sealed queue weekly.yml commits (the plaintext never leaves the runner);
    the lines to print."""
    path = write(doc, root)
    lines = [f"thesis queue {doc['week']}: {len(doc['packs'])} packs -> {path.relative_to(root)}"]
    if not secret:
        lines.append(NO_KEY)
        return lines
    written = vault.seal_queue(doc["week"], secret, root)
    lines.append(f"thesis queue {doc['week']}: {'sealed' if written else 'unchanged'} -> "
                 f"{vault.sealed_queue(doc['week'], root).relative_to(root)}")  # fmt: skip
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--week", type=date.fromisoformat, default=last_friday(datetime.now(UTC).date()))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn:
        doc = build_queue(conn, a.week)
    for line in publish(doc, settings.thesis_vault_key):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
