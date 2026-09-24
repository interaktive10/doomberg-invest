"""M0-07: protected paths need the `human-approved` label (BRIEF Appendix D). PROTECTED."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import protected_check  # noqa: E402

PROTECTED_SAMPLES = [
    "config/guards.yaml",
    "config/signals.yaml",
    "config/weights.yaml",
    "config/context.yaml",
    "config/redflags.yaml",
    "scripts/guard.py",
    "tests/guard/cases/broker_import.py",
    "tests/guard/test_guard.py",
    "pipeline/llm/privacy.py",
    "pipeline/db/pit.py",
    ".claude/agents/reviewer.md",
    "docs/BRIEF.md",
]


@pytest.mark.parametrize("path", PROTECTED_SAMPLES)
def test_protected_file_without_label_fails(path: str) -> None:
    ok, hits = protected_check.evaluate(["pipeline/us/form4.py", path], labels=["enhancement"])
    assert not ok and hits == [path]


@pytest.mark.parametrize("path", PROTECTED_SAMPLES)
def test_protected_file_with_label_passes(path: str) -> None:
    assert protected_check.evaluate([path], labels=["human-approved"]) == (True, [path])


def test_unprotected_diff_passes_without_label() -> None:
    files = ["pipeline/us/form4.py", "config/quotas.yaml", "docs/DECISIONS.log", "tests/test_x.py", "config/terms.yaml"]
    assert protected_check.evaluate(files, labels=[]) == (True, [])


def test_lookalikes_are_not_protected() -> None:
    assert protected_check.evaluate(["config/signals.yaml.bak", "tests/guardian.py", "docs/BRIEF.md.orig"], []) == (
        True,
        [],
    )


def test_cli_synthetic_diff_exit_codes() -> None:
    script = str(ROOT / "scripts" / "protected_check.py")
    bad = subprocess.run([sys.executable, script, "--files", "config/weights.yaml"], capture_output=True, text=True)
    assert bad.returncode == 1 and "config/weights.yaml" in bad.stderr
    good = subprocess.run(
        [sys.executable, script, "--files", "config/weights.yaml", "--labels", "x,human-approved"],
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0


def test_cli_git_diff_mode(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "weights.yaml").write_text("a: 1\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "feature")
    (tmp_path / "config" / "weights.yaml").write_text("a: 2\n")
    git("commit", "-qam", "change weights")
    script = str(ROOT / "scripts" / "protected_check.py")
    p = subprocess.run([sys.executable, script, "--base", "main"], cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 1 and "config/weights.yaml" in p.stderr
