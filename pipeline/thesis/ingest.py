"""Thesis-card ingest (BRIEF §4.9 step 3; thesis-ingest.yml, on a push touching data/thesis_cards/**): the pushed
weeks' sealed cards and main's sealed queue are opened (pipeline/thesis/vault.py; the repository is public, SPEC_ISSUES
60), and every card is validated again against its pack and upserted into `theses` (state `research`, author `routine`)
with its kill criteria. One generated card per company and week: a re-run replaces a card still in `research` and
leaves one Manzoor already moved on alone (idempotent; M6-03). A card that fails validation is not ingested, so a
research entry waiting for it keeps no card and can't be accepted. A card for a company with an open manual research
entry (the queue packs those after the shortlist) fills that entry in place, with its author and validation result
(thesis_repo.upsert_generated_thesis; docs/SPEC_ISSUES.md 35).

The push supplies cards only (M6 review R1-F4): thesis-ingest.yml runs main's code against main's queue files, with
only data/thesis_cards/** taken from the pushed commit, and a push that changed any other path (a queue file, code, a
plaintext card) ingests nothing. `card_md` is always the rendering of the validated JSON, never a pushed .md (R1-F7).
The log is public, so it counts the rejected cards without naming them; the run's stats keep the reasons.

`python -m pipeline.thesis.ingest --changed changed.txt` (the push's changed paths, one per line) or
`--week 2026-W38`."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import facts_repo, repo, thesis_repo
from pipeline.llm.router import Router
from pipeline.settings import REPO_ROOT, Settings
from pipeline.thesis import validate as v
from pipeline.thesis import vault
from pipeline.thesis.evidence_pack import values_by_id
from pipeline.thesis.render import render, title_for

CARD_PATH = re.compile(r"^data/thesis_cards/(?P<week>\d{4}-W\d{2})\.sealed$")


def outside_cards(paths: Iterable[str]) -> list[str]:
    """Changed paths a card push may not touch (anything but a sealed bundle data/thesis_cards/<week>.sealed)."""
    return sorted({p for p in paths if p.strip() and not CARD_PATH.match(p.strip())})


def outside_message(bad: Sequence[str]) -> str:
    """Why a push ingests nothing, naming no card: a plaintext card's path names its company (the log is public)."""
    plain = [p for p in bad if p.startswith("data/thesis_cards/")]
    other = [p for p in bad if not p.startswith("data/thesis_cards/")]
    parts = []
    if plain:
        parts.append(f"{len(plain)} unsealed file(s) under data/thesis_cards/ (a plaintext card names its company and "
                     "the repository is public: delete the branch)")  # fmt: skip
    if other:
        parts.append(f"changed paths outside data/thesis_cards/**: {', '.join(other[:10])}")
    return "; ".join([*parts, "a card push carries only data/thesis_cards/<week>.sealed (make thesis-seal; §4.9)"])


def weeks_of(paths: Iterable[str]) -> list[str]:
    return sorted({m.group("week") for p in paths if (m := CARD_PATH.match(p.strip()))})


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
        md = render(card, title_for(path, root))  # the validated JSON, never a pushed .md (M6 review R1-F7)
        _, written = ingest_card(conn, card, pack, md, "routine", res)
        (stats.ingested if written else stats.unchanged).append(f"{week}/{name}")
    return stats


def open_week(week: str, secret: str | None, root: Path = REPO_ROOT) -> None:
    """The week's sealed queue and sealed cards as working copies (a sealed file replaces its working copy); a week with
    nothing sealed keeps its working copies (a local run, the tests)."""
    queue, cards = vault.sealed_queue(week, root), vault.sealed_cards(week, root)
    if not (queue.exists() or cards.exists()):
        return
    if not secret:
        raise vault.VaultError("THESIS_VAULT_KEY is not set, so the sealed queue and cards can't be read (BRIEF §2.4)")
    if queue.exists():
        vault.open_queue(week, secret, root)
    if cards.exists():
        vault.open_cards(week, secret, root)


def ingest(conn: psycopg.Connection[Any], weeks: Iterable[str], root: Path = REPO_ROOT,
           router: Router | None = None, secret: str | None = None) -> IngestStats:  # fmt: skip
    stats = IngestStats()
    for week in weeks:
        try:
            open_week(week, secret, root)
        except vault.VaultError as e:
            stats.rejected[week] = [str(e)]
            continue
        if v.queue_path(week, root).exists():
            with conn.transaction():
                ingest_week(conn, week, root, router, stats)
        else:
            stats.rejected[week] = [f"no queue for {week} (weekly.yml commits data/thesis_queue/{week}.sealed)"]
    return stats


def from_changed(conn: psycopg.Connection[Any], paths: Iterable[str], root: Path = REPO_ROOT,
                 router: Router | None = None, secret: str | None = None) -> IngestStats:  # fmt: skip
    """A push's changed paths (thesis-ingest.yml): sealed cards only, else nothing is ingested (M6 review R1-F4)."""
    paths = [p.strip() for p in paths if p.strip()]
    bad = outside_cards(paths)
    if bad:
        stats = IngestStats()
        stats.rejected["push"] = [outside_message(bad)]
        return stats
    return ingest(conn, weeks_of(paths), root, router, secret)


def log_lines(stats: IngestStats) -> list[str]:
    """The public log's lines: a rejected card is counted under its week, never named; a week or push error is shown
    (it names no company)."""
    cards: dict[str, int] = {}
    out = []
    for k, errs in stats.rejected.items():
        if "/" in k:
            week = k.split("/", 1)[0]
            cards[week] = cards.get(week, 0) + 1
        else:
            out.append(f"  rejected {k}: {'; '.join(errs)[:500]}")
    out += [f"  rejected {n} card(s) of {week}: the reasons are in this run's stats (runs, kind thesis_ingest)"
            for week, n in sorted(cards.items())]  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas
    from pipeline.net.http import HttpClient

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--changed", type=Path, help="the push's changed paths, one per line (thesis-ingest.yml)")
    src.add_argument("--week", help="an ISO week, e.g. 2026-W38")
    a = ap.parse_args(argv)
    paths = a.changed.read_text(encoding="utf-8").splitlines() if a.changed else []
    weeks = weeks_of(paths) if a.changed else [a.week]
    settings = Settings.from_env()
    secret = settings.thesis_vault_key
    quotas = Quotas.load()
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "thesis_ingest") as tracked:
        router = (facts_repo.logged_router(conn, providers(HttpClient(settings), settings, quotas), quotas,
                                           datetime.now(UTC).date()) if quotas.configured() else None)  # fmt: skip
        stats = (from_changed(conn, paths, router=router, secret=secret) if a.changed
                 else ingest(conn, weeks, router=router, secret=secret))  # fmt: skip
        tracked.update({"weeks": stats.weeks, "ingested": stats.ingested, "unchanged": stats.unchanged,
                        "errors": [f"{k}: {'; '.join(e)}"[:300] for k, e in stats.rejected.items()]})  # fmt: skip
    print(f"thesis ingest {', '.join(weeks) or '(no card changes)'}: {len(stats.ingested)} ingested, "
          f"{len(stats.unchanged)} left as they were, {len(stats.rejected)} rejected")  # fmt: skip
    for line in log_lines(stats):
        print(line)
    return 1 if stats.rejected else 0


if __name__ == "__main__":
    sys.exit(main())
