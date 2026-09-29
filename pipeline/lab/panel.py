"""The Signal Lab's monthly panel (BRIEF §4.10.1).

One row per company and month-end (from config/lab.yaml `start`) for every company with a close that month that is
in the month's population (the §1.3 universe as of that month, `Population`; the loader drops the structural
exclusions):
- signals S1-S12, the red flags and Evidence from the live code itself (pipeline.signals.weekly.score_company over
  registry.SIGNALS: imported, not copied), fed point in time: fundamentals, ownership, insider trades, events and
  facts filed (published) before the month-end's cutoff, exactly the rows as_of(month-end) returns;
- the legacy rules L1-L6 (legacy_doomberg.py);
- Gap from the live context code (C1 over the month-end multiples of the last `c1.history_years`, C2 the reverse
  DCF, C3 the `c3_runup.lookback_weeks` return within the month's population; C4 has no history, so it is missing);
- forward price returns at each horizon and the excess over the equal-weighted mean of the month's population priced
  at both dates (survivorship: only companies still in the database have prices; §7 caveat 2).

Phase A walks the months once for the cross-sectional inputs (S8 size deciles, S12 sector medians, the legacy
thresholds, C3's population); phase B scores each company month by month (in parallel by company chunks with
`workers` > 1). Market caps use the split-adjusted closes with share counts put on the same basis by the company's
whole share-count history. A split ratio changes no economic value, so a detected split leaks nothing; a missed one
(a ratio outside splits.RATIOS, or one hidden by issuance) would, which docs/DECISIONS.log records.
"""

from __future__ import annotations

import bisect
import multiprocessing
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
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
from pipeline.us.quarterize import QuarterRow, ttm_revenue

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Population:
    """The §1.3 universe rules that change with time, applied as of each month-end from the point-in-time series,
    never from today's in_universe flag (that would add survivorship bias; M8 review R2-F1): a 10-K/10-Q filed in
    the last `filing_days` days (the latest fundamentals version) and, when set, TTM revenue of at least
    `min_ttm_revenue` (the universe's own TTM, pipeline.us.quarterize.ttm_revenue)."""

    filing_days: int
    min_ttm_revenue: Decimal | None = None


@dataclass(frozen=True)
class Shared:
    """The live run's settings the Lab reads from the same config (M8 review R2-F4): S12's tightness lookback,
    C3's return window (weeks, as months) and C1's history window (years, as months)."""

    tightness_quarters: int = 2
    c3_months: int = 12
    c1_months: int = 120

    @classmethod
    def of(cls, cfgs: live.Configs) -> Shared:
        weeks = int(cfgs.context["c3_runup"]["lookback_weeks"])
        return cls(
            tightness_quarters=int(cfgs.signals["s12_cycle"]["tightness_lookback_quarters"]),
            c3_months=max(1, round(weeks * 12 / 52)),
            c1_months=12 * int(cfgs.context["c1"]["history_years"]),
        )


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
    left_out: int = 0  # companies the loader dropped as structural exclusions (pipeline.us.universe.structural)


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
        self._ttm: Decimal | None = None  # the universe's TTM revenue from the rows known now
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
            known = sorted(self._latest.values(), key=lambda r: r.period_end)
            self.series = Series.from_rows(known, self.market)
            self._ttm = ttm_revenue([QuarterRow(r.period_end, r.fiscal_label, r.filed_at, {"revenue": r.revenue})
                                     for r in known])[0]  # fmt: skip

    def eligible(self, m: date, pop: Population | None) -> bool:
        """In month m's population (after advance(cutoff_for(m))): a 10-K/10-Q within `filing_days` of m and TTM
        revenue at or above the floor, both as known at m. None: every priced company (F-LAB)."""
        if pop is None:
            return True
        if self._next == 0 or (m - self._versions[self._next - 1].filed_at.date()).days > pop.filing_days:
            return False
        return pop.min_ttm_revenue is None or (self._ttm is not None and self._ttm >= pop.min_ttm_revenue)

    def batch(self, m: date, cutoff: datetime) -> live.Batch:
        cid = self.company.id
        assert cid is not None
        filed_since = datetime.combine(m - timedelta(days=live.INSIDER_DAYS), time(0), tzinfo=UTC)  # as the live
        # loader: by filing time, so a Form 4/A filed later still reaches S7 (M4 review R2-F4)
        since_ev = m - timedelta(days=31 * live.EVENT_MONTHS)
        since_fact = m - timedelta(days=365 * live.FACT_YEARS)
        return live.Batch(
            {cid: list(self._latest.values())},
            {cid: [live.holding(o) for o in ownership_as_of(self._own.upto(cutoff), cutoff)]},
            {cid: [live.insider(i) for i in self._ins.upto(cutoff) if i.filed_at >= filed_since]},
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
    population: Population | None = None  # None: every priced company


@dataclass
class MonthCross:
    cross: live.CrossSection
    legacy: legacy.LegacyCross
    returns: list[Decimal]  # C3's population: the month's population's returns over Shared.c3_months


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


def cross_sections(
    data: LabData, months: Sequence[date], opts: Options | None = None, shared: Shared | None = None
) -> dict[date, MonthCross]:
    opts, shared = opts or Options(), shared or Shared()
    feeds = [Feed(c, data) for c in data.companies]
    out: dict[date, MonthCross] = {}
    for m in months:
        cutoff = cutoff_for(m)
        cross, inputs, returns = live.CrossSection(tightness_quarters=shared.tightness_quarters), [], []
        for f in feeds:
            if f.close(m) is None:
                continue
            f.advance(cutoff)
            if not f.eligible(m, opts.population):
                continue
            b = f.batch(m, cutoff)
            cid = f.company.id
            assert cid is not None
            cross.add(f.company, f.series, b.ownership[cid], b.facts[cid], m)
            if opts.with_legacy:
                shares, close = f.shares(), f.close(m)
                inputs.append(_legacy_inputs(f, m, None if shares is None or close is None else close * shares))
            r = _ret(f, m, shared.c3_months) if opts.with_gap else None
            if r is not None:
                returns.append(r)
        cross.finish()
        out[m] = MonthCross(cross, legacy.cross_section(inputs), returns)
    return out


# ---------------------------------------------------------------- phase B: scores per company


Multiples = list[tuple[date, Decimal | None, Decimal | None]]  # (month-end, EV/Sales, EV/EBIT), C1's history


def _gap(
    feed: Feed, sc: live.Scored, m: date, cap: Decimal | None, history: Multiples, mc: MonthCross, cfgs: live.Configs,
    opts: Options, shared: Shared,
) -> float | None:  # fmt: skip
    """history: C1's month-end multiples of the last shared.c1_months months, this month's last when cap is known."""
    ev, _, _ = context.multiples(feed.series, cap)
    c1 = context.c1(history, opts.c1_min_months) if cap is not None else context.Metric(None, None, None, {})
    c2 = reverse_dcf.c2(feed.series, ev, feed.market, cfgs.context["c2_reverse_dcf"], sc.g_ob)
    ran = Decimal(str(cfgs.context["c3_runup"]["already_ran_pct"]))
    c3 = context.c3(_ret(feed, m, shared.c3_months), mc.returns, ran)
    need = int(cfgs.signals["scores"]["gap_min_metrics"])
    g = gap_score({"C1": c1.score, "C2": c2.score, "C3": c3.score, "C4": None}, cfgs.weights, need)
    return None if g is None else float(g)


def score_feed(
    company: Company, data: LabData, months: Sequence[date], crosses: Mapping[date, MonthCross], cfgs: live.Configs,
    opts: Options, shared: Shared | None = None,
) -> list[PanelRow]:  # fmt: skip
    shared = shared or Shared()
    feed = Feed(company, data)
    assert company.id is not None
    rows: list[PanelRow] = []
    history: Multiples = []  # C1: every priced month's multiples (in the population or not, as the live price history)
    for m in months:
        close = feed.close(m)
        if close is None:
            continue
        cutoff = cutoff_for(m)
        feed.advance(cutoff)
        shares = feed.shares()
        cap = None if shares is None else close * shares
        if opts.with_gap:
            start = add_months(m, -shared.c1_months)  # the last c1.history_years (M8 review R2-F2)
            while history and history[0][0] <= start:
                del history[0]
            if cap is not None:
                _, ev_sales, ev_ebit = context.multiples(feed.series, cap)
                history.append((m, ev_sales, ev_ebit))
        if not feed.eligible(m, opts.population):
            continue
        mc = crosses[m]
        results, _, sc = live.score_company(company, feed.series, feed.batch(m, cutoff), cfgs, mc.cross, m,
                                            opts.modules)  # fmt: skip
        fired = {k: bool(v.fired) for k, v in results.items()}
        if opts.with_legacy:
            fired |= legacy.evaluate(_legacy_inputs(feed, m, cap), mc.legacy)
        g = _gap(feed, sc, m, cap, history, mc, cfgs, opts, shared) if opts.with_gap else None
        rows.append(PanelRow(company.id, m, fired, float(sc.evidence.score), g, float(close)))
    return rows


_JOB: dict[str, Any] = {}  # the forked workers' inputs (copy-on-write)


def _work(chunk: list[int]) -> list[PanelRow]:
    data, months, crosses, cfgs, opts, shared = (_JOB[k] for k in ("data", "months", "crosses", "cfgs", "opts",
                                                                    "shared"))  # fmt: skip
    return [r for i in chunk for r in score_feed(data.companies[i], data, months, crosses, cfgs, opts, shared)]


# ---------------------------------------------------------------- the panel


def forward_returns(
    rows: list[PanelRow], horizons: Sequence[int], closes: Mapping[UUID, Mapping[date, float]] | None = None
) -> list[PanelRow]:
    """fwd = close(m + h) / close(m) - 1 where both exist, from every close of the company (`closes`; default: the
    rows'), so a company that leaves the population later keeps its return; excess = fwd minus the mean fwd of that
    month's rows (the month's population priced at both dates)."""
    if closes is None:
        own: dict[UUID, dict[date, float]] = defaultdict(dict)
        for r in rows:
            own[r.company_id][r.month_end] = r.close
        closes = own
    for r in rows:
        mine = closes.get(r.company_id, {})
        for h in horizons:
            later = mine.get(add_months(r.month_end, h))
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
    opts, shared = opts or Options(), Shared.of(cfgs)
    crosses = cross_sections(data, months, opts, shared)
    idx = list(range(len(data.companies)))
    if workers <= 1:
        rows = [r for c in data.companies for r in score_feed(c, data, months, crosses, cfgs, opts, shared)]
    else:
        _JOB.update(data=data, months=list(months), crosses=crosses, cfgs=cfgs, opts=opts, shared=shared)
        chunks = [idx[i::workers] for i in range(workers)]
        with multiprocessing.get_context("fork").Pool(workers) as pool:
            rows = [r for part in pool.map(_work, chunks) for r in part]
        _JOB.clear()
    rows.sort(key=lambda r: (r.month_end, str(r.company_id)))
    closes = {c.id: {b.month_end: float(b.close) for b in data.bars.get(c.id, [])} for c in data.companies if c.id}
    return forward_returns(rows, horizons, closes)
