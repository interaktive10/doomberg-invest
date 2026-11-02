"""Settings picks OpenRouter's model and effort per task (docs/SPEC_ISSUES.md 69): config/quotas.yaml lists what may be
picked; app_settings holds the pick; the router uses it; caps stay as configured."""

from __future__ import annotations

from pipeline.llm.quotas import Quotas


def test_a_listed_model_and_effort_replace_the_configs_per_task() -> None:
    q = Quotas.load()
    assert "deepseek/deepseek-v4.1-flash" in q.choices() and len(q.choices()) >= 5
    p = q.with_settings({"extract": "z-ai/glm-5.3-flash", "card": "deepseek/deepseek-v4.1-flash"},
                        {"extract": "none", "card": "medium"}).providers["openrouter"]  # fmt: skip
    assert p.model("extract") == "z-ai/glm-5.3-flash" and p.model("card") == "deepseek/deepseek-v4.1-flash"
    assert p.reasoning == {"card": "medium"}  # none sends no effort
    assert p.requests_per_day == q.providers["openrouter"].requests_per_day  # the caps hold


def test_anything_unlisted_keeps_the_configs_value() -> None:
    q = Quotas.load()
    base = q.providers["openrouter"]
    p = q.with_settings({"extract": "openai/gpt-7-ultra", "card": 5}, {"card": "max"}).providers["openrouter"]
    assert p.models == base.models and p.reasoning == base.reasoning
    assert q.with_settings(None, None).providers["openrouter"] == base
