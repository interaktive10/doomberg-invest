"""Manual CSV imports: the last fallback when NSE and BSE are both unavailable (BRIEF §4.3 "Access rules").

Manzoor downloads CSVs with the NSE pages' own "Download (.csv)" buttons and adds them through the web upload screen,
which commits them under `imports/` (M7). The pipeline reads every CSV there; the kind is recognised by its header:
- `bhavcopy`: the CM-UDiFF common bhavcopy (TradDt, ISIN, TckrSymb, SctySrs, ClsPric, …), NSE or BSE;
- `bhavdata_full`: NSE's "security-wise full bhavcopy" (SYMBOL, SERIES, DATE1, CLOSE_PRICE, TTL_TRD_QNTY, …);
- `announcements`: the corporate-announcements page (SYMBOL, SUBJECT, DETAILS, DISSEMINATION, ATTACHMENT): every
  field corp_events keeps. The daily run reads it for a day the API couldn't give (review F4 on M3).
- `shareholding`: the shareholding-pattern page (COMPANY, PROMOTER & PROMOTER GROUP (A), AS ON DATE, ACTION, …): the
  promoter % only, by company name. The weekly run writes it when the listing API fails and queues the pattern's
  XBRL link (ACTION) for the full row (FII, DII, pledge), which replaces it once NSE answers.
Anything else is reported and skipped. The results and insider-trading pages' CSVs carry only links to each
filing's XBRL, not the numbers, so they can't replace the network; those filings wait in the runs' queues and
cursors until NSE answers (docs/SPEC_ISSUES.md 17). Imports are idempotent: the same file gives the same rows, and
the writers upsert or skip duplicates, so a file can stay in imports/ after it was used.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline.india import bhavcopy
from pipeline.india.announcements import IST, Announcement, ist_to_utc
from pipeline.india.bhavcopy import BhavRow
from pipeline.settings import REPO_ROOT

IMPORTS_DIR = REPO_ROOT / "imports"
FULL_BHAV_REQUIRED = ("SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE")
ANNOUNCEMENTS_REQUIRED = ("SYMBOL", "SUBJECT", "DETAILS", "DISSEMINATION", "ATTACHMENT")
SHAREHOLDING_REQUIRED = ("COMPANY", "PROMOTER & PROMOTER GROUP (A)", "AS ON DATE", "ACTION", "BROADCAST DATE/TIME")


def _norm(h: str) -> str:
    return " ".join(h.replace("﻿", "").split()).upper()


def detect(header: list[str]) -> str:
    cols = {_norm(h) for h in header}
    if {"TRADDT", "ISIN", "TCKRSYMB", "CLSPRIC"} <= cols:
        return "bhavcopy"
    if set(FULL_BHAV_REQUIRED) <= cols:
        return "bhavdata_full"
    if set(ANNOUNCEMENTS_REQUIRED) <= cols:
        return "announcements"
    if set(SHAREHOLDING_REQUIRED) <= cols:
        return "shareholding"
    return "unknown"


@dataclass(frozen=True)
class ShareholdingCsvRow:
    """One row of the NSE shareholding-pattern page's CSV."""

    company: str  # the company name (the CSV has no symbol)
    quarter_end: date
    promoter_pct: Decimal | None  # promoter and promoter group, percent of total shares
    filed_at: datetime  # UTC broadcast time, the same as the listing API's
    xbrl_url: str


@dataclass
class Imported:
    path: Path
    kind: str
    prices: list[BhavRow] = field(default_factory=list)
    announcements: list[Announcement] = field(default_factory=list)
    shareholding: list[ShareholdingCsvRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _decimal(s: str | None) -> Decimal | None:
    s = (s or "").strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_bhavdata_full(text: str, series: tuple[str, ...] = ("EQ",)) -> list[BhavRow]:
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [_norm(h) for h in (reader.fieldnames or [])]
    out: list[BhavRow] = []
    for r in reader:
        row = {k: (v or "").strip() for k, v in r.items() if k}
        close = _decimal(row.get("CLOSE_PRICE"))
        if row.get("SERIES", "").upper() not in series or close is None or close <= 0:
            continue
        vol = _decimal(row.get("TTL_TRD_QNTY"))
        out.append(
            BhavRow(
                trade_date=datetime.strptime(row["DATE1"], "%d-%b-%Y").date(),
                source="NSE",
                symbol=row["SYMBOL"].upper(),
                isin="",  # this format has no ISIN: matched by symbol
                series=row["SERIES"].upper(),
                close=close,
                volume=int(vol) if vol is not None else None,
                name="",
            )
        )
    return out


def _rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [_norm(h) for h in (reader.fieldnames or [])]
    return [{k: (v or "").strip() for k, v in r.items() if k} for r in reader]


def parse_announcements_csv(text: str) -> list[Announcement]:
    """The corporate-announcements page CSV. filed_at is the exchange's dissemination time (the API's exchdisstime),
    so a row matches the one the API gives for the same announcement."""
    out: list[Announcement] = []
    for row in _rows(text):
        when = row.get("DISSEMINATION") or row.get("BROADCAST DATE/TIME")
        if not row.get("SYMBOL") or not when:
            continue
        filed = ist_to_utc(when.title())
        pdf = row.get("ATTACHMENT") or None
        if pdf is not None and (not pdf.lower().startswith("https://") or pdf.endswith("/null")):
            pdf = None
        out.append(
            Announcement(
                symbol=row["SYMBOL"].upper(),
                isin="",
                company=row.get("COMPANY NAME", ""),
                category=row.get("SUBJECT", ""),
                text=" ".join(row.get("DETAILS", "").split()),
                event_date=filed.astimezone(IST).date(),
                filed_at=filed,
                pdf_url=pdf,
                seq_id="",
                has_xbrl=False,
            )
        )
    return out


def parse_shareholding_csv(text: str) -> list[ShareholdingCsvRow]:
    out: list[ShareholdingCsvRow] = []
    for row in _rows(text):
        url = row.get("ACTION", "")
        if not row.get("COMPANY") or not row.get("AS ON DATE") or not url.startswith("https://"):
            continue
        quarter = datetime.strptime(row["AS ON DATE"].title(), "%d-%b-%Y").date()
        when = row.get("BROADCAST DATE/TIME")
        if when:
            filed = ist_to_utc(when.title())
        else:  # date only: the end of that day in India (as shareholding.parse_listing)
            day = datetime.strptime(row["SUBMISSION DATE"].title(), "%d-%b-%Y").date()
            filed = datetime.combine(day + timedelta(days=1), time(0), tzinfo=IST).astimezone(UTC)
        pct = _decimal(row.get("PROMOTER & PROMOTER GROUP (A)"))
        out.append(ShareholdingCsvRow(row["COMPANY"], quarter, None if pct is None else pct.quantize(Decimal("0.0001")),
                                      filed, url))  # fmt: skip
    return out


def company_key(name: str) -> str:
    """A company name for matching the shareholding CSV to the securities list: case, punctuation, "&" and the
    Limited/Ltd suffix don't count."""
    words = re.sub(r"[^0-9a-z]+", " ", name.casefold().replace("&", " and ")).split()
    return " ".join(w for w in words if w not in ("limited", "ltd", "the"))


def import_file(path: Path) -> Imported:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    header = next(csv.reader(io.StringIO(text)), [])
    kind = detect(header)
    out = Imported(path, kind)
    if kind == "bhavcopy":
        parsed = bhavcopy.parse(raw, series=None)
        if parsed.source == "NSE":  # NSE files carry series: keep EQ; BSE files carry groups, matched by ISIN
            parsed = bhavcopy.parse(raw)
        out.prices, out.warnings = parsed.rows, parsed.warnings
    elif kind == "bhavdata_full":
        out.prices = parse_bhavdata_full(text)
    elif kind == "announcements":
        out.announcements = parse_announcements_csv(text)
    elif kind == "shareholding":
        out.shareholding = parse_shareholding_csv(text)
    else:
        out.warnings.append(f"{path.name}: unrecognised CSV (header {header[:6]}); skipped")
    return out


def import_dir(directory: Path = IMPORTS_DIR) -> list[Imported]:
    if not directory.is_dir():
        return []
    return [import_file(p) for p in sorted(directory.iterdir()) if p.suffix.lower() == ".csv" and p.is_file()]


def announcements_by_day(directory: Path = IMPORTS_DIR) -> dict[date, list[Announcement]]:
    """The imported announcements by IST day. A file covers every day from its first announcement to its last (NSE
    has announcements every day, weekends included), so a covered day may hold none."""
    out: dict[date, dict[tuple[str, datetime, str], Announcement]] = {}
    for imp in import_dir(directory):
        if imp.kind != "announcements" or not imp.announcements:
            continue
        first, last = min(a.event_date for a in imp.announcements), max(a.event_date for a in imp.announcements)
        for n in range((last - first).days + 1):
            out.setdefault(first + timedelta(days=n), {})
        for a in imp.announcements:
            out[a.event_date].setdefault((a.symbol, a.filed_at, a.pdf_url or a.text), a)
    return {d: list(v.values()) for d, v in sorted(out.items())}
