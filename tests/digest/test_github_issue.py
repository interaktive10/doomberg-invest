"""The digest issue (BRIEF §4.12): created once a week, updated by a re-run; the real client's requests."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.digest.github_issue import API, GitHubIssues, MockIssues, publish
from pipeline.net.http import HttpClient
from pipeline.settings import Settings


def test_publish_creates_then_updates_the_weeks_issue() -> None:
    api = MockIssues()
    assert publish(api, "Doomberg weekly — 2026-W38", "body 1") == 1
    assert publish(api, "Doomberg weekly — 2026-W38", "body 2") == 1
    assert publish(api, "Doomberg weekly — 2026-W39", "body 3") == 2
    assert api.issues[1]["body"] == "body 2" and [m for m, _, _ in api.requests] == ["GET", "POST", "GET", "PATCH",
                                                                                      "GET", "POST"]  # fmt: skip


def test_the_real_client_finds_by_title_among_digest_issues(tmp_path: Path) -> None:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    listing = [{"number": 7, "title": "Doomberg weekly — 2026-W38"},
               {"number": 9, "title": "Doomberg weekly — 2026-W38", "pull_request": {}}]  # fmt: skip
    http.register_mock(f"{API}/repos/o/r/issues?state=all&labels=digest&per_page=100", json.dumps(listing).encode())
    gh = GitHubIssues(http, "o/r", "t0ken")
    assert gh.find("Doomberg weekly — 2026-W38") == 7 and gh.find("Doomberg weekly — 2026-W39") is None
    assert gh._headers()["Authorization"] == "Bearer t0ken"
