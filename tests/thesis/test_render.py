"""The markdown rendering of a card (Appendix G: `python -m pipeline.thesis.render <json>`)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pipeline.thesis import render

F = Path(__file__).resolve().parents[2] / "fixtures" / "card"


def test_render_writes_the_md_next_to_the_card_with_the_packs_name(tmp_path: Path) -> None:
    week = tmp_path / "data" / "thesis_cards" / "2026-W38"
    week.mkdir(parents=True)
    (tmp_path / "data" / "thesis_queue").mkdir(parents=True)
    pack = json.loads((F / "pack.json").read_text(encoding="utf-8"))
    (tmp_path / "data" / "thesis_queue" / "2026-W38.json").write_text(json.dumps({"week": "2026-W38", "packs": [pack]}))
    shutil.copy(F / "good.json", week / "us-nmbs.json")
    assert render.main([str(week / "us-nmbs.json")]) == 0
    md = (week / "us-nmbs.md").read_text(encoding="utf-8")
    assert md.startswith("# Nimbus Compute Corp. (NMBS) — 2026-W38\n")
    for heading in ("## Facts", "## Why it may be mispriced", "## Inferences", "## Assumptions", "## Risks",
                    "## Kill criteria", "## Read next"):  # fmt: skip
        assert heading in md
    assert "| `m:rpo_yoy` | < 0.1 | 2026-11-20 |" in md


def test_cites_missing_from_the_text_are_appended() -> None:
    card = {"summary": "s", "facts": [{"text": "Revenue rose.", "cites": ["m:revenue:2026-06-30"]}]}
    assert "- Revenue rose. [m:revenue:2026-06-30]" in render.render(card, "T")
