"""The quarterly run's 13F data sets (pipeline/us/quarterly.py). The first live run (2026-09-29) and the 2026-10-26 run
asked for the June-August 2026 window at structureddata/ and got a 404: SEC had published it on 2026-09-14 under
datastandardsinnovation/ (every earlier window stays under structureddata/), so ownership_q stopped at 2026-03-31 while
both runs read "ok"."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline.us.quarterly import fetch_windows
from pipeline.us.thirteenf import dataset_urls

TODAY = date(2026, 10, 26)  # the second run: June-August closed 56 days ago, published 42 days ago
NEW, OLD = 0, 1  # dataset_urls() order: datastandardsinnovation/, then structureddata/
JUN_AUG = dataset_urls(date(2026, 6, 1), date(2026, 8, 31))
MAR_MAY = dataset_urls(date(2026, 3, 1), date(2026, 5, 31))
DEC_FEB = dataset_urls(date(2025, 12, 1), date(2026, 2, 28))
SEP_NOV = dataset_urls(date(2025, 9, 1), date(2025, 11, 30))
SEC_NOW = {JUN_AUG[NEW], MAR_MAY[OLD], DEC_FEB[OLD], SEP_NOV[OLD]}  # what SEC serves (HEAD-checked 2026-10-28)


def sec(served: set[str], calls: list[str], errors: dict[str, int] | None = None):
    """A fake SEC: the exact URLs in `served` download, `errors` answer their status, anything else is a 404."""

    def download(url: str, dest: Path) -> Path:
        calls.append(url)
        status = (errors or {}).get(url, 0 if url in served else 404)
        if status:
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(f"{status}", request=req, response=httpx.Response(status, request=req))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"zip")
        return dest

    return download


def test_the_june_august_2026_window_is_read_from_secs_new_directory(tmp_path: Path) -> None:
    """Regression (2026-10-26): the newest window is SEC's, not the one before it."""
    calls: list[str] = []
    notes: list[str] = []
    got = fetch_windows(sec(SEC_NOW, calls), tmp_path, TODAY, 1, notes)
    assert [end for _, end in got] == [date(2026, 8, 31)]
    assert calls == [JUN_AUG[NEW]] and notes == []
    assert JUN_AUG[NEW] == (
        "https://www.sec.gov/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip"
    )


def test_older_windows_still_come_from_the_old_directory(tmp_path: Path) -> None:
    calls: list[str] = []
    got = fetch_windows(sec(SEC_NOW, calls), tmp_path, TODAY, 3)
    assert [end for _, end in got] == [date(2026, 2, 28), date(2026, 5, 31), date(2026, 8, 31)]
    assert calls == [JUN_AUG[NEW], MAR_MAY[NEW], MAR_MAY[OLD], DEC_FEB[NEW], DEC_FEB[OLD]]
    again: list[str] = []
    assert fetch_windows(sec(SEC_NOW, again), tmp_path, TODAY, 3) == got and again == []  # all from the cache


def test_an_unpublished_newest_window_falls_back_and_says_so(tmp_path: Path) -> None:
    calls: list[str] = []
    notes: list[str] = []
    got = fetch_windows(sec(SEC_NOW - {JUN_AUG[NEW]}, calls), tmp_path, TODAY, 1, notes)
    assert [end for _, end in got] == [date(2026, 5, 31)]
    assert calls == [*JUN_AUG, *MAR_MAY]
    assert len(notes) == 1 and "2026-06-01..2026-08-31" in notes[0] and all(u in notes[0] for u in JUN_AUG)


def test_a_missing_older_window_is_an_error_not_skipped(tmp_path: Path) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        fetch_windows(sec(SEC_NOW - {DEC_FEB[OLD]}, []), tmp_path, TODAY, 3)
    with pytest.raises(RuntimeError, match="published"):  # nothing out at all within the spare windows
        fetch_windows(sec(set(), []), tmp_path / "none", TODAY, 1)


def test_a_refusal_is_an_error_not_a_missing_file(tmp_path: Path) -> None:
    """A 403 (SEC refusing the user agent or rate) neither falls back nor tries the other directory."""
    calls: list[str] = []
    with pytest.raises(httpx.HTTPStatusError, match="403"):
        fetch_windows(sec(SEC_NOW, calls, errors={JUN_AUG[NEW]: 403}), tmp_path, TODAY, 1)
    assert calls == [JUN_AUG[NEW]]
