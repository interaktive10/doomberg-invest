"""Weight proposals (BRIEF §4.10.5), read at config/lab.yaml `proposal_horizon_months`:

- out-of-sample mean excess > 0 and t_nw >= 2 and the same sign in-sample -> weight 1.5;
- out-of-sample insignificant -> 1.0;
- out-of-sample negative with t_nw <= -2 -> 0;
- legacy signals (L*) start at 0 and become live only by the first rule (insignificant keeps them at 0).

The thresholds are config/weights.yaml `lab_rules`. `render` rewrites only the changed weights and the version line
of config/weights.yaml, keeping every comment. The lab workflow commits that one file to a branch and opens a PR, and
config/weights.yaml is a protected path: the PR passes the `protected` check only with the human-approved label.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pipeline.lab.evaluate import Stat


@dataclass(frozen=True)
class Proposal:
    signal_id: str
    section: str  # "signals" | "legacy"
    old: Decimal
    new: Decimal
    reason: str


def rule(oos: Stat | None, ins: Stat | None, rules: Mapping[str, Any], legacy: bool) -> tuple[Decimal, str]:
    promote, neutral, demote = (Decimal(str(rules[k])) for k in ("promote_weight", "neutral_weight", "demote_weight"))
    t_up, t_down = float(rules["promote_min_t_nw"]), float(rules["demote_max_t_nw"])
    if oos is None or oos.mean is None or oos.t_nw is None:
        return (demote if legacy else neutral), "no out-of-sample events"
    if oos.mean > 0 and oos.t_nw >= t_up:
        if ins is not None and ins.mean is not None and ins.mean > 0:
            return promote, f"OOS mean {oos.mean:+.4f}, t_nw {oos.t_nw:.2f} >= {t_up:g}, in-sample {ins.mean:+.4f}"
        why = "has no events" if ins is None or ins.mean is None else f"mean {ins.mean:+.4f} has the opposite sign"
        return (demote if legacy else neutral), (f"OOS mean {oos.mean:+.4f}, t_nw {oos.t_nw:.2f} >= {t_up:g}, but "
                                                 f"in-sample {why}")  # fmt: skip
    if oos.mean < 0 and oos.t_nw <= t_down:
        return demote, f"OOS mean {oos.mean:+.4f}, t_nw {oos.t_nw:.2f} <= {t_down:g}"
    return (demote if legacy else neutral), f"OOS insignificant (mean {oos.mean:+.4f}, t_nw {oos.t_nw:.2f})"


def propose(stats: Sequence[Stat], weights: Mapping[str, Any], horizon: int) -> list[Proposal]:
    """One proposal per S* and L* weight in config/weights.yaml (unchanged ones included)."""
    by = {(s.signal_id, s.period): s for s in stats if s.horizon == horizon}
    out = []
    for section, is_legacy in (("signals", False), ("legacy", True)):
        for sid, old in (weights.get(section) or {}).items():
            new, why = rule(by.get((sid, "out_of_sample")), by.get((sid, "in_sample")), weights["lab_rules"], is_legacy)
            out.append(Proposal(str(sid), section, Decimal(str(old)), new, why))
    return out


def render(text: str, proposals: Sequence[Proposal], version: str) -> str:
    """config/weights.yaml with the proposed weights and a new version; comments and layout unchanged."""
    changes = {(p.section, p.signal_id): p.new for p in proposals if p.new != p.old}
    if not changes:
        return text  # nothing to propose: no new version, no PR (lab.yml's "no weight change" branch)
    lines = text.splitlines(keepends=True)
    section = ""
    for i, line in enumerate(lines):
        top = re.match(r"^(\w+):", line)
        if top:
            section = top.group(1)
            if section == "version":
                lines[i] = re.sub(r"^version:\s*\S+", f"version: {version}", line)
            continue
        m = re.match(r"^(\s+)(\w+):(\s*)([-\d.]+)(.*)$", line.rstrip("\n"))
        if m and (section, m.group(2)) in changes:
            lines[i] = f"{m.group(1)}{m.group(2)}:{m.group(3)}{changes[(section, m.group(2))]}{m.group(5)}\n"
    return "".join(lines)
