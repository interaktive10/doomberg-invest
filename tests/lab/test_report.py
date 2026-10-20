"""The Lab report (BRIEF §4.10.6, §8 M8-03): the first four §7 caveats, verbatim, at the top."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from pipeline.lab import report
from pipeline.lab.evaluate import Stat
from pipeline.lab.proposals import Proposal

BRIEF = Path(__file__).resolve().parents[2] / "docs" / "BRIEF.md"


def brief_caveats() -> list[str]:
    text = BRIEF.read_text(encoding="utf-8")
    section = text[text.index("## 7. Honest limits") :].split("\n---", 1)[0]
    return [ln for ln in section.splitlines() if re.match(r"^\d\. ", ln)][:4]


def test_caveats_are_the_briefs_verbatim() -> None:
    assert list(report.CAVEATS) == brief_caveats() and len(report.CAVEATS) == 4


def test_the_report_starts_with_the_caveats() -> None:
    info = report.RunInfo("us", date(2010, 1, 31), date(2026, 8, 31), 3, 30, 2,
                          {"in_sample": (date(2012, 1, 31), date(2018, 12, 31))}, "F-LAB synthetic panel")  # fmt: skip
    stats = [Stat("S1", 12, "in_sample", 2, 0.1, 0.1, 1.0, 0.05, 2.5, 0.02)]
    text = report.render(info, stats, [], [], [Proposal("S1", "signals", report_dec("1.0"), report_dec("1.5"), "x")])
    lines = text.splitlines()
    assert lines[0] == "# Signal Lab report" and lines[4:8] == brief_caveats()
    assert "| S1 | 12m | in-sample | 2 | +10.0% |" in text and "| signals.S1 | – | 1.0 | 1.5 | x |" in text
    blocked = report.render(info, [], [], [], [], blocked="BLOCKED(human: no prices)")
    assert blocked.splitlines()[4:8] == brief_caveats() and "**No run yet: BLOCKED(human: no prices)**" in blocked


def report_dec(x: str):  # type: ignore[no-untyped-def]
    from decimal import Decimal

    return Decimal(x)


def test_the_run_section_names_the_se_floor() -> None:
    """Review R1-F2: the report says t (NW) uses a standard error floored at the plain one (SPEC_ISSUES 19)."""
    info = report.RunInfo("us", date(2010, 1, 31), date(2026, 8, 31), 3, 30, 2,
                          {"in_sample": (date(2012, 1, 31), date(2018, 12, 31))}, "F-LAB synthetic panel")  # fmt: skip
    text = report.render(info, [], [], [], [])
    assert "floored at the plain standard error" in text and "docs/SPEC_ISSUES.md 19" in text
    assert "unfloored" in text


def test_the_report_gives_each_signals_verdict_when_no_weight_changes() -> None:
    """PR 3 review lab-F4: with no weight change no weights PR is opened, so the report PR (opened on every run) is
    where the verdicts are read: S1-S6 unproven at their weights, the L* at 0, S7-S12 not testable yet."""
    import yaml

    from pipeline.lab import run
    from pipeline.lab.proposals import propose

    weights = yaml.safe_load((BRIEF.parents[1] / "config" / "weights.yaml").read_text(encoding="utf-8"))
    props = propose([], weights, 12, run.lab_config()["not_testable"])
    assert props and all(p.new == p.old for p in props)  # nothing changes: no weights PR
    info = report.RunInfo("us", date(2010, 1, 31), date(2026, 8, 31), 3, 30, 0,
                          {"in_sample": (date(2012, 1, 31), date(2018, 12, 31))}, "F-LAB synthetic panel")  # fmt: skip
    text = report.render(info, [], [], [], props)
    assert "| Weight | Verdict | Now | Proposed | Why |" in text
    assert "| signals.S1 | unproven | 1.0 | 1.0 |" in text and "| legacy.L1 | unproven | 0.0 | 0.0 |" in text
    assert "| signals.S9 | not testable yet | 1.0 | 1.0 |" in text
