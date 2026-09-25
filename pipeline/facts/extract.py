"""P-01 fact extraction (Appendix F.4 step 3): one chunk -> the router -> proposed facts.

The response is checked field by field here (not trusted): an item with an unknown fact type or unit, a missing
quote, a non-numeric value or a confidence outside 0-1 is rejected with a reason. Grounding and the number, unit,
period and key checks follow in verify1.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from pipeline.facts.keys import vocabulary
from pipeline.facts.types import FACT_TYPES, SCALE_WORDS, UNITS, definitions_text
from pipeline.llm.prompt import PromptInput, nullable, obj

FACT_SCHEMA = obj(
    {
        "fact_type": {"type": "string", "enum": list(FACT_TYPES)},
        "subject": {"type": "string"},
        "subject_key": {"type": "string"},
        "value": nullable("number"),
        "value_low": nullable("number"),
        "value_high": nullable("number"),
        "unit": {"type": "string", "enum": list(UNITS)},
        "currency": nullable("string"),
        "scale_word": nullable("string", enum=list(SCALE_WORDS)),
        "period_label": nullable("string"),
        "as_of": nullable("string"),
        "counterparty": nullable("string"),
        "location": nullable("string"),
        "withdrawn": {"type": "boolean"},
        "quote": {"type": "string"},
        "confidence": {"type": "number"},
    }
)


@dataclass(frozen=True)
class ExtractInput(PromptInput):
    prompt_id: ClassVar[str] = "P-01"
    name: str
    ticker: str
    fye: str
    kind: str
    title: str
    published_at: str
    section: str
    char_start: int
    char_end: int
    text: str

    def variables(self) -> dict[str, str]:
        keys, _, _ = vocabulary()
        return {
            "fact_types_with_definitions": definitions_text(),
            "subject_keys": ", ".join(keys),
            "name": self.name,
            "ticker": self.ticker,
            "fye": self.fye,
            "kind": self.kind,
            "title": self.title,
            "published_at": self.published_at,
            "section": self.section,
            "char_start": str(self.char_start),
            "char_end": str(self.char_end),
            "text": self.text,
        }

    def schema(self) -> dict[str, Any]:
        return obj({"facts": {"type": "array", "items": FACT_SCHEMA}})


@dataclass(frozen=True)
class Proposed:
    fact_type: str
    subject: str
    subject_key: str
    value: Decimal | None
    value_low: Decimal | None
    value_high: Decimal | None
    unit: str
    currency: str | None
    scale_word: str | None
    period_label: str | None
    as_of: date | None
    counterparty: str | None
    location: str | None
    withdrawn: bool
    quote: str
    confidence: Decimal


def _num(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float | str):
        raise ValueError("not a number")
    try:
        d = Decimal(str(v))
    except InvalidOperation as e:
        raise ValueError("not a number") from e
    if not d.is_finite():
        raise ValueError("not a finite number")
    return d


def _str(v: Any, limit: int | None = None) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("not a string")
    s = v.strip()
    return (s[:limit] if limit else s) or None


def _date(v: Any) -> date | None:
    s = _str(v)
    if s is None:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None  # an unparseable as_of falls back to the publication date (V1-PERIOD notes it)


def parse_item(item: Any) -> Proposed:
    if not isinstance(item, dict):
        raise ValueError("item is not an object")
    fact_type = item.get("fact_type")
    if fact_type not in FACT_TYPES:
        raise ValueError(f"unknown fact_type {fact_type!r}")
    unit = item.get("unit")
    if unit not in UNITS:
        raise ValueError(f"unknown unit {unit!r}")
    quote = _str(item.get("quote"))
    if not quote:
        raise ValueError("no quote")
    scale = _str(item.get("scale_word"))
    if scale is not None and scale.lower() not in SCALE_WORDS:
        raise ValueError(f"unknown scale_word {scale!r}")
    conf = _num(item.get("confidence"))
    if conf is None or not Decimal(0) <= conf <= Decimal(1):
        raise ValueError("confidence outside 0-1")
    withdrawn = item.get("withdrawn", False)
    if not isinstance(withdrawn, bool):
        raise ValueError("withdrawn is not a boolean")
    return Proposed(
        fact_type=str(fact_type),
        subject=_str(item.get("subject"), 120) or str(fact_type),
        subject_key=_str(item.get("subject_key")) or "",
        value=_num(item.get("value")),
        value_low=_num(item.get("value_low")),
        value_high=_num(item.get("value_high")),
        unit=str(unit),
        currency=_str(item.get("currency")),
        scale_word=scale.lower() if scale else None,
        period_label=_str(item.get("period_label")),
        as_of=_date(item.get("as_of")),
        counterparty=_str(item.get("counterparty"), 200),
        location=_str(item.get("location"), 200),
        withdrawn=withdrawn,
        quote=quote,
        confidence=conf.quantize(Decimal("0.01")),
    )


def parse(content: dict[str, Any]) -> tuple[list[Proposed], list[str]]:
    """The facts of a P-01 answer and one reason per rejected item."""
    items = content.get("facts")
    if not isinstance(items, list):
        return [], ["answer has no facts list"]
    out, rejects = [], []
    for k, item in enumerate(items):
        try:
            out.append(parse_item(item))
        except ValueError as e:
            rejects.append(f"item {k}: {e}")
    return out, rejects
