"""Canonical text (Appendix F.3): every character offset in documents, facts and risk changes refers to it.

- Unicode NFC; non-breaking and other Unicode spaces count as whitespace;
- inside a line, whitespace runs collapse to one space, and lines are trimmed;
- a paragraph's lines stay separated by "\\n"; paragraphs are separated by exactly "\\n\\n" (a blank line or more in
  the input is one paragraph break); no leading or trailing blank lines.
Deterministic and idempotent: canonical(canonical(x)) == canonical(x).
"""

from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"[^\S\n]+")  # whitespace except newlines (includes NBSP, thin space, tabs)
_BREAK = re.compile(r"\n[^\S\n]*\n(?:[^\S\n]*\n)*")  # one or more blank lines
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))  # zero-width chars, soft hyphen


def canonical(text: str) -> str:
    t = unicodedata.normalize("NFC", text).translate(_ZERO_WIDTH)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n").replace(" ", "\n")
    t = t.replace(" ", "\n\n")
    paragraphs = []
    for para in _BREAK.split(t):
        lines = [_SPACE.sub(" ", line).strip() for line in para.split("\n")]
        lines = [line for line in lines if line]
        if lines:
            paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)


def join_blocks(blocks: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Canonical blocks (paragraphs, table rows grouped as one paragraph, pages) joined with "\\n\\n", and each
    block's (char_start, char_end) in the result. Empty blocks are dropped (their span is (start, start))."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    for b in blocks:
        c = canonical(b)
        if not c:
            spans.append((pos, pos))
            continue
        if out:
            pos += 2
        spans.append((pos, pos + len(c)))
        out.append(c)
        pos += len(c)
    return "\n\n".join(out), spans
