"""Winners (docs/SPEC_ISSUES.md 64; reports.yml): each market's biggest gainers of this year so far (the ten to
watch for next January), last calendar year's five and how they have done this year, and a backtest of buying the
previous year's top five every January.

Manzoor: "pick top five best performing assets each from the previous year ... a portfolio which only invests in
biggest gainers of the previous year vastly outperforms the index." This shows the list and tests the claim on our own
prices before anyone trusts it.

- A year's return is its last close over the previous year's last close (price only, no dividends). US prices are the
  Signal Lab's month-ends (Twelve Data, split-adjusted; pipeline/lab/prices.py); India's are the weekly bhavcopy
  closes (prices_w). A US month up more than MAX_STEP_US or an Indian week up more than MAX_STEP_IN is taken for an
  unadjusted corporate action or a bad print, and that name sits the year out.
- A winner was investable: a price of at least MIN_PRICE when the year began, and a market cap (that close times the
  diluted shares, else shares outstanding, of the latest quarter filed by then: pipeline/db/pit.py) of at least
  MIN_CAP when it ended.
- The backtest (US only, from the Lab's 2010 start; India has two years of prices): in each year, the previous year's
  top five, equal weight, against the average stock investable at that year's start. Both read today's universe, so
  companies that died since are missing from both (survivorship). That flatters the picks more than the average: a
  year's big winner that later collapsed and delisted is exactly what the list can't show.

`python -m pipeline.reports.winners [--week D]` writes reports('winners', D)."""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import fmean
from typing import Any
from uuid import UUID

import psycopg

from pipeline.db import repo
from pipeline.db import state as db_state
from pipeline.db.models import Company, FundamentalsRow
from pipeline.db.pit import as_of
from pipeline.lab.prices import read_prices
from pipeline.settings import Settings
from pipeline.signals.weekly import last_friday

TOP = 5
MIN_PRICE = {"us": Decimal(5), "in": Decimal(20)}  # USD, INR
MIN_CAP = {"us": Decimal(1_000_000_000), "in": Decimal(50_000_000_000)}  # $1B; Rs 5,000 crore
MAX_STEP_US = Decimal(3)  # a month up 300%: a bad print
MAX_STEP_IN = Decimal(1)  # a week up 100%: an unadjusted consolidation or a bad print
TOLERANCE_DAYS = {"us": 0, "in": 10}  # month-ends are exact; a week-end within 10 days of the year's end
LAB_ASSET = "lab_us_month_prices"
CAP_DAYS = 45  # a market cap "today" needs a close this recent (the US closes are month-ends)
# the Winners screen's market-cap range (2026-11-02): a bucket between each step and the next, the last open-ended
CAP_STEPS = {
    "us": [Decimal(x) * 10**9 for x in (1, 2, 5, 10, 20, 50, 100, 200, 500)],  # $1B .. $500B
    "in": [Decimal(x) * 10**10 for x in (5, 10, 20, 50, 100, 200, 500)],  # Rs 5,000 crore .. Rs 5 lakh crore
}
CURRENCY = {"us": "USD", "in": "INR"}

Series = Mapping[UUID, Sequence[tuple[date, Decimal]]]


@dataclass(frozen=True)
class Pick:
    company_id: UUID
    ret: float
    start: Decimal
    end: Decimal
    cap: Decimal | None = None


def close_at(series: Sequence[tuple[date, Decimal]], day: date, tolerance: int) -> Decimal | None:
    """The last close on or before `day`, at most `tolerance` days before it."""
    best = None
    for d, c in series:
        if d > day:
            break
        if (day - d).days <= tolerance:
            best = c
    return best


def jumpy(series: Sequence[tuple[date, Decimal]], start: date, end: date, max_step: Decimal) -> bool:
    """Whether any step inside (start, end] rose more than max_step (a corporate action, not a move)."""
    prev = None
    for d, c in series:
        if d > end:
            break
        if prev is not None and d > start and prev > 0 and c / prev - 1 > max_step:
            return True
        prev = c
    return False


def _shares(r: FundamentalsRow) -> Decimal | None:
    """Diluted shares, else shares outstanding (India's filings give paid-up capital over face value, no diluted
    count: pipeline/india/results_xbrl.py)."""
    return r.diluted_shares or r.shares_outstanding


def shares_at(versions: Mapping[UUID, Sequence[FundamentalsRow]], cutoff: datetime) -> dict[UUID, Decimal]:
    """Each company's share count in the latest quarter filed before the cutoff (point in time)."""
    out: dict[UUID, Decimal] = {}
    for cid, rows in versions.items():
        known = [r for r in rows if r.filed_at < cutoff and _shares(r)]
        if known:
            last = max(known, key=lambda r: (r.period_end, r.filed_at))
            n = _shares(last)
            assert n is not None
            out[cid] = n
    return out


def _cutoff(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, tzinfo=UTC)


def year_winners(series: Series, versions: Mapping[UUID, Sequence[FundamentalsRow]], market: str, year: int,
                 top: int = TOP, skipped: dict[str, int] | None = None,
                 min_cap: Decimal | None = None) -> list[Pick]:  # fmt: skip
    """The year's `top` gainers among the names investable that year (MIN_PRICE at its start, MIN_CAP at its end);
    `skipped` counts why the others were left out."""
    start, end = date(year - 1, 12, 31), date(year, 12, 31)
    shares = shares_at(versions, _cutoff(end))
    step = MAX_STEP_US if market == "us" else MAX_STEP_IN
    floor = MIN_CAP[market] if min_cap is None else min_cap
    why = skipped if skipped is not None else {}
    out = []
    for cid, s in series.items():
        a, b = close_at(s, start, TOLERANCE_DAYS[market]), close_at(s, end, TOLERANCE_DAYS[market])
        reason = ("no price at the start" if a is None else "no price at the end" if b is None
                  else "under the price floor" if a < MIN_PRICE[market] else "no share count" if cid not in shares
                  else "under the size floor" if b * shares[cid] < floor
                  else "a jump read as a bad print" if jumpy(s, start, end, step) else None)  # fmt: skip
        if reason is not None:
            why[reason] = why.get(reason, 0) + 1
            continue
        assert a is not None and b is not None
        out.append(Pick(cid, float(b / a - 1), a, b, b * shares[cid]))
    return sorted(out, key=lambda p: p.ret, reverse=True)[:top]


LEADERS = 10


def ytd_leaders(series: Series, versions: Mapping[UUID, Sequence[FundamentalsRow]], market: str, year: int,
                through: date, top: int = LEADERS, min_cap: Decimal | None = None) -> list[Pick]:  # fmt: skip
    """This year's biggest gainers so far, by the same rules as a year's winners (MIN_PRICE when the year began,
    MIN_CAP at `through` from the shares filed by then, no bad print), through the date most names have a close."""
    start = date(year - 1, 12, 31)
    shares = shares_at(versions, _cutoff(through))
    step = MAX_STEP_US if market == "us" else MAX_STEP_IN
    out = []
    for cid, s in series.items():
        a, b = close_at(s, start, TOLERANCE_DAYS[market]), close_at(s, through, TOLERANCE_DAYS[market])
        if a is None or b is None or a < MIN_PRICE[market] or cid not in shares:
            continue
        if b * shares[cid] < (MIN_CAP[market] if min_cap is None else min_cap) or jumpy(s, start, through, step):
            continue
        out.append(Pick(cid, float(b / a - 1), a, b, b * shares[cid]))
    return sorted(out, key=lambda p: p.ret, reverse=True)[:top]


def year_return(s: Sequence[tuple[date, Decimal]], year: int, market: str, through: date | None = None) -> float | None:
    a = close_at(s, date(year - 1, 12, 31), TOLERANCE_DAYS[market])
    b = close_at(s, through or date(year, 12, 31), TOLERANCE_DAYS[market] if through is None else 40)
    return None if a is None or b is None or a <= 0 else float(b / a - 1)


def investable_at_start(series: Series, versions: Mapping[UUID, Sequence[FundamentalsRow]], market: str,
                        year: int, min_cap: Decimal | None = None) -> list[UUID]:  # fmt: skip
    start = date(year - 1, 12, 31)
    shares = shares_at(versions, _cutoff(start))
    floor = MIN_CAP[market] if min_cap is None else min_cap
    out = []
    for cid, s in series.items():
        a = close_at(s, start, TOLERANCE_DAYS[market])
        if a is not None and a >= MIN_PRICE[market] and cid in shares and a * shares[cid] >= floor:
            out.append(cid)
    return out


def backtest(series: Series, versions: Mapping[UUID, Sequence[FundamentalsRow]], market: str, first: int,
             last: int) -> list[dict[str, Any]]:  # fmt: skip
    """Each year from `first` to `last`: the previous year's top five (equal weight) against the average stock
    investable at the year's start, both over the stocks with a close at the year's end."""
    rows = []
    for year in range(first, last + 1):
        picks = year_winners(series, versions, market, year - 1)
        rets = [r for p in picks if (r := year_return(series[p.company_id], year, market)) is not None]
        pool = [r for cid in investable_at_start(series, versions, market, year)
                if (r := year_return(series[cid], year, market)) is not None]  # fmt: skip
        if len(rets) < 3 or len(pool) < 50:
            continue
        rows.append({"year": year, "picks": [str(p.company_id) for p in picks], "ret": fmean(rets),
                     "average": fmean(pool), "stocks": len(pool)})  # fmt: skip
    return rows


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Growth of 1 and the yearly rate for both, how many years the picks won, and their best and worst years."""
    if not rows:
        return None
    n = len(rows)
    picks = math.prod(1 + float(r["ret"]) for r in rows)
    avg = math.prod(1 + float(r["average"]) for r in rows)
    return {"years": n, "first": rows[0]["year"], "last": rows[-1]["year"], "growth": picks, "average_growth": avg,
            "cagr": picks ** (1 / n) - 1, "average_cagr": avg ** (1 / n) - 1,
            "beat": sum(1 for r in rows if r["ret"] > r["average"]),
            "worst": min(rows, key=lambda r: r["ret"])["year"],
            "best": max(rows, key=lambda r: r["ret"])["year"]}  # fmt: skip


# ---------------------------------------------------------------- the database


def us_series(conn: psycopg.Connection[Any], companies: Sequence[Company]) -> dict[UUID, list[tuple[date, Decimal]]]:
    stored = db_state.get(conn, LAB_ASSET)
    if stored is None:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "us_month_prices.csv.gz"
        path.write_bytes(stored.body)
        bars = read_prices(path, [c.ticker for c in companies if c.ticker])
    return {c.id: [(b.month_end, b.close) for b in bars[c.ticker]]
            for c in companies if c.id is not None and c.ticker in bars}  # fmt: skip


def india_series(
    conn: psycopg.Connection[Any], ids: Sequence[UUID], today: date
) -> dict[UUID, list[tuple[date, Decimal]]]:
    out: dict[UUID, list[tuple[date, Decimal]]] = {}
    for p in repo.prices(conn, ids, date(2000, 1, 1), today):
        out.setdefault(p.company_id, []).append((p.week_end, p.adj_close if p.adj_close is not None else p.close))
    return out


def versions_of(conn: psycopg.Connection[Any], ids: Sequence[UUID], today: date) -> dict[UUID, list[FundamentalsRow]]:
    out: dict[UUID, list[FundamentalsRow]] = {}
    for r in as_of(today).fundamental_versions(conn, list(ids)):
        out.setdefault(r.company_id, []).append(r)
    return out


def latest(s: Sequence[tuple[date, Decimal]]) -> tuple[date, Decimal] | None:
    return s[-1] if s else None


def market_report(market: str, companies: Mapping[UUID, Company], series: Series,
                  versions: Mapping[UUID, Sequence[FundamentalsRow]], today: date,
                  universe: int) -> dict[str, Any]:  # fmt: skip
    year = today.year - 1
    skipped: dict[str, int] = {}
    # every qualifier at the floor, best first: a slider step keeps those whose market cap today clears it
    picks = year_winners(series, versions, market, year, top=len(series), skipped=skipped)
    # this year so far: through the latest close most of the investable names have (month-ends for the US)
    pool = investable_at_start(series, versions, market, today.year)
    ends = sorted((last[0] for cid in pool if (last := latest(series[cid])) is not None and last[0].year == today.year),
                  reverse=True)  # fmt: skip
    through = ends[len(ends) * 4 // 5] if ends else None

    def ytd(cid: UUID) -> float | None:
        return None if through is None else year_return(series[cid], today.year, market, through)

    # market caps today: the latest close (within CAP_DAYS) times the shares of the latest quarter filed by today
    now_shares = shares_at(versions, _cutoff(today))
    caps: dict[UUID, Decimal] = {}
    for cid, s in series.items():
        last = latest(s)
        if last is not None and (today - last[0]).days <= CAP_DAYS and cid in now_shares:
            caps[cid] = last[1] * now_shares[cid]
    leaders_all = ytd_leaders(series, versions, market, today.year, through, top=len(series)) if through else []

    def above(cid: UUID, floor: Decimal) -> bool:
        """The floor step keeps the report's own rules; a higher step needs a market cap today above it."""
        return floor == MIN_CAP[market] or caps.get(cid, Decimal(0)) >= floor

    steps = CAP_STEPS[market]

    def bucket_of(cid: UUID) -> int:
        """Which step's bucket a company's market cap today falls in: [step i, step i+1), the last open-ended; one
        with no cap today (or under the second step) is in the floor's bucket, as the floor step keeps it."""
        cap = caps.get(cid)
        return 0 if cap is None else max(i for i, s in enumerate(steps) if i == 0 or cap >= s)

    def row(p: Pick, key: str) -> dict[str, Any]:
        c = companies[p.company_id]
        cap = caps.get(p.company_id)
        out = {"company_id": str(p.company_id), "code": c.ticker or c.nse_symbol, "name": c.name, "sector": c.sector,
               key: p.ret, "start": float(p.start), "end": float(p.end),
               "cap": float(cap) if cap is not None else None}  # fmt: skip
        if key == "ret":
            out["ytd"] = ytd(p.company_id)
        return out

    def band(floor: Decimal) -> dict[str, Any]:
        """Last year's five, this year's ten and the average stock, among companies above `floor`."""
        top = [row(p, "ret") for p in [p for p in picks if above(p.company_id, floor)][:TOP]]
        picks_ytd = [float(t["ytd"]) for t in top if t["ytd"] is not None]
        pool_ytd = [r for cid in pool if above(cid, floor) and (r := ytd(cid)) is not None]
        leaders = [row(p, "ytd") for p in [p for p in leaders_all if above(p.company_id, floor)][:LEADERS]]
        return {"min_cap": float(floor), "top": top, "leaders": leaders,
                "this_year": {"through": through.isoformat() if through else None,
                              "picks": fmean(picks_ytd) if picks_ytd else None,
                              "average": fmean(pool_ytd) if pool_ytd else None, "stocks": len(pool_ytd)}}  # fmt: skip

    def bucket(i: int) -> dict[str, Any]:
        """One bucket's own lists, so the screen can merge any range of buckets (2026-11-02: a min and a max): each
        bucket's best five and ten hold the best of any union of buckets; the average stock is a sum and a count."""
        mine = [p for p in picks if bucket_of(p.company_id) == i][:TOP]
        ytds = [r for cid in pool if bucket_of(cid) == i and (r := ytd(cid)) is not None]
        return {"min_cap": float(steps[i]), "max_cap": float(steps[i + 1]) if i + 1 < len(steps) else None,
                "top": [row(p, "ret") for p in mine],
                "leaders": [row(p, "ytd") for p in [p for p in leaders_all if bucket_of(p.company_id) == i][:LEADERS]],
                "ytd_sum": sum(ytds), "ytd_n": len(ytds)}  # fmt: skip

    floor = band(steps[0])
    buckets = [bucket(i) for i in range(len(steps))]
    rows = backtest(series, versions, market, 2012, year) if market == "us" else []
    return {"market": market, "year": year, "currency": CURRENCY[market], "priced": len(series), "universe": universe,
            "min_price": float(MIN_PRICE[market]), "min_cap": float(MIN_CAP[market]), "skipped": skipped,
            "top": floor["top"], "leaders": floor["leaders"], "this_year": floor["this_year"], "buckets": buckets,
            "cap_as_of": max((latest(series[c]) or (date.min, 0))[0] for c in caps).isoformat() if caps else None,
            "backtest": {"rows": rows, "summary": summary(rows)} if rows else None}  # fmt: skip


def build(conn: psycopg.Connection[Any], today: date) -> dict[str, Any]:
    out = []
    for market in ("us", "in"):
        companies = {c.id: c for c in repo.companies(conn, market=market, in_universe=True) if c.id is not None}
        ids = list(companies)
        series = us_series(conn, list(companies.values())) if market == "us" else india_series(conn, ids, today)
        series = {cid: s for cid, s in series.items() if cid in companies}
        versions = versions_of(conn, list(series), today)
        out.append(market_report(market, companies, series, versions, today, len(companies)))
    return {"markets": out, "as_of": today.isoformat()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=date.fromisoformat, default=None, help="the report's Friday (default: the last)")
    a = ap.parse_args(argv)
    today = datetime.now(UTC).date()
    week = a.week or last_friday(today)
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn:
        body = build(conn, today)
        repo.upsert_report(conn, "winners", week, body)
    for m in body["markets"]:
        bt = (m["backtest"] or {}).get("summary") if m["backtest"] else None
        left = ", ".join(f"{n} {why}" for why, n in sorted(m["skipped"].items(), key=lambda kv: -kv[1]))
        print(f"winners {m['market']} {m['year']}: {len(m['top'])} picks from {m['priced']} priced of {m['universe']}"
              + (f" (left out: {left})" if left else "")
              + (f"; backtest {bt['first']}-{bt['last']}: picks {bt['cagr']:.1%} a year vs average "
                 f"{bt['average_cagr']:.1%}, ahead in {bt['beat']} of {bt['years']} years" if bt else ""))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
