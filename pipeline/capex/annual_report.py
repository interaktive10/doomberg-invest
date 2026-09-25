"""India annual-report excerpts for P-06 (BRIEF §4.11 "business description, annual-report text"): NSE's
annual-reports API lists each company's reports; the latest PDF's pages are read with pypdfium2 and the pages that
pass the Appendix F keyword prefilter (score >= 3) are kept, up to MAX_CHARS, labelled with their page numbers.

Listing shape (live, 2026-09-25; fixtures/in/annual_reports/): {"data": [{"companyName", "fromYr", "toYr",
"fileName": "https://nsearchives.nseindia.com/annual_reports/AR_..._KEI_2025_2026_....pdf",
"disseminationDateTime": "05-SEP-2026 16:22:32"}]} (IST).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from pipeline.facts.canonical import canonical
from pipeline.facts.chunk import score
from pipeline.india.announcements import ist_to_utc

API = "annual-reports?index=equities&symbol={symbol}"
MAX_CHARS = 20_000
MAX_PDF_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True)
class Report:
    url: str
    from_year: str
    to_year: str
    published: datetime

    @property
    def label(self) -> str:
        return f"Annual report {self.from_year}-{self.to_year[-2:]}"


def listing_path(symbol: str) -> str:
    return API.format(symbol=quote(symbol, safe=""))


def latest(raw: bytes) -> Report | None:
    doc = json.loads(raw)
    rows = doc.get("data", []) if isinstance(doc, dict) else doc
    out = []
    for r in rows:
        url = str(r.get("fileName") or "")
        when = r.get("disseminationDateTime") or r.get("broadcast_dttm")
        if not url.lower().endswith(".pdf") or not url.startswith("https://") or not when:
            continue
        out.append(Report(url, str(r.get("fromYr") or ""), str(r.get("toYr") or ""), ist_to_utc(str(when))))
    return max(out, key=lambda r: r.published) if out else None


def excerpts(pages: list[str], label: str, max_chars: int = MAX_CHARS) -> list[tuple[str, str]]:
    """(label with page number, page text) for the pages that pass the prefilter, best-scoring first, within
    max_chars."""
    scored = sorted(((score(t), i, canonical(t)) for i, t in enumerate(pages)), key=lambda x: (-x[0], x[1]))
    out, used = [], 0
    for s, i, text in scored:
        if s < 3 or not text:
            continue
        if used + len(text) > max_chars:
            break
        out.append((f"{label}, p. {i + 1}", text))
        used += len(text)
    return sorted(out, key=lambda x: int(x[0].rsplit("p. ", 1)[1]))
