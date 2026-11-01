"""Themes: a library of demand chains that evolves (docs/SPEC_ISSUES.md 67, 68; weekly.yml's publish job, reports.yml).

Manzoor: "we need a way to see which sectors will have demand and outperform in the future. not the ones that have
already run up ... an evolution prompt which should kinda have it's own consiousness"; then: "don't make this specific
to AI ... a lot of automobiles purchased in certain year ... people would want to replace the tires after four years
... if people are buying homes, we should buy more paint ... I should be able to see things in the dropdown ... this
needs to evolve as well".

A theme is a chain: a driver (a public FRED series, config/drivers.yaml, or `filings`: its industries' own demand
evidence), read one way (pipeline/reports/drivers.py: yoy, level, or cohort `lag_months` back), reaching the companies
whose industry, sector or name matches its keywords. The library starts from config/themes_seed.yaml and lives in the
weekly report body (`library`, `retired`); each week's report carries it forward.

Every Saturday (numbers only, no LLM), per theme: the driver's z-score and its last ten years; its companies' demand
evidence (verified demand facts of the last 180 days, S1 fired, revenue accelerating; point in time through as_of) and
median 12-month price move against the market's; the undervalued names among them (the latest scores' Candidate and
Watch buckets); a history check (US: did these companies beat the market in years the driver said so); a status:
- building: the driver is a tailwind (z >= 0.5; for `filings`, the evidence share in the industries' top quarter) and
  the price hasn't run (at most RUN_UP above the market's median move);
- priced in: a tailwind, and the price already ran;
- fading: the driver turned (z <= -0.5);
- watching: anything else.

Monthly, P-08 rethinks the library (the first Saturday of a month; sooner when a theme's status changed or a driver
moved a full z since the last rethink; never more than weekly): keep, edit or retire each theme, propose at most three
new ones. Its answer is checked: a real driver and reading, keywords that match at least MIN_MEMBERS companies, word
limits, no number the input lacks; what fails is dropped and counted. Notes accumulate per theme, so the library has
a memory of why it changed. Not part of the Evidence score; no weight reads it.

`python -m pipeline.reports.themes [--week D] [--rethink]`."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db import state as db_state
from pipeline.db.models import Company, FactRow, FundamentalsRow
from pipeline.db.pit import as_of
from pipeline.llm.router import Deferred, Router
from pipeline.llm.themes import CATEGORIES, MAX_NEW, READINGS, ThemesInput
from pipeline.net import fred
from pipeline.net.http import HttpClient
from pipeline.reports import drivers as dv
from pipeline.reports.winners import close_at, india_series, us_series, year_return
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals.weekly import last_friday

DEMAND_FACTS = ("order_win", "customer_win", "capacity_addition", "lead_time", "price_increase", "new_segment")
DEMAND_DAYS = 180
ACCEL = 0.03
MIN_GROWTH = 0.05
MIN_NAMES = 5  # an industry row in the table
MIN_MEMBERS = 3  # a theme's keywords must match at least this many companies
RUN_UP = 0.10
TAILWIND = 0.5
MAX_ACTIVE = 24
MAX_NAMES = 8
MAX_NOTES = 12
MAX_RETIRED = 30
WORDS = {"title": 8, "why": 45, "wrong_if": 25, "note": 60, "review": 35}
FIRST_YEAR = 2012

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
    evidence: float | None = None
    bucket: str | None = None
    series: Sequence[tuple[date, Decimal]] = ()

    @property
    def demand(self) -> bool:
        return self.accelerating or self.order_book or bool(self.facts)

    def haystack(self) -> str:
        c = self.company
        return " | ".join(x for x in (c.industry, c.sector, c.name) if x).casefold()


# ---------------------------------------------------------------- per company


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


# ---------------------------------------------------------------- the industry table


def industries(firms: Sequence[Firm]) -> list[dict[str, Any]]:
    """Per market and industry with at least MIN_NAMES priced companies: counts, demand share and median move."""
    groups: dict[tuple[str, str], list[Firm]] = defaultdict(list)
    for f in firms:
        if f.move is not None:
            groups[(f.company.market, f.industry)].append(f)
    out = []
    for (market, ind), fs in groups.items():
        if len(fs) < MIN_NAMES:
            continue
        shown = sum(f.demand for f in fs)
        out.append({"market": market, "industry": ind, "companies": len(fs), "with_demand": shown,
                    "share": round(shown / len(fs), 3), "facts": sum(len(f.facts) for f in fs),
                    "median_move": round(statistics.median(f.move for f in fs if f.move is not None), 3)})  # fmt: skip
    return sorted(out, key=lambda r: (r["market"], -r["share"], -r["companies"]))


# ---------------------------------------------------------------- a theme's numbers


def members(firms: Sequence[Firm], keywords: Sequence[str]) -> list[Firm]:
    keys = [k.casefold().strip() for k in keywords if k.strip()]
    return [f for f in firms if any(k in f.haystack() for k in keys)]


def slug_of(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:60] or "theme"


def group_excess(fs: Sequence[Firm], market_by_year: Mapping[int, float], last_year: int) -> dict[int, float]:
    """Each year's average return of the US companies in `fs` with a price at both ends, minus the market's."""
    out = {}
    for year in range(FIRST_YEAR, last_year + 1):
        rets = [r for f in fs if f.company.market == "us" and f.series
                and (r := year_return(f.series, year, "us")) is not None]  # fmt: skip
        if len(rets) >= MIN_MEMBERS and year in market_by_year:
            out[year] = statistics.fmean(rets) - market_by_year[year]
    return out


def market_years(firms: Sequence[Firm], last_year: int) -> dict[int, float]:
    out = {}
    for year in range(FIRST_YEAR, last_year + 1):
        rets = [r for f in firms if f.company.market == "us" and f.series
                and (r := year_return(f.series, year, "us")) is not None]  # fmt: skip
        if len(rets) >= 50:
            out[year] = statistics.fmean(rets)
    return out


def status_of(z: float | None, run: float | None) -> str:
    if z is not None and z >= TAILWIND:
        return "priced_in" if run is not None and run > RUN_UP else "building"
    if z is not None and z <= -TAILWIND:
        return "fading"
    return "watching"


def filings_z(share: float, shares: Sequence[float]) -> float | None:
    """`filings` themes: the companies' evidence share against the industries' shares, as a z-score."""
    if len(shares) < 5 or statistics.pstdev(shares) == 0:
        return None
    return round((share - statistics.fmean(shares)) / statistics.pstdev(shares), 2)


def numbers(theme: Mapping[str, Any], firms: Sequence[Firm], points: Mapping[str, dv.Points],
            drv: Mapping[str, dv.Driver], medians: Mapping[str, float], shares: Sequence[float],
            market_by_year: Mapping[int, float], last_year: int) -> dict[str, Any]:  # fmt: skip
    """This week's numbers for one theme (merged into its library entry)."""
    fs = members(firms, theme["keywords"])
    priced = [f for f in fs if f.move is not None]
    shown = sum(f.demand for f in fs)
    share = round(shown / len(fs), 3) if fs else 0.0
    moves = [f.move for f in priced if f.move is not None]
    move = round(statistics.median(moves), 3) if moves else None
    markets = sorted({f.company.market for f in priced})
    market_move = (round(statistics.fmean(medians[m] for m in markets if m in medians), 3)
                   if any(m in medians for m in markets) else None)  # fmt: skip
    run = round(move - market_move, 3) if move is not None and market_move is not None else None
    driver, reading, lag = theme["driver"], theme["transform"], int(theme.get("lag_months") or 0)
    pts = points.get(driver, [])
    if driver == dv.FILINGS:
        z, chart, history = filings_z(share, shares), [], None
    else:
        d = drv.get(driver)
        inv = bool(d.inverse) if d else False
        z = dv.latest_z(pts, reading, lag, inv) if pts else None
        chart = dv.chart(pts)
        history = (dv.history_check(pts, reading, lag, inv, group_excess(fs, market_by_year, last_year))
                   if pts else None)  # fmt: skip
    ranked = sorted(fs, key=lambda f: ({"candidate": 0, "watch": 1}.get(f.bucket or "", 2), -(f.evidence or 0),
                                       f.company.name))  # fmt: skip
    names = [{"company_id": str(f.company.id), "code": f.company.ticker or f.company.nse_symbol,
              "name": f.company.name, "market": f.company.market, "industry": f.industry,
              "evidence": f.evidence, "bucket": f.bucket, "move": round(f.move, 3) if f.move is not None else None,
              "demand": f.demand} for f in ranked[:MAX_NAMES]]  # fmt: skip
    return {"z": z, "signal": dv.words(z), "chart": chart, "companies": len(fs), "priced": len(priced),
            "with_demand": shown, "share": share, "move": move, "market_move": market_move, "run": run,
            "markets": markets, "status": status_of(z, run), "history": history, "names": names,
            "undervalued": sum(1 for f in fs if f.bucket in ("candidate", "watch"))}  # fmt: skip


# ---------------------------------------------------------------- the library and its rethink


def seed(root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    doc = yaml.safe_load((root / "config" / "themes_seed.yaml").read_text(encoding="utf-8"))
    return [{**t, "lag_months": int(t.get("lag_months") or 0), "origin": "starter", "born": None, "notes": []}
            for t in doc["themes"]]  # fmt: skip


def rethink_due(week: date, last: date | None, triggered: bool) -> tuple[bool, str]:
    if last is None:
        return True, "the first rethink"
    days = (week - last).days
    if days < 7:
        return False, ""
    if week.day <= 7 and (week.year, week.month) != (last.year, last.month):
        return True, "the month's rethink"
    if days >= 35:
        return True, "five weeks since the last rethink"
    if triggered:
        return True, "a theme's status changed or its driver moved"
    return False, ""


def next_rethink(week: date) -> date:
    """The first Friday of next month: the week whose Saturday run rethinks."""
    first = date(week.year + (week.month == 12), week.month % 12 + 1, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7)


def triggered(prev: Sequence[Mapping[str, Any]], now: Sequence[Mapping[str, Any]]) -> bool:
    before = {t["slug"]: t for t in prev}
    for t in now:
        p = before.get(t["slug"])
        if p is None:
            continue
        if p.get("status") and p.get("status") != t.get("status"):
            return True
        z0, z1 = p.get("z_at_rethink"), t.get("z")
        if z0 is not None and z1 is not None and abs(z1 - z0) >= 1.0:
            return True
    return False


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _norm(n: str) -> str:
    """ "12.0" -> "12", "0.50" -> "0.5", "1,240" -> "1240"."""
    n = n.replace(",", "")
    return n.rstrip("0").rstrip(".") if "." in n else n


def allowed_numbers(text: str) -> set[str]:
    """The numbers the input states, and each fraction as the percent a writer says it as (0.123 -> 12.3 and 12):
    a theme may say "up 12%" for a move of 0.12, never a number the input lacks."""
    out = set()
    for raw in NUMBER.findall(text):
        n = _norm(raw)
        out.add(n)
        v = float(n)
        if v < 10:
            out.update(_norm(f"{v * 100:.{d}f}") for d in (0, 1))
    return out


def _words(text: str) -> int:
    return len(text.split())


@dataclass
class Rethink:
    reviews: dict[str, dict[str, Any]] = field(default_factory=dict)
    new: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    dropped: list[str] = field(default_factory=list)


def check_answer(answer: Mapping[str, Any], library: Sequence[Mapping[str, Any]], firms: Sequence[Firm],
                 drivers: Mapping[str, dv.Driver], input_text: str) -> Rethink:  # fmt: skip
    """P-08's answer, checked; what fails is dropped with why."""
    out = Rethink()
    allowed = allowed_numbers(input_text)
    slugs = {t["slug"] for t in library} | {slug_of(t["title"]) for t in library}

    def ok_text(text: str, limit: int) -> bool:
        return bool(text) and _words(text) <= limit and all(_norm(n) in allowed for n in NUMBER.findall(text))

    def ok_keywords(kws: Any) -> list[str] | None:
        if not isinstance(kws, list) or not 1 <= len(kws) <= 6:
            return None
        clean = [str(k).strip() for k in kws if isinstance(k, str) and 3 <= len(str(k).strip()) <= 40]
        return clean if len(clean) == len(kws) and len(members(firms, clean)) >= MIN_MEMBERS else None

    for r in answer.get("reviews") or []:
        if not isinstance(r, dict) or r.get("slug") not in slugs:
            continue
        note = str(r.get("note") or "").strip()
        decision = r.get("decision")
        if decision not in ("keep", "edit", "retire") or not ok_text(note, WORDS["review"]):
            out.dropped.append(f"review {r.get('slug')}: no decision or a bad note")
            continue
        review: dict[str, Any] = {"decision": decision, "note": note}
        if decision == "edit":
            for k in ("title", "why", "wrong_if"):
                v = str(r.get(k) or "").strip()
                if v and ok_text(v, WORDS[k]):
                    review[k] = v
            if r.get("keywords") is not None:
                kws = ok_keywords(r.get("keywords"))
                if kws:
                    review["keywords"] = kws
        out.reviews[str(r["slug"])] = review
    for n in (answer.get("new") or [])[:MAX_NEW]:
        if not isinstance(n, dict):
            continue
        title, why, wrong = (str(n.get(k) or "").strip() for k in ("title", "why", "wrong_if"))
        driver, reading = str(n.get("driver") or ""), str(n.get("reading") or "")
        lag = n.get("lag_months")
        kws = ok_keywords(n.get("keywords"))
        problem = ("an unknown category" if n.get("category") not in CATEGORIES
                   else "an unknown driver" if driver != dv.FILINGS and driver not in drivers
                   else "an unknown reading" if reading not in READINGS
                   else "a bad lag" if not isinstance(lag, int) or not 0 <= lag <= 120
                   or (reading == "cohort" and lag < 12)
                   else "keywords that match too few companies" if kws is None
                   else "a title, why or wrong-if that is empty, too long or has a number the input lacks"
                   if not (ok_text(title, WORDS["title"]) and ok_text(why, WORDS["why"])
                           and ok_text(wrong, WORDS["wrong_if"]))
                   else "a theme the library has" if slug_of(title) in slugs else None)  # fmt: skip
        if problem:
            out.dropped.append(f"new {title[:40]!r}: {problem}")
            continue
        assert kws is not None and isinstance(lag, int)
        out.new.append({"slug": slug_of(title), "title": title, "category": n["category"], "driver": driver,
                        "transform": reading, "lag_months": lag, "keywords": kws, "why": why, "wrong_if": wrong,
                        "origin": "ai"})  # fmt: skip
    note = str(answer.get("note") or "").strip()
    if note and ok_text(note, WORDS["note"]):
        out.note = note
    elif note:
        out.dropped.append("note: too long or a number the input lacks")
    return out


def apply(library: list[dict[str, Any]], retired: list[dict[str, Any]], r: Rethink,
          week: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:  # fmt: skip
    """The rethink applied: notes appended, edits made, retired themes moved out, new ones added (MAX_ACTIVE)."""
    kept = []
    for t in library:
        rev = r.reviews.get(t["slug"])
        if rev is None:
            kept.append(t)
            continue
        t = {**t, **{k: v for k, v in rev.items() if k in ("title", "why", "wrong_if", "keywords")}}
        t["notes"] = ([*t.get("notes", []), {"week": week.isoformat(), "decision": rev["decision"],
                                             "text": rev["note"]}])[-MAX_NOTES:]  # fmt: skip
        if rev["decision"] == "retire":
            retired = [{"slug": t["slug"], "title": t["title"], "category": t["category"], "week": week.isoformat(),
                        "note": rev["note"], "notes": t["notes"], "status": t.get("status")},
                       *retired][:MAX_RETIRED]  # fmt: skip
        else:
            kept.append(t)
    for n in r.new:
        if len(kept) >= MAX_ACTIVE:
            break
        kept.append({**n, "born": week.isoformat(), "notes": [{"week": week.isoformat(), "decision": "new",
                                                              "text": n["why"]}]})  # fmt: skip
    return kept, retired


def prompt_input(drivers_summary: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]],
                 library: Sequence[Mapping[str, Any]],
                 retired: Sequence[Mapping[str, Any]]) -> ThemesInput:  # fmt: skip
    lib = [{k: t.get(k) for k in ("slug", "title", "category", "driver", "transform", "lag_months", "keywords",
                                  "why", "status", "z", "signal", "companies", "with_demand", "share", "move",
                                  "market_move", "history")}
           | {"notes": [n["text"] for n in t.get("notes", [])[-3:]]} for t in library]  # fmt: skip
    ind = [{k: r[k] for k in ("market", "industry", "companies", "with_demand", "share", "median_move")} for r in rows]
    ret = [{"title": t["title"], "week": t["week"], "note": t["note"]} for t in retired[:10]]
    return ThemesInput(json.dumps(list(drivers_summary), ensure_ascii=False), json.dumps(ind, ensure_ascii=False),
                       json.dumps(lib, ensure_ascii=False), json.dumps(ret, ensure_ascii=False))  # fmt: skip


# ---------------------------------------------------------------- the database


def gather(conn: psycopg.Connection[Any], week: date, today: date) -> list[Firm]:
    firms: dict[UUID, Firm] = {}
    scores = repo.scores_for_week(conn, week)
    for market in ("us", "in"):
        cs = [c for c in repo.companies(conn, market=market, in_universe=True) if c.id is not None]
        ids = [c.id for c in cs if c.id is not None]
        series: Series = us_series(conn, cs) if market == "us" else india_series(conn, ids, today)
        for c in cs:
            assert c.id is not None
            s = series.get(c.id, [])
            f = Firm(c, industry_of(c) or "Unclassified", series=s if market == "us" else ())
            f.move, f.price = move_12m(s, today)
            sc = scores.get(c.id)
            if sc is not None:
                f.evidence, f.bucket = float(sc.evidence), sc.bucket
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


FRED_STATE = "fred_series"
FRED_BUDGET_S = 150.0  # all the drivers' downloads together; past it, last good copies are used


Fetched = tuple[dict[str, dv.Points], list[str]]


def driver_points(http: HttpClient, ids: Sequence[str], cached: Mapping[str, dv.Points] | None = None,
                  budget: float = FRED_BUDGET_S, api_key: str | None = None) -> Fetched:  # fmt: skip
    """Each driver's monthly points from FRED (20 s a request, FRED_BUDGET_S in all); a series that fails, comes back
    empty or is past the budget uses its last good copy (`cached`), else is missing."""
    out: dict[str, dv.Points] = {}
    missing: list[str] = []
    t0 = time.monotonic()
    for i in ids:
        why = ""
        if time.monotonic() - t0 > budget:
            why = "over the time budget"
        else:
            try:
                pts = fred.series(http, i, api_key=api_key)
                if pts:
                    out[i] = pts
                    continue
                why = "empty"
            except Exception as e:  # noqa: BLE001 - one series down must not stop the week's themes
                why = type(e).__name__
        if cached and cached.get(i):
            out[i] = cached[i]
            missing.append(f"{i}: {why}, last good copy used")
        else:
            missing.append(f"{i}: {why}")
    return out, missing


SNAPSHOT = REPO_ROOT / "data" / "fred"  # the series as of 2026-11-01, committed: the first last-good copies


def load_cached(conn: psycopg.Connection[Any], snapshot: Path = SNAPSHOT) -> dict[str, dv.Points]:
    """The last good copy of each series: the database's (saved each week), else the committed snapshot's."""
    out: dict[str, dv.Points] = {
        f.stem: fred.parse(f.read_text(encoding="utf-8")) for f in sorted(snapshot.glob("*.csv"))
    }
    stored = db_state.get(conn, FRED_STATE)
    if stored is not None:
        doc = json.loads(stored.body)
        out.update({k: [(date.fromisoformat(d), float(v)) for d, v in pts] for k, pts in doc.items() if pts})
    return out


def save_cached(conn: psycopg.Connection[Any], points: Mapping[str, dv.Points]) -> None:
    doc = {k: [[d.isoformat(), v] for d, v in pts] for k, pts in points.items()}
    db_state.put(conn, FRED_STATE, json.dumps(doc).encode())


def build(conn: psycopg.Connection[Any], router: Router | None, http: HttpClient, week: date, today: date,
          force_rethink: bool = False, root: Path = REPO_ROOT) -> dict[str, Any]:  # fmt: skip
    t0 = time.monotonic()

    def lap(what: str) -> None:  # the log is public: counts and seconds only
        print(f"themes: {what} at {time.monotonic() - t0:.0f} s", flush=True)

    firms = gather(conn, week, today)
    lap(f"{len(firms)} companies gathered")
    rows = industries(firms)
    medians = {m: round(statistics.median(f.move for f in firms if f.company.market == m and f.move is not None), 3)
               for m in ("us", "in") if any(f.company.market == m and f.move is not None for f in firms)}  # fmt: skip
    drv = dv.load(root)
    points, missing = driver_points(http, list(drv), load_cached(conn), api_key=http.settings.fred_api_key)
    save_cached(conn, points)
    lap(f"{len(points)} drivers read, {len(missing)} not fresh")
    shares = [r["share"] for r in rows]
    last_year = today.year - 1
    mkt = market_years(firms, last_year)
    prev: dict[str, Any] = next((b for _, b in repo.recent_reports(conn, "themes", week, 1)), {})
    library: list[dict[str, Any]] = list(prev.get("library") or seed(root))
    retired: list[dict[str, Any]] = list(prev.get("retired") or [])
    last = date.fromisoformat(prev["last_rethink"]) if prev.get("last_rethink") else None

    def refresh(lib: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**t, **numbers(t, firms, points, drv, medians, shares, mkt, last_year)} for t in lib]

    library = refresh(library)
    lap(f"{len(library)} themes measured")
    due, why = rethink_due(week, last, triggered(prev.get("library") or [], library))
    if force_rethink and not due:
        due, why = True, "asked for"
    body: dict[str, Any] = {"week": week.isoformat(), "as_of": today.isoformat(), "version": 2, "medians": medians,
                            "industries": rows[:80], "missing_drivers": missing,
                            "drivers": {k: d.name for k, d in drv.items()},
                            "last_rethink": last.isoformat() if last else None, "rethought": False, "why": "",
                            "note": prev.get("note", ""), "dropped": []}  # fmt: skip
    if due and router is not None:
        inp = prompt_input([dv.summary(points[k], d) for k, d in drv.items() if k in points], rows, library, retired)
        answer = router.call(inp)
        lap("the rethink answered" if not isinstance(answer, Deferred) else "the rethink deferred")
        if isinstance(answer, Deferred):
            body["dropped"] = [f"no answer: {answer.reason}"[:200]]
        else:
            text = inp.drivers_json + inp.industries_json + inp.library_json
            r = check_answer(answer.content, library, firms, drv, text)
            library, retired = apply(library, retired, r, week)
            library = refresh(library)
            for t in library:
                t["z_at_rethink"] = t.get("z")
            body.update({"rethought": True, "why": why, "last_rethink": week.isoformat(), "note": r.note,
                         "dropped": r.dropped})  # fmt: skip
    elif due:
        body["dropped"] = ["no rethink: no LLM provider is configured"]
    body["next_rethink"] = next_rethink(week).isoformat()
    order = {"building": 0, "priced_in": 1, "watching": 2, "fading": 3}
    body["library"] = sorted(library, key=lambda t: (order.get(t.get("status", ""), 9), -(t.get("z") or -9)))
    body["retired"] = retired
    return body


def main(argv: list[str] | None = None) -> int:
    from pipeline.db import facts_repo
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=date.fromisoformat, default=None, help="the scored week (default: the last Friday)")
    ap.add_argument("--rethink", action="store_true", help="rethink the library now, whatever the calendar says")
    a = ap.parse_args(argv)
    today = datetime.now(UTC).date()
    week = a.week or last_friday(today)
    settings = Settings.from_env()
    quotas = Quotas.load()
    http = HttpClient(settings)
    with psycopg.connect(settings.database_url) as conn:
        router = (facts_repo.logged_router(conn, providers(http, settings, quotas), quotas, today)
                  if quotas.configured() else None)  # fmt: skip
        body = build(conn, router, http, week, today, force_rethink=a.rethink)
        repo.upsert_report(conn, "themes", week, body)
    counts: dict[str, int] = defaultdict(int)
    for t in body["library"]:
        counts[t["status"]] += 1
    # the log is public: counts only
    print(f"themes {week}: {len(body['library'])} in the library ({dict(counts)}), {len(body['retired'])} retired, "
          f"rethought={body['rethought']}, {len(body['dropped'])} dropped, {len(body['missing_drivers'])} drivers "
          f"missing; next rethink {body['next_rethink']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
