"""The thesis queue's order (overhaul PR 5, docs/SPEC_ISSUES.md 35; pipeline/thesis/queue.py order): the shortlist in
rank order, then the open manual research entries, oldest first, within the same 10 packs. tests/db/test_thesis.py
builds the queue from real rows (research entries read oldest first, a filled one no longer queued)."""

from __future__ import annotations

import uuid

from pipeline.thesis import queue


def ids(*ns: int) -> list[uuid.UUID]:
    return [uuid.UUID(f"00000000-0000-4000-8000-{n:012d}") for n in ns]


def test_research_entries_come_after_the_shortlist_oldest_first() -> None:
    assert queue.order(ids(3, 1), ids(7, 5, 6)) == ids(3, 1, 7, 5, 6)


def test_a_research_entry_on_the_shortlist_is_packed_once_in_its_rank() -> None:
    assert queue.order(ids(3, 1), ids(1, 7)) == ids(3, 1, 7)


def test_at_most_10_packs_and_the_shortlist_keeps_its_places() -> None:
    assert queue.MAX_PACKS == 10
    shortlist, research = ids(*range(1, 9)), ids(*range(20, 25))
    assert queue.order(shortlist, research) == ids(*range(1, 9), 20, 21)  # the oldest two fit, the rest wait
    full = ids(*range(1, 11))
    assert queue.order(full, research) == full  # a full shortlist leaves no room this week
    assert queue.order([], research, limit=3) == ids(20, 21, 22)
