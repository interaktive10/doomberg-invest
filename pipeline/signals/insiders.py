"""Insider events as a reader sees them (BRIEF §4.6 S7; review F4 and R2-F7 on M2).

insider_events keeps every filing as filed, point-in-time: a Form 4/A that restates a Form 4, or a revised Indian
PIT disclosure, is a second row with its own source_url and later filed_at. Deleting the original would rewrite what
was known before the amendment. Readers therefore take, at their cutoff (as_of already hides later filings):

- US: a Form 4/A names the Form 4 it amends by filing date only (`amends`). It replaces, whole, the original filed
  that day that shares a trade date with it; when none does, the only original of that day (a corrected trade date)
  or the one nearest in trade date. The latest amendment of an original wins over earlier ones. Every other original
  counts, including the same insider's other same-day filings (review R3-F2).
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


def _amended[E: _Event](amendment: list[E], originals: dict[str, list[E]]) -> list[str]:
    """The same-day originals a Form 4/A replaces: those sharing a trade date with it; else the only one (a corrected
    trade date); else the nearest in trade date."""
    dates = {e.event_date for e in amendment}
    shared = [u for u, evs in originals.items() if dates & {e.event_date for e in evs}]
    if shared or len(originals) <= 1:
        return shared or list(originals)

    def gap(evs: list[E]) -> int:
        return min(abs((e.event_date - d).days) for e in evs for d in dates)

    nearest = min(gap(evs) for evs in originals.values())
    return [u for u, evs in originals.items() if gap(evs) == nearest]


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
        originals: dict[str, list[E]] = {u: evs for u, evs in by_filing.items() if u not in amendments}
        if key[2] == "trade" or not originals:
            pool = amendments or by_filing
            latest = max(pool.values(), key=lambda evs: (max(x.filed_at for x in evs), evs[0].source_url))
            out += latest  # the latest filing (or amendment) wins
            continue
        winner: dict[str, str] = {}  # original -> the latest amendment replacing it
        for u, evs in sorted(amendments.items(), key=lambda kv: (max(x.filed_at for x in kv[1]), kv[0])):
            for o in _amended(evs, originals):
                winner[o] = u
        out += [e for u, evs in originals.items() if u not in winner for e in evs]
        out += [e for u in sorted(set(winner.values())) for e in amendments[u]]
    return sorted(out, key=lambda e: (str(e.company_id), e.event_date, e.person, e.filed_at, e.source_url))
