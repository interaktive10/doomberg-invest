"""The Capex Desk demand index per category (BRIEF §4.11), weekly.

Inputs (config/categories.yaml): hyperscaler capex guidance (the latest fiscal-year guidance per anchor, USD, summed),
the utility large-load pipeline (GW, verified facts), EIA planned generator additions (MW), and stated lead times
(months) for transformers, turbines and switchgear. Each input's level is taken point in time at each week (facts
whose document was published by then), so its history exists from the facts already in the ledger.

- YoY change of an input at week t: level(t) / level(t - 52 weeks) - 1. Summed inputs (guidance, large load) compare
  only the companies present at both dates, so a company entering the ledger isn't growth.
- z: the latest YoY against the input's own weekly YoY values over the last `history_weeks` (at least
  `min_history` of them, spread at least `min_spread`), i.e. how unusual this year's change is for that input.
- category value: the mean z of its inputs that have one; direction `rising` (>= +0.5 sigma), `falling`
  (<= -0.5 sigma), else `flat` (also when no input has a z yet).
- input growth (S11's "category input growth"): the mean latest YoY of its inputs.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

YEAR = timedelta(weeks=52)
Level = Callable[[date], "Panel | Decimal | None"]


@dataclass(frozen=True)
class Panel:
    """A summed input's parts (company -> value), so YoY can compare like with like."""

    parts: Mapping[str, Decimal]

    @property
    def total(self) -> Decimal:
        return sum(self.parts.values(), Decimal(0))


def yoy(now: Panel | Decimal | None, then: Panel | Decimal | None) -> Decimal | None:
    if now is None or then is None:
        return None
    if isinstance(now, Panel) and isinstance(then, Panel):
        common = set(now.parts) & set(then.parts)
        a = sum((now.parts[k] for k in common), Decimal(0))
        b = sum((then.parts[k] for k in common), Decimal(0))
    elif isinstance(now, Decimal) and isinstance(then, Decimal):
        a, b = now, then
    else:
        return None
    return a / b - 1 if b > 0 else None


def weeks_back(week: date, n: int) -> list[date]:
    return [week - timedelta(weeks=k) for k in range(n - 1, -1, -1)]


@dataclass(frozen=True)
class InputStat:
    input_id: str
    level: Decimal | None
    yoy: Decimal | None
    z: Decimal | None
    history: int  # YoY observations behind z


def input_stat(input_id: str, level: Level, week: date, history_weeks: int, min_history: int,
               min_spread: float = 0.005) -> InputStat:  # fmt: skip
    cache: dict[date, Panel | Decimal | None] = {}

    def at(d: date) -> Panel | Decimal | None:
        if d not in cache:
            cache[d] = level(d)
        return cache[d]

    series = [(d, yoy(at(d), at(d - YEAR))) for d in weeks_back(week, history_weeks)]
    values = [float(v) for _, v in series if v is not None]
    now = at(week)
    latest = series[-1][1]
    z = None
    if latest is not None and len(values) >= min_history:
        sd = statistics.pstdev(values)
        if sd >= min_spread:  # a YoY that barely moves (< 0.5 pp spread) has no meaningful z
            z = Decimal(str(round((float(latest) - statistics.fmean(values)) / sd, 6)))
    total = now.total if isinstance(now, Panel) else now
    return InputStat(input_id, total, latest, z, len(values))


@dataclass(frozen=True)
class CategoryIndex:
    category: str
    value: Decimal | None
    direction: str
    input_growth: Decimal | None
    inputs: dict[str, Any] = field(default_factory=dict)


def direction(value: Decimal | None, cfg: Mapping[str, Any]) -> str:
    if value is None:
        return "flat"
    if value >= Decimal(str(cfg["rising_min_sigma"])):
        return "rising"
    if value <= Decimal(str(cfg["falling_max_sigma"])):
        return "falling"
    return "flat"


def _mean(xs: Sequence[Decimal]) -> Decimal | None:
    return sum(xs, Decimal(0)) / len(xs) if xs else None


def categories(stats: Mapping[str, InputStat], cfg: Mapping[str, Any]) -> list[CategoryIndex]:
    out = []
    for name, c in cfg["categories"].items():
        mine = [stats[i] for i in c["inputs"] if i in stats]
        zs = [s.z for s in mine if s.z is not None]
        growths = [s.yoy for s in mine if s.yoy is not None]
        value = _mean(zs)
        value = value.quantize(Decimal("0.0001")) if value is not None else None
        growth = _mean(growths)
        detail = {s.input_id: {"level": None if s.level is None else str(s.level),
                               "yoy": None if s.yoy is None else str(s.yoy), "z": None if s.z is None else str(s.z),
                               "history": s.history} for s in mine}  # fmt: skip
        out.append(CategoryIndex(name, value, direction(value, cfg["direction"]),
                                 None if growth is None else growth.quantize(Decimal("0.0001")), detail))  # fmt: skip
    return out
