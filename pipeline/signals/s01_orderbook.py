"""S1 order-book acceleration (BRIEF §4.6): the order book (US RPO, else the latest verified `backlog` fact per
quarter) grows faster than TTM revenue by >= 10 pp in each of the last 2 quarters, and coverage (ob / TTM revenue) is
above its year-ago value. Strength clip((g(ob) - g(rev)) / 0.30, 0, 1)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from pipeline.signals.base import Ctx, Fact, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, Series, clip, growth, ratio

ID, FAMILY = "S1", "fundamentals"
MATCH_DAYS = 20  # a backlog fact belongs to a quarter when its period end is within this many days


def order_book(ctx: Ctx) -> tuple[Callable[[int], Decimal | None], str]:
    return book(ctx.series, ctx.market, ctx.facts)


def book(s: Series, market: str, facts: Sequence[Fact]) -> tuple[Callable[[int], Decimal | None], str]:
    """The order book by lag: US RPO where the filer tags it, else the latest verified `backlog:total` fact for the
    quarter; and which of the two (the Company page's chart uses it too, weekly.series_points)."""
    if market == "us" and any(q.get("rpo") is not None for q in s.quarters):
        return (lambda k: s.value("rpo", k)), "rpo"
    backlog = sorted(
        (f for f in facts if f.fact_type == "backlog" and f.subject_key == "backlog:total" and f.period_end),
        key=lambda f: f.as_of,
    )

    def from_facts(k: int) -> Decimal | None:
        q = s.at(k)
        if q is None:
            return None
        hits = [f for f in backlog if f.period_end and abs((f.period_end - q.end).days) <= MATCH_DAYS]
        return hits[-1].value_num if hits else None  # the latest statement for that quarter

    return from_facts, "backlog_fact"


def orderbook_growth(ctx: Ctx, lag: int = 0) -> Decimal | None:
    """g(ob) at `lag` against a year earlier (None without a year back; C2's evidence growth uses it too)."""
    ob, _ = order_book(ctx)
    return growth(ob(lag), ob(lag + 4)) if ctx.series.year_back_ok(lag) else None


def compute(ctx: Ctx) -> SignalResult:
    c = ctx.section("s1_orderbook")
    ob, source = order_book(ctx)
    s = ctx.series
    gaps: list[Decimal] = []
    detail: dict[str, object] = {"source": source}
    for k in range(int(c["consecutive_quarters"])):
        g_ob = growth(ob(k), ob(k + 4)) if s.year_back_ok(k) else None
        g_rev = s.ttm_yoy("revenue", k)
        if g_ob is None or g_rev is None:
            return missing("order_book_growth" if g_ob is None else "ttm_revenue_growth", lag=k, **detail)
        gaps.append(g_ob - g_rev)
        detail[f"g_ob_{k}"], detail[f"g_rev_{k}"] = num(g_ob), num(g_rev)
    cov_now = ratio(ob(0), s.ttm("revenue", 0))
    cov_then = ratio(ob(4), s.ttm("revenue", 4)) if s.year_back_ok(0) else None
    if cov_now is None or cov_then is None:
        return missing("coverage", **detail)
    inputs = {**detail, "gaps": [num(g) for g in gaps], "coverage": num(cov_now), "coverage_year_ago": num(cov_then)}
    ok = all(g >= cfg_dec(c, "min_growth_gap") for g in gaps)
    if c.get("coverage_must_rise_yoy", True):
        ok = ok and cov_now > cov_then
    if not ok:
        return quiet(**inputs)
    return fired(clip(gaps[0] / cfg_dec(c, "strength_divisor"), ZERO, Decimal(1)), **inputs)
