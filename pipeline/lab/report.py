"""The Signal Lab report (BRIEF §4.10.6): docs/LAB_REPORT.md, with the first four §7 caveats verbatim at the top
(the M7 Lab screen prints the same CAVEATS)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from pipeline.lab.evaluate import Stat
from pipeline.lab.proposals import Proposal

CAVEATS = (  # BRIEF §7 items 1-4, verbatim (tests/lab/test_report.py compares them with the brief)
    "1. No signal set reliably beats the market. The Lab exists to find out, and most signals will fail out of "
    "sample. That's useful information, not a bug.",
    "2. **Survivorship bias:** the free US price file may miss delisted companies, so Lab results are an optimistic "
    "upper bound.",
    "3. Lab returns exclude dividends (v1), taxes and costs.",
    "4. The reverse DCF is a rough lens (one growth rate, generic discount rates). It ranks expectations; it doesn't "
    "value companies.",
)


@dataclass(frozen=True)
class RunInfo:
    market: str
    first_month: date
    last_month: date
    companies: int
    company_months: int
    events: int
    periods: Mapping[str, tuple[date, date]]
    source: str  # where the prices came from ("Twelve Data month-end closes (...)", "F-LAB synthetic panel", ...)
    population: str = ""  # which companies each month-end's cross-section holds (run.describe)


def _f(x: float | None, pct: bool = True) -> str:
    if x is None:
        return "–"
    return f"{100 * x:+.1f}%" if pct else f"{x:.2f}"


def _table(stats: Sequence[Stat]) -> list[str]:
    out = ["| Signal | Horizon | Period | N | Mean excess | Median | Hit rate | P10 | t (NW) |",
           "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for s in stats:
        hit = "–" if s.hit_rate is None else f"{100 * s.hit_rate:.0f}%"
        out.append(f"| {s.signal_id} | {s.horizon}m | {s.period.replace('_', '-')} | {s.n} | {_f(s.mean)} | "
                   f"{_f(s.median)} | {hit} | {_f(s.p10)} | {_f(s.t_nw, pct=False)} |")  # fmt: skip
    return out


def render(info: RunInfo, events: Sequence[Stat], evidence: Sequence[Stat], gap: Sequence[Stat],
           proposals: Sequence[Proposal], blocked: str | None = None) -> str:  # fmt: skip
    lines = ["# Signal Lab report", "", "**Read this first (BRIEF §7):**", "", *CAVEATS, ""]
    if blocked:
        lines += [f"**No run yet: {blocked}**", ""]
    periods = ", ".join(f"{k.replace('_', '-')} {a:%Y-%m} to {b:%Y-%m}" for k, (a, b) in info.periods.items())
    lines += [
        "## Run",
        f"- Market: {info.market}. Prices: {info.source}.",
        *([f"- Population: {info.population}."] if info.population else []),
        f"- Months: {info.first_month:%Y-%m} to {info.last_month:%Y-%m}; {info.companies} companies, "
        f"{info.company_months} company-months, {info.events} events (first fire per company in 12 months).",
        f"- Periods (by event month): {periods}.",
        "- Excess = forward price return minus the equal-weighted mean of the month's population priced at both "
        "dates. t (NW) is the Newey-West t-stat of the mean excess (lags = horizon months) with its standard error "
        "floored at the plain standard error, so it is never larger than the plain t (docs/SPEC_ISSUES.md 19); "
        "lab_results notes keep the unfloored value.",
        "",
        "## Signals",
        *_table(events),
        "",
        "## Evidence deciles (company-months)",
        *_table(evidence),
        "",
        "## Gap deciles (company-months)",
        *_table(gap),
        "",
        "## Weight proposals (BRIEF §4.10.5)",
        "| Weight | Now | Proposed | Why |",
        "|---|---|---|---|",
        *(f"| {p.section}.{p.signal_id} | {p.old} | {p.new} | {p.reason} |" for p in proposals),
        "",
        "Weights change only through a PR with the `human-approved` label (config/weights.yaml is protected).",
        "",
    ]
    return "\n".join(lines)
