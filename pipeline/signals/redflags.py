"""Red flags R1-R6 (BRIEF §1.5, §4.6; thresholds in config/redflags.yaml). Hard flags exclude, soft ones subtract.
Missing inputs never fire a flag: the flag is recorded as `unknown` with what was missing.

Conventions shared with the text pipeline (M5): governance_flag facts use subject keys
`governance:<topic>:added|removed` (topics: going_concern, material_weakness, auditor_change, restatement); a
disclosed related-party revenue share is a fact with subject key `related_party:revenue_pct` (unit percent)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pipeline.signals.base import Ctx, Event, Fact, months_before, num
from pipeline.signals.s04_earnings_quality import sloan
from pipeline.signals.series import Series, growth

Status = Literal["fired", "clear", "unknown"]
FLAGS = ("R1", "R2", "R3", "R4", "R5", "R6")


@dataclass(frozen=True)
class FlagResult:
    flag_id: str
    status: Status
    hard: bool
    inputs: dict[str, Any]


def _dec(section: Mapping[str, Any], key: str) -> Decimal:
    return Decimal(str(section[key]))


def r1(ctx: Ctx, c: Mapping[str, Any]) -> FlagResult:
    """Sloan accruals >= 10% of assets, or CFO/NI < 0.5 with positive NI."""
    s = ctx.series
    ni, cfo, sl = s.ttm("net_income"), s.ttm("cfo"), sloan(s, 0)
    if ni is None or cfo is None:
        return FlagResult("R1", "unknown", False, {"missing": ["ttm_net_income" if ni is None else "ttm_cfo"]})
    ratio = cfo / ni if ni > 0 else None
    inputs = {"sloan": num(sl), "cfo_to_ni": num(ratio)}
    hit = (sl is not None and sl >= _dec(c, "sloan_min")) or (ratio is not None and ratio < _dec(c, "cfo_ni_max"))
    if not hit and sl is None and ratio is None:
        return FlagResult("R1", "unknown", False, {"missing": ["sloan"], **inputs})
    return FlagResult("R1", "fired" if hit else "clear", False, inputs)


def r2(ctx: Ctx, c: Mapping[str, Any]) -> FlagResult:
    """Receivables growth - revenue growth >= 20 pp YoY (receivables at the quarter end vs TTM revenue)."""
    s = ctx.series
    g_rec, g_rev = growth(s.point("receivables", 0), s.point("receivables", 4)), s.ttm_yoy("revenue", 0)
    if g_rec is None or g_rev is None:
        return FlagResult(
            "R2", "unknown", False, {"missing": ["receivables_growth" if g_rec is None else "revenue_growth"]}
        )
    gap_pp = (g_rec - g_rev) * 100
    inputs = {"receivables_growth": num(g_rec), "revenue_growth": num(g_rev), "gap_pp": num(gap_pp)}
    return FlagResult(
        "R2", "fired" if gap_pp >= _dec(c, "receivables_minus_revenue_growth_pp") else "clear", False, inputs
    )


def governance(facts: Sequence[Fact], topics: Sequence[str], since: date, until: date) -> list[str]:
    return sorted(
        {f.subject_key for f in facts if f.fact_type == "governance_flag" and since <= f.as_of <= until
         and f.subject_key.endswith(":added") and any(f":{t}:" in f"{f.subject_key}:" for t in topics)}
    )  # fmt: skip


def r3(ctx: Ctx, c: Mapping[str, Any]) -> FlagResult:
    """Auditor change (8-K 4.01) in the last 12 months; NT 10-K/10-Q; going-concern or material-weakness language."""
    since = months_before(ctx.week, int(c["auditor_change_months"]))
    kinds = {"auditor_change"} | ({"late_filing"} if c.get("late_filing", True) else set())
    events = sorted(
        {f"{e.kind}:{e.event_date}" for e in ctx.events if e.kind in kinds and since <= e.event_date <= ctx.week}
    )
    text = governance(ctx.facts, list(c["text_types"]), since, ctx.week)
    inputs = {"events": events, "text": text}
    return FlagResult("R3", "fired" if events or text else "clear", True, inputs)


def acquisition(events: Sequence[Event], since: date, until: date) -> list[str]:
    """US 8-K item 2.01 (completion of an acquisition), or an Indian announcement that mentions one."""
    out = []
    for e in events:
        if not since <= e.event_date <= until:
            continue
        text = f"{e.detail.get('category', '')} {e.detail.get('text', '')}".lower()
        if e.kind == "acquisition" or (e.kind == "announcement" and ("acqui" in text or "amalgamat" in text)):
            out.append(f"{e.kind}:{e.event_date}")
    return sorted(set(out))


def r4(ctx: Ctx, c: Mapping[str, Any]) -> FlagResult:
    """Share count +10% YoY without an acquisition."""
    s = ctx.series
    (now, source), (then, _) = s.shares(0), s.shares(4)
    g = growth(now, then)
    if g is None:
        return FlagResult("R4", "unknown", False, {"missing": ["share_count_yoy"]})
    deals = acquisition(ctx.events, months_before(ctx.week, 12), ctx.week) if c.get("unless_acquisition", True) else []
    inputs = {"share_change_yoy": num(g), "shares_source": source, "acquisitions": deals}
    return FlagResult("R4", "fired" if g >= _dec(c, "share_growth_min") and not deals else "clear", False, inputs)


def r5(ctx: Ctx, c: Mapping[str, Any]) -> FlagResult | None:
    """India only: promoter pledge >= 20% of the promoter holding (hard); on ASM/GSM (hard); related-party revenue
    >= 10% of revenue when disclosed (soft)."""
    if ctx.market != "in":
        return None
    pledged = [h for h in sorted(ctx.ownership, key=lambda h: h.quarter_end) if h.promoter_pledged_pct is not None]
    pct = pledged[-1].promoter_pledged_pct if pledged else None
    rpt_facts = [f for f in ctx.facts if f.subject_key == "related_party:revenue_pct" and f.value_num is not None]
    rpt = max(rpt_facts, key=lambda f: f.as_of).value_num if rpt_facts else None
    hits: list[str] = []
    if pct is not None and pct >= _dec(c["pledge"], "min_pledged_pct_of_promoter"):
        hits.append("pledge")
    if ctx.surveillance:
        hits.append("surveillance")
    hard = bool(hits)
    if rpt is not None and rpt >= _dec(c["related_party"], "min_rpt_revenue_pct"):
        hits.append("related_party")
    inputs = {"pledged_pct_of_promoter": num(pct), "surveillance": ctx.surveillance, "rpt_revenue_pct": num(rpt),
              "hits": hits}  # fmt: skip
    if hits:
        return FlagResult("R5", "fired", hard, inputs)
    return FlagResult("R5", "unknown" if pct is None else "clear", False, inputs)


def r6(ctx: Ctx, c: Mapping[str, Any]) -> FlagResult:
    """FCF < 0 and net debt rising for 4 straight quarters, unless S1 fires. India reports cash flow and debt
    half-yearly, so the same span is 2 straight half-years there."""
    s: Series = ctx.series
    n = int(c["consecutive_quarters"])
    step = 2 if ctx.market == "in" else 1
    lags = list(range(0, n + 1, step))
    nds = [s.net_debt(k) for k in lags]
    fcfs = [s.fcf(k) for k in lags[:-1]]
    if any(v is None for v in nds) or any(v is None for v in fcfs):
        return FlagResult("R6", "unknown", False, {"missing": ["net_debt" if any(v is None for v in nds) else "fcf"]})
    rising = all((a or 0) > (b or 0) for a, b in zip(nds, nds[1:], strict=False))
    burning = all((f or 0) < 0 for f in fcfs)
    s1 = bool(ctx.fired.get(str(c.get("unless_signal", "S1"))))
    inputs = {"net_debt": [num(v) for v in nds], "fcf": [num(v) for v in fcfs], "s1": s1}
    return FlagResult("R6", "fired" if rising and burning and not s1 else "clear", False, inputs)


def compute_all(ctx: Ctx, cfg: Mapping[str, Any]) -> list[FlagResult]:
    """Every applicable flag for one company (R5 applies to India only)."""
    out = [r1(ctx, cfg["R1"]), r2(ctx, cfg["R2"]), r3(ctx, cfg["R3"]), r4(ctx, cfg["R4"])]
    five = r5(ctx, cfg["R5"])
    if five is not None:
        out.append(five)
    out.append(r6(ctx, cfg["R6"]))
    return out
