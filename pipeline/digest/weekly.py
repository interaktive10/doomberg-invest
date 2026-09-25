"""The weekly digest (BRIEF §4.12): a GitHub issue "Doomberg weekly — {week}" (the web Home screen shows the same
markdown, from the `digests` table).

Sections: new candidates (at most 10, one line each: families fired, Evidence, Gap, link); theses needing attention
(kill criteria triggered this week, reviews due); the Capex brief; source health and staleness; LLM quota use; Lab
notes when a run happened this week. No price-move content: no gainers, losers or returns.

`python -m pipeline.digest.weekly [--week D]` (weekly.yml `thesis` job, after the queue). The issue is published
with GITHUB_TOKEN / GITHUB_REPOSITORY from Actions; without them (or with MOCK_EXTERNALS=true) it is only stored.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.db import repo, thesis_repo
from pipeline.db.models import Company, SourceHealth
from pipeline.digest.github_issue import GitHubIssues, Issues, MockIssues, publish
from pipeline.net.http import HttpClient
from pipeline.settings import Settings
from pipeline.signals.weekly import last_friday
from pipeline.thesis.evidence_pack import week_label

STALE_AFTER_DAYS = {"sec": 3, "nse": 3, "stooq": 8, "llm": 3}  # a source not refreshed this long reads as late


def _fmt(x: Decimal | float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{Decimal(str(x)):.{digits}f}"


def _code(c: Company) -> str:
    code = c.ticker if c.market == "us" else c.nse_symbol
    return f"{code}, {c.market.upper()}" if code else c.market.upper()


def _link(c: Company, app_url: str) -> str:
    return f" · [company page]({app_url.rstrip('/')}/company/{c.id})" if app_url else ""


def candidates(conn: psycopg.Connection[Any], week: date, companies: Mapping[Any, Company], app_url: str) -> list[str]:
    out = []
    for r in thesis_repo.shortlist(conn, week)[:10]:
        c = companies.get(r["company_id"])
        if c is None:
            continue
        score = thesis_repo.week_score(conn, r["company_id"], week)
        families = ", ".join(sorted(score.families)) if score is not None and score.families else "none"
        out.append(f"{r['rank']}. **{c.name}** ({_code(c)}): families {families} · Evidence {_fmt(r['evidence'])} "
                   f"· Gap {_fmt(r['gap'])}{_link(c, app_url)}")  # fmt: skip
    return out or ["No new candidates this week."]


def attention(conn: psycopg.Connection[Any], week: date) -> list[str]:
    out = []
    for t in thesis_repo.triggered_in_week(conn, week):
        cond = t["operator"] if t["threshold"] is None else f"{t['operator']} {t['threshold']}"
        out.append(f"- **{t['name']}**: kill criterion `{t['metric']}` {cond} met (now {_fmt(t['last_value'], 4)}); "
                   "moved to review")  # fmt: skip
    triggered = {t["thesis_id"] for t in thesis_repo.triggered_in_week(conn, week)}
    for t in thesis_repo.reviews_due(conn, week):
        if t["thesis_id"] in triggered:
            continue
        why = "in review" if t["state"] == "review" else f"review due {t['next_review']}"
        out.append(f"- **{t['name']}**: {why}")
    return out or ["Nothing needs attention."]


def capex(conn: psycopg.Connection[Any], week: date) -> list[str]:
    body = thesis_repo.capex_brief(conn, week)
    if not body:
        return ["No Capex brief this week."]
    lines = body.strip().splitlines()
    if lines and lines[0].startswith("## "):
        lines = lines[1:]  # the brief's own title; its ### sections stay
    while lines and not lines[0].strip():
        lines = lines[1:]
    return lines or ["No Capex brief this week."]


def health(rows: Sequence[SourceHealth], now: datetime) -> list[str]:
    if not rows:
        return ["No source has reported yet."]
    out = ["| Source | Last success | Status |", "|---|---|---|"]
    for h in rows:
        late = STALE_AFTER_DAYS.get(h.source)
        if h.stale:
            status = "**stale**" + (f": {h.last_error.removeprefix('stale: ')[:120]}" if h.last_error else "")
        elif h.last_error:
            status = f"error: {h.last_error[:120]}"
        elif h.last_success is None:
            status = "never succeeded"
        elif late is not None and now - h.last_success > timedelta(days=late):
            status = f"late (no success for {(now - h.last_success).days} days)"
        else:
            status = "ok"
        when = "never" if h.last_success is None else f"{h.last_success:%Y-%m-%d %H:%M}Z"
        out.append(f"| {h.source} | {when} | {status} |")
    return out


def llm(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return ["No LLM calls this week."]
    out = ["| Provider | Calls | OK | Rate-limited | Tokens in | Tokens out |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['provider']} | {r['calls']} | {r['ok']} | {r['rate_limited']} | {r['tokens_in']} | "
                   f"{r['tokens_out']} |")  # fmt: skip
    return out


def lab(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return []
    runs = sorted({r["run_at"].date() for r in rows})
    by_market = Counter(str(r["market"]) for r in rows)
    markets = ", ".join(f"{m.upper()}: {n}" for m, n in sorted(by_market.items()))
    results = f"{len(rows)} result{'' if len(rows) == 1 else 's'}"
    return [f"The Signal Lab ran on {', '.join(map(str, runs))}: {results} ({markets}). The report and any weight "
            "proposals arrive as pull requests (docs/LAB_REPORT.md)."]  # fmt: skip


def build(conn: psycopg.Connection[Any], week: date, app_url: str = "", now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(UTC)
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    since = datetime.combine(week - timedelta(days=6), time(0), tzinfo=UTC)
    until = datetime.combine(week + timedelta(days=1), time(0), tzinfo=UTC)
    title = f"Doomberg weekly — {week_label(week)}"
    parts: list[tuple[str, list[str]]] = [
        ("New candidates", candidates(conn, week, companies, app_url)),
        ("Theses needing attention", attention(conn, week)),
        ("Capex brief", capex(conn, week)),
        ("Source health", health(repo.source_health(conn), now)),
        ("LLM quota use", llm(thesis_repo.llm_use(conn, since, until))),
    ]
    notes = lab(thesis_repo.lab_runs(conn, since, until))
    if notes:
        parts.append(("Lab notes", notes))
    lines = [f"Week ending {week:%Y-%m-%d}. Research only: no orders, no price alerts.", ""]
    for name, body in parts:
        lines += [f"## {name}", "", *body, ""]
    return title, "\n".join(lines).rstrip() + "\n"


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
    api = issues_client(settings, HttpClient(settings))
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "digest") as tracked:
        title, body = build(conn, a.week, os.environ.get("APP_URL", ""))
        number = publish(api, title, body) if api is not None else None
        thesis_repo.upsert_digest(conn, a.week, title, body, number)
        tracked.update({"week": a.week.isoformat(), "issue": number})
    print(f"{title}: {'issue #' + str(number) if number is not None else 'stored (no GitHub token)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
