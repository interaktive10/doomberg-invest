"""scripts/verify.py: BLOCKED is reported, never turned into PASS (BRIEF §9). M5-01 runs its mock-based structure
tests first and reports BLOCKED(key) only when they pass and no cassette is recorded."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify  # noqa: E402


def check(command: list[str], after: str | None) -> verify.Check:
    return verify.Check("X-01", "m5", "test", command, requires_after=lambda: after)


def test_requires_after_blocks_only_a_passing_command() -> None:
    assert verify.run_check(check(["true"], "key:GEMINI_API_KEY")).status == "BLOCKED(key:GEMINI_API_KEY)"
    assert verify.run_check(check(["false"], "key:GEMINI_API_KEY")).status == "FAIL"  # structure tests must pass
    assert verify.run_check(check(["true"], None)).status == "PASS"


def test_m5_01_is_blocked_on_the_key_until_cassettes_exist() -> None:
    m5_01 = next(c for c in verify.CHECKS if c.id == "M5-01")
    assert m5_01.requires_after is verify._needs_cassettes and m5_01.requires is None
    recorded = any((verify.CASSETTES / "P-01").glob("*.json"))
    assert (verify._needs_cassettes() is None) == recorded
    assert "pipeline.facts.evaluate --replay" in m5_01.command[-1] and "tests/facts/test_fsyn.py" in m5_01.command[-1]
    assert [c.id for c in verify.CHECKS if c.milestone == "m5"] == [f"M5-0{i}" for i in range(1, 8)]


def test_m6_checks() -> None:
    assert [c.id for c in verify.CHECKS if c.milestone == "m6"] == [f"M6-0{i}" for i in range(1, 7)]


def test_a_failing_check_prints_its_whole_output(monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    """Overhaul PR 1 review (pipeline-F3): CI's only test run is M0-01 inside verify, so a failing check's whole
    output reaches the log (tracebacks and every FAILED line), not only the 6-line tail the summary and the report
    keep; a passing check's output stays out."""
    lines = [f"failure line {i}" for i in range(1, 21)]
    failing = [sys.executable, "-c", f"print({chr(10).join(lines)!r}); raise SystemExit(1)"]
    passing = [sys.executable, "-c", "print('quiet line')"]
    monkeypatch.setattr(verify, "CHECKS", [verify.Check("X-01", "m0", "fails", failing),
                                           verify.Check("X-02", "m0", "passes", passing)])  # fmt: skip
    monkeypatch.setattr(verify, "write_report", lambda results, target: None)  # not docs/VERIFY_REPORT.md
    assert verify.main(["--milestone", "m0"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert [line for line in out if line.startswith("failure line")] == lines
    assert out[-1] == "verify-m0: 1 PASS, 0 BLOCKED, 1 FAIL" and not any("quiet line" in line for line in out)
    assert "       failure line 20" in out  # the summary's tail, as before
