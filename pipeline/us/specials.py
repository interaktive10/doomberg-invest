"""Spin-offs (BRIEF §4.2, §4.6 S10): Form 10-12B registrations that become effective.

A registration counts as done at the first of: an 8-K with item 5.01 or 3.03 after the Form 10 (the separation:
change in control / material modification of holders' rights), an EFFECT notice for the 10-12B, or the registrant's
first 10-Q/10-K. The parent is proposed from company names mentioned in the Form 10 (e.g. "Separation and
Distribution Agreement, by and between General Electric Company and the registrant") and confirmed by hand in the
web app; nothing here is treated as confirmed.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from pipeline.us.names import normalize_name
from pipeline.us.submissions import Filing, Submissions, filing_doc_url

FORM10 = frozenset({"10-12B", "10-12B/A"})
SEPARATION_ITEMS = frozenset({"5.01", "3.03"})
PERIODIC = frozenset({"10-Q", "10-K"})
MIN_MENTIONS = 2
MAX_CANDIDATES = 3


@dataclass(frozen=True)
class Spinoff:
    registrant_cik: str
    registrant_name: str
    event_date: date
    filed_at: datetime  # when the evidence of effectiveness became public
    evidence: str  # "8-K 5.01/3.03" | "EFFECT" | "first periodic report"
    form10_accession: str
    form10_doc_url: str


def effective_spinoff(subs: Submissions) -> Spinoff | None:
    form10 = [f for f in subs.filings if f.form in FORM10]
    if not form10:
        return None
    first = min(form10, key=lambda f: f.accepted_at)
    latest = max(form10, key=lambda f: f.accepted_at)
    after = sorted((f for f in subs.filings if f.accepted_at > first.accepted_at), key=lambda f: f.accepted_at)
    hit: tuple[Filing, str] | None = None
    for f in after:
        if f.form.startswith("8-K") and SEPARATION_ITEMS & set(f.items):
            hit = (f, "8-K 5.01/3.03")
        elif f.form == "EFFECT" and any(i.upper().startswith("10-12B") for i in f.items):
            hit = (f, "EFFECT")
        elif f.form in PERIODIC:
            hit = (f, "first periodic report")
        if hit:
            break
    if hit is None:
        return None
    f, evidence = hit
    return Spinoff(
        registrant_cik=subs.cik,
        registrant_name=subs.name,
        event_date=f.filing_date,
        filed_at=f.accepted_at,
        evidence=evidence,
        form10_accession=latest.accession,
        form10_doc_url=filing_doc_url(subs.cik, latest.accession, latest.primary_document),
    )


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parent_candidates(
    form10_text: str, companies: Mapping[str, str], exclude_cik: str | None = None
) -> list[dict[str, object]]:
    """Universe companies (CIK -> name) named at least twice in the Form 10 text, most mentioned first."""
    norm = " " + normalize_name(form10_text) + " "
    scored: list[tuple[int, str, str]] = []
    for cik, name in companies.items():
        if cik == exclude_cik:
            continue
        n = normalize_name(name)
        if len(n) < 6 or " " not in n:  # one-word names ("APPLE", "TARGET") are too ambiguous in prose
            continue
        count = norm.count(f" {n} ")
        if count >= MIN_MENTIONS:
            scored.append((count, cik, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"cik": cik, "name": name, "mentions": n} for n, cik, name in scored[:MAX_CANDIDATES]]
