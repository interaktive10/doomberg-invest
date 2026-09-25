"""Insider events as a reader sees them (BRIEF §4.6 S7; review F4 and R2-F7 on M2).

insider_events keeps every filing as filed, point-in-time: a Form 4/A that restates a Form 4, or a revised Indian
PIT disclosure, is a second row with its own source_url and later filed_at. Deleting the original would rewrite what
was known before the amendment. Readers therefore take, at their cutoff (as_of already hides later filings):

- US: a Form 4/A names the Form 4 it amends by filing date (`amends`). The latest amendment replaces that original
  and any earlier amendment of it, whole, even when it corrects a trade date. Original filings without an amendment
  all count, including two separate same-day filings.
- India: revisions carry no link, so the latest disclosure per company, person and trade date wins.

Two lots on the same day in one filing both count.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")  # EDGAR filing dates are Eastern; Form 4s are accepted until 22:00 ET


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
    @property
    def kind(self) -> str: ...
    @property
    def amends(self) -> date | None: ...


def _group(e: _Event) -> tuple[Hashable, str, str, date]:
    if e.amends is not None:
        return (e.company_id, e.person, "original", e.amends)
    if e.kind.startswith(("promoter_", "pledge_")):
        return (e.company_id, e.person, "trade", e.event_date)
    return (e.company_id, e.person, "original", e.filed_at.astimezone(EASTERN).date())


def latest_versions[E: _Event](events: Iterable[E]) -> list[E]:
    groups: dict[tuple[Hashable, str, str, date], dict[str, list[E]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        groups[_group(e)][e.source_url].append(e)
    out: list[E] = []
    for key, by_filing in groups.items():
        amendments = {u: evs for u, evs in by_filing.items() if evs[0].amends is not None}
        if key[2] == "original" and not amendments:
            out += [e for evs in by_filing.values() for e in evs]  # separate original filings all count
            continue
        pool = amendments or by_filing
        latest = max(pool.values(), key=lambda evs: (max(x.filed_at for x in evs), evs[0].source_url))
        out += latest
    return sorted(out, key=lambda e: (str(e.company_id), e.event_date, e.person, e.filed_at, e.source_url))
