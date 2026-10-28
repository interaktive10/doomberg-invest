"""The digest issue (BRIEF §4.12): created once a week, updated by a re-run; the real client's requests."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.digest import weekly
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


def test_the_real_client_reads_whether_the_repository_is_public(tmp_path: Path) -> None:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    http.register_mock(f"{API}/repos/o/r", json.dumps({"private": False}).encode())
    http.register_mock(f"{API}/repos/o/p", json.dumps({"private": True}).encode())
    assert GitHubIssues(http, "o/r", "t").public() and not GitHubIssues(http, "o/p", "t").public()
    assert weekly.repository_public(GitHubIssues(http, "o/unknown", "t"))  # not read: the safe side
    assert MockIssues(is_public=True).public() and not MockIssues().public()


BODY = """Week ending 2026-09-18. Research only: no orders, no price alerts.

## This week

US 4 → stage 4 → candidates 1 → new 0 · 1 of 4 fire one family, capped at 55

## To do

- Cards to accept or dismiss: 2 (Echo Grid Corp. (ECHO), Kappa Cables (KAPPA))
- Theses in review: 1 (Private Test (PRIV))

## What changed

- [PRIV](https://doomberg.example/company/x) Evidence 61 → 73: S4 fired
- [DISM](https://doomberg.example/company/y) left Candidate: Evidence 64 → 63

## Health

Sources: none late or stale.
"""


def test_a_public_repositorys_issue_names_no_company() -> None:
    """SPEC_ISSUES 57: the counts stay, the names go, and the issue points to the app for the rest."""
    pub = weekly.public_body(BODY, "https://doomberg.example")
    for name in ("ECHO", "KAPPA", "Echo Grid", "PRIV", "Private Test", "DISM", "/company/"):
        assert name not in pub, name
    assert "- Cards to accept or dismiss: 2\n- Theses in review: 1\n" in pub
    assert "## What changed\n\n2 changes: see the app.\n" in pub
    assert "US 4 → stage 4 → candidates 1 → new 0" in pub and "Sources: none late or stale." in pub
    assert pub.splitlines()[2] == f"{weekly.PUBLIC_NOTE} (https://doomberg.example)."
    quiet = weekly.public_body(BODY.replace("- Cards to accept or dismiss: 2 (Echo Grid Corp. (ECHO), Kappa Cables "
                                            "(KAPPA))\n- Theses in review: 1 (Private Test (PRIV))",
                                            "Nothing needs you this week.").replace(
        "- [PRIV](https://doomberg.example/company/x) Evidence 61 → 73: S4 fired\n- [DISM](https://doomberg.example/"
        "company/y) left Candidate: Evidence 64 → 63", "Nothing changed this week."))  # fmt: skip
    assert "Nothing needs you this week." in quiet and "Nothing changed this week." in quiet
