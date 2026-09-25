"""SEC bulk files (BRIEF §4.1.1): companyfacts.zip and submissions.zip, or a directory holding the same JSON files."""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path


def index_pages(names: Iterable[str]) -> dict[str, list[str]]:
    """CIK -> its older-filings pages (CIK##########-submissions-001.json ...), in order. submissions.zip holds ~1M
    members, so this is built once per run; each company's lookup is then a dict hit, not a scan (review F1)."""
    pages: dict[str, list[str]] = {}
    for n in names:
        cik, sep, rest = n.partition("-submissions-")
        if sep and cik.startswith("CIK") and rest.endswith(".json"):
            pages.setdefault(cik[3:], []).append(n)
    for v in pages.values():
        v.sort()
    return pages


class JsonSource:
    """Members of a bulk zip (companyfacts.zip, submissions.zip) or a directory of the same JSON files."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip = zipfile.ZipFile(path) if path.is_file() else None
        names = self._zip.namelist() if self._zip else [p.name for p in path.glob("*.json")]
        self._names = set(names)
        self._pages = index_pages(names)

    def read(self, name: str) -> bytes | None:
        if name not in self._names:
            return None
        return self._zip.read(name) if self._zip else (self.path / name).read_bytes()

    def pages(self, cik: str) -> list[bytes]:
        return [b for n in self._pages.get(cik, []) if (b := self.read(n)) is not None]
