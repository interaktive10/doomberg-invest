"""NSE corporate announcements (BRIEF §4.3 "Announcements") -> corp_events(kind='announcement') with the PDF link.

API: https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY
Times on NSE are IST; filed_at is the exchange's dissemination time converted to UTC (the moment it was public).
Triage (P-07) and PDF extraction for the capex desk and candidates are M5's.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


_ACQUISITION = re.compile(r"\bacqui(?:re|red|res|ring|sitions?)\b|\bamalgamat", re.I)
_NOT_ACQUISITION = re.compile(  # M4 review R1-F5: shareholders' takeover-code disclosures and new subsidiaries
    r"regulation\s*29|substantial\s+acquisition\s+of\s+shares|\bSAST\b|takeovers?\)?\s+regulations|"
    r"incorporat(?:ion|ed|es|ing)\b",
    re.I,
)


def is_acquisition(category: str, text: str) -> bool:
    """An announcement of the company acquiring or amalgamating a business (R4's India exception): NSE files
    SEBI takeover-code disclosures (Regulation 29, "Substantial Acquisition of Shares and Takeovers") and the
    incorporation of subsidiaries under the same words, and those are not the company buying anything."""
    s = f"{category} {text}"
    return bool(_ACQUISITION.search(s)) and not _NOT_ACQUISITION.search(s)


def ist_to_utc(s: str, fmt: str = "%d-%b-%Y %H:%M:%S") -> datetime:
    return datetime.strptime(s.strip(), fmt).replace(tzinfo=IST).astimezone(UTC)


def api_path(day_from: date, day_to: date) -> str:
    return f"corporate-announcements?index=equities&from_date={day_from:%d-%m-%Y}&to_date={day_to:%d-%m-%Y}"


@dataclass(frozen=True)
class Announcement:
    symbol: str
    isin: str
    company: str
    category: str  # NSE's subject line ("Credit Rating", "Trading Window", …)
    text: str
    event_date: date  # IST calendar date
    filed_at: datetime  # UTC
    pdf_url: str | None
    seq_id: str
    has_xbrl: bool


def parse(raw: bytes | str) -> list[Announcement]:
    doc = json.loads(raw)
    rows = doc.get("data", []) if isinstance(doc, dict) else doc
    out: list[Announcement] = []
    for r in rows:
        when = r.get("exchdisstime") or r.get("an_dt")
        if not when or not r.get("symbol"):
            continue
        filed = ist_to_utc(when)
        pdf = (r.get("attchmntFile") or "").strip() or None
        if pdf is not None and (not pdf.lower().startswith("https://") or pdf.endswith("/null")):
            pdf = None
        out.append(
            Announcement(
                symbol=str(r["symbol"]).strip().upper(),
                isin=str(r.get("sm_isin") or "").strip(),
                company=str(r.get("sm_name") or "").strip(),
                category=str(r.get("desc") or "").strip(),
                text=" ".join(str(r.get("attchmntText") or "").split()),
                event_date=filed.astimezone(IST).date(),
                filed_at=filed,
                pdf_url=pdf,
                seq_id=str(r.get("seq_id") or ""),
                has_xbrl=bool(r.get("hasXbrl")),
            )
        )
    return out
