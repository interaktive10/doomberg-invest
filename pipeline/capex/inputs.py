"""Demand-input levels at a date (BRIEF §4.11), from verified facts known by then (pit.AsOf.facts rows: published
before the cutoff) and from the EIA series.

- hyperscaler_capex_guidance: per anchor company, its capex_guidance fact for the latest fiscal year it has guided
  (the most recent statement of it); summed over anchors (a Panel, USD).
- utility_large_load_gw: per company, its latest utility_load fact in GW (MW / 1000); summed (a Panel).
- lead_time_<equipment>: the median over companies of each one's latest lead_time fact whose key names the
  equipment, in months (weeks x 12/52, years x 12).
- eia_planned_additions_mw: the latest EIA monthly total on or before the date.
Facts older than `fact_max_age_days` (by as_of) no longer set a level.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pipeline.capex.index import Panel


class FactLike(Protocol):
    @property
    def company_id(self) -> UUID: ...
    @property
    def fact_type(self) -> str: ...
    @property
    def subject_key(self) -> str: ...
    @property
    def value_num(self) -> Decimal | None: ...
    @property
    def unit(self) -> str: ...
    @property
    def period_end(self) -> date | None: ...
    @property
    def as_of(self) -> date: ...
    @property
    def published_at(self) -> datetime: ...


def _known(facts: Sequence[FactLike], d: date, max_age: int) -> list[FactLike]:
    """Facts published by the end of day d, stated within max_age days."""
    return [f for f in facts if f.published_at.date() <= d and f.as_of >= d - timedelta(days=max_age)]


def _latest(fs: Sequence[FactLike]) -> FactLike:
    return max(fs, key=lambda f: (f.as_of, f.published_at))


def guidance(facts: Sequence[FactLike], anchors: Mapping[UUID, str], d: date, max_age: int) -> Panel | None:
    parts: dict[str, Decimal] = {}
    for cid, ticker in anchors.items():
        fs = [f for f in _known(facts, d, max_age) if f.company_id == cid and f.fact_type == "capex_guidance"
              and f.value_num is not None and f.unit == "usd" and f.period_end is not None]  # fmt: skip
        if fs:
            last_year = max(f.period_end for f in fs if f.period_end is not None)
            v = _latest([f for f in fs if f.period_end == last_year]).value_num
            if v is not None:
                parts[ticker] = v
    return Panel(parts) if parts else None


def _gw(f: FactLike) -> Decimal | None:
    if f.value_num is None:
        return None
    return {"gw": f.value_num, "mw": f.value_num / 1000}.get(f.unit)


def large_load(facts: Sequence[FactLike], d: date, max_age: int) -> Panel | None:
    by: dict[UUID, list[FactLike]] = {}
    for f in _known(facts, d, max_age):
        if f.fact_type == "utility_load" and _gw(f) is not None:
            by.setdefault(f.company_id, []).append(f)
    parts = {str(cid): v for cid, fs in by.items() if (v := _gw(_latest(fs))) is not None}
    return Panel(parts) if parts else None


def _months(f: FactLike) -> Decimal | None:
    if f.value_num is None:
        return None
    factor = {"months": Decimal(1), "weeks": Decimal(12) / 52, "years": Decimal(12)}.get(f.unit)
    return None if factor is None else f.value_num * factor


def lead_time(facts: Sequence[FactLike], equipment: str, d: date, max_age: int) -> Decimal | None:
    pat = re.compile(rf"^lead_time:.*{re.escape(equipment)}", re.I)
    by: dict[UUID, list[FactLike]] = {}
    for f in _known(facts, d, max_age):
        if f.fact_type == "lead_time" and pat.search(f.subject_key) and _months(f) is not None:
            by.setdefault(f.company_id, []).append(f)
    vals = [m for fs in by.values() if (m := _months(_latest(fs))) is not None]
    return Decimal(str(statistics.median(vals))) if vals else None


def series_at(series: Sequence[tuple[date, Decimal]], d: date) -> Decimal | None:
    """The latest observation on or before d."""
    past = [v for day, v in series if day <= d]
    return past[-1] if past else None
