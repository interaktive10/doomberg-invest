"""config/quotas.yaml (BRIEF §2.6): per-provider daily request and token budgets, the routing order per prompt, the
work order and the daily text limits.

The values are per project and change, so they are copied from each provider's console (docs/QUOTAS.md), never
hard-coded. A provider whose `requests_per_day` is null hasn't been filled in and is treated as unavailable; a null
`requests_per_minute` or `tokens_per_day` means the provider states no such limit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pipeline.settings import REPO_ROOT


@dataclass(frozen=True)
class ProviderQuota:
    name: str
    models: Mapping[str, str]
    requests_per_day: int | None
    requests_per_minute: int | None
    tokens_per_day: int | None
    base_url: str | None = None

    @property
    def configured(self) -> bool:
        return self.requests_per_day is not None

    def model(self, task: str) -> str:
        """The model for a task ('extract' or 'card'); a provider without a card model uses its extract model."""
        return self.models.get(task) or self.models["extract"]


def _int(v: Any) -> int | None:
    return None if v is None else int(v)


@dataclass(frozen=True)
class Quotas:
    providers: Mapping[str, ProviderQuota]
    routing: Mapping[str, tuple[str, ...]]
    work_order: tuple[str, ...] = ()
    documents_per_day: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_doc(cls, doc: Mapping[str, Any]) -> Quotas:
        providers = {
            name: ProviderQuota(
                name=name,
                models=dict(p.get("models") or {}),
                requests_per_day=_int(p.get("requests_per_day")),
                requests_per_minute=_int(p.get("requests_per_minute")),
                tokens_per_day=_int(p.get("tokens_per_day")),
                base_url=p.get("base_url"),
            )
            for name, p in (doc.get("providers") or {}).items()
        }
        routing = {pid: tuple(order) for pid, order in (doc.get("routing") or {}).items()}
        limits = doc.get("text_daily_limits") or {}
        return cls(providers, routing, tuple(doc.get("work_order") or ()), _int(limits.get("documents_per_day")), doc)

    @classmethod
    def load(cls, root: Path = REPO_ROOT) -> Quotas:
        return cls.from_doc(yaml.safe_load((root / "config" / "quotas.yaml").read_text(encoding="utf-8")))

    def configured(self) -> list[str]:
        return [n for n, p in self.providers.items() if p.configured]
