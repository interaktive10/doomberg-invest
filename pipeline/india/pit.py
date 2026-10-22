"""Insider trading (SEBI PIT Reg 7(2)) disclosures -> insider_events (BRIEF §4.3, §4.6 S7-IN, §8 M3-04).

NSE publishes an index (the insider-trading page's API `corporates-pit-gg`) with one row per disclosure: symbol,
regulation, broadcast time and a link to the disclosure's XBRL. The XBRL holds the trades (one typed-dimension context
per disclosure line): category of person, name, shares, value, buy/sell, mode.
(The old `corporates-pit` API with the trades inline now returns nothing.)

Kept: promoter / promoter-group trades in equity shares:
- market purchases -> promoter_buy; market sales -> promoter_sell (S7-IN: purchases ≥ ₹2 crore within 90 days);
- pledge creation / revocation -> pledge_created / pledge_released;
- everything else (off-market and inter-se transfers, gifts, ESOPs, invocations by lenders, trades by directors,
  employees and relatives who are not in the promoter group) is not kept: none is a promoter's market decision.
A revised disclosure is stored as filed; S7 counts one trade per (person, date, kind), the latest filing winning.
Each line keeps its identity (`line`, the line's XBRL context), so two identical lines in one disclosure (two equal
same-day purchases) stay two trades (review F5 on M3).
Times on NSE are IST; filed_at is the exchange's broadcast time in UTC.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from pipeline.india.announcements import IST
from pipeline.india.xbrl import XbrlError, parse_instance

if TYPE_CHECKING:
    from pipeline.db.models import InsiderKind

API_PATH = "corporates-pit-gg?index=equities"  # the NSE page's activeApiName
PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading"
_TIME_FORMATS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M")


def _time(s: str | None) -> datetime | None:
    t = (s or "").strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=IST).astimezone(UTC)
        except ValueError:
            continue
    return None


def _decimal(s: str | None) -> Decimal | None:
    t = (s or "").strip().replace(",", "")
    if not t or t in ("-", "NIL", "Nil", "NA"):
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------- the index


@dataclass(frozen=True)
class PitFiling:
    symbol: str
    company: str
    regulation: str
    filed_at: datetime  # UTC broadcast time
    xbrl_url: str
    revision: bool


def parse_index_json(raw: bytes | str) -> list[PitFiling]:
    doc = json.loads(raw)
    rows = doc.get("data", []) if isinstance(doc, dict) else doc
    out: list[PitFiling] = []
    for r in rows:
        url, when = str(r.get("xmlFileName") or ""), _time(r.get("exchdisstime") or r.get("broadcastDateTime"))
        if not url.startswith("https://") or when is None or not r.get("symbol"):
            continue
        out.append(PitFiling(str(r["symbol"]).upper(), str(r.get("companyName") or ""), str(r.get("regulation") or ""),
                             when, url, str(r.get("typeOfSubmission") or "").lower() == "revision"))  # fmt: skip
    return out


# ---------------------------------------------------------------- one disclosure


@dataclass(frozen=True)
class PitTrade:
    symbol: str
    isin: str | None
    person: str
    category: str  # Promoter, Promoter Group, Director, KMP, Immediate relative, Designated Employee, …
    instrument: str  # Equity, …
    shares: Decimal | None
    value: Decimal | None  # INR
    transaction: str  # Buy, Sell, …
    mode: str  # Market Purchase, Market Sale, Off Market, Pledge Creation, …
    date_from: date | None
    date_to: date | None
    line: str = ""  # the disclosure line's context id: unique within the filing

    @property
    def promoter(self) -> bool:
        c = self.category.lower()
        return c.startswith("promoter")

    @property
    def equity(self) -> bool:
        return "equity" in self.instrument.lower()

    @property
    def kind(self) -> InsiderKind | None:
        """The insider_events kind, or None when the trade is not kept."""
        if not self.promoter or not self.equity:
            return None
        mode, tx = self.mode.lower(), self.transaction.lower()
        if "pledge" in mode or "pledge" in tx:
            if "creat" in mode or "creat" in tx:
                return "pledge_created"
            if any(k in mode or k in tx for k in ("revok", "revoc", "release")):
                return "pledge_released"
            return None  # invocation: the lender sold, not the promoter
        if "market purchase" in mode:
            return "promoter_buy"
        if "market sale" in mode:
            return "promoter_sell"
        return None

    @property
    def event_date(self) -> date | None:
        return self.date_to or self.date_from


def parse_disclosure(raw: bytes | str) -> list[PitTrade]:
    inst = parse_instance(raw)
    symbol, isin = (inst.text("Symbol") or "").upper(), inst.text("ISINCode")
    if not symbol:
        raise XbrlError("insider-trading XBRL without a Symbol")
    lines: dict[str, dict[str, str]] = defaultdict(dict)
    for name, facts in inst.facts.items():
        for f in facts:
            if f.context.dims:  # one context per disclosure line
                lines[f.context.id][name] = f.value.strip()
    out: list[PitTrade] = []
    for line, v in sorted(lines.items()):
        out.append(
            PitTrade(
                symbol=symbol,
                isin=isin,
                person=" ".join(v.get("NameOfThePerson", "").split()),
                category=v.get("CategoryOfPerson", ""),
                instrument=v.get("TypeOfInstrument", ""),
                shares=_decimal(v.get("SecuritiesAcquiredOrDisposedNumberOfSecurity")),
                value=_decimal(v.get("SecuritiesAcquiredOrDisposedValueOfSecurity")),
                transaction=v.get("SecuritiesAcquiredOrDisposedTransactionType", ""),
                mode=v.get("ModeOfAcquisitionOrDisposal", ""),
                date_from=_date(v.get("DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyFromDate")),
                date_to=_date(v.get("DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyToDate")),
                line=line,
            )
        )
    return out
