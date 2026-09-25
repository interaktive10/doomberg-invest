"""The provider contract (BRIEF §2.6): one request in, one parsed JSON object out.

Schemas are written once in a neutral JSON-Schema subset (`nullable: true` marks a value that may be null) and
translated per provider: OpenAI-compatible APIs (Groq, OpenRouter) take JSON Schema with `["t", "null"]` types;
Gemini takes its OpenAPI subset (upper-case types, `nullable`).

A 429 (or a quota error) raises RateLimited so the router falls back to the next provider; any other failure
(HTTP error, timeout, a response that isn't the requested JSON) raises ProviderError.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

Mode = Literal["tool", "json"]


@dataclass(frozen=True)
class Request:
    prompt_id: str
    model: str
    system: str
    user: str
    schema: Mapping[str, Any]
    mode: Mode
    tool_name: str
    temperature: float


@dataclass(frozen=True)
class Completion:
    content: dict[str, Any]
    tokens_in: int | None = None
    tokens_out: int | None = None


class RateLimited(Exception):
    """HTTP 429 / quota exhausted. retry_after (seconds) when the provider says; None means the day's quota."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderError(Exception):
    """Any other failure: the router records it and tries the next provider."""


class Provider(Protocol):
    @property
    def name(self) -> str: ...

    def available(self) -> bool: ...

    def complete(self, req: Request) -> Completion: ...


def to_json_schema(s: Mapping[str, Any]) -> dict[str, Any]:
    """Neutral schema -> JSON Schema (OpenAI-compatible tools and response formats)."""
    out: dict[str, Any] = {}
    for k, v in s.items():
        if k == "nullable":
            continue
        if k == "properties":
            out[k] = {name: to_json_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out[k] = to_json_schema(v)
        else:
            out[k] = v
    if s.get("nullable"):
        out["type"] = [s["type"], "null"]
        if "enum" in out:
            out["enum"] = [*out["enum"], None]
    if s.get("type") == "object":
        out.setdefault("additionalProperties", False)
    return out


def to_gemini_schema(s: Mapping[str, Any]) -> dict[str, Any]:
    """Neutral schema -> Gemini's OpenAPI subset (no additionalProperties; upper-case types)."""
    out: dict[str, Any] = {}
    for k, v in s.items():
        if k == "properties":
            out[k] = {name: to_gemini_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out[k] = to_gemini_schema(v)
        elif k == "type":
            out[k] = str(v).upper()
        elif k in {"enum", "required", "nullable", "description", "minimum", "maximum", "maxItems", "minItems"}:
            out[k] = v
    return out


def parse_json_object(text: str) -> dict[str, Any]:
    """A JSON object from a model's text (a ```json fence around it is tolerated, nothing else)."""
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", body, re.S)
    if fenced:
        body = fenced.group(1)
    try:
        doc = json.loads(body)
    except json.JSONDecodeError as e:
        raise ProviderError(f"not JSON: {e}") from e
    if not isinstance(doc, dict):
        raise ProviderError(f"expected a JSON object, got {type(doc).__name__}")
    return doc


def retry_after(e: httpx.HTTPStatusError) -> float | None:
    """Seconds to wait from a 429: the Retry-After header, or Gemini's RetryInfo ("retryDelay": "31s")."""
    h = e.response.headers.get("retry-after")
    if h:
        try:
            return float(h)
        except ValueError:
            return None
    try:
        text = e.response.text
    except httpx.ResponseNotRead:
        return None
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text)
    return float(m.group(1)) if m else None


def raise_for(e: httpx.HTTPError, provider: str) -> None:
    """Map an httpx error to RateLimited / ProviderError (never returns)."""
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
        raise RateLimited(f"{provider}: 429", retry_after(e)) from e
    if isinstance(e, httpx.HTTPStatusError):
        raise ProviderError(f"{provider}: HTTP {e.response.status_code}") from e
    raise ProviderError(f"{provider}: {type(e).__name__}") from e
