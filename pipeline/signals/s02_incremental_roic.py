"""S2 incremental-ROIC inflection (BRIEF §4.6): IncROIC = dNOPAT_12q / dIC_12q (only when dIC_12q > 0.05 x IC 12
quarters ago) >= 0.15, while ROIC is still modest (0.03-0.12) and up >= 0.03 vs 8 quarters ago.
Strength 0.5 + 0.5 x clip((IncROIC - 0.15) / 0.25, 0, 1)."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, clip

ID, FAMILY = "S2", "fundamentals"


def compute(ctx: Ctx) -> SignalResult:
    c, s = ctx.section("s2_incremental_roic"), ctx.series
    lb, back = int(c["lookback_quarters"]), int(c["roic_rise_lookback_quarters"])
    nopat, nopat_then = s.nopat(0), s.nopat(lb)
    ic, ic_then = s.invested_capital(0), s.invested_capital(lb)
    roic, roic_then = s.roic(0), s.roic(back)
    named = {"nopat": nopat, f"nopat_{lb}q": nopat_then, "ic": ic, f"ic_{lb}q": ic_then, "roic": roic,
             f"roic_{back}q": roic_then}  # fmt: skip
    if nopat is None or nopat_then is None or ic is None or ic_then is None or roic is None or roic_then is None:
        return missing(*[k for k, v in named.items() if v is None])
    d_ic = ic - ic_then
    inputs = {k: num(v) for k, v in named.items()} | {"d_ic": num(d_ic)}
    if d_ic <= cfg_dec(c, "min_delta_ic_pct") * ic_then:
        return quiet(reason="invested capital grew too little for an incremental return", **inputs)
    inc = (nopat - nopat_then) / d_ic
    lo, hi = (Decimal(str(x)) for x in c["roic_band"])
    inputs["inc_roic"] = num(inc)
    ok = inc >= cfg_dec(c, "min_inc_roic") and lo <= roic <= hi and roic - roic_then >= cfg_dec(c, "roic_rise_min")
    if not ok:
        return quiet(**inputs)
    scaled = clip((inc - cfg_dec(c, "min_inc_roic")) / cfg_dec(c, "strength_divisor"), ZERO, Decimal(1))
    return fired(cfg_dec(c, "strength_base") + cfg_dec(c, "strength_scale") * scaled, **inputs)
