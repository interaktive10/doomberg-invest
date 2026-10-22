"""The weekly digest (BRIEF §4.12): a GitHub issue "Doomberg weekly — {week}" (the web Home screen shows the same
markdown, from the `digests` table: the funnel and What changed from body_md, To do live from the database).

Sections, in order, each under a level-2 heading (overhaul PR 5, docs/SPEC_ISSUES.md 53):
- "## This week": the funnel line per market, from the week's stored scores and shortlist ('US 4,659 → stage 456 →
  candidates 4 → new 0 · 440 of 456 fire one family, capped at 55': scored, Evidence >= the stage threshold, the
  Candidate bucket, the shortlist, and the stage names with fewer than two families). A week without scores still
  goes out and says why, from weekly.yml's job results.
- "## To do": cards to accept or dismiss and theses in review, as counts and company names only.
- "## What changed": at most 20 lines (pipeline/digest/changes.py).
- "## Health": one line naming every source that is stale or past its §2.7 SLA (config/staleness.yaml), then the
  Actions minutes line (pipeline/digest/minutes.py).
No LLM, no price-move content (no gainers, losers or returns), and nothing a thesis's owner wrote: journal entries,
positions, notes and reasons never reach the issue.

`python -m pipeline.digest.weekly [--week D]` (weekly.yml `publish` job: every week, whatever the other jobs did).
The issue is published with GITHUB_TOKEN / GITHUB_REPOSITORY from Actions; without them (or with MOCK_EXTERNALS=true)
it is only stored.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import yaml

from pipeline.db import repo, thesis_repo
from pipeline.db.models import SourceHealth
from pipeline.digest import changes, minutes
from pipeline.digest.github_issue import GitHubIssues, Issues, MockIssues, publish
from pipeline.lab import price_history
from pipeline.lab.run import lab_config
from pipeline.net.http import HttpClient
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals.weekly import last_friday
from pipeline.thesis.evidence_pack import week_label


def sla_days(root: Any = REPO_ROOT) -> dict[str, int]:
    """Each source's §2.7 SLA in days (config/staleness.yaml)."""
    doc = yaml.safe_load((root / "config" / "staleness.yaml").read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in (doc.get("sla_days") or {}).items()}


def fallbacks(root: Any = REPO_ROOT) -> dict[str, str]:
    """Fallback source -> its primary (config/staleness.yaml `fallback_of`: bse -> nse, none while India is paused)."""
    doc = yaml.safe_load((root / "config" / "staleness.yaml").read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in (doc.get("fallback_of") or {}).items()}


def scores_config(root: Any = REPO_ROOT) -> dict[str, Any]:
    """config/signals.yaml `scores` (the stage threshold, the two-family rule and its cap)."""
    doc = yaml.safe_load((root / "config" / "signals.yaml").read_text(encoding="utf-8"))
    return dict(doc["scores"])


UNSCORED = "the scoring run didn't finish"  # a digest run outside weekly.yml: the jobs' results aren't known
ENDED = {"failure": "failed", "cancelled": "was cancelled or timed out"}  # needs.<job>.result, besides success/skipped


def unscored_why(env: Mapping[str, str]) -> str:
    """Why a week has no scores, from weekly.yml's job results (the digest step's US_RESULT and SCORES_RESULT are
    needs.<job>.result, US_RAN the us job's secret check): scores run only after a us job that ran and succeeded."""
    us, scores = env.get("US_RESULT", ""), env.get("SCORES_RESULT", "")
    if us in ENDED:
        return f"the US data run {ENDED[us]}, so nothing was scored"
    if us == "success" and env.get("US_RAN") != "true":
        return "the US data run skipped its steps (a secret is missing), so nothing was scored"
    if scores in ENDED:
        return f"the scoring run {ENDED[scores]}"
    if scores == "success":
        return "the scoring run finished without writing any"
    return UNSCORED


def funnel_line(row: Mapping[str, Any], cap: Any) -> str:
    n = {k: int(row[k]) for k in ("scored", "stage", "candidates", "shortlisted", "one_family")}
    return (f"{str(row['market']).upper()} {n['scored']:,} → stage {n['stage']:,} → candidates {n['candidates']:,} → "
            f"new {n['shortlisted']:,} · {n['one_family']:,} of {n['stage']:,} fire one family, capped at "
            f"{cap}")  # fmt: skip


def this_week(funnel: Sequence[Mapping[str, Any]], week: date, cap: Any, why: str = UNSCORED) -> list[str]:
    if not funnel:
        return [f"**Candidates are missing this week:** no scores were written for {week:%Y-%m-%d} ({why}; see "
                "health below)."]  # fmt: skip
    out: list[str] = []
    for r in funnel:  # one paragraph per market (the US alone while India is paused)
        out += [*([""] if out else []), funnel_line(r, cap)]
    return out


def _name(r: Mapping[str, Any]) -> str:
    code = r["ticker"] if r["market"] == "us" else r["nse_symbol"]
    return f"{r['name']} ({code})" if code else str(r["name"])


def to_do(cards: Sequence[Mapping[str, Any]], reviewing: Sequence[Mapping[str, Any]]) -> list[str]:
    """Counts and company names only."""
    out = []
    if cards:
        out.append(f"- Cards to accept or dismiss: {len(cards)} ({', '.join(map(_name, cards))})")
    if reviewing:
        out.append(f"- Theses in review: {len(reviewing)} ({', '.join(map(_name, reviewing))})")
    return out or ["Nothing needs you this week."]


def late(h: SourceHealth, now: datetime, sla: Mapping[str, int]) -> bool:
    days = sla.get(h.source)
    return days is not None and h.last_success is not None and now - h.last_success > timedelta(days=days)


def resting(h: SourceHealth, rows: Sequence[SourceHealth], now: datetime, sla: Mapping[str, int],
            fallback_of: Mapping[str, str]) -> bool:  # fmt: skip
    """A fallback source whose primary is fine: it isn't needed, so its age says nothing (M6 review R2-F5)."""
    primary = next((r for r in rows if r.source == fallback_of.get(h.source)), None)
    return (primary is not None and not primary.stale and primary.last_success is not None
            and not late(primary, now, sla))  # fmt: skip


def banner(rows: Sequence[SourceHealth], now: datetime, sla: Mapping[str, int],
           fallback_of: Mapping[str, str] | None = None) -> list[str]:  # fmt: skip
    """§2.7: every source with an SLA in config/staleness.yaml that is stale, or past its SLA, in one line (a fallback
    only when its primary isn't fine). A source without an SLA is one the pipeline no longer reads (yahoo, stooq,
    fred, eia, gdelt; India's while it is paused): its leftover health row never reaches the line, as on the app's
    Home (overhaul PR 4, docs/SPEC_ISSUES.md 52)."""
    items = []
    for h in rows:
        if h.source not in sla or resting(h, rows, now, sla, fallback_of or {}):
            continue
        if h.stale:
            items.append(f"{h.source} (stale)")
        elif late(h, now, sla) and h.last_success is not None:
            items.append(f"{h.source} (no success for {(now - h.last_success).days} days; SLA {sla[h.source]})")
    return [f"**Stale data:** {', '.join(items)}. Signals and scores that read these sources may be out of date."
            ] if items else []  # fmt: skip


def health_line(rows: Sequence[SourceHealth], now: datetime, sla: Mapping[str, int],
                fallback_of: Mapping[str, str] | None = None) -> str:  # fmt: skip
    """The digest's one health line: the late sources (banner), else that none is late."""
    if not rows:
        return "No source has reported yet."
    late_ones = banner(rows, now, sla, fallback_of)
    return late_ones[0] if late_ones else "Sources: none late or stale."


def health(rows: Sequence[SourceHealth], now: datetime, sla: Mapping[str, int] | None = None,
           fallback_of: Mapping[str, str] | None = None) -> list[str]:  # fmt: skip
    """Each source's status as a table, the way the app's Settings reads it (web/lib/staleness.ts; tests/
    test_web_parity.py keeps the two alike). The digest prints only health_line since overhaul PR 5."""
    if not rows:
        return ["No source has reported yet."]
    sla = sla if sla is not None else sla_days()
    out = ["| Source | Last success | Status |", "|---|---|---|"]
    for h in rows:
        if resting(h, rows, now, sla, fallback_of or {}):
            status = f"fallback, not needed ({(fallback_of or {})[h.source]} ok)"
        elif h.stale:
            status = "**stale**" + (f": {h.last_error.removeprefix('stale: ')[:120]}" if h.last_error else "")
        elif h.last_error:
            status = f"error: {h.last_error[:120]}"
        elif h.last_success is None:
            status = "never succeeded"
        elif late(h, now, sla):
            status = f"late (no success for {(now - h.last_success).days} days; SLA {sla[h.source]} days)"
        else:
            status = "ok"
        when = "never" if h.last_success is None else f"{h.last_success:%Y-%m-%d %H:%M}Z"
        out.append(f"| {h.source} | {when} | {status} |")
    return out


def render(week: date, sections: Sequence[tuple[str, Sequence[str]]]) -> str:
    lines = [f"Week ending {week:%Y-%m-%d}. Research only: no orders, no price alerts.", ""]
    for name, body in sections:
        lines += [f"## {name}", "", *body, ""]
    return "\n".join(lines).rstrip() + "\n"


def build(conn: psycopg.Connection[Any], week: date, app_url: str = "", now: datetime | None = None,
          why_unscored: str = UNSCORED, actions: Sequence[str] = ()) -> tuple[str, str]:  # fmt: skip
    """`actions`: the Actions minutes line (minutes.digest_lines), after the health line."""
    now = now or datetime.now(UTC)
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    cfg = scores_config()
    funnel = thesis_repo.funnel(conn, week, Decimal(str(cfg["us_price_candidate_min_evidence"])),
                                int(cfg["min_families"]))  # fmt: skip
    names, facts = changes.gather(conn, week, companies)
    changed = changes.lines(names, facts, app_url) or [changes.NOTHING if funnel else changes.UNSCORED]
    health_ = health_line(repo.source_health(conn), now, sla_days(), fallbacks())
    body = render(week, [
        ("This week", this_week(funnel, week, cfg["single_family_cap"], why_unscored)),
        ("To do", to_do(thesis_repo.cards_to_decide(conn), thesis_repo.in_review(conn, week))),
        ("What changed", changed),
        ("Health", [health_, *(["", *actions] if actions else [])]),
    ])  # fmt: skip
    return f"Doomberg weekly — {week_label(week)}", body


def issues_client(settings: Settings, http: HttpClient) -> Issues | None:
    token, repo_name = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if settings.mock_externals:
        return MockIssues()
    if not token or not repo_name:
        return None
    return GitHubIssues(http, repo_name, token)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=date.fromisoformat, default=last_friday(datetime.now(UTC).date()))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    http = HttpClient(settings)
    api = issues_client(settings, http)
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "digest") as tracked:
        actions = minutes.digest_lines(settings, http, download_pending=price_history.pending_tickers(conn),
                                       tickers_per_run=int(lab_config()["prices"]["max_credits"]))  # fmt: skip
        title, body = build(conn, a.week, os.environ.get("APP_URL", ""), why_unscored=unscored_why(os.environ),
                            actions=actions)  # fmt: skip
        number = publish(api, title, body) if api is not None else None
        thesis_repo.upsert_digest(conn, a.week, title, body, number)
        tracked.update({"week": a.week.isoformat(), "issue": number})
    print(f"{title}: {'issue #' + str(number) if number is not None else 'stored (no GitHub token)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
