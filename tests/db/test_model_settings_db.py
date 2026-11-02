"""The router reads Settings' OpenRouter pick from app_settings (docs/SPEC_ISSUES.md 69)."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from pipeline.db import facts_repo
from pipeline.llm.quotas import Quotas


def test_the_logged_router_uses_the_settings_pick(conn: psycopg.Connection[Any]) -> None:
    q = Quotas.load()
    before = facts_repo.logged_router(conn, {}, q, date(2026, 11, 2)).quotas.providers["openrouter"]
    assert before.models == q.providers["openrouter"].models
    conn.execute("insert into app_settings (key, value) values ('llm_models', %s), ('llm_effort', %s)",
                 (Jsonb({"extract": "z-ai/glm-5.3-flash"}), Jsonb({"card": "low"})))  # fmt: skip
    after = facts_repo.logged_router(conn, {}, q, date(2026, 11, 2)).quotas.providers["openrouter"]
    assert after.model("extract") == "z-ai/glm-5.3-flash" and after.reasoning["card"] == "low"
    assert after.model("card") == q.providers["openrouter"].model("card")
