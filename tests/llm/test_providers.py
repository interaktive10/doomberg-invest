"""Provider request shapes and response parsing (offline, HTTP mocks): Gemini's forced function call / JSON output,
OpenAI-compatible tool calls (Groq, OpenRouter), and the 429 / error mapping the router relies on."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pipeline.llm.providers import gemini
from pipeline.llm.providers.base import (
    ProviderError,
    RateLimited,
    Request,
    retry_after,
    to_gemini_schema,
    to_json_schema,
)
from pipeline.llm.providers.gemini import Gemini
from pipeline.llm.providers.openai_compat import GROQ_BASE_URL, OpenAICompatible
from pipeline.net.http import HttpClient
from pipeline.settings import Settings

SCHEMA = {"type": "object", "properties": {"n": {"type": "number", "nullable": True},
                                           "k": {"type": "string", "enum": ["a", "b"], "nullable": True}},
          "required": ["n", "k"]}  # fmt: skip
TOOL = Request("P-02", "m", "sys", "usr", SCHEMA, "tool", "record_matches", 0.0)
JSON = Request("P-07", "m", "sys", "usr", SCHEMA, "json", "announcement_triage", 0.0)


def http(tmp_path: Path) -> HttpClient:
    return HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent=None, cache_dir=tmp_path))


def test_schema_translations() -> None:
    js = to_json_schema(SCHEMA)
    assert js["properties"]["n"] == {"type": ["number", "null"]}
    assert js["properties"]["k"] == {"type": ["string", "null"], "enum": ["a", "b", None]}
    assert js["additionalProperties"] is False
    gs = to_gemini_schema(SCHEMA)
    assert gs["type"] == "OBJECT" and gs["properties"]["n"] == {"type": "NUMBER", "nullable": True}


def test_gemini_tool_call_and_json_output(tmp_path: Path) -> None:
    h = http(tmp_path)
    call = {"candidates": [{"content": {"parts": [{"functionCall": {"name": "record_matches", "args": {"n": 1}}}]}}],
            "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 3}}  # fmt: skip
    h.register_mock(gemini.url("m"), json.dumps(call).encode())
    c = Gemini(h, "k").complete(TOOL)
    assert c.content == {"n": 1} and (c.tokens_in, c.tokens_out) == (12, 3)
    body = gemini.body(TOOL)
    assert body["toolConfig"]["functionCallingConfig"] == {"mode": "ANY", "allowedFunctionNames": ["record_matches"]}
    assert body["systemInstruction"]["parts"][0]["text"] == "sys" and "responseSchema" not in body["generationConfig"]
    text = {"candidates": [{"content": {"parts": [{"text": '```json\n{"n": 2, "k": "a"}\n```'}]}}]}
    h.register_mock(gemini.url("m"), json.dumps(text).encode())
    assert Gemini(h, "k").complete(JSON).content == {"n": 2, "k": "a"}
    assert gemini.body(JSON)["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_errors(tmp_path: Path) -> None:
    h = http(tmp_path)
    h.register_error(gemini.url("m"), 429)
    with pytest.raises(RateLimited):
        Gemini(h, "k").complete(TOOL)
    h.register_error(gemini.url("m"), 500)
    with pytest.raises(ProviderError):
        Gemini(h, "k").complete(TOOL)
    h.register_mock(gemini.url("m"), b'{"candidates": [{"content": {"parts": [{"text": "no json"}]}}]}')
    with pytest.raises(ProviderError):
        Gemini(h, "k").complete(TOOL)  # no function call
    assert not Gemini(h, None).available()


def test_openai_compatible_tool_call_json_and_429(tmp_path: Path) -> None:
    h = http(tmp_path)
    url = f"{GROQ_BASE_URL}/chat/completions"
    msg = {"tool_calls": [{"function": {"name": "record_matches", "arguments": '{"n": 3, "k": null}'}}]}
    h.register_mock(
        url, json.dumps({"choices": [{"message": msg}], "usage": {"prompt_tokens": 9, "completion_tokens": 4}}).encode()
    )
    groq = OpenAICompatible(h, "k", GROQ_BASE_URL, "groq")
    c = groq.complete(TOOL)
    assert c.content == {"n": 3, "k": None} and c.tokens_in == 9
    h.register_mock(url, json.dumps({"choices": [{"message": {"content": '{"n": 4, "k": "b"}'}}]}).encode())
    assert groq.complete(JSON).content == {"n": 4, "k": "b"}
    h.register_error(url, 429)
    with pytest.raises(RateLimited):
        groq.complete(JSON)


def test_retry_after_from_header_or_gemini_retry_info() -> None:
    req = httpx.Request("POST", "https://api.groq.com/x")
    e = httpx.HTTPStatusError(
        "429", request=req, response=httpx.Response(429, headers={"retry-after": "7"}, request=req)
    )
    assert retry_after(e) == 7.0
    body = '{"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "31s"}]}}'
    e2 = httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, text=body, request=req))
    assert retry_after(e2) == 31.0
    # a per-day quota is the day's, whatever retryDelay says: the router would otherwise wait it out every item
    # (docs/SPEC_ISSUES.md 59)
    daily = ('{"error": {"details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": '
             '[{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}, '
             '{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "19s"}]}}')  # fmt: skip
    e3 = httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, text=daily, request=req))
    assert retry_after(e3) is None
    minute = daily.replace("PerDayPerProject", "PerMinutePerProject")
    e4 = httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, text=minute, request=req))
    assert retry_after(e4) == 19.0
