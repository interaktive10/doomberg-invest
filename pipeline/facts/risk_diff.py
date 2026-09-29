"""Risk-factor diffs (Appendix F.6) between consecutive Item 1A sections of the same form (10-K to 10-K, 10-Q to 10-Q):

- split into paragraphs; match with rapidfuzz token_set_ratio, one to one, best pairs first: >= 90 same, 60-89
  `modified`, unmatched -> `added` (new) or `removed` (old);
- P-03 tags each changed paragraph; only the allowed tags are kept, and only changes with at least one tag are
  stored (the desk follows AI, data-center, power and supply-chain risk; docs/DECISIONS.log);
- the stored text is <= 25 words, chosen by code: the sentence with the largest change (for a modified paragraph,
  the new sentence least like any old one; for an added or removed one, its first sentence).
A 10-Q whose Item 1A only points back to the 10-K (fewer than MIN_PARAGRAPHS paragraphs) isn't compared.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from rapidfuzz import fuzz

from pipeline.llm.prompt import PromptInput, obj

TAGS = ("ai_demand", "data_center", "power_supply", "grid_interconnection", "supply_chain", "customer_concentration",
        "export_controls", "financing", "construction", "regulation")  # fmt: skip
SAME, MODIFIED = 90, 60
MIN_PARAGRAPH_CHARS, MIN_PARAGRAPHS, QUOTE_WORDS = 80, 5, 25
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


@dataclass(frozen=True)
class Para:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Change:
    kind: str  # added | removed | modified
    old: Para | None
    new: Para | None
    similarity: float | None


def paragraphs(text: str, start: int, end: int) -> list[Para]:
    out, pos = [], start
    for block in text[start:end].split("\n\n"):
        b_start = pos
        pos += len(block) + 2
        if len(block) >= MIN_PARAGRAPH_CHARS and "|" not in block.split("\n", 1)[0]:
            out.append(Para(b_start, b_start + len(block), block))
    return out


def compare(old: Sequence[Para], new: Sequence[Para]) -> list[Change]:
    pairs = sorted(((fuzz.token_set_ratio(o.text, n.text), i, j) for i, o in enumerate(old) for j, n in enumerate(new)),
                   reverse=True)  # fmt: skip
    used_old: set[int] = set()
    used_new: set[int] = set()
    out: list[Change] = []
    for score, i, j in pairs:
        if score < MODIFIED:
            break
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        if score < SAME:
            out.append(Change("modified", old[i], new[j], score / 100))
    out += [Change("added", None, n, None) for j, n in enumerate(new) if j not in used_new]
    out += [Change("removed", o, None, None) for i, o in enumerate(old) if i not in used_old]
    return out


def _sentences(p: Para) -> list[tuple[int, int, str]]:
    """(start, end, text) of each sentence, offsets absolute and trimmed of surrounding whitespace."""
    out = []
    for m in _SENTENCE.finditer(p.text):
        raw = m.group(0)
        s = raw.strip()
        if s:
            k = p.start + m.start() + len(raw) - len(raw.lstrip())
            out.append((k, k + len(s), s))
    return out


def quote(c: Change) -> tuple[str, int | None, int | None]:
    """(text of at most 25 words, char_start, char_end): the sentence with the largest change, cut to 25 words. The
    text is the document's own characters at those offsets (into the new document; None for a removal)."""
    para = c.new if c.new is not None else c.old
    assert para is not None
    sents = _sentences(para)
    if c.kind == "modified" and c.old is not None:
        olds = [s[2] for s in _sentences(c.old)]
        sents.sort(key=lambda s: max((fuzz.token_set_ratio(s[2], o) for o in olds), default=0))
    start, end, text = sents[0]
    m = re.match(rf"(?:\S+\s+){{{QUOTE_WORDS - 1}}}\S+", text)
    if m is not None:
        text, end = text[: m.end()], start + m.end()
    if c.kind == "removed":
        return text, None, None
    return text, start, end


@dataclass(frozen=True)
class RiskTagInput(PromptInput):
    prompt_id: ClassVar[str] = "P-03"
    items: tuple[tuple[str, str], ...]  # (id, paragraph text)

    def variables(self) -> dict[str, str]:
        return {
            "tags": json.dumps(list(TAGS)),
            "id_text_list": json.dumps([{"id": i, "text": t} for i, t in self.items], ensure_ascii=False),
        }

    def schema(self) -> dict[str, Any]:
        item = obj(
            {"id": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string", "enum": list(TAGS)}}}
        )
        return obj({"items": {"type": "array", "items": item}})


def parse_tags(content: dict[str, Any], ids: Sequence[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {i: [] for i in ids}
    items = content.get("items")
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and it.get("id") in out and isinstance(it.get("tags"), list):
                out[str(it["id"])] = sorted({t for t in it["tags"] if t in TAGS})
    return out
