"""Thesis-card ingest (BRIEF §4.9 step 3; thesis-ingest.yml, on a push touching data/thesis_cards/**): every card of
the pushed weeks is validated again against its pack and upserted into `theses` (state `research`, author `routine`)
with its kill criteria. One generated card per company and week: a re-run replaces a card still in `research` and
leaves one Manzoor already moved on alone (idempotent; M6-03). A card that fails validation is not ingested.

`python -m pipeline.thesis.ingest --event "$GITHUB_EVENT_PATH"` (the weeks come from the push's changed paths) or
`--week 2026-W38`."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import repo, thesis_repo
from pipeline.llm.router import Router
from pipeline.settings import REPO_ROOT, Settings
from pipeline.thesis import validate as v
from pipeline.thesis.evidence_pack import values_by_id
from pipeline.thesis.render import render, title_for

CARD_PATH = re.compile(r"^data/thesis_cards/(?P<week>\d{4}-W\d{2})/[^/]+\.(?:json|md)$")


@dataclass
class IngestStats:
    weeks: list[str] = field(default_factory=list)
    ingested: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)  # already accepted or dismissed: left alone
    rejected: dict[str, list[str]] = field(default_factory=dict)


def weeks_from_event(event: Mapping[str, Any]) -> list[str]:
    """The weeks whose cards a push added or changed (GitHub's push event payload: commits[].added/modified)."""
    paths: set[str] = set()
    for c in event.get("commits") or []:
        paths.update(c.get("added") or [])
        paths.update(c.get("modified") or [])
    head = event.get("head_commit") or {}
    paths.update(head.get("added") or [])
    paths.update(head.get("modified") or [])
    return sorted({m.group("week") for p in paths if (m := CARD_PATH.match(p))})


def criteria(card: Mapping[str, Any], pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = values_by_id(pack)
    out = []
    for k in card.get("kill_criteria") or []:
        base = next(iter(values.get(str(k["metric_id"])) or []), None)
        t = k.get("threshold")
        out.append({"metric": str(k["metric_id"]), "operator": str(k["operator"]),
                    "threshold": None if t is None else Decimal(str(t)),
                    "check_after": date.fromisoformat(str(k["check_after"])),
                    "baseline": base, "why": str(k.get("why") or "")})  # fmt: skip
    return out


def ingest_card(
    conn: psycopg.Connection[Any], card: Mapping[str, Any], pack: Mapping[str, Any], md: str, author: str,
    result: v.Result,
) -> tuple[UUID, bool]:  # fmt: skip
    company_id = UUID(str(pack["company"]["company_id"]))
    week_end = date.fromisoformat(str(pack["week_end"]))
    return thesis_repo.upsert_generated_thesis(conn, company_id, week_end, author, md, dict(card), dict(pack),
                                               result.as_json(), criteria(card, pack))  # fmt: skip


def ingest_week(conn: psycopg.Connection[Any], week: str, root: Path = REPO_ROOT, router: Router | None = None,
                stats: IngestStats | None = None) -> IngestStats:  # fmt: skip
    stats = stats or IngestStats()
    stats.weeks.append(week)
    packs = v.packs_of(week, root)
    known = {str(c.id) for c in repo.companies(conn) if c.id is not None}
    for name, res in v.validate_week(week, root, router).items():
        key = Path(name).stem
        if not res.ok:
            stats.rejected[f"{week}/{name}"] = res.errors
            continue
        pack = packs[key]
        if str(pack["company"]["company_id"]) not in known:
            stats.rejected[f"{week}/{name}"] = ["the pack's company is not in the database"]
            continue
        path = v.cards_dir(week, root) / name
        card = json.loads(path.read_text(encoding="utf-8"))
        md_path = path.with_suffix(".md")
        md = md_path.read_text(encoding="utf-8") if md_path.exists() else render(card, title_for(path, root))
        _, written = ingest_card(conn, card, pack, md, "routine", res)
        (stats.ingested if written else stats.unchanged).append(f"{week}/{name}")
    return stats


def ingest(conn: psycopg.Connection[Any], weeks: Iterable[str], root: Path = REPO_ROOT,
           router: Router | None = None) -> IngestStats:  # fmt: skip
    stats = IngestStats()
    for week in weeks:
        if v.queue_path(week, root).exists():
            with conn.transaction():
                ingest_week(conn, week, root, router, stats)
        else:
            stats.rejected[week] = [f"no queue file {v.queue_path(week, root).name}"]
    return stats


def main(argv: list[str] | None = None) -> int:
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas
    from pipeline.net.http import HttpClient

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--event", type=Path, help="the GitHub push event JSON (GITHUB_EVENT_PATH)")
    src.add_argument("--week", help="an ISO week, e.g. 2026-W38")
    a = ap.parse_args(argv)
    weeks = [a.week] if a.week else weeks_from_event(json.loads(a.event.read_text(encoding="utf-8")))
    settings = Settings.from_env()
    quotas = Quotas.load()
    router = Router(providers(HttpClient(settings), settings, quotas), quotas) if quotas.configured() else None
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "thesis_ingest") as tracked:
        stats = ingest(conn, weeks, router=router)
        tracked.update({"weeks": stats.weeks, "ingested": stats.ingested, "unchanged": stats.unchanged,
                        "errors": [f"{k}: {'; '.join(e)}"[:300] for k, e in stats.rejected.items()]})  # fmt: skip
    print(f"thesis ingest {', '.join(weeks) or '(no card changes)'}: {len(stats.ingested)} ingested, "
          f"{len(stats.unchanged)} left as they were, {len(stats.rejected)} rejected")  # fmt: skip
    for k, errs in stats.rejected.items():
        print(f"  rejected {k}: {'; '.join(errs)[:500]}")
    return 1 if stats.rejected else 0


if __name__ == "__main__":
    sys.exit(main())
