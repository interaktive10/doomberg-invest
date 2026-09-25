"""Numbers in a quote (Appendix F.4 step 5, V1-NUM, V1-UNIT).

Parsed: `$X.Y billion/million/thousand` (also `$1.2B`, `$500M`, `US$`, `USD`, `dollars`), bare numbers with a scale
word, ranges (`X to Y`, `X-Y`, `X–Y`, `between X and Y`, `from X to Y`, sharing a scale, unit or currency given once),
`approximately`/`about`/... (ignored), percents, MW/GW/MWh, months/weeks/years, square feet, small number words
("two gigawatts", "twelve months"), and Indian amounts (Rs, INR, ₹, crore, lakh; Indian digit grouping).

A model value matches a parsed number when it equals the numeral as written (with or without the scale word) or the
scaled amount, within the rounding of the last reported digit. The stored value is always the parsed, scaled amount:
the model points at a number in the quote; it never supplies one (it may not calculate or convert, P-01).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

SCALE: dict[str, Decimal] = {
    "thousand": Decimal(10) ** 3, "k": Decimal(10) ** 3,
    "million": Decimal(10) ** 6, "mn": Decimal(10) ** 6, "mm": Decimal(10) ** 6, "m": Decimal(10) ** 6,
    "billion": Decimal(10) ** 9, "bn": Decimal(10) ** 9, "b": Decimal(10) ** 9,
    "trillion": Decimal(10) ** 12, "tn": Decimal(10) ** 12, "t": Decimal(10) ** 12,
    "lakh": Decimal(10) ** 5, "lakhs": Decimal(10) ** 5, "lac": Decimal(10) ** 5, "lacs": Decimal(10) ** 5,
    "crore": Decimal(10) ** 7, "crores": Decimal(10) ** 7, "cr": Decimal(10) ** 7,
}  # fmt: skip
SCALE_WORD = {"thousand": "thousand", "k": "thousand", "million": "million", "mn": "million", "mm": "million",
              "m": "million", "billion": "billion", "bn": "billion", "b": "billion", "trillion": "trillion",
              "tn": "trillion", "t": "trillion"}  # fmt: skip
WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())} | {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                                             "eighty": 80, "ninety": 90, "hundred": 100}  # fmt: skip

_NUM = re.compile(
    r"(?<![\w.])(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d,]*\d)"
    r"|(?<![\w])(?P<word>" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")(?!\w)",
    re.I,
)
_CURRENCY_BEFORE = re.compile(r"(?P<cur>US\$|\$|USD|₹|Rs\.?|INR|€|EUR|£|GBP)\s?$", re.I)
_SCALE_AFTER = re.compile(r"^\s?(?P<s>thousand|million|billion|trillion|mn|mm|bn|tn|lakhs?|lacs?|crores?|cr)\b", re.I)
_SCALE_LETTER = re.compile(r"^(?P<s>[kKmMbBtT])(?![A-Za-z])")  # "$1.2B", "$500M" (glued to a currency amount)
_UNIT_AFTER = re.compile(
    r"^\s?(?:(?P<pct>%|percent\b|per\s?cent\b|pct\b)"
    r"|(?P<mwh>MWh\b|megawatt[- ]hours?\b)|(?P<mw>MW\b|megawatts?\b)|(?P<gw>GW\b|gigawatts?\b)"
    r"|(?P<months>months?\b)|(?P<weeks>weeks?\b)|(?P<years>years?\b)"
    r"|(?P<sqft>(?:square|sq\.?)\s?(?:feet|foot|ft\.?)|sf\b))",
    re.I,
)
_CURRENCY_AFTER = re.compile(r"^\s?(?P<cur>dollars|U\.?S\.? dollars|rupees)\b", re.I)
_RANGE = re.compile(r"^\s?(?:to|-|–|—|and|through)\s?", re.I)
_BETWEEN = re.compile(r"(?:between|from)\s$", re.I)
_PER_YEAR = re.compile(r"\b(?:per\s+(?:year|annum)|a\s+year|annually|annual)\b", re.I)

CURRENCY = {"$": "usd", "us$": "usd", "usd": "usd", "dollars": "usd", "u.s. dollars": "usd", "us dollars": "usd",
            "₹": "inr", "rs": "inr", "rs.": "inr", "inr": "inr", "rupees": "inr", "€": "eur", "eur": "eur",
            "£": "gbp", "gbp": "gbp"}  # fmt: skip
INDIAN_SCALES = frozenset({"lakh", "lakhs", "lac", "lacs", "crore", "crores", "cr"})


@dataclass(frozen=True)
class Parsed:
    numeral: Decimal  # as written ("1.25" in "$1.25 billion")
    decimals: int  # digits after the point as written
    scale: Decimal  # 1 when there is no scale word
    scale_word: str | None  # "billion", "crore", ... as written (lower case)
    currency: str | None  # usd | inr | eur | gbp
    unit: str | None  # percent | mw | gw | mwh | months | weeks | years | sq_ft
    start: int
    end: int
    range_with: int | None = None  # index of the other end of a range

    @property
    def value(self) -> Decimal:
        return self.numeral * self.scale

    @property
    def tol(self) -> Decimal:
        """Half a unit of the last reported digit (unscaled)."""
        return Decimal(5) * Decimal(10) ** -(self.decimals + 1)


def _numeral(m: re.Match[str]) -> tuple[Decimal, int]:
    if m.group("num"):
        raw = m.group("num").replace(",", "")
        return Decimal(raw), len(raw.split(".")[1]) if "." in raw else 0
    return Decimal(WORDS[m.group("word").lower()]), 0


def parse(quote: str) -> list[Parsed]:
    out: list[Parsed] = []
    for m in _NUM.finditer(quote):
        value, decimals = _numeral(m)
        before, after = quote[max(0, m.start() - 6) : m.start()], quote[m.end() :]
        cur = _CURRENCY_BEFORE.search(before)
        currency = CURRENCY.get(cur.group("cur").lower()) if cur else None
        end = m.end()
        scale, scale_word = Decimal(1), None
        s = _SCALE_AFTER.match(after) or (_SCALE_LETTER.match(after) if currency else None)
        if s:
            scale_word = s.group("s").lower()
            scale = SCALE[scale_word]
            end += s.end()
            after = quote[end:]
        c2 = _CURRENCY_AFTER.match(after)
        if c2 and currency is None:
            currency = "usd" if "dollar" in c2.group("cur").lower() else "inr"
            end += c2.end()
            after = quote[end:]
        unit = None
        u = _UNIT_AFTER.match(after)
        if u:
            unit = next(k for k, v in u.groupdict().items() if v)
            unit = {"pct": "percent", "sqft": "sq_ft"}.get(unit, unit)
            end += u.end()
        if currency is None and scale_word in INDIAN_SCALES:
            currency = "inr"
        out.append(Parsed(value, decimals, scale, scale_word, currency, unit, m.start(), end))
    return _ranges(quote, out)


def _ranges(quote: str, nums: list[Parsed]) -> list[Parsed]:
    """Link `X to Y` pairs and share the scale, currency and unit written on one side only."""
    out = list(nums)
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        between = _CURRENCY_BEFORE.sub("", quote[a.end : b.start])  # "$70 billion to $75 billion"
        if not _RANGE.fullmatch(between + " ") and not _RANGE.fullmatch(between):
            continue
        if between.strip().lower() == "and" and not _BETWEEN.search(quote[max(0, a.start - 8) : a.start]):
            continue
        a2 = replace(a, range_with=i + 1,
                     scale=a.scale if a.scale_word else b.scale, scale_word=a.scale_word or b.scale_word,
                     currency=a.currency or b.currency, unit=a.unit or b.unit)  # fmt: skip
        b2 = replace(b, range_with=i, currency=b.currency or a.currency, unit=b.unit or a.unit)
        out[i], out[i + 1] = a2, b2
    return out


def scale_of(word: str | None) -> Decimal:
    return SCALE.get((word or "").lower(), Decimal(1))


def match(model_value: Decimal, model_scale_word: str | None, nums: Sequence[Parsed]) -> Parsed | None:
    """The parsed number the model's value refers to: the numeral as written (with its scale word, or none given),
    or the scaled amount, within the rounding of the last reported digit."""
    scaled = model_value * scale_of(model_scale_word)
    for p in nums:
        tol = p.tol
        if abs(model_value - p.numeral) <= tol and model_scale_word in (None, SCALE_WORD.get(p.scale_word or "", "")):
            return p
        if abs(scaled - p.value) <= tol * p.scale or abs(model_value - p.value) <= tol * p.scale:
            return p
    return None


def per_year(quote: str) -> bool:
    return bool(_PER_YEAR.search(quote))
