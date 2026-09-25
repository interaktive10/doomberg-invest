"""What a signal or red flag sees (BRIEF §4.6): one company as known at the as-of week, plus the cross-sectional
views some rules need. Plain dataclasses, built from point-in-time rows by the weekly run or from F-SYNQ cases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pipeline.signals.series import ZERO, Series


@dataclass(frozen=True)
class SignalResult:
    fired: bool
    strength: Decimal
    inputs: dict[str, Any]


def fired(strength: Decimal, **inputs: Any) -> SignalResult:
    return SignalResult(True, max(ZERO, min(Decimal(1), strength)), inputs)


def quiet(**inputs: Any) -> SignalResult:
    return SignalResult(False, ZERO, inputs)


def missing(*names: str, **inputs: Any) -> SignalResult:
    """An input the rule needs is unknown: never fires (BRIEF §4.6), and says which."""
    return SignalResult(False, ZERO, {"missing": list(names), **inputs})


@dataclass(frozen=True)
class Holding:
    """An ownership_q row: 13F holder count (US) or the shareholding pattern (India)."""

    quarter_end: date
    inst_holders: int | None = None
    fii_pct: Decimal | None = None
    dii_pct: Decimal | None = None
    promoter_pct: Decimal | None = None
    promoter_pledged_pct: Decimal | None = None


@dataclass(frozen=True)
class Insider:
    company_id: str
    person: str
    event_date: date
    filed_at: datetime
    kind: str
    value: Decimal | None
    planned: bool
    source_url: str
    currency: str | None = None


@dataclass(frozen=True)
class Event:
    kind: str
    event_date: date
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fact:
    """A verified text fact (Appendix F) whose document was published by the as-of date."""

    fact_type: str
    subject_key: str
    as_of: date
    value_num: Decimal | None = None
    unit: str = "other"
    subject: str = ""
    period_end: date | None = None
    counterparty: str | None = None


@dataclass(frozen=True)
class SectorView:
    """S12's sector conditions, computed across the sector's companies as of the week."""

    sector: str | None
    capex_da_medians: Sequence[Decimal | None] = ()  # trailing years ending at lags 0, 4, 8
    revenue_yoy_medians: Sequence[Decimal | None] = ()  # quarterly YoY medians at lags 0, 1, 2
    tightness_facts: int = 0  # verified price_increase / longer lead_time facts in the sector, last 2 quarters


@dataclass(frozen=True)
class CapexView:
    """S11's inputs from the Capex Desk (M5): confirmed memberships and the category demand index."""

    categories: Sequence[str] = ()  # confirmed memberships
    direction: Mapping[str, str] = field(default_factory=dict)  # category -> rising | flat | falling
    input_growth: Mapping[str, Decimal] = field(default_factory=dict)  # category -> YoY growth of its inputs
    graph_distance: int | None = None  # from an anchor company (0 = anchor)
    export_exposure_rising: bool = False
    export_quote: bool = False  # India: a verified US/data-center export quote


@dataclass(frozen=True)
class Ctx:
    company_id: str
    market: str  # 'us' | 'in'
    week: date
    series: Series
    cfg: Mapping[str, Any]  # config/signals.yaml
    ownership: Sequence[Holding] = ()
    insiders: Sequence[Insider] = ()
    events: Sequence[Event] = ()
    facts: Sequence[Fact] = ()
    holdco: bool = False
    holder_pct_in_size_decile: Decimal | None = None  # S8 (US), cross-sectional
    sector: SectorView | None = None
    capex: CapexView | None = None
    surveillance: str | None = None  # India ASM/GSM reason (R5)
    fired: Mapping[str, bool] = field(default_factory=dict)  # signals computed earlier this week

    def section(self, name: str) -> Mapping[str, Any]:
        sec: Mapping[str, Any] = self.cfg[name]
        return sec


def months_before(d: date, months: int) -> date:
    """The same day `months` earlier (clamped to the month's last day). Look-back windows ("<= 18 months ago", "in
    the last 2 quarters") include this start day."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


def num(x: Decimal | int | None) -> float | int | None:
    """A JSON-friendly number for `inputs` (6 decimals; the exact Decimal decides whether a rule fired)."""
    if x is None or isinstance(x, int):
        return x
    return float(round(x, 6))


def cfg_dec(section: Mapping[str, Any], key: str) -> Decimal:
    return Decimal(str(section[key]))
