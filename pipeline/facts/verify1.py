"""Verify-1 (Appendix F.5): a proposed fact enters the ledger only if `verified`.

| Check     | Rule                                                                         | On failure              |
| V1-QUOTE  | the quote is grounded in its chunk; the stored quote is text[start:end]      | failed (not stored)     |
| V1-NUM    | every numeric field is a number in the quote (numbers.match)                 | failed                  |
| V1-UNIT   | the unit agrees with the quote's tokens ("MW" <-> mw, "$" <-> usd, ...)      | failed                  |
| V1-TYPE   | allowed type; no share-price facts (labels or quote); subject_key valid      | failed / needs_review   |
| V1-KIND   | the quote shows the type S9 or R3 reads (below); a deal is no order          | failed / needs_review   |
| V1-PERIOD | period resolvable and plausible (where the type needs one: below)            | needs_review            |
| V1-XBRL   | |value - XBRL| <= 0.5% for the same concept and period                       | needs_review (mismatch) |
| V1-CONF   | confidence >= 0.70                                                           | needs_review            |
| V1-DUP    | the document already has the same subject_key and value                      | dropped                 |
Currency: the filer's own only (USD for a US company, INR for an Indian one: docs/SPEC_ISSUES.md 31 option b), so
a company's amounts compare within one currency (diffs, S1's backlog against revenue); any other currency is
needs_review. Money keeps the unit `usd` (facts.unit has no other money unit) and `currency` says which. An unknown
subject_key becomes other:<slug> and needs_review (F.4 step 7). Stored values come from the quote (the parsed, scaled
amount), not from the model.
What the model adds around a grounded number doesn't send a fact to review (docs/SPEC_ISSUES.md 59, the first runs on
the real model): an as_of after publication (a delivery or effective date) is the publication date; a period label
that names no fiscal or calendar period ("15 years", "total", a date) is kept as written with no period, except on
capex guidance/reported, which need one; and the model's own midpoint of a quoted range gives way to code's. A fact of
a type that is a measure (MEASURES) needs a number in its quote. A fact of a type S9 counts or R3 reads (KIND_TYPES)
needs its type's words in its quote (V1-KIND, docs/SPEC_ISSUES.md 61).
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
PLAUSIBLE_DAYS = 3653  # V1-PERIOD "plausible": a period ending more than 10 years from as_of goes to review
XBRL_TOLERANCE = Decimal("0.005")
PRICE_SUBJECT = re.compile(
    r"\b(?:share|stock)\s+price|price\s+target|market\s+cap(?:italization)?|dividends?|repurchases?|buybacks?|"
    r"stock\s+performance|analysts?\b|ratings?\b|valuation\b|per\s+(?:diluted\s+)?share\b|\bEPS\b",
    re.I,
)
# Share-price topics in the document's own words (M5 review R1-F1, R2-F1/F2): the model's subject, key and even its
# quote are its own choices, so V1-TYPE reads the sentence that contains the quote in the canonical text, clause by
# clause. A number fails when its clause names a price topic, or when the clause only modifies the one before it
# ("..., up 14% from a year ago") and that one does. Plain words ("upgraded our plant", "analysts had modeled",
# "continuing to pay dividends") don't: only these phrases do.
PRICE_TOPIC = re.compile(
    r"\b(?:share|stock)\s+prices?\b|\bprice\s+(?:target|objective)s?\b|\bmarket\s+cap(?:italization)?\b"
    r"|\bmarket\s+value\s+of\s+(?:our\s+)?(?:common\s+)?(?:stock|shares)\b"
    r"|\btotal\s+(?:share|stock)holder\s+returns?\b|\bTSR\b|\b(?:share|stock)holder\s+returns?\b"
    r"|\b(?:total\s+|capital\s+|cash\s+)?returns?\s+to\s+(?:share|stock)holders\b"  # M5 review R3 (R2-F1)
    r"|\breturned\b(?:[^.;]|\.(?=\d)){0,60}\bto\s+(?:share|stock)holders\b"
    r"|\b(?:common\s+)?(?:stock|shares)\s+(?:(?:is|was|are|were|has|have|had|has\s+been|have\s+been)\s+)?(?:up|down|higher|lower|rose|"
    r"risen|fell|fallen|gained|lost|jumped|dropped|declined|climbed|traded|closed|outperformed|underperformed|returned|"
    r"increased|decreased)\b"
    r"|\b(?:share|stock)\s+(?:repurchases?|buy-?backs?)\b|\brepurchase\s+(?:program|plan|authorization)s?\b|\bbuy-?backs?\b"
    r"|\brepurchased?\b(?:[^.;]|\.(?=\d)){0,30}\bshares\b"
    r"|\bdividends?\s+(?:of|per|declared|paid|payable|yield|increase)\b|\bdividend\s+yield\b"
    r"|\b(?:declared|paid|raised|increased|cut)\s+(?:a|the|our|its)?\s*(?:quarterly\s+|annual\s+|special\s+|cash\s+)?"
    r"dividends?\b"
    r"|\b(?:earnings|net\s+income|income|loss)\s+per\s+(?:diluted\s+|basic\s+)?(?:common\s+)?share\b"
    r"|\bper\s+diluted\s+share\b|\bEPS\b"
    r"|\banalysts?\s+(?:upgraded|downgraded|rated|raised|cut|lowered)\b"
    r"|\b(?:upgraded|downgraded)\s+(?:their|the|our|its)?\s*(?:ratings?|stock|shares)\b"
    r"|\b(?:buy|sell|hold|overweight|underweight)\s+ratings?\b",
    re.I,
)
CLAUSE_BREAK = re.compile(r"[,;:()\u2014\u2013]|\s(?:and|while|but|whereas)\s", re.I)
MODIFIER = re.compile(
    r"^\s*(?:up|down|higher|lower|rising|falling|an?\s+(?:increase|decrease|rise|decline|gain|drop|jump)\s+of|compared|"
    r"versus|vs\.?|from|to)\b",
    re.I,
)
SENTENCE_END = re.compile(r"(?<=[.!?])[\"'\u201d\u2019)]*\s+(?=[A-Z0-9\"'\u201c(])|\n")


def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """The sentence(s) of the canonical text that contain [start, end)."""
    lo, hi = max(0, start - 2000), min(len(text), end + 2000)
    a, b = lo, hi
    for m in SENTENCE_END.finditer(text, lo, hi):
        if m.end() <= start:
            a = m.end()
        elif m.start() >= end:
            b = m.start()
            break
    return a, b


def _is_break(sentence: str, m: re.Match[str]) -> bool:
    """A comma inside a number ("$1,234.50") or a date ("September 30, 2026") doesn't end a clause (M5 review R3)."""
    if m.group(0) != ",":
        return True
    before, after = sentence[: m.start()], sentence[m.end() :]
    if before[-1:].isdigit() and after[:1].isdigit():
        return False
    return not (re.search(r"\b\d{1,2}$", before) and re.match(r"\s\d{4}\b", after))


def _clauses(sentence: str) -> list[tuple[int, int]]:
    breaks = [m for m in CLAUSE_BREAK.finditer(sentence) if _is_break(sentence, m)]
    cuts = [0, *(x for m in breaks for x in (m.start(), m.end())), len(sentence)]
    return [(cuts[i], cuts[i + 1]) for i in range(0, len(cuts) - 1, 2)]


def _clause_of(sentence: str, pos: int) -> tuple[int, int, int]:
    clauses = _clauses(sentence)
    k = next((i for i, (a, b) in enumerate(clauses) if a <= pos < b), len(clauses) - 1)
    return k, *clauses[k]


def price_context(sentence: str, pos: int) -> bool:
    """Whether the number at `pos` of the sentence is about the share price, EPS, a buyback or a dividend: its clause
    names one, or its clause only modifies what came before ("..., up 14% from a year ago") and anything before it
    in the sentence names one (M5 review R2-F1, R3)."""
    k, a, b = _clause_of(sentence, pos)
    if PRICE_TOPIC.search(sentence[a:b]):
        return True
    return k > 0 and bool(MODIFIER.match(sentence[a:b])) and bool(PRICE_TOPIC.search(sentence[:a]))


PRICING = re.compile(r"\bpric(?:e|es|ed|ing)\b|\bsurcharges?\b|\btariffs?\b|\brate\s+(?:increase|hike)s?\b", re.I)


def pricing_word(sentence: str) -> bool:
    """A price_increase fact's sentence names a price of the business, not only a share price (M5 review R3)."""
    return bool(PRICING.search(PRICE_TOPIC.sub(" ", sentence)))


# V1-KIND (docs/SPEC_ISSUES.md 61). The new P-01's first day stored as order wins:
# - acquisitions, mergers and sales of a business
# - legal settlements, escrow and refunds
# - recurring revenue and guidance
# It also stored an officer's resignation as an auditor change, a mortgage default as a material weakness, a margin
# outlook as a price increase, a company's existing segments as a new one, and a new president as a customer win.
# S9 counts these types, R3's hard flag reads the governance ones, and a fact's quote is its evidence, so the quote
# has to show its type:
# - an order's quote that names a deal fails it
# - a quote without its type's words waits for review
# The text run checks the stored quotes of earlier facts the same way (pipeline/facts/run.py recheck_stored).
DEAL = re.compile(
    r"\bacquir(?:e|ed|es|ing)\b|\bacquisitions?\b|\bmerg(?:e|er|ers|ed|ing)\b|\bconsideration\b|\bdivest\w*"
    r"|\bsale\s+of\b|\bsold\b|\bsettlements?\b|\bescrow(?:ed)?\b|\brefunds?\b|\bguidance\b|\boutlook\b"
    r"|\bproceeds\b|\bliabilit(?:y|ies)\b|\b(?:equity|enterprise)\s+value\b|\brecurring\s+revenue\b|(?-i:\bARR\b)",
    re.I,
)
ORDER = re.compile(
    r"(?<!\bin\s)\border(?:s|ed)?\b|\bawards?\b|\bawarded\b|\bcontract(?:s|ed)?\b|\bbookings?\b|\bbooked\b"
    r"|\bwins?\b|\bwon\b|\bselected\b|\bletters?\s+of\s+(?:award|intent)\b|\bauthori[sz]ation\s+to\s+proceed\b"
    r"|\bdesign-build\b|\bagreements?\b|\btenders?\b|\bsecured\b|\bbagged\b|\bsigned\b",
    re.I,
)
GOVERNANCE_WORDS = {
    "material_weakness": re.compile(r"\bmaterial\s+weakness(?:es)?\b|\bnot\s+effective\b|\bineffective\b", re.I),
    "going_concern": re.compile(r"\bgoing\s+concern\b|\bsubstantial\s+doubt\b", re.I),
    "auditor_change": re.compile(
        r"\bauditors?\b|\baccounting\s+firm\b|\bregistered\s+public\s+accounting\b|\bindependent\s+accountants?\b", re.I
    ),
    "restatement": re.compile(r"\brestat(?:e|ed|es|ing|ement|ements)\b|\bnon-?reliance\b", re.I),
}
BUSINESS_LINE = re.compile(
    r"\bsegments?\b|\blines?\s+of\s+business\b|\bbusiness(?:es|\s+lines?|\s+units?)?\b|\bdivisions?\b|\bverticals?\b",
    re.I,
)
NEW = re.compile(
    r"\bnew(?:ly)?\b|\bestablish\w*|\blaunch\w*|\bcreat(?:e|ed|es|ing|ion)\b|\bform(?:ed|ing|ation)\b"
    r"|\benter(?:ed|ing|s)?\b|\bentry\b|\bexpan(?:d|ded|ding|sion)\s+into\b|\bintroduc\w*|\bbegin(?:s|ning)?\b|\bbegan\b",
    re.I,
)
CUSTOMER = re.compile(
    r"\bcustomers?\b|\bclients?\b|\blogos?\b|\brelationships?\b|\bpartner(?:s|ships?)?\b|\baccounts?\b|\bprograms?\b"
    r"|\bselected\b|\bchose\b|\bawards?\b|\bawarded\b|\bcontracts?\b|\bwins?\b|\bwon\b|\bonboard\w*",
    re.I,
)
KIND_TYPES = frozenset({"order_win", "customer_win", "governance_flag", "new_segment", "price_increase"})


def kind_problem(fact_type: str, subject_key: str, quote: str) -> tuple[bool, str] | None:
    """(fails, why) when the quote doesn't show the fact's type (V1-KIND), else None. Only a deal fails an order: a
    quote that lacks its type's words may still be one, so it waits for review."""
    if fact_type == "order_win":
        if DEAL.search(quote):
            return True, "an acquisition, a sale of a business, a settlement, a refund, revenue or guidance is no order"
        if not ORDER.search(quote):
            return False, "the quote names no order, award, contract or booking"
    elif fact_type == "governance_flag":
        parts = subject_key.split(":")
        words = GOVERNANCE_WORDS.get(parts[1]) if len(parts) == 3 else None
        if words is not None and not words.search(quote):
            return False, f"the quote names no {parts[1].replace('_', ' ')}"
    elif fact_type == "new_segment":
        if not (BUSINESS_LINE.search(quote) and NEW.search(quote)):
            return False, "the quote doesn't say a segment or business line is new"
    elif fact_type == "price_increase" and not pricing_word(quote):
        return False, "the quote names no price or pricing action"
    elif fact_type == "customer_win" and not CUSTOMER.search(quote):
        return False, "the quote names no customer, client, partner or program"
    return None


PER_SHARE_AFTER = re.compile(r"^\s*(?:per|a)\s+(?:diluted\s+)?share\b", re.I)
# up to 40 characters back within the clause; a decimal point ("$1.87") doesn't end it (M5 review R1-F1)
PER_SHARE_BEFORE = re.compile(r"(?:\bper\s+(?:diluted\s+)?share|\bEPS)\b(?:[^.;]|\.(?=\d)){0,40}$", re.I)
UNIT_OF = {"mw": "mw", "gw": "gw", "mwh": "mwh", "percent": "percent", "months": "months", "weeks": "weeks",
           "years": "years", "sq_ft": "sq_ft"}  # fmt: skip
PERIOD_REQUIRED = frozenset({"capex_guidance", "capex_reported"})
# types that are a measure: without a number in the quote ("we monitor lead time trends") there is no fact
# (docs/SPEC_ISSUES.md 59); an event (an order, a customer, a segment, a governance event) needs none
MEASURES = frozenset({"capex_guidance", "capex_reported", "backlog", "rpo", "lead_time", "commitment_lease",
                      "commitment_purchase", "customer_concentration", "utility_load", "export_exposure"})  # fmt: skip
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
    currency: str = "usd"  # the filer's reporting currency (numbers.CURRENCY codes): inr for an Indian company


# how a model may name each filer currency (P-01's `currency` field)
CURRENCY_NAMES = {"usd": frozenset({"USD", "US$", "$"}), "inr": frozenset({"INR", "RS", "RS.", "₹", "RUPEES"})}


def own_currency_note(found: str, doc: DocContext) -> str:
    return f"{found} amount: only the filer's own currency ({doc.currency.upper()}) is stored verified"


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


def stored_unit(unit: str, matched: dict[str, numbers.Parsed]) -> str:
    """A unit with no number in the quote says nothing (M5 review R1-F9); an amount whose quote names a currency is
    money (`usd`, the money unit; `currency` says which), whatever unit "other" the model gave it."""
    if not matched:
        return "other"
    return "usd" if unit == "other" and any(m.currency for m in matched.values()) else unit


def verify(p: Proposed, chunk: Chunk, doc: DocContext, xbrl: XbrlLookup | None = None,
           seen: set[tuple[Any, ...]] | None = None) -> Candidate | Rejected | None:  # fmt: skip
    """A Candidate (verified or needs_review), a Rejected (failed; not stored), or None (a duplicate, dropped)."""
    g = grounded_quote(p.quote, doc.text, chunk.char_start, chunk.char_end)
    if g is None:
        return Rejected("V1-QUOTE", "quote not found in the chunk (exact, then whitespace/punctuation-insensitive)")
    start, end, quote = g
    if PRICE_SUBJECT.search(p.subject) or PRICE_SUBJECT.search(p.subject_key):
        return Rejected("V1-TYPE", "share-price, valuation or capital-return facts are not stored (prices_w)")
    s0, s1 = sentence_span(doc.text, start, end)
    sentence = doc.text[s0:s1]
    review: dict[str, str] = {}

    parsed = numbers.parse(quote)
    matched: dict[str, numbers.Parsed] = {}
    for name in ("value_low", "value_high", "value"):
        v = getattr(p, name)
        if v is None:
            continue
        m = numbers.match(v, p.scale_word, parsed)
        if m is None and name == "value" and {"value_low", "value_high"} <= matched.keys():
            continue  # the model's midpoint of a quoted range (P-01 may not calculate): code computes it below
        if m is None:
            return Rejected("V1-NUM", f"{name}={v} is not a number in the quote")
        matched[name] = m
    for m in matched.values():
        if not _unit_ok(p.unit, m, quote):
            return Rejected("V1-UNIT", f"unit {p.unit} disagrees with the quote around {quote[m.start : m.end]!r}")
        pos = start - s0 + m.start  # the number's place in its sentence
        _, a, _ = _clause_of(sentence, pos)  # the per-share words must be in the number's own clause (M5 review R3)
        if PER_SHARE_AFTER.match(sentence[pos - m.start + m.end :]) or PER_SHARE_BEFORE.search(sentence[a:pos]):
            return Rejected("V1-TYPE", "a per-share amount is a price field")
        if price_context(sentence, pos):
            return Rejected("V1-TYPE", "share-price, valuation or capital-return facts are not stored (prices_w)")
        if m.currency is not None and m.currency != doc.currency:  # whatever the model said (M5 review R3-F1)
            review["currency"] = own_currency_note(m.currency.upper(), doc)
    if not matched and p.fact_type in MEASURES:
        return Rejected("V1-NUM", f"a {p.fact_type} fact is a number, and the quote states none")
    if not matched and price_context(sentence, start - s0):
        return Rejected("V1-TYPE", "share-price, valuation or capital-return facts are not stored (prices_w)")
    if p.fact_type == "price_increase" and not pricing_word(sentence):
        return Rejected("V1-TYPE", "a price increase names a price of the business, not only a share price")
    if p.currency and p.currency.strip().upper() not in CURRENCY_NAMES.get(doc.currency, frozenset()):
        review["currency"] = own_currency_note(p.currency, doc)

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
    if as_of > doc.published + timedelta(days=1):  # a delivery or effective date: the fact is as of publication
        as_of = doc.published
    period: Period | None = resolve(p.period_label, doc.fye, as_of)
    if p.period_label and period is None and p.fact_type in PERIOD_REQUIRED:
        review["period"] = f"period {p.period_label!r} not resolvable"
    elif period is not None and abs((period.end - as_of).days) > PLAUSIBLE_DAYS:
        review["period"] = f"period {p.period_label!r} ends {period.end}, more than 10 years from {as_of}"
    elif p.fact_type in PERIOD_REQUIRED and period is None:
        review["period"] = "capex guidance/reported needs a period"
    elif p.fact_type in GUIDANCE and period is not None and period.end < doc.published and not p.withdrawn:
        review["period"] = f"guidance for a period that ended {period.end} (published {doc.published})"

    slug = period_slug(period, doc.fye) if period is not None else None
    key, key_ok = keys.check(p.fact_type, p.subject_key, p.subject, slug)
    if not key_ok:
        review["subject_key"] = f"{p.subject_key!r} is not in config/subject_keys.yaml for {p.fact_type}"
    problem = kind_problem(p.fact_type, key, quote)
    if problem is not None:
        fails, why = problem
        if fails:
            return Rejected("V1-KIND", why)
        review["kind"] = why

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
        unit=stored_unit(p.unit, matched),
        currency=next((m.currency.upper() for m in matched.values() if m.currency), None) or p.currency,
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
