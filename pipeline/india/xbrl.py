"""Minimal XBRL instance reader for NSE/BSE/SEBI filings (results, shareholding patterns).

Namespace-agnostic: facts are keyed by local element name, so the legacy results taxonomy (in-bse-fin, 2020),
SEBI's integrated-filing taxonomy (in-capmkt, 2025+) and the shareholding taxonomy all read the same way.
DTDs and entity declarations are refused (no entity-expansion attacks); ElementTree never fetches external entities.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
_SKIP_NS = ("http://www.xbrl.org/2003/instance", "http://www.xbrl.org/2003/linkbase")


class XbrlError(ValueError):
    pass


@dataclass(frozen=True)
class Context:
    id: str
    start: date | None  # None for an instant
    end: date
    dims: tuple[tuple[str, str], ...]  # (axis, member): explicit members by local name, typed members by value

    @property
    def days(self) -> int | None:
        return None if self.start is None else (self.end - self.start).days + 1


@dataclass(frozen=True)
class Fact:
    name: str  # local element name
    context: Context
    value: str
    unit: str | None

    @property
    def number(self) -> Decimal | None:
        if self.unit is None:
            return None
        try:
            return Decimal(self.value.strip().replace(",", ""))
        except InvalidOperation:
            return None


@dataclass
class Instance:
    contexts: dict[str, Context]
    facts: dict[str, list[Fact]] = field(default_factory=lambda: defaultdict(list))
    # Facts whose contextRef names a context the file never defines (some of NSE's legacy results files of January
    # 2023): context id -> (local name, text, unit), for a caller that knows what the context was (results_xbrl).
    orphans: dict[str, list[tuple[str, str, str | None]]] = field(default_factory=lambda: defaultdict(list))

    def adopt(self, ctx: Context) -> None:
        """Define a context the file left out: its orphan facts become facts."""
        self.contexts[ctx.id] = ctx
        for name, value, unit in self.orphans.pop(ctx.id, []):
            self.facts[name].append(Fact(name, ctx, value, unit))

    def text(self, name: str) -> str | None:
        """First non-empty text value of a non-numeric fact (metadata such as Symbol, NatureOf…)."""
        for f in self.facts.get(name, []):
            if f.value.strip():
                return f.value.strip()
        return None

    def number(
        self, name: str, start: date | None, end: date, dims: tuple[tuple[str, str], ...] = ()
    ) -> Decimal | None:
        """The numeric fact for exactly this period (start None = instant) and dimensions."""
        for f in self.facts.get(name, []):
            c = f.context
            if c.start == start and c.end == end and c.dims == dims:
                n = f.number
                if n is not None:
                    return n
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _date(s: str | None) -> date:
    if not s:
        raise XbrlError("context without a date")
    return date.fromisoformat(s.strip()[:10])


def safe_parse(raw: bytes | str) -> ET.Element:
    body = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    if re.search(rb"<!DOCTYPE|<!ENTITY", body, re.IGNORECASE):
        raise XbrlError("XML with a DTD/entity declaration refused")
    try:
        return ET.fromstring(body)  # noqa: S314 — DTDs refused above; the input is an exchange filing
    except ET.ParseError as e:
        raise XbrlError(f"XML does not parse: {e}") from e


def parse_instance(raw: bytes | str) -> Instance:
    root = safe_parse(raw)
    if _local(root.tag) != "xbrl":
        raise XbrlError(f"not an XBRL instance: <{_local(root.tag)}>")
    contexts: dict[str, Context] = {}
    for c in root.iter(XBRLI + "context"):
        period = c.find(XBRLI + "period")
        if period is None:
            continue
        instant = period.find(XBRLI + "instant")
        if instant is not None:
            start, end = None, _date(instant.text)
        else:
            start, end = _date(period.findtext(XBRLI + "startDate")), _date(period.findtext(XBRLI + "endDate"))
        explicit = [(_local(m.get("dimension", "")), _local((m.text or "").strip()))
                    for m in c.iter(XBRLDI + "explicitMember")]  # fmt: skip
        typed = [
            (_local(m.get("dimension", "")), "".join(m.itertext()).strip()) for m in c.iter(XBRLDI + "typedMember")
        ]
        dims = tuple(sorted(explicit + typed))
        contexts[c.get("id", "")] = Context(c.get("id", ""), start, end, dims)
    inst = Instance(contexts)
    for el in root:
        tag = el.tag
        ns = tag[1:].split("}", 1)[0] if tag.startswith("{") else ""
        if ns in _SKIP_NS or not isinstance(tag, str):
            continue
        ref = el.get("contextRef", "")
        ctx = contexts.get(ref)
        if ctx is None:
            if ref:
                inst.orphans[ref].append((_local(tag), el.text or "", el.get("unitRef")))
            continue
        inst.facts[_local(tag)].append(Fact(_local(tag), ctx, el.text or "", el.get("unitRef")))
    return inst
