"""S3 operating-leverage onset (BRIEF §4.6): quarterly revenue YoY growth rose in each of the last 2 quarters, OPM
up >= 0.01 vs 4 quarters ago, and TTM opex (revenue - op_income) grows slower than TTM revenue.
Strength clip(dOPM / 0.05, 0, 1)."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, clip, growth

ID, FAMILY = "S3", "fundamentals"


def compute(ctx: Ctx) -> SignalResult:
    c, s = ctx.section("s3_operating_leverage"), ctx.series
    n = int(c["growth_rising_quarters"])
    yoy = [s.quarterly_yoy("revenue", k) for k in range(n + 1)]
    back = int(c["opm_lookback_quarters"])
    opm, opm_then = s.opm(0), s.opm(back)
    rev, rev_then = s.ttm("revenue", 0), s.ttm("revenue", back)
    op, op_then = s.ttm("op_income", 0), s.ttm("op_income", back)
    if any(v is None for v in yoy):
        return missing("quarterly_revenue_yoy")
    if opm is None or opm_then is None or rev is None or rev_then is None or op is None or op_then is None:
        return missing("opm")
    g_opex, g_rev = growth(rev - op, rev_then - op_then), growth(rev, rev_then)
    if g_opex is None or g_rev is None:
        return missing("opex_growth")
    known = [v for v in yoy if v is not None]
    d_opm = opm - opm_then
    inputs = {"revenue_yoy": [num(v) for v in known], "opm": num(opm), "opm_year_ago": num(opm_then),
              "g_opex": num(g_opex), "g_revenue": num(g_rev)}  # fmt: skip
    rising = all(known[k] > known[k + 1] for k in range(n))
    if not (rising and d_opm >= cfg_dec(c, "min_opm_rise") and g_opex < g_rev):
        return quiet(**inputs)
    return fired(clip(d_opm / cfg_dec(c, "strength_divisor"), ZERO, Decimal(1)), **inputs)
