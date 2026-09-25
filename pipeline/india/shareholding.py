"""Quarterly shareholding patterns (SEBI LODR Reg 31) -> ownership_q (BRIEF §4.3, §8 M3-03).

From the shareholding XBRL (context axis CategoryOfShareholdersAxis; percentages are fractions in the file and are
stored as percent, matching the config thresholds):
- promoter_pct: ShareholdingOfPromoterAndPromoterGroup share of total shares.
- promoter_pledged_pct: shares pledged by the promoter group as a percent **of the promoter holding** (R5's
  "pledge ≥ 20% of promoter holding"; S7-IN's pledge release is a drop in this measure).
- fii_pct: foreign portfolio investors (FPI category I + II). Foreign direct/strategic holders (e.g. a foreign
  parent) are not portfolio money; the foreign-institutions total is the fallback when FPI rows are absent.
- dii_pct: domestic institutions (mutual funds, insurers, banks, pension funds, AIFs, …).
- inst_pct: domestic + foreign institutions.
filed_at is the exchange's broadcast time of the filing (IST in the listing, stored in UTC).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from pipeline.india.announcements import IST, ist_to_utc
from pipeline.india.xbrl import Instance, XbrlError, parse_instance

AXIS = "CategoryOfShareholdersAxis"
PROMOTER = "ShareholdingOfPromoterAndPromoterGroupMember"
TOTAL = "ShareholdingPatternMember"
FPI = ("InstitutionsForeignPortfolioInvestorCategoryOneMember", "InstitutionsForeignPortfolioInvestorCategoryTwoMember")
FOREIGN_INST = "InstitutionsForeignMember"
DOMESTIC_INST = "InstitutionsDomesticMember"
HUNDRED = Decimal(100)


class ShareholdingError(XbrlError):
    pass


@dataclass(frozen=True)
class Shareholding:
    symbol: str
    isin: str | None
    quarter_end: date
    total_shares: Decimal | None
    promoter_shares: Decimal | None
    pledged_shares: Decimal | None
    promoter_pct: Decimal | None
    promoter_pledged_pct: Decimal | None
    fii_pct: Decimal | None
    dii_pct: Decimal | None
    inst_pct: Decimal | None


def _category(inst: Instance, name: str, member: str, end: date) -> Decimal | None:
    return inst.number(name, None, end, ((AXIS, member),))


def _pct(fraction: Decimal | None) -> Decimal | None:
    return None if fraction is None else (fraction * HUNDRED).quantize(Decimal("0.0001"))


def parse_shareholding(raw: bytes | str) -> Shareholding:
    inst = parse_instance(raw)
    report = inst.text("DateOfReport")
    if not report:
        raise ShareholdingError("shareholding XBRL without DateOfReport")
    end = date.fromisoformat(report[:10])
    share = "ShareholdingAsAPercentageOfTotalNumberOfShares"
    promoter_frac = _category(inst, share, PROMOTER, end)
    promoter_shares = _category(inst, "NumberOfShares", PROMOTER, end)
    pledged = _category(inst, "NumberOfSharesEncumberedUnderPledged", PROMOTER, end)
    pledged_frac = _category(inst, "EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares", PROMOTER, end)
    if pledged_frac is None and pledged is not None and promoter_shares:
        pledged_frac = pledged / promoter_shares
    no_pledge = (inst.text("WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged") or "").lower() == "false"
    if no_pledge:
        pledged = Decimal(0) if pledged is None else pledged
        pledged_frac = Decimal(0) if pledged_frac is None else pledged_frac
    fpi = [_category(inst, share, m, end) for m in FPI]
    foreign = _category(inst, share, FOREIGN_INST, end)
    fii = sum((x for x in fpi if x is not None), Decimal(0)) if any(x is not None for x in fpi) else foreign
    dii = _category(inst, share, DOMESTIC_INST, end)
    inst_total = (dii or Decimal(0)) + (foreign or Decimal(0)) if dii is not None or foreign is not None else None
    return Shareholding(
        symbol=(inst.text("Symbol") or "").upper(),
        isin=inst.text("ISIN"),
        quarter_end=end,
        total_shares=_category(inst, "NumberOfShares", TOTAL, end),
        promoter_shares=promoter_shares,
        pledged_shares=pledged,
        promoter_pct=_pct(promoter_frac),
        promoter_pledged_pct=_pct(pledged_frac),
        fii_pct=_pct(fii),
        dii_pct=_pct(dii),
        inst_pct=_pct(inst_total),
    )


@dataclass(frozen=True)
class ShpListing:
    """One row of NSE's corporate-share-holdings-master API."""

    symbol: str
    isin: str
    quarter_end: date
    filed_at: datetime  # UTC
    xbrl_url: str
    record_id: str
    revised: bool


def parse_listing(raw: bytes | str) -> list[ShpListing]:
    doc = json.loads(raw)
    rows = doc.get("data", []) if isinstance(doc, dict) else doc
    out: list[ShpListing] = []
    for r in rows:
        url = str(r.get("xbrl") or "")
        if not url.startswith("https://") or not r.get("symbol") or not r.get("date"):
            continue
        quarter = datetime.strptime(str(r["date"]).title(), "%d-%b-%Y").date()
        when = r.get("broadcastDate") or r.get("systemDate")
        if when:
            filed = ist_to_utc(str(when).title(), "%d-%b-%Y %H:%M:%S")
        else:  # date only: the end of that day in India
            day = datetime.strptime(str(r["submissionDate"]).title(), "%d-%b-%Y").date()
            filed = datetime.combine(day + timedelta(days=1), time(0), tzinfo=IST).astimezone(UTC)
        out.append(
            ShpListing(
                str(r["symbol"]).upper(),
                str(r.get("isin") or ""),
                quarter,
                filed,
                url,
                str(r.get("recordId") or ""),
                str(r.get("revisedData") or "N").upper() == "Y",
            )
        )
    return out
