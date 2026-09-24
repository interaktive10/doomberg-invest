"""M0-04: docs/DOOMBERG_AUDIT.md has every BRIEF §8 section and every claimed rule carries a file:line.

When the old repo is checked out (env DOOMBERG_REPO, default ../doomberg), every reference is also resolved:
the file must exist and the cited lines must be inside it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = (ROOT / "docs" / "DOOMBERG_AUDIT.md").read_text(encoding="utf-8")
OLD_REPO = Path(os.environ.get("DOOMBERG_REPO", ROOT.parent / "doomberg"))

SECTIONS = [
    "## 1. Overview",
    "## 2. Data sources used",
    "## 3. Long-term / investing logic",
    "## 4. What's reusable as code",
    "## 5. Cliché rules",
    "## 6. Trading / execution parts (not ported)",
    "## 7. Gaps",
]
# `path:12`, `path:12-30`, `path:77/94`; a bare `:12` continues the previous path in the same cell/sentence.
REF = re.compile(r"`((?:[\w./-]+\.(?:py|md|json|js|toml|example))?):(\d+)(?:[-/](\d+))?`")


def _section(title: str) -> str:
    start = AUDIT.index(title)
    nxt = AUDIT.find("\n## ", start + 1)
    return AUDIT[start : nxt if nxt != -1 else len(AUDIT)]


def _refs(text: str) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    last = ""
    for m in REF.finditer(text):
        path = m.group(1) or last
        last = path
        a = int(m.group(2))
        b = int(m.group(3)) if m.group(3) else a
        out.append((path, a, b))
    return out


def test_all_sections_present_in_order() -> None:
    positions = [AUDIT.index(s) for s in SECTIONS]
    assert positions == sorted(positions)


def test_every_rule_row_has_a_file_line() -> None:
    rows = [ln for ln in _section("## 3.").splitlines() if re.match(r"\| (LB|PV)-\d+", ln)]
    assert len(rows) >= 25
    missing = [r.split("|")[1].strip() for r in rows if not _refs(r)]
    assert missing == [], f"rules without file:line: {missing}"


def test_every_legacy_signal_row_cites_its_source_rule() -> None:
    rows = [ln for ln in _section("## 5.").splitlines() if re.match(r"\| L\d+ ", ln)]
    assert [r.split("|")[1].strip() for r in rows] == [f"L{i}" for i in range(1, 7)]
    assert all(re.search(r"LB-\d+", r) for r in rows)


def _resolve(path: str) -> Path | None:
    for cand in (OLD_REPO / path, OLD_REPO / "doomberg" / path, OLD_REPO / "doomberg" / "data" / path):
        if cand.is_file():
            return cand
    hits = [p for p in OLD_REPO.rglob(Path(path).name) if ".git" not in p.parts and p.as_posix().endswith(path)]
    return hits[0] if len(hits) == 1 else None


@pytest.mark.oldrepo
def test_references_resolve_in_old_repo() -> None:
    bad: list[str] = []
    for path, a, b in _refs(AUDIT):
        f = _resolve(path)
        if f is None:
            bad.append(f"{path}: file not found")
            continue
        n = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        if not (1 <= a <= b <= n) and not (b < a <= n):  # `77/94` style pairs may be unordered
            bad.append(f"{path}:{a}-{b} outside 1..{n}")
    assert bad == []
