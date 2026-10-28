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


def why(doc: Any) -> str:
    """Gemini's finishReason (or the prompt's blockReason) for an answer without a usable part, for the log
    (MALFORMED_FUNCTION_CALL, MAX_TOKENS, SAFETY, ...; docs/SPEC_ISSUES.md 59)."""
    if not isinstance(doc, dict):
        return ""
    cands, fb = doc.get("candidates"), doc.get("promptFeedback")
    first: dict[str, Any] = cands[0] if isinstance(cands, list) and cands and isinstance(cands[0], dict) else {}
    feedback: dict[str, Any] = fb if isinstance(fb, dict) else {}
    reason = first.get("finishReason") or feedback.get("blockReason")
    return f" ({reason})" if reason else ""


def parse(raw: bytes, req: Request) -> Completion:
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise ProviderError("gemini: unexpected response (not JSON)") from e
    try:
        parts = doc["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"gemini: unexpected response ({type(e).__name__}){why(doc)}") from e
    usage = doc.get("usageMetadata") or {}
    tin, tout = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
    if req.mode == "tool":
        calls = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
        if not calls or calls[0].get("name") != req.tool_name or not isinstance(calls[0].get("args"), dict):
            raise ProviderError(f"gemini: no call to the requested tool{why(doc)}")
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
