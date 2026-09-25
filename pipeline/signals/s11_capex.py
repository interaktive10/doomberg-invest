"""S11 capex propagation (BRIEF §4.11): the company is a confirmed member of a `rising` demand category, has order
evidence (S1, S9 order/customer/export facts, or rising export exposure), and either its revenue growth lags the
category's input growth by >= 10 pp or it is second-order (graph distance 2 from an anchor).
Strength 0.5, +0.25 for India export exposure with a verified US/data-center quote, +0.25 if S1 also fires; cap 1.
The Capex Desk (M5) supplies memberships and the demand index; without them the signal stays quiet."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, num, quiet
from pipeline.signals.s09_text import recent_facts

ID, FAMILY = "S11", "capex"
ORDER_FACTS = frozenset({"order_win", "customer_win", "export_exposure"})


def compute(ctx: Ctx) -> SignalResult:
    c, cap = ctx.section("s11_capex"), ctx.capex
    if cap is None or not cap.categories:
        return quiet(reason="no confirmed category membership")
    rising = sorted(k for k in cap.categories if cap.direction.get(k) == "rising")
    if not rising:
        return quiet(categories=list(cap.categories), reason="no rising category")
    s1 = bool(ctx.fired.get("S1"))
    order_facts = [f for f in recent_facts(ctx, int(ctx.section("s9_text")["lookback_quarters"]))
                   if f.fact_type in ORDER_FACTS]  # fmt: skip
    evidence = s1 or bool(order_facts) or cap.export_exposure_rising
    growth = ctx.series.ttm_yoy("revenue", 0)
    inputs_growth = [cap.input_growth[k] for k in rising if k in cap.input_growth]
    lag = None if growth is None or not inputs_growth else max(inputs_growth) - growth
    second_order = cap.graph_distance == int(c["second_order_distance"])
    inputs = {"rising": rising, "order_evidence": evidence, "revenue_growth": num(growth), "lag": num(lag),
              "second_order": second_order}  # fmt: skip
    lagging = lag is not None and lag >= cfg_dec(c, "min_lag_pp") / 100
    if not (evidence and (lagging or second_order)):
        return quiet(**inputs)
    strength = cfg_dec(c, "strength_base")
    if ctx.market == "in" and cap.export_quote:
        strength += cfg_dec(c, "strength_india_export_bonus")
    if s1:
        strength += cfg_dec(c, "strength_s1_bonus")
    return fired(min(Decimal(1), strength), **inputs)
