"""US events from EDGAR (BRIEF §4.2, §2.7): Form 4 purchases, 8-K items, late filings, spin-offs.

The daily run reads the EDGAR daily master index and keeps filings of universe companies (plus Form 10-12B
registrants, which are not listed yet):
- Form 4 / 4/A -> fetch the submission, keep non-derivative code-P purchases (form4.py).
- 8-K item 4.01 -> corp_events(kind='auditor_change'). Items 1.01 and 2.03 on capex-desk companies -> `filings`
  (status new) for text extraction in M5.
- NT 10-K / NT 10-Q -> corp_events(kind='late_filing').
- Form 10-12B registrations that become effective -> corp_events(kind='spinoff') with parent candidates to confirm
  in the web app (specials.py).
Items and acceptance times come from the company's submissions JSON (the index has neither).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pipeline.us.submissions import Submissions, end_of_day_utc, filing_doc_url, filing_txt_url

FORM4 = frozenset({"4", "4/A"})
EIGHT_K = frozenset({"8-K", "8-K/A"})
LATE = frozenset({"NT 10-K", "NT 10-Q", "NT 10-K/A", "NT 10-Q/A"})
FORM10 = frozenset({"10-12B", "10-12B/A"})
AUDITOR_ITEM = "4.01"
TEXT_ITEMS = frozenset({"1.01", "2.03"})


@dataclass(frozen=True)
class IndexRow:
    cik: str  # 10 digits
    company: str
    form: str
    date_filed: date
    path: str  # edgar/data/886744/0000950170-25-030327.txt

    @property
    def accession(self) -> str:
        return self.path.rsplit("/", 1)[-1].removesuffix(".txt")

    @property
    def url(self) -> str:
        return f"https://www.sec.gov/Archives/{self.path}"


def parse_master_index(text: str) -> list[IndexRow]:
    """EDGAR daily/quarterly master.idx: header, a dashed line, then CIK|Company|Form|Date|File rows."""
    rows: list[IndexRow] = []
    body = False
    for line in text.splitlines():
        if not body:
            body = line.startswith("-----")
            continue
        parts = line.split("|")
        if len(parts) != 5 or not parts[0].strip().isdigit():
            continue
        cik, company, form, filed, path = (p.strip() for p in parts)
        rows.append(
            IndexRow(cik.zfill(10), company, form, date(int(filed[:4]), int(filed[4:6]), int(filed[6:8])), path)
        )
    return rows


def master_index_url(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{q}/master.{d:%Y%m%d}.idx"


@dataclass(frozen=True)
class Selection:
    form4: list[IndexRow]
    need_submissions: set[str]  # CIKs whose submissions JSON gives items / acceptance / 10-12B history


def select(rows: Iterable[IndexRow], universe: set[str]) -> Selection:
    """Index rows the daily run acts on. A Form 4 appears once per filer (issuer and owner); only the issuer's row
    (a universe CIK) is kept, once per accession. Form 10 registrants are not in the universe: the daily run tracks
    them separately (pending registrations) and checks them whenever they file."""
    form4: dict[str, IndexRow] = {}
    need: set[str] = set()
    for r in rows:
        if r.cik not in universe:
            continue
        if r.form in FORM4:
            form4.setdefault(r.accession, r)
        elif r.form in EIGHT_K or r.form in LATE:
            need.add(r.cik)
    return Selection(list(form4.values()), need)


EventKind = Literal["auditor_change", "late_filing", "spinoff"]


@dataclass(frozen=True)
class CorpEventDraft:
    cik: str
    kind: EventKind
    event_date: date
    filed_at: datetime
    source_url: str
    detail: dict[str, object]


@dataclass(frozen=True)
class TextFilingDraft:
    """An 8-K (items 1.01/2.03) queued for M5 text extraction."""

    cik: str
    accession: str
    form: str
    items: tuple[str, ...]
    filed_at: datetime
    accepted_at: datetime
    period_of_report: date | None
    primary_doc_url: str
    index_url: str


def filing_events(
    subs: Submissions,
    accessions: set[str] | None = None,
    capex_desk: bool = False,
) -> tuple[list[CorpEventDraft], list[TextFilingDraft]]:
    """Events from a company's submissions; `accessions` limits it to today's filings (None = all history)."""
    events: list[CorpEventDraft] = []
    texts: list[TextFilingDraft] = []
    for f in subs.filings:
        if accessions is not None and f.accession not in accessions:
            continue
        url = filing_txt_url(subs.cik, f.accession)
        if f.form in EIGHT_K and AUDITOR_ITEM in f.items:
            events.append(
                CorpEventDraft(
                    subs.cik,
                    "auditor_change",
                    f.filing_date,
                    f.accepted_at,
                    url,
                    {"form": f.form, "items": list(f.items), "accession": f.accession},
                )  # fmt: skip
            )
        if f.form in EIGHT_K and capex_desk and TEXT_ITEMS & set(f.items):
            texts.append(
                TextFilingDraft(
                    subs.cik,
                    f.accession,
                    f.form,
                    f.items,
                    end_of_day_utc(f.filing_date),
                    f.accepted_at,
                    f.report_date,
                    filing_doc_url(subs.cik, f.accession, f.primary_document),
                    url,
                )  # fmt: skip
            )
        if f.form in LATE:
            events.append(
                CorpEventDraft(
                    subs.cik,
                    "late_filing",
                    f.filing_date,
                    f.accepted_at,
                    url,
                    {"form": f.form, "accession": f.accession},
                )  # fmt: skip
            )
    return events, texts
