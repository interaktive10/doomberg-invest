"""HTML (EDGAR filings, inline XBRL, press releases) -> canonical text and section_map (Appendix F.3).

- script, style, head and hidden elements (style display:none, the `hidden` attribute, ix:header) are dropped;
- block elements end a paragraph; <br> is a line break inside one; headings are paragraphs of their own;
- a table becomes one paragraph whose lines are its rows, `cell | cell | cell` in row order (empty cells dropped);
- section_map: 10-K/10-Q items by heading regexes (Item 1A Risk Factors, Item 7 / Part I Item 2 MD&A, Item 8 /
  Item 1 financial statements) and notes by title keywords (Commitments, Contingencies, Leases, Revenue, Debt,
  Subsequent Events). A table of contents repeats the headings, so each section keeps its longest span.
Standard library only (html.parser), so the result is deterministic across environments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from pipeline.facts.canonical import join_blocks

BLOCK = frozenset(
    "p div section article header footer main aside blockquote pre ul ol li dl dt dd h1 h2 h3 h4 h5 h6 hr center "
    "address figure figcaption form fieldset nav body html title caption".split()
)
SKIP = frozenset({"script", "style", "head", "noscript", "template", "ix:header", "svg", "object"})
VOID = frozenset("br img hr meta link input col area base embed param source track wbr".split())
_HIDDEN = re.compile(r"display\s*:\s*none", re.I)


@dataclass
class _Table:
    lines: list[str] = field(default_factory=list)
    row: list[str] | None = None
    cell: list[str] | None = None


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.cur: list[str] = []
        self.stack: list[tuple[str, bool]] = []  # (tag, hidden)
        self.tables: list[_Table] = []

    # -- helpers
    def _hidden(self) -> bool:
        return any(h for _, h in self.stack)

    def _flush(self) -> None:
        text = "".join(self.cur)
        self.cur = []
        if text.strip():
            self.blocks.append(text)

    def _end_cell(self, t: _Table) -> None:
        if t.cell is not None:
            text = " ".join("".join(t.cell).split())
            if text and t.row is not None:
                t.row.append(text)
            t.cell = None

    def _end_row(self, t: _Table) -> None:
        self._end_cell(t)
        if t.row:
            t.lines.append(" | ".join(t.row))
        t.row = None

    # -- parser callbacks
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        hidden = tag in SKIP or "hidden" in a or bool(_HIDDEN.search(a.get("style", "")))
        if tag not in VOID:
            self.stack.append((tag, hidden))
        if self._hidden():
            return
        t = self.tables[-1] if self.tables else None
        if tag == "table":
            if t is not None:
                self._end_row(t)  # a nested table: its rows follow the outer table's
            else:
                self._flush()
            self.tables.append(_Table())
        elif tag == "tr" and t is not None:
            self._end_row(t)
            t.row = []
        elif tag in {"td", "th"} and t is not None:
            self._end_cell(t)
            if t.row is None:
                t.row = []
            t.cell = []
        elif tag == "br":
            self._text("\n")
        elif tag in BLOCK:
            if t is not None and t.cell is not None:
                t.cell.append(" ")
            elif t is None:
                self._flush()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        was_hidden = self._hidden()
        if any(s == tag for s, _ in self.stack):
            while self.stack:
                s, _ = self.stack.pop()
                if s == tag:
                    break
        if was_hidden:
            return
        t = self.tables[-1] if self.tables else None
        if tag == "table" and t is not None:
            self._end_row(t)
            self.tables.pop()
            if self.tables:
                self.tables[-1].lines.extend(t.lines)
            elif t.lines:
                self.blocks.append("\n".join(t.lines))
        elif tag == "tr" and t is not None:
            self._end_row(t)
        elif tag in {"td", "th"} and t is not None:
            self._end_cell(t)
        elif tag in BLOCK and t is None:
            self._flush()

    def _text(self, data: str) -> None:
        t = self.tables[-1] if self.tables else None
        if t is not None:
            if t.cell is not None:
                t.cell.append(" " if data == "\n" else data)
            elif data.strip():  # text directly inside <table>/<tr>: keep it as its own cell
                if t.row is None:
                    t.row = []
                t.row.append(" ".join(data.split()))
        else:
            self.cur.append(data)

    def handle_data(self, data: str) -> None:
        if self._hidden() or not data:
            return
        pre = any(s == "pre" for s, _ in self.stack)
        self._text(data if pre else data.replace("\n", " ").replace("\r", " "))

    def close(self) -> None:
        super().close()
        while self.tables:
            t = self.tables.pop()
            self._end_row(t)
            if self.tables:
                self.tables[-1].lines.extend(t.lines)
            elif t.lines:
                self.blocks.append("\n".join(t.lines))
        self._flush()


@dataclass(frozen=True)
class Normalized:
    text: str
    section_map: list[dict[str, object]]
    page_map: list[dict[str, int]]


def html_blocks(html: str) -> list[str]:
    p = _Parser()
    p.feed(html)
    p.close()
    return p.blocks


# ---------------------------------------------------------------- section map

_SEP = r"\s*[.:\-–—]?\s*"
ITEM_HEADINGS: list[tuple[str, re.Pattern[str]]] = [
    ("risk_factors", re.compile(rf"^item\s*1a{_SEP}risk\s+factors\b", re.I)),
    ("mdna", re.compile(rf"^item\s*[72]{_SEP}management[’']?s\s+discussion\s+and\s+analysis\b", re.I)),
    (
        "financial_statements",
        re.compile(rf"^item\s*[81]{_SEP}(?:consolidated\s+|condensed\s+)*financial\s+statements\b", re.I),
    ),  # fmt: skip
    ("other_item", re.compile(rf"^item\s*\d{{1,2}}[a-c]?{_SEP}\S", re.I)),
]
NOTE_TOPICS = ("commitments", "contingencies", "leases", "revenue", "debt", "subsequent events")
_NOTE = re.compile(rf"^(?:note\s+\d{{1,2}}{_SEP}|\d{{1,2}}\.\s+)(?P<title>[a-z][a-z ,&\-–—()]*)$", re.I)
MAX_HEADING_CHARS = 120


def _first_line(block: str) -> str | None:
    line = block.split("\n", 1)[0].strip()
    return None if len(line) > MAX_HEADING_CHARS or "|" in line else line


def _item(block: str) -> str | None:
    line = _first_line(block)
    if line is None:
        return None
    return next((name for name, pat in ITEM_HEADINGS if pat.search(line)), None)


def _note(block: str) -> str | None:
    """A numbered note heading ("Note 9 — Leases", "9. Commitments and Contingencies") on a named topic."""
    line = _first_line(block)
    m = _NOTE.match(line) if line else None
    if m is None:
        return None
    title = m.group("title").lower()
    return next(("note_" + t.replace(" ", "_") for t in NOTE_TOPICS if t in title), "note_other")


def section_map(blocks: list[str], spans: list[tuple[int, int]], text_len: int) -> list[dict[str, object]]:
    """Item sections run from their heading to the next item heading; per item the longest span wins (a table of
    contents repeats every heading with a few characters under it). Note sections are numbered note headings inside
    the financial statements, each running to the next note heading."""
    heads = [(spans[i][0], name) for i, b in enumerate(blocks) if (name := _item(b)) is not None]
    best: dict[str, tuple[int, int]] = {}
    for k, (start, name) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else text_len
        if name != "other_item" and (name not in best or end - start > best[name][1] - best[name][0]):
            best[name] = (start, end)
    out: list[dict[str, object]] = [{"name": n, "char_start": s, "char_end": e} for n, (s, e) in best.items()]
    fs = best.get("financial_statements")
    if fs is not None:
        notes = [(spans[i][0], name) for i, b in enumerate(blocks)
                 if fs[0] < spans[i][0] < fs[1] and (name := _note(b)) is not None]  # fmt: skip
        for k, (start, name) in enumerate(notes):
            end = notes[k + 1][0] if k + 1 < len(notes) else fs[1]
            if name != "note_other":
                out.append({"name": name, "char_start": start, "char_end": end})
    return sorted(out, key=lambda d: (int(str(d["char_start"])), str(d["name"])))


def normalize_html(html: str) -> Normalized:
    blocks = html_blocks(html)
    text, spans = join_blocks(blocks)
    return Normalized(text, section_map(blocks, spans, len(text)), [])


def normalize_plain(raw: str) -> Normalized:
    blocks = re.split(r"\n\s*\n", raw)
    text, spans = join_blocks(blocks)
    return Normalized(text, section_map(blocks, spans, len(text)), [])
