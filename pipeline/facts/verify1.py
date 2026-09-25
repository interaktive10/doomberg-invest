"""Verify-1 (Appendix F.5): a proposed fact enters the ledger only if `verified`.

| Check     | Rule                                                                         | On failure              |
| V1-QUOTE  | the quote is grounded in its chunk; the stored quote is text[start:end]      | failed (not stored)     |
| V1-NUM    | every numeric field is a number in the quote (numbers.match)                 | failed                  |
| V1-UNIT   | the unit agrees with the quote's tokens ("MW" <-> mw, "$" <-> usd, ...)      | failed                  |
| V1-TYPE   | allowed type; no share-price facts; subject_key valid                        | failed / needs_review   |
| V1-PERIOD | period resolvable and plausible                                              | needs_review            |
| V1-XBRL   | |value - XBRL| <= 0.5% for the same concept and period                       | needs_review (mismatch) |
| V1-CONF   | confidence >= 0.70                                                           | needs_review            |
| V1-DUP    | the document already has the same subject_key and value                      | dropped                 |
Currency: USD only in v1; any other currency is needs_review. An unknown subject_key becomes other:<slug> and
needs_review (F.4 step 7). Stored values come from the quote (the parsed, scaled amount), not from the model.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pipeline.facts import keys, numbers
from pipeline.facts.chunk import Chunk
from pipeline.facts.extract import Proposed
from pipeline.facts.ground import grounded_quote
from pipeline.facts.periods import Period, period_slug, resolve

MIN_CONFIDENCE = Decimal("0.70")
XBRL_TOLERANCE = Decimal("0.005")
PRICE_SUBJECT = re.compile(
    r"\b(?:share|stock)\s+price|price\s+target|market\s+cap(?:italization)?|dividends?|repurchases?|buybacks?|"
    r"stock\s+performance|analysts?\b|ratings?\b|valuation\b|per\s+(?:diluted\s+)?share\b|\bEPS\b",
    re.I,
)
PER_SHARE_AFTER = re.compile(r"^\s*(?:per|a)\s+(?:diluted\s+)?share\b", re.I)
PER_SHARE_BEFORE = re.compile(r"(?:\bper\s+(?:diluted\s+)?share|\bEPS)\b[^.;]{0,40}$", re.I)
UNIT_OF = {"mw": "mw", "gw": "gw", "mwh": "mwh", "percent": "percent", "months": "months", "weeks": "weeks",
           "years": "years", "sq_ft": "sq_ft"}  # fmt: skip
PERIOD_REQUIRED = frozenset({"capex_guidance", "capex_reported"})
GUIDANCE = frozenset({"capex_guidance"})

# (concept, period_end, months) -> the XBRL value known when the document was published, or None
XbrlLookup = Callable[[str, date, int], Decimal | None]
XBRL_CONCEPT = {"capex_reported": "capex", "rpo": "rpo"}


@dataclass(frozen=True)
class DocContext:
    kind: str
    published: date
    fye: str | None
    text: str  # the document's canonical text


@dataclass(frozen=True)
class Candidate:
    fact_type: str
    subject: str
    subject_key: str
    value_num: Decimal | None
    value_low: Decimal | None
    value_high: Decimal | None
    unit: str
    currency: str | None
    scale_word: str | None
    period_label: str | None
    period_start: date | None
    period_end: date | None
    as_of: date
    counterparty: str | None
    location: str | None
    quote: str
    char_start: int
    char_end: int
    section: str | None
    page: int | None
    xbrl_concept: str | None
    xbrl_check: str  # match | mismatch | na
    confidence: Decimal
    verification_status: str  # verified | needs_review
    verification_notes: dict[str, Any] = field(default_factory=dict)
    withdrawn: bool = False

    def dup_key(self) -> tuple[Any, ...]:
        return (self.subject_key, self.value_num, self.value_low, self.value_high)


@dataclass(frozen=True)
class Rejected:
    check: str
    reason: str


def _unit_ok(unit: str, p: numbers.Parsed, quote: str) -> bool:
    if unit in {"usd", "usd_per_year"}:
        return p.currency is not None and (unit == "usd" or numbers.per_year(quote))
    if unit in UNIT_OF:
        return p.unit == UNIT_OF[unit]
    if unit == "count":
        return p.currency is None and p.unit is None
    return True  # other


def verify(p: Proposed, chunk: Chunk, doc: DocContext, xbrl: XbrlLookup | None = None,
           seen: set[tuple[Any, ...]] | None = None) -> Candidate | Rejected | None:  # fmt: skip
    """A Candidate (verified or needs_review), a Rejected (failed; not stored), or None (a duplicate, dropped)."""
    g = grounded_quote(p.quote, doc.text, chunk.char_start, chunk.char_end)
    if g is None:
        return Rejected("V1-QUOTE", "quote not found in the chunk (exact, then whitespace/punctuation-insensitive)")
    start, end, quote = g
    if PRICE_SUBJECT.search(p.subject) or PRICE_SUBJECT.search(p.subject_key):
        return Rejected("V1-TYPE", "share-price, valuation or capital-return facts are not stored (prices_w)")
    review: dict[str, str] = {}

    parsed = numbers.parse(quote)
    matched: dict[str, numbers.Parsed] = {}
    for name in ("value", "value_low", "value_high"):
        v = getattr(p, name)
        if v is None:
            continue
        m = numbers.match(v, p.scale_word, parsed)
        if m is None:
            return Rejected("V1-NUM", f"{name}={v} is not a number in the quote")
        matched[name] = m
    for m in matched.values():
        if not _unit_ok(p.unit, m, quote):
            return Rejected("V1-UNIT", f"unit {p.unit} disagrees with the quote around {quote[m.start : m.end]!r}")
        if PER_SHARE_AFTER.match(quote[m.end :]) or PER_SHARE_BEFORE.search(quote[: m.start]):
            return Rejected("V1-TYPE", "a per-share amount is a price field")
        if m.currency is not None and m.currency != "usd":
            review["currency"] = f"{m.currency.upper()} amount: v1 stores USD only"
    if p.currency and p.currency.strip().upper() not in {"USD", "US$", "$"}:
        review["currency"] = f"{p.currency} amount: v1 stores USD only"

    low = matched["value_low"].value if "value_low" in matched else None
    high = matched["value_high"].value if "value_high" in matched else None
    value: Decimal | None
    if "value" in matched:
        value = matched["value"].value
    elif low is not None and high is not None:
        value = (low + high) / 2  # a range's midpoint, computed by code
    else:
        value = low if low is not None else high
    scale_word = next((numbers.SCALE_WORD.get(m.scale_word or "") for m in matched.values() if m.scale_word), None)
    scale_word = scale_word or next((m.scale_word for m in matched.values() if m.scale_word), None)

    as_of = p.as_of or doc.published
    if as_of > doc.published + timedelta(days=1):
        review["as_of"] = f"as_of {as_of} is after the document's publication ({doc.published})"
    period: Period | None = resolve(p.period_label, doc.fye, as_of)
    if p.period_label and period is None:
        review["period"] = f"period {p.period_label!r} not resolvable"
    elif p.fact_type in PERIOD_REQUIRED and period is None:
        review["period"] = "capex guidance/reported needs a period"
    elif p.fact_type in GUIDANCE and period is not None and period.end < doc.published and not p.withdrawn:
        review["period"] = f"guidance for a period that ended {period.end} (published {doc.published})"

    slug = period_slug(period, doc.fye) if period is not None else None
    key, key_ok = keys.check(p.fact_type, p.subject_key, p.subject, slug)
    if not key_ok:
        review["subject_key"] = f"{p.subject_key!r} is not in config/subject_keys.yaml for {p.fact_type}"

    concept, xcheck = XBRL_CONCEPT.get(p.fact_type), "na"
    if concept and xbrl is not None and value is not None and "currency" not in review:
        ref_end = period.end if period is not None else as_of
        months = 12 if period is not None and (period.end - period.start).days > 300 else 3
        ref = xbrl(concept, ref_end, months)
        if ref is not None and ref != 0:
            xcheck = "match" if abs(abs(value) - abs(ref)) <= XBRL_TOLERANCE * abs(ref) else "mismatch"
            if xcheck == "mismatch":
                review["xbrl"] = f"{concept} XBRL {ref} vs {value}"
    if p.confidence < MIN_CONFIDENCE:
        review["confidence"] = f"{p.confidence} < {MIN_CONFIDENCE}"

    c = Candidate(
        fact_type=p.fact_type, subject=p.subject, subject_key=key, value_num=value, value_low=low, value_high=high,
        unit=p.unit, currency="USD" if any(m.currency == "usd" for m in matched.values()) else p.currency,
        scale_word=scale_word, period_label=p.period_label, period_start=period.start if period else None,
        period_end=period.end if period else None, as_of=as_of, counterparty=p.counterparty, location=p.location,
        quote=quote, char_start=start, char_end=end, section=chunk.section, page=chunk.page,
        xbrl_concept=concept if xcheck != "na" else None, xbrl_check=xcheck, confidence=p.confidence,
        verification_status="needs_review" if review else "verified", verification_notes=review,
        withdrawn=p.withdrawn,
    )  # fmt: skip
    if seen is not None:
        if c.dup_key() in seen:
            return None
        seen.add(c.dup_key())
    return c
