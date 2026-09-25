"""S5 capital discipline (BRIEF §4.6), either path:
(A) diluted shares YoY <= -2%, FCF > 0, and net debt not up > 10% YoY -> strength clip(-dshares / 0.06, 0, 1);
(B) share growth >= +5% in each of the 2 prior years and <= 0% in the latest year -> strength 0.6."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, clip, growth

ID, FAMILY = "S5", "fundamentals"


def compute(ctx: Ctx) -> SignalResult:
    c, s = ctx.section("s5_capital_discipline"), ctx.series
    sh = {k: s.shares(k) for k in (0, 4, 8, 12)}
    source = sh[0][1]
    latest = growth(sh[0][0], sh[4][0]) if s.year_back_ok(0) else None
    if latest is None:
        return missing("share_count_yoy", shares_source=source)
    inputs: dict[str, object] = {"shares_source": source, "share_change_yoy": num(latest)}
    strengths: list[Decimal] = []

    fcf, nd, nd_then = s.fcf(0), s.net_debt(0), s.net_debt(4)
    inputs.update(fcf=num(fcf), net_debt=num(nd), net_debt_year_ago=num(nd_then))
    buyback = latest <= cfg_dec(c, "a_max_share_change") and fcf is not None and fcf > 0
    if buyback and nd is not None and nd_then is not None:
        if nd <= nd_then + cfg_dec(c, "a_max_nd_rise") * abs(nd_then):  # "not up > 10%", for net cash too
            strengths.append(clip(-latest / cfg_dec(c, "a_strength_divisor"), ZERO, Decimal(1)))
            inputs["path_a"] = True

    prior = [growth(sh[4 * (k + 1)][0], sh[4 * (k + 2)][0]) if s.year_back_ok(4 * (k + 1)) else None
             for k in range(int(c["b_prior_years"]))]  # fmt: skip
    inputs["share_change_prior_years"] = [num(g) for g in prior]
    if all(g is not None and g >= cfg_dec(c, "b_min_prior_dilution") for g in prior):
        if latest <= cfg_dec(c, "b_max_latest_change"):
            strengths.append(cfg_dec(c, "b_strength"))
            inputs["path_b"] = True

    return fired(max(strengths), **inputs) if strengths else quiet(**inputs)
