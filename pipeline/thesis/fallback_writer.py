"""The thesis-card fallback (BRIEF §4.9 step 4; thesis-fallback.yml, Monday 06:00 UTC): when no card was ingested for
the week (the routine didn't run, or hit a plan limit), Gemini writes them from the queue's packs with P-04 on the
free tier; each card is validated like the routine's (at most 2 attempts) and upserted with author `fallback`.

It runs only from Monday 06:00 UTC after the week's Friday, and only when the week has no generated card (M6-04). The
packs are main's sealed queue, opened with THESIS_VAULT_KEY; without it (or a sealed queue), they are built from the
database as weekly.yml builds them, for a week that has scores (pipeline/thesis/vault.py; SPEC_ISSUES 60).
`python -m pipeline.thesis.fallback_writer [--week 2026-W38]` (default: the week of the last Friday)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import psycopg
from pydantic import ValidationError

from pipeline.db import facts_repo, repo, thesis_repo
from pipeline.llm.router import Deferred, Router
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals.weekly import last_friday
from pipeline.thesis import queue, vault
from pipeline.thesis import validate as v
from pipeline.thesis.evidence_pack import CardInput, EvidencePack, week_label
from pipeline.thesis.ingest import ingest_card
from pipeline.thesis.render import render

ATTEMPTS = 2
RUN_AT = time(6, 0)  # Monday, UTC (§2.5)


@dataclass
class FallbackStats:
    week: str
    ran: bool = False
    reason: str = ""
    written: list[str] = field(default_factory=list)
    failed: dict[str, list[str]] = field(default_factory=dict)
    deferred: list[str] = field(default_factory=list)


def due(week_end: date) -> datetime:
    """Monday 06:00 UTC after the week's Friday: the routine had Sunday."""
    return datetime.combine(week_end + timedelta(days=(7 - week_end.weekday()) % 7 or 7), RUN_AT, tzinfo=UTC)


def should_run(conn: psycopg.Connection[Any], week_end: date, now: datetime) -> tuple[bool, str]:
    if now < due(week_end):
        return False, f"too early: the fallback waits for the routine until {due(week_end):%Y-%m-%d %H:%M}Z"
    if thesis_repo.generated_theses(conn, week_end):
        return False, "the week already has cards"
    return True, "no cards for the week"


def week_end_of(week: str) -> date:
    """The Friday of an ISO week ("2026-W38" -> 2026-09-18), the week_end its queue and scores use."""
    year, num = week.split("-W")
    return date.fromisocalendar(int(year), int(num), 5)


def prepare(conn: psycopg.Connection[Any], week: str, secret: str | None, root: Path = REPO_ROOT) -> str:
    """The week's packs as the working copy of its queue, which write_cards reads: main's sealed queue opened with the
    key, else the working copy already there, else the packs built from the database as weekly.yml builds them (it
    seals nothing without the key). Returns where the packs came from; "" when the week has no scores, since weekly.yml
    queues a week only after its scores."""
    if secret and vault.sealed_queue(week, root).exists():
        try:
            vault.open_queue(week, secret, root)
            return "the sealed queue"
        except vault.VaultError as e:
            print(f"::warning::thesis fallback: {vault.sealed_queue(week, root).name}: {e}; the packs are built from "
                  "the database")  # fmt: skip
    if v.queue_path(week, root).exists():
        return "the queue file"
    week_end = week_end_of(week)
    if not thesis_repo.scored(conn, week_end):
        return ""
    queue.write(queue.build_queue(conn, week_end), root)
    return "the database"


def write_cards(
    conn: psycopg.Connection[Any],
    router: Router,
    week: str,
    root: Path = REPO_ROOT,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    hype: Sequence[str] | None = None,
) -> FallbackStats:
    stats = FallbackStats(week)
    packs = v.packs_of(week, root)
    if not packs:
        stats.reason = "the queue is empty"
        return stats
    week_end = date.fromisoformat(str(next(iter(packs.values()))["week_end"]))
    ok, stats.reason = should_run(conn, week_end, now())
    if not ok:
        return stats
    stats.ran = True
    words = list(hype) if hype is not None else v.hype_words(root)
    known = {str(c.id) for c in repo.companies(conn) if c.id is not None}
    for key, pack in packs.items():
        if str(pack["company"]["company_id"]) not in known:
            stats.failed[key] = ["the pack's company is not in the database"]
            continue
        _one(conn, router, key, pack, words, stats)
    return stats


def _one(conn: psycopg.Connection[Any], router: Router, key: str, pack: Mapping[str, Any], words: Sequence[str],
         stats: FallbackStats) -> None:  # fmt: skip
    try:
        model = EvidencePack.model_validate(pack)  # the schema first: P-04 reads only a valid pack (M6 R1-F4)
    except ValidationError as e:
        stats.failed[key] = [f"pack: not a valid evidence pack: {e}"[:500]]
        return
    errors: list[str] = []
    for _ in range(ATTEMPTS):
        answer = router.call(CardInput(model))
        if isinstance(answer, Deferred):
            stats.deferred.append(key)
            return
        res = v.validate(answer.content, pack, words, router)
        if res.ok:
            c = pack["company"]
            code = c.get("ticker") or c.get("nse_symbol")
            md = render(answer.content, f"{c['name']}{f' ({code})' if code else ''} — {pack['week']}")
            with conn.transaction():
                ingest_card(conn, answer.content, pack, md, "fallback", res)
            stats.written.append(key)
            return
        errors = res.errors
    stats.failed[key] = errors


def main(argv: list[str] | None = None) -> int:
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas
    from pipeline.net.http import HttpClient

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", default=None, help="ISO week (default: the week of the last Friday)")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    week = a.week or week_label(last_friday(now.date()))
    settings = Settings.from_env()
    quotas = Quotas.load()
    if not quotas.configured():
        print("thesis fallback: no provider quota is set in config/quotas.yaml (BRIEF §11.3); nothing to do")
        return 0
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "thesis_fallback", "llm") as tracked:
        router = facts_repo.logged_router(
            conn, providers(HttpClient(settings), settings, quotas), quotas, datetime.now(UTC).date()
        )  # llm_calls rows, the day's shared budget (R1-F9)
        ok, reason = should_run(conn, week_end_of(week), now)  # before the packs: most Mondays have the cards
        source = prepare(conn, week, settings.thesis_vault_key) if ok else ""
        if ok and not source:
            reason = "the week has no scores, so weekly.yml queued nothing"
        stats = write_cards(conn, router, week) if source else FallbackStats(week, reason=reason)
        tracked.update({"week": week, "packs": source, "ran": stats.ran, "reason": stats.reason,
                        "written": stats.written, "deferred": stats.deferred,
                        "errors": [f"{k}: {'; '.join(e)}"[:300] for k, e in stats.failed.items()]})  # fmt: skip
    print(f"thesis fallback {week}: {'ran' if stats.ran else 'skipped'} ({stats.reason}"
          f"{f'; packs from {source}' if source else ''}); {len(stats.written)} written, {len(stats.failed)} failed, "
          f"{len(stats.deferred)} deferred")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
