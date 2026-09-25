"""The real provider clients, built from the environment's free-tier keys and config/quotas.yaml (BRIEF §2.6)."""

from __future__ import annotations

from pipeline.llm.providers.base import Provider
from pipeline.llm.providers.gemini import Gemini
from pipeline.llm.providers.openai_compat import GROQ_BASE_URL, OpenAICompatible
from pipeline.llm.quotas import Quotas
from pipeline.net.http import HttpClient
from pipeline.settings import Settings


def providers(http: HttpClient, settings: Settings, quotas: Quotas) -> dict[str, Provider]:
    out: dict[str, Provider] = {
        "gemini": Gemini(http, settings.gemini_api_key),
        "groq": OpenAICompatible(http, settings.groq_api_key, GROQ_BASE_URL, "groq"),
    }
    openrouter = quotas.providers.get("openrouter")
    if openrouter is not None and openrouter.base_url:
        out["openrouter"] = OpenAICompatible(http, settings.openrouter_api_key, openrouter.base_url, "openrouter")
    return out
