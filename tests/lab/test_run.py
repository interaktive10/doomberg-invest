"""M8-05: a real Lab run is BLOCKED(human) until the Stooq bulk release asset exists."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.lab import run


def test_a_run_without_the_bulk_file_is_blocked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run.main(["--market", "us", "--prices", str(tmp_path / "d_us_txt.zip")]) == run.BLOCKED_EXIT
    out = capsys.readouterr().out
    assert "BLOCKED(human: the Stooq bulk file d_us_txt.zip is not attached to the `lab-data-v1` release" in out


def test_india_waits_for_eight_quarters(capsys: pytest.CaptureFixture[str]) -> None:
    assert run.main(["--market", "in"]) == 0
    assert "not enabled" in capsys.readouterr().out


def test_the_release_is_the_one_manzoor_uploads() -> None:
    """BRIEF §11.5: the bulk file goes to the release asset `lab-data-v1`; config/lab.yaml and lab.yml use it."""
    root = Path(__file__).resolve().parents[2]
    tag = run.lab_config()["prices"]["release_tag"]
    assert f"release asset `{tag}`" in (root / "docs" / "BRIEF.md").read_text(encoding="utf-8")
    wf = (root / ".github" / "workflows" / "lab.yml").read_text(encoding="utf-8")
    assert f"gh release download {tag} " in wf and f"gh release upload {tag} " in wf
