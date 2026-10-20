"""Vercel deploys the web app (root directory web/). Its free plan stops deploying after its daily build limit: on
2026-10-07 every push built a preview, pipeline-only PRs included, until Vercel answered "Deployment rate limited -
retry in 24 hours", which holds production deploys back too. A push that changes neither web/ nor config/ skips the
build; without a parent commit the command fails and Vercel builds. Since overhaul PR 4 the deployment reads no file
outside web/: Settings no longer shows the config files, so next.config.ts traces none into it."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vercel_builds_only_when_the_app_or_its_config_changes() -> None:
    doc = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))
    assert doc["ignoreCommand"] == "git diff --quiet HEAD^ HEAD -- . ../config"


def test_the_deployment_traces_no_config_file() -> None:
    """Overhaul PR 4: web/lib/config-files.ts and the Settings YAML dumps are gone, and with them next.config.ts's
    outputFileTracingIncludes; no app code reads a file at run time (the old reader used node:fs on ../config)."""
    config = (ROOT / "web" / "next.config.ts").read_text(encoding="utf-8")
    assert "outputFileTracingIncludes" not in config and "config/*.yaml" not in config
    assert not (ROOT / "web" / "lib" / "config-files.ts").exists()
    runtime = [p for d in ("app", "components", "lib") for p in (ROOT / "web" / d).rglob("*.ts*")]
    reads = re.compile(r"""from ["'](?:node:)?fs(?:/promises)?["']""")
    assert runtime and not [p for p in runtime if reads.search(p.read_text(encoding="utf-8"))]


def test_the_screener_and_the_capex_desk_redirect() -> None:
    """Overhaul PR 4: the pages are gone and their old links land on Candidates and This week
    (web/tests/redirect.test.ts reads the same rules from next.config.ts)."""
    config = (ROOT / "web" / "next.config.ts").read_text(encoding="utf-8")
    assert '{ source: "/screener/:path*", destination: "/candidates", permanent: false }' in config
    assert '{ source: "/capex/:path*", destination: "/", permanent: false }' in config
    assert not (ROOT / "web" / "app" / "(app)" / "screener").exists()
    assert not (ROOT / "web" / "app" / "(app)" / "capex").exists()


def test_only_main_deploys() -> None:
    """Every PR push also made a preview deployment, which counts against the same daily limit; on 2026-10-08 the
    previews of pipeline PRs held the production deploy of the simplified app back. Only main deploys now."""
    doc = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))
    assert doc["git"]["deploymentEnabled"] == {"*": False, "main": True}
