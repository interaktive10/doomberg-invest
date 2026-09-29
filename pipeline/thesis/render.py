"""A thesis card as markdown (BRIEF §4.9; Appendix G: `uv run python -m pipeline.thesis.render <json>` writes the .md
next to the card). The company's name comes from its pack in the week's queue file when there is one."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pipeline.settings import REPO_ROOT

OPS = {"<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=", "changes": "changes"}


def _cited(item: Mapping[str, Any]) -> str:
    text = str(item["text"]).strip()
    missing = [c for c in item.get("cites") or [] if f"[{c}]" not in text]
    return text + ("" if not missing else " " + " ".join(f"[{c}]" for c in missing))


def render(card: Mapping[str, Any], title: str) -> str:
    lines = [f"# {title}", "", str(card.get("summary", "")).strip(), ""]

    def section(name: str, items: Sequence[str]) -> None:
        if items:
            lines.extend([f"## {name}", *[f"- {x}" for x in items], ""])

    section("Facts", [_cited(x) for x in card.get("facts") or []])
    section("Why it may be mispriced", [_cited(x) for x in card.get("why_mispriced") or []])
    section("Inferences", [str(x) for x in card.get("inferences") or []])
    section("Assumptions", [str(x) for x in card.get("assumptions") or []])
    section("Risks", [_cited(x) for x in card.get("risks") or []])
    kills = card.get("kill_criteria") or []
    if kills:
        lines += ["## Kill criteria", "| Metric | Condition | Check after | Why |", "|---|---|---|---|"]
        for k in kills:
            op = OPS.get(str(k.get("operator")), str(k.get("operator")))
            cond = op if k.get("threshold") is None else f"{op} {k['threshold']}"
            lines.append(f"| `{k.get('metric_id')}` | {cond} | {k.get('check_after')} | {k.get('why', '')} |")
        lines.append("")
    section("Read next", [f"[{r.get('title')}]({r.get('url')})" for r in card.get("read_next") or []])
    return "\n".join(lines).rstrip() + "\n"


def title_for(path: Path, root: Path = REPO_ROOT) -> str:
    """The card's title, "<name> — <week>", from the week's queue file, else the card's file name."""
    week, key = path.parent.name, path.stem
    queue = root / "data" / "thesis_queue" / f"{week}.json"
    if queue.exists():
        for p in json.loads(queue.read_text(encoding="utf-8")).get("packs") or []:
            c = p.get("company") or {}
            if c.get("key") == key:
                code = c.get("ticker") or c.get("nse_symbol")
                return f"{c.get('name')}{f' ({code})' if code else ''} — {week}"
    return f"{key} — {week}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m pipeline.thesis.render data/thesis_cards/<week>/<company>.json", file=sys.stderr)
        return 2
    path = Path(args[0]).resolve()
    card = json.loads(path.read_text(encoding="utf-8"))
    root = next((p for p in path.parents if (p / "data" / "thesis_queue").is_dir()), REPO_ROOT)
    out = path.with_suffix(".md")
    out.write_text(render(card, title_for(path, root)), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
