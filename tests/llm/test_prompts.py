"""The prompt files are the brief's text verbatim (BRIEF §5, Appendix F.7), and rendering is a single pass."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.llm.prompt import PROMPT_DIR, PROMPTS, render, template

BRIEF = (Path(__file__).resolve().parents[2] / "docs" / "BRIEF.md").read_text(encoding="utf-8")


def blocks(title: str) -> list[str]:
    i = BRIEF.index(title)
    j = BRIEF.find("\n### ", i + 5)
    return re.findall(r"```\n(.*?)```", BRIEF[i:j], re.S)


@pytest.mark.parametrize(
    ("file", "title", "k"),
    [
        ("P-01.system.txt", "### P-01 EXTRACT_FACTS", 0),
        ("P-01.user.txt", "### P-01 EXTRACT_FACTS", 1),
        ("P-02.system.txt", "### P-02 ENTITY_NORMALIZE", 0),
        ("P-04.system.txt", "### P-04 THESIS_CARD", 0),
        ("P-05.system.txt", "### P-05 CLAIM_SUPPORT · free", 0),
        ("P-07.system.txt", "### P-07 ANNOUNCEMENT_TRIAGE", 0),
    ],
)
def test_prompt_text_is_verbatim(file: str, title: str, k: int) -> None:
    assert (PROMPT_DIR / file).read_text(encoding="utf-8") == blocks(title)[k]


@pytest.mark.parametrize(
    ("pid", "line"),
    [("P-02", "`NAMES: {{names}}` and `CANDIDATES: {{candidates}}`"),
     ("P-05", "`SENTENCE: {{sentence}}`, then `QUOTES: {{quotes}}`, then `COMPUTED: {{computed}}`")],
)  # fmt: skip
def test_user_messages_carry_the_briefs_fields_in_order(pid: str, line: str) -> None:
    assert line in BRIEF
    fields = re.findall(r"`([A-Z]+): (\{\{\w+\}\})`", line)
    assert template(pid, "user") == "\n".join(f"{k}: {v}" for k, v in fields)


def test_every_prompt_has_both_templates() -> None:
    for pid in PROMPTS:
        assert template(pid, "system") and template(pid, "user")


def test_render_is_one_pass_and_strict() -> None:
    assert render("A {{x}} B", {"x": "{{y}}"}) == "A {{y}} B"  # document text is never re-scanned
    with pytest.raises(KeyError):
        render("{{missing}}", {})


def test_p04_user_message_is_the_pack() -> None:
    """§5: `EVIDENCE PACK:` followed by `{{pack_json}}` (the pack's JSON on the next line)."""
    assert "**User:** `EVIDENCE PACK:` followed by `{{pack_json}}`" in BRIEF
    assert template("P-04", "user") == "EVIDENCE PACK:\n{{pack_json}}"
    assert PROMPTS["P-04"].route == "P-04-fallback" and PROMPTS["P-04"].temperature == 0.3
