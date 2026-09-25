"""Quarterize SEC facts into point-in-time rows for fundamentals_q (BRIEF §4.1.3-§4.1.5).

- Flows: a ~3-month value is the quarter; otherwise YTD values are differenced; Q4 = FY - Q1 - Q2 - Q3 when all
  exist. |Q4 derived| > 3 x mean(|Q1|, |Q2|, |Q3|) -> flagged, left null, reason logged.
- Diluted shares are a weighted average, not additive: quarters come from 3-month values; Q4 is derived as
  4 x FY - (Q1 + Q2 + Q3) (the FY average is the mean of the four quarterly averages), with the same 3x check,
  and only when Q1-Q3 are each within 0.5-2x of FY: after a split, later filings restate some periods but not
  others, and mixing bases gives a plausible-looking wrong number (NVDA FY2024 Q4: 47.3B instead of ~24.9B).
- Instants (balance sheet) are taken as reported at the quarter end. Cover-page shares are keyed by the filing's
  report period, because they are dated after it.
- Sanity: revenue >= 0 and shares > 0, else null + reason.

Point in time: every fact carries its filing's acceptance time. Rows are rebuilt at each acceptance time using only
facts accepted by then, and a quarter gets a new row (with that filed_at) whenever any of its values changes. A
restatement is therefore a new row with a later filed_at; the old row stays. The fiscal calendar (quarter end dates)
is derived from all filings: dates, never values, so it cannot leak a number into the past.
Vintages: a derived value (YTD difference, Q4) is recomputed only when the larger period's value comes from a filing
at least as recent as every value subtracted from it; while a later filing has restated a subtracted quarter but
not yet the year, the last consistent value is kept (and the reason logged).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from pipeline.us.companyfacts import ANNUAL_FORMS, COLUMN_KIND, Fact, Kind

QUARTER_DAYS = (80, 100)
HALF_DAYS = (170, 200)
NINE_DAYS = (260, 290)
YEAR_DAYS = (350, 380)
Q4_MAX_MULTIPLE = Decimal(3)

Key = tuple[str, date, date]  # ("D", start, end) | ("I", end, end) | ("C", report_end, report_end)
Timed = tuple[Decimal, datetime]  # a value and the acceptance time of the filing(s) it came from
QuarterEnds = tuple[date | None, date | None, date | None, date | None]


def _in(days: int | None, band: tuple[int, int]) -> bool:
    return days is not None and band[0] <= days <= band[1]


@dataclass(frozen=True)
class FiscalYear:
    start: date
    end: date | None  # None while the year is in progress
    quarter_ends: QuarterEnds

    def quarter_start(self, k: int) -> date | None:
        """Start of quarter k (1..4)."""
        if k == 1:
            return self.start
        prev = self.quarter_ends[k - 2]
        return prev + timedelta(days=1) if prev else None

    def contains(self, d: date) -> bool:
        return self.start <= d and (self.end is None or d <= self.end)


@dataclass(frozen=True)
class QuarterRow:
    period_end: date
    fiscal_label: str
    filed_at: datetime
    values: dict[str, Decimal | None]


@dataclass(frozen=True)
class Issue:
    period_end: date
    column: str
    reason: str


def _quarter_ends(start: date, end: date | None, durations: set[tuple[date, date]]) -> QuarterEnds:
    """e1..e4 for a fiscal year starting at `start`: from YTD periods starting at `start`, else by chaining
    3-month periods. e4 is the year end (None while the year is open)."""
    ytd: dict[int, date] = {}
    for d_start, d_end in durations:
        if d_start != start:
            continue
        days = (d_end - d_start).days
        for k, band in ((1, QUARTER_DAYS), (2, HALF_DAYS), (3, NINE_DAYS)):
            if _in(days, band):
                ytd.setdefault(k, d_end)
    ends: list[date | None] = []
    cur: date | None = start
    for k in (1, 2, 3):
        e: date | None = ytd.get(k)
        if e is None and cur is not None:
            chained = sorted(e2 for s2, e2 in durations if s2 == cur and _in((e2 - s2).days, QUARTER_DAYS))
            e = chained[0] if chained else None
        if e is not None and end is not None and e > end:
            e = None  # outside a closed year (bad data)
        ends.append(e)
        cur = e + timedelta(days=1) if e else None
    return (ends[0], ends[1], ends[2], end)


def fiscal_years(facts: Sequence[Fact]) -> list[FiscalYear]:
    """Fiscal years from annual 10-K durations; the year after the last one is open (in progress)."""
    durations = {(f.start, f.end) for f in facts if f.start is not None}
    by_end: dict[date, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for f in facts:
        if f.start is not None and f.form in ANNUAL_FORMS and _in(f.days, YEAR_DAYS):
            by_end[f.end][f.start] += 1
    years: list[tuple[date, date]] = []
    for end in sorted(by_end):
        start = max(by_end[end].items(), key=lambda kv: (kv[1], kv[0]))[0]  # most reported start for this end
        if years and start <= years[-1][1]:
            continue  # overlaps the previous year (restated calendar or a stray 12-month period)
        years.append((start, end))
    out = [FiscalYear(s, e, _quarter_ends(s, e, durations)) for s, e in years]
    if years:
        nxt = years[-1][1] + timedelta(days=1)
        if any(s == nxt for s, _ in durations):
            out.append(FiscalYear(nxt, None, _quarter_ends(nxt, None, durations)))
    else:  # no 10-K yet (new registrant): anchor on the earliest 3-month period
        starts = sorted(s for s, e in durations if _in((e - s).days, QUARTER_DAYS))
        if starts:
            out.append(FiscalYear(starts[0], None, _quarter_ends(starts[0], None, durations)))
    return out


def _sig_digits(v: Decimal) -> int:
    """Significant digits of an integer value (trailing zeros don't count)."""
    return len(str(abs(int(v))).rstrip("0"))


def rounding_equal(a: Decimal, b: Decimal) -> bool:
    """True when the coarser value is exactly the finer one rounded to the coarser value's precision, e.g.
    105,100,000,000 (a footnote's "$105.1 billion") vs 105,103,000,000 (the balance sheet), or 29,000,000 vs
    29,068,000 after a filer moves its tables from thousands to millions. The coarser value needs >= 2
    significant digits; values with the same precision are only equal when identical."""
    if a == b:
        return True
    if a == 0 or b == 0 or (a < 0) != (b < 0):
        return False
    coarse, fine = (a, b) if _trailing_zeros(a) >= _trailing_zeros(b) else (b, a)
    tz = _trailing_zeros(coarse)
    if tz == 0 or tz == _trailing_zeros(fine) or _sig_digits(coarse) < 2:
        return False
    unit = Decimal(10) ** tz
    return (fine / unit).quantize(Decimal(1), rounding="ROUND_HALF_UP") * unit == coarse


def _trailing_zeros(v: Decimal) -> int:
    if v != v.to_integral_value():
        return 0
    s = str(abs(int(v)))
    return len(s) - len(s.rstrip("0")) if s != "0" else 0


class _State:
    """Latest value per (column, key, alternative, part) as of the facts applied so far, with the acceptance time
    of the filing it came from. The effective value is the lowest-ranked alternative whose required part (0) is
    present, summed over its parts; its time is the latest of those parts'. A later value that only differs by
    rounding keeps the more precise of the two and the earlier time (not a restatement)."""

    def __init__(self) -> None:
        self._by: dict[tuple[str, Key], dict[tuple[int, int], tuple[Decimal, datetime]]] = {}

    def apply(self, column: str, key: Key, rank: int, part: int, val: Decimal, t: datetime) -> None:
        parts = self._by.setdefault((column, key), {})
        old = parts.get((rank, part))
        if old is not None and rounding_equal(old[0], val):
            val, t = (old[0] if _trailing_zeros(old[0]) <= _trailing_zeros(val) else val), old[1]
        parts[(rank, part)] = (val, t)

    def get_t(self, column: str, key: Key) -> Timed | None:
        parts = self._by.get((column, key))
        if not parts:
            return None
        ranks = [r for r, p in parts if p == 0]
        if not ranks:
            return None
        best = min(ranks)
        chosen = [vt for (r, _), vt in parts.items() if r == best]
        return sum((v for v, _ in chosen), Decimal(0)), max(t for _, t in chosen)

    def get(self, column: str, key: Key) -> Decimal | None:
        vt = self.get_t(column, key)
        return None if vt is None else vt[0]


def _key(f: Fact, report_end: Mapping[str, date]) -> Key | None:
    kind = COLUMN_KIND[f.column]
    if kind is Kind.COVER:
        rep = report_end.get(f.accn)
        return ("C", rep, rep) if rep else None
    if f.start is None:
        return ("I", f.end, f.end) if kind is Kind.INSTANT else None
    return ("D", f.start, f.end) if kind in (Kind.FLOW, Kind.AVERAGE) else None


def _q4_check(q4: Decimal, q: list[Decimal]) -> bool:
    mean_abs = sum(abs(x) for x in q) / Decimal(3)
    return abs(q4) <= Q4_MAX_MULTIPLE * mean_abs


def _consistent(minuend: Timed, subtrahends: Sequence[Timed]) -> bool:
    """A derived value (YTD difference, Q4 = FY - Q1..Q3) is only computed when the larger period comes from a
    filing at least as recent as every value subtracted from it. Otherwise a restated quarter would be subtracted
    from an unrestated year, giving a number no filing reported (review F3)."""
    return all(minuend[1] >= t for _, t in subtrahends)


MIXED = "inputs from different vintages (a later filing restated a subtracted period); kept the last consistent value"


def _year_values(
    st: _State,
    fy: FiscalYear,
    columns: Sequence[str],
    issues: set[Issue],
    last: Mapping[date, Mapping[str, Decimal | None]],
) -> dict[date, dict[str, Decimal | None]]:
    out: dict[date, dict[str, Decimal | None]] = {}
    ends = fy.quarter_ends
    for k in range(1, 5):
        e = ends[k - 1]
        if e is not None:
            out[e] = {}

    def keep(e: date, c: str) -> Decimal | None:
        issues.add(Issue(e, c, MIXED))
        return last.get(e, {}).get(c)

    for c in columns:
        kind = COLUMN_KIND[c]
        if kind in (Kind.INSTANT, Kind.COVER):
            tag = "I" if kind is Kind.INSTANT else "C"
            for e in out:
                out[e][c] = st.get(c, (tag, e, e))
            continue
        q: dict[int, Timed | None] = {}
        for k in (1, 2, 3):
            e, s = ends[k - 1], fy.quarter_start(k)
            if e is None or s is None:
                q[k] = None
                continue
            direct = st.get_t(c, ("D", s, e))
            if direct is None and kind is Kind.FLOW and k > 1:
                ytd = st.get_t(c, ("D", fy.start, e))
                prev: Timed | None = None
                pe = ends[k - 2]
                subtrahends: list[Timed] = []
                if pe is not None:
                    prev = st.get_t(c, ("D", fy.start, pe)) if k > 2 else q.get(1)
                    subtrahends = [prev] if prev is not None else []
                if prev is None:
                    known = [q.get(j) for j in range(1, k)]
                    if all(v is not None for v in known):
                        subtrahends = [v for v in known if v is not None]
                        prev = (sum((v for v, _ in subtrahends), Decimal(0)), max(t for _, t in subtrahends))
                if ytd is not None and prev is not None:
                    if _consistent(ytd, subtrahends):
                        direct = (ytd[0] - prev[0], ytd[1])
                    else:
                        kept = keep(e, c)
                        direct = None if kept is None else (kept, ytd[1])
            q[k] = direct
            out[e][c] = None if direct is None else direct[0]
        e4, s4 = ends[3], fy.quarter_start(4)
        if e4 is None or s4 is None:
            continue
        direct4 = st.get(c, ("D", s4, e4))
        if direct4 is not None:
            out[e4][c] = direct4
            continue
        annual = st.get_t(c, ("D", fy.start, e4))
        q123 = [q.get(1), q.get(2), q.get(3)]
        if annual is None or any(v is None for v in q123):
            out[e4][c] = None
            continue
        timed: list[Timed] = [v for v in q123 if v is not None]
        parts = [v for v, _ in timed]
        if not _consistent(annual, timed):
            out[e4][c] = keep(e4, c)
            continue
        if kind is Kind.AVERAGE and not all(annual[0] / 2 <= v <= annual[0] * 2 for v in parts):
            out[e4][c] = None  # a split restated some periods but not others: the bases don't match
            issues.add(Issue(e4, c, "Q1-Q3 and FY share counts are on different bases (split?); Q4 left null"))
            continue
        q4 = annual[0] - sum(parts) if kind is Kind.FLOW else Decimal(4) * annual[0] - sum(parts)
        if _q4_check(q4, parts):
            out[e4][c] = q4
        else:
            out[e4][c] = None
            issues.add(Issue(e4, c, f"derived Q4 {q4} is more than 3x the Q1-Q3 mean; left null"))
    for e, vals in out.items():
        rev = vals.get("revenue")
        if rev is not None and rev < 0:
            vals["revenue"] = None
            issues.add(Issue(e, "revenue", f"negative revenue {rev}; left null"))
        for c in ("diluted_shares", "shares_outstanding"):
            v = vals.get(c)
            if v is not None and v <= 0:
                vals[c] = None
                issues.add(Issue(e, c, f"non-positive shares {v}; left null"))
    return out


def year_labels(years: Sequence[FiscalYear], facts: Sequence[Fact], report_end: Mapping[str, date]) -> list[int]:
    """Fiscal-year number for each year: anchored on the latest 10-K's own `fy` (the most common one among its
    facts), then counted along the calendar. SEC's `fy` tags are sometimes wrong on individual 10-Qs (ORCL tagged
    Q1 FY2027 as fy 2026), so they are not trusted quarter by quarter."""
    votes: dict[date, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for f in facts:
        rep = report_end.get(f.accn)
        if rep is not None and f.form in ANNUAL_FORMS and f.fp == "FY" and f.fy is not None:
            votes[rep][f.fy] += 1
    ends = [fy.end or (fy.start + timedelta(days=364)) for fy in years]
    anchor = next((i for i in range(len(years) - 1, -1, -1) if years[i].end in votes), None)
    if anchor is None:
        return [e.year for e in ends]
    anchor_year = max(votes[ends[anchor]].items(), key=lambda kv: kv[1])[0]
    return [anchor_year + round((e - ends[anchor]).days / 365.25) for e in ends]


def quarterize(
    facts: Sequence[Fact],
    report_end: Mapping[str, date],
    columns: Sequence[str] | None = None,
) -> tuple[list[QuarterRow], list[Issue]]:
    """Point-in-time quarter rows. `report_end` maps accession -> the filing's report period end (submissions)."""
    cols = list(columns or COLUMN_KIND)
    years = fiscal_years(facts)
    labels = year_labels(years, facts, report_end)
    by_time: dict[datetime, list[Fact]] = defaultdict(list)
    for f in facts:
        by_time[f.filed_at].append(f)
    st = _State()
    last: dict[date, dict[str, Decimal | None]] = {}
    rows: list[QuarterRow] = []
    issues: set[Issue] = set()
    for t in sorted(by_time):
        touched: set[int] = set()
        for f in sorted(by_time[t], key=lambda x: (x.accn, x.rank, x.part)):
            key = _key(f, report_end)
            if key is None:
                continue
            st.apply(f.column, key, f.rank, f.part, f.val, f.filed_at)
            touched.update(i for i, fy in enumerate(years) if fy.contains(key[2]))
        for i in sorted(touched):
            fy = years[i]
            for e, vals in sorted(_year_values(st, fy, cols, issues, last).items()):
                if all(v is None for v in vals.values()) or last.get(e) == vals:
                    continue
                last[e] = vals
                n = next(k for k, q in enumerate(fy.quarter_ends, 1) if q == e)
                rows.append(QuarterRow(e, f"FY{labels[i]}Q{n}", t, dict(vals)))
    rows.sort(key=lambda r: (r.period_end, r.filed_at))
    return rows, sorted(issues, key=lambda i: (i.period_end, i.column))


def ttm_revenue(rows: Sequence[QuarterRow]) -> tuple[Decimal | None, bool]:
    """TTM revenue for the universe rule (§1.3 "TTM revenue ≥ $50M"), from the latest version of each quarter: the
    sum of the last 4 quarters. With fewer known quarters in the last 12 months (a spin-off, an IPO, or a quarter
    left null by a sanity check), the sum of the known ones, flagged by the bool: revenue is never negative, so it is
    a lower bound, and a company it clears certainly passes. Otherwise a new registrant stays out until its fourth
    quarter (review F5: GE Vernova for ~10 months of S10's 18-month window). Signals compute their own TTM (M4)."""
    latest = {r.period_end: r for r in rows}
    if not latest:
        return None, False
    ends = sorted(latest)
    last4 = ends[-4:]
    vals = [latest[e].values.get("revenue") for e in last4]
    if len(last4) == 4 and all(v is not None for v in vals) and (last4[-1] - last4[0]).days <= 300:
        return sum((v for v in vals if v is not None), Decimal(0)), False
    recent = [latest[e].values.get("revenue") for e in ends if (ends[-1] - e).days < 300]
    known = [v for v in recent if v is not None]
    if not known or len(known) >= 4:
        return None, False
    return sum(known, Decimal(0)), True
