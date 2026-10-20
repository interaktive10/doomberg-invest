"""S4 earnings-quality inflection (BRIEF §4.6): NI > 0; CCR = TTM(cfo) / TTM(net_income) >= 1.0 and up >= 0.2 YoY;
Sloan (TTM NI - TTM CFO) / mean(total_assets 4q) < 0.05 and falling YoY; TTM CFO above a year earlier, so a fall in
net income alone doesn't fire it (docs/SPEC_ISSUES.md 41); TTM NI >= 0.9 x a year earlier, so a smaller fall with
CFO up a little doesn't either. Quiet for banks, lenders and insurers (SIC 6000-6411), whose CFO carries loan, deposit
and trading flows; REITs (6798) are scored (SPEC_ISSUES 47). Strength clip((CCR - 1) / 0.5, 0, 1)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, Series, clip

ID, FAMILY = "S4", "fundamentals"


def sloan(s: Series, lag: int) -> Decimal | None:
    ni, cfo, assets = s.ttm("net_income", lag), s.ttm("cfo", lag), s.mean_point("total_assets", lag)
    if ni is None or cfo is None or assets is None or assets <= 0:
        return None
    return (ni - cfo) / assets


def sic_in(sic: str | None, ranges: Sequence[Sequence[int]]) -> bool:
    """`sic` lies in one of the [lo, hi] ranges (inclusive); an unknown or non-numeric SIC lies in none."""
    if not sic or not sic.isdigit():
        return False
    return any(lo <= int(sic) <= hi for lo, hi in ranges)


def compute(ctx: Ctx) -> SignalResult:
    c, s = ctx.section("s4_earnings_quality"), ctx.series
    if sic_in(ctx.sic, c.get("exclude_sic", ())):
        return quiet(reason="financial SIC excluded", sic=ctx.sic)
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
    inputs = {"ccr": num(ccr), "ccr_year_ago": num(ccr_then), "sloan": num(sl), "sloan_year_ago": num(sl_then),
              "ttm_cfo": num(cfo), "ttm_cfo_year_ago": num(cfo_then), "ttm_net_income": num(ni),
              "ttm_net_income_year_ago": num(ni_then)}  # fmt: skip
    ni_floor = c.get("ni_min_ratio_yoy")
    ok = (
        ccr >= cfg_dec(c, "min_ccr")
        and ccr - ccr_then >= cfg_dec(c, "min_ccr_rise_yoy")
        and sl < cfg_dec(c, "max_sloan")
        and sl < sl_then
        and (cfo > cfo_then or not c.get("cfo_must_rise_yoy", False))
        and (ni_floor is None or ni >= Decimal(str(ni_floor)) * ni_then)
    )
    if not ok:
        return quiet(**inputs)
    return fired(clip((ccr - 1) / cfg_dec(c, "strength_divisor"), ZERO, Decimal(1)), **inputs)
