"""Grounding (Appendix F.4 step 4): find a model's quote in the chunk it came from.

1. exact match on canonical text;
2. else a whitespace/punctuation-insensitive match (Unicode punctuation, whitespace and the `|` table separator are
   ignored on both sides; letters, digits and symbols such as $ and % must match exactly, case included);
3. no fuzzy matching: not found -> rejected.
The fact's quote becomes the canonical text between the returned offsets, so V1-QUOTE holds by construction.
"""

from __future__ import annotations

import unicodedata

from pipeline.facts.canonical import canonical

MIN_QUOTE, MAX_QUOTE = 5, 600  # facts.quote check (Appendix F.2)


def _kept(c: str) -> bool:
    return not (c.isspace() or c == "|" or unicodedata.category(c).startswith("P"))


def ground(quote: str, text: str, lo: int = 0, hi: int | None = None) -> tuple[int, int] | None:
    """Absolute (char_start, char_end) of `quote` inside text[lo:hi], or None."""
    hi = len(text) if hi is None else hi
    q = canonical(quote)
    if not q:
        return None
    i = text.find(q, lo, hi)
    if i >= 0:
        return i, i + len(q)
    nq = "".join(c for c in q if _kept(c))
    if not nq:
        return None
    idx = [k for k in range(lo, hi) if _kept(text[k])]
    hay = "".join(text[k] for k in idx)
    j = hay.find(nq)
    if j < 0:
        return None
    return idx[j], idx[j + len(nq) - 1] + 1


def grounded_quote(quote: str, text: str, lo: int = 0, hi: int | None = None) -> tuple[int, int, str] | None:
    """(start, end, the canonical text there) when grounded and the span is a storable quote (5-600 chars)."""
    span = ground(quote, text, lo, hi)
    if span is None:
        return None
    s, e = span
    if not MIN_QUOTE <= e - s <= MAX_QUOTE:
        return None
    return s, e, text[s:e]
