"""scripts/verify.py: BLOCKED is reported, never turned into PASS (BRIEF §9). M5-01 runs its mock-based structure
tests first and reports BLOCKED(key) only when they pass and no cassette is recorded. Retired checks are never run."""

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
    assert [c.id for c in verify.CHECKS if c.milestone == "m5"] == [f"M5-0{i}" for i in range(1, 5)]


def test_the_capex_desk_checks_are_retired() -> None:
    """Overhaul PR 4 (docs/SPEC_ISSUES.md 52): M5-05/06/07 tested the Capex Desk and S11, which are deleted, so they
    are retired (never run, listed as RETIRED in verify-m5 and later), and no check runs a deleted test file."""
    assert set(verify.RETIRED) == {"M5-05", "M5-06", "M5-07"}
    assert not set(verify.RETIRED) & {c.id for c in verify.CHECKS}
    commands = " ".join(" ".join(c.command) for c in verify.CHECKS)
    assert "tests/capex" not in commands and "test_capex.py" not in commands
    assert not any("capex" in c.description.lower() or "S1-S12" in c.description for c in verify.CHECKS)
    assert all((ROOT / p).exists() for c in verify.CHECKS for p in c.command if p.startswith("tests/"))


def test_retired_checks_are_listed_for_their_milestones(monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setattr(verify, "CHECKS", [])
    monkeypatch.setattr(verify, "write_report", lambda results, target: None)  # not docs/VERIFY_REPORT.md
    assert verify.main(["--milestone", "m4"]) == 0
    assert "RETIRED" not in capsys.readouterr().out
    assert verify.main(["--milestone", "m5"]) == 0
    out = capsys.readouterr().out.splitlines()
    retired = [line.split()[:2] for line in out if "RETIRED" in line]
    assert retired == [[i, "RETIRED"] for i in ("M5-05", "M5-06", "M5-07")]


def test_m7_01_is_the_restated_flow() -> None:
    """Overhaul PR 4: the Screener UI and the Capex Desk page are gone, so M7-01 is login -> candidates -> company ->
    thesis -> journal entry -> review -> close with a post-mortem (BRIEF §8), still read from flow.spec.ts."""
    m7_01 = next(c for c in verify.CHECKS if c.id == "M7-01")
    assert "candidates -> company -> thesis -> journal entry -> review -> close with a post-mortem" in m7_01.description
    assert "screener" not in m7_01.description and "capex" not in m7_01.description
    assert m7_01.command[-2:] == ["auth.setup.ts", "flow.spec.ts"]


def test_m6_checks() -> None:
    assert [c.id for c in verify.CHECKS if c.milestone == "m6"] == [f"M6-0{i}" for i in range(1, 7)]


def test_m8_05_has_no_human_step() -> None:
    """Overhaul PR 3 (docs/SPEC_ISSUES.md 51): the Lab's prices come from the Twelve Data download (lab-prices.yml),
    not a Stooq file Manzoor fetches through a CAPTCHA, so M8-05 runs the download's and the blocked run's tests and
    is never BLOCKED(human)."""
    m8 = [c for c in verify.CHECKS if c.milestone == "m8"]
    assert [c.id for c in m8] == [f"M8-0{i}" for i in range(1, 6)]
    m8_05 = m8[-1]
    assert m8_05.requires is None and m8_05.requires_after is None
    assert m8_05.command[: len(verify.PYTEST)] == verify.PYTEST
    assert {"tests/lab/test_price_history.py", "tests/lab/test_run.py"} <= set(m8_05.command)
    assert "Stooq" not in m8_05.description and "human" not in m8_05.description.replace("no human step", "")
    assert not hasattr(verify, "_needs_lab_prices") and not hasattr(verify, "LAB_PRICES")


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
