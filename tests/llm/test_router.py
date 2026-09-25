"""M5-03: the router falls back on a 429, defers when every provider is out, and the next day's run picks the item
up (simulated clock); budgets and pacing come from config/quotas.yaml (BRIEF §2.6)."""

from __future__ import annotations

from pipeline.india.triage import TriageInput
from pipeline.llm.providers.base import ProviderError, RateLimited
from pipeline.llm.router import CallRecord, Deferred, Done, Router
from tests.llm.conftest import FakeClock, Scripted, quotas

ITEM = TriageInput("Award of Order", "The company has received an order worth Rs 450 crore for 765 kV substations.")
ANSWER = {"categories": ["order_win"], "read_pdf": True}


def providers(*scripts: list[object]) -> dict[str, Scripted]:
    names = ("gemini", "groq", "openrouter")
    return {n: Scripted(n, list(s)) for n, s in zip(names, scripts, strict=False)}


def test_a_429_falls_back_to_the_next_provider(clock: FakeClock) -> None:
    ps = providers([RateLimited("gemini: 429")], [ANSWER], [])
    log: list[CallRecord] = []
    r = Router(ps, quotas(), clock, log.append)
    out = r.call(ITEM)
    assert isinstance(out, Done) and out.provider == "groq" and out.model == "groq-small"
    assert out.content == ANSWER
    assert [(c.provider, c.ok) for c in log] == [("gemini", False), ("groq", True)]
    assert r.unavailable("gemini", 0) == "rate limited until 2026-09-26 00:00:00Z"  # no Retry-After: the day's quota
    assert len(ps["openrouter"].requests) == 0


def test_all_providers_exhausted_defers_and_the_next_day_picks_it_up(clock: FakeClock) -> None:
    ps = providers([RateLimited("429"), ANSWER], [RateLimited("429")], [RateLimited("429")])
    r = Router(ps, quotas(), clock)
    first = r.call(ITEM)
    assert isinstance(first, Deferred)
    assert "gemini: rate limited" in first.reason and "openrouter: rate limited" in first.reason
    assert r.exhausted("P-07")
    later_today = r.call(ITEM)  # still blocked: nobody is asked again today
    assert isinstance(later_today, Deferred) and len(ps["gemini"].requests) == 1
    clock.advance(hours=15)  # 2026-09-26 00:00 UTC: a new day resets the daily blocks
    out = r.call(ITEM)
    assert isinstance(out, Done) and out.provider == "gemini" and not r.exhausted("P-07")


def test_retry_after_blocks_only_for_that_long(clock: FakeClock) -> None:
    ps = providers([RateLimited("429", retry_after=30), ANSWER], [ProviderError("groq: HTTP 503")], [])
    r = Router(ps, quotas(), clock)
    assert isinstance(r.call(ITEM), Done)  # gemini 429 -> groq 503 -> openrouter answers
    clock.advance(seconds=31)
    out = r.call(ITEM)
    assert isinstance(out, Done) and out.provider == "gemini"


def test_daily_request_budget_and_usage_carried_from_earlier_runs(clock: FakeClock) -> None:
    ps = providers([ANSWER, ANSWER], [ANSWER], [])
    r = Router(ps, quotas(rpd=2), clock, used_today={"gemini": (1, 0), "groq": (2, 0), "openrouter": (2, 0)})
    assert isinstance(r.call(ITEM), Done)  # gemini's second request of the day
    out = r.call(ITEM)
    assert isinstance(out, Deferred) and "gemini: daily requests used" in out.reason


def test_token_budget_skips_a_provider_that_cannot_take_the_request(clock: FakeClock) -> None:
    ps = providers([ANSWER], [ANSWER], [])
    r = Router(ps, quotas(tpd=10), clock)  # the request alone is ~25 tokens
    out = r.call(ITEM)
    assert isinstance(out, Deferred) and "daily tokens used" in out.reason and not ps["gemini"].requests


def test_unfilled_quota_or_missing_key_means_unavailable(clock: FakeClock) -> None:
    ps = providers([ANSWER], [ANSWER], [ANSWER])
    ps["gemini"].key = False
    r = Router(ps, quotas(rpd=None), clock)
    out = r.call(ITEM)
    assert isinstance(out, Deferred)
    assert "gemini: no API key" in out.reason and "groq: quota not set in config/quotas.yaml" in out.reason


def test_requests_per_minute_are_paced_on_the_clock(clock: FakeClock) -> None:
    ps = providers([ANSWER] * 3, [], [])
    r = Router(ps, quotas(rpm=2), clock)
    for _ in range(3):
        assert isinstance(r.call(ITEM), Done)
    assert clock.slept == 60.0  # the third request waited for the first to leave the minute window


def test_the_request_carries_the_verbatim_prompt_and_the_task_model(clock: FakeClock) -> None:
    ps = providers([ANSWER], [], [])
    Router(ps, quotas(), clock).call(ITEM)
    req = ps["gemini"].requests[0]
    assert req.system.startswith("Classify one Indian exchange announcement title and summary.")
    assert req.user == f"TITLE: {ITEM.title}\nSUMMARY: {ITEM.summary}"
    assert req.mode == "json" and req.temperature == 0.0 and req.model == "gemini-small"  # P-07: Flash-Lite class
