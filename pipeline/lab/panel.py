"""The Signal Lab's monthly panel (BRIEF §4.10.1).

One row per company and month-end (from config/lab.yaml `start`) for every company with a close that month:
- signals S1-S12, the red flags and Evidence from the live code itself (pipeline.signals.weekly.score_company over
  registry.SIGNALS: imported, not copied), fed point in time: fundamentals, ownership, insider trades, events and
  facts filed (published) before the month-end's cutoff, exactly the rows as_of(month-end) returns;
- the legacy rules L1-L6 (legacy_doomberg.py);
- Gap from the live context code (C1 over month-end multiples, C2 the reverse DCF, C3 the 12-month return within the
  month's priced companies; C4 has no history, so it is missing);
- forward price returns at each horizon and the excess over the equal-weighted mean of the companies priced at both
  dates (survivorship: only companies still in the database have prices; §7 caveat 2).

Phase A walks the months once for the cross-sectional inputs (S8 size deciles, S12 sector medians, the legacy
thresholds, C3's population); phase B scores each company month by month (in parallel by company chunks with
`workers` > 1). Market caps use the split-adjusted closes with share counts put on the same basis by the company's
whole share-count history (a split ratio changes no economic value, so this leaks nothing).
"""

from __future__ import annotations

import bisect
import multiprocessing
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import ModuleType
from typing import Any
from uuid import UUID

from pipeline.db.models import Company, CorpEvent, FactRow, FundamentalsRow, InsiderEvent, OwnershipRow
from pipeline.db.pit import cutoff_for, ownership_as_of
from pipeline.lab import legacy_doomberg as legacy
from pipeline.lab.prices import MonthBar, add_months
from pipeline.prices.splits import share_splits
from pipeline.signals import context, registry, reverse_dcf
from pipeline.signals import weekly as live
from pipeline.signals.scores import gap as gap_score
from pipeline.signals.series import Series

HUNDRED = Decimal(100)


@dataclass
class LabData:
    """Everything the panel reads, each row with its filing (publication) time."""

    market: str
    companies: list[Company]
    versions: dict[UUID, list[FundamentalsRow]]  # every version of every quarter
    bars: dict[UUID, list[MonthBar]]
    ownership: dict[UUID, list[OwnershipRow]] = field(default_factory=dict)
    insiders: dict[UUID, list[InsiderEvent]] = field(default_factory=dict)
    events: dict[UUID, list[CorpEvent]] = field(default_factory=dict)
    facts: dict[UUID, list[FactRow]] = field(default_factory=dict)


@dataclass(frozen=True)
class PanelRow:
    company_id: UUID
    month_end: date
    fired: dict[str, bool]
    evidence: float | None
    gap: float | None
    close: float
    fwd: dict[int, float] = field(default_factory=dict)  # horizon (months) -> forward price return
    excess: dict[int, float] = field(default_factory=dict)  # horizon -> fwd minus the month's equal-weighted mean


class _Stream[T]:
    """Rows sorted by filing time; `upto(cutoff)` is every row filed before it."""

    def __init__(self, rows: Sequence[T], filed: Callable[[T], datetime]) -> None:
        self.rows = sorted(rows, key=filed)
        self.times = [filed(r) for r in self.rows]

    def upto(self, cutoff: datetime) -> list[T]:
        return self.rows[: bisect.bisect_left(self.times, cutoff)]


class Feed:
    """One company's point-in-time inputs at successive month-ends (the rows as_of(month-end) would return)."""

    def __init__(self, company: Company, data: LabData) -> None:
        assert company.id is not None
        cid = company.id
        self.company = company
        self.market = company.market
        self._versions = sorted(data.versions.get(cid, []), key=lambda v: v.filed_at)
        self._next = 0
        self._latest: dict[date, FundamentalsRow] = {}
        self.series = Series([], company.market)
        self._own = _Stream(data.ownership.get(cid, []), lambda o: o.filed_at)
        self._ins = _Stream(data.insiders.get(cid, []), lambda i: i.filed_at)
        self._evs = _Stream(data.events.get(cid, []), lambda e: e.filed_at)
        self._facts = _Stream(data.facts.get(cid, []), lambda x: x.published_at)
        self.bars = {b.month_end: b for b in data.bars.get(cid, [])}
        self._closes = sorted(self.bars)
        first: dict[date, FundamentalsRow] = {}  # each quarter as first reported: on the basis of its own time
        for v in self._versions:
            first.setdefault(v.period_end, v)
        as_reported = Series.from_rows(sorted(first.values(), key=lambda r: r.period_end), company.market)
        self._splits = [(s.old_end, s.ratio) for s in share_splits(live.shares_history(as_reported))]

    def advance(self, cutoff: datetime) -> None:
        changed = False
        while self._next < len(self._versions) and self._versions[self._next].filed_at < cutoff:
            v = self._versions[self._next]
            self._latest[v.period_end] = v  # sorted by filing time: a later version replaces an earlier one
            self._next += 1
            changed = True
        if changed:
            self.series = Series.from_rows(sorted(self._latest.values(), key=lambda r: r.period_end), self.market)

    def batch(self, m: date, cutoff: datetime) -> live.Batch:
        cid = self.company.id
        assert cid is not None
        since_ins = m - timedelta(days=live.INSIDER_DAYS)
        since_ev = m - timedelta(days=31 * live.EVENT_MONTHS)
        since_fact = m - timedelta(days=365 * live.FACT_YEARS)
        return live.Batch(
            {cid: list(self._latest.values())},
            {cid: [live.holding(o) for o in ownership_as_of(self._own.upto(cutoff), cutoff)]},
            {cid: [live.insider(i) for i in self._ins.upto(cutoff) if i.event_date >= since_ins]},
            {cid: [live.event(e) for e in self._evs.upto(cutoff) if e.event_date >= since_ev]},
            {cid: [live.fact(x) for x in self._facts.upto(cutoff) if x.as_of >= since_fact]},
        )

    def close(self, m: date) -> Decimal | None:
        b = self.bars.get(m)
        return None if b is None else b.close

    def window(self, m: date, months: int) -> list[MonthBar]:
        """The bars of the `months` month-ends up to and including m."""
        lo = bisect.bisect_left(self._closes, add_months(m, -(months - 1)))
        hi = bisect.bisect_right(self._closes, m)
        return [self.bars[d] for d in self._closes[lo:hi]]

    def shares(self) -> Decimal | None:
        """The latest share count known now, on the closes' (today's) split basis: close x shares is the market
        cap."""
        shares, end = live.point_shares(self.series)
        return None if shares is None or end is None else shares * self._factor(end)

    def _factor(self, period_end: date) -> Decimal:
        f = Decimal(1)
        for old_end, ratio in self._splits:
            if old_end >= period_end:
                f *= ratio
        return f


# ---------------------------------------------------------------- phase A: cross-sections


@dataclass(frozen=True)
class Options:
    modules: tuple[ModuleType, ...] = registry.SIGNALS
    with_legacy: bool = True
    with_gap: bool = True
    c1_min_months: int = 12


@dataclass
class MonthCross:
    cross: live.CrossSection
    legacy: legacy.LegacyCross
    returns: list[Decimal]  # C3's population: 12-month returns of the companies priced this month


def _ret(feed: Feed, m: date, months: int) -> Decimal | None:
    now, then = feed.close(m), feed.close(add_months(m, -months))
    return None if now is None or then is None or then <= 0 else now / then - 1


def _legacy_inputs(feed: Feed, m: date, mcap: Decimal | None) -> legacy.LegacyInputs:
    s, close = feed.series, feed.close(m)
    year = feed.window(m, 12)
    hi = max((b.high for b in year), default=None)
    lo = min((b.low for b in year), default=None)
    ret = _ret(feed, m, 12)
    ni = s.ttm("net_income", 0)
    pe = float(mcap / ni) if mcap is not None and ni is not None and ni > 0 else None
    return legacy.LegacyInputs(
        market=feed.market,
        ret_12m=None if ret is None else float(ret),
        drawdown=float(close / hi - 1) if close is not None and hi and len(year) >= 12 else None,
        above_low=float(close / lo - 1) if close is not None and lo and len(year) >= 12 else None,
        fcf_ttm=s.fcf(0),
        net_debt=s.net_debt(0),
        net_debt_year_ago=s.net_debt(4),
        pe=pe,
        revenue_yoy=s.ttm_yoy("revenue", 0),
        market_cap=None if mcap is None else float(mcap),
    )


def cross_sections(data: LabData, months: Sequence[date], opts: Options | None = None) -> dict[date, MonthCross]:
    opts = opts or Options()
    feeds = [Feed(c, data) for c in data.companies]
    out: dict[date, MonthCross] = {}
    for m in months:
        cutoff = cutoff_for(m)
        cross, inputs, returns = live.CrossSection(), [], []
        for f in feeds:
            if f.close(m) is None:
                continue
            f.advance(cutoff)
            b = f.batch(m, cutoff)
            cid = f.company.id
            assert cid is not None
            cross.add(f.company, f.series, b.ownership[cid], b.facts[cid], m)
            if opts.with_legacy:
                shares, close = f.shares(), f.close(m)
                inputs.append(_legacy_inputs(f, m, None if shares is None or close is None else close * shares))
            r = _ret(f, m, 12) if opts.with_gap else None
            if r is not None:
                returns.append(r)
        cross.finish()
        out[m] = MonthCross(cross, legacy.cross_section(inputs), returns)
    return out


# ---------------------------------------------------------------- phase B: scores per company


Multiples = list[tuple[date, Decimal | None, Decimal | None]]  # (month-end, EV/Sales, EV/EBIT), C1's history


def _gap(
    feed: Feed, sc: live.Scored, m: date, cap: Decimal | None, history: Multiples, mc: MonthCross, cfgs: live.Configs,
    opts: Options,
) -> float | None:  # fmt: skip
    ev, ev_sales, ev_ebit = context.multiples(feed.series, cap)
    if cap is not None:
        history.append((m, ev_sales, ev_ebit))
    c1 = context.c1(history, opts.c1_min_months) if cap is not None else context.Metric(None, None, None, {})
    c2 = reverse_dcf.c2(feed.series, ev, feed.market, cfgs.context["c2_reverse_dcf"], sc.g_ob)
    ran = Decimal(str(cfgs.context["c3_runup"]["already_ran_pct"]))
    c3 = context.c3(_ret(feed, m, 12), mc.returns, ran)
    need = int(cfgs.signals["scores"]["gap_min_metrics"])
    g = gap_score({"C1": c1.score, "C2": c2.score, "C3": c3.score, "C4": None}, cfgs.weights, need)
    return None if g is None else float(g)


def score_feed(
    company: Company, data: LabData, months: Sequence[date], crosses: Mapping[date, MonthCross], cfgs: live.Configs,
    opts: Options,
) -> list[PanelRow]:  # fmt: skip
    feed = Feed(company, data)
    assert company.id is not None
    rows: list[PanelRow] = []
    history: Multiples = []
    for m in months:
        close = feed.close(m)
        if close is None:
            continue
        cutoff = cutoff_for(m)
        feed.advance(cutoff)
        mc = crosses[m]
        results, _, sc = live.score_company(company, feed.series, feed.batch(m, cutoff), cfgs, mc.cross, m,
                                            opts.modules)  # fmt: skip
        fired = {k: bool(v.fired) for k, v in results.items()}
        shares = feed.shares()
        cap = None if shares is None else close * shares
        if opts.with_legacy:
            fired |= legacy.evaluate(_legacy_inputs(feed, m, cap), mc.legacy)
        g = _gap(feed, sc, m, cap, history, mc, cfgs, opts) if opts.with_gap else None
        rows.append(PanelRow(company.id, m, fired, float(sc.evidence.score), g, float(close)))
    return rows


_JOB: dict[str, Any] = {}  # the forked workers' inputs (copy-on-write)


def _work(chunk: list[int]) -> list[PanelRow]:
    data, months, crosses, cfgs, opts = (_JOB[k] for k in ("data", "months", "crosses", "cfgs", "opts"))
    return [r for i in chunk for r in score_feed(data.companies[i], data, months, crosses, cfgs, opts)]


# ---------------------------------------------------------------- the panel


def forward_returns(rows: list[PanelRow], horizons: Sequence[int]) -> list[PanelRow]:
    """fwd = close(m + h) / close(m) - 1 where both exist; excess = fwd minus the mean fwd of that month."""
    close = {(r.company_id, r.month_end): r.close for r in rows}
    for r in rows:
        for h in horizons:
            later = close.get((r.company_id, add_months(r.month_end, h)))
            if later is not None and r.close > 0:
                r.fwd[h] = later / r.close - 1
    sums: dict[tuple[date, int], list[float]] = defaultdict(list)
    for r in rows:
        for h, v in r.fwd.items():
            sums[(r.month_end, h)].append(v)
    means = {k: sum(v) / len(v) for k, v in sums.items()}
    for r in rows:
        for h, v in r.fwd.items():
            r.excess[h] = v - means[(r.month_end, h)]
    return rows


def build(
    data: LabData, months: Sequence[date], cfgs: live.Configs, horizons: Sequence[int], opts: Options | None = None,
    workers: int = 1,
) -> list[PanelRow]:  # fmt: skip
    opts = opts or Options()
    crosses = cross_sections(data, months, opts)
    idx = list(range(len(data.companies)))
    if workers <= 1:
        rows = [r for c in data.companies for r in score_feed(c, data, months, crosses, cfgs, opts)]
    else:
        _JOB.update(data=data, months=list(months), crosses=crosses, cfgs=cfgs, opts=opts)
        chunks = [idx[i::workers] for i in range(workers)]
        with multiprocessing.get_context("fork").Pool(workers) as pool:
            rows = [r for part in pool.map(_work, chunks) for r in part]
        _JOB.clear()
    rows.sort(key=lambda r: (r.month_end, str(r.company_id)))
    return forward_returns(rows, horizons)
