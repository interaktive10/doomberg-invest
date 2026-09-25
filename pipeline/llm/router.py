"""The free-tier LLM router (BRIEF §2.6).

- Input: a PromptInput (public data only; privacy.check runs first and raises PrivacyViolation).
- Providers are tried in config/quotas.yaml `routing` order. A provider is skipped when it has no client or key,
  its quota isn't filled in, today's requests or tokens are used up, or a 429 blocked it.
- On a 429 the provider is blocked (for its Retry-After, else until the next UTC day: the daily quota) and the next
  one is tried; any other failure (HTTP error, bad JSON) also moves to the next. Each attempt is logged (llm_calls).
- When every provider is out, the result is Deferred: the caller keeps the item `deferred` and the next day's run
  picks it up. A new UTC day resets the counters and the daily blocks (the clock is injectable: M5-03).
- Requests per minute are paced by sleeping on the clock.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from pipeline.llm import privacy
from pipeline.llm.prompt import PROMPTS, PromptInput, render, template
from pipeline.llm.providers.base import Provider, ProviderError, RateLimited, Request
from pipeline.llm.quotas import Quotas

CHARS_PER_TOKEN = 4  # the request-size estimate used before a call (the response's usage replaces it after)


class Clock(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class CallRecord:
    """One provider attempt, for the llm_calls table (the caller writes it: this package imports no db models)."""

    prompt_id: str
    provider: str
    model: str
    ok: bool
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class Done:
    content: dict[str, Any]
    provider: str
    model: str


@dataclass(frozen=True)
class Deferred:
    reason: str


@dataclass
class _Usage:
    requests: int = 0
    tokens: int = 0
    minute: deque[datetime] = field(default_factory=deque)
    blocked_until: datetime | None = None


def _next_day(t: datetime) -> datetime:
    return datetime.combine(t.date() + timedelta(days=1), datetime.min.time(), UTC)


def route(prompt_id: str) -> str:
    """The config/quotas.yaml `routing` key of a prompt (P-04 routes as P-04-fallback)."""
    spec = PROMPTS.get(prompt_id)
    return (spec.route or spec.id) if spec is not None else prompt_id


class Router:
    def __init__(
        self,
        providers: Mapping[str, Provider],
        quotas: Quotas,
        clock: Clock | None = None,
        log: Callable[[CallRecord], None] | None = None,
        used_today: Mapping[str, tuple[int, int]] | None = None,
    ) -> None:
        """`used_today`: provider -> (requests, tokens) already spent today (repo.llm_usage), so several runs in one
        day share the budget."""
        self.providers = dict(providers)
        self.quotas = quotas
        self.clock: Clock = clock or SystemClock()
        self.log = log
        self._day: date = self.clock.now().date()
        self._usage = {n: _Usage(*(used_today or {}).get(n, (0, 0))) for n in quotas.providers}

    # ------------------------------------------------------------------ state

    def _roll_day(self) -> None:
        today = self.clock.now().date()
        if today != self._day:
            self._day = today
            self._usage = {n: _Usage() for n in self.quotas.providers}

    def unavailable(self, name: str, tokens: int = 0) -> str | None:
        """Why `name` can't take a request of `tokens` now (None when it can)."""
        q = self.quotas.providers.get(name)
        p = self.providers.get(name)
        if q is None or p is None:
            return "no client"
        if not p.available():
            return "no API key"
        if not q.configured:
            return "quota not set in config/quotas.yaml"
        u = self._usage[name]
        if u.blocked_until is not None and self.clock.now() < u.blocked_until:
            return f"rate limited until {u.blocked_until:%Y-%m-%d %H:%M:%S}Z"
        if q.requests_per_day is not None and u.requests >= q.requests_per_day:
            return "daily requests used"
        if q.tokens_per_day is not None and u.tokens + tokens > q.tokens_per_day:
            return "daily tokens used"
        return None

    def exhausted(self, prompt_id: str) -> bool:
        """True when no provider routed for `prompt_id` can take a request now (callers stop early)."""
        self._roll_day()
        return all(self.unavailable(n) for n in self.quotas.routing.get(route(prompt_id), ()))

    def _pace(self, name: str) -> None:
        rpm = self.quotas.providers[name].requests_per_minute
        u = self._usage[name]
        if rpm is None or rpm <= 0:
            return
        while True:
            now = self.clock.now()
            while u.minute and (now - u.minute[0]).total_seconds() >= 60:
                u.minute.popleft()
            if len(u.minute) < rpm:
                return
            self.clock.sleep(60 - (now - u.minute[0]).total_seconds())

    def _record(self, prompt_id: str, name: str, model: str, ok: bool, t0: float, **kw: Any) -> None:
        if self.log is not None:
            ms = int((time.monotonic() - t0) * 1000)
            self.log(CallRecord(prompt_id, name, model, ok, ms, **kw))

    # ------------------------------------------------------------------ the call

    def call(self, data: PromptInput) -> Done | Deferred:
        privacy.check(data)
        spec = PROMPTS[data.prompt_id]
        variables = data.variables()
        system = render(template(spec.id, "system"), variables)
        user = render(template(spec.id, "user"), variables)
        schema = data.schema()
        estimate = (len(system) + len(user)) // CHARS_PER_TOKEN
        self._roll_day()
        reasons: list[str] = []
        for name in self.quotas.routing.get(route(spec.id), ()):
            why = self.unavailable(name, estimate)
            if why:
                reasons.append(f"{name}: {why}")
                continue
            q, u = self.quotas.providers[name], self._usage[name]
            model = q.model(spec.task)
            self._pace(name)
            req = Request(spec.id, model, system, user, schema, spec.mode, spec.tool_name, spec.temperature)
            t0 = time.monotonic()
            u.requests += 1
            u.minute.append(self.clock.now())
            try:
                c = self.providers[name].complete(req)
            except RateLimited as e:
                now = self.clock.now()
                u.blocked_until = now + timedelta(seconds=e.retry_after) if e.retry_after else _next_day(now)
                self._record(spec.id, name, model, False, t0, error=str(e)[:500])
                reasons.append(f"{name}: rate limited")
                continue
            except ProviderError as e:
                u.tokens += estimate
                self._record(spec.id, name, model, False, t0, error=str(e)[:500])
                reasons.append(f"{name}: {e}")
                continue
            used = (c.tokens_in or 0) + (c.tokens_out or 0)
            u.tokens += used or estimate
            self._record(spec.id, name, model, True, t0, tokens_in=c.tokens_in, tokens_out=c.tokens_out)
            return Done(c.content, name, model)
        return Deferred("; ".join(reasons) or f"no provider routed for {spec.id}")
