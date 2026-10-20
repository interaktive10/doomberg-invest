"""Chunk selection and the keyword prefilter (Appendix F.4 steps 1-2).

- 10-K/10-Q: the MD&A and the notes named in F.3 (Commitments, Contingencies, Leases, Revenue, Debt, Subsequent
  Events); when no MD&A heading is found, the whole document. EX-99.x, press releases, transcripts and other
  documents: the whole document. Presentations: page by page. Risk factors aren't extracted (F.4 left them to the
  risk diff, which no longer runs: docs/SPEC_ISSUES.md 50).
- Chunks are at most MAX_TOKENS tokens (4 characters a token) with OVERLAP_TOKENS of overlap, cut at a paragraph,
  line or sentence end when one is near; each carries its absolute char_start in the canonical text.
- Prefilter: the number of keyword hits from config/terms.yaml; only chunks scoring >= min_score (3) go to P-01.
  All-caps keywords (AI, MW, GW, GPU) match case-sensitively, the rest case-insensitively, on word boundaries, with
  an optional plural ending ("leases", "transformers", "GPUs").
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from pipeline.settings import REPO_ROOT

CHARS_PER_TOKEN = 4
MAX_TOKENS, OVERLAP_TOKENS = 10_000, 400
MAX_CHARS, OVERLAP_CHARS = MAX_TOKENS * CHARS_PER_TOKEN, OVERLAP_TOKENS * CHARS_PER_TOKEN
FILING_KINDS = frozenset({"10-K", "10-Q"})
EXTRACT_SECTIONS = ("mdna", "note_commitments", "note_contingencies", "note_leases", "note_revenue", "note_debt",
                    "note_subsequent_events")  # fmt: skip


@dataclass(frozen=True)
class Chunk:
    text: str
    char_start: int
    section: str | None = None
    page: int | None = None

    @property
    def char_end(self) -> int:
        return self.char_start + len(self.text)


def _cut(text: str, lo: int, hi: int) -> int:
    """A good end for a window [lo, hi): the last paragraph/line/sentence end in its final fifth, else hi."""
    if hi >= len(text):
        return len(text)
    floor = lo + (hi - lo) * 4 // 5
    for sep in ("\n\n", "\n", ". "):
        k = text.rfind(sep, floor, hi)
        if k > floor:
            return k + len(sep.rstrip(" ")) if sep == ". " else k
    return hi


def split(text: str, start: int, end: int, section: str | None = None, page: int | None = None,
          max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:  # fmt: skip
    out: list[Chunk] = []
    lo = start
    while lo < end:
        hi = _cut(text, lo, min(end, lo + max_chars)) if lo + max_chars < end else end
        piece = text[lo:hi]
        if piece.strip():
            out.append(Chunk(piece, lo, section, page))
        if hi >= end:
            break
        lo = max(hi - overlap, lo + 1)
    return out


def select(kind: str, text: str, section_map: Sequence[Mapping[str, Any]],
           page_map: Sequence[Mapping[str, int]]) -> list[Chunk]:  # fmt: skip
    if kind in FILING_KINDS:
        spans = [s for s in section_map if s["name"] in EXTRACT_SECTIONS]
        if any(s["name"] == "mdna" for s in spans):
            out = []
            for s in sorted(spans, key=lambda s: int(s["char_start"])):
                out += split(text, int(s["char_start"]), int(s["char_end"]), str(s["name"]))
            return out
        out, pos = [], 0  # no MD&A heading found: the whole document except its risk factors (above)
        for s in sorted((s for s in section_map if s["name"] == "risk_factors"), key=lambda s: int(s["char_start"])):
            out += split(text, pos, int(s["char_start"]))
            pos = max(pos, int(s["char_end"]))
        return out + split(text, pos, len(text))
    if kind == "presentation" and page_map:
        out = []
        for p in page_map:
            out += split(text, p["char_start"], p["char_end"], None, p["page"])
        return out
    return split(text, 0, len(text))


@cache
def _terms(root: Path = REPO_ROOT) -> tuple[int, tuple[re.Pattern[str], ...]]:
    doc = yaml.safe_load((root / "config" / "terms.yaml").read_text(encoding="utf-8"))["prefilter"]
    pats = []
    for kw in doc["keywords"]:
        flags = 0 if kw.isupper() else re.I
        pats.append(re.compile(rf"(?<!\w){re.escape(kw)}(?:s|es)?(?!\w)", flags))  # plurals count: "leases"
    return int(doc["min_score"]), tuple(pats)


def score(text: str) -> int:
    return sum(len(p.findall(text)) for p in _terms()[1])


def prefilter(chunks: Sequence[Chunk]) -> list[Chunk]:
    need = _terms()[0]
    return [c for c in chunks if score(c.text) >= need]
