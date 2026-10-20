"""The weekly digest (BRIEF §4.12): a GitHub issue "Doomberg weekly — {week}" (the web Home screen shows the same
markdown, from the `digests` table).

Under the title, a banner lists every source that is stale or past its §2.7 SLA (config/staleness.yaml; M6 review
R1-F12). Sections: new candidates (at most 10, one line each: families fired, Evidence, Gap, link; when the week has
no scores, it says the candidates are missing); theses needing attention (kill criteria triggered this week, reviews
due); the Capex brief; source health and staleness; LLM quota use; Lab notes when a run happened this week. No
price-move content: no gainers, losers or returns.

`python -m pipeline.digest.weekly [--week D]` (weekly.yml `publish` job: every week, whatever the other jobs did).
The issue is published with GITHUB_TOKEN / GITHUB_REPOSITORY from Actions; without them (or with MOCK_EXTERNALS=true)
it is only stored.
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
import yaml

from pipeline.db import repo, thesis_repo
from pipeline.db.models import Company, SourceHealth
from pipeline.digest.github_issue import GitHubIssues, Issues, MockIssues, publish
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


def _fmt(x: Decimal | float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{Decimal(str(x)):.{digits}f}"


def _code(c: Company) -> str:
    code = c.ticker if c.market == "us" else c.nse_symbol
    return f"{code}, {c.market.upper()}" if code else c.market.upper()


def _link(c: Company, app_url: str) -> str:
    return f" · [company page]({app_url.rstrip('/')}/company/{c.id})" if app_url else ""


def candidates(conn: psycopg.Connection[Any], week: date, companies: Mapping[Any, Company], app_url: str) -> list[str]:
    if not thesis_repo.scored(conn, week):
        return [f"**Candidates are missing this week:** no scores were written for {week:%Y-%m-%d} (the scoring run "
                "didn't finish; see source health below)."]  # fmt: skip
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
    """§2.7: every source that is stale, or past its SLA, named under the title (a fallback only when its primary
    isn't fine)."""
    items = []
    for h in rows:
        if resting(h, rows, now, sla, fallback_of or {}):
            continue
        if h.stale:
            items.append(f"{h.source} (stale)")
        elif late(h, now, sla) and h.last_success is not None:
            items.append(f"{h.source} (no success for {(now - h.last_success).days} days; SLA {sla[h.source]})")
    return [f"**Stale data:** {', '.join(items)}. Signals and scores that read these sources may be out of date.",
            ""] if items else []  # fmt: skip


def health(rows: Sequence[SourceHealth], now: datetime, sla: Mapping[str, int] | None = None,
           fallback_of: Mapping[str, str] | None = None) -> list[str]:  # fmt: skip
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
    sources, sla, fb = repo.source_health(conn), sla_days(), fallbacks()
    parts: list[tuple[str, list[str]]] = [
        ("New candidates", candidates(conn, week, companies, app_url)),
        ("Theses needing attention", attention(conn, week)),
        ("Capex brief", capex(conn, week)),
        ("Source health", health(sources, now, sla, fb)),
        ("LLM quota use", llm(thesis_repo.llm_use(conn, since, until))),
    ]
    notes = lab(thesis_repo.lab_runs(conn, since, until))
    if notes:
        parts.append(("Lab notes", notes))
    lines = [
        f"Week ending {week:%Y-%m-%d}. Research only: no orders, no price alerts.",
        "",
        *banner(sources, now, sla, fb),
    ]
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
