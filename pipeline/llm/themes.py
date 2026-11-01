"""P-08 themes (docs/SPEC_ISSUES.md 67; pipeline/reports/themes.py): the weekly theme pass reads industry aggregates
computed from public filings and prices, plus its own earlier calls, and names where demand is building before the
price. The input is JSON text built from those public values only (llm/privacy.py: no private record)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from pipeline.llm.prompt import PromptInput, obj

MAX_THEMES = 5
CONFIDENCE = ("low", "medium", "high")


@dataclass(frozen=True)
class ThemesInput(PromptInput):
    prompt_id: ClassVar[str] = "P-08"
    industries_json: str
    calls_json: str

    def variables(self) -> dict[str, str]:
        return {"industries": self.industries_json, "calls": self.calls_json}

    def schema(self) -> dict[str, Any]:
        theme = obj({
            "market": {"type": "string", "enum": ["us", "in"]},
            "industry": {"type": "string"},
            "title": {"type": "string"},
            "why": {"type": "string"},
            "wrong_if": {"type": "string"},
            "confidence": {"type": "string", "enum": list(CONFIDENCE)},
            "evidence": {"type": "array", "items": {"type": "string"}},
        })  # fmt: skip
        review = obj({"market": {"type": "string"}, "industry": {"type": "string"},
                      "decision": {"type": "string", "enum": ["keep", "drop"]},
                      "reason": {"type": "string"}})  # fmt: skip
        return obj({"themes": {"type": "array", "items": theme}, "reviews": {"type": "array", "items": review},
                    "note": {"type": "string"}})  # fmt: skip
