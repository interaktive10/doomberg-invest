"""What the LLM router accepts (BRIEF §2.6): public data only, as typed values.

Free tiers may use their inputs to improve their services, which is acceptable only for public filings, exchange
announcements and values computed from them. The owner's private records (entries about their own decisions, the
reviews written after closing a thesis, position sizes, notes) must never reach a provider. The rule is structural,
so no private type needs to be named here:

- every router input is a `PublicData` value: a frozen dataclass whose class is defined in one of PUBLIC_MODULES
  (the LLM package, the text-facts engine, the Capex Desk, the India announcement triage, the thesis evidence pack);
  a subclass defined anywhere else is refused, so nothing can wrap a private row to get through. A field may also
  hold a pydantic model defined in a public module (the EvidencePack P-04 reads; M6 review R1-F4), checked field by
  field the same way;
- every field holds what its annotation says (a `str` field a str, `tuple[str, ...]` a tuple of str, a PublicData
  field that PublicData type, ...; M5 review R1-F6), built only from str, number, bool, date/datetime, UUID, None
  and other PublicData values; anything else (a pydantic row, a database record as a dict or a tuple, an arbitrary
  object) is refused;
- `check()` runs on every input before a request is built and raises PrivacyViolation (M5-04; reviewer check d);
  the router also refuses any value that isn't a PromptInput.

The guard's privacy_rule adds the static half: modules under pipeline/llm/ and pipeline/thesis/evidence_pack.py
never reference the private tables at all.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

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


def is_public_model(t: Any) -> bool:
    """A pydantic model class defined in a public module (the evidence pack and its parts)."""
    return isinstance(t, type) and issubclass(t, BaseModel) and _public_module(t.__module__)


def _model_hints(t: type) -> dict[str, Any]:
    """Each field's annotation: pydantic's resolved one (model_fields[...].annotation), else the class's hints."""
    if t not in _HINTS:
        fields: dict[str, Any] = dict(getattr(t, "model_fields", {}) or {})
        found = {name: getattr(f, "annotation", None) for name, f in fields.items()}
        if any(a is None for a in found.values()):
            declared = typing.get_type_hints(t)
            found = {n: a if a is not None else declared.get(n, Any) for n, a in found.items()}
        _HINTS[t] = found
    return _HINTS[t]


_HINTS: dict[type, dict[str, Any]] = {}


def _hints(t: type) -> dict[str, Any]:
    if t not in _HINTS:
        _HINTS[t] = typing.get_type_hints(t)
    return _HINTS[t]


def _refuse(path: str, value: Any, hint: Any) -> PrivacyViolation:
    t = type(value)
    return PrivacyViolation(f"{path}: {t.__module__}.{t.__qualname__} doesn't fit the field's type {hint!r}")


def fits(value: Any, hint: Any, path: str = "input") -> None:
    """Raise PrivacyViolation unless `value` is what the annotation `hint` says, all the way down."""
    if hint is Any or hint is object:
        check(value, path)
        return
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        for a in args:
            try:
                fits(value, a, path)
                return
            except PrivacyViolation:
                continue
        raise _refuse(path, value, hint)
    if hint is None or hint is type(None):
        if value is None:
            return
        raise _refuse(path, value, hint)
    if origin is typing.Literal:
        if isinstance(value, _SCALARS) and value in args:
            return
        raise _refuse(path, value, hint)
    if origin is tuple:
        if not isinstance(value, tuple):
            raise _refuse(path, value, hint)
        if len(args) == 2 and args[1] is Ellipsis:
            for i, v in enumerate(value):
                fits(v, args[0], f"{path}[{i}]")
        elif args:
            if len(value) != len(args):
                raise _refuse(path, value, hint)
            for i, (v, a) in enumerate(zip(value, args, strict=True)):
                fits(v, a, f"{path}[{i}]")
        else:
            check(value, path)
        return
    if origin in (list, Sequence):
        if not isinstance(value, list if origin is list else list | tuple):
            raise _refuse(path, value, hint)
        for i, v in enumerate(value):
            fits(v, args[0] if args else Any, f"{path}[{i}]")
        return
    if origin in (dict, Mapping):
        if not isinstance(value, dict):
            raise _refuse(path, value, hint)
        for k, v in value.items():
            if not isinstance(k, str):
                raise PrivacyViolation(f"{path}: dict keys must be str, got {type(k).__name__}")
            fits(v, args[1] if len(args) == 2 else Any, f"{path}.{k}")
        return
    if isinstance(hint, type) and (issubclass(hint, PublicData) or is_public_model(hint)):
        if not isinstance(value, hint):
            raise _refuse(path, value, hint)
        check(value, path)
        return
    if hint is float and isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        return
    if hint is int and isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(hint, type) and hint in _SCALARS and hint not in (int, float) and isinstance(value, hint):
        return
    raise _refuse(path, value, hint)


def check(value: Any, path: str = "input") -> None:
    """Raise PrivacyViolation unless `value` is public data all the way down (a PublicData value's fields checked
    against their annotations)."""
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
        hints = _hints(t)
        for f in dataclasses.fields(value):
            fits(getattr(value, f.name), hints.get(f.name, Any), f"{path}.{f.name}")
        return
    if isinstance(value, BaseModel) and is_public_model(t):
        for name, hint in _model_hints(t).items():
            fits(getattr(value, name), hint, f"{path}.{name}")
        return
    raise PrivacyViolation(
        f"{path}: {t.__module__}.{t.__qualname__} is not public data; the router accepts only PublicData types "
        "defined in " + ", ".join(PUBLIC_MODULES) + " (BRIEF §2.6)"
    )
