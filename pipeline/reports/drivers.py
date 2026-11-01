"""Themes' demand drivers, read the same way for every series (docs/SPEC_ISSUES.md 68; config/drivers.yaml).

A reading compares months of a monthly series:
- yoy: the latest 3 months against the same 3 months a year before (a ratio - 1);
- level: the latest 3 months against the 120 months before them;
- cohort: the 12 months that ended `lag` months ago against the 120 months before them (a wave bought then is due now).

Its z-score is the reading against the same reading at every month of the 20 years before (at least 60 of them), so a
1.0 means "as unusual as one standard deviation" whatever the series; `inverse` drivers (rates) flip the sign. Pure:
tests/reports/test_drivers.py covers it."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pipeline.settings import REPO_ROOT

TRANSFORMS = ("yoy", "level", "cohort")
HISTORY_MONTHS = 240
MIN_HISTORY = 60
FILINGS = "filings"

Points = Sequence[tuple[date, float]]


@dataclass(frozen=True)
class Driver:
    id: str
    name: str
    unit: str
    inverse: bool = False


def load(root: Path = REPO_ROOT) -> dict[str, Driver]:
    doc = yaml.safe_load((root / "config" / "drivers.yaml").read_text(encoding="utf-8"))
    return {k: Driver(k, str(v["name"]), str(v.get("unit", "")), bool(v.get("inverse", False)))
            for k, v in doc["drivers"].items()}  # fmt: skip


def _mean(vals: Sequence[float]) -> float | None:
    return statistics.fmean(vals) if vals else None


def reading(values: Sequence[float], i: int, transform: str, lag: int = 0) -> float | None:
    """The transform at month index i (values oldest first, one per month); None without enough months."""
    if transform == "yoy":
        if i < 14:
            return None
        now, then = _mean(values[i - 2 : i + 1]), _mean(values[i - 14 : i - 11])
    elif transform == "level":
        if i < 122:
            return None
        now, then = _mean(values[i - 2 : i + 1]), _mean(values[i - 122 : i - 2])
    elif transform == "cohort":
        end = i - lag
        if end < 131:
            return None
        now, then = _mean(values[end - 11 : end + 1]), _mean(values[end - 131 : end - 11])
    else:
        raise ValueError(f"unknown transform {transform!r}")
    if now is None or then is None or then == 0:
        return None
    return now / then - 1


def z_at(values: Sequence[float], i: int, transform: str, lag: int = 0, inverse: bool = False) -> float | None:
    """The reading at month i as a z-score against its own last HISTORY_MONTHS months (MIN_HISTORY at least)."""
    r = reading(values, i, transform, lag)
    if r is None:
        return None
    past = [x for j in range(max(0, i - HISTORY_MONTHS), i) if (x := reading(values, j, transform, lag)) is not None]
    if len(past) < MIN_HISTORY:
        return None
    sd = statistics.pstdev(past)
    if sd == 0:
        return None
    z = (r - statistics.fmean(past)) / sd
    return round(-z if inverse else z, 2)


def latest_z(points: Points, transform: str, lag: int = 0, inverse: bool = False) -> float | None:
    values = [v for _, v in points]
    return z_at(values, len(values) - 1, transform, lag, inverse) if values else None


def index_at(points: Points, day: date) -> int | None:
    """The last month at or before `day` (its index), or None."""
    best = None
    for i, (m, _) in enumerate(points):
        if m > day:
            break
        best = i
    return best


def words(z: float | None) -> str:
    if z is None:
        return "not enough history"
    if z >= 1:
        return "well above normal"
    if z >= 0.5:
        return "above normal"
    if z > -0.5:
        return "about normal"
    if z > -1:
        return "below normal"
    return "well below normal"


def summary(points: Points, d: Driver) -> dict[str, Any]:
    """What P-08 reads about one driver: the latest month and value, and its z for each reading (cohort at 2-7
    years back)."""
    last_m, last_v = points[-1] if points else (None, None)
    out: dict[str, Any] = {"id": d.id, "name": d.name, "unit": d.unit, "inverse": d.inverse,
                           "latest_month": last_m.isoformat() if last_m else None,
                           "latest": round(last_v, 3) if last_v is not None else None,
                           "yoy_z": latest_z(points, "yoy", 0, d.inverse),
                           "level_z": latest_z(points, "level", 0, d.inverse)}  # fmt: skip
    out["cohort_z"] = {str(lag): latest_z(points, "cohort", lag, d.inverse) for lag in (24, 36, 48, 60, 84)}
    return out


def chart(points: Points, months: int = 120) -> list[list[Any]]:
    """The last `months` months as [month, value] pairs (the Themes screen's driver chart)."""
    return [[m.isoformat()[:7], round(v, 3)] for m, v in points[-months:]]


def history_check(points: Points, transform: str, lag: int, inverse: bool,
                  group_excess: Mapping[int, float]) -> dict[str, Any] | None:  # fmt: skip
    """Did these industries beat the market in the years the driver said so? For each year with a group excess return
    (the group's average year return minus the market's), the driver's z at the November before (what was known
    when the year began). A tailwind year is z >= 0.5."""
    values = [v for _, v in points]
    rows = []
    for year, excess in sorted(group_excess.items()):
        i = index_at(points, date(year - 1, 11, 1))
        z = None if i is None else z_at(values, i, transform, lag, inverse)
        if z is not None:
            rows.append((year, z, excess))
    if len(rows) < 5:
        return None
    tail = [e for _, z, e in rows if z >= 0.5]
    other = [e for _, z, e in rows if z < 0.5]
    return {"years": len(rows), "first": rows[0][0], "last": rows[-1][0], "tail_years": len(tail),
            "tail_beat": sum(1 for e in tail if e > 0),
            "tail_excess": round(statistics.fmean(tail), 3) if tail else None,
            "other_excess": round(statistics.fmean(other), 3) if other else None}  # fmt: skip
