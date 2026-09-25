"""Promoter pledge creation and release (BRIEF §4.3 "Pledge creation and release events -> insider_events").

Derived from consecutive quarterly shareholding patterns: the change in shares the promoter group has pledged
(shareholding.py). A rise is `pledge_created`, a fall `pledge_released`, dated at the quarter end and filed when the
later pattern was published. The quarterly pledge % itself (R5, S7-IN's "pledge down ≥ 5 pp") lives in ownership_q.
Event-by-event SAST Reg 31 disclosures would date pledges more precisely; they are not needed by any rule in §4.6-4.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pipeline.india.shareholding import Shareholding

PERSON = "promoter group"
MAX_GAP_DAYS = 100  # consecutive quarters only; a skipped quarter would date the change wrongly


@dataclass(frozen=True)
class PledgeEvent:
    symbol: str
    kind: Literal["pledge_created", "pledge_released"]
    event_date: date
    filed_at: datetime
    shares: Decimal
    pledged_pct_before: Decimal | None
    pledged_pct_after: Decimal | None


def pledge_event(prev: Shareholding | None, cur: Shareholding, filed_at: datetime) -> PledgeEvent | None:
    if prev is None or prev.symbol != cur.symbol or prev.pledged_shares is None or cur.pledged_shares is None:
        return None
    gap = cur.quarter_end - prev.quarter_end
    if not timedelta(days=0) < gap <= timedelta(days=MAX_GAP_DAYS):
        return None
    delta = cur.pledged_shares - prev.pledged_shares
    if delta == 0:
        return None
    return PledgeEvent(
        symbol=cur.symbol,
        kind="pledge_created" if delta > 0 else "pledge_released",
        event_date=cur.quarter_end,
        filed_at=filed_at,
        shares=abs(delta),
        pledged_pct_before=prev.promoter_pledged_pct,
        pledged_pct_after=cur.promoter_pledged_pct,
    )
