"""The daily text-facts run (BRIEF §4.5, §4.11 ledger, §2.6 router; daily.yml `text` job).
`python -m pipeline.facts.run [--day D]`.

1. Scope, in config/quotas.yaml work order: capex-desk companies, the candidate shortlist (top 100 by Evidence in the
   latest scored week, without text facts yet), companies with a live thesis.
2. Queue: for each US company in scope, its 10-K, 10-Q and 8-K (items 1.01, 2.02, 2.03, 7.01, 8.01) filings of the
   last FILING_DAYS -> `filings` (new accessions only).
3. India: P-07 triage of the scope companies' announcements of the last TRIAGE_DAYS (point-in-time reader);
   `read_pdf` ones join the document queue.
4. Documents, in work order (deferred ones first, then new filings, then India PDFs): fetch, normalize, P-01 per
   chunk, Verify-1, store facts, diffs (code, F.6) and, for 10-K/10-Q, the risk-factor diff with P-03 tags.
5. Links: verified facts with a counterparty -> P-02 -> entities and links.
The run stops asking providers when every one is out for the day (the rest stays queued or `deferred`) or at the
daily document limit (config/quotas.yaml text_daily_limits). Journal data never enters this module (llm/privacy.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
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
from pipeline.facts import entities, risk_diff
from pipeline.facts.diff import Value, compute
from pipeline.facts.fetch import AGREEMENT_ITEMS, exhibit_urls, since, store_raw, text_filings
from pipeline.facts.html_text import Normalized
from pipeline.facts.process import DocMeta, extract_document, normalize
from pipeline.facts.types import RELATION
from pipeline.facts.verify1 import Candidate, XbrlLookup
from pipeline.india import triage
from pipeline.llm.quotas import Quotas
from pipeline.llm.router import CallRecord, Deferred, Router
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.settings import Settings
from pipeline.us.daily import submissions_url
from pipeline.us.submissions import parse_submissions

SHORTLIST = 100
TRIAGE_DAYS = 3
DEFAULT_DOCUMENTS_PER_DAY = 40  # used while config/quotas.yaml text_daily_limits.documents_per_day is null
LINK_BATCH = 20
RANK = {"capex_desk": 0, "candidate_shortlist": 1, "other": 2}
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
    queued_filings: int = 0
    documents: int = 0
    extracted: int = 0
    deferred: int = 0
    failed: int = 0
    facts_verified: int = 0
    facts_review: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    diffs: int = 0
    risk_changes: int = 0
    links: int = 0
    triaged: int = 0
    triage_deferred: int = 0
    stopped: str | None = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- scope and queue


def scope(conn: psycopg.Connection[Any], companies: Sequence[Company]) -> dict[UUID, int]:
    """company -> work rank (0 capex desk, 1 shortlist, 2 thesis)."""
    ranks: dict[UUID, int] = {}
    for c in companies:
        if c.capex_desk and c.id is not None:
            ranks[c.id] = RANK["capex_desk"]
    week = facts_repo.latest_scored_week(conn)
    if week is not None:
        for cid in facts_repo.text_shortlist(conn, week, SHORTLIST):
            ranks.setdefault(cid, RANK["candidate_shortlist"])
    for cid in repo.research_company_ids(conn):
        ranks.setdefault(cid, RANK["other"])
    return ranks


def queue_us(conn: psycopg.Connection[Any], http: HttpClient, companies: Iterable[Company], today: date,
             stats: TextStats) -> None:  # fmt: skip
    rows: list[FilingRow] = []
    for c in companies:
        if c.market != "us" or not c.cik or c.id is None:
            continue
        try:
            subs = parse_submissions(json.loads(http.get_bytes(submissions_url(c.cik))))
        except (httpx.HTTPError, ValueError, KeyError) as e:
            stats.errors.append(f"submissions {c.cik}: {type(e).__name__}"[:200])
            continue
        refs = text_filings(subs, since(today))
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
    return Value(c.value_num, c.value_low, c.value_high, c.unit)


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
        d = compute(None if prev is None else Value(prev.value_num, prev.value_low, prev.value_high, prev.unit),
                    _value(c), c.withdrawn)  # fmt: skip
        facts_repo.insert_diff(conn, job.company.id, c.subject_key, None if prev is None else prev.id, fid, d)
        stats.diffs += 1
    return ids


def risk_changes(conn: psycopg.Connection[Any], job: DocJob, doc_id: UUID, norm: Normalized,
                 fetch: Callable[[DocJob], bytes], router: Router, stats: TextStats) -> None:  # fmt: skip
    """Item 1A against the same company's previous document of the same form (Appendix F.6)."""
    assert job.company.id is not None
    new_rf = next((s for s in norm.section_map if s["name"] == "risk_factors"), None)
    prev = facts_repo.previous_document(conn, job.company.id, job.kind, job.published_at)
    if new_rf is None or prev is None:
        return
    try:
        old = normalize(prev["url"], fetch(DocJob(job.company, job.kind, prev["url"], "", prev["published_at"])))
    except (httpx.HTTPError, NseBlocked, ValueError) as e:
        stats.errors.append(f"risk diff {prev['url']}: {type(e).__name__}"[:200])
        return
    old_rf = next((s for s in old.section_map if s["name"] == "risk_factors"), None)
    if old_rf is None:
        return
    new_p = risk_diff.paragraphs(norm.text, int(str(new_rf["char_start"])), int(str(new_rf["char_end"])))
    old_p = risk_diff.paragraphs(old.text, int(str(old_rf["char_start"])), int(str(old_rf["char_end"])))
    if min(len(new_p), len(old_p)) < risk_diff.MIN_PARAGRAPHS:
        return
    changes = risk_diff.compare(old_p, new_p)
    if not changes:
        return
    items = tuple((f"p{k}", para.text[:2000]) for k, c in enumerate(changes) if (para := c.new or c.old) is not None)
    answer = router.call(risk_diff.RiskTagInput(items))
    if isinstance(answer, Deferred):
        stats.errors.append(f"risk tags deferred for {job.url}")
        return
    tags = risk_diff.parse_tags(answer.content, [i for i, _ in items])
    rows = []
    for k, c in enumerate(changes):
        t = tags.get(f"p{k}", [])
        if not t:
            continue
        text, start, end = risk_diff.quote(c)
        rows.append(
            {
                "company_id": job.company.id,
                "from_document_id": prev["id"],
                "to_document_id": doc_id,
                "change_kind": c.kind,
                "text_before": text if c.kind == "removed" else None,
                "text_after": None if c.kind == "removed" else text,
                "similarity": None if c.similarity is None else Decimal(str(c.similarity)).quantize(Decimal("0.001")),
                "topic_tags": t,
                "char_start": start,
                "char_end": end,
            }
        )
    facts_repo.insert_risk_changes(conn, rows)
    stats.risk_changes += len(rows)


def process(conn: psycopg.Connection[Any], job: DocJob, fetch: Callable[[DocJob], bytes], router: Router,
            raw_root: Path, stats: TextStats) -> str:  # fmt: skip
    """extracted | deferred | failed"""
    c = job.company
    assert c.id is not None
    try:
        body = fetch(job)
    except (httpx.HTTPError, NseBlocked) as e:
        stats.errors.append(f"fetch {job.url}: {type(e).__name__}"[:200])
        stats.failed += 1
        return "failed"
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
    meta = DocMeta(c.name, c.ticker or c.nse_symbol or "", c.fiscal_year_end, job.kind, job.title, job.published_at)
    out = extract_document(meta, norm, router, xbrl_lookup(conn, c.id, job.published_at))
    stats.documents += 1
    for k, n in out.rejected.items():
        stats.rejected[k] = stats.rejected.get(k, 0) + n
    if out.status == "deferred":
        facts_repo.set_document_status(conn, doc_id, "deferred")
        stats.deferred += 1
        return "deferred"
    store_facts(conn, job, doc_id, out.facts, stats)
    if job.kind in {"10-K", "10-Q"}:
        risk_changes(conn, job, doc_id, norm, fetch, router, stats)
    facts_repo.set_document_status(conn, doc_id, "extracted")
    stats.extracted += 1
    return "extracted"


# ---------------------------------------------------------------- filings -> documents


def filing_jobs(f: Mapping[str, Any], company: Company, http: HttpClient) -> list[DocJob]:
    form, filed = str(f["form_type"]), f["filed_at"]
    if form in {"10-K", "10-Q"}:
        return [DocJob(company, form, f["primary_doc_url"], f"Form {form}", filed, f["id"])]
    jobs = []
    try:
        ex = exhibit_urls(http.get_bytes(f["index_url"]).decode("utf-8", errors="replace"))
    except httpx.HTTPError:
        ex = {}
    for kind, u in sorted(ex.items()):
        jobs.append(DocJob(company, kind, u, f"8-K {kind}", filed, f["id"]))
    if AGREEMENT_ITEMS & set(f.get("items") or []):
        jobs.append(DocJob(company, "8-K", f["primary_doc_url"], "Form 8-K", filed, f["id"]))
    return jobs


# ---------------------------------------------------------------- India triage (P-07)


def triage_announcements(conn: psycopg.Connection[Any], router: Router, companies: Mapping[UUID, Company],
                         day: date, stats: TextStats) -> list[DocJob]:  # fmt: skip
    """Triage the scope companies' recent announcements; returns PDF jobs for read_pdf ones not read yet."""
    ids = [cid for cid, c in companies.items() if c.market == "in"]
    if not ids:
        return []
    events = [e for e in as_of(day).corp_events(conn, ids, since=day - timedelta(days=TRIAGE_DAYS))
              if e.kind == "announcement" and e.id is not None]  # fmt: skip
    done = facts_repo.triaged(conn, [e.id for e in events if e.id is not None])
    jobs = []
    for e in events:
        assert e.id is not None
        title = str(e.detail.get("category") or "")
        if e.id in done or any(s in title.lower() for s in SKIP_TRIAGE):
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


def run(conn: psycopg.Connection[Any], day: date, router: Router, http: HttpClient, nse: NseClient | None,
        raw_root: Path, documents_per_day: int | None = None) -> TextStats:  # fmt: skip
    stats = TextStats(day.isoformat())
    all_companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    ranks = scope(conn, list(all_companies.values()))
    stats.scope = len(ranks)
    in_scope = {cid: all_companies[cid] for cid in ranks if cid in all_companies}
    with conn.transaction():
        queue_us(conn, http, sorted(in_scope.values(), key=lambda c: (ranks[c.id or UUID(int=0)], c.name)), day, stats)

    def fetch(job: DocJob) -> bytes:
        if job.via_nse:
            if nse is None:
                raise NseBlocked("NSE client not configured")
            return nse.get(job.url)
        return http.get_bytes(job.url)

    limit = documents_per_day if documents_per_day is not None else DEFAULT_DOCUMENTS_PER_DAY
    with conn.transaction():
        pdf_jobs = triage_announcements(conn, router, in_scope, day, stats)

    jobs: list[tuple[int, datetime, DocJob, UUID | None]] = []
    for d in facts_repo.deferred_documents(conn):
        c = all_companies.get(d["company_id"])
        if c is not None:
            jobs.append(
                (
                    -1,
                    d["published_at"],
                    DocJob(
                        c,
                        d["kind"],
                        d["url"],
                        d["title"] or "",
                        d["published_at"],
                        d["filing_id"],
                        d["url"].startswith("https://nsearchives"),
                    ),
                    None,
                )
            )
    for f in facts_repo.filings_by_status(conn, ["new"]):
        c = in_scope.get(f["company_id"])
        if c is not None:
            jobs.append((ranks[f["company_id"]], f["filed_at"], DocJob(c, str(f["form_type"]), "", "", f["filed_at"],
                                                                       f["id"]), f["id"]))  # fmt: skip
    seen_urls = set(facts_repo.document_status(conn, [j.url for j in pdf_jobs]))
    for j in pdf_jobs:
        if j.url not in seen_urls:
            jobs.append((ranks.get(j.company.id or UUID(int=0), 2), j.published_at, j, None))
    jobs.sort(key=lambda x: (x[0], x[1]))

    done = 0
    for _, _, job, filing_id in jobs:
        if done >= limit:
            stats.stopped = f"daily document limit ({limit})"
            break
        if router.exhausted("P-01"):
            stats.stopped = "every provider is out for today"
            break
        with conn.transaction():
            if filing_id is not None:
                f = next(x for x in facts_repo.filings_by_status(conn, ["new"]) if x["id"] == filing_id)
                results = [process(conn, j, fetch, router, raw_root, stats) for j in filing_jobs(f, job.company, http)]
                done += len(results)
                status = ("failed" if results and all(r == "failed" for r in results) else
                          "new" if "deferred" in results else "extracted")  # fmt: skip
                if status != "new":
                    facts_repo.set_filing_status(conn, filing_id, status)
            else:
                process(conn, job, fetch, router, raw_root, stats)
                done += 1
    with conn.transaction():
        link_pending(conn, router, stats)
    stats.errors = stats.errors[:50]
    return stats


def main(argv: list[str] | None = None) -> int:
    from pipeline.llm.clients import providers

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", type=date.fromisoformat, default=datetime.now(UTC).date())
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
        stats = run(conn, a.day, router, http, nse, settings.cache_dir / "raw", quotas.documents_per_day)
        tracked.update(asdict(stats))
    print(f"text {a.day}: {stats.extracted} documents extracted, {stats.deferred} deferred, "
          f"{stats.facts_verified} verified facts, {stats.facts_review} for review, {stats.links} links; "
          f"stopped: {stats.stopped or 'queue empty'}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
