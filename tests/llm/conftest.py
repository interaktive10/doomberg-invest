"""Offline doubles for the LLM layer: a scripted provider and a simulated clock."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pipeline.llm.providers.base import Completion, Request
from pipeline.llm.quotas import Quotas


@dataclass
class FakeClock:
    t: datetime = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)
    slept: float = 0.0

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.t += timedelta(seconds=seconds)

    def advance(self, **kw: float) -> None:
        self.t += timedelta(**kw)


@dataclass
class Scripted:
    """Answers each request with the next scripted outcome (a Completion, a dict, or an exception to raise)."""

    name: str
    script: list[Any] = field(default_factory=list)
    key: bool = True
    requests: list[Request] = field(default_factory=list)

    def available(self) -> bool:
        return self.key

    def complete(self, req: Request) -> Completion:
        self.requests.append(req)
        outcome = self.script.pop(0) if self.script else {"categories": ["other"], "read_pdf": False}
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, Completion):
            return outcome
        return Completion(dict(outcome), 100, 20)


def quotas(names: Iterable[str] = ("gemini", "groq", "openrouter"), rpd: int | None = 100, rpm: int | None = None,
           tpd: int | None = None) -> Quotas:  # fmt: skip
    names = list(names)
    return Quotas.from_doc({
        "providers": {n: {"models": {"extract": f"{n}-small", "card": f"{n}-big"}, "requests_per_day": rpd,
                          "requests_per_minute": rpm, "tokens_per_day": tpd} for n in names},
        "routing": {p: names for p in ("P-01", "P-02", "P-05", "P-07")},
    })  # fmt: skip


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
