"""Insider events as a reader sees them (BRIEF §4.6 S7; review F4 on M2).

insider_events keeps every filing as filed, point-in-time: a Form 4/A that restates a Form 4, or a revised Indian
PIT disclosure, is a second row with its own source_url and later filed_at. Deleting the original would rewrite what
was known before the amendment. Readers therefore take, per company, person and trade date, only the trades of the
latest filing known at their cutoff (as_of already hides later ones). Two lots on the same day in one filing both
count.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable
from datetime import date, datetime
from typing import Protocol


class _Event(Protocol):
    @property
    def company_id(self) -> Hashable: ...
    @property
    def person(self) -> str: ...
    @property
    def event_date(self) -> date: ...
    @property
    def filed_at(self) -> datetime: ...
    @property
    def source_url(self) -> str: ...


def latest_versions[E: _Event](events: Iterable[E]) -> list[E]:
    groups: dict[tuple[Hashable, str, date], dict[str, list[E]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        groups[(e.company_id, e.person, e.event_date)][e.source_url].append(e)
    out: list[E] = []
    for by_filing in groups.values():
        latest = max(by_filing.values(), key=lambda evs: (max(x.filed_at for x in evs), evs[0].source_url))
        out += latest
    return sorted(out, key=lambda e: (str(e.company_id), e.event_date, e.person, e.filed_at))
