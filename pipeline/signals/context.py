"""Context metrics C1, C3, C4 (BRIEF §1.6, §4.7; C2 is reverse_dcf.py). Candidate stage only: they use price, and
they feed the Gap score, never Evidence.

- EV = price x shares_outstanding + total_debt - cash (INR for India, USD for US).
- C1: EV/Sales_TTM and EV/EBIT_TTM (EBIT > 0) percentile vs the company's own weekly history (up to 10 years,
  point-in-time fundamentals). Score = 100 - mean(percentiles).
- C3: 52-week return percentile within the market's candidate set plus a benchmark sample. Score = 100 - pct;
  `already_ran` if pct >= 90.
- C4: GDELT article count over 90 days, percentile within the candidate set. Score = 100 - pct.

Percentile rank: the share of the population below the value, ties counted as half (0-100).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pipeline.signals.series import ZERO, Series

HUNDRED = Decimal(100)
C1_MIN_WEEKS = 52  # a year of weekly history before C1 means anything
RETURN_START_SLACK_DAYS = 14  # C3: the start close may be up to two weeks older than exactly `weeks` back


def percentile_rank(x: Decimal, population: Sequence[Decimal]) -> Decimal:
    if not population:
        raise ValueError("empty population")
    below = sum(1 for v in population if v < x)
    ties = sum(1 for v in population if v == x)
    return HUNDRED * (Decimal(below) + Decimal(ties) / 2) / Decimal(len(population))


def enterprise_value(market_cap: Decimal | None, debt: Decimal | None, cash: Decimal | None) -> Decimal | None:
    """Market cap + debt - cash; unknown debt (Series.debt: not reported within a year though the filer reports
    debt) makes EV unknown, never debt-free (M4 review R1-F1)."""
    if market_cap is None or cash is None or debt is None:
        return None
    return market_cap + debt - cash


def multiples(s: Series, market_cap: Decimal | None) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """(EV, EV/Sales_TTM, EV/EBIT_TTM) at the latest quarter; EV/EBIT only for EBIT > 0."""
    ev = enterprise_value(market_cap, s.debt(0), s.point("cash", 0))
    rev, ebit = s.ttm("revenue", 0), s.ttm("op_income", 0)
    if ev is None:
        return None, None, None
    ev_sales = ev / rev if rev is not None and rev > 0 else None
    ev_ebit = ev / ebit if ebit is not None and ebit > 0 else None
    return ev, ev_sales, ev_ebit


@dataclass(frozen=True)
class Metric:
    value: Decimal | None
    pct: Decimal | None
    score: Decimal | None
    inputs: dict[str, Any]


def c1(history: Sequence[tuple[date, Decimal | None, Decimal | None]], min_weeks: int = C1_MIN_WEEKS) -> Metric:
    """history: (week_end, EV/Sales, EV/EBIT) per week, oldest first, the last row being this week."""
    if len(history) < min_weeks:
        return Metric(None, None, None, {"weeks": len(history), "missing": ["history"]})
    _, sales_now, ebit_now = history[-1]
    pcts: dict[str, Decimal] = {}
    for name, now, col in (("ev_sales", sales_now, 1), ("ev_ebit", ebit_now, 2)):
        pop = [v for v in (row[col] for row in history) if isinstance(v, Decimal)]
        if now is not None and len(pop) >= min_weeks:
            pcts[name] = percentile_rank(now, pop)
    inputs: dict[str, Any] = {"weeks": len(history), "ev_sales": _f(sales_now), "ev_ebit": _f(ebit_now)}
    inputs |= {f"pct_{k}": _f(v) for k, v in pcts.items()}
    if not pcts:
        return Metric(None, None, None, {**inputs, "missing": ["multiples"]})
    mean = sum(pcts.values(), ZERO) / len(pcts)
    return Metric(sales_now if sales_now is not None else ebit_now, mean, HUNDRED - mean, inputs)


def c3(ret: Decimal | None, population: Sequence[Decimal], already_ran_pct: Decimal) -> Metric:
    """population: 52-week returns of the market's candidate set plus the benchmark sample (including ret)."""
    if ret is None or not population:
        return Metric(None, None, None, {"missing": ["return_52w"]})
    pct = percentile_rank(ret, population)
    return Metric(ret, pct, HUNDRED - pct, {"return_52w": _f(ret), "population": len(population),
                                          "already_ran": pct >= already_ran_pct})  # fmt: skip


def c4(count: int | None, population: Sequence[int]) -> Metric:
    if count is None or not population:
        return Metric(None, None, None, {"missing": ["gdelt_count"]})
    pct = percentile_rank(Decimal(count), [Decimal(c) for c in population])
    return Metric(Decimal(count), pct, HUNDRED - pct, {"articles_90d": count, "population": len(population)})


def return_52w(closes: Sequence[tuple[date, Decimal]], week: date, weeks: int = 52) -> Decimal | None:
    """adj_close at `week` over the adj_close `weeks` earlier (config/context.yaml c3_runup.lookback_weeks): the
    latest week <= week - 7 x weeks days, within RETURN_START_SLACK_DAYS."""
    by = sorted(closes)
    back = 7 * weeks
    now = [c for d, c in by if d <= week and (week - d).days <= 7]
    start = [c for d, c in by if d <= week - timedelta(days=back) and (week - d).days <= back + RETURN_START_SLACK_DAYS]
    if not now or not start or start[-1] <= 0:
        return None
    return now[-1] / start[-1] - 1


def _f(x: Decimal | None) -> float | None:
    return None if x is None else float(round(x, 6))
