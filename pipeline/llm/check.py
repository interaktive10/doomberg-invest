"""A live check of each LLM provider (llm-check.yml, manual; docs/SPEC_ISSUES.md 63): one tiny JSON answer and one
forced tool call per provider with a key, through the real clients and config/quotas.yaml's models and reasoning
efforts. Prints only ok, latency and token counts (the log is public), and the database's region, which decides the
web app's Vercel region (web/vercel.json). Exit 1 when the first provider in P-01's routing fails.

`python -m pipeline.llm.check`."""

from __future__ import annotations

import sys
import time
from urllib.parse import urlparse

from pipeline.llm.clients import providers
from pipeline.llm.providers.base import ProviderError, RateLimited, Request
from pipeline.llm.quotas import Quotas
from pipeline.net.http import HttpClient
from pipeline.settings import Settings

ANSWER = {"type": "object", "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}},
          "required": ["ok", "word"]}  # fmt: skip


def probes(model: str, effort: str | None) -> list[Request]:
    system = "You are a health check. Answer with the requested JSON only."
    user = 'Return {"ok": true, "word": "<one word that names a color>"}.'
    return [Request("check-json", model, system, user, ANSWER, "json", "record_check", 0.0, effort),
            Request("check-tool", model, system, user, ANSWER, "tool", "record_check", 0.0, effort)]  # fmt: skip


def db_region(url: str) -> str:
    """The region part of a Supabase pooler host (aws-0-ap-south-1.pooler.supabase.com -> ap-south-1)."""
    host = urlparse(url).hostname or ""
    first = host.split(".")[0]
    if first.startswith("aws-") and first.count("-") >= 2:
        return first.split("-", 2)[2]
    return "unknown (not a pooler host)"


def main() -> int:
    settings = Settings.from_env()
    quotas = Quotas.load()
    clients = providers(HttpClient(settings), settings, quotas)
    print(f"database region: {db_region(settings.database_url)}")
    first = (quotas.routing.get("P-01") or ("",))[0]
    failed_first = False
    for name, client in clients.items():
        q = quotas.providers.get(name)
        if q is None or not client.available():
            print(f"{name}: no key or no quota (skipped)")
            continue
        for task in ("extract", "card"):
            for req in probes(q.model(task), q.reasoning.get(task)):
                t0 = time.monotonic()
                try:
                    c = client.complete(req)
                    ok = bool(c.content.get("ok"))
                    what = f"ok={ok} tokens {c.tokens_in}/{c.tokens_out}"
                except (ProviderError, RateLimited) as e:
                    ok, what = False, f"failed: {str(e)[:160]}"
                ms = int(1000 * (time.monotonic() - t0))
                print(f"{name} {task} {req.mode:4s} {req.model} effort={req.reasoning_effort}: {what} in {ms} ms")
                failed_first = failed_first or (name == first and not ok)
    return 1 if failed_first else 0


if __name__ == "__main__":
    sys.exit(main())
