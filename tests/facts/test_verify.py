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


DISTRACTORS = ("Our stock price rose 23% during the quarter, and two analysts upgraded their ratings to buy.\n\n"
               "Diluted earnings per share were $1.87, up 14% from a year ago.\n\n"
               "The Board authorized a new share repurchase program of up to $2.0 billion.")  # fmt: skip


@pytest.mark.parametrize(
    "change",
    [
        {"fact_type": "price_increase", "subject": "price increase", "subject_key": "price_increase:quarter",
         "value": D(23), "unit": "percent", "currency": None, "scale_word": None, "period_label": None,
         "quote": "Our stock price rose 23% during the quarter"},
        {"fact_type": "price_increase", "subject": "earnings increase", "subject_key": "price_increase:year",
         "value": D(14), "unit": "percent", "currency": None, "scale_word": None, "period_label": None,
         "quote": "Diluted earnings per share were $1.87, up 14% from a year ago."},
        {"fact_type": "commitment_purchase", "subject": "purchase commitment",
         "subject_key": "purchase_obligations:total", "value": D("2.0"), "unit": "usd", "currency": "USD",
         "scale_word": "billion", "period_label": None,
         "quote": "The Board authorized a new share repurchase program of up to $2.0 billion."},
    ],
)  # fmt: skip
def test_price_topics_in_the_quote_are_rejected_whatever_the_labels(change: dict[str, Any]) -> None:
    """M5 review R1-F1: F-SYN's distractors labelled with a subject and key that don't name the topic (a stock-price
    move, EPS, a buyback) are rejected from the quote itself, not trusted from the model's labels."""
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", DISTRACTORS)
    r = verify(prop(**change), Chunk(DISTRACTORS, 0, "mdna"), doc)
    assert isinstance(r, Rejected) and r.check == "V1-TYPE", r


@pytest.mark.parametrize(
    ("label", "fye", "expected"),
    [
        ("FY2025-26", "0331", (date(2025, 4, 1), date(2026, 3, 31))),  # India names the year it ends in
        ("FY 2025\u201326", "0331", (date(2025, 4, 1), date(2026, 3, 31))),
        ("Q1 FY2025-26", "0331", (date(2025, 4, 1), date(2025, 6, 30))),
        ("FY26", "0331", (date(2025, 4, 1), date(2026, 3, 31))),
        ("1H FY26", "0331", (date(2025, 4, 1), date(2025, 9, 30))),
        ("2H FY26", "0331", (date(2025, 10, 1), date(2026, 3, 31))),
        ("three months ended June 30, 2026", "1231", (date(2026, 4, 1), date(2026, 6, 30))),
        ("six months ended Sept. 30, 2025", "0331", (date(2025, 4, 1), date(2025, 9, 30))),
        ("year ended December 31, 2025", "1231", (date(2025, 1, 1), date(2025, 12, 31))),
        ("quarter ended 2026-06-30", "1231", (date(2026, 4, 1), date(2026, 6, 30))),
        ("as of June 30, 2026", "1231", (date(2026, 6, 30), date(2026, 6, 30))),  # a point in time
        ("nine months ended September 27, 2025", "0927", (date(2024, 12, 28), date(2025, 9, 27))),  # 52/53 weeks
    ],
)
def test_period_labels_india_halves_and_dates(label: str, fye: str, expected: tuple[date, date]) -> None:
    """M5 review R1-F4: Indian year ranges, "1H", and the SEC's date labels resolve to the right period."""
    p = resolve(label, fye)
    assert p is not None and (p.start, p.end) == expected, (label, p)


def test_a_unit_without_a_number_and_an_implausible_period() -> None:
    """M5 review R1-F9: a fact with no value in the quote keeps no unit ("other"), and a period ending more than
    10 years from the document goes to review."""
    text = "Backlog reached a record.\n\nWe expect capital expenditures of about $2 billion in fiscal 2090."
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", text)
    none = ok(verify(prop(fact_type="backlog", subject="backlog", subject_key="backlog:total", value=None,
                          unit="mw", currency=None, scale_word=None, period_label=None,
                          quote="Backlog reached a record."), Chunk(text, 0, None), doc))  # fmt: skip
    assert none.unit == "other" and none.value_num is None
    far = ok(verify(prop(value=D(2), period_label="fiscal 2090", subject_key="capex_guidance:fy2090",
                         quote="We expect capital expenditures of about $2 billion in fiscal 2090."),
                    Chunk(text, 0, None), doc))  # fmt: skip
    assert far.verification_status == "needs_review" and "more than 10 years" in far.verification_notes["period"]


def test_grounding_keeps_percent_signs() -> None:
    """M5 review R1-F10: % is a unit, so "35%" never grounds to "35"."""
    from pipeline.facts.ground import ground

    assert ground("Exports were 35% of revenue", "Exports were 35 of revenue") is None
    assert ground("Exports were 35 % of revenue", "Exports were 35% of revenue") == (0, 27)


MORE_PRICE = "Our common stock is up 23% this year.\n\nTotal shareholder return was 23% for the year."


@pytest.mark.parametrize(
    "change",
    [
        {"fact_type": "price_increase", "subject": "price increase", "subject_key": "price_increase:quarter",
         "value": D(23), "unit": "percent", "currency": None, "scale_word": None, "period_label": None,
         "quote": "rose 23% during the quarter"},
        {"fact_type": "price_increase", "subject": "increase", "subject_key": "price_increase:year",
         "value": D(14), "unit": "percent", "currency": None, "scale_word": None, "period_label": None,
         "quote": "up 14% from a year ago"},
        {"fact_type": "commitment_purchase", "subject": "purchase commitment",
         "subject_key": "purchase_obligations:total", "value": D("2.0"), "unit": "usd", "currency": "USD",
         "scale_word": "billion", "period_label": None, "quote": "up to $2.0 billion"},
    ],
    ids=["stock-price-part", "eps-part", "buyback-part"],
)  # fmt: skip
def test_a_partial_quote_is_read_in_its_sentence(change: dict[str, Any]) -> None:
    """M5 review R2-F1: the quote's span is the model's choice too, so V1-TYPE reads the whole sentence around it in
    the canonical text."""
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", DISTRACTORS)
    r = verify(prop(**change), Chunk(DISTRACTORS, 0, "mdna"), doc)
    assert isinstance(r, Rejected) and r.check == "V1-TYPE", r


@pytest.mark.parametrize("quote", ["Our common stock is up 23% this year.",
                                   "Total shareholder return was 23% for the year."])  # fmt: skip
def test_other_share_price_phrasings_are_rejected(quote: str) -> None:
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", MORE_PRICE)
    r = verify(prop(fact_type="price_increase", subject="price increase", subject_key="price_increase:year",
                    value=D(23), unit="percent", currency=None, scale_word=None, period_label=None, quote=quote),
               Chunk(MORE_PRICE, 0, "mdna"), doc)  # fmt: skip
    assert isinstance(r, Rejected) and r.check == "V1-TYPE", r


@pytest.mark.parametrize(
    "change",
    [
        {"fact_type": "capacity_addition", "subject": "transformer capacity", "subject_key": "capacity_addition:mw",
         "value": D(500), "unit": "mw", "currency": None, "scale_word": None, "period_label": None,
         "quote": "We upgraded our Chennai plant, adding 500 MW of transformer capacity."},
        {"quote": "In fiscal 2027 we expect capital expenditures of about $80 billion, while continuing to pay "
                  "dividends."},
        {"fact_type": "backlog", "subject": "backlog", "subject_key": "backlog:total", "value": D("13.2"),
         "period_label": None, "quote": "Backlog was $13.2 billion, ahead of what analysts had modeled."},
    ],
    ids=["upgraded-plant", "dividends-later", "analysts-modeled"],
)  # fmt: skip
def test_business_facts_near_price_words_are_kept(change: dict[str, Any]) -> None:
    """M5 review R2-F2: a capex, capacity or backlog figure is stored though its sentence mentions an upgrade,
    dividends or analysts elsewhere."""
    text = str(change["quote"])
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", text)
    r = verify(prop(**change), Chunk(text, 0, "mdna"), doc)
    assert isinstance(r, Candidate), r


@pytest.mark.parametrize("label", ["fiscal 2026-2028", "FY2026-2030", "CY2026-27"])
def test_a_multi_year_range_is_no_single_period(label: str) -> None:
    """M5 review R2-F5: a multi-year plan's label resolves to no period (the fact goes to review), while an Indian
    fiscal year written as a range still resolves."""
    assert resolve(label, "1231") is None
    fy = resolve("FY2025-26", "0331")
    assert fy is not None and (fy.start, fy.end) == (date(2025, 4, 1), date(2026, 3, 31))


RUPEES = ("The company received an order worth Rs 450 crore from a US data center developer.\n\n"
          "Arvl won an order of ₹371 crore.")  # fmt: skip


@pytest.mark.parametrize("currency", [None, "USD"])
@pytest.mark.parametrize("unit", ["usd", "other"])
@pytest.mark.parametrize(
    ("quote", "value"),
    [("The company received an order worth Rs 450 crore", D(450)), ("Arvl won an order of ₹371 crore", D(371))],
    ids=["rs", "rupee-sign"],
)
def test_a_rupee_amount_goes_to_review_whatever_the_model_says(quote: str, value: D, unit: str,
                                                               currency: str | None) -> None:  # fmt: skip
    """M5 review R3-F1: the quote's own currency decides; a null or "USD" answer can't make rupees dollars."""
    doc = DocContext("press_release", date(2026, 9, 21), "0331", RUPEES)
    r = ok(verify(prop(fact_type="order_win", subject="order", subject_key="order_win:india_order", value=value,
                       unit=unit, currency=currency, scale_word=None, period_label=None, quote=quote),
                  Chunk(RUPEES, 0, "body"), doc))  # fmt: skip
    assert r.verification_status == "needs_review" and "currency" in r.verification_notes, r


DATED_PRICE = (
    "Diluted earnings per share were $1.87 for the quarter ended September 30, 2026, up 14% from a year ago. "
    "Diluted earnings per share for the three months ended September 30, 2026 were $1.87, an increase of 14% from "
    "the prior-year period. Our stock price was $48.20 on June 30, 2026, up 23% from a year earlier. Our share price "
    "closed the quarter at $1,234.50, up 23% from a year earlier. Our shares have gained 23% this year. Our stock has "
    "risen 23% since the start of the year. Total return to shareholders was 23% in 2026. We returned $3.1 billion to "
    "shareholders through dividends and share repurchases."
)


@pytest.mark.parametrize(
    ("quote", "value", "fact"),
    [
        ("up 14% from a year ago", D(14), "price"),
        ("an increase of 14% from the prior-year period", D(14), "price"),
        ("up 23% from a year earlier", D(23), "price"),
        ("Our shares have gained 23% this year.", D(23), "price"),
        ("Our stock has risen 23% since the start of the year.", D(23), "price"),
        ("Total return to shareholders was 23% in 2026.", D(23), "price"),
        ("We returned $3.1 billion to shareholders through dividends and share repurchases.", D("3.1"), "buyback"),
    ],
    ids=["eps-dated", "eps-increase-of", "stock-dated", "shares-gained", "stock-has-risen", "return-to-holders",
         "returned-to-holders"],
)  # fmt: skip
def test_dated_and_other_share_price_sentences_are_not_stored(quote: str, value: D, fact: str) -> None:
    """M5 review R3 (R2-F1 still open): a comma inside a date or a number doesn't cut the sentence, a modifier clause
    is judged with everything before it, and "has risen", "have gained", "return to shareholders" are price topics."""
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", DATED_PRICE)
    if fact == "price":
        change = {"fact_type": "price_increase", "subject": "increase", "subject_key": "price_increase:year",
                  "unit": "percent", "currency": None, "scale_word": None}  # fmt: skip
    else:
        change = {"fact_type": "commitment_purchase", "subject": "purchase commitment",
                  "subject_key": "purchase_obligations:total", "unit": "usd", "currency": "USD",
                  "scale_word": "billion"}  # fmt: skip
    r = verify(prop(value=value, period_label=None, quote=quote, **change), Chunk(DATED_PRICE, 0, "mdna"), doc)
    assert not (isinstance(r, Candidate) and r.verification_status == "verified"), r


@pytest.mark.parametrize(
    "change",
    [
        {"fact_type": "backlog", "subject": "backlog", "subject_key": "backlog:total", "value": D("13.2"),
         "period_label": None, "quote": "Backlog was $13.2 billion, up 14% from a year ago."},
        {"fact_type": "backlog", "subject": "backlog", "subject_key": "backlog:total", "value": D("13.2"),
         "period_label": None, "quote": "backlog of $13.2 billion",
         "text": "Diluted EPS of $2.10, backlog of $13.2 billion and capital expenditures of $4.5 billion."},
        {"fact_type": "price_increase", "subject": "cooling units", "subject_key": "price_increase:cooling_units",
         "value": D(11), "unit": "percent", "currency": None, "scale_word": None, "period_label": None,
         "quote": "Effective January 1, the company will raise list prices on data center cooling units by 11%."},
    ],
    ids=["backlog-up-14", "backlog-after-eps", "list-prices"],
)  # fmt: skip
def test_business_facts_next_to_eps_or_dates_are_kept(change: dict[str, Any]) -> None:
    """M5 review R3-F3: the per-share check reads the number's own clause; a real price increase names a price."""
    text = str(change.pop("text", change["quote"]))
    doc = DocContext("10-Q", date(2026, 10, 28), "0630", text)
    r = ok(verify(prop(**change), Chunk(text, 0, "mdna"), doc))
    assert r.verification_status == "verified", r
    eps = verify(
        prop(
            fact_type="capex_reported",
            subject="capital expenditures",
            subject_key="capex_reported:q1",
            value=D("1.87"),
            scale_word=None,
            quote="Diluted earnings per share were $1.87.",
        ),
        CHUNK,
        DOC,
    )
    assert isinstance(eps, Rejected) and eps.check == "V1-TYPE"  # fmt: skip


@pytest.mark.parametrize(
    ("label", "fye", "expected"),
    [
        ("fiscal 2026 through 2028", "1231", None),
        ("fiscal 2026 to 2028", "1231", None),
        ("FY2026-FY2028", "1231", None),
        ("FY26-27", "0331", (date(2026, 4, 1), date(2027, 3, 31))),
        ("fiscal 2026-2027", "1231", None),
        ("FY2026-27", "1231", None),
        ("FY2025-26", "0331", (date(2025, 4, 1), date(2026, 3, 31))),
    ],
)
def test_multi_year_and_indian_labels(label: str, fye: str, expected: tuple[date, date] | None) -> None:
    """M5 review R3-F4: a multi-year plan is no single period, "FY26-27" is FY2027 for a March year end, and a
    calendar-year company's fiscal year doesn't span two years."""
    p = resolve(label, fye)
    assert (None if p is None else (p.start, p.end)) == expected


INDIA_TEXT = RUPEES + "\n\nArvl also won a US$12 million order from a US utility."
INDIA_DOC = DocContext("press_release", date(2026, 9, 21), "0331", INDIA_TEXT, "inr")


@pytest.mark.parametrize("currency", [None, "INR", "Rs", "₹"])
@pytest.mark.parametrize("unit", ["usd", "other"])
def test_an_indian_companys_rupee_amount_is_verified_as_rupees(unit: str, currency: str | None) -> None:
    """docs/SPEC_ISSUES.md 31 option b (58): an Indian company's amounts in its own currency are verified, stored as
    money (the unit `usd`, whatever "other" the model said) with currency INR, so S9 and S1 read them unattended."""
    r = ok(verify(prop(fact_type="order_win", subject="order", subject_key="order_win:india_order", value=D(450),
                       unit=unit, currency=currency, scale_word=None, period_label=None,
                       quote="The company received an order worth Rs 450 crore"),
                  Chunk(INDIA_TEXT, 0, "body"), INDIA_DOC))  # fmt: skip
    assert (r.verification_status, r.currency, r.unit, r.value_num) == ("verified", "INR", "usd", D(450) * 10**7)


@pytest.mark.parametrize(
    ("quote", "value", "scale", "currency"),
    [("Arvl also won a US$12 million order from a US utility", D(12), "million", "USD"),  # a dollar amount
     ("The company received an order worth Rs 450 crore", D(450), None, "USD")],  # rupees the model calls dollars
)  # fmt: skip
def test_another_currency_at_an_indian_company_waits_for_review(quote: str, value: D, scale: str | None,
                                                                 currency: str) -> None:  # fmt: skip
    """Only the filer's own currency is verified: a company's amounts then compare within one currency (diffs, S1's
    backlog against revenue); a dollar order of an Indian company waits in the review queue, as rupees at a US one."""
    r = ok(verify(prop(fact_type="order_win", subject="order", subject_key="order_win:us_order", value=value,
                       unit="usd", currency=currency, scale_word=scale, period_label=None, quote=quote),
                  Chunk(INDIA_TEXT, 0, "body"), INDIA_DOC))  # fmt: skip
    assert r.verification_status == "needs_review" and "(INR)" in r.verification_notes["currency"]


FIELDS = ("Effective January 1, the company will raise list prices on data center cooling units by 11%.\n\n"
          "We signed a 15-year power purchase agreement with Nimbus Compute for 400 MW.\n\n"
          "Customers now face lead times of 30 to 36 months for large gas turbines.")  # fmt: skip
FIELDS_DOC = DocContext("press_release", date(2026, 9, 15), "1231", FIELDS)


def fields(**kw: Any) -> Candidate:
    return ok(verify(prop(**kw), Chunk(FIELDS, 0, "body"), FIELDS_DOC))


def test_an_as_of_after_publication_is_the_publication_date() -> None:
    """docs/SPEC_ISSUES.md 59 (the first real-model run): "Effective January 1" came back as as_of 2027-01-01, which
    sent the price increase to review and would have put it outside S9's window; the fact is as of its publication."""
    quote = "the company will raise list prices on data center cooling units by 11%"
    c = fields(fact_type="price_increase", subject="list prices", subject_key="price_increase:cooling_units",
               value=D(11), unit="percent", currency=None, scale_word=None, period_label=None,
               as_of=date(2027, 1, 1), quote=quote)  # fmt: skip
    assert c.verification_status == "verified" and c.as_of == date(2026, 9, 15)


@pytest.mark.parametrize("label", ["15 years", "2026-09-15", "total", "multi-year", "September 30, 2025"])
def test_a_label_that_names_no_period_is_kept_without_one(label: str) -> None:
    """The top reason facts went to review in production (2026-10-28: dates, "total", "current" ...). A type that
    needs no period keeps the label as written and no period; capex guidance/reported still go to review."""
    c = fields(fact_type="commitment_ppa", subject="PPA", subject_key="ppa:nimbus_compute:ohio", value=D(400),
               unit="mw", currency=None, scale_word=None, period_label=label,
               quote="We signed a 15-year power purchase agreement with Nimbus Compute for 400 MW.")  # fmt: skip
    assert c.verification_status == "verified" and c.period_label == label and c.period_end is None


def test_the_models_midpoint_of_a_quoted_range_gives_way_to_codes() -> None:
    quote = "Customers now face lead times of 30 to 36 months for large gas turbines."
    for value in (D(33), D(34)):  # its midpoint, or any other number not in the quote: code's midpoint is stored
        c = fields(fact_type="lead_time", subject="gas turbines", subject_key="lead_time:gas_turbines", value=value,
                   value_low=D(30), value_high=D(36), unit="months", currency=None, scale_word=None,
                   period_label=None, quote=quote)  # fmt: skip
        assert (c.verification_status, c.value_num, c.value_low, c.value_high) == ("verified", D(33), D(30), D(36))
    one_end = verify(prop(fact_type="lead_time", subject="gas turbines", subject_key="lead_time:gas_turbines",
                          value=D(33), value_low=D(30), unit="months", currency=None, scale_word=None,
                          period_label=None, quote=quote), Chunk(FIELDS, 0, "body"), FIELDS_DOC)  # fmt: skip
    assert isinstance(one_end, Rejected) and one_end.check == "V1-NUM"  # not a range: the model's number must be quoted
