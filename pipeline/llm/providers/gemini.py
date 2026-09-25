"""Gemini (free tier, BRIEF §2.6) over the REST API: generateContent with a forced function call (the carried-over
prompts "Return only the tool call") or JSON output with a response schema. The key travels in the
x-goog-api-key header, never in a URL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from pipeline.llm.providers.base import (
    Completion,
    ProviderError,
    Request,
    parse_json_object,
    raise_for,
    to_gemini_schema,
)
from pipeline.net.http import HttpClient

API = "https://generativelanguage.googleapis.com/v1beta/models"


def url(model: str) -> str:
    return f"{API}/{model}:generateContent"


def body(req: Request) -> dict[str, Any]:
    schema = to_gemini_schema(req.schema)
    out: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": req.system}]},
        "contents": [{"role": "user", "parts": [{"text": req.user}]}],
        "generationConfig": {"temperature": req.temperature},
    }
    if req.mode == "tool":
        out["tools"] = [
            {
                "functionDeclarations": [
                    {"name": req.tool_name, "description": f"Record the {req.prompt_id} result.", "parameters": schema}
                ]
            }
        ]
        out["toolConfig"] = {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [req.tool_name]}}
    else:
        out["generationConfig"] |= {"responseMimeType": "application/json", "responseSchema": schema}
    return out


def parse(raw: bytes, req: Request) -> Completion:
    try:
        doc = json.loads(raw)
        parts = doc["candidates"][0]["content"]["parts"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"gemini: unexpected response ({type(e).__name__})") from e
    usage = doc.get("usageMetadata") or {}
    tin, tout = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
    if req.mode == "tool":
        calls = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
        if not calls or calls[0].get("name") != req.tool_name or not isinstance(calls[0].get("args"), dict):
            raise ProviderError("gemini: no call to the requested tool")
        return Completion(dict(calls[0]["args"]), tin, tout)
    text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
    return Completion(parse_json_object(text), tin, tout)


@dataclass
class Gemini:
    http: HttpClient
    key: str | None
    name: str = "gemini"

    def available(self) -> bool:
        return bool(self.key)

    def complete(self, req: Request) -> Completion:
        try:
            raw = self.http.post_json(url(req.model), body(req), headers={"x-goog-api-key": self.key or ""})
        except httpx.HTTPError as e:
            raise_for(e, self.name)
        return parse(raw, req)
