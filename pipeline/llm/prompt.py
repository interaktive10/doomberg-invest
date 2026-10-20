"""Prompt specs (BRIEF §5 and Appendix F.7). The system and user templates are the files in pipeline/llm/prompts/,
verbatim from the brief (tests/llm/test_prompts.py compares them); the brief gives no user message for P-07, so its
is the simplest one that carries the inputs (docs/DECISIONS.log). P-03 (risk tags) is no longer called: its
risk_changes rows had no reader (docs/SPEC_ISSUES.md 50). P-06 (cross-border map) went with the Capex Desk (52).

A router input is a `PromptInput`: public data (llm/privacy.py) that names its prompt and supplies the template
variables and the response schema, so every character sent to a provider comes from a checked public value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

from pipeline.llm.privacy import PublicData
from pipeline.llm.providers.base import Mode

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class PromptSpec:
    id: str
    mode: Mode  # "tool": the carried-over prompts end "Return only the tool call"; "json": "Return only JSON"
    tool_name: str
    temperature: float
    task: str  # the config/quotas.yaml model: "extract" (Flash-Lite class) or "card" (Flash)
    route: str = ""  # the config/quotas.yaml `routing` key, when it isn't the id (P-04 runs only as the fallback)


PROMPTS: dict[str, PromptSpec] = {
    "P-01": PromptSpec("P-01", "tool", "record_facts", 0.0, "extract"),
    "P-02": PromptSpec("P-02", "tool", "record_matches", 0.0, "extract"),
    "P-04": PromptSpec("P-04", "json", "thesis_card", 0.3, "card", route="P-04-fallback"),
    "P-05": PromptSpec("P-05", "tool", "record_support", 0.0, "card"),
    "P-07": PromptSpec("P-07", "json", "announcement_triage", 0.0, "extract"),
}


@cache
def template(prompt_id: str, part: str) -> str:
    """The verbatim 'system' or 'user' template (the files end with one newline, which isn't sent)."""
    return (PROMPT_DIR / f"{prompt_id}.{part}.txt").read_text(encoding="utf-8").removesuffix("\n")


def render(text: str, variables: Mapping[str, str]) -> str:
    """{{name}} -> variables[name] in one pass (values are never re-scanned); a missing variable is an error."""

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in variables:
            raise KeyError(f"prompt variable {{{{{name}}}}} not supplied")
        return variables[name]

    return re.sub(r"\{\{(\w+)\}\}", sub, text)


@dataclass(frozen=True)
class PromptInput(PublicData):
    """A router input. Subclasses (in a public module) set prompt_id and implement variables() and schema()."""

    prompt_id: ClassVar[str] = ""

    def variables(self) -> dict[str, str]:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        raise NotImplementedError


def nullable(t: str, **kw: Any) -> dict[str, Any]:
    return {"type": t, "nullable": True, **kw}


def obj(properties: Mapping[str, Any], required: tuple[str, ...] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(required or properties)}
