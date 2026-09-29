"""Counterparties -> entities -> links (Appendix F.2, P-02): the counterparty graph of the Capex Desk (§4.11).

For each verified fact with a counterparty, the candidates are the SEC company list plus the existing entities, top
5 by rapidfuzz token_set_ratio on normalized names; P-02 picks one or none (it may not invent an entity). A pick of a
company becomes (or reuses) that company's entity (with its CIK); no pick creates a new entity with P-02's kind. The
fact's relation (types.RELATION) makes the link from the fact's company to the entity. When the router defers, the
facts stay unlinked and a later run links them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from rapidfuzz import fuzz, process

from pipeline.llm.prompt import PromptInput, nullable, obj

KINDS = ("company", "utility", "developer", "government", "other")
TOP_K = 5
SUFFIXES = re.compile(
    r"\b(?:the|inc|incorporated|corp|corporation|co|company|llc|l\.l\.c|ltd|limited|plc|lp|l\.p|holdings?|group|"
    r"sa|ag|nv|se|pvt|private)\b\.?",
    re.I,
)


def normalize_name(name: str) -> str:
    s = SUFFIXES.sub(" ", name.lower().replace("&", " and "))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


@dataclass(frozen=True)
class Candidate:
    id: str  # "c:<company uuid>" or "e:<entity uuid>"
    name: str


def candidates_for(name: str, pool: Sequence[Candidate], k: int = TOP_K) -> list[Candidate]:
    norm = normalize_name(name)
    if not norm or not pool:
        return []
    choices = [normalize_name(c.name) for c in pool]
    hits = process.extract(norm, choices, scorer=fuzz.token_set_ratio, limit=k)
    return [pool[i] for _, score, i in hits if score >= 60]


@dataclass(frozen=True)
class EntityInput(PromptInput):
    prompt_id: ClassVar[str] = "P-02"
    names: tuple[str, ...]
    candidates: tuple[tuple[str, str], ...]  # (id, name)

    def variables(self) -> dict[str, str]:
        return {
            "names": json.dumps(list(self.names), ensure_ascii=False),
            "candidates": json.dumps([{"id": i, "name": n} for i, n in self.candidates], ensure_ascii=False),
        }

    def schema(self) -> dict[str, Any]:
        item = obj({"name": {"type": "string"}, "candidate_id": nullable("string"),
                    "kind": {"type": "string", "enum": list(KINDS)}, "confidence": {"type": "number"}})  # fmt: skip
        return obj({"matches": {"type": "array", "items": item}})


@dataclass(frozen=True)
class Match:
    name: str
    candidate_id: str | None
    kind: str


def parse(content: dict[str, Any], names: Sequence[str], allowed: set[str]) -> dict[str, Match]:
    """name -> Match for the names asked about; a candidate_id outside the offered list counts as none."""
    out: dict[str, Match] = {}
    items = content.get("matches")
    if not isinstance(items, list):
        return out
    wanted = set(names)
    for m in items:
        if not isinstance(m, dict) or m.get("name") not in wanted:
            continue
        cid = m.get("candidate_id")
        kind = str(m["kind"]) if m.get("kind") in KINDS else "other"
        out[str(m["name"])] = Match(str(m["name"]), cid if isinstance(cid, str) and cid in allowed else None, kind)
    return out
