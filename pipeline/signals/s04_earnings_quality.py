"""S4 earnings-quality inflection (BRIEF §4.6): NI > 0; CCR = TTM(cfo) / TTM(net_income) >= 1.0 and up >= 0.2 YoY;
Sloan (TTM NI - TTM CFO) / mean(total_assets 4q) < 0.05 and falling YoY. Strength clip((CCR - 1) / 0.5, 0, 1)."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, Series, clip

ID, FAMILY = "S4", "fundamentals"


def sloan(s: Series, lag: int) -> Decimal | None:
    ni, cfo, assets = s.ttm("net_income", lag), s.ttm("cfo", lag), s.mean_point("total_assets", lag)
    if ni is None or cfo is None or assets is None or assets <= 0:
        return None
    return (ni - cfo) / assets


def compute(ctx: Ctx) -> SignalResult:
    c, s = ctx.section("s4_earnings_quality"), ctx.series
    ni, cfo, ni_then, cfo_then = s.ttm("net_income", 0), s.ttm("cfo", 0), s.ttm("net_income", 4), s.ttm("cfo", 4)
    if ni is None or cfo is None:
        return missing("ttm_net_income" if ni is None else "ttm_cfo")
    if ni <= 0:
        return quiet(reason="net income not positive", ttm_net_income=num(ni))
    if not s.year_back_ok(0) or ni_then is None or cfo_then is None or ni_then <= 0:  # a year back (R2-F3)
        return missing("ccr_year_ago", ttm_net_income=num(ni))
    ccr, ccr_then = cfo / ni, cfo_then / ni_then
    sl, sl_then = sloan(s, 0), sloan(s, 4)
    if sl is None or sl_then is None:
        return missing("sloan", ccr=num(ccr))
    inputs = {"ccr": num(ccr), "ccr_year_ago": num(ccr_then), "sloan": num(sl), "sloan_year_ago": num(sl_then)}
    ok = (
        ccr >= cfg_dec(c, "min_ccr")
        and ccr - ccr_then >= cfg_dec(c, "min_ccr_rise_yoy")
        and sl < cfg_dec(c, "max_sloan")
        and sl < sl_then
    )
    if not ok:
        return quiet(**inputs)
    return fired(clip((ccr - 1) / cfg_dec(c, "strength_divisor"), ZERO, Decimal(1)), **inputs)
