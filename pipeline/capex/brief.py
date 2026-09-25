"""The weekly Capex brief (BRIEF §4.11), markdown for the digest: category index moves, the 10 most material new
verified facts, new links, new India cross-border memberships, and the S11 companies. Plain statements of what the
ledger recorded; no price content."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class IndexMove:
    category: str
    value: Decimal | None
    direction: str
    previous: Decimal | None
    previous_direction: str | None


@dataclass(frozen=True)
class NewFact:
    company: str
    fact_type: str
    subject_key: str
    note: str  # the diff's computed note, e.g. "$38.0B → $45.0B (+18.4%)"
    change_kind: str
    quote: str
    url: str
    materiality: Decimal  # |delta %| for a change, 100 for a new fact with a value, 0 otherwise


def _names(v: object) -> str:
    return ", ".join(str(x) for x in v) if isinstance(v, list | tuple) else ""


def _sigma(v: Decimal | None) -> str:
    return "–" if v is None else f"{v:+.2f}σ"


def material(facts: Sequence[NewFact], k: int = 10) -> list[NewFact]:
    return sorted(facts, key=lambda f: (-f.materiality, f.company, f.subject_key))[:k]


def render(
    week: date,
    moves: Sequence[IndexMove],
    facts: Sequence[NewFact],
    links: Sequence[tuple[str, str, str]],
    memberships: Sequence[tuple[str, str, str]],
    s11: Sequence[tuple[str, Mapping[str, object]]],
) -> str:
    lines = [f"## Capex brief — week ending {week:%Y-%m-%d}", "", "### Demand index", "",
             "| Category | Index | Direction | Last week |", "|---|---|---|---|"]  # fmt: skip
    for m in sorted(moves, key=lambda m: m.category):
        was = f"{_sigma(m.previous)} {m.previous_direction or ''}".strip()
        lines.append(f"| {m.category} | {_sigma(m.value)} | {m.direction} | {was} |")
    lines += ["", "### Most material new facts", ""]
    top = material(facts)
    lines += [f"- **{f.company}** · {f.fact_type} `{f.subject_key}` · {f.change_kind}: {f.note} — “{f.quote}” "
              f"([source]({f.url}))" for f in top] or ["- None this week."]  # fmt: skip
    lines += ["", "### New links", ""]
    lines += [f"- {a} → {b} ({rel})" for a, b, rel in links] or ["- None this week."]
    lines += ["", "### New India cross-border memberships (awaiting confirmation)", ""]
    lines += [f"- {name} → {cat}: “{quote}”" for name, cat, quote in memberships] or ["- None this week."]
    lines += ["", "### S11 capex propagation", ""]
    lines += [
        f"- {name}: rising {_names(inputs.get('rising'))}{'; second-order' if inputs.get('second_order') else ''}"
        for name, inputs in s11
    ] or ["- None."]
    return "\n".join(lines) + "\n"
