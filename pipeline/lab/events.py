"""Signal events (BRIEF §4.10.2): the first fire of each signal per company within a rolling 12 months.

A company-month where the signal fires is an event unless the same signal had an event for that company in the
previous `window` months; a signal that keeps firing therefore gives one event a year, not one a month.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pipeline.lab.panel import PanelRow
from pipeline.lab.prices import add_months


@dataclass(frozen=True)
class Event:
    signal_id: str
    company_id: UUID
    month_end: date
    excess: dict[int, float]  # horizon -> excess forward return (only horizons with a later close)


def signal_ids(rows: Iterable[PanelRow]) -> list[str]:
    ids: set[str] = set()
    for r in rows:
        ids.update(r.fired)
    return sorted(ids, key=lambda s: (s[0], int(s[1:]) if s[1:].isdigit() else 0, s))


def events(rows: Sequence[PanelRow], window_months: int = 12, signals: Sequence[str] | None = None) -> list[Event]:
    out: list[Event] = []
    last: dict[tuple[str, UUID], date] = {}
    ids = list(signals) if signals is not None else signal_ids(rows)
    for r in sorted(rows, key=lambda r: (r.month_end, str(r.company_id))):
        for sid in ids:
            if not r.fired.get(sid):
                continue
            prev = last.get((sid, r.company_id))
            if prev is not None and add_months(prev, window_months) > r.month_end:
                continue
            last[(sid, r.company_id)] = r.month_end
            out.append(Event(sid, r.company_id, r.month_end, dict(r.excess)))
    return out
