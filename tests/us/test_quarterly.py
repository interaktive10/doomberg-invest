"""The quarterly run's 13F data sets (pipeline/us/quarterly.py): the first live run (2026-09-29) asked for the
June-August 2026 window, which SEC hadn't published yet (404), and stopped before the universe rebuild."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline.us.quarterly import fetch_windows
from pipeline.us.thirteenf import dataset_url

TODAY = date(2026, 9, 29)  # June-August closed 29 days ago: past the assumed lag, not yet released


def downloader(missing: set[str], calls: list[str]):
    def download(url: str, dest: Path) -> Path:
        calls.append(url)
        if any(m in url for m in missing):
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("404 Not Found", request=req, response=httpx.Response(404, request=req))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"zip")
        return dest

    return download


def test_an_unpublished_newest_window_falls_back_to_the_one_before(tmp_path: Path) -> None:
    calls: list[str] = []
    got = fetch_windows(downloader({"01jun2026-31aug2026"}, calls), tmp_path, TODAY, 1)
    assert [end for _, end in got] == [date(2026, 5, 31)]
    assert calls == [dataset_url(date(2026, 6, 1), date(2026, 8, 31)), dataset_url(date(2026, 3, 1), date(2026, 5, 31))]


def test_three_windows_are_the_three_newest_published_oldest_first(tmp_path: Path) -> None:
    got = fetch_windows(downloader({"01jun2026-31aug2026"}, []), tmp_path, TODAY, 3)
    assert [end for _, end in got] == [date(2025, 11, 30), date(2026, 2, 28), date(2026, 5, 31)]
    calls: list[str] = []
    again = fetch_windows(downloader({"01jun2026-31aug2026"}, calls), tmp_path, TODAY, 3)
    assert again == got and calls == [dataset_url(date(2026, 6, 1), date(2026, 8, 31))]  # the rest come from the cache


def test_a_missing_older_window_is_an_error_not_skipped(tmp_path: Path) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        fetch_windows(downloader({"01dec2025-28feb2026"}, []), tmp_path, TODAY, 3)
    with pytest.raises(RuntimeError, match="published"):  # nothing out at all within the spare windows
        fetch_windows(downloader({"2026_form13f", "2025_form13f"}, []), tmp_path / "none", TODAY, 1)
