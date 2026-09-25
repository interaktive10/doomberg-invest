"""M5-04 (and reviewer check d): the router accepts public data only. Objects shaped like the private tables (BRIEF §3
`journal`, `postmortems`) raise PrivacyViolation before any request is built, whether passed directly, wrapped in a
public input, or wrapped in a PublicData subclass defined outside the public modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
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


# ---------------------------------------------------------------- M5 review R1-F6: rows as the driver returns them

JOURNAL_ROW = {"id": uuid4(), "thesis_id": uuid4(), "entry_date": date(2026, 9, 1), "action": "start_position",
               "portfolio_pct": Decimal("2.5"), "reason": "private reasoning"}  # fmt: skip
POSTMORTEM_ROW = {"thesis_id": uuid4(), "what_happened": "private", "thesis_right": False, "lessons": "private"}
ROWS = {
    "journal dict_row": JOURNAL_ROW,
    "journal tuple": tuple(JOURNAL_ROW.values()),
    "journal str dict": {k: str(v) for k, v in JOURNAL_ROW.items()},
    "postmortem dict_row": POSTMORTEM_ROW,
    "postmortem tuple": tuple(POSTMORTEM_ROW.values()),
}


def wrappers(row: object) -> list[object]:
    """The row passed directly and nested in every PromptInput of the public modules."""
    from pipeline.capex.membership import CrossBorderInput
    from pipeline.facts.entities import EntityInput
    from pipeline.facts.extract import ExtractInput
    from pipeline.facts.risk_diff import RiskTagInput

    return [
        row,
        TriageInput("Award of Order", row),  # type: ignore[arg-type]
        ExtractInput("n", "T", "0630", "10-Q", "t", "2026-09-01", "mdna", 0, 10, row),  # type: ignore[arg-type]
        EntityInput((row,), ()),  # type: ignore[arg-type]
        EntityInput(("Acme",), (("e1", row),)),  # type: ignore[arg-type]
        RiskTagInput((("p0", row),)),  # type: ignore[arg-type]
        CrossBorderInput("n", "SYM", ("grid",), row),  # type: ignore[arg-type]
        CrossBorderInput("n", "SYM", (row,), "text"),  # type: ignore[arg-type]
    ]


@pytest.mark.parametrize("name", list(ROWS))
def test_driver_rows_raise_directly_or_nested(router: tuple[Router, Scripted], name: str) -> None:
    r, gemini = router
    for value in wrappers(ROWS[name]):
        with pytest.raises(PrivacyViolation):
            r.call(value)  # type: ignore[arg-type]
    assert gemini.requests == []


def test_fields_are_checked_against_their_annotations() -> None:
    from pipeline.facts.entities import EntityInput

    check(EntityInput(("Acme Corp",), (("e1", "Acme Corporation"),)))
    with pytest.raises(PrivacyViolation, match=r"names\[0\]"):
        check(EntityInput((1,), ()))  # type: ignore[arg-type]
    with pytest.raises(PrivacyViolation, match=r"candidates\[0\]"):
        check(EntityInput(("Acme",), (("e1", "a", "extra"),)))  # type: ignore[arg-type]


def test_public_modules_never_name_the_private_tables() -> None:
    """The static half for every public module (the guard's privacy rule covers pipeline/llm and the evidence pack):
    no module whose classes may reach the router mentions the private tables or their columns."""
    import re
    from pathlib import Path

    from pipeline.llm.privacy import PUBLIC_MODULES

    root = Path(__file__).resolve().parents[2]
    words = re.compile(r"\b(journal|postmortems?|portfolio_pct)\b", re.I)
    found = []
    for mod in PUBLIC_MODULES:
        base = root / Path(*mod.split("."))
        files = sorted(base.rglob("*.py")) if base.is_dir() else [base.with_suffix(".py")]
        for f in files:
            if f.exists():
                found += [f"{f.relative_to(root)}:{i}" for i, line in enumerate(f.read_text().splitlines(), 1)
                          if words.search(line)]  # fmt: skip
    assert found == []


# ---------------------------------------------------------------- pydantic models (M6: the evidence pack)


def _pack() -> Any:
    import json
    from pathlib import Path

    from pipeline.thesis.evidence_pack import EvidencePack

    doc = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "card" / "pack.json").read_text("utf-8"))
    return EvidencePack.model_validate(doc)


def test_pydantic_private_model_in_a_card_input_is_refused(router: tuple[Router, Scripted]) -> None:
    """M6 review R2-F6: a CardInput whose pack is a private pydantic model (not the public EvidencePack) raises."""
    from pipeline.thesis.evidence_pack import CardInput

    r, gemini = router
    with pytest.raises(PrivacyViolation):
        r.call(CardInput(JOURNAL))  # type: ignore[arg-type]
    assert gemini.requests == []


def test_pydantic_pack_subclass_outside_the_public_modules_is_refused(router: tuple[Router, Scripted]) -> None:
    """An EvidencePack subclass defined here (not in a public module) with a journal field raises."""
    from pipeline.thesis.evidence_pack import CardInput, EvidencePack

    class LeakyPack(EvidencePack):
        journal: str = "private reasoning"

    r, gemini = router
    leaky = LeakyPack.model_validate(_pack().model_dump())
    with pytest.raises(PrivacyViolation):
        r.call(CardInput(leaky))
    assert gemini.requests == []


def test_pydantic_pack_with_a_journal_row_in_signal_inputs_is_refused(router: tuple[Router, Scripted]) -> None:
    """A pack whose signal `inputs` (dict[str, Any]) hold a journal row raises: Any is checked all the way down."""
    from pipeline.thesis.evidence_pack import CardInput

    pack = _pack()
    signal = pack.signals[0].model_copy(update={"inputs": {**pack.signals[0].inputs, "row": JOURNAL}})
    leaky = pack.model_copy(update={"signals": [signal, *pack.signals[1:]]})
    r, gemini = router
    with pytest.raises(PrivacyViolation):
        r.call(CardInput(leaky))
    assert gemini.requests == []
    check(CardInput(pack))  # the pack itself is public data
