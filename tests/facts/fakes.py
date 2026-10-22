"""A provider that answers every M5 prompt the way a well-behaved model would, from F-SYN's ground truth (P-01) and
simple rules (P-02, P-07); `fail=True` makes it answer 429 to everything (the day's quota is out)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pipeline.facts.entities import normalize_name
from pipeline.llm.providers.base import Completion, RateLimited, Request
from tests.facts.oracle import Oracle


def _after(label: str, text: str) -> str:
    return text.split(f"{label}: ", 1)[1].split("\n", 1)[0]


def _p02(req: Request) -> dict[str, Any]:
    names = json.loads(_after("NAMES", req.user))
    cands = json.loads(_after("CANDIDATES", req.user))
    out = []
    for n in names:
        hit = next((c for c in cands if normalize_name(n) in normalize_name(c["name"])
                    or normalize_name(c["name"]) in normalize_name(n)), None)  # fmt: skip
        out.append({"name": n, "candidate_id": hit["id"] if hit else None, "kind": "company", "confidence": 0.9})
    return {"matches": out}


def _p07(req: Request) -> dict[str, Any]:
    title = _after("TITLE", req.user).lower()
    order = "order" in title or "contract" in title
    return {"categories": ["order_win"] if order else ["other"], "read_pdf": order}


@dataclass
class MultiOracle:
    truth: dict[str, Any]
    fail: bool = False
    name: str = "gemini"
    requests: list[Request] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def complete(self, req: Request) -> Completion:
        self.requests.append(req)
        if self.fail:
            raise RateLimited("gemini: 429")
        if req.prompt_id == "P-01":
            return Oracle(self.truth, noise=False).complete(req)
        answer = {"P-02": _p02, "P-07": _p07}[req.prompt_id](req)
        return Completion(answer, 200, 50)
