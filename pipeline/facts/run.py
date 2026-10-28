"""The daily text-facts run (BRIEF §4.5, §2.6 router; daily.yml, the step after SEC events;
docs/SPEC_ISSUES.md 50). `python -m pipeline.facts.run [--day D]`.

1. Scope, in work order (ORDER): companies with a live thesis or research entry, then the stage names (Evidence >=
   STAGE_MIN_EVIDENCE in their market's latest scored week) with filings still queued or nothing read in
   READ_AGAIN_DAYS: those on a board (Candidate, Watch, Early), then those one verified text fact would make a
   Candidate (Gap >= ONE_FACT_MIN_GAP), the rest, Excluded names last (docs/SPEC_ISSUES.md 58).
2. Queue: queued filings that no company in scope reads are marked `skipped` (a thesis's come back within
   FILING_DAYS). SEC submissions are read only for the US companies new to the scope (or a stage name that became a
   thesis) and those listed in the daily EDGAR indexes the SEC step read since the last run; each queues the filings
   fetch.scope_filings picks (a thesis's of FILING_DAYS; a stage name's latest report and press releases of
   STAGE_DAYS) -> `filings` (new accessions only).
3. India: P-07 triage of the scope companies' announcements of the last TRIAGE_DAYS (point-in-time reader);
   `read_pdf` ones join the document queue.
4. Documents, in work order (by the scope's order, each newest first; a deferred document or an India PDF in its
   company's place, a stage name's only within its STAGE_DAYS and not of a skipped filing): fetch, normalize,
   P-01 per chunk, Verify-1, store facts and diffs (code, F.6). Risk factors aren't read: P-03 isn't called
   (docs/SPEC_ISSUES.md 50).
5. Links: verified facts with a counterparty -> P-02 -> entities and links.
The run stops asking providers when every one is out for the day (the rest stays queued or `deferred`), at the daily
document limit (config/quotas.yaml text_daily_limits) or at the time budget. Private data never enters this module
(llm/privacy.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg

from pipeline.db import facts_repo, repo
from pipeline.db.models import Company, FilingRow, LlmCall
from pipeline.db.pit import as_of
from pipeline.facts import entities
from pipeline.facts.diff import Value, compute
from pipeline.facts.fetch import AGREEMENT_ITEMS, PERIODIC, STAGE_DAYS, exhibit_urls, scope_filings, since, store_raw
from pipeline.facts.process import DocMeta, extract_document, normalize, reporting_currency
from pipeline.facts.types import RELATION
from pipeline.facts.verify1 import Candidate, XbrlLookup
from pipeline.india import triage
from pipeline.llm.quotas import Quotas
from pipeline.llm.router import CallRecord, Deferred, Router
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.settings import Settings
from pipeline.us.daily import CATCH_UP_DAYS, submissions_url
from pipeline.us.events import master_index_url, parse_master_index
from pipeline.us.submissions import parse_submissions

STAGE_MIN_EVIDENCE = Decimal(40)  # config/signals.yaml scores.us_price_candidate_min_evidence: the candidate stage
READ_AGAIN_DAYS = 100  # a stage name read this long ago is read again: its next quarter's report is out by then
TRIAGE_DAYS = 3
DEFAULT_DOCUMENTS_PER_DAY = 40  # used while config/quotas.yaml text_daily_limits.documents_per_day is null
RETRY_DAYS = 14  # a filing whose documents can't be fetched is tried daily this long after it was queued, then
# `failed` (M5 review R2-F4)
TIME_BUDGET_MIN = 15.0  # document starts: about 150 documents at Gemini's 15 a minute (SPEC_ISSUES 29, 50, 58)
LINK_BATCH = 20
RANK = {"thesis": 0, "stage": 1}  # whose filings a company's SEC submissions queue (fetch.scope_filings): a thesis's
# FILING_DAYS or a stage name's STAGE_DAYS, wherever it stands in ORDER; TextStats.checked keeps this rank
ORDER = ("thesis", "board", "one_fact", "stage", "excluded")  # the work order: a lower index is read first
BOARDS = frozenset({"candidate", "watch", "early"})  # the buckets the Candidates screen lists (Priced-in aside)
ONE_FACT_MIN_GAP = Decimal(50)  # config/signals.yaml scores.buckets.candidate.min_gap: one verified S9 fact (0.4,
# 20 Evidence points) lifts a stage name (Evidence >= 40) with this Gap to a Candidate
SKIP_TRIAGE = (
    "trading window",
    "newspaper publication",
    "loss of share certificate",
    "duplicate share certificate",
    "shareholders meeting",
    "record date",
    "book closure",
    "change in registrar",
    "certificate under sebi",
)


@dataclass
class TextStats:
    day: str
    scope: int = 0
    theses: int = 0
    stage: int = 0
    skipped_filings: int = 0  # queued filings no company in scope reads
    reset_filings: int = 0  # skipped filings back in a new thesis's window
    submissions: int = 0  # companies whose SEC submissions were read
    indexed: int = 0  # of the scope's companies, those listed in the daily EDGAR indexes
    queued_filings: int = 0
    documents: int = 0
    extracted: int = 0
    deferred: int = 0
    failed: int = 0
    facts_verified: int = 0
    facts_review: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    diffs: int = 0
    links: int = 0
    triaged: int = 0
    triage_deferred: int = 0
    stopped: str | None = None
    errors: list[str] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)  # CIK -> rank of the US companies in scope whose filings
    # are queued (their submissions read today or earlier): the next run's "new to the scope" is one not in here
    scope_by_order: dict[str, int] = field(default_factory=dict)  # companies in scope by their place in ORDER
    read_by_order: dict[str, int] = field(default_factory=dict)  # documents read (sent to P-01 or found read) by it


# ---------------------------------------------------------------- scope and queue


def _start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def due(last_read: datetime | None, queued: bool, day: date) -> bool:
    """A stage name is read while filings of its are queued, and again once nothing of it was read (a document
    stored) in READ_AGAIN_DAYS."""
    return queued or last_read is None or last_read < _start(day - timedelta(days=READ_AGAIN_DAYS))


def stage_order(s: facts_repo.StageName) -> int:
    """A stage name's place in ORDER (docs/SPEC_ISSUES.md 58): a board's names first (a fact adds to them, or R3's
    material weakness takes one off), then those one verified text fact would make a Candidate, then the rest;
    Excluded names last (a hard flag stays, whatever the text says)."""
    if s.bucket == "excluded":
        return ORDER.index("excluded")
    if s.bucket in BOARDS:
        return ORDER.index("board")
    if s.gap is not None and s.gap >= ONE_FACT_MIN_GAP:
        return ORDER.index("one_fact")
    return ORDER.index("stage")


def scope(conn: psycopg.Connection[Any], day: date, theses: Iterable[UUID]) -> dict[UUID, int]:
    """company -> its place in ORDER: theses and research entries, then the stage names due for reading."""
    ranks = dict.fromkeys(theses, ORDER.index("thesis"))
    for s in facts_repo.stage_names(conn, STAGE_MIN_EVIDENCE):
        if due(s.last_read, s.queued, day):
            ranks.setdefault(s.company_id, stage_order(s))
    return ranks


def to_fetch(scope: Mapping[str, int], checked: Mapping[str, int] | None, indexed: AbstractSet[str]) -> dict[str, int]:
    """CIK -> rank of the companies in scope whose SEC submissions are read today: every one without the last run's
    record; else those new to the scope, a stage name that became a thesis (its longer window), and those the daily
    EDGAR indexes list (a new filing)."""
    if checked is None:
        return dict(scope)
    return {cik: r for cik, r in scope.items() if cik in indexed or cik not in checked or r < checked[cik]}


def indexed_ciks(conn: psycopg.Connection[Any], http: HttpClient, after: datetime, stats: TextStats) -> set[str] | None:
    """CIKs with a 10-K, 10-Q or 8-K in the daily EDGAR indexes the SEC step read in its runs since `after` (the last
    text run); None when one of them couldn't be read, or an SEC step since failed or was cut off (its days are in no
    runs row): every company's submissions are read then."""
    days = facts_repo.sec_days_since(conn, after)
    if days is None:
        stats.errors.append("SEC step failed or cut off since the last text run: every name's submissions read")
        return None
    out: set[str] = set()
    for d in days:
        try:
            text = http.get_bytes(master_index_url(d)).decode("latin-1")
        except httpx.HTTPError as e:
            stats.errors.append(f"daily index {d}: {type(e).__name__}"[:200])
            return None
        out |= {r.cik for r in parse_master_index(text) if r.form.upper() in PERIODIC | {"8-K"}}
    return out


def queue_us(conn: psycopg.Connection[Any], http: HttpClient, companies: Mapping[UUID, Company],
             ranks: Mapping[UUID, int], day: date, stats: TextStats) -> None:  # fmt: skip
    """Queue the filings of the US companies in scope whose submissions to_fetch picks; stats.checked records the
    scope's companies (less those whose submissions couldn't be read: they count as new tomorrow). `ranks` are places
    in ORDER; what counts here is RANK, a thesis's window or a stage name's, so a stage name moving up the order
    isn't fetched again."""
    us = {c.cik: (c, min(ranks[cid], RANK["stage"])) for cid, c in companies.items() if c.market == "us" and c.cik}
    checked: Mapping[str, int] | None = None
    indexed: set[str] = set()
    last = facts_repo.last_checked(conn)
    if last is not None and last[0] >= _start(day - timedelta(days=CATCH_UP_DAYS)):  # older: the SEC step's
        found = indexed_ciks(conn, http, last[0], stats)  # catch-up didn't read every day since (pipeline.us.daily)
        if found is not None:
            checked, indexed = last[1], found
    wanted = to_fetch({cik: r for cik, (_, r) in us.items()}, checked, indexed)
    stats.indexed = len(indexed & set(us))
    rows: list[FilingRow] = []
    for cik, (c, rank) in sorted(us.items(), key=lambda kv: (kv[1][1], kv[0])):
        assert c.id is not None
        if cik not in wanted:
            stats.checked[cik] = min(rank, checked[cik]) if checked is not None and cik in checked else rank
            continue
        try:
            subs = parse_submissions(json.loads(http.get_bytes(submissions_url(cik))))
        except (httpx.HTTPError, ValueError, KeyError) as e:
            stats.errors.append(f"submissions {cik}: {type(e).__name__}"[:200])
            continue
        stats.submissions += 1
        stats.checked[cik] = rank
        refs = scope_filings(subs, day, thesis=rank == RANK["thesis"])
        known = facts_repo.queued_accessions(conn, [r.accession for r in refs])
        rows += [FilingRow(company_id=c.id, accession_no=r.accession, form_type=r.form, items=list(r.items),
                           filed_at=r.accepted_at, accepted_at=r.accepted_at, period_of_report=r.report_date,
                           primary_doc_url=r.primary_doc_url, index_url=r.index_url)
                 for r in refs if r.accession not in known]  # fmt: skip
    repo.insert_filings(conn, rows)
    stats.queued_filings = len(rows)


# ---------------------------------------------------------------- one document


@dataclass(frozen=True)
class DocJob:
    company: Company
    kind: str
    url: str
    title: str
    published_at: datetime
    filing_id: UUID | None = None
    via_nse: bool = False


def xbrl_lookup(conn: psycopg.Connection[Any], company_id: UUID, published: datetime) -> XbrlLookup:
    """V1-XBRL: the fundamentals_q value known when the document was published (a quarter, or 4 quarters)."""
    rows = sorted(as_of(published).fundamentals(conn, [company_id]), key=lambda r: r.period_end)

    def lookup(concept: str, period_end: date, months: int) -> Decimal | None:
        idx = next((i for i, r in enumerate(rows) if abs((r.period_end - period_end).days) <= 7), None)
        if idx is None:
            return None
        take = rows[max(0, idx - 3) : idx + 1] if months == 12 else rows[idx : idx + 1]
        if months == 12 and len(take) < 4:
            return None
        vals = [getattr(r, concept) for r in take]
        return None if any(v is None for v in vals) else sum(vals, Decimal(0))

    return lookup


def _value(c: Candidate) -> Value:
    return Value(c.value_num, c.value_low, c.value_high, c.unit, c.currency)


def store_facts(conn: psycopg.Connection[Any], job: DocJob, doc_id: UUID, facts: Sequence[tuple[Candidate, str]],
                stats: TextStats) -> list[UUID]:  # fmt: skip
    assert job.company.id is not None
    ids = facts_repo.insert_facts(conn, job.company.id, doc_id, facts)
    for (c, _), fid in zip(facts, ids, strict=True):
        if c.verification_status != "verified":
            stats.facts_review += 1
            continue
        stats.facts_verified += 1
        prev = facts_repo.prior_verified(conn, job.company.id, c.subject_key, c.as_of, ids)
        d = compute(None if prev is None else Value(prev.value_num, prev.value_low, prev.value_high, prev.unit,
                                                    prev.currency), _value(c), c.withdrawn)  # fmt: skip
        facts_repo.insert_diff(conn, job.company.id, c.subject_key, None if prev is None else prev.id, fid, d)
        stats.diffs += 1
    return ids


def process(conn: psycopg.Connection[Any], job: DocJob, fetch: Callable[[DocJob], bytes], router: Router,
            raw_root: Path, stats: TextStats) -> str:  # fmt: skip
    """extracted | deferred | retry (the fetch failed: try again another day) | failed (the document is broken)"""
    c = job.company
    assert c.id is not None
    try:
        body = fetch(job)
    except (httpx.HTTPError, NseBlocked) as e:
        stats.errors.append(f"fetch {job.url}: {type(e).__name__}"[:200])
        stats.failed += 1
        return "retry"
    path, digest = store_raw(raw_root, c.cik or c.nse_symbol or str(c.id), "", job.url, body)
    try:
        norm = normalize(job.url, body)
    except Exception as e:  # noqa: BLE001 — a malformed document fails alone
        stats.errors.append(f"normalize {job.url}: {type(e).__name__}"[:200])
        stats.failed += 1
        return "failed"
    doc_id = facts_repo.upsert_document(
        conn, company_id=c.id, filing_id=job.filing_id, kind=job.kind, url=job.url, title=job.title,
        published_at=job.published_at, sha256=digest, raw_path=str(path), text_chars=len(norm.text),
        section_map=norm.section_map, page_map=norm.page_map, status="normalized",
    )  # fmt: skip
    stats.documents += 1
    # Facts stored on an earlier day: a 10-K or 10-Q deferred for its risk diff before P-03 was dropped (SPEC_ISSUES
    # 50) has nothing left to read.
    if not facts_repo.document_has_facts(conn, doc_id):
        meta = DocMeta(c.name, c.ticker or c.nse_symbol or "", c.fiscal_year_end, job.kind, job.title,
                       job.published_at, reporting_currency(c.market))  # fmt: skip
        out = extract_document(meta, norm, router, xbrl_lookup(conn, c.id, job.published_at))
        for k, n in out.rejected.items():
            stats.rejected[k] = stats.rejected.get(k, 0) + n
        if out.status == "deferred":
            facts_repo.set_document_status(conn, doc_id, "deferred")
            stats.deferred += 1
            return "deferred"
        store_facts(conn, job, doc_id, out.facts, stats)
    facts_repo.set_document_status(conn, doc_id, "extracted")
    stats.extracted += 1
    return "extracted"


# ---------------------------------------------------------------- filings -> documents


class IndexUnavailable(Exception):
    """An 8-K's filing index couldn't be fetched: the filing stays `new` and is tried again (M5 review R2-F4)."""


def filing_status(results: list[str], expired: bool) -> str:
    """A filing is `new` (read again tomorrow) while a document is deferred, or one couldn't be fetched and the
    filing is younger than RETRY_DAYS; `failed` when no document could be read; else `extracted`."""
    if "deferred" in results or ("retry" in results and not expired):
        return "new"
    if results and all(r in ("failed", "retry") for r in results):
        return "failed"
    return "extracted"


def filing_jobs(f: Mapping[str, Any], company: Company, http: HttpClient) -> list[DocJob]:
    form, filed = str(f["form_type"]), f["filed_at"]
    if form in {"10-K", "10-Q"}:
        return [DocJob(company, form, f["primary_doc_url"], f"Form {form}", filed, f["id"])]
    jobs = []
    try:
        ex = exhibit_urls(http.get_bytes(f["index_url"]).decode("utf-8", errors="replace"))
    except httpx.HTTPError as e:
        raise IndexUnavailable(f"filing index {f['index_url']}: {type(e).__name__}") from e
    for kind, u in sorted(ex.items()):
        jobs.append(DocJob(company, kind, u, f"8-K {kind}", filed, f["id"]))
    if AGREEMENT_ITEMS & set(f.get("items") or []):
        jobs.append(DocJob(company, "8-K", f["primary_doc_url"], "Form 8-K", filed, f["id"]))
    return jobs


# ---------------------------------------------------------------- India triage (P-07)


def triage_announcements(conn: psycopg.Connection[Any], router: Router, companies: Mapping[UUID, Company],
                         day: date, stats: TextStats) -> list[DocJob]:  # fmt: skip
    """Triage the scope companies' recent announcements (the last TRIAGE_DAYS); returns PDF jobs for read_pdf ones,
    also those triaged on an earlier day whose PDF couldn't be fetched (the caller skips URLs already read)."""
    ids = [cid for cid, c in companies.items() if c.market == "in"]
    if not ids:
        return []
    events = [e for e in as_of(day).corp_events(conn, ids, since=day - timedelta(days=TRIAGE_DAYS + RETRY_DAYS))
              if e.kind == "announcement" and e.id is not None]  # fmt: skip
    recent = day - timedelta(days=TRIAGE_DAYS)
    done = facts_repo.triaged(conn, [e.id for e in events if e.id is not None])
    first = day - timedelta(days=RETRY_DAYS)
    pdf = facts_repo.triaged_pdf(conn, [e.id for e in events if e.id is not None],
                                 datetime(first.year, first.month, first.day, tzinfo=UTC))  # fmt: skip
    jobs = []
    for e in events:
        assert e.id is not None
        title = str(e.detail.get("category") or "")
        if e.id in pdf and e.source_url.lower().endswith(".pdf"):  # triaged in the last RETRY_DAYS: its PDF until read
            jobs.append(DocJob(companies[e.company_id], "press_release", e.source_url, title, e.filed_at, None, True))
            continue  # (the caller drops a URL already read; a failed fetch left none: M5 review R2-F4, R3)
        if e.event_date < recent or e.id in done or any(s in title.lower() for s in SKIP_TRIAGE):
            continue
        if router.exhausted("P-07"):
            stats.triage_deferred += 1
            continue
        answer = router.call(triage.TriageInput(title, str(e.detail.get("text") or "")))
        if isinstance(answer, Deferred):
            stats.triage_deferred += 1
            continue
        t = triage.parse(answer.content)
        if t is None:
            stats.errors.append(f"triage {e.id}: malformed answer")
            continue
        facts_repo.insert_triage(
            conn, e.id, e.company_id, t.categories, t.read_pdf, f"{answer.provider}:{answer.model}"
        )
        stats.triaged += 1
        if t.read_pdf and e.source_url.lower().endswith(".pdf"):
            jobs.append(DocJob(companies[e.company_id], "press_release", e.source_url, title, e.filed_at, None, True))
    return jobs


# ---------------------------------------------------------------- links (P-02)


def link_pending(conn: psycopg.Connection[Any], router: Router, stats: TextStats) -> None:
    facts = facts_repo.unlinked_facts(conn)
    if not facts:
        return
    pool = [entities.Candidate(str(r["id"]), str(r["name"])) for r in facts_repo.entity_pool(conn)]
    ciks = {str(r["id"]): r.get("cik") for r in facts_repo.entity_pool(conn)}
    names = sorted({str(f["counterparty"]) for f in facts})
    resolved: dict[str, UUID] = {}
    for k in range(0, len(names), LINK_BATCH):
        batch = names[k : k + LINK_BATCH]
        offered = {n: entities.candidates_for(n, pool) for n in batch}
        cands = tuple(dict.fromkeys((c.id, c.name) for cs in offered.values() for c in cs))
        answer = router.call(entities.EntityInput(tuple(batch), cands))
        if isinstance(answer, Deferred):
            stats.errors.append("links deferred (P-02)")
            break
        matches = entities.parse(answer.content, batch, {c[0] for c in cands})
        by_id = dict(cands)
        for n in batch:
            m = matches.get(n)
            if m is None:
                continue
            if m.candidate_id is not None:
                name = by_id[m.candidate_id]
                cik = ciks.get(m.candidate_id)
                kind = "company" if m.candidate_id.startswith("c:") else m.kind
                resolved[n] = facts_repo.upsert_entity(conn, name, entities.normalize_name(name), kind, cik)
            else:
                resolved[n] = facts_repo.upsert_entity(conn, n, entities.normalize_name(n), m.kind)
    for f in facts:
        eid = resolved.get(str(f["counterparty"]))
        if eid is not None:
            facts_repo.link_fact(conn, f["id"], f["company_id"], eid, RELATION.get(str(f["fact_type"])))
            stats.links += 1


# ---------------------------------------------------------------- the run


def _llm_log(conn: psycopg.Connection[Any]) -> Callable[[CallRecord], None]:
    def log(r: CallRecord) -> None:
        facts_repo.record_llm_calls(conn, [LlmCall(**asdict(r))])

    return log


Job = tuple[int, datetime, DocJob, UUID | None]  # (place in ORDER, filed or published, the document, its filing)


def work_order(jobs: Iterable[Job]) -> list[Job]:
    """In the scope's ORDER (theses, a board's names, one fact from the board, the rest, Excluded), each place newest
    first (docs/SPEC_ISSUES.md 50, 58)."""
    return sorted(jobs, key=lambda j: (j[0], -j[1].timestamp()))


def _tally(counts: dict[str, int], rank: int, n: int = 1) -> None:
    name = ORDER[rank] if 0 <= rank < len(ORDER) else "other"
    counts[name] = counts.get(name, 0) + n


def run(conn: psycopg.Connection[Any], day: date, router: Router, http: HttpClient, nse: NseClient | None,
        raw_root: Path, documents_per_day: int | None = None, minutes: float | None = None,
        clock: Callable[[], float] = time.monotonic) -> TextStats:  # fmt: skip
    """`minutes`: no document starts after this much time (BRIEF §2.5: the daily run's minutes budget); a document
    is read whole or not at all, so the rest waits for the next day."""
    stats = TextStats(day.isoformat())
    deadline = None if minutes is None else clock() + 60 * minutes
    all_companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    with conn.transaction():
        theses = repo.research_company_ids(conn)
        stats.skipped_filings, stats.reset_filings = facts_repo.skip_stale_filings(
            conn, sorted(theses), _start(since(day, STAGE_DAYS)), _start(since(day))
        )
        ranks = scope(conn, day, sorted(theses))
    in_scope = {cid: all_companies[cid] for cid in ranks if cid in all_companies}
    stats.scope = len(in_scope)
    stats.theses = sum(1 for cid in in_scope if ranks[cid] == RANK["thesis"])
    stats.stage = stats.scope - stats.theses
    for cid in in_scope:
        _tally(stats.scope_by_order, ranks[cid])
    with conn.transaction():
        queue_us(conn, http, in_scope, ranks, day, stats)

    def fetch(job: DocJob) -> bytes:
        if job.via_nse:
            if nse is None:
                raise NseBlocked("NSE client not configured")
            return nse.get(job.url)
        return http.get_bytes(job.url)

    limit = documents_per_day if documents_per_day is not None else DEFAULT_DOCUMENTS_PER_DAY
    with conn.transaction():
        pdf_jobs = triage_announcements(conn, router, in_scope, day, stats)

    jobs: list[Job] = []
    # one query a place in ORDER: the later places' filings never crowd the earlier ones' out of the window
    new_filings = [
        f
        for rank in sorted({ranks[i] for i in in_scope})
        for f in facts_repo.filings_by_status(conn, ["new"], [i for i in in_scope if ranks[i] == rank])
    ]
    queued = {f["id"] for f in new_filings}
    for d in facts_repo.deferred_documents(conn, list(in_scope), theses=sorted(theses),  # a stage name's: 120 days
                                           stage_since=_start(since(day, STAGE_DAYS))):  # fmt: skip
        if d["filing_id"] not in queued:  # else its filing, still new, re-reads it (M5 R1-F2)
            job = DocJob(in_scope[d["company_id"]], d["kind"], d["url"], d["title"] or "", d["published_at"],
                         d["filing_id"], d["url"].startswith("https://nsearchives"))  # fmt: skip
            jobs.append((ranks[d["company_id"]], d["published_at"], job, None))
    for f in new_filings:
        c = in_scope[f["company_id"]]
        jobs.append((ranks[f["company_id"]], f["filed_at"], DocJob(c, str(f["form_type"]), "", "", f["filed_at"],
                                                                   f["id"]), f["id"]))  # fmt: skip
    seen_urls = set(facts_repo.document_status(conn, [j.url for j in pdf_jobs]))
    for j in pdf_jobs:
        if j.url not in seen_urls:
            jobs.append((ranks.get(j.company.id or UUID(int=0), len(ORDER)), j.published_at, j, None))

    done = 0
    for rank, _, job, filing_id in work_order(jobs):
        if done >= limit:
            stats.stopped = f"daily document limit ({limit})"
            break
        if deadline is not None and clock() >= deadline:
            stats.stopped = f"time budget ({minutes:g} min)"
            break
        if router.exhausted("P-01"):
            stats.stopped = "every provider is out for today"
            break
        with conn.transaction():
            if filing_id is not None:
                row = facts_repo.filing(conn, filing_id)
                if row is None:
                    continue
                expired = (day - row["created_at"].date()).days > RETRY_DAYS  # RETRY_DAYS after it was first queued
                try:
                    parts = filing_jobs(row, job.company, http)
                except IndexUnavailable as e:
                    stats.errors.append(str(e)[:200])
                    stats.failed += 1
                    if expired:
                        facts_repo.set_filing_status(conn, filing_id, "failed")
                    continue
                known = facts_repo.document_status(conn, [j.url for j in parts])
                todo = [j for j in parts if known.get(j.url, (None, ""))[1] != "extracted"]  # read once (M5 R1-F2)
                results = [process(conn, j, fetch, router, raw_root, stats) for j in todo]
                results += ["extracted"] * (len(parts) - len(todo))
                done += len(todo)
                _tally(stats.read_by_order, rank, len(todo))
                facts_repo.set_filing_status(conn, filing_id, filing_status(results, expired))
            else:
                process(conn, job, fetch, router, raw_root, stats)
                done += 1
                _tally(stats.read_by_order, rank)
    with conn.transaction():
        link_pending(conn, router, stats)
    stats.errors = stats.errors[:50]
    return stats


def main(argv: list[str] | None = None) -> int:
    from pipeline.llm.clients import providers

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", type=date.fromisoformat, default=datetime.now(UTC).date())
    ap.add_argument("--minutes", type=float, default=TIME_BUDGET_MIN, help="no document starts after this")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    quotas = Quotas.load()
    http = HttpClient(settings)
    nse = NseClient(http)
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "text", source="llm") as tracked:
        router = Router(providers(http, settings, quotas), quotas, log=_llm_log(conn),
                        used_today=facts_repo.llm_usage(conn, a.day))  # fmt: skip
        if not quotas.configured():
            print("text: no provider quota is set in config/quotas.yaml (BRIEF §11.3); nothing to do")
            tracked.update({"skipped": "quotas not set"})
            return 0
        stats = run(conn, a.day, router, http, nse, settings.cache_dir / "raw", quotas.documents_per_day, a.minutes)
        tracked.update(asdict(stats))
    print(f"text {a.day}: scope {stats.scope} (theses {stats.theses}, stage names {stats.stage}), "
          f"{stats.extracted} documents extracted, {stats.deferred} deferred, "
          f"{stats.facts_verified} verified facts, {stats.facts_review} for review, {stats.links} links; "
          f"stopped: {stats.stopped or 'queue empty'}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
