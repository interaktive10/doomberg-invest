"""P-07 announcement triage (BRIEF §5, §2.6): each new Indian exchange announcement (title = NSE's subject line,
summary = its text) gets categories and a read_pdf flag from the free-tier router. The result is stored in
announcement_triage; read_pdf items go to the text-facts queue (pipeline/facts/run.py). An announcement the router
defers has no triage row, so the next day's run picks it up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from pipeline.llm.prompt import PromptInput, obj

CATEGORIES = (
    "order_win",
    "capacity_expansion",
    "customer_win",
    "fund_raise",
    "rights_issue",
    "demerger",
    "acquisition",
    "pledge_change",
    "auditor_change",
    "management_change",
    "results",
    "credit_rating",
    "other",
)
SUMMARY_CHARS = 2000  # the announcement text NSE gives is a summary; very long ones are cut (the PDF has the rest)


@dataclass(frozen=True)
class TriageInput(PromptInput):
    prompt_id: ClassVar[str] = "P-07"
    title: str
    summary: str

    def variables(self) -> dict[str, str]:
        return {"title": self.title, "summary": self.summary[:SUMMARY_CHARS]}

    def schema(self) -> dict[str, Any]:
        return obj({"categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)}},
                    "read_pdf": {"type": "boolean"}})  # fmt: skip


@dataclass(frozen=True)
class Triage:
    categories: tuple[str, ...]
    read_pdf: bool


def parse(content: dict[str, Any]) -> Triage | None:
    """The model's JSON -> Triage; unknown categories are dropped, a malformed answer is None."""
    cats = content.get("categories")
    flag = content.get("read_pdf")
    if not isinstance(cats, list) or not isinstance(flag, bool):
        return None
    kept = tuple(dict.fromkeys(c for c in cats if isinstance(c, str) and c in CATEGORIES))
    return Triage(kept or ("other",), flag)
