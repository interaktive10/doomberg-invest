"""S6 de-risking complete (BRIEF §4.6): max ND / TTM(op_income + da) over quarters q-8 ... q-4 >= 3.0, current
<= 1.5, and TTM(op_income) / TTM(interest) >= 5. Strength 0.8. Quarters with EBITDA <= 0 have no leverage ratio."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import Series

ID, FAMILY = "S6", "fundamentals"


def leverage(s: Series, lag: int) -> Decimal | None:
    nd, ebitda = s.net_debt(lag), s.ebitda(lag)
    if nd is None or ebitda is None or ebitda <= 0:
        return None
    return nd / ebitda


def compute(ctx: Ctx) -> SignalResult:
    c, s = ctx.section("s6_derisking"), ctx.series
    far, near = (int(x) for x in c["window_quarters"])
    past = [v for v in (leverage(s, k) for k in range(near, far + 1)) if v is not None]
    now = leverage(s, 0)
    op, interest = s.ttm("op_income", 0), s.ttm("interest_expense", 0)
    if not past:
        return missing("past_leverage")
    if now is None:
        return missing("current_leverage", past_max=num(max(past)))
    if op is None or interest is None:
        return missing("interest_coverage", past_max=num(max(past)), current=num(now))
    coverage = None if interest <= 0 else op / interest
    inputs = {"past_max": num(max(past)), "current": num(now), "interest_coverage": num(coverage)}
    covered = op > 0 if coverage is None else coverage >= cfg_dec(c, "min_interest_coverage")
    ok = max(past) >= cfg_dec(c, "min_past_leverage") and now <= cfg_dec(c, "max_current_leverage") and covered
    return fired(cfg_dec(c, "strength"), **inputs) if ok else quiet(**inputs)
