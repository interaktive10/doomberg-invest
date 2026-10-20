"""Signal Lab statistics (BRIEF §4.10.3) per signal x horizon x period, and for Evidence and Gap score deciles.

For the excess forward returns of a signal's events (or of a decile's company-months) whose month falls in the
period: N, mean and median excess, hit rate (excess > 0), 10th percentile, and the Newey-West t-stat with lags =
horizon months.

Newey-West here: the events overlap in time (a 12-month return starts every month) and cluster by month (many
companies fire at once), so the variance of the mean excess uses the monthly sums of residuals S_t with Bartlett
weights on the month distance: Var(mean) = (1/N^2) sum_{t,u: |t-u| <= L} (1 - |t-u| / (L + 1)) S_t S_u, L = horizon.
It is the usual estimator on the calendar-time series (a month without events adds nothing). With lags as long as
a third of the period, that estimate is noisy and can fall far below the plain standard error by chance (F-LAB: a
pure-noise signal at t = -5.2 against -1.4 with the plain error), so t_nw divides by the larger of the two: the
§4.10.5 rule never promotes or demotes on a variance the data can't support (docs/SPEC_ISSUES.md 19; the unfloored
t is kept in lab_results.notes). The prove-first lower bound of the old Doomberg (mean - 1.645 SE;
docs/DOOMBERG_AUDIT.md §4.9) is reported next to it, not used by rules.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from pipeline.lab.events import Event
from pipeline.lab.legacy_doomberg import quantile
from pipeline.lab.panel import PanelRow
from pipeline.lab.prices import month_end

Z_LOWER = 1.6449


@dataclass(frozen=True)
class Stat:
    signal_id: str
    horizon: int
    period: str
    n: int
    mean: float | None
    median: float | None
    hit_rate: float | None
    p10: float | None
    t_nw: float | None  # mean / max(NW SE, plain SE): the floored t the §4.10.5 rule reads (SPEC_ISSUES 19)
    lower_bound: float | None
    t_nw_unfloored: float | None = None  # mean / NW SE alone, kept for the record (M8 review R1-F2)


def period_bounds(cfg: Mapping[str, Sequence[str]]) -> dict[str, tuple[date, date]]:
    """config/lab.yaml periods ("2012-01", "2018-12") -> (first month-end, last month-end)."""
    out = {}
    for name, (a, b) in cfg.items():
        out[name] = (month_end(date.fromisoformat(f"{a}-01")), month_end(date.fromisoformat(f"{b}-01")))
    return out


def _month(d: date) -> int:
    return d.year * 12 + d.month


def newey_west_se(obs: Sequence[tuple[date, float]], lags: int) -> float | None:
    """Standard error of the mean of `obs` (month, value) with Bartlett weights over month distances <= lags."""
    n = len(obs)
    if n < 2:
        return None
    mean = sum(v for _, v in obs) / n
    sums: dict[int, float] = defaultdict(float)
    for d, v in obs:
        sums[_month(d)] += v - mean
    months = sorted(sums)
    var = 0.0
    for i, a in enumerate(months):
        for b in months[i:]:
            gap = b - a
            if gap > lags:
                break
            term = (1 - gap / (lags + 1)) * sums[a] * sums[b]
            var += term if gap == 0 else 2 * term
    var /= n * n
    return math.sqrt(var) if var > 0 else None


def plain_se(vals: Sequence[float]) -> float | None:
    n = len(vals)
    if n < 2:
        return None
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return math.sqrt(var / n) if var > 0 else None


def stat(signal_id: str, horizon: int, period: str, obs: Sequence[tuple[date, float]]) -> Stat:
    vals = [v for _, v in obs]
    n = len(vals)
    if n == 0:
        return Stat(signal_id, horizon, period, 0, None, None, None, None, None, None)
    mean = sum(vals) / n
    nw = newey_west_se(obs, horizon)
    known = [s for s in (nw, plain_se(vals)) if s is not None]
    se = max(known) if known else None
    return Stat(
        signal_id, horizon, period, n, mean, quantile(vals, 0.5), sum(v > 0 for v in vals) / n, quantile(vals, 0.1),
        None if se is None else mean / se, None if se is None else mean - Z_LOWER * se,
        None if nw is None else mean / nw,
    )  # fmt: skip


def _in(d: date, bounds: tuple[date, date]) -> bool:
    return bounds[0] <= d <= bounds[1]


def event_stats(
    evts: Iterable[Event], horizons: Sequence[int], periods: Mapping[str, tuple[date, date]],
    signals: Sequence[str] = (),
) -> list[Stat]:  # fmt: skip
    """Per signal: every one in `signals` (N = 0 when it never fired), then any other that has events."""
    by: dict[str, list[Event]] = defaultdict(list)
    for e in evts:
        by[e.signal_id].append(e)
    out = []
    for sid in [*signals, *sorted(set(by) - set(signals))]:
        for h in horizons:
            for period, bounds in periods.items():
                obs = [(e.month_end, e.excess[h]) for e in by[sid] if h in e.excess and _in(e.month_end, bounds)]
                out.append(stat(sid, h, period, obs))
    return out


def deciles(rows: Sequence[PanelRow], score: str, k: int = 10) -> dict[tuple[object, date], int]:
    """Each company-month's decile (1 = lowest) of `score` ("evidence" or "gap") among that month's companies with a
    score; ties share a rank (percentile rank with ties counted half, like the live context metrics)."""
    by_month: dict[date, list[tuple[object, float]]] = defaultdict(list)
    for r in rows:
        v = getattr(r, score)
        if v is not None:
            by_month[r.month_end].append((r.company_id, v))
    out: dict[tuple[object, date], int] = {}
    for m, pairs in by_month.items():
        vals = sorted(v for _, v in pairs)
        n = len(vals)
        for cid, v in pairs:
            below = _count_below(vals, v)
            ties = _count_below(vals, v, inclusive=True) - below
            pct = (below + ties / 2) / n
            out[(cid, m)] = min(k, int(pct * k) + 1)
    return out


def _count_below(sorted_vals: list[float], v: float, inclusive: bool = False) -> int:
    return bisect.bisect_right(sorted_vals, v) if inclusive else bisect.bisect_left(sorted_vals, v)


def decile_stats(
    rows: Sequence[PanelRow], score: str, horizons: Sequence[int], periods: Mapping[str, tuple[date, date]],
    k: int = 10,
) -> list[Stat]:  # fmt: skip
    """The same statistics for every company-month of each score decile (not events)."""
    dec = deciles(rows, score, k)
    out = []
    for d in range(1, k + 1):
        members = [r for r in rows if dec.get((r.company_id, r.month_end)) == d]
        for h in horizons:
            for period, bounds in periods.items():
                obs = [(r.month_end, r.excess[h]) for r in members if h in r.excess and _in(r.month_end, bounds)]
                out.append(stat(f"{score.upper()}_D{d}", h, period, obs))
    return out
