"""S7 insider conviction (BRIEF §4.6).
US: >= 2 distinct insiders with unplanned open-market (code P) buys of >= $25k each within 60 days, >= $250k in all.
India: promoter-group market purchases >= Rs 2 crore within 90 days, or the promoter pledged % down >= 5 pp QoQ.
Strength min(1, 0.5 + 0.1 (n - 2) + 0.1 log2(total / threshold)); the India pledge path is 0.6.
Amended filings count once: the latest filing per insider and trade date (insiders.latest_versions, M2 review F4)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

from pipeline.signals.base import Ctx, Insider, SignalResult, cfg_dec, fired, num, quiet
from pipeline.signals.insiders import latest_versions
from pipeline.signals.series import ZERO

ID, FAMILY = "S7", "behavior"
LN2 = Decimal(2).ln()


def cluster_strength(n: int, total: Decimal, threshold: Decimal, c: Mapping[str, Any]) -> Decimal:
    base, per = cfg_dec(c, "strength_base"), cfg_dec(c, "strength_per_extra_insider")
    return min(Decimal(1), base + per * (n - 2) + cfg_dec(c, "strength_log2_scale") * ((total / threshold).ln() / LN2))


def _window(ctx: Ctx, kind: str, days: int) -> list[Insider]:
    start = ctx.week - timedelta(days=days)
    evs = [e for e in ctx.insiders if e.kind == kind and not e.planned and start < e.event_date <= ctx.week]
    return latest_versions(evs)


def compute(ctx: Ctx) -> SignalResult:
    c = ctx.section("s7_insider")
    return _us(ctx, c) if ctx.market == "us" else _india(ctx, c)


def _us(ctx: Ctx, c: Mapping[str, Any]) -> SignalResult:
    by_person: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for e in _window(ctx, "open_market_buy", int(c["us_window_days"])):
        by_person[e.person] += e.value or ZERO
    each, need = cfg_dec(c, "us_min_buy_usd"), cfg_dec(c, "us_min_total_usd")
    buyers = {p: v for p, v in by_person.items() if v >= each}
    total = sum(buyers.values(), ZERO)
    inputs = {"insiders": len(buyers), "total_usd": num(total), "buyers": sorted(buyers)}
    if len(buyers) < int(c["us_min_insiders"]) or total < need:
        return quiet(**inputs)
    return fired(cluster_strength(len(buyers), total, need, c), **inputs)


def _india(ctx: Ctx, c: Mapping[str, Any]) -> SignalResult:
    buys = _window(ctx, "promoter_buy", int(c["in_window_days"]))
    total = sum((e.value or ZERO for e in buys), ZERO)
    people = {e.person for e in buys}
    need = cfg_dec(c, "in_min_promoter_buy_inr")
    inputs: dict[str, object] = {"promoter_buyers": len(people), "total_inr": num(total)}
    strengths: list[Decimal] = []
    if buys and total >= need:
        strengths.append(max(ZERO, cluster_strength(len(people), total, need, c)))
    pledged = sorted(
        ((h.quarter_end, h.promoter_pledged_pct) for h in ctx.ownership if h.promoter_pledged_pct is not None),
        key=lambda x: x[0],
    )
    if len(pledged) >= 2 and (pledged[-1][0] - pledged[-2][0]).days <= 100:  # consecutive quarters (QoQ)
        drop = pledged[-2][1] - pledged[-1][1]
        inputs["pledge_drop_pp"] = num(drop)
        if drop >= cfg_dec(c, "in_pledge_drop_pp"):
            strengths.append(cfg_dec(c, "in_pledge_strength"))
    return fired(max(strengths), **inputs) if strengths else quiet(**inputs)
