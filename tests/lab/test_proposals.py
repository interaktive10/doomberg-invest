"""Weight proposals (BRIEF §4.10.5, §8 M8-04): the rule, and a proposal commit that touches only
config/weights.yaml, which the protected check fails without the human-approved label."""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

import yaml

from pipeline.lab.evaluate import Stat
from pipeline.lab.proposals import propose, render, rule

ROOT = Path(__file__).resolve().parents[2]
RULES = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))["lab_rules"]


def s(sid: str, period: str, mean: float | None, t: float | None, n: int = 50) -> Stat:
    return Stat(sid, 12, period, n, mean, mean, None, None, t, None)


def test_the_rule() -> None:
    assert rule(s("S1", "out_of_sample", 0.05, 2.0), s("S1", "in_sample", 0.01, 0.5), RULES, False)[0] == D("1.5")
    assert rule(s("S1", "out_of_sample", 0.05, 2.0), s("S1", "in_sample", -0.01, 0.5), RULES, False)[0] == D("1.0")
    assert rule(s("S1", "out_of_sample", 0.05, 1.99), s("S1", "in_sample", 0.01, 3), RULES, False)[0] == D("1.0")
    assert rule(s("S1", "out_of_sample", -0.05, -2.0), None, RULES, False)[0] == D("0.0")
    assert rule(s("S1", "out_of_sample", -0.05, -1.9), None, RULES, False)[0] == D("1.0")
    assert rule(None, None, RULES, False)[0] == D("1.0")
    # legacy rules start at 0 and go live only by the first rule
    assert rule(s("L1", "out_of_sample", 0.05, 1.0), s("L1", "in_sample", 0.02, 1.0), RULES, True)[0] == D("0.0")
    assert rule(s("L1", "out_of_sample", 0.05, 2.5), s("L1", "in_sample", 0.02, 1.0), RULES, True)[0] == D("1.5")


def weights_text() -> str:
    return (ROOT / "config" / "weights.yaml").read_text(encoding="utf-8")


def test_render_changes_only_the_proposed_values_and_the_version() -> None:
    stats = [s("S3", "out_of_sample", 0.06, 3.1), s("S3", "in_sample", 0.02, 1.0),
             s("S9", "out_of_sample", -0.05, -2.2), s("L2", "out_of_sample", 0.04, 2.4),
             s("L2", "in_sample", 0.01, 0.3)]  # fmt: skip
    props = propose(stats, yaml.safe_load(weights_text()), 12)
    changed = {(p.section, p.signal_id): p.new for p in props if p.new != p.old}
    assert changed == {("signals", "S3"): D("1.5"), ("signals", "S9"): D("0.0"), ("legacy", "L2"): D("1.5")}
    before, after = weights_text(), render(weights_text(), props, "lab-2026-10-01")
    diff = [(a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b]
    assert [b for _, b in diff] == ["version: lab-2026-10-01", "  S3: 1.5", "  S9: 0.0", "  L2: 1.5"]
    new = yaml.safe_load(after)
    assert (
        new["signals"]["S3"] == 1.5
        and new["legacy"]["L2"] == 1.5
        and new["families"] == yaml.safe_load(before)["families"]
    )


def test_the_proposal_commit_touches_only_weights_and_needs_the_label(tmp_path: Path) -> None:
    """M8-04: what lab.yml commits for its PR is config/weights.yaml alone; the protected check fails on it without
    the human-approved label and passes with it."""

    def git(*args: str) -> str:
        out = subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True)
        return out.stdout

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "weights.yaml").write_text(weights_text(), encoding="utf-8")
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "base")
    props = propose([s("S3", "out_of_sample", 0.06, 3.1), s("S3", "in_sample", 0.02, 1.0)],
                    yaml.safe_load(weights_text()), 12)  # fmt: skip
    path = tmp_path / "config" / "weights.yaml"
    path.write_text(render(path.read_text(encoding="utf-8"), props, "lab-2026-10-01"), encoding="utf-8")
    files = git("diff", "--name-only").split()
    assert files == ["config/weights.yaml"]
    check = [sys.executable, str(ROOT / "scripts" / "protected_check.py"), "--files", *files]
    assert subprocess.run([*check, "--labels", ""], capture_output=True).returncode == 1
    assert subprocess.run([*check, "--labels", "human-approved"], capture_output=True).returncode == 0
