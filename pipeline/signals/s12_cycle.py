"""S12 cycle position (BRIEF §4.6): the company's sector (config/sectors.yaml) had median capex/da <= 1.0 in each of
the last 3 years, median revenue YoY growth > 0 in the last 2 quarters after <= 0 before, and >= 2 verified
price_increase or longer lead_time facts in 2 quarters; and the company fires S2 or S6. Strength 0.6.
Years are trailing 4-quarter windows at lags 0, 4 and 8, so sectors mixing fiscal year-ends line up."""

from __future__ import annotations

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet

ID, FAMILY = "S12", "cycle"


def compute(ctx: Ctx) -> SignalResult:
    c, sec = ctx.section("s12_cycle"), ctx.sector
    if sec is None or sec.sector is None:
        return missing("sector")
    years, turn = int(c["underinvest_years"]), int(c["demand_turn_quarters"])
    capex = list(sec.capex_da_medians)[:years]
    yoy = list(sec.revenue_yoy_medians)[: turn + 1]
    if len(capex) < years or any(v is None for v in capex):
        return missing("sector_capex_da", sector=sec.sector)
    if len(yoy) < turn + 1 or any(v is None for v in yoy):
        return missing("sector_revenue_yoy", sector=sec.sector)
    inputs = {"sector": sec.sector, "capex_da_medians": [num(v) for v in capex],
              "revenue_yoy_medians": [num(v) for v in yoy], "tightness_facts": sec.tightness_facts,
              "company_fires": [s for s in c["requires_any_of"] if ctx.fired.get(s)]}  # fmt: skip
    underinvested = all(v is not None and v <= cfg_dec(c, "max_capex_to_da") for v in capex)
    turning = all(v is not None and v > 0 for v in yoy[:turn]) and (yoy[turn] or 0) <= 0
    tight = sec.tightness_facts >= int(c["min_tightness_facts"])
    company = any(ctx.fired.get(s) for s in c["requires_any_of"])
    if underinvested and turning and tight and company:
        return fired(cfg_dec(c, "strength"), **inputs)
    return quiet(**inputs)
