"""Which documents to read, and fetching them (BRIEF §4.5 scope, Appendix F.3).

Scope, in the config/quotas.yaml work order: capex-desk companies (US + India), the weekly candidate shortlist (top
100 by Evidence with no text facts yet), then companies with a live thesis. For each US company in scope, the SEC
submissions list gives its filings of the last FILING_DAYS: 10-K and 10-Q (the primary document) and 8-Ks with
items 1.01, 2.02, 2.03, 7.01 or 8.01 (the EX-99.1/EX-99.2 press releases from the filing index, and the 8-K itself
for 1.01/2.03 agreements). New ones go to `filings`; India's documents are the announcement PDFs P-07 flagged.
Raw files stay on the runner (§2.8): raw/{cik}/{accession}/{filename}, deduplicated by sha256.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from pipeline.us.submissions import Submissions, filing_doc_url, filing_index_url

FILING_DAYS = 400  # a new company's history: about four quarters of reports (diffs and the demand index need them)
PERIODIC = frozenset({"10-K", "10-Q"})
EIGHT_K_ITEMS = frozenset({"1.01", "2.02", "2.03", "7.01", "8.01"})
AGREEMENT_ITEMS = frozenset({"1.01", "2.03"})
EXHIBITS = ("EX-99.1", "EX-99.2")


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str
    items: tuple[str, ...]
    accepted_at: datetime
    report_date: date | None
    primary_doc_url: str
    index_url: str


def text_filings(subs: Submissions, since: date) -> list[FilingRef]:
    out = []
    for f in subs.filings:
        if f.filing_date < since:
            continue
        form = f.form.upper()
        if form in PERIODIC or (form == "8-K" and EIGHT_K_ITEMS & set(f.items)):
            out.append(FilingRef(f.accession, form, tuple(f.items), f.accepted_at, f.report_date,
                                 filing_doc_url(subs.cik, f.accession, f.primary_document),
                                 filing_index_url(subs.cik, f.accession)))  # fmt: skip
    return out


class _IndexParser(HTMLParser):
    """Rows of an EDGAR filing index table: (document href, type)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.links: list[str | None] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row, self._link = [], None
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "a" and self._row is not None and self._link is None:
            href = dict(attrs).get("href") or ""
            if "/Archives/edgar/data/" in href and not href.endswith("-index.htm"):
                self._link = href

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self.links.append(self._link)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def exhibit_urls(index_html: str, types: tuple[str, ...] = EXHIBITS) -> dict[str, str]:
    """type -> absolute URL of each wanted exhibit in a filing index page (inline-XBRL viewer links unwrapped)."""
    p = _IndexParser()
    p.feed(index_html)
    out: dict[str, str] = {}
    for row, link in zip(p.rows, p.links, strict=True):
        if link is None:
            continue
        kind = next((c.upper() for c in row if re.fullmatch(r"EX-\d+(?:\.\d+)?", c.upper())), None)
        if kind in types and kind not in out:
            href = link.split("?doc=", 1)[-1] if "?doc=" in link else link
            out[kind] = href if href.startswith("https://") else f"https://www.sec.gov{href}"
    return out


def raw_path(root: Path, cik_or_key: str, accession_or_hash: str, filename: str) -> Path:
    return root / "raw" / cik_or_key / accession_or_hash / re.sub(r"[^\w.\-]", "_", filename)


def store_raw(root: Path, key: str, sub: str, url: str, body: bytes) -> tuple[Path, str]:
    """Write a fetched file under raw/ (same sha256 = same file) and return (path, sha256)."""
    digest = hashlib.sha256(body).hexdigest()
    name = url.rsplit("/", 1)[-1] or digest
    p = raw_path(root, key, sub or digest[:16], name)
    if not (p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == digest):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return p, digest


def since(today: date, days: int = FILING_DAYS) -> date:
    return today - timedelta(days=days)
