"""Research cards on demand (research.yml, every 10 minutes; docs/SPEC_ISSUES.md 66). The web app's Research button
opens a manual research entry with no card (app/(app)/candidates/actions.ts); until now the entry waited for Sunday's
routine. This writes its card now: the evidence pack as of the entry's week (as weekly.yml builds packs), P-04 through
the router (OpenRouter's DeepSeek first), validated like every card, and filled into the same entry
(thesis_repo.upsert_generated_thesis: author `fallback`, the link stays the same).

- At most MAX_PER_RUN entries a run, oldest first. A run the router defers (out of budget) leaves the entry for the
  next run. A card that fails validation twice (fallback_writer.ATTEMPTS) counts as one attempt; after MAX_ATTEMPTS
  the entry is left for the routine and the web app says why (validation.on_demand).
- When the week already has a generated card of the company (it was on the shortlist), the entry points to it.

`python -m pipeline.thesis.on_demand`."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import facts_repo, repo, thesis_repo
from pipeline.db.models import Company
from pipeline.llm.router import Router
from pipeline.settings import REPO_ROOT, Settings
from pipeline.thesis import validate as v
from pipeline.thesis.evidence_pack import build, to_json
from pipeline.thesis.fallback_writer import FallbackStats, write_one

MAX_PER_RUN = 3
MAX_ATTEMPTS = 2


@dataclass
class OnDemandStats:
    written: int = 0
    pointed: int = 0
    deferred: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def db_pack(conn: psycopg.Connection[Any], company: Company, week: date) -> dict[str, Any]:
    return to_json(build(conn, company, week))


PackOf = Callable[[psycopg.Connection[Any], Company, date], dict[str, Any]]


def run(conn: psycopg.Connection[Any], router: Router, root: Path = REPO_ROOT, limit: int = MAX_PER_RUN,
        pack_of: PackOf = db_pack) -> OnDemandStats:  # fmt: skip
    stats = OnDemandStats()
    entries = thesis_repo.pending_research(conn, MAX_ATTEMPTS, limit)
    if not entries:
        return stats
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    words = v.hype_words(root)
    for e in entries:
        tid: UUID = e["id"]
        cid: UUID = e["company_id"]
        week = e["created_week"]
        attempts = int(e["attempts"]) + 1
        existing = thesis_repo.generated_for(conn, cid, week)
        if existing is not None:
            with conn.transaction():
                thesis_repo.mark_research(conn, tid, {"card": str(existing), "attempts": attempts - 1})
            stats.pointed += 1
            continue
        company = companies.get(cid)
        if company is None:
            errors = ["the company is not in the database"]
        else:
            try:
                pack = pack_of(conn, company, week)
            except (ValueError, KeyError, TypeError, AssertionError) as ex:  # no rows for the week: say so, go on
                pack, errors = None, [f"no evidence pack for the week: {type(ex).__name__}: {ex}"[:300]]
            if pack is not None:
                one = FallbackStats(week=str(pack["week"]))
                write_one(conn, router, str(pack["company"]["key"]), pack, words, one)
                if one.written:
                    stats.written += 1
                    continue
                if one.deferred:
                    stats.deferred += 1
                    continue
                errors = next(iter(one.failed.values()), ["no card"])
        with conn.transaction():
            thesis_repo.mark_research(conn, tid, {"attempts": attempts, "errors": [x[:300] for x in errors[:5]],
                                                  "at": datetime.now(UTC).isoformat(timespec="seconds")})  # fmt: skip
        stats.failed += 1
        stats.errors.append(f"{tid}: {'; '.join(errors)[:200]}")
    return stats


def main() -> int:
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas
    from pipeline.net.http import HttpClient

    settings = Settings.from_env()
    quotas = Quotas.load()
    if not quotas.configured():
        print("research cards: no provider quota is set in config/quotas.yaml; nothing to do")
        return 0
    with psycopg.connect(settings.database_url) as conn:
        if not thesis_repo.pending_research(conn, MAX_ATTEMPTS, 1):
            print("research cards: none waiting")
            return 0
        with repo.tracked_run(conn, "research_cards", "llm") as tracked:
            router = facts_repo.logged_router(
                conn, providers(HttpClient(settings), settings, quotas), quotas, datetime.now(UTC).date()
            )
            stats = run(conn, router)
            tracked.update({"written": stats.written, "pointed": stats.pointed, "deferred": stats.deferred,
                            "failed": stats.failed, "errors": stats.errors})  # fmt: skip
    # the log is public (the repository is): counts only, no company
    print(f"research cards: {stats.written} written, {stats.pointed} already had a card, {stats.deferred} deferred, "
          f"{stats.failed} failed")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
