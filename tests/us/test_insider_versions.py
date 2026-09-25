"""Review F4 / R2-F7: a Form 4/A replaces the Form 4 it amends (the latest amendment wins, also when it corrects a
trade date); separate filings and same-day lots in one filing all count; India revisions win per trade date."""

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
    kind: str = "open_market_buy"
    amends: date | None = None


def test_amendment_replaces_the_original_filing() -> None:
    amended = parse_submission((F4 / "0000950170-25-055869.txt").read_text(encoding="utf-8"))  # Solaris 4/A
    assert amended.document_type == "4/A" and amended.accepted_at is not None
    assert amended.original_date == date(2025, 2, 28)  # dateOfOriginalSubmission
    rows = [Ev("SEI", amended.person, t.date, amended.accepted_at, "4a", t.value or D(0), amends=amended.original_date)
            for t in amended.purchases()]  # fmt: skip
    original = [replace(r, filed_at=datetime(2025, 2, 28, 21, tzinfo=UTC), source_url="4", value=r.value + 1,
                        amends=None) for r in rows]  # fmt: skip
    kept = latest_versions([*original, *rows])
    assert [(k.source_url, k.event_date) for k in kept] == [("4a", date(2025, 2, 27)), ("4a", date(2025, 2, 28))]
    assert latest_versions(original) == original  # before the amendment is filed, the original counts


def test_an_amendment_that_corrects_the_trade_date_counts_once() -> None:
    """Review R2-F7: the 4/A moves a $150k lot from 03-03 to 03-04; grouping by trade date counted it twice."""
    original = Ev("X", "DOE JANE", date(2025, 3, 3), datetime(2025, 3, 4, 22, tzinfo=UTC), "form4", D(150000))
    fixed = replace(original, event_date=date(2025, 3, 4), filed_at=datetime(2025, 3, 20, 21, tzinfo=UTC),
                    source_url="form4a", amends=date(2025, 3, 4))  # fmt: skip
    assert latest_versions([original, fixed]) == [fixed]  # after the 4/A's filed_at: one lot, on 03-04
    assert latest_versions([original]) == [original]  # before it (as_of hides the 4/A): the original lot


def test_separate_same_day_filings_and_two_lots_in_one_filing_all_count() -> None:
    t = datetime(2025, 3, 3, 21, tzinfo=UTC)
    lots = [
        Ev("X", "DOE JANE", date(2025, 3, 3), t, "f1", D(100)),
        Ev("X", "DOE JANE", date(2025, 3, 3), t, "f1", D(200)),
    ]
    trust = Ev("X", "DOE JANE", date(2025, 3, 3), t, "f2", D(300))  # a second Form 4 the same day (another account)
    other = Ev("X", "ROE RICHARD", date(2025, 3, 3), t, "f3", D(50))
    assert latest_versions([*lots, trust, other]) == [*lots, trust, other]


def test_india_revision_wins_per_trade_date() -> None:
    first = Ev("Y", "PROMOTER LTD", date(2025, 3, 3), datetime(2025, 3, 5, tzinfo=UTC), "d1", D(10), "promoter_buy")
    revised = replace(first, filed_at=datetime(2025, 3, 9, tzinfo=UTC), source_url="d2", value=D(12))
    assert latest_versions([first, revised]) == [revised]
