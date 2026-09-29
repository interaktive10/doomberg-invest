"""SEC submissions JSON (BRIEF §2.7, §4.1-4.2): company metadata, the filing list and acceptance timestamps.

`acceptanceDateTime` is UTC. Checked on the F-US fixture: EDGAR dates a filing accepted after 17:30 ET on the next
business day, and 3,057 of 3,082 filings are consistent with that rule only when the timestamp is read as UTC (the
rest are SEC-internal EFFECT notices and a back-dated 10-Q). A missing timestamp falls back to the end of the filing
date (next day 00:00 UTC), which is never earlier than the real acceptance.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


@dataclass(frozen=True)
class Filing:
    accession: str  # 0000320193-24-000123
    form: str
    filing_date: date
    report_date: date | None
    accepted_at: datetime  # UTC
    items: tuple[str, ...]
    primary_document: str


@dataclass(frozen=True)
class Submissions:
    cik: str  # zero-padded to 10 digits
    name: str
    entity_type: str | None
    sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None  # "0926" (MMDD)
    tickers: tuple[str, ...]
    exchanges: tuple[str, ...]
    filings: tuple[Filing, ...]

    def accepted(self) -> dict[str, datetime]:
        return {f.accession: f.accepted_at for f in self.filings}

    def by_accession(self) -> dict[str, Filing]:
        return {f.accession: f for f in self.filings}


def end_of_day_utc(d: date) -> datetime:
    """Conservative availability for a date-only timestamp: the next day at 00:00 UTC."""
    return datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=UTC)


def parse_acceptance(raw: str | None, filing_date: date) -> datetime:
    if raw:
        try:
            return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            pass
    return end_of_day_utc(filing_date)


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _rows(block: Mapping[str, Sequence[Any]]) -> Iterable[Filing]:
    n = len(block.get("accessionNumber", []))
    col = {k: block.get(k) or [None] * n for k in ("form", "filingDate", "reportDate", "acceptanceDateTime",
                                                   "items", "primaryDocument")}  # fmt: skip
    for i in range(n):
        filed = date.fromisoformat(str(col["filingDate"][i]))
        items = str(col["items"][i] or "")
        yield Filing(
            accession=str(block["accessionNumber"][i]),
            form=str(col["form"][i]),
            filing_date=filed,
            report_date=_date(col["reportDate"][i] or None),
            accepted_at=parse_acceptance(col["acceptanceDateTime"][i], filed),
            items=tuple(x.strip() for x in items.split(",") if x.strip()),
            primary_document=str(col["primaryDocument"][i] or ""),
        )


def parse_submissions(doc: Mapping[str, Any], pages: Sequence[Mapping[str, Any]] = ()) -> Submissions:
    """`doc` is CIK##########.json; `pages` are its older-filings files (CIK##########-submissions-NNN.json)."""
    filings = {f.accession: f for block in [doc["filings"]["recent"], *pages] for f in _rows(block)}
    return Submissions(
        cik=str(doc["cik"]).zfill(10),
        name=str(doc.get("name") or ""),
        entity_type=doc.get("entityType"),
        sic=str(doc["sic"]) if doc.get("sic") else None,
        sic_description=doc.get("sicDescription"),
        fiscal_year_end=doc.get("fiscalYearEnd"),
        tickers=tuple(doc.get("tickers") or ()),
        exchanges=tuple(e for e in (doc.get("exchanges") or ()) if e),
        filings=tuple(sorted(filings.values(), key=lambda f: (f.accepted_at, f.accession))),
    )


def filing_index_url(cik: str, accession: str) -> str:
    return f"{ARCHIVES}/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"


def filing_doc_url(cik: str, accession: str, document: str) -> str:
    return f"{ARCHIVES}/{int(cik)}/{accession.replace('-', '')}/{document}"


def filing_txt_url(cik: str, accession: str) -> str:
    """The full submission text (SGML header + every document); its header carries ACCEPTANCE-DATETIME."""
    return f"{ARCHIVES}/{int(cik)}/{accession.replace('-', '')}/{accession}.txt"
