"""The text family's readers of governance and customer facts (docs/SPEC_ISSUES.md 58): S9 counts a new customer only
when it is named, and a governance removal; R3 (hard) fires on a material weakness or going-concern doubt that
P-01 now reads in Controls and Procedures; the subject-key vocabulary carries exactly the topics both read."""

from __future__ import annotations

from datetime import date

import yaml

from pipeline.facts import keys
from pipeline.settings import REPO_ROOT
from pipeline.signals import redflags, s09_text
from pipeline.signals.base import Ctx, Fact
from pipeline.signals.series import Series

WEEK = date(2026, 10, 30)
SIGNALS = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
FLAGS = yaml.safe_load((REPO_ROOT / "config" / "redflags.yaml").read_text(encoding="utf-8"))


def ctx(*facts: Fact) -> Ctx:
    return Ctx("c1", "us", WEEK, Series([], "us"), SIGNALS, facts=facts)


def test_s9_counts_a_new_customer_only_when_it_is_named() -> None:
    """BRIEF §1.9: customer_win is "a new named customer or program"; "we added new customers" says nothing S9 can
    stand on, and one fact is 20 Evidence points (docs/SPEC_ISSUES.md 58)."""
    unnamed = Fact("customer_win", "customer_win:new_customers", date(2026, 8, 5))
    named = Fact("customer_win", "customer_win:acme_program", date(2026, 8, 5), counterparty="Acme Corp")
    assert s09_text.compute(ctx(unnamed)).fired is False
    r = s09_text.compute(ctx(unnamed, named))
    assert r.fired and r.inputs["facts"] == ["customer_win:customer_win:acme_program"]
    # an order, a price increase and a new segment count as stated; capacity with a counterparty or a commitment
    plain = [Fact(t, f"{t}:x", date(2026, 8, 5)) for t in ("order_win", "price_increase", "new_segment")]
    assert s09_text.compute(ctx(*plain)).inputs["count"] == 3
    day = date(2026, 8, 5)
    capacity = [Fact("capacity_addition", "capacity:mw:a", day),
                Fact("capacity_addition", "capacity:mw:b", day, counterparty="Utility Co"),
                Fact("capacity_addition", "capacity:mw:c", day, subject="committed expansion")]  # fmt: skip
    assert s09_text.compute(ctx(*capacity)).inputs["count"] == 2


def test_s9_counts_a_governance_removal_and_r3_fires_on_an_addition() -> None:
    """A remediated material weakness is S9 evidence; one reported (now read in a 10-Q's Item 4) is R3's hard flag."""
    removed = Fact("governance_flag", "governance:material_weakness:removed", date(2026, 8, 4))
    added = Fact("governance_flag", "governance:material_weakness:added", date(2026, 8, 4))
    doubt = Fact("governance_flag", "governance:going_concern:added", date(2026, 5, 12))
    assert s09_text.compute(ctx(removed)).fired and not s09_text.compute(ctx(added)).fired
    r3 = redflags.r3(ctx(added, doubt), FLAGS["R3"])
    assert r3.status == "fired" and r3.hard
    assert r3.inputs["text"] == ["governance:going_concern:added", "governance:material_weakness:added"]
    assert redflags.r3(ctx(removed), FLAGS["R3"]).status == "clear"


def test_the_governance_keys_are_the_topics_r3_and_s9_read() -> None:
    """config/subject_keys.yaml names each governance topic (P-01 sees the vocabulary): R3's text topics have an
    `:added` key and a `:removed` one, so the model can't invent a topic R3 never reads; any other is other:<slug>
    and needs_review."""
    for topic in FLAGS["R3"]["text_types"]:
        assert keys.check("governance_flag", f"governance:{topic}:added", "x") == (f"governance:{topic}:added", True)
        assert keys.check("governance_flag", f"governance:{topic}:removed", "x")[1]
    assert keys.check("governance_flag", "governance:auditor_change:added", "x")[1]
    assert keys.check("governance_flag", "governance:auditor_resignation:added", "x")[1] is False
    assert keys.check("governance_flag", "governance:material-weakness:added", "x")[1] is False
