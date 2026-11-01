"""P-08 themes (docs/SPEC_ISSUES.md 67, 68; pipeline/reports/themes.py): the monthly rethink of the theme library. It
reads the demand drivers (public FRED series), the industries' demand evidence and price moves (public filings and
prices) and its own library with this week's numbers, then keeps, edits or retires each theme and proposes new ones.
The input is JSON text built from those public values only (llm/privacy.py: no private record)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from pipeline.llm.prompt import PromptInput, obj

MAX_NEW = 3
CATEGORIES = (
    "Replacement cycles",
    "Housing & construction",
    "Consumer",
    "Energy & power",
    "Industrial capex",
    "Technology & AI",
    "Materials & commodities",
    "Rates & credit",
    "Transport & travel",
    "Health",
    "From the filings",
)
READINGS = ("yoy", "level", "cohort")


@dataclass(frozen=True)
class ThemesInput(PromptInput):
    prompt_id: ClassVar[str] = "P-08"
    drivers_json: str
    industries_json: str
    library_json: str
    retired_json: str

    def variables(self) -> dict[str, str]:
        return {"drivers": self.drivers_json, "industries": self.industries_json, "library": self.library_json,
                "retired": self.retired_json}  # fmt: skip

    def schema(self) -> dict[str, Any]:
        s = {"type": "string"}
        words = {"type": "array", "items": s}
        review = obj({"slug": s, "decision": {"type": "string", "enum": ["keep", "edit", "retire"]}, "note": s,
                      "title": s, "why": s, "wrong_if": s, "keywords": words},
                     ("slug", "decision", "note"))  # fmt: skip
        new = obj({"title": s, "category": {"type": "string", "enum": list(CATEGORIES)}, "driver": s,
                   "reading": {"type": "string", "enum": list(READINGS)}, "lag_months": {"type": "integer"},
                   "keywords": words, "why": s, "wrong_if": s})  # fmt: skip
        return obj({"reviews": {"type": "array", "items": review}, "new": {"type": "array", "items": new},
                    "note": s})  # fmt: skip
