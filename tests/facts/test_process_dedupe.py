"""One sentence about one named partner is one fact (pipeline/facts/process.py one_relationship; 2026-11-02, F-SYN on
DeepSeek read "a multi-year agreement to supply ... to Nimbus Compute" as both a supply_link and a customer_win)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from pipeline.facts.process import one_relationship
from pipeline.facts.verify1 import Candidate

Q = "We entered into a multi-year agreement to supply power transformers and switchgear to Nimbus Compute."


def fact(kind: str, value: Decimal | None = None, partner: str = "Nimbus Compute", quote: str = Q) -> Candidate:
    return Candidate(fact_type=kind, subject="s", subject_key=f"{kind}:nimbus", value_num=value, value_low=None,
                     value_high=None, unit="other", currency=None, scale_word=None, period_label=None,
                     period_start=None, period_end=None, as_of=date(2026, 7, 30), counterparty=partner, location=None,
                     quote=quote, char_start=0, char_end=len(quote), section=None, page=None, xbrl_concept=None,
                     xbrl_check="na", confidence=Decimal("0.9"), verification_status="verified")  # fmt: skip


def test_a_customer_win_read_from_a_supply_link_sentence_is_dropped() -> None:
    link, win = fact("supply_link"), fact("customer_win")
    kept, merged = one_relationship([(link, "m"), (win, "m")])
    assert kept == [(link, "m")] and merged == 1


def test_a_customer_win_with_a_value_or_another_partner_or_sentence_stays() -> None:
    link = fact("supply_link")
    keep = [fact("customer_win", value=Decimal(40_000_000)), fact("customer_win", partner="Orbit Labs"),
            replace(fact("customer_win"), quote="Nimbus Compute signed on as a customer.")]  # fmt: skip
    kept, merged = one_relationship([(link, "m"), *[(k, "m") for k in keep]])
    assert merged == 0 and len(kept) == 4
