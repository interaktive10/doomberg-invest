"""Weekly scoring run (BRIEF §2.1 "weekly", §4.4-§4.8): signals -> red flags -> Evidence -> candidate prices (Stooq)
-> context C1-C4 -> Gap -> buckets -> shortlist. `python -m pipeline.signals.weekly [--week YYYY-MM-DD]`.

Everything as of week W reads through pipeline.db.pit.as_of(W), so a re-run over the same data gives the same rows
whether or not later filings exist (M4-02). Evidence never uses price; prices enter only at the candidate stage
(Evidence >= 40 this week or last): US closes come from Stooq for that set only, India from the bhavcopy (M3).

Two passes over the universe in batches keep memory flat: the first collects the cross-sectional inputs (S8's
revenue-size deciles, S12's sector medians), the second computes signals, flags and Evidence.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any
from uuid import UUID

import httpx
import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import Company, ContextValue, FundamentalsRow, PriceW, RedflagValue, Score, SignalValue
from pipeline.db.pit import as_of, cutoff_for, select_as_of
from pipeline.net.gdelt import GdeltClient, GdeltError
from pipeline.net.http import HttpClient
from pipeline.net.stooq import StooqClient, StooqUnavailable
from pipeline.prices import benchmarks as bench
from pipeline.prices.splits import Adjusted, adjust
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals import context, redflags, registry, reverse_dcf, s01_orderbook
from pipeline.signals.base import CapexView, Ctx, Event, Fact, Holding, Insider, SectorView, num
from pipeline.signals.buckets import Ranked, bucket, market_cap_ok, shortlist
from pipeline.signals.context import percentile_rank
from pipeline.signals.scores import Evidence, Weights, evidence, gap
from pipeline.signals.series import Series, growth

BATCH = 300
STOOQ_MAX_SYMBOLS = 400  # §4.4, benchmarks included
GDELT_MAX_QUERIES = 100  # ~8 minutes at GDELT's 1 request / 5 s; the rest reuse a count under 28 days old
GDELT_REUSE_DAYS = 28
PRICE_YEARS = 10  # C1 looks back up to 10 years
EVENT_MONTHS = 25  # S10 reorganizations (24 months) and R3/R4 (12 months)
FACT_YEARS = 3  # S9 "longer lead time" compares with the previous statement
NONE_SCORE_WEEKS = 13  # 'none' rows are kept for a quarter (the novelty window is 12 weeks)
KEEP_YEARS = 3  # §2.8


def last_friday(today: date) -> date:
    return today - timedelta(days=(today.weekday() - 4) % 7)


def chunks[T](items: Sequence[T], n: int) -> Iterator[Sequence[T]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


@dataclass
class ScoresStats:
    week: str
    companies: int = 0
    signals_fired: dict[str, int] = field(default_factory=dict)
    flags_fired: dict[str, int] = field(default_factory=dict)
    stage: int = 0  # companies at the candidate stage (Evidence >= 40)
    stooq_ok: int = 0
    stooq_failed: int = 0
    stooq_imported: int = 0
    gdelt_queried: int = 0
    gdelt_reused: int = 0
    gdelt_failed: int = 0
    unconfirmed_jumps: list[str] = field(default_factory=list)
    buckets: dict[str, int] = field(default_factory=dict)
    shortlist: list[str] = field(default_factory=list)
    pruned: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0


@dataclass
class Configs:
    signals: dict[str, Any]
    flags: dict[str, Any]
    context: dict[str, Any]
    universe: dict[str, dict[str, Any]]
    sectors: dict[str, Any]
    holdcos: set[tuple[str, str]]
    weights: Weights

    @classmethod
    def load(cls, root: Path = REPO_ROOT) -> Configs:
        def y(name: str) -> Any:
            return yaml.safe_load((root / "config" / name).read_text(encoding="utf-8"))

        holdcos = {(str(h["market"]), str(h["symbol"]).upper()) for h in (y("holdcos.yaml").get("holdcos") or [])}
        return cls(
            y("signals.yaml"),
            y("redflags.yaml"),
            y("context.yaml"),
            {m: y(f"universe_{m}.yaml") for m in ("us", "in")},
            y("sectors.yaml"),
            holdcos,
            Weights.load(root),
        )


# ---------------------------------------------------------------- loading one batch as of W


@dataclass
class Batch:
    rows: dict[UUID, list[FundamentalsRow]]
    ownership: dict[UUID, list[Holding]]
    insiders: dict[UUID, list[Insider]]
    events: dict[UUID, list[Event]]
    facts: dict[UUID, list[Fact]]


def load_batch(conn: psycopg.Connection[Any], week: date, ids: Sequence[UUID], full: bool) -> Batch:
    snap = as_of(week)
    b = Batch(defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list))
    for f in snap.fundamentals(conn, ids):
        b.rows[f.company_id].append(f)
    for o in snap.ownership(conn, ids):
        b.ownership[o.company_id].append(
            Holding(o.quarter_end, o.inst_holders, o.fii_pct, o.dii_pct, o.promoter_pct, o.promoter_pledged_pct)
        )
    for x in snap.facts(conn, ids, since=week - timedelta(days=365 * FACT_YEARS)):
        b.facts[x.company_id].append(
            Fact(x.fact_type, x.subject_key, x.as_of, x.value_num, x.unit, x.subject, x.period_end, x.counterparty)
        )
    if full:
        for i in snap.insider_events(conn, ids, since=week - timedelta(days=100)):
            b.insiders[i.company_id].append(
                Insider(
                    str(i.company_id),
                    i.person,
                    i.event_date,
                    i.filed_at,
                    i.kind,
                    i.value,
                    i.planned,
                    i.source_url,
                    i.currency,
                    i.amends,
                )
            )
        for e in snap.corp_events(conn, ids, since=week - timedelta(days=31 * EVENT_MONTHS)):
            b.events[e.company_id].append(Event(e.kind, e.event_date, e.detail))
    return b


# ---------------------------------------------------------------- cross-sectional inputs (pass 1)


@dataclass
class CrossSection:
    size: list[tuple[UUID, Decimal, int]] = field(default_factory=list)  # US: (id, TTM revenue, 13F holders)
    sector_rows: dict[tuple[str, str], list[tuple[list[Decimal | None], list[Decimal | None]]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    tightness: Counter[tuple[str, str]] = field(default_factory=Counter)
    holder_pct: dict[UUID, Decimal] = field(default_factory=dict)
    sectors: dict[tuple[str, str], SectorView] = field(default_factory=dict)

    def add(self, c: Company, s: Series, holdings: list[Holding], facts: list[Fact], week: date) -> None:
        assert c.id is not None
        if c.market == "us":
            rev = s.ttm("revenue", 0)
            holders = [h for h in sorted(holdings, key=lambda h: h.quarter_end) if h.inst_holders is not None]
            if rev is not None and holders:
                self.size.append((c.id, rev, holders[-1].inst_holders or 0))
        if c.sector:
            key = (c.market, c.sector)
            capex_da = []
            for k in (0, 4, 8):
                capex, da = s.ttm("capex", k), s.ttm("da", k)
                capex_da.append(capex / da if capex is not None and da is not None and da > 0 else None)
            self.sector_rows[key].append((capex_da, [s.quarterly_yoy("revenue", k) for k in range(3)]))
            start = week - timedelta(days=183)
            self.tightness[key] += sum(1 for f in facts if start <= f.as_of <= week and _tight(f, facts))

    def finish(self) -> None:
        ranked = sorted(self.size, key=lambda x: x[1])
        n = len(ranked)
        deciles: dict[int, list[tuple[UUID, int]]] = defaultdict(list)
        for i, (cid, _, holders) in enumerate(ranked):
            deciles[min(9, 10 * i // max(n, 1))].append((cid, holders))
        for members in deciles.values():
            pop = [Decimal(h) for _, h in members]
            for cid, h in members:
                self.holder_pct[cid] = percentile_rank(Decimal(h), pop)
        for key, rows in self.sector_rows.items():
            capex_meds = [_median([r[0][i] for r in rows]) for i in range(3)]
            yoy_meds = [_median([r[1][i] for r in rows]) for i in range(3)]
            self.sectors[key] = SectorView(key[1], capex_meds, yoy_meds, self.tightness[key])


def _median(vals: Sequence[Decimal | None]) -> Decimal | None:
    known = [v for v in vals if v is not None]
    return Decimal(str(median(known))) if known else None


def _tight(f: Fact, facts: list[Fact]) -> bool:
    from pipeline.signals.s09_text import longer_lead_time

    return f.fact_type == "price_increase" or (f.fact_type == "lead_time" and longer_lead_time(f, facts))


# ---------------------------------------------------------------- signals, flags, evidence (pass 2)


@dataclass
class Scored:
    company: Company
    series: Series
    evidence: Evidence
    hard: bool
    fired: dict[str, bool]
    g_ob: Decimal | None
    metrics: dict[str, Any]


def company_metrics(s: Series) -> dict[str, Any]:
    """The screener's per-company numbers (company_metrics; price-based ones are added at the candidate stage)."""
    nd, ebitda = s.net_debt(0), s.ebitda(0)
    shares, then = s.shares(0)[0], s.shares(4)[0]
    ni, cfo = s.ttm("net_income", 0), s.ttm("cfo", 0)
    rows = {
        "revenue_ttm": s.ttm("revenue", 0),
        "revenue_yoy": s.ttm_yoy("revenue", 0),
        "opm": s.opm(0),
        "roic": s.roic(0),
        "fcf_ttm": s.fcf(0),
        "ccr": cfo / ni if cfo is not None and ni is not None and ni > 0 else None,
        "nd_to_ebitda": nd / ebitda if nd is not None and ebitda is not None and ebitda > 0 else None,
        "share_change_yoy": growth(shares, then),
    }
    return {k: num(v) for k, v in rows.items() if v is not None}


def score_company(
    c: Company, s: Series, b: Batch, cfgs: Configs, cross: CrossSection, week: date
) -> tuple[dict[str, Any], list[redflags.FlagResult], Scored]:
    assert c.id is not None
    symbol = (c.ticker if c.market == "us" else c.nse_symbol) or ""
    surveillance = c.excluded_reason if (c.excluded_reason or "").startswith("surveillance") else None
    ctx = Ctx(
        company_id=str(c.id),
        market=c.market,
        week=week,
        series=s,
        cfg=cfgs.signals,
        ownership=b.ownership.get(c.id, []),
        insiders=b.insiders.get(c.id, []),
        events=b.events.get(c.id, []),
        facts=b.facts.get(c.id, []),
        holdco=(c.market, symbol.upper()) in cfgs.holdcos,
        holder_pct_in_size_decile=cross.holder_pct.get(c.id),
        sector=cross.sectors.get((c.market, c.sector)) if c.sector else SectorView(None),
        capex=CapexView(),
        surveillance=surveillance,
    )
    results = registry.evaluate(ctx)
    fired = {k: v.fired for k, v in results.items()}
    flags = redflags.compute_all(replace(ctx, fired=fired), cfgs.flags)
    soft = sum(1 for f in flags if f.status == "fired" and not f.hard)
    hard = any(f.status == "fired" and f.hard for f in flags)
    ev = evidence(results, soft, cfgs.weights, cfgs.signals["scores"])
    ob, _ = s01_orderbook.order_book(ctx)
    return results, flags, Scored(c, s, ev, hard, fired, growth(ob(0), ob(4)), company_metrics(s))


# ---------------------------------------------------------------- prices and context (candidate stage)


def ingest_us_prices(
    conn: psycopg.Connection[Any],
    stooq: StooqClient,
    targets: Sequence[Company],
    week: date,
    imports: Path,
    stats: ScoresStats,
) -> None:
    start = week - timedelta(days=365 * PRICE_YEARS)
    for c in targets:
        assert c.id is not None and c.ticker
        try:
            bars = stooq.weekly(c.ticker)
            stats.stooq_ok += 1
        except (StooqUnavailable, httpx.HTTPError) as e:
            manual = imports / f"{c.ticker.upper()}.csv"
            if not manual.exists():
                stats.stooq_failed += 1
                stats.errors.append(f"stooq {c.ticker}: {type(e).__name__}: {e}"[:200])
                continue
            from pipeline.net.stooq import parse_csv

            bars = parse_csv(manual.read_bytes())
            stats.stooq_imported += 1
        rows = [
            PriceW(
                company_id=c.id, week_end=b.week_end, close=b.close, adj_close=b.close, volume=b.volume, source="stooq"
            )
            for b in bars
            if start < b.week_end <= week
        ]
        repo.upsert_prices(conn, rows)


def shares_history(s: Series) -> list[tuple[date, Decimal]]:
    out = []
    for q in s.quarters:
        v = q.get("shares_outstanding") or q.get("diluted_shares")
        if v is not None:
            out.append((q.end, v))
    return out


def point_shares(s: Series) -> tuple[Decimal | None, date | None]:
    for k in range(3):
        q = s.at(k)
        if q is None:
            break
        v = q.get("shares_outstanding") or q.get("diluted_shares")
        if v is not None:
            return v, q.end
    return None, None


def c1_history(
    versions: Sequence[FundamentalsRow], closes: Sequence[tuple[date, Decimal]], adj: Adjusted, market: str
) -> list[tuple[date, Decimal | None, Decimal | None]]:
    """(week, EV/Sales, EV/EBIT) for every priced week, each from the fundamentals known that week."""
    out: list[tuple[date, Decimal | None, Decimal | None]] = []
    seen, s = -1, Series([], market)
    for d, _ in sorted(closes):
        cutoff = cutoff_for(d)
        visible = sum(1 for v in versions if v.filed_at < cutoff)
        if visible != seen:
            rows = select_as_of(versions, cutoff, lambda v: v.period_end, lambda v: v.filed_at)
            s, seen = Series.from_rows(rows, market), visible
        shares, end = point_shares(s)
        price = adj.adj_close.get(d)
        if shares is None or end is None or price is None:
            continue
        _, ev_sales, ev_ebit = context.multiples(s, price * shares * adj.share_factor(end))
        out.append((d, ev_sales, ev_ebit))
    return out


@dataclass
class Priced:
    market_cap: Decimal | None
    ev: Decimal | None
    ret_52w: Decimal | None
    c1: context.Metric
    c2: reverse_dcf.C2


def price_company(
    conn: psycopg.Connection[Any], sc: Scored, week: date, cfgs: Configs, stats: ScoresStats
) -> Priced | None:
    c = sc.company
    assert c.id is not None
    rows = repo.prices(conn, [c.id], week - timedelta(days=365 * PRICE_YEARS), week)
    closes = [(p.week_end, p.close) for p in rows]
    if not closes or (week - closes[-1][0]).days > 7:
        return None  # no price this week
    adj = adjust(closes, shares_history(sc.series))
    stats.unconfirmed_jumps += [f"{c.ticker or c.nse_symbol} {j.week_end}" for j in adj.unconfirmed]
    changed = [
        PriceW(**{**p.model_dump(), "adj_close": adj.adj_close[p.week_end]})
        for p in rows
        if p.adj_close != adj.adj_close[p.week_end]
    ]
    if changed:
        repo.upsert_prices(conn, changed)
    shares, end = point_shares(sc.series)
    mcap = None if shares is None or end is None else adj.adj_close[closes[-1][0]] * shares * adj.share_factor(end)
    ev, _, _ = context.multiples(sc.series, mcap)
    versions = as_of(week).fundamental_versions(conn, [c.id])
    history = c1_history(versions, closes, adj, c.market)
    c2 = reverse_dcf.c2(sc.series, ev, c.market, cfgs.context["c2_reverse_dcf"], sc.g_ob)
    ret = context.return_52w([(d, adj.adj_close[d]) for d, _ in closes], week)
    return Priced(mcap, ev, ret, context.c1(history), c2)


def benchmark_returns(conn: psycopg.Connection[Any], symbols: Sequence[str], week: date) -> list[Decimal]:
    rows = repo.benchmark_closes(conn, symbols, week - timedelta(days=400), week)
    by: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for r in rows:
        by[r.symbol].append((r.week_end, r.close))
    return [x for x in (context.return_52w(v, week) for v in by.values()) if x is not None]


# ---------------------------------------------------------------- the run


def run(
    conn: psycopg.Connection[Any],
    week: date,
    http: HttpClient | None = None,
    root: Path = REPO_ROOT,
    imports: Path | None = None,
    stooq_limit: int = STOOQ_MAX_SYMBOLS,
    gdelt_limit: int = GDELT_MAX_QUERIES,
) -> ScoresStats:
    t0 = time.monotonic()
    stats = ScoresStats(week.isoformat())
    cfgs = Configs.load(root)
    research = repo.research_company_ids(conn)
    companies = [c for c in repo.companies(conn) if c.id is not None and (c.in_universe or c.id in research)]
    stats.companies = len(companies)
    repo.clear_week(conn, week)

    cross = CrossSection()
    for part in chunks(companies, BATCH):
        b = load_batch(conn, week, [c.id for c in part if c.id], full=False)
        for c in part:
            assert c.id is not None
            cross.add(
                c,
                Series.from_rows(b.rows.get(c.id, []), c.market),
                b.ownership.get(c.id, []),
                b.facts.get(c.id, []),
                week,
            )
    cross.finish()

    scored: dict[UUID, Scored] = {}
    for part in chunks(companies, BATCH):
        b = load_batch(conn, week, [c.id for c in part if c.id], full=True)
        sig_rows: list[SignalValue] = []
        flag_rows: list[RedflagValue] = []
        for c in part:
            assert c.id is not None
            s = Series.from_rows(b.rows.get(c.id, []), c.market)
            results, flags, sc = score_company(c, s, b, cfgs, cross, week)
            scored[c.id] = sc
            for sid, r in results.items():
                sig_rows.append(
                    SignalValue(
                        company_id=c.id,
                        week_end=week,
                        signal_id=sid,
                        fired=r.fired,
                        strength=r.strength.quantize(Decimal("0.000001")),
                        inputs=r.inputs,
                    )
                )
                if r.fired:
                    stats.signals_fired[sid] = stats.signals_fired.get(sid, 0) + 1
            for f in flags:
                if f.status == "clear":
                    continue
                flag_rows.append(
                    RedflagValue(
                        company_id=c.id,
                        week_end=week,
                        flag_id=f.flag_id,
                        hard=f.hard,
                        inputs={"status": f.status, **f.inputs},
                    )
                )
                if f.status == "fired":
                    stats.flags_fired[f.flag_id] = stats.flags_fired.get(f.flag_id, 0) + 1
        repo.upsert_signal_values(conn, sig_rows)
        repo.upsert_redflag_values(conn, flag_rows)

    min_ev = Decimal(str(cfgs.signals["scores"]["us_price_candidate_min_evidence"]))
    last = repo.scores_for_week(conn, week - timedelta(days=7))
    stage = [sc for cid, sc in scored.items() if sc.evidence.score >= min_ev or cid in research]
    stats.stage = len(stage)

    if http is not None:
        stooq = StooqClient(http)
        us_bench = list(cfgs.context["benchmarks"]["us"])
        rows, errs = bench.fetch_us(stooq, us_bench, week)
        repo.upsert_benchmarks(conn, rows)
        stats.errors += errs
        prev = {cid for cid, s in last.items() if s.evidence >= min_ev}
        us = sorted(
            (
                sc
                for cid, sc in scored.items()
                if sc.company.market == "us"
                and sc.company.ticker
                and (sc.evidence.score >= min_ev or cid in prev or cid in research)
            ),
            key=lambda sc: -sc.evidence.score,
        )
        ingest_us_prices(
            conn,
            stooq,
            [sc.company for sc in us[: max(0, stooq_limit - len(us_bench))]],
            week,
            imports or root / "imports" / "us_prices",
            stats,
        )

    priced: dict[UUID, Priced] = {}
    for sc in stage:
        assert sc.company.id is not None
        p = price_company(conn, sc, week, cfgs, stats)
        if p is not None:
            priced[sc.company.id] = p

    ctx_rows = context_rows(conn, week, cfgs, scored, priced, http, gdelt_limit, stats)
    repo.upsert_context_values(conn, ctx_rows)
    gaps = gap_scores(ctx_rows, cfgs)

    score_rows, ranked = [], []
    metrics: dict[UUID, dict[str, Any]] = {}
    for cid, sc in scored.items():
        p = priced.get(cid)
        g = gaps.get(cid)
        b_ = bucket(
            sc.evidence.score,
            g,
            len(sc.evidence.families),
            sc.hard,
            cfgs.signals["scores"]["buckets"],
            market_cap_ok(sc.company.market, p.market_cap if p else None, cfgs.universe),
        )
        score_rows.append(
            Score(
                company_id=cid,
                week_end=week,
                evidence=sc.evidence.score.quantize(Decimal("0.01")),
                gap=None if g is None else g.quantize(Decimal("0.01")),
                families=sorted(sc.evidence.families),
                bucket=b_,
                weights_version=cfgs.weights.version,
            )
        )
        stats.buckets[b_] = stats.buckets.get(b_, 0) + 1
        ranked.append(Ranked(cid, sc.evidence.score, g, b_))
        m = dict(sc.metrics)
        if p is not None:
            m |= {
                k: num(v)
                for k, v in (("market_cap", p.market_cap), ("ev", p.ev), ("return_52w", p.ret_52w))
                if v is not None
            }
        metrics[cid] = m
    repo.upsert_scores(conn, score_rows)

    cfg_scores = cfgs.signals["scores"]
    seen = repo.recently_shortlisted(conn, week, week - timedelta(weeks=int(cfg_scores["novelty_weeks"])))
    top = shortlist(ranked, seen, int(cfg_scores["weekly_new_candidates"]))
    repo.insert_shortlist(
        conn,
        week,
        [
            (
                r.company_id,
                r.evidence.quantize(Decimal("0.01")),
                None if r.gap is None else r.gap.quantize(Decimal("0.01")),
            )
            for r in top
        ],
    )
    stats.shortlist = [scored[r.company_id].company.name for r in top]
    repo.upsert_company_metrics(conn, week, metrics)
    stats.pruned = repo.prune_scoring_history(
        conn,
        week,
        keep_from=week - timedelta(days=365 * KEEP_YEARS),
        none_from=week - timedelta(weeks=NONE_SCORE_WEEKS),
    )
    stats.unconfirmed_jumps = stats.unconfirmed_jumps[:50]
    stats.errors = stats.errors[:50]
    stats.seconds = round(time.monotonic() - t0, 2)
    return stats


def context_rows(
    conn: psycopg.Connection[Any],
    week: date,
    cfgs: Configs,
    scored: Mapping[UUID, Scored],
    priced: Mapping[UUID, Priced],
    http: HttpClient | None,
    gdelt_limit: int,
    stats: ScoresStats,
) -> list[ContextValue]:
    rows: list[ContextValue] = []
    c3_cfg = cfgs.context["c3_runup"]
    for market in ("us", "in"):
        ids = [cid for cid in priced if scored[cid].company.market == market]
        if not ids:
            continue
        pop = [r for r in (priced[cid].ret_52w for cid in ids) if r is not None]
        pop += benchmark_returns(conn, cfgs.context["benchmarks"][market], week)
        counts = attention(conn, week, [scored[cid].company for cid in ids], http, gdelt_limit, stats)
        count_pop = list(counts.values())
        for cid in ids:
            p = priced[cid]
            metrics = {
                "C1": p.c1,
                "C2": context.Metric(p.c2.value, None, p.c2.score, p.c2.inputs),
                "C3": context.c3(p.ret_52w, pop, Decimal(str(c3_cfg["already_ran_pct"]))),
                "C4": context.c4(counts.get(cid), count_pop),
            }
            for mid, m in metrics.items():
                rows.append(
                    ContextValue(
                        company_id=cid,
                        week_end=week,
                        metric_id=mid,
                        value=None if m.value is None else m.value.quantize(Decimal("0.000001")),
                        pct=None if m.pct is None else m.pct.quantize(Decimal("0.01")),
                        inputs={**m.inputs, "score": num(m.score)},
                    )
                )
    return rows


def attention(
    conn: psycopg.Connection[Any],
    week: date,
    companies: Sequence[Company],
    http: HttpClient | None,
    limit: int,
    stats: ScoresStats,
) -> dict[UUID, int]:
    """GDELT article counts: re-used for 28 days, at most `limit` new queries a run (highest Evidence first is the
    caller's order)."""
    reuse = repo.recent_attention(conn, week, week - timedelta(days=GDELT_REUSE_DAYS))
    out: dict[UUID, int] = {}
    client = GdeltClient(http) if http is not None else None
    for c in companies:
        assert c.id is not None
        if c.id in reuse:
            out[c.id] = reuse[c.id]
            stats.gdelt_reused += 1
            continue
        if client is None or stats.gdelt_queried >= limit:
            continue
        try:
            out[c.id] = client.article_count(c.name, c.ticker if c.market == "us" else c.nse_symbol, c.market)
            stats.gdelt_queried += 1
        except (GdeltError, httpx.HTTPError) as e:
            stats.gdelt_failed += 1
            stats.errors.append(f"gdelt {c.name}: {type(e).__name__}: {e}"[:200])
    return out


def gap_scores(rows: Sequence[ContextValue], cfgs: Configs) -> dict[UUID, Decimal | None]:
    by: dict[UUID, dict[str, Decimal | None]] = defaultdict(dict)
    for r in rows:
        score = r.inputs.get("score")
        by[r.company_id][r.metric_id] = None if score is None else Decimal(str(score))
    need = int(cfgs.signals["scores"]["gap_min_metrics"])
    return {cid: gap(m, cfgs.weights, need) for cid, m in by.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--week", type=date.fromisoformat, default=None, help="Friday to score (default: the latest)")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    week = a.week or last_friday(datetime.now(UTC).date())
    http = HttpClient(settings)
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "scores_weekly", "stooq") as run_:
        stats = run(conn, week, http)
        run_.update(stats.__dict__)
    print(
        f"scores {stats.week}: {stats.companies} companies, stage {stats.stage}, buckets {stats.buckets}, "
        f"shortlist {len(stats.shortlist)}, {stats.seconds}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
