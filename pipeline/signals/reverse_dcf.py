"""C2 expectations gap (BRIEF §4.7; config/context.yaml `c2_reverse_dcf`).

A rough lens (§7.4): one constant growth rate over 10 years plus a terminal value, generic discount rates. It ranks
expectations; it doesn't value companies.

- revenue_0 = TTM revenue; margin m = max(OPM_TTM, median OPM over 5 years), floored at 0.02; tax t as in §4.6
- sales-to-capital S2C = median(d revenue / d IC) over 5 years, clipped to [0.5, 4], default 1.5
- FCFF_t = rev_t x m x (1 - t) - d rev_t / S2C, discounted at 9% (US) / 12% (IN); terminal growth 2.5% / 4.5%
- g* solves PV = EV (brentq on [-0.20, 0.60]; no root -> None)
- evidence growth g_e = 0.4 clip(g(ob), -0.2, 0.6) + 0.3 x 3-year revenue CAGR + 0.3 x latest revenue YoY, capped to
  [-0.10, 0.40]; the weights renormalize over the parts that exist
- C2 = g_e - g*; score = clip(50 + 250 x C2, 0, 100)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any

from scipy.optimize import brentq

from pipeline.signals.base import num
from pipeline.signals.series import ZERO, Series, clip, growth


@dataclass(frozen=True)
class DcfInputs:
    ev: float
    revenue: float
    margin: float
    tax: float
    s2c: float
    discount: float
    terminal_growth: float
    years: int = 10


def present_value(g: float, x: DcfInputs) -> float:
    rev, pv = x.revenue, 0.0
    after_tax = x.margin * (1 - x.tax)
    for t in range(1, x.years + 1):
        nxt = rev * (1 + g)
        pv += (nxt * after_tax - (nxt - rev) / x.s2c) / (1 + x.discount) ** t
        rev = nxt
    term = rev * (1 + x.terminal_growth)
    fcff = term * after_tax - (term - rev) / x.s2c
    return pv + fcff / (x.discount - x.terminal_growth) / (1 + x.discount) ** x.years


def implied_growth(x: DcfInputs, lo: float = -0.20, hi: float = 0.60) -> float | None:
    """The constant 10-year growth g* at which PV = EV, or None when no root lies in [lo, hi]."""

    def f(g: float) -> float:
        return present_value(g, x) - x.ev

    f_lo, f_hi = f(lo), f(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        return None
    return float(brentq(f, lo, hi, xtol=1e-10))


def five_year_margin(s: Series, cfg: Mapping[str, Any]) -> Decimal | None:
    opm = s.opm(0)
    if opm is None:
        return None
    history = [v for v in (s.opm(k) for k in range(4 * int(cfg["margin_median_years"]))) if v is not None]
    return max(opm, Decimal(str(median(history))), Decimal(str(cfg["margin_floor"])))


def sales_to_capital(s: Series, cfg: Mapping[str, Any]) -> Decimal:
    ratios: list[Decimal] = []
    for k in range(0, 4 * int(cfg["s2c_median_years"]), 4):
        rev, rev_then = s.ttm("revenue", k), s.ttm("revenue", k + 4)
        ic, ic_then = s.invested_capital(k), s.invested_capital(k + 4)
        if rev is None or rev_then is None or ic is None or ic_then is None or ic - ic_then <= 0:
            continue
        ratios.append((rev - rev_then) / (ic - ic_then))
    if not ratios:
        return Decimal(str(cfg["s2c_default"]))
    lo, hi = (Decimal(str(v)) for v in cfg["s2c_clip"])
    return clip(Decimal(str(median(ratios))), lo, hi)


def evidence_growth(
    g_ob: Decimal | None, cagr3: Decimal | None, latest_yoy: Decimal | None, cfg: Mapping[str, Any]
) -> Decimal | None:
    eg = cfg["evidence_growth"]
    ob_lo, ob_hi = (Decimal(str(v)) for v in eg["orderbook_clip"])
    parts = [
        (Decimal(str(eg["w_orderbook"])), None if g_ob is None else clip(g_ob, ob_lo, ob_hi)),
        (Decimal(str(eg["w_cagr3"])), cagr3),
        (Decimal(str(eg["w_latest_yoy"])), latest_yoy),
    ]
    known = [(w, v) for w, v in parts if v is not None]
    if not any(v is not None for _, v in parts[1:]):
        return None  # revenue history is required; the order book alone isn't evidence of growth
    total = sum((w for w, _ in known), ZERO)
    cap_lo, cap_hi = (Decimal(str(v)) for v in eg["cap"])
    return clip(sum((w * v for w, v in known), ZERO) / total, cap_lo, cap_hi)


def revenue_cagr3(s: Series) -> Decimal | None:
    now, then = s.ttm("revenue", 0), s.ttm("revenue", 12)
    if now is None or then is None or now <= 0 or then <= 0:
        return None
    return Decimal(str(float(now / then) ** (1 / 3) - 1))


@dataclass(frozen=True)
class C2:
    value: Decimal | None  # g_e - g*
    score: Decimal | None
    inputs: dict[str, Any]


def c2(s: Series, ev: Decimal | None, market: str, cfg: Mapping[str, Any], g_ob: Decimal | None = None) -> C2:
    """cfg is config/context.yaml `c2_reverse_dcf`."""
    revenue, margin = s.ttm("revenue", 0), five_year_margin(s, cfg)
    if ev is None or revenue is None or revenue <= 0 or margin is None:
        named = (("ev", ev), ("revenue", revenue), ("margin", margin))
        return C2(None, None, {"missing": [n for n, v in named if v is None or v <= 0]})
    x = DcfInputs(
        ev=float(ev), revenue=float(revenue), margin=float(margin), tax=float(s.tax_rate(0)),
        s2c=float(sales_to_capital(s, cfg)), discount=float(cfg["discount_rate"][market]),
        terminal_growth=float(cfg["terminal_growth"][market]), years=int(cfg["years"]),
    )  # fmt: skip
    lo, hi = (float(v) for v in cfg["brentq_bounds"])
    g_star = implied_growth(x, lo, hi)
    latest = s.quarterly_yoy("revenue", 0)
    if latest is None:
        latest = growth(s.ttm("revenue", 0), s.ttm("revenue", 4))
    g_e = evidence_growth(g_ob, revenue_cagr3(s), latest, cfg)
    inputs = {"g_star": g_star, "g_e": num(g_e), "margin": x.margin, "s2c": x.s2c, "tax": x.tax, "ev": x.ev,
              "revenue": x.revenue, "discount": x.discount, "terminal_growth": x.terminal_growth}  # fmt: skip
    if g_star is None or g_e is None:
        return C2(None, None, inputs)
    value = g_e - Decimal(str(round(g_star, 10)))
    score = clip(Decimal(str(cfg["score_center"])) + Decimal(str(cfg["score_slope"])) * value, ZERO, Decimal(100))
    return C2(value, score, inputs)
