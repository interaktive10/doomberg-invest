"""The weekly run's bulk downloads (pipeline/us/weekly.py): the first live run (2026-09-29) got 403 for
daily-index/bulkdata/companyfacts.zip. SEC publishes companyfacts under daily-index/xbrl and submissions under
daily-index/bulkdata."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.us import weekly


class Stop(Exception):
    pass


def test_the_bulk_files_come_from_where_sec_publishes_them(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []

    class Client:
        def __init__(self, settings: object) -> None:
            pass

        def download(self, url: str, dest: Path) -> Path:
            calls.append((url, dest))
            if len(calls) == 2:
                raise Stop  # both URLs are known; the run itself needs a database
            return dest

    monkeypatch.setattr(weekly, "HttpClient", Client)
    monkeypatch.setenv("DOOM_CACHE_DIR", str(tmp_path))
    with pytest.raises(Stop):
        weekly.main([])
    assert [u for u, _ in calls] == [
        "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
        "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
    ]
    assert [d.name for _, d in calls] == ["companyfacts.zip", "submissions.zip"]


def test_local_files_skip_the_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    class Client:
        def __init__(self, settings: object) -> None:
            pass

        def download(self, url: str, dest: Path) -> Path:
            calls.append(url)
            return dest

    def no_db(*a: object, **k: object) -> None:
        raise Stop

    monkeypatch.setattr(weekly, "HttpClient", Client)
    monkeypatch.setattr(weekly.psycopg, "connect", no_db)
    monkeypatch.setenv("DOOM_CACHE_DIR", str(tmp_path))
    with pytest.raises(Stop):
        weekly.main(["--companyfacts", str(tmp_path / "cf.zip"), "--submissions", str(tmp_path / "sub.zip")])
    assert calls == []
