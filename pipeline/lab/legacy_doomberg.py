"""The old Doomberg's long-term rules as Lab-only signals L1-L6 (BRIEF §4.10.4, docs/DOOMBERG_AUDIT.md §5).

They use price, so they never feed the Evidence score (§1.2.3). They are evaluated exactly like S1-S12 (events,
statistics, the §4.10.5 rule) and carry weight 0 in config/weights.yaml until that rule promotes them. Point in time
at a month-end: prices up to that month, fundamentals filed by then, and cross-sections over the month's population
(the priced companies in the universe then, panel.Population).

| ID | Rule | Definition |
|---|---|---|
| L1 | not ripped, not broken | 12-month return in (-92%, +80%] |
| L2 | wreckage survivor | drawdown from the 52-week high in [-95%, -70%], TTM FCF > 0, net debt down YoY |
| L3 | cheap and still growing | trailing P/E in the bottom tercile (positive P/Es), revenue YoY > 0 |
| L4 | near the 52-week low with positive FCF | close within 10% of the 52-week low, TTM FCF > 0 |
| L5 | small-cap momentum | market cap < $2B, 12-month return in the top decile |
| L6 | size ceiling | $250M <= market cap <= $35B (US); market cap <= Rs 50,000 crore (India) |
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

L1_BAND = (-0.92, 0.80)  # (exclusive, inclusive]
L2_DRAWDOWN = (-0.95, -0.70)  # inclusive
L4_NEAR_LOW = 0.10
L5_MAX_CAP_USD = 2e9
L5_TOP = 0.90  # the top decile
L6_US = (250e6, 35e9)
L6_IN_MAX_INR = 50_000e7  # Rs 50,000 crore
IDS = ("L1", "L2", "L3", "L4", "L5", "L6")


@dataclass(frozen=True)
class LegacyInputs:
    market: str
    ret_12m: float | None  # close / close 12 months earlier - 1
    drawdown: float | None  # close / highest close of the last 12 months - 1
    above_low: float | None  # close / lowest close of the last 12 months - 1
    fcf_ttm: Decimal | None
    net_debt: Decimal | None
    net_debt_year_ago: Decimal | None
    pe: float | None  # market cap / TTM net income, only for positive earnings
    revenue_yoy: Decimal | None
    market_cap: float | None  # in the market's currency


@dataclass(frozen=True)
class LegacyCross:
    """Thresholds over the month's population."""

    pe_tercile_max: float | None  # the bottom tercile's upper bound among positive P/Es
    ret_top_decile_min: float | None


def quantile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolation quantile (numpy's default)."""
    xs = sorted(values)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def cross_section(inputs: Sequence[LegacyInputs]) -> LegacyCross:
    pes = [x.pe for x in inputs if x.pe is not None and x.pe > 0]
    rets = [x.ret_12m for x in inputs if x.ret_12m is not None]
    return LegacyCross(quantile(pes, 1 / 3), quantile(rets, L5_TOP))


def evaluate(x: LegacyInputs, cross: LegacyCross) -> dict[str, bool]:
    """Fired or not for each rule; a missing input means not fired."""
    fcf_pos = x.fcf_ttm is not None and x.fcf_ttm > 0
    out = {k: False for k in IDS}
    if x.ret_12m is not None:
        out["L1"] = L1_BAND[0] < x.ret_12m <= L1_BAND[1]
    if x.drawdown is not None and x.net_debt is not None and x.net_debt_year_ago is not None:
        out["L2"] = L2_DRAWDOWN[0] <= x.drawdown <= L2_DRAWDOWN[1] and fcf_pos and x.net_debt < x.net_debt_year_ago
    if x.pe is not None and x.pe > 0 and cross.pe_tercile_max is not None and x.revenue_yoy is not None:
        out["L3"] = x.pe <= cross.pe_tercile_max and x.revenue_yoy > 0
    if x.above_low is not None:
        out["L4"] = x.above_low <= L4_NEAR_LOW and fcf_pos
    if x.market_cap is not None and x.ret_12m is not None and cross.ret_top_decile_min is not None:
        out["L5"] = x.market == "us" and x.market_cap < L5_MAX_CAP_USD and x.ret_12m >= cross.ret_top_decile_min
    if x.market_cap is not None:
        out["L6"] = L6_US[0] <= x.market_cap <= L6_US[1] if x.market == "us" else x.market_cap <= L6_IN_MAX_INR
    return out
