"""Themes: where demand is building before the price (docs/SPEC_ISSUES.md 67; weekly.yml's publish job, reports.yml).

Manzoor: "we need a way to see which sectors will have demand and outperform in the future. not the ones that have
already run up ... an evolution prompt which should kinda have it's own consiousness ... and try to adapt to what's
happening in the world."

1. Per company in the universe, as of the latest scored week (point in time: fundamentals and facts through as_of):
   demand evidence = verified demand facts of the last DEMAND_DAYS (order and customer wins, capacity additions, lead
   times, price increases, new segments), S1 (the order book growing faster than sales) fired, or revenue
   accelerating (TTM growth up at least ACCEL points on the quarter before, and above MIN_GROWTH). Its 12-month price
   move: the Lab's US month-ends, India's weekly closes.
2. Per market and industry (at least MIN_NAMES priced companies): the share with demand evidence and the median price
   move. An industry is a candidate when at least two companies show evidence and its share is in the market's top
   quarter; "early" when its median move is at or below the market's.
3. P-08 reads the candidates (numbers and evidence ids only) and its own earlier calls with how their companies have
   moved since, names at most five themes and reviews the earlier calls. Its answer is checked: a theme must name a
   candidate industry, cite that industry's evidence, and use no number the input lacks; one that fails is dropped
   (counted). Without an answer (out of budget, no provider) the report still carries the table.

Not part of the Evidence score; no weight reads it. `python -m pipeline.reports.themes [--week D]`."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import repo
from pipeline.db.models import Company, FactRow, FundamentalsRow
from pipeline.db.pit import as_of
from pipeline.llm.router import Deferred, Router
from pipeline.llm.themes import CONFIDENCE, MAX_THEMES, ThemesInput
from pipeline.reports.winners import close_at, india_series, us_series
from pipeline.settings import Settings
from pipeline.signals.weekly import last_friday

DEMAND_FACTS = ("order_win", "customer_win", "capacity_addition", "lead_time", "price_increase", "new_segment")
DEMAND_DAYS = 180
ACCEL = 0.03
MIN_GROWTH = 0.05
MIN_NAMES = 5
TOP_SHARE = 0.75  # the market's top quarter of industries by demand share
MAX_EXAMPLES = 4
MEMORY_WEEKS = 8
WORDS = {"title": 8, "why": 45, "wrong_if": 25, "note": 60, "reason": 30}

Series = Mapping[UUID, Sequence[tuple[date, Decimal]]]


@dataclass
class Firm:
    company: Company
    industry: str
    accelerating: bool = False
    order_book: bool = False
    facts: list[FactRow] = field(default_factory=list)
    move: float | None = None
    price: float | None = None

    @property
    def demand(self) -> bool:
        return self.accelerating or self.order_book or bool(self.facts)


def ttm_growth(rows: Sequence[FundamentalsRow], back: int) -> float | None:
    """TTM revenue growth `back` quarters ago (0 = the latest): the four quarters ending there over the four a year
    before. Rows are one company's quarters, oldest first."""
    rev = [r.revenue for r in rows]
    end = len(rev) - back
    if end < 8 or any(v is None for v in rev[end - 8 : end]):
        return None
    now = sum(v for v in rev[end - 4 : end] if v is not None)
    before = sum(v for v in rev[end - 8 : end - 4] if v is not None)
    return None if before <= 0 else float(now / before - 1)


def accelerating(rows: Sequence[FundamentalsRow]) -> bool:
    g0, g1 = ttm_growth(rows, 0), ttm_growth(rows, 1)
    return g0 is not None and g1 is not None and g0 > MIN_GROWTH and g0 - g1 >= ACCEL


def move_12m(s: Sequence[tuple[date, Decimal]], today: date) -> tuple[float | None, float | None]:
    """(12-month price move, latest close): the latest close within 40 days of today over the close a year before it."""
    if not s:
        return None, None
    last_day, last = s[-1]
    if (today - last_day).days > 40:
        return None, None
    then = close_at(s, last_day - timedelta(days=365), 40)
    return (None if then is None or then <= 0 else float(last / then - 1)), float(last)


def industry_of(c: Company) -> str | None:
    return c.industry or c.sector


def industries(firms: Sequence[Firm]) -> list[dict[str, Any]]:
    """Per market and industry with at least MIN_NAMES priced companies: counts, the demand share, the median move
    and up to MAX_EXAMPLES pieces of evidence (ids e1, e2, ... assigned later)."""
    groups: dict[tuple[str, str], list[Firm]] = defaultdict(list)
    for f in firms:
        if f.move is not None:
            groups[(f.company.market, f.industry)].append(f)
    out = []
    for (market, ind), fs in groups.items():
        if len(fs) < MIN_NAMES:
            continue
        shown = [f for f in fs if f.demand]
        examples = []
        for f in sorted(shown, key=lambda f: (-len(f.facts), f.company.name)):
            what = (f"{f.facts[-1].fact_type}: {f.facts[-1].subject}"[:160] if f.facts
                    else "order book growing faster than sales" if f.order_book
                    else "revenue growth accelerating")  # fmt: skip
            examples.append({"company_id": str(f.company.id), "code": f.company.ticker or f.company.nse_symbol,
                             "name": f.company.name, "what": what, "move": round(f.move or 0.0, 3)})  # fmt: skip
            if len(examples) == MAX_EXAMPLES:
                break
        out.append({"market": market, "industry": ind, "companies": len(fs), "with_demand": len(shown),
                    "share": round(len(shown) / len(fs), 3),
                    "facts": sum(len(f.facts) for f in fs), "order_book": sum(f.order_book for f in fs),
                    "accelerating": sum(f.accelerating for f in fs),
                    "median_move": round(statistics.median(f.move for f in fs if f.move is not None), 3),
                    "examples": examples})  # fmt: skip
    return sorted(out, key=lambda r: (r["market"], -r["share"], -r["with_demand"]))


def candidates(rows: Sequence[dict[str, Any]], market_median: Mapping[str, float]) -> list[dict[str, Any]]:
    """The industries P-08 reads: at least two companies with evidence and a share in the market's top quarter, each
    marked early (median move at or below the market's) or running; evidence ids e1, e2, ... in order."""
    out = []
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_market[r["market"]].append(r)
    n = 0
    for market, rs in sorted(by_market.items()):
        shares = sorted(r["share"] for r in rs)
        cut = shares[int(len(shares) * TOP_SHARE)] if len(shares) >= 4 else 0.0
        for r in rs:
            if r["with_demand"] < 2 or r["share"] < cut:
                continue
            ex = []
            for e in r["examples"]:
                n += 1
                ex.append({**e, "id": f"e{n}"})
            out.append({**r, "examples": ex, "early": r["median_move"] <= market_median.get(market, 0.0)})
    return out


# ---------------------------------------------------------------- P-08's answer, checked


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _words(text: str) -> int:
    return len(text.split())


Checked = tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str]]


def check_answer(answer: Mapping[str, Any], cands: Sequence[Mapping[str, Any]], input_text: str,
                 earlier: Sequence[Mapping[str, Any]]) -> Checked:  # fmt: skip
    """(themes kept, reviews kept, note, why each dropped one was dropped)."""
    known = {(c["market"], c["industry"]): c for c in cands}
    numbers = set(NUMBER.findall(input_text))
    dropped: list[str] = []

    def numbers_ok(text: str) -> bool:
        return all(n in numbers or n.rstrip("0").rstrip(".") in numbers for n in NUMBER.findall(text))

    themes = []
    for t in answer.get("themes") or []:
        if not isinstance(t, dict):
            continue
        key = (str(t.get("market")), str(t.get("industry")))
        c = known.get(key)
        ids = {e["id"] for e in c["examples"]} if c else set()
        cited = [e for e in (t.get("evidence") or []) if isinstance(e, str)]
        texts = {k: str(t.get(k) or "").strip() for k in ("title", "why", "wrong_if")}
        why = ("not a candidate industry" if c is None
               else "cites no evidence of its industry" if not cited or not set(cited) <= ids
               else "a theme needs evidence from two companies" if len({e["company_id"] for e in c["examples"]
                                                                         if e["id"] in cited}) < 2
               else "a number the input lacks" if not all(numbers_ok(v) for v in texts.values())
               else "too long" if any(_words(v) > WORDS[k] for k, v in texts.items())
               else "empty" if not all(texts.values())
               else "unknown confidence" if t.get("confidence") not in CONFIDENCE else None)  # fmt: skip
        if why is not None:
            dropped.append(f"{key[0]} {key[1]}: {why}")
            continue
        assert c is not None
        themes.append({**texts, "market": key[0], "industry": key[1], "confidence": t["confidence"],
                       "evidence": [e for e in c["examples"] if e["id"] in cited],
                       "share": c["share"], "with_demand": c["with_demand"], "companies": c["companies"],
                       "median_move": c["median_move"], "early": c["early"]})  # fmt: skip
        if len(themes) == MAX_THEMES:
            break
    called = {(str(e["market"]), str(e["industry"])) for e in earlier}
    reviews = []
    for r in answer.get("reviews") or []:
        if not isinstance(r, dict):
            continue
        key = (str(r.get("market")), str(r.get("industry")))
        reason = str(r.get("reason") or "").strip()
        if key in called and r.get("decision") in ("keep", "drop") and reason and _words(reason) <= WORDS["reason"] \
                and numbers_ok(reason):  # fmt: skip
            reviews.append({"market": key[0], "industry": key[1], "decision": r["decision"], "reason": reason})
    note = str(answer.get("note") or "").strip()
    if _words(note) > WORDS["note"] or not numbers_ok(note):
        dropped.append("note: too long or a number the input lacks")
        note = ""
    return themes, reviews, note, dropped


# ---------------------------------------------------------------- memory: earlier calls and how they did


def scorecard(earlier: Sequence[Mapping[str, Any]], prices: Mapping[str, float]) -> list[dict[str, Any]]:
    """Each earlier theme (newest week first, one per industry) with its companies' average move since the call."""
    out, seen = [], set()
    for rep in earlier:
        for t in rep.get("themes") or []:
            key = (t.get("market"), t.get("industry"))
            if key in seen:
                continue
            seen.add(key)
            moves = [prices[e["company_id"]] / e["price"] - 1 for e in t.get("evidence") or []
                     if e.get("price") and e.get("company_id") in prices]  # fmt: skip
            out.append({"week": rep.get("week"), "market": key[0], "industry": key[1], "title": t.get("title"),
                        "since": round(statistics.fmean(moves), 3) if moves else None})  # fmt: skip
    return out


# ---------------------------------------------------------------- the database


def gather(conn: psycopg.Connection[Any], week: date, today: date) -> list[Firm]:
    firms: dict[UUID, Firm] = {}
    for market in ("us", "in"):
        cs = [c for c in repo.companies(conn, market=market, in_universe=True) if c.id is not None and industry_of(c)]
        ids = [c.id for c in cs if c.id is not None]
        series: Series = us_series(conn, cs) if market == "us" else india_series(conn, ids, today)
        for c in cs:
            assert c.id is not None
            f = Firm(c, str(industry_of(c)))
            f.move, f.price = move_12m(series.get(c.id, []), today)
            firms[c.id] = f
    ids = list(firms)
    snap = as_of(week)
    rows: dict[UUID, list[FundamentalsRow]] = defaultdict(list)
    for r in snap.fundamentals(conn, ids):
        rows[r.company_id].append(r)
    for cid, rs in rows.items():
        firms[cid].accelerating = accelerating(sorted(rs, key=lambda r: r.period_end))
    for fact in snap.facts(conn, ids, since=week - timedelta(days=DEMAND_DAYS)):
        if fact.fact_type in DEMAND_FACTS:
            firms[fact.company_id].facts.append(fact)
    for cid in repo.fired_companies(conn, week, "S1"):
        if cid in firms:
            firms[cid].order_book = True
    return list(firms.values())


def build(conn: psycopg.Connection[Any], router: Router | None, week: date, today: date) -> dict[str, Any]:
    firms = gather(conn, week, today)
    rows = industries(firms)
    medians = {m: round(statistics.median(f.move for f in firms if f.company.market == m and f.move is not None), 3)
               for m in ("us", "in") if any(f.company.market == m and f.move is not None for f in firms)}  # fmt: skip
    cands = candidates(rows, medians)
    prices = {str(f.company.id): f.price for f in firms if f.price}
    earlier = [r for _, r in repo.recent_reports(conn, "themes", week, MEMORY_WEEKS)]
    card = scorecard(earlier, prices)
    body: dict[str, Any] = {"week": week.isoformat(), "as_of": today.isoformat(), "medians": medians,
                            "industries": rows[:60], "candidates": len(cands), "themes": [], "reviews": [],
                            "note": "", "scorecard": card, "dropped": [], "answered": False}  # fmt: skip
    if router is None or not cands:
        body["note"] = "" if cands else "No industry shows broad demand evidence this week."
        return body
    slim = [{k: c[k] for k in ("market", "industry", "companies", "with_demand", "share", "facts", "order_book",
                               "accelerating", "median_move", "early")}
            | {"market_median_move": medians.get(c["market"]),
               "evidence": [{"id": e["id"], "company": e["code"] or e["name"], "what": e["what"], "move": e["move"]}
                            for e in c["examples"]]} for c in cands]  # fmt: skip
    industries_json = json.dumps(slim, ensure_ascii=False)
    calls_json = json.dumps(card, ensure_ascii=False)
    answer = router.call(ThemesInput(industries_json, calls_json))
    if isinstance(answer, Deferred):
        body["note"] = ""
        body["dropped"] = [f"no answer: {answer.reason}"[:200]]
        return body
    themes, reviews, note, dropped = check_answer(answer.content, cands, industries_json + calls_json, card)
    for t in themes:
        for e in t["evidence"]:
            e["price"] = prices.get(e["company_id"])
    body.update({"themes": themes, "reviews": reviews, "note": note, "dropped": dropped, "answered": True})
    return body


def main(argv: list[str] | None = None) -> int:
    from pipeline.db import facts_repo
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas
    from pipeline.net.http import HttpClient

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=date.fromisoformat, default=None, help="the scored week (default: the last Friday)")
    a = ap.parse_args(argv)
    today = datetime.now(UTC).date()
    week = a.week or last_friday(today)
    settings = Settings.from_env()
    quotas = Quotas.load()
    with psycopg.connect(settings.database_url) as conn:
        router = (facts_repo.logged_router(conn, providers(HttpClient(settings), settings, quotas), quotas, today)
                  if quotas.configured() else None)  # fmt: skip
        body = build(conn, router, week, today)
        repo.upsert_report(conn, "themes", week, body)
    print(f"themes {week}: {len(body['industries'])} industries, {body['candidates']} candidates, "
          f"{len(body['themes'])} themes, {len(body['dropped'])} dropped, answered={body['answered']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
