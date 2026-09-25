"""Review F4: a Form 4/A restating a Form 4 counts once (the latest filing), same-day lots in one filing both count."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

from pipeline.signals.insiders import latest_versions
from pipeline.us.form4 import parse_submission

F4 = Path(__file__).resolve().parents[2] / "fixtures" / "us" / "form4"


@dataclass(frozen=True)
class Ev:
    company_id: str
    person: str
    event_date: date
    filed_at: datetime
    source_url: str
    value: D


def test_amendment_replaces_the_original_filing() -> None:
    amended = parse_submission((F4 / "0000950170-25-055869.txt").read_text(encoding="utf-8"))  # Solaris 4/A
    assert amended.document_type == "4/A" and amended.accepted_at is not None
    rows = [Ev("SEI", amended.person, t.date, amended.accepted_at, "4a", t.value or D(0)) for t in amended.purchases()]
    original = [replace(r, filed_at=datetime(2025, 3, 3, 21, tzinfo=UTC), source_url="4", value=r.value + 1)
                for r in rows]  # fmt: skip
    kept = latest_versions([*original, *rows])
    assert [(k.source_url, k.event_date) for k in kept] == [("4a", date(2025, 2, 27)), ("4a", date(2025, 2, 28))]
    assert latest_versions(original) == original  # before the amendment is filed, the original counts


def test_two_lots_in_one_filing_both_count() -> None:
    t = datetime(2025, 3, 3, 21, tzinfo=UTC)
    lots = [
        Ev("X", "DOE JANE", date(2025, 3, 3), t, "f1", D(100)),
        Ev("X", "DOE JANE", date(2025, 3, 3), t, "f1", D(200)),
    ]
    other = Ev("X", "ROE RICHARD", date(2025, 3, 3), t, "f2", D(50))
    assert latest_versions([*lots, other]) == [*lots, other]
