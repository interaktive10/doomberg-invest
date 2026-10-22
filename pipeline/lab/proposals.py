"""Weight proposals (BRIEF §4.10.5), read at config/lab.yaml `proposal_horizon_months`:

- out-of-sample mean excess > 0 and t_nw >= 2 and the same sign in-sample -> weight 1.5;
- out-of-sample insignificant -> 1.0;
- out-of-sample negative with t_nw <= -2 -> 0;
- legacy signals (L*) start at 0 and become live only by the first rule (insignificant keeps them at 0).

The thresholds are config/weights.yaml `lab_rules`. Each signal also gets one verdict from the same rule (`verdict`):
works (the first rule), hurts (the third) or unproven (anything else); the signals config/lab.yaml lists as
`not_testable` (S7-S12: no history before 2026) are "not testable yet" and keep their weights, so S9 never earns
weight. `render` rewrites only the changed weights and the version line of config/weights.yaml, keeping every comment.
The lab workflow commits that one file to a branch and opens a PR with `pr_body`, and config/weights.yaml is a
protected path: the PR passes the `protected` check only with the human-approved label.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
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
    verdict: str = ""  # works | unproven | hurts | not testable yet (verdict)


NOT_TESTABLE = "not testable yet"
REOPEN = "close and reopen to run the checks, then add human-approved"


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


def verdict(oos: Stat | None, ins: Stat | None, rules: Mapping[str, Any]) -> str:
    """The Lab's one verdict on a signal, read from the §4.10.5 rule itself: works where it proposes the promoted
    weight, hurts where it proposes the demoted one, unproven otherwise (legacy signals are judged the same way)."""
    new, _ = rule(oos, ins, rules, False)
    if new == Decimal(str(rules["promote_weight"])):
        return "works"
    return "hurts" if new == Decimal(str(rules["demote_weight"])) else "unproven"


def propose(stats: Sequence[Stat], weights: Mapping[str, Any], horizon: int, not_testable: Collection[str] = ()
            ) -> list[Proposal]:  # fmt: skip
    """One proposal per S* and L* weight in config/weights.yaml (unchanged ones included); a signal in `not_testable`
    keeps its weight whatever its statistics say."""
    by = {(s.signal_id, s.period): s for s in stats if s.horizon == horizon}
    rules = weights["lab_rules"]
    out = []
    for section, is_legacy in (("signals", False), ("legacy", True)):
        for sid, old in (weights.get(section) or {}).items():
            was = Decimal(str(old))
            if sid in not_testable:
                why = f"{NOT_TESTABLE}: no history before 2026 (config/lab.yaml not_testable)"
                out.append(Proposal(str(sid), section, was, was, why, NOT_TESTABLE))
                continue
            oos, ins = by.get((sid, "out_of_sample")), by.get((sid, "in_sample"))
            new, why = rule(oos, ins, rules, is_legacy)
            out.append(Proposal(str(sid), section, was, new, why, verdict(oos, ins, rules)))
    return out


def pr_body(proposals: Sequence[Proposal], rules: Mapping[str, Any], horizon: int) -> str:
    """The weights PR's body (lab.yml): the verdict and the proposal for every weight, what the verdicts mean, and how
    to get the PR's checks to run."""
    untested = [p.signal_id for p in proposals if p.verdict == NOT_TESTABLE]
    lines = [
        f"Signal Lab weight proposals (BRIEF §4.10.5, {horizon}-month excess returns). The statistics are in the "
        "report PR and in lab_results.",
        "",
        "| Weight | Verdict | Now | Proposed | Why |",
        "|---|---|---|---|---|",
        *(f"| {p.section}.{p.signal_id} | {p.verdict} | {p.old} | {p.new} | {p.reason} |" for p in proposals),
        "",
        f"Verdicts (§4.10.5): **works** = out-of-sample mean excess > 0 with t_nw >= {rules['promote_min_t_nw']} and "
        f"the same sign in-sample; **hurts** = out-of-sample mean excess < 0 with t_nw <= {rules['demote_max_t_nw']}; "
        "**unproven** = anything else, which means not shown, not wrong.",
    ]
    if untested:
        never = "; S9 never earns weight" if "S9" in untested else ""
        lines.append(f"{', '.join(untested)}: **{NOT_TESTABLE}** (the data they read was collected only from 2026 on), "
                     f"so they keep their weights{never}.")  # fmt: skip
    lines += [
        "",
        "config/weights.yaml is protected: this PR needs the human-approved label. If you edit a weight, also change "
        "`version:` (the proposal's version is stored as proposed; weights.yml fails on edited weights under the same "
        "version).",
        "",
        f"Opened with the workflow token, so no check has run yet: {REOPEN}.",
        "",
    ]
    return "\n".join(lines)


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
