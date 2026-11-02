"""OpenAI-compatible chat completions over plain HTTP (BRIEF §2.6): OpenRouter (DeepSeek V4.1 Flash, the primary since
docs/SPEC_ISSUES.md 63) and Groq's free tier. No SDK: the request is a JSON POST with a bearer key to an allowlisted
host (pipeline/net/http.py), so nothing can reach a banned endpoint (the guard's banned_runtime_domains).
OpenRouter's base URL comes from config/quotas.yaml (the guard's openai_client_rule)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from pipeline.llm.providers.base import (
    Completion,
    ProviderError,
    Request,
    parse_json_object,
    raise_for,
    to_json_schema,
)
from pipeline.net.http import HttpClient

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def strict(s: Mapping[str, Any]) -> dict[str, Any]:
    """A JSON Schema with every object closed (additionalProperties false), as strict structured outputs need."""
    out: dict[str, Any] = dict(s)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["properties"] = {k: strict(v) for k, v in (out.get("properties") or {}).items()}
    if isinstance(out.get("items"), Mapping):
        out["items"] = strict(out["items"])
    return out


def body(req: Request, structured: bool = False) -> dict[str, Any]:
    """`structured`: the JSON answer is held to the request's schema (OpenRouter's structured outputs, 2026-11-02:
    with a bare json_object DeepSeek guessed the card's shape and every P-04 card failed validation)."""
    out: dict[str, Any] = {
        "model": req.model,
        "temperature": req.temperature,
        "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
    }
    if req.mode == "tool":
        fn = {"name": req.tool_name, "description": f"Record the {req.prompt_id} result.",
              "parameters": to_json_schema(req.schema)}  # fmt: skip
        out["tools"] = [{"type": "function", "function": fn}]
        out["tool_choice"] = {"type": "function", "function": {"name": req.tool_name}}
    elif structured:
        out["response_format"] = {"type": "json_schema", "json_schema": {
            "name": req.tool_name, "strict": True, "schema": strict(to_json_schema(req.schema))}}  # fmt: skip
        out["provider"] = {"require_parameters": True}  # only a provider that honours the schema
    else:
        out["response_format"] = {"type": "json_object"}
    if req.reasoning_effort:
        out["reasoning"] = {"effort": req.reasoning_effort, "exclude": True}  # the answer only, not the thinking
    return out


def parse(raw: bytes, req: Request, provider: str) -> Completion:
    try:
        doc = json.loads(raw)
        msg = doc["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"{provider}: unexpected response ({type(e).__name__})") from e
    usage = doc.get("usage") or {}
    tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if req.mode == "tool":
        calls = msg.get("tool_calls") or []
        fn = calls[0].get("function", {}) if calls and isinstance(calls[0], dict) else {}
        if fn.get("name") != req.tool_name:
            if not calls and msg.get("content"):  # a reasoning model may answer the tool's JSON as text
                return Completion(parse_json_object(str(msg["content"])), tin, tout)
            raise ProviderError(f"{provider}: no call to the requested tool")
        args = fn.get("arguments")
        content = args if isinstance(args, dict) else parse_json_object(str(args or ""))
        return Completion(dict(content), tin, tout)
    return Completion(parse_json_object(str(msg.get("content") or "")), tin, tout)


@dataclass
class OpenAICompatible:
    http: HttpClient
    key: str | None
    base_url: str
    name: str
    structured: bool = False  # sends json_schema response formats (OpenRouter)

    def available(self) -> bool:
        return bool(self.key)

    def complete(self, req: Request) -> Completion:
        try:
            raw = self.http.post_json(
                f"{self.base_url.rstrip('/')}/chat/completions",
                body(req, self.structured),
                headers={"Authorization": f"Bearer {self.key}", "X-Title": "Doomberg Invest"},
            )
        except httpx.HTTPError as e:
            raise_for(e, self.name)
        return parse(raw, req, self.name)
