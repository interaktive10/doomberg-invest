"""Numbers in quotes (Appendix F.4 step 5): scales, ranges, units, currencies, and matching a model's value."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from pipeline.facts.numbers import match, parse


def one(q: str) -> tuple[str, str | None, str | None]:
    p = parse(q)[0]
    return str(p.value.normalize()), p.currency, p.unit


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("capex of approximately $75 billion", ("7.5E+10", "usd", None)),
        ("RPO of $1.2B", ("1.2E+9", "usd", None)),
        ("orders of $500M", ("5E+8", "usd", None)),
        ("USD 2.3 billion", ("2.3E+9", "usd", None)),
        ("costs of 5 million dollars", ("5E+6", "usd", None)),
        ("orders worth Rs 450 crore", ("4.5E+9", "inr", None)),
        ("₹1,234.5 crore", ("1.2345E+10", "inr", None)),
        ("a 500,000 square foot plant", ("5E+5", None, "sq_ft")),
        ("a pipeline of 2.5 GW", ("2.5", None, "gw")),
        ("adding two gigawatts", ("2", None, "gw")),
        ("lead times of 120 weeks", ("1.2E+2", None, "weeks")),
        ("45% of revenue", ("45", None, "percent")),
        ("12 MWh of storage", ("12", None, "mwh")),
    ],
)
def test_parse(quote: str, expected: tuple[str, str | None, str | None]) -> None:
    assert one(quote) == expected


def test_ranges_share_scale_unit_and_currency() -> None:
    for q in ("capex of $70 billion to $75 billion", "capex of $70-75 billion", "between $70 and $75 billion"):
        a, b = parse(q)[:2]
        assert (a.value, b.value) == (D(70) * 10**9, D(75) * 10**9) and a.range_with == 1 and b.currency == "usd"
    a, b = parse("12 to 18 months")
    assert (a.unit, b.unit) == ("months", "months")
    x, y = parse("in 2026 and 3 new sites")
    assert x.range_with is None and y.range_with is None  # "and" without "between" is not a range


def test_match_accepts_the_number_as_written_or_scaled() -> None:
    nums = parse("approximately $75 billion")
    assert match(D(75), "billion", nums) is not None
    assert match(D(75), None, nums) is not None
    assert match(D(75_000_000_000), None, nums) is not None
    assert match(D("75.4"), "billion", nums) is not None  # within the rounding of the last reported digit
    assert match(D(76), "billion", nums) is None
    assert match(D(75), "million", nums) is None
    assert match(D("1.26"), "billion", parse("$1.2 billion")) is None
