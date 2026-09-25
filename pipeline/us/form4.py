"""SEC Form 4 parsing (BRIEF §4.2): insider open-market purchases for S7.

- Only non-derivative transactions with code P become insider events (open-market or private purchases). The
  derivative table (options, RSUs) is parsed for completeness but never stored.
- value = shares x price.
- planned = the Rule 10b5-1 checkbox (aff10b5One, on forms since April 2023) is marked, or a footnote referenced by
  the transaction mentions 10b5-1.
- roles come from the reporting-owner relationship; joint filers are one person (joined names), so S7's
  "distinct insiders" counts people, not filing entities.

Input is the full submission text (.txt): its SGML header carries ACCEPTANCE-DATETIME in US Eastern time (checked on
F-F4: the header's 06:01:05 is the JSON's 11:01:05Z), converted to UTC here.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
TENB5 = re.compile(r"10b5\s*[-‐–—]?\s*1", re.IGNORECASE)
_TRUE = {"1", "true", "yes"}


@dataclass(frozen=True)
class Owner:
    cik: str
    name: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class Transaction:
    security: str
    date: date
    code: str
    shares: Decimal | None
    price: Decimal | None
    acquired: bool | None  # A = True, D = False
    direct: bool | None
    footnote_ids: tuple[str, ...]
    planned: bool
    derivative: bool

    @property
    def value(self) -> Decimal | None:
        return self.shares * self.price if self.shares is not None and self.price is not None else None


@dataclass(frozen=True)
class Form4:
    accession: str | None
    accepted_at: datetime | None  # UTC
    document_type: str  # "4" or "4/A"
    original_date: date | None  # a 4/A's dateOfOriginalSubmission: the filing date of the Form 4 it amends
    issuer_cik: str
    issuer_name: str
    issuer_symbol: str | None
    owners: tuple[Owner, ...]
    checkbox_10b5_1: bool
    footnotes: dict[str, str]
    transactions: tuple[Transaction, ...]

    @property
    def person(self) -> str:
        return " / ".join(o.name for o in self.owners)

    @property
    def role(self) -> str:
        roles: list[str] = []
        for o in self.owners:
            roles.extend(r for r in o.roles if r not in roles)
        return "; ".join(roles)

    def purchases(self) -> list[Transaction]:
        """Non-derivative code-P transactions: the only ones S7 uses."""
        return [t for t in self.transactions if not t.derivative and t.code == "P"]


class Form4Error(ValueError):
    pass


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _decimal(s: str | None) -> Decimal | None:
    if s is None:
        return None
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def _roles(rel: ET.Element | None) -> tuple[str, ...]:
    if rel is None:
        return ()
    roles: list[str] = []
    if (_text(rel, "isDirector") or "").lower() in _TRUE:
        roles.append("director")
    if (_text(rel, "isOfficer") or "").lower() in _TRUE:
        roles.append(_text(rel, "officerTitle") or "officer")
    if (_text(rel, "isTenPercentOwner") or "").lower() in _TRUE:
        roles.append("10% owner")
    if (_text(rel, "isOther") or "").lower() in _TRUE:
        roles.append(_text(rel, "otherText") or "other")
    return tuple(roles)


def _transaction(el: ET.Element, derivative: bool, checkbox: bool, footnotes: dict[str, str]) -> Transaction | None:
    code = _text(el, "transactionCoding/transactionCode")
    when = _text(el, "transactionDate/value")
    if not code or not when:
        return None
    ids = tuple(dict.fromkeys(f.get("id", "") for f in el.iter("footnoteId") if f.get("id")))
    footnote_planned = any(TENB5.search(footnotes.get(i, "")) for i in ids)
    ad = _text(el, "transactionAmounts/transactionAcquiredDisposedCode/value")
    di = _text(el, "ownershipNature/directOrIndirectOwnership/value")
    return Transaction(
        security=_text(el, "securityTitle/value") or "",
        date=date.fromisoformat(when[:10]),
        code=code.upper(),
        shares=_decimal(_text(el, "transactionAmounts/transactionShares/value")),
        price=_decimal(_text(el, "transactionAmounts/transactionPricePerShare/value")),
        acquired=None if ad is None else ad.upper() == "A",
        direct=None if di is None else di.upper() == "D",
        footnote_ids=ids,
        planned=checkbox or footnote_planned,
        derivative=derivative,
    )


def safe_xml(xml: str) -> ET.Element:
    """Parse XML with no DTD allowed. SEC ownership XML never declares one, so refusing <!DOCTYPE removes entity
    expansion attacks entirely; ElementTree never fetches external entities."""
    body = xml.strip()
    if re.search(r"<!DOCTYPE|<!ENTITY", body, re.IGNORECASE):
        raise Form4Error("XML with a DTD/entity declaration refused")
    try:
        return ET.fromstring(body)  # noqa: S314 — DTDs refused above; the input is an SEC filing
    except ET.ParseError as e:
        raise Form4Error(f"XML does not parse: {e}") from e


def parse_xml(xml: str, accession: str | None = None, accepted_at: datetime | None = None) -> Form4:
    root = safe_xml(xml)
    if root.tag != "ownershipDocument":
        raise Form4Error(f"not an ownershipDocument: <{root.tag}>")
    footnotes = {f.get("id", ""): " ".join("".join(f.itertext()).split()) for f in root.iter("footnote")}
    checkbox = (_text(root, "aff10b5One") or "").lower() in _TRUE
    owners = tuple(
        Owner(
            cik=(_text(o, "reportingOwnerId/rptOwnerCik") or "").zfill(10),
            name=_text(o, "reportingOwnerId/rptOwnerName") or "",
            roles=_roles(o.find("reportingOwnerRelationship")),
        )
        for o in root.findall("reportingOwner")
    )
    txs: list[Transaction] = []
    for derivative, path in ((False, "nonDerivativeTable/nonDerivativeTransaction"),
                             (True, "derivativeTable/derivativeTransaction")):  # fmt: skip
        for el in root.findall(path):
            t = _transaction(el, derivative, checkbox, footnotes)
            if t is not None:
                txs.append(t)
    return Form4(
        accession=accession,
        accepted_at=accepted_at,
        document_type=_text(root, "documentType") or "4",
        original_date=_date(_text(root, "dateOfOriginalSubmission")),
        issuer_cik=(_text(root, "issuer/issuerCik") or "").zfill(10),
        issuer_name=_text(root, "issuer/issuerName") or "",
        issuer_symbol=_text(root, "issuer/issuerTradingSymbol"),
        owners=owners,
        checkbox_10b5_1=checkbox,
        footnotes=footnotes,
        transactions=tuple(txs),
    )


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v.strip()[:10]) if v else None
    except ValueError:
        return None


def header_acceptance(text: str) -> datetime | None:
    """ACCEPTANCE-DATETIME from an SGML header (US Eastern) as UTC."""
    m = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", text)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=EASTERN).astimezone(UTC)


def header_accession(text: str) -> str | None:
    m = re.search(r"ACCESSION NUMBER:\s*(\d{10}-\d{2}-\d{6})", text)
    return m.group(1) if m else None


def parse_submission(text: str) -> Form4:
    """A full submission (.txt): header + the Form 4 XML document."""
    m = re.search(r"<XML>(.*?)</XML>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        raise Form4Error("no <XML> document in the submission")
    return parse_xml(m.group(1), header_accession(text), header_acceptance(text))
