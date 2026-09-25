"""What the LLM router accepts (BRIEF §2.6): public data only, as typed values.

Free tiers may use their inputs to improve their services, which is acceptable only for public filings, exchange
announcements and values computed from them. The owner's private records (entries about their own decisions, the
reviews written after closing a thesis, position sizes, notes) must never reach a provider. The rule is structural,
so no private type needs to be named here:

- every router input is a `PublicData` value: a frozen dataclass whose class is defined in one of PUBLIC_MODULES
  (the LLM package, the text-facts engine, the Capex Desk, the India announcement triage, the thesis evidence pack);
  a subclass defined anywhere else is refused, so nothing can wrap a private row to get through;
- every field holds a str, number, bool, date/datetime, UUID, None, another PublicData value, or a list, tuple or
  str-keyed dict of those; anything else (a pydantic row, a database record, an arbitrary object) is refused;
- `check()` runs on every input before a request is built and raises PrivacyViolation (M5-04; reviewer check d).

The guard's privacy_rule adds the static half: modules under pipeline/llm/ and pipeline/thesis/evidence_pack.py
never reference the private tables at all.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

PUBLIC_MODULES = (
    "pipeline.llm",
    "pipeline.facts",
    "pipeline.capex",
    "pipeline.india.triage",
    "pipeline.thesis.evidence_pack",
)
_SCALARS = (str, int, float, bool, Decimal, date, datetime, UUID, type(None))


class PrivacyViolation(Exception):
    """A router input that isn't public data (BRIEF §2.6)."""


@dataclasses.dataclass(frozen=True)
class PublicData:
    """Base class of every router input. Subclasses are frozen dataclasses in a PUBLIC_MODULES module."""


def _public_module(module: str) -> bool:
    return any(module == m or module.startswith(m + ".") for m in PUBLIC_MODULES)


def is_public_type(t: type) -> bool:
    return issubclass(t, PublicData) and dataclasses.is_dataclass(t) and _public_module(t.__module__)


def check(value: Any, path: str = "input") -> None:
    """Raise PrivacyViolation unless `value` is public data all the way down."""
    if isinstance(value, _SCALARS):
        return
    if isinstance(value, list | tuple):
        for i, v in enumerate(value):
            check(v, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise PrivacyViolation(f"{path}: dict keys must be str, got {type(k).__name__}")
            check(v, f"{path}.{k}")
        return
    t = type(value)
    if isinstance(value, PublicData) and is_public_type(t):
        for f in dataclasses.fields(value):
            check(getattr(value, f.name), f"{path}.{f.name}")
        return
    raise PrivacyViolation(
        f"{path}: {t.__module__}.{t.__qualname__} is not public data; the router accepts only PublicData types "
        "defined in " + ", ".join(PUBLIC_MODULES) + " (BRIEF §2.6)"
    )
