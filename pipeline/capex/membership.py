"""Capex Desk memberships (BRIEF §4.11): which companies belong to which demand categories.

- US: proposed from the industry map (config/categories.yaml): a capex-desk company by its Appendix H seed group,
  another company in the ledger by its SIC code.
- India: P-06 on the company's own text (exchange announcements and annual-report excerpts): each category must come
  with an exact quote, grounded like Appendix F (exact, then whitespace/punctuation-insensitive; never fuzzy);
  ungrounded entries are dropped, as are categories outside the list. A stated export share or overseas order book
  is returned the same way and becomes an `export_exposure` fact through Verify-1.
- Every membership starts `proposed`; only `confirmed` ones (Manzoor, in the web app) count for S11 (M5-06).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from pipeline.facts.ground import grounded_quote
from pipeline.llm.prompt import PromptInput, nullable, obj

MAX_TEXT_CHARS = 30_000  # the P-06 text: announcement summaries and annual-report pages that pass the prefilter
MAX_QUOTE_WORDS = 60


@dataclass(frozen=True)
class CrossBorderInput(PromptInput):
    prompt_id: ClassVar[str] = "P-06"
    name: str
    symbol: str
    categories: tuple[str, ...]
    text: str

    def variables(self) -> dict[str, str]:
        return {"categories": ", ".join(self.categories), "name": self.name, "symbol": self.symbol,
                "text": self.text[:MAX_TEXT_CHARS]}  # fmt: skip

    def schema(self) -> dict[str, Any]:
        cat = obj({"category": {"type": "string", "enum": list(self.categories)}, "quote": {"type": "string"},
                   "confidence": {"type": "number"}})  # fmt: skip
        exp = obj({"share_pct": nullable("number"), "overseas_order_book": nullable("string"),
                   "quote": nullable("string")})  # fmt: skip
        return obj({"categories": {"type": "array", "items": cat}, "export_exposure": exp})


@dataclass(frozen=True)
class Grounded:
    category: str
    quote: str
    char_start: int
    char_end: int
    confidence: Decimal


@dataclass(frozen=True)
class Export:
    share_pct: Decimal | None
    order_book: str | None
    quote: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class CrossBorder:
    categories: list[Grounded]
    export: Export | None
    dropped: list[str]  # why entries were dropped


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool) or not isinstance(v, int | float | str):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def parse(content: Mapping[str, Any], text: str, allowed: Sequence[str]) -> CrossBorder:
    """Keep only categories from the list whose quote is grounded in `text` (<= 60 words); the best-grounded quote
    per category wins (highest confidence)."""
    kept: dict[str, Grounded] = {}
    dropped: list[str] = []
    items = content.get("categories")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            dropped.append("item is not an object")
            continue
        cat, quote = item.get("category"), item.get("quote")
        if cat not in allowed:
            dropped.append(f"category {cat!r} not in the list")
            continue
        if not isinstance(quote, str) or len(quote.split()) > MAX_QUOTE_WORDS:
            dropped.append(f"{cat}: no quote, or longer than {MAX_QUOTE_WORDS} words")
            continue
        g = grounded_quote(quote, text)
        if g is None:
            dropped.append(f"{cat}: quote not found in the text")
            continue
        conf = _dec(item.get("confidence")) or Decimal(0)
        conf = min(max(conf, Decimal(0)), Decimal(1)).quantize(Decimal("0.01"))
        if cat not in kept or conf > kept[cat].confidence:
            kept[str(cat)] = Grounded(str(cat), g[2], g[0], g[1], conf)
    export = None
    e = content.get("export_exposure")
    if isinstance(e, dict) and isinstance(e.get("quote"), str) and (e.get("share_pct") is not None
                                                                   or e.get("overseas_order_book")):  # fmt: skip
        g = grounded_quote(str(e["quote"]), text)
        if g is None:
            dropped.append("export_exposure: quote not found in the text")
        else:
            book = e.get("overseas_order_book")
            export = Export(_dec(e.get("share_pct")), str(book) if isinstance(book, str) else None, g[2], g[0], g[1])
    return CrossBorder(sorted(kept.values(), key=lambda g: g.category), export, dropped)


def us_categories(seed_group: str | None, sic: str | None, cfg: Mapping[str, Any]) -> tuple[list[str], str]:
    """US proposals from the industry map and the evidence line shown with them."""
    m = cfg["industry_map"]
    if seed_group and seed_group in m["seed_groups"]:
        return list(m["seed_groups"][seed_group]), f"Capex Desk seed group {seed_group} (BRIEF Appendix H)"
    if sic and sic in m["sic"]:
        return list(m["sic"][sic]), f"SIC {sic}"
    return [], ""


def profile_text(parts: Sequence[tuple[str, str]]) -> str:
    """The P-06 text: labelled sources ("Announcement 2026-09-18: ..."), one paragraph each."""
    return "\n\n".join(f"{label}: {body.strip()}" for label, body in parts if body.strip())


def evidence(g: Grounded) -> str:
    return json.dumps({"quote": g.quote, "confidence": str(g.confidence)}, ensure_ascii=False)
