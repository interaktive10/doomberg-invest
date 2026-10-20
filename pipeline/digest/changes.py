"""What changed this week (overhaul PR 5; BRIEF §4.12): the digest's "## What changed" lines, which the web Home shows
from the same digests.body_md. A pure function (`lines`) over stored weekly rows; `gather` reads them.

Two kinds of line, at most MAX_LINES in all, each '- [TICKER](APP_URL/company/<id>) <text>':
1. One line per company in a bucket (Candidate, Early, Priced-in) this week or in the previous scored week, or with a
   live thesis or research entry: its biggest change and the reason, e.g. "left Candidate: S4 stopped, Evidence
   62 → 48" or "now priced in (Gap 48)". The week's shortlist comes first, in rank order. Then a bucket change, then an
   Evidence move of EVIDENCE_MOVE or more (exactly 10 counts, as for a dismissal's hold), then a signal or red flag
   that started or stopped; the bigger Evidence move first within each. A week without scores has no such lines.
2. The scope's new verified facts of the week (stored in the 7 days to the week's cutoff, from a document published
   before it: the pipeline.db.pit rule; a fact read late still comes once), newest document first, with their diff
   (Appendix F.6): raised, lowered, widened, narrowed, changed or new; a reaffirmed one is left out.

No LLM, and no price moves: Gap is named only as a level ("now priced in (Gap 48)"), never a return or a gain. The rows
read here are scores, signal_values, redflag_values, shortlists, facts, documents and diffs, and the ids of companies
with a live thesis; nothing a thesis's owner wrote is read, so nothing private can reach the digest's GitHub issue.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import facts_repo, repo, thesis_repo
from pipeline.db.models import Company
from pipeline.db.pit import cutoff_for

BUCKETS = ("candidate", "early", "priced_in")
LABEL = {"candidate": "Candidate", "early": "Early", "priced_in": "Priced-in", "excluded": "Excluded", "none": "none"}
EVIDENCE_MOVE = Decimal(10)
MAX_LINES = 20
NOTHING = "Nothing changed this week."
UNSCORED = "No scores this week, so no score changes."
SUBJECT_CHARS = 80

# the order of a company's biggest change
BUCKET, EVIDENCE, OTHER = 1, 2, 3


@dataclass(frozen=True)
class WeekRow:
    """One company's stored rows of one scored week: its scores row, fired signals and fired red flags."""

    evidence: Decimal
    gap: Decimal | None
    bucket: str
    families: tuple[str, ...] = ()
    fired: frozenset[str] = frozenset()
    hard_flags: frozenset[str] = frozenset()
    soft_flags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Name:
    """A company in scope: its rows this week (`now`) and in the previous scored week (`before`)."""

    company_id: UUID
    code: str
    now: WeekRow | None
    before: WeekRow | None
    rank: int | None = None  # its place in this week's shortlist


@dataclass(frozen=True)
class FactNews:
    """A verified fact of the week with its diff (None: no diff row)."""

    company_id: UUID
    code: str
    fact_type: str
    subject: str
    change_kind: str | None
    note: str | None
    published_at: datetime


@dataclass(frozen=True)
class Change:
    order: int  # BUCKET, EVIDENCE or OTHER
    size: Decimal  # the Evidence move, either way
    text: str


def num(x: Decimal | None) -> str:
    """62.5 -> "62.5", 48.0 -> "48" (one decimal at most)."""
    if x is None:
        return "n/a"
    s = f"{Decimal(str(x)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):f}"
    return s[:-2] if s.endswith(".0") else s


def _ids(ids: Iterable[str]) -> str:
    return ", ".join(sorted(ids, key=lambda s: (len(s), s)))  # S2 before S10


def _gap(r: WeekRow) -> str:
    return "Gap not known this week" if r.gap is None else f"Gap {num(r.gap)}"


def reasons(now: WeekRow, before: WeekRow) -> list[str]:
    """What differs between the two weeks' rows: signals and flags that started or stopped, then Evidence."""
    out = []
    if started := now.fired - before.fired:
        out.append(f"{_ids(started)} fired")
    if stopped := before.fired - now.fired:
        out.append(f"{_ids(stopped)} stopped")
    if hard := now.hard_flags - before.hard_flags:
        out.append(f"{_ids(hard)} hard flag")
    if soft := now.soft_flags - before.soft_flags:
        out.append(f"{_ids(soft)} soft flag")
    if cleared := (before.hard_flags | before.soft_flags) - (now.hard_flags | now.soft_flags):
        out.append(f"{_ids(cleared)} cleared")
    if num(now.evidence) != num(before.evidence):
        out.append(f"Evidence {num(before.evidence)} → {num(now.evidence)}")
    return out


def _bucket_change(now: WeekRow, before: WeekRow) -> str:
    a, b = now.bucket, before.bucket
    why = ", ".join(reasons(now, before))
    if a == "priced_in":
        if b in BUCKETS:
            return f"now priced in ({_gap(now)})"
        return f"entered Priced-in ({_gap(now)})" + (f": {why}" if why else "")
    detail = why or _gap(now)
    if b in BUCKETS and a in BUCKETS:
        return f"moved from {LABEL[b]} to {LABEL[a]}: {detail}"
    if b in BUCKETS:
        return f"left {LABEL[b]}: {detail}"
    if a in BUCKETS:
        return f"entered {LABEL[a]}: {detail}"
    return f"now Excluded: {detail}" if a == "excluded" else f"no longer Excluded: {detail}"


def change(n: Name) -> Change | None:
    """The company's biggest change this week, or None when nothing that counts changed."""
    now, before = n.now, n.before
    if now is None:
        if before is not None and before.bucket in BUCKETS:
            return Change(BUCKET, Decimal(0), f"left {LABEL[before.bucket]}: not scored this week")
        return None
    if before is None:
        if now.bucket in BUCKETS:
            return Change(BUCKET, Decimal(0), f"entered {LABEL[now.bucket]}: Evidence {num(now.evidence)}")
        return None
    size = abs(now.evidence - before.evidence)
    if now.bucket != before.bucket:
        return Change(BUCKET, size, _bucket_change(now, before))
    why = reasons(now, before)
    if size >= EVIDENCE_MOVE:
        move = f"Evidence {num(before.evidence)} → {num(now.evidence)}"
        rest = [w for w in why if not w.startswith("Evidence ")]
        return Change(EVIDENCE, size, move + (f": {', '.join(rest)}" if rest else ""))
    if any(not w.startswith("Evidence ") for w in why):
        return Change(OTHER, size, ", ".join(why))
    return None


def shortlisted(n: Name) -> str:
    r = n.now
    if r is None:
        return f"new candidate (#{n.rank})"
    fired = f"{_ids(r.fired)} fired" if r.fired else "no signal fired"
    families = f" ({', '.join(r.families)})" if r.families else ""
    return f"new candidate (#{n.rank}): {fired}{families}, Evidence {num(r.evidence)}, {_gap(r)}"


def fact_text(f: FactNews) -> str | None:
    """None for a reaffirmed fact (the same value restated is no news)."""
    kind = (f.fact_type or "fact").replace("_", " ")
    if f.change_kind == "reaffirmed":
        return None
    if f.change_kind in (None, "new"):
        subject = " ".join(f.subject.split())
        subject = subject if len(subject) <= SUBJECT_CHARS else subject[: SUBJECT_CHARS - 1].rstrip() + "…"
        value = (f.note or "").removeprefix("new: ").strip()
        return f"new verified {kind}: {subject}" + (f" ({value})" if value and value != "–" else "")
    return f"{kind} {f.change_kind}: {f.note or 'changed'}"


def link(code: str, company_id: UUID, app_url: str) -> str:
    return f"- [{code}]({app_url.rstrip('/')}/company/{company_id})"


def lines(names: Sequence[Name], facts: Sequence[FactNews], app_url: str = "", limit: int = MAX_LINES) -> list[str]:
    """The What changed lines: shortlist, then each company's biggest change, then the week's facts."""
    out = [f"{link(n.code, n.company_id, app_url)} {shortlisted(n)}"
           for n in sorted((n for n in names if n.rank is not None), key=lambda n: (n.rank or 0))]  # fmt: skip
    changed = []
    for n in names:
        if n.rank is None and (c := change(n)) is not None:
            changed.append((c.order, -c.size, n.code, f"{link(n.code, n.company_id, app_url)} {c.text}"))
    out += [line for *_, line in sorted(changed)]
    news = sorted(facts, key=lambda f: (-f.published_at.timestamp(), f.code, f.fact_type, f.subject))
    out += [f"{link(f.code, f.company_id, app_url)} {t}" for f in news if (t := fact_text(f)) is not None]
    return out[:limit]


# ---------------------------------------------------------------- reading the rows


def code(c: Company) -> str:
    return (c.ticker if c.market == "us" else c.nse_symbol) or c.name


def week_rows(scores: Sequence[Mapping[str, Any]], fired: Sequence[Mapping[str, Any]],
              flags: Sequence[Mapping[str, Any]]) -> dict[tuple[UUID, date], WeekRow]:  # fmt: skip
    """(company, week) -> WeekRow from thesis_repo's scores, fired-signal and fired-flag rows."""
    sigs: dict[tuple[UUID, date], set[str]] = {}
    for s in fired:
        sigs.setdefault((s["company_id"], s["week_end"]), set()).add(str(s["signal_id"]))
    hard: dict[tuple[UUID, date], set[str]] = {}
    soft: dict[tuple[UUID, date], set[str]] = {}
    for f in flags:
        (hard if f["hard"] else soft).setdefault((f["company_id"], f["week_end"]), set()).add(str(f["flag_id"]))
    out = {}
    for r in scores:
        k = (r["company_id"], r["week_end"])
        out[k] = WeekRow(Decimal(str(r["evidence"])), None if r["gap"] is None else Decimal(str(r["gap"])),
                         str(r["bucket"]), tuple(r["families"] or ()), frozenset(sigs.get(k, ())),
                         frozenset(hard.get(k, ())), frozenset(soft.get(k, ())))  # fmt: skip
    return out


def gather(conn: psycopg.Connection[Any], week: date, companies: Mapping[UUID, Company]
           ) -> tuple[list[Name], list[FactNews]]:  # fmt: skip
    """The scope's rows of `week` and of the previous scored week, and the verified facts stored in the week. Without
    scores this week, no company lines (everyone would read as not scored); the facts still come."""
    scored = thesis_repo.scored(conn, week) > 0
    prev = thesis_repo.previous_scored_week(conn, week)
    weeks = [week] + ([prev] if prev is not None else [])
    ranks = {r["company_id"]: int(r["rank"]) for r in thesis_repo.shortlist(conn, week)}
    scope = thesis_repo.bucket_company_ids(conn, weeks, BUCKETS) | repo.research_company_ids(conn) | set(ranks)
    scope = {cid for cid in scope if cid in companies}
    ids = sorted(scope, key=str)
    names: list[Name] = []
    if scored and ids:
        rows = week_rows(thesis_repo.scores_of(conn, ids, weeks), thesis_repo.fired_signals_of(conn, ids, weeks),
                         thesis_repo.fired_flags_of(conn, ids, weeks))  # fmt: skip
        names = [Name(cid, code(companies[cid]), rows.get((cid, week)),
                      rows.get((cid, prev)) if prev is not None else None, ranks.get(cid)) for cid in ids]  # fmt: skip
    since, until = cutoff_for(week - timedelta(days=7)), cutoff_for(week)
    facts = [FactNews(r["company_id"], code(companies[r["company_id"]]), str(r["fact_type"]), str(r["subject"]),
                      r["change_kind"], r["computed_note"], r["published_at"])
             for r in facts_repo.week_facts(conn, ids, since, until)] if ids else []  # fmt: skip
    return names, facts
