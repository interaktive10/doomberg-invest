"""Vercel deploys the web app (root directory web/). Its free plan stops deploying after its daily build limit: on
2026-10-07 every push built a preview, pipeline-only PRs included, until Vercel answered "Deployment rate limited -
retry in 24 hours", which holds production deploys back too. A push that changes neither web/ nor the config/*.yaml
the Settings page reads (web/next.config.ts traces them into the deployment) skips the build; without a parent commit
the command fails and Vercel builds."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vercel_builds_only_when_the_app_or_its_config_changes() -> None:
    doc = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))
    assert doc["ignoreCommand"] == "git diff --quiet HEAD^ HEAD -- . ../config"
    traced = (ROOT / "web" / "next.config.ts").read_text(encoding="utf-8")
    assert '"../config/*.yaml"' in traced  # the only files outside web/ the deployment reads


def test_only_main_deploys() -> None:
    """Every PR push also made a preview deployment, which counts against the same daily limit; on 2026-10-08 the
    previews of pipeline PRs held the production deploy of the simplified app back. Only main deploys now."""
    doc = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))
    assert doc["git"]["deploymentEnabled"] == {"*": False, "main": True}


def test_a_daily_cron_keeps_the_database_awake() -> None:
    """Supabase's free plan pauses after 7 days without activity; with Actions blocked (billing, 2026-10-20) nothing
    else touched it. Vercel's free plan allows a daily cron: it reads one row through /api/keepalive, which the
    middleware lets through without a session."""
    doc = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))
    assert doc["crons"] == [{"path": "/api/keepalive", "schedule": "17 9 * * *"}]
    assert (ROOT / "web" / "app" / "api" / "keepalive" / "route.ts").exists()
    assert '"/api/keepalive"' in (ROOT / "web" / "middleware.ts").read_text(encoding="utf-8")
