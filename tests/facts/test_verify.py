"""Verify-1 (Appendix F.5), P-01 parsing, subject keys and fiscal periods."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from typing import Any

import pytest

from pipeline.facts import keys
from pipeline.facts.chunk import Chunk
from pipeline.facts.extract import Proposed, parse
from pipeline.facts.periods import period_slug, resolve
from pipeline.facts.verify1 import Candidate, DocContext, Rejected, verify

TEXT = ("MD&A\n\nWe expect capital expenditures of approximately $80 billion in fiscal 2027.\n\n"
        "Lead times for large power transformers extended to 130 weeks.\n\n"
        "Capital expenditures were $19.2 billion in the first quarter of fiscal 2027.\n\n"
        "The company received an order worth Rs 450 crore.\n\n"
        "Diluted earnings per share were $1.87.")  # fmt: skip
CHUNK = Chunk(TEXT, 0, "mdna")
DOC = DocContext("10-Q", date(2026, 10, 28), "0630", TEXT)


def prop(**kw: Any) -> Proposed:
    base: dict[str, Any] = dict(
        fact_type="capex_guidance", subject="capital expenditures", subject_key="capex_guidance:fy2027",
        value=D(80), value_low=None, value_high=None, unit="usd", currency="USD", scale_word="billion",
        period_label="fiscal 2027", as_of=None, counterparty=None, location=None, withdrawn=False,
        quote="We expect capital expenditures of approximately $80 billion in fiscal 2027.", confidence=D("0.9"),
    )  # fmt: skip
    return Proposed(**{**base, **kw})


def ok(r: Candidate | Rejected | None) -> Candidate:
    assert isinstance(r, Candidate), r
    return r


def test_a_correct_fact_is_verified_with_values_from_the_quote() -> None:
    c = ok(verify(prop(), CHUNK, DOC))
    assert c.verification_status == "verified" and c.value_num == D(80) * 10**9
    assert c.subject_key == "capex_guidance:FY2027" and (c.period_start, c.period_end) == (
        date(2026, 7, 1),
        date(2027, 6, 30),
    )
    assert TEXT[c.char_start : c.char_end] == c.quote and c.as_of == date(2026, 10, 28)


@pytest.mark.parametrize(
    ("change", "check"),
    [
        ({"quote": "Capex will roughly double next year."}, "V1-QUOTE"),
        ({"value": D(85)}, "V1-NUM"),
        ({"unit": "mw"}, "V1-UNIT"),
        ({"subject": "share repurchase program"}, "V1-TYPE"),
        ({"fact_type": "capex_reported", "subject": "diluted EPS", "value": D("1.87"), "scale_word": None,
          "quote": "Diluted earnings per share were $1.87."}, "V1-TYPE"),
    ],
)  # fmt: skip
def test_failures_are_not_stored(change: dict[str, Any], check: str) -> None:
    r = verify(prop(**change), CHUNK, DOC)
    assert isinstance(r, Rejected) and r.check == check


@pytest.mark.parametrize(
    ("change", "note"),
    [
        ({"confidence": D("0.6")}, "confidence"),
        ({"period_label": "the plan period"}, "period"),
        ({"period_label": "fiscal 2026"}, "period"),  # guidance for a year that ended before publication
        ({"subject_key": "capex_plan:big"}, "period"),  # no period: a capex fact needs one (and the key is rebuilt)
        ({"fact_type": "order_win", "subject_key": "order_win:india_order", "value": D(450), "scale_word": None,
          "currency": "INR", "period_label": None, "quote": "The company received an order worth Rs 450 crore."},
         "currency"),
    ],
)  # fmt: skip
def test_review_cases_are_stored_as_needs_review(change: dict[str, Any], note: str) -> None:
    if change.get("subject_key") == "capex_plan:big":
        change = {**change, "period_label": None}
    c = ok(verify(prop(**change), CHUNK, DOC))
    assert c.verification_status == "needs_review" and note in c.verification_notes


def test_unknown_key_becomes_other_and_goes_to_review() -> None:
    p = prop(fact_type="lead_time", subject="transformer lead time", subject_key="leadtime:transformers",
             value=D(130), unit="weeks", scale_word=None, currency=None, period_label=None,
             quote="Lead times for large power transformers extended to 130 weeks.")  # fmt: skip
    c = ok(verify(p, CHUNK, DOC))
    assert c.subject_key == "other:transformers" and c.verification_status == "needs_review"


def test_xbrl_check_and_duplicates() -> None:
    q = "Capital expenditures were $19.2 billion in the first quarter of fiscal 2027."
    p = prop(fact_type="capex_reported", value=D("19.2"), period_label="first quarter of fiscal 2027", quote=q)
    good = ok(verify(p, CHUNK, DOC, xbrl=lambda concept, end, months: D("19.25") * 10**9))
    assert good.xbrl_check == "match" and good.subject_key == "capex_reported:Q1FY2027"
    bad = ok(verify(p, CHUNK, DOC, xbrl=lambda concept, end, months: D(21) * 10**9))
    assert bad.xbrl_check == "mismatch" and bad.verification_status == "needs_review"
    seen: set[tuple[object, ...]] = set()
    assert verify(p, CHUNK, DOC, seen=seen) is not None and verify(p, CHUNK, DOC, seen=seen) is None  # V1-DUP


def test_p01_answers_are_checked_item_by_item() -> None:
    good = {"fact_type": "backlog", "subject": "backlog", "subject_key": "backlog:total", "value": 12.5,
            "value_low": None, "value_high": None, "unit": "usd", "currency": "USD", "scale_word": "billion",
            "period_label": None, "as_of": "2026-06-30", "counterparty": None, "location": None, "withdrawn": False,
            "quote": "Total backlog reached $12.5 billion.", "confidence": 0.95}  # fmt: skip
    facts, rejects = parse({"facts": [good, {**good, "fact_type": "stock_tip"}, {**good, "value": "12,5"},
                                      {**good, "confidence": 1.4}, {**good, "quote": ""}, "junk"]})  # fmt: skip
    assert len(facts) == 1 and facts[0].as_of == date(2026, 6, 30) and facts[0].value == D("12.5")
    assert len(rejects) == 5
    assert parse({"not_facts": []}) == ([], ["answer has no facts list"])


def test_subject_keys_follow_the_vocabulary() -> None:
    assert keys.check("backlog", "backlog:Data Center", "x") == ("backlog:data_center", True)
    assert keys.check("governance_flag", "governance:material_weakness:removed", "x")[1]
    assert keys.check("governance_flag", "governance:material_weakness", "x")[1] is False
    assert keys.check("backlog", "rpo:total", "Backlog")[0] == "other:total"  # a key of another type
    assert keys.check("capex_guidance", "capex_guidance:whatever", "x", "FY2027") == ("capex_guidance:FY2027", True)


@pytest.mark.parametrize(
    ("label", "fye", "expected"),
    [
        ("FY2027", "0630", (date(2026, 7, 1), date(2027, 6, 30), "FY2027")),
        ("second quarter of fiscal 2026", "0630", (date(2025, 10, 1), date(2025, 12, 31), "Q2FY2026")),
        ("3Q26", "1231", (date(2026, 7, 1), date(2026, 9, 30), "Q3FY2026")),
        ("H1 FY27", "0331", (date(2026, 4, 1), date(2026, 9, 30), "H1FY2027")),
        ("fiscal 2027", "0126", (date(2026, 1, 27), date(2027, 1, 26), "FY2027")),
        ("calendar 2026", "0630", (date(2026, 1, 1), date(2026, 12, 31), "20260101-20261231")),
        ("2026", None, (date(2026, 1, 1), date(2026, 12, 31), "FY2026")),
    ],
)
def test_periods(label: str, fye: str | None, expected: tuple[date, date, str]) -> None:
    p = resolve(label, fye)
    assert p is not None and (p.start, p.end, period_slug(p, fye)) == expected


def test_unresolvable_periods() -> None:
    assert resolve("the plan period", "1231") is None and resolve(None, "1231") is None
    nxt = resolve("the next 12 months", "1231", date(2026, 6, 30))
    assert nxt is not None and nxt.end == date(2027, 6, 30)
