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


# ---------------------------------------------------------------- M6 review round 1

F_ORDER = "f:6f1c2a52-3b1e-4c43-9e59-3d1b1f0a0002"
REV = "[m:revenue:2026-06-30] [m:revenue:2025-06-30]"


def with_fact(text: str, cites: list[str] | None = None, index: int = 3, section: str = "facts") -> v.Result:
    card = copy.deepcopy(GOOD)
    card[section][index] = {"text": text, "cites": cites if cites is not None else []}
    return check(card)


@pytest.mark.parametrize(
    "text",
    [
        f'Management called demand "unprecedented." A hyperscale cloud provider placed a $600 million multi-year '
        f"order [{F_ORDER}].",
        f"Nimbus will dominate AI servers.A hyperscale cloud provider placed a $600 million multi-year order "
        f"[{F_ORDER}].",
        f"A hyperscale cloud provider placed a $600 million multi-year order [{F_ORDER}]\nNimbus is the only "
        "supplier able to meet this demand",
    ],
    ids=["after-a-quote", "no-space", "line-break"],
)
def test_sentence_variants_without_a_citation_are_rejected(text: str) -> None:
    """M6 review R1-F2: every part of the text is a checked sentence."""
    r = with_fact(text)
    assert any("sentence cites no pack id" in e for e in r.errors), r.errors


@pytest.mark.parametrize(
    "text",
    [
        f"Nimbus Compute Corp. received a $600 million multi-year order from a hyperscale cloud provider [{F_ORDER}].",
        f"A U.S. hyperscale cloud provider placed a $600 million multi-year order [{F_ORDER}].",
        f"A hyperscale cloud provider placed a $600 million multi-year order. [{F_ORDER}]",
    ],
    ids=["corp", "u-s", "citation-after-the-period"],
)
def test_sentence_variants_with_abbreviations_are_accepted(text: str) -> None:
    r = with_fact(text)
    assert r.ok, r.errors


def test_sentences_cover_every_character() -> None:
    text = 'Nimbus Inc. said "demand is strong." It grew.A new order arrived!\nAnd more [m:x]. [f:y]'
    parts = v._sentences(text)
    assert "".join(parts).replace(" ", "") == text.replace(" ", "").replace("\n", "")
    assert parts[0] == 'Nimbus Inc. said "demand is strong."' and parts[-1] == "And more [m:x]. [f:y]"


@pytest.mark.parametrize(
    ("text", "cites", "section", "index"),
    [
        (f"Revenue rose to $1.25 billion from $980 million a year earlier; the company now has 2,000 hyperscale "
         f"customers {REV}.", [], "facts", 0),
        (f"Revenue rose to [$1.95 billion] in the June 2026 quarter from $980 million a year earlier {REV}.", [],
         "facts", 0),
        (f"Revenue rose to $1.25 billion from $980 million a year earlier, up fifty percent {REV}.", [], "facts", 0),
        ("The price implies 42% annual growth, below the 18% the evidence supports [c:C2].", ["c:C2"],
         "why_mispriced", 0),
        ("The price implies 12% annual growth, below the 67% the evidence supports [c:C2].", ["c:C2"],
         "why_mispriced", 0),
        ("The order-book signal S1 fired with strength 0.82; backlog grew 91% [s:S1].", ["s:S1"], "facts", 4),
        ("The order-book signal S1 fired with strength 0.60 [s:S1].", ["s:S1"], "facts", 4),
        ("The price implies -4% annual growth [c:C2].", ["c:C2"], "why_mispriced", 0),
        (f"Revenue fell to $980 million from $1.25 billion a year earlier, down 21.6% {REV}.", [], "facts", 0),
        (f"Revenue fell to $980 million from $1.25 billion a year earlier {REV}.", [], "facts", 0),
    ],
    ids=["thousands-separator-year", "bracketed-figure", "number-word", "cross-input-ratio", "cross-input-ratio-2",
         "input-ratio", "wrong-strength", "sign", "reversed-percent", "reversed-direction"],
)  # fmt: skip
def test_wrong_number_variants_are_rejected(text: str, cites: list[str], section: str, index: int) -> None:
    """M6 review R1-F3: every figure must be a cited value or a delta between two cited periods of one metric, with
    its sign, and "to X from Y" must run from the earlier period to the later one."""
    r = with_fact(text, cites, index, section)
    assert not r.ok, text


def test_percents_are_cited_ratios_not_every_input_combination() -> None:
    """R1-F3: citing only s:S1, a percent passes only when it is one of S1's values x 100 (not 34 of 1..99)."""
    ok = [n for n in range(1, 100) if with_fact(f"Backlog grew {n}% [s:S1].", ["s:S1"], 4).ok]
    assert ok == [17, 28, 45, 82]  # gap 0.1728, g_rev 0.2755, g_ob 0.4483, strength 0.82


def test_natural_phrasing_is_accepted_and_still_checked() -> None:
    """M6 review R1-F8: "rose 27.6% to $1.25 billion" is a change and a level (not a range), and "June 30, 2026" is
    a date; the figures are still checked."""
    good = f"Revenue rose 27.6% to $1.25 billion from $980 million a year earlier {REV}."
    assert with_fact(good, [], 0).ok
    assert with_fact("In the quarter ended June 30, 2026, revenue was $1.25 billion [m:revenue:2026-06-30].", [], 0).ok
    wrong = f"Revenue rose 27.6% to $1.35 billion from $980 million a year earlier {REV}."
    assert any("'1.35 billion'" in e for e in with_fact(wrong, [], 0).errors)


@pytest.mark.parametrize(
    "phrase", ["It can’t lose.", "A multi-bagger in the making.", "A sure-shot idea.", "Headed to the  moon."]
)
def test_hype_variants_are_rejected(phrase: str) -> None:
    """M6 review R1-F11: apostrophes, hyphens and spacing are folded before the hype check."""
    card = copy.deepcopy(GOOD)
    card["summary"] = f"{card['summary']} {phrase}"
    assert any(e.startswith("hype word") for e in check(card).errors), phrase


RPO = "[m:rpo:2026-06-30] [m:rpo:2025-06-30]"
ORDER = f"A hyperscale cloud provider placed a $600 million multi-year order [{F_ORDER}]."


@pytest.mark.parametrize(
    "text",
    [
        f"Nimbus's largest customer is Microsoft Corp. The customer placed a $600 million multi-year order "
        f"[{F_ORDER}].",
        f"Nimbus will dominate the AI server market in the U.S. {ORDER}",
        f"Nimbus's only real rival is Dell Inc. {ORDER}",
        f"Nimbus sells servers, storage, networking, etc. {ORDER}",
        f"Nimbus will dominate AI servers.({ORDER[:-1]}.)",
        f"{ORDER[:-1]}\u2028Nimbus is the only supplier able to meet this demand",
        f"{ORDER[:-1]}\rNimbus is the only supplier able to meet this demand",
    ],
    ids=["corp", "u-s", "inc", "etc", "open-paren", "u2028", "lone-cr"],
)
def test_abbreviation_end_hides_no_uncited_sentence(text: str) -> None:
    """M6 review R2-F1: after Corp., Inc., U.S. or etc. a capital starts a new sentence, and so does "(" or any line
    break, so the uncited claim before it is checked on its own."""
    r = with_fact(text)
    assert any("sentence cites no pack id" in e for e in r.errors), r.errors


@pytest.mark.parametrize(
    "text",
    [
        f"Nimbus Compute Corp. received a $600 million multi-year order from a hyperscale cloud provider [{F_ORDER}].",
        f"A U.S. hyperscale cloud provider placed a $600 million multi-year order [{F_ORDER}].",
        f"Director John A. Smith said a hyperscale cloud provider placed a $600 million multi-year order [{F_ORDER}].",
        f"A hyperscale cloud provider placed a $600 million multi-year order with J.P. Morgan as adviser [{F_ORDER}].",
    ],
    ids=["corp-runs-on", "u-s-runs-on", "initial", "dotted-initials"],
)
def test_abbreviation_end_keeps_names_and_abbreviations_in_one_sentence(text: str) -> None:
    r = with_fact(text)
    assert r.ok, r.errors


@pytest.mark.parametrize(
    "text",
    [
        f"Revenue fell from $1.25 billion to $980 million {REV}.",
        f"Revenue fell from $1.25 billion a year earlier to $980 million {REV}.",
        f"Revenue posted a 27.6% decline to $1.25 billion {REV}.",
        f"Remaining performance obligations reached $4.2 billion, 44.8% lower {RPO}.",
        f"Revenue plunged 27.6% to $1.25 billion from $980 million a year earlier {REV}.",
        f"Revenue slumped 27.6% year over year to $1.25 billion {REV}.",
        f"Revenue doubled to $1.25 billion from $980 million a year earlier {REV}.",
        f"Revenue tripled to $1.25 billion {REV}.",
        f"Revenue halved to $1.25 billion {REV}.",
        f"Revenue rose to $1.25 billion from $980 million, up by half {REV}.",
    ],
    ids=["fell-from-to", "fell-from-a-year-earlier", "decline-after", "lower-after", "plunged", "slumped", "doubled",
         "tripled", "halved", "up-by-half"],
)  # fmt: skip
def test_direction_variants_are_rejected(text: str) -> None:
    """M6 review R2-F2: every figure here is a pack value, but the words give the move the wrong direction or size."""
    r = with_fact(text, [], 0)
    assert not r.ok, text


def test_direction_variants_that_are_true_still_pass() -> None:
    assert with_fact(f"Revenue rose from $980 million a year earlier to $1.25 billion, up 27.6% {REV}.", [], 0).ok
    assert with_fact(f"Remaining performance obligations reached $4.2 billion, 44.8% higher {RPO}.", [], 0).ok
    doubled = v.Candidates(raw=(), differences=(), changes=(D("1.01"),), ratios=(D("2.01"),))
    assert v.multiplier_errors("Backlog doubled.", doubled) == []
    assert v.multiplier_errors("Backlog more than doubled.", doubled) == []
    assert v.multiplier_errors("Backlog nearly doubled.", doubled) != []  # 2.01 is not "nearly" 2


@pytest.mark.parametrize(
    ("text", "cites"),
    [
        (f"In Q2 45% of orders came from hyperscalers [{F_ORDER}].", []),
        (f"In H1 40% of orders came from hyperscalers [{F_ORDER}].", []),
        (f"The order is worth Rs50 crore [{F_ORDER}].", []),
        (f"The company now has 2000 hyperscale customers {REV}.", []),
        (f"A hyperscale cloud provider placed a $600 million multi-year order, the largest of its 1995 orders "
         f"[{F_ORDER}].", []),
    ],
    ids=["q2", "h1", "rs50", "2000-customers", "1995-orders"],
)  # fmt: skip
def test_masked_figures_are_checked(text: str, cites: list[str]) -> None:
    """M6 review R2-F3: a label doesn't take the figure after it, signal names are capitals, and a four-digit number
    is a year only in a year's context."""
    r = with_fact(text, cites)
    assert any("matches no cited pack value" in e for e in r.errors), r.errors


@pytest.mark.parametrize(
    "text", ["In Q2 2026", "In Q2'26", "In FY2026", "In FY 2026", "Signal S1 and context C2", "in 2026",
             "on June 30, 2026", "2026 revenue", "since 2019,", "Q2FY26"],
)  # fmt: skip
def test_masked_figures_labels_still_read_as_labels(text: str) -> None:
    assert v.sentence_numbers(text, (1996, 2041)) == [], text


@pytest.mark.parametrize(
    ("good", "bad"),
    [
        ("Revenue was $1.25 billion for the three months ended June 30, 2026 [m:revenue:2026-06-30].", "$1.35 billion"),
        ("Revenue was $1.25 billion in the three months to June [m:revenue:2026-06-30].", "$1.35 billion"),
        ("Revenue for the quarter ended June 30 was $1.25 billion [m:revenue:2026-06-30].", "$1.35 billion"),
        ("Revenue for the 12 months ended June 30, 2026 grew 24.1% [m:revenue_ttm_yoy].", "34.1%"),
    ],
    ids=["three-months-ended", "three-months-to", "month-day", "twelve-months"],
)
def test_period_phrasing_is_a_label(good: str, bad: str) -> None:
    """M6 review R2-F4: how 10-Qs name their periods is a label, and the figures stay checked."""
    assert with_fact(good, [], 0).ok, with_fact(good, [], 0).errors
    wrong = good.replace("$1.25 billion", bad) if bad.startswith("$") else good.replace("24.1%", bad)
    assert any(repr(bad.lstrip("$")) in e for e in with_fact(wrong, [], 0).errors)
