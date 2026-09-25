"""M8-05: a real Lab run is BLOCKED(human) until the Stooq bulk release asset exists."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.lab import run


def test_a_run_without_the_bulk_file_is_blocked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run.main(["--market", "us", "--prices", str(tmp_path / "d_us_txt.zip")]) == run.BLOCKED_EXIT
    out = capsys.readouterr().out
    assert "BLOCKED(human: the Stooq bulk file d_us_txt.zip is not attached to the `lab-data` release" in out


def test_india_waits_for_eight_quarters(capsys: pytest.CaptureFixture[str]) -> None:
    assert run.main(["--market", "in"]) == 0
    assert "not enabled" in capsys.readouterr().out
