"""M6-02: validate.py rejects F-CARD's bad cards (uncited fact, mismatched number, unlabeled inference, invalid kill
criterion, hype word) and accepts the good one; the number, label and kill-criterion rules one by one."""

from __future__ import annotations

import copy
import json
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest

from pipeline.llm.router import Deferred, Done
from pipeline.thesis import validate as v

F = Path(__file__).resolve().parents[2] / "fixtures" / "card"
PACK = json.loads((F / "pack.json").read_text(encoding="utf-8"))
GOOD = json.loads((F / "good.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((F / "expected.json").read_text(encoding="utf-8"))
HYPE = v.hype_words()


def check(card: dict[str, Any], router: Any = None) -> v.Result:
    return v.validate(card, PACK, HYPE, router)


def test_the_good_card_passes() -> None:
    r = check(GOOD)
    assert r.ok and r.errors == []


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_bad_card_is_rejected_for_its_defect(name: str) -> None:
    r = check(json.loads((F / f"{name}.json").read_text(encoding="utf-8")))
    assert not r.ok and len(r.errors) == 1 and EXPECTED[name] in r.errors[0], r.errors


def test_the_fixture_is_the_generators_output() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_card", F / "make_card.py")
    assert spec is not None and spec.loader is not None
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    for name, text in gen.files().items():
        assert (F / name).read_text(encoding="utf-8") == text, name


def test_numbers_are_pack_values_or_deltas_of_cited_values() -> None:
    card = copy.deepcopy(GOOD)
    fact = card["facts"][0]
    fact["text"] = "Revenue was $1.25 billion, up $270 million or 27.6% on $980 million [m:revenue:2026-06-30] " \
                   "[m:revenue:2025-06-30]."  # fmt: skip
    assert check(card).ok  # a difference and a change computed from the two cited values
    fact["text"] = "Revenue was $1.25 billion [m:revenue:2026-06-30]."  # 980 million is no longer cited
    fact["cites"] = ["m:revenue:2026-06-30"]
    assert check(card).ok
    fact["text"] = "Revenue was $1.25 billion, up 27.6% [m:revenue:2026-06-30]."
    assert any("'27.6%'" in e for e in check(card).errors)  # the delta needs both values cited


def test_labels_are_not_numbers() -> None:
    nums = v.sentence_numbers("In FY2026 Q2 the 10-Q (Item 2.02) showed S1 and C2 on 2026-06-30 [m:rpo:2026-06-30].")
    assert nums == []
    assert [p.numeral for p in v.sentence_numbers("one of the two largest orders, $600 million")] == [D(600)]


def test_inferences_and_assumptions_are_labelled_and_numbers_marked() -> None:
    card = copy.deepcopy(GOOD)
    card["assumptions"][0] = "Assumption: backlog converts to revenue within 24 months."
    assert any("'24 months' is not marked (assumed)" in e for e in check(card).errors)
    card = copy.deepcopy(GOOD)
    card["assumptions"][1] = "Margins stay above 15% (assumed)."
    assert any("does not start with 'Assumption:'" in e for e in check(card).errors)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"metric_id": "m:revenue:2026-06-30"}, "is not a kill-criteria metric of the pack"),
        ({"metric_id": "m:free_cash_flow_margin"}, "is not a kill-criteria metric of the pack"),
        ({"threshold": None}, "needs a threshold"),
        ({"operator": "changes"}, "`changes` takes no threshold"),
        ({"threshold": 0.5}, "already met by the pack value"),  # rpo_yoy 0.4483 < 0.5 today
        ({"check_after": "2026-11-14"}, "is not after the next filing window"),
    ],
)
def test_invalid_kill_criteria(change: dict[str, Any], error: str) -> None:
    card = copy.deepcopy(GOOD)
    card["kill_criteria"][0].update(change)
    errors = check(card).errors
    assert any(error in e for e in errors), errors


def test_changes_without_threshold_is_valid() -> None:
    card = copy.deepcopy(GOOD)
    card["kill_criteria"][0].update({"metric_id": "m:signal:S1", "operator": "changes", "threshold": None})
    assert check(card).ok


def test_schema_counts_and_summary_length() -> None:
    card = copy.deepcopy(GOOD)
    card["facts"] = card["facts"][:2]
    assert any(e.startswith("schema: facts") for e in check(card).errors)
    card = copy.deepcopy(GOOD)
    card["summary"] = "word " * 61
    assert any("60 words" in e for e in check(card).errors)
    card = copy.deepcopy(GOOD)
    card["price_target"] = 120
    assert any("price_target" in e for e in check(card).errors)


class FakeRouter:
    def __init__(self, answer: dict[str, Any] | None) -> None:
        self.answer, self.inputs = answer, []

    def call(self, data: Any) -> Done | Deferred:
        self.inputs.append(data)
        return Deferred("every provider is out") if self.answer is None else Done(self.answer, "fake", "m")


def test_p05_checks_sentences_without_numbers() -> None:
    card = copy.deepcopy(GOOD)
    card["facts"][3]["text"] = "A hyperscale cloud provider placed a large multi-year order [f:6f1c2a52-3b1e-4c43-" \
                               "9e59-3d1b1f0a0002]."  # fmt: skip
    ok = FakeRouter({"supported": True, "unsupported_parts": [], "reason": "stated"})
    assert check(card, ok).ok and len(ok.inputs) == 1  # the only fact or why-mispriced sentence without numbers
    assert ok.inputs[0].sentence == "A hyperscale cloud provider placed a large multi-year order."
    assert ok.inputs[0].quotes and "$600 million" in ok.inputs[0].quotes[0]
    no = FakeRouter({"supported": False, "unsupported_parts": ["large"], "reason": "the size is not stated"})
    assert any("P-05 finds it unsupported" in e for e in check(card, no).errors)
    out = FakeRouter(None)
    r = check(card, out)
    assert r.ok and any("not checked" in w for w in r.warnings)
