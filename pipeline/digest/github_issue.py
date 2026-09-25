"""The digest's GitHub issue (BRIEF §4.12): "Doomberg weekly — {week}" in the private repo, created by weekly.yml
with the workflow's GITHUB_TOKEN (issues: write); GitHub e-mails Manzoor for free. A re-run of the week edits the
same issue (found by its title among the `digest`-labelled issues) instead of opening another.

`MockIssues` is the mock (MOCK_EXTERNALS=true, tests): it keeps issues in memory and records every request."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pipeline.net.http import HttpClient

API = "https://api.github.com"
LABEL = "digest"


class Issues(Protocol):
    def find(self, title: str) -> int | None: ...
    def create(self, title: str, body: str) -> int: ...
    def update(self, number: int, body: str) -> None: ...


@dataclass
class GitHubIssues:
    http: HttpClient
    repo: str  # owner/name (GITHUB_REPOSITORY)
    token: str

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}  # fmt: skip

    def find(self, title: str) -> int | None:
        url = f"{API}/repos/{self.repo}/issues?state=all&labels={LABEL}&per_page=100"
        for issue in json.loads(self.http.get_bytes(url, headers=self._headers())):
            if issue.get("title") == title and "pull_request" not in issue:
                return int(issue["number"])
        return None

    def create(self, title: str, body: str) -> int:
        payload = {"title": title, "body": body, "labels": [LABEL]}
        raw = self.http.send_json("POST", f"{API}/repos/{self.repo}/issues", payload, headers=self._headers())
        return int(json.loads(raw)["number"])

    def update(self, number: int, body: str) -> None:
        self.http.send_json("PATCH", f"{API}/repos/{self.repo}/issues/{number}", {"body": body},
                            headers=self._headers())  # fmt: skip


@dataclass
class MockIssues:
    issues: dict[int, dict[str, Any]] = field(default_factory=dict)
    requests: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def find(self, title: str) -> int | None:
        self.requests.append(("GET", f"/issues?labels={LABEL}", {}))
        return next((n for n, i in self.issues.items() if i["title"] == title), None)

    def create(self, title: str, body: str) -> int:
        n = len(self.issues) + 1
        self.issues[n] = {"title": title, "body": body, "labels": [LABEL]}
        self.requests.append(("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]}))
        return n

    def update(self, number: int, body: str) -> None:
        self.issues[number]["body"] = body
        self.requests.append(("PATCH", f"/issues/{number}", {"body": body}))


def publish(api: Issues, title: str, body: str) -> int:
    """Create the week's issue, or update it when a re-run finds it."""
    number = api.find(title)
    if number is None:
        return api.create(title, body)
    api.update(number, body)
    return number
