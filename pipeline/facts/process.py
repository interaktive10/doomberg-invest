"""One document through the text-facts engine (BRIEF §4.5, Appendix F.3-F.5):
normalize -> chunk selection -> keyword prefilter -> P-01 per chunk (router) -> parse -> Verify-1.

All or nothing per document: when the router defers (every provider is out), no fact of the document is kept and
the whole document is retried the next day, so a document is never half-read.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.facts import extract
from pipeline.facts.chunk import prefilter, select
from pipeline.facts.html_text import Normalized, normalize_html, normalize_plain
from pipeline.facts.pdf_text import normalize_pdf
from pipeline.facts.verify1 import Candidate, DocContext, Rejected, XbrlLookup, verify
from pipeline.llm.router import Deferred, Router


@dataclass(frozen=True)
class DocMeta:
    company_name: str
    ticker: str
    fye: str | None
    kind: str  # documents.kind
    title: str
    published_at: datetime


@dataclass
class Outcome:
    status: str  # extracted | deferred
    facts: list[tuple[Candidate, str]] = field(default_factory=list)  # (candidate, "provider:model")
    rejected: Counter[str] = field(default_factory=Counter)  # Verify-1 failures by check
    parse_rejects: int = 0
    duplicates: int = 0
    chunks: int = 0
    sent: int = 0
    reason: str | None = None


def normalize(url: str, body: bytes, content_type: str = "") -> Normalized:
    """HTML (EDGAR, press releases), PDF (presentations, India announcements) or plain text."""
    head = body[:1024].lstrip().lower()
    if body[:5] == b"%PDF-" or "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        return normalize_pdf(body)
    text = body.decode("utf-8", errors="replace") if not head.startswith(b"<") else _decode_html(body)
    if head.startswith(b"<") or url.lower().endswith((".htm", ".html", ".xhtml")):
        return normalize_html(text)
    return normalize_plain(text)


def _decode_html(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("latin-1")


def extract_document(meta: DocMeta, norm: Normalized, router: Router, xbrl: XbrlLookup | None = None) -> Outcome:
    chunks = select(meta.kind, norm.text, norm.section_map, norm.page_map)
    kept = prefilter(chunks)
    out = Outcome("extracted", chunks=len(chunks))
    ctx = DocContext(meta.kind, meta.published_at.date(), meta.fye, norm.text)
    seen: set[tuple[object, ...]] = set()
    for ch in kept:
        inp = extract.ExtractInput(
            name=meta.company_name, ticker=meta.ticker, fye=meta.fye or "", kind=meta.kind, title=meta.title,
            published_at=meta.published_at.date().isoformat(), section=ch.section or "whole document",
            char_start=ch.char_start, char_end=ch.char_end, text=ch.text,
        )  # fmt: skip
        answer = router.call(inp)
        out.sent += 1
        if isinstance(answer, Deferred):
            return Outcome("deferred", chunks=len(chunks), sent=out.sent, reason=answer.reason)
        proposed, rejects = extract.parse(answer.content)
        out.parse_rejects += len(rejects)
        for p in proposed:
            r = verify(p, ch, ctx, xbrl, seen)
            if r is None:
                out.duplicates += 1
            elif isinstance(r, Rejected):
                out.rejected[r.check] += 1
            else:
                out.facts.append((r, f"{answer.provider}:{answer.model}"))
    return out
