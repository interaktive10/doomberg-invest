"""A card's second attempt is a repair (docs/SPEC_ISSUES.md 70): the model gets its failed card and validate.py's errors
as turns after the verbatim P-04 prompt, so a retry no longer repeats the first one's mistakes. A first attempt's
request, and its cassette key, are unchanged."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from pipeline.llm import cassettes, privacy
from pipeline.llm.providers import gemini, openai_compat
from pipeline.llm.providers.base import Request
from pipeline.llm.router import Done
from pipeline.thesis import validate as v
from pipeline.thesis.evidence_pack import CardInput, EvidencePack
from pipeline.thesis.fallback_writer import ATTEMPTS, attempts

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "card"
PACK = json.loads((FIX / "pack.json").read_text(encoding="utf-8"))
GOOD = json.loads((FIX / "good.json").read_text(encoding="utf-8"))
BAD = json.loads((FIX / "bad_number.json").read_text(encoding="utf-8"))


class Seq:
    """P-04 answers in turn (P-05 always supports); records each P-04 input."""

    def __init__(self, *cards: dict[str, Any]) -> None:
        self.cards: list[dict[str, Any]] = list(cards)
        self.seen: list[Any] = []

    def call(self, data: Any) -> Done:
        privacy.check(data)  # the repair rides in the checked input
        if data.prompt_id == "P-05":
            return Done({"supported": True, "unsupported_parts": [], "reason": "stated"}, "fake", "m")
        self.seen.append(data)
        return Done(copy.deepcopy(self.cards.pop(0)), "fake", "m")


def test_the_second_attempt_carries_the_failed_card_and_its_errors() -> None:
    model = EvidencePack.model_validate(PACK)
    r = Seq(BAD, GOOD)
    _, content, res = attempts(r, model, PACK, v.hype_words())  # type: ignore[arg-type]
    assert res is not None and res.ok and ATTEMPTS == 2
    first, second = r.seen
    assert first.follow() == ()
    (role1, previous), (role2, ask) = second.follow()
    assert role1 == "assistant" and json.loads(previous)["summary"] == BAD["summary"]
    assert role2 == "user" and "failed these checks" in ask
    failed = v.validate(v.card_fields(BAD, PACK), PACK, v.hype_words())
    assert failed.errors and all(f"- {e[:400]}" in ask for e in failed.errors[:20])
    assert second.variables() == first.variables()  # the verbatim prompt itself is unchanged


def test_a_repair_turn_reaches_each_provider_and_only_its_cassette_key_changes() -> None:
    req = Request("P-04", "m", "sys", "user", {"type": "object", "properties": {}}, "json", "card", 0.2)
    fixed = replace(req, follow=(("assistant", "{}"), ("user", "fix it")))
    assert openai_compat.body(req)["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert openai_compat.body(fixed)["messages"][2:] == [{"role": "assistant", "content": "{}"},
                                                         {"role": "user", "content": "fix it"}]  # fmt: skip
    assert [c["role"] for c in gemini.body(fixed)["contents"]] == ["user", "model", "user"]
    assert cassettes.request_key("p", req) != cassettes.request_key("p", fixed)
    # a first attempt's key is the one recorded before the repair existed
    doc = {"provider": "p", "model": "m", "prompt_id": "P-04", "system": "sys", "user": "user",
           "schema": req.schema, "mode": "json", "tool_name": "card", "temperature": 0.2}  # fmt: skip
    import hashlib

    want = hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert cassettes.request_key("p", req) == want


def test_a_repair_input_is_bounded() -> None:
    inp = CardInput(EvidencePack.model_validate(PACK)).repair({"summary": "x"}, [f"e{i} " * 200 for i in range(50)])
    ask = inp.follow()[1][1]
    assert ask.count("\n- ") <= 20 and all(len(e) <= 400 for e in inp.errors)


def test_a_repair_reads_the_same_whatever_the_answers_key_order() -> None:
    """A recorded answer comes back key-sorted; the live one in the model's order. The repair turn must not differ,
    or its cassette never replays."""
    inp = CardInput(EvidencePack.model_validate(PACK))
    a = inp.repair({"summary": "s", "facts": []}, ["e"])
    b = inp.repair({"facts": [], "summary": "s"}, ["e"])
    assert a.follow() == b.follow()
