"""M5-04 (and reviewer check d): the router accepts public data only. Objects shaped like the private tables (BRIEF §3
`journal`, `postmortems`) raise PrivacyViolation before any request is built, whether passed directly, wrapped in a
public input, or wrapped in a PublicData subclass defined outside the public modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from pipeline.db.models import Row
from pipeline.india.triage import TriageInput
from pipeline.llm.privacy import PrivacyViolation, PublicData, check
from pipeline.llm.router import Router
from tests.llm.conftest import FakeClock, Scripted, quotas


class JournalEntry(Row):
    """A row of the private `journal` table (BRIEF §3)."""

    thesis_id: str | None = None
    entry_date: date
    action: str
    portfolio_pct: Decimal | None = None
    reason: str


class Postmortem(Row):
    thesis_id: str
    what_happened: str
    lessons: str


JOURNAL = JournalEntry(entry_date=date(2026, 9, 1), action="start_position", portfolio_pct=Decimal("2.5"),
                       reason="private reasoning")  # fmt: skip
POSTMORTEM = Postmortem(thesis_id=str(uuid4()), what_happened="private", lessons="private")


@dataclass(frozen=True)
class Wrapped(PublicData):  # defined outside PUBLIC_MODULES
    text: str


@pytest.fixture
def router(clock: FakeClock) -> tuple[Router, Scripted]:
    gemini = Scripted("gemini")
    return Router({"gemini": gemini}, quotas(["gemini"]), clock), gemini


@pytest.mark.parametrize("private", [JOURNAL, POSTMORTEM], ids=["journal", "postmortem"])
def test_private_rows_raise_before_any_request(router: tuple[Router, Scripted], private: object) -> None:
    r, gemini = router
    with pytest.raises(PrivacyViolation):
        r.call(private)  # type: ignore[arg-type]
    with pytest.raises(PrivacyViolation):
        r.call(TriageInput("Award of Order", private))  # type: ignore[arg-type]
    assert gemini.requests == []


def test_a_public_data_subclass_outside_the_public_modules_is_refused(router: tuple[Router, Scripted]) -> None:
    r, gemini = router
    with pytest.raises(PrivacyViolation, match="tests.llm.test_privacy.Wrapped"):
        r.call(Wrapped("x"))  # type: ignore[arg-type]
    assert gemini.requests == []


def test_nested_values_are_checked() -> None:
    check({"a": [1, "b", date(2026, 1, 1), None, Decimal(1)]})
    with pytest.raises(PrivacyViolation):
        check({"a": [JOURNAL]})
    with pytest.raises(PrivacyViolation):
        check({1: "non-str key"})
    with pytest.raises(PrivacyViolation):
        check(object())


def test_public_inputs_go_through(router: tuple[Router, Scripted]) -> None:
    r, gemini = router
    r.call(TriageInput("Award of Order", "Order for 765 kV substations."))
    assert len(gemini.requests) == 1
