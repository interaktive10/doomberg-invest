"""Fiscal periods (Appendix F.4 step 6, V1-PERIOD): a fact's period_label resolved with the company's fiscal year
end (companies.fiscal_year_end, "MMDD" from the SEC submissions; India "0331").

Fiscal year N ends in calendar year N on the fiscal year-end day (FY2027 with a June year end: 2026-07-01 to
2027-06-30; a January year end: fiscal 2027 ends in January 2027). Quarters and halves are consecutive 3- and
6-month blocks from the fiscal year's start. Two-digit years are 20xx. An Indian year range names the year it ends
in (FY2025-26 = FY2026). Date labels resolve from their end date: "three months ended June 30, 2026", "year ended
December 31, 2025", and "as of June 30, 2026" (a point in time: start = end).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

_Y = r"'?(\d{4}(?:\s*[-\u2013/]\s*'?\d{2}(?:\d{2})?)?|\d{2})"  # 2027, '27, 27, or India's 2025-26 (-> 2026)
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
_QUARTER = [
    re.compile(rf"\bQ([1-4])\s*(?:FY|fiscal(?:\s+year)?)?\s*{_Y}\b", re.I),
    re.compile(rf"\b([1-4])Q\s*(?:FY)?\s*{_Y}\b", re.I),
    re.compile(
        rf"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+(?:fiscal\s+)?quarter\s+(?:of\s+)?"
        rf"(?:fiscal\s+(?:year\s+)?|FY\s*)?{_Y}\b",
        re.I,
    ),  # fmt: skip
]
_HALF = re.compile(
    rf"\b(?:H([12])|([12])H|(first|second)\s+half)\s*(?:of\s+)?(?:FY|fiscal(?:\s+year)?)?\s*{_Y}\b", re.I
)  # H1 FY26, 1H FY26, first half of fiscal 2026
_CALENDAR = re.compile(rf"\b(?:calendar(?:\s+year)?|CY)\s*{_Y}\b", re.I)
_FISCAL = re.compile(rf"\b(?:FY|fiscal(?:\s+year)?)\s*{_Y}\b", re.I)
_PLAIN_YEAR = re.compile(r"^\s*(?:(?:full|the)[- ]year\s+)?(\d{4})\s*$", re.I)
_NEXT_12 = re.compile(r"\bnext\s+(?:12|twelve)\s+months\b", re.I)
MONTHS = (
    {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
    | {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
    | {"sept": 9}
)
_DATE = r"(?:(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})|(?P<iso>\d{4}-\d{2}-\d{2}))"
SPAN_MONTHS = {"three": 3, "3": 3, "six": 6, "6": 6, "nine": 9, "9": 9, "twelve": 12, "12": 12, "quarter": 3,
               "half-year": 6, "half year": 6, "year": 12, "fiscal year": 12}  # fmt: skip
_ENDED = re.compile(
    rf"\b(?:(?P<n>three|six|nine|twelve|3|6|9|12)[- ]months?|(?P<unit>quarter|half[- ]year|fiscal\s+year|year))\s+"
    rf"(?:ended|ending)\s+{_DATE}",
    re.I,
)
_AS_OF = re.compile(rf"\b(?:as\s+(?:of|at)|at)\s+{_DATE}", re.I)


@dataclass(frozen=True)
class Period:
    start: date
    end: date


def _year(s: str) -> int | None:
    """2027, '27 and 27 -> 2027. An Indian range names the year it ends in (2025-26 -> 2026, 1999-2000 -> 2000); a
    range of more than one year ("2026-2028", a multi-year plan) is no single period: None (M5 review R2-F5)."""
    parts = re.split(r"\s*[-\u2013/]\s*", s.strip())
    if len(parts) == 2:
        first, last = int(parts[0].lstrip("'")), parts[1].lstrip("'")
        if len(last) == 4:
            end = int(last)
        else:
            end = first // 100 * 100 + int(last)
            end = end + 100 if end < first else end
        return end if end == first + 1 else None
    y = int(s.lstrip("'"))
    return 2000 + y if y < 100 else y


def _fy(s: str, fye: str | None) -> Period | None:
    y = _year(s)
    return None if y is None else fiscal_year(y, fye)


def _date(m: re.Match[str]) -> date | None:
    try:
        if m.group("iso"):
            return date.fromisoformat(m.group("iso"))
        month = MONTHS.get(m.group("mon").lower().rstrip("."))
        return None if month is None else date(int(m.group("year")), month, int(m.group("day")))
    except ValueError:
        return None


def _ending(end: date, months: int) -> Period:
    """`months` months ending on `end`: whole calendar months when `end` is a month end, else 52/53-week style
    (months x 30.44 days)."""
    if end == _month_end(end.year, end.month):
        return Period(_add_months(date(end.year, end.month, 1), -(months - 1)), end)
    return Period(end - timedelta(days=round(months * 30.4375)) + timedelta(days=1), end)


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def fiscal_year(fy: int, fye: str | None) -> Period:
    mm, dd = 12, 31
    if fye and len(fye) == 4 and fye.isdigit() and 1 <= int(fye[:2]) <= 12:
        mm, dd = int(fye[:2]), int(fye[2:])
    end = date(fy, mm, min(max(dd, 1), calendar.monthrange(fy, mm)[1]))
    prev = date(fy - 1, mm, min(max(dd, 1), calendar.monthrange(fy - 1, mm)[1]))
    return Period(prev + timedelta(days=1), end)


def _block(fy: Period, first_month: int, months: int) -> Period:
    start = _add_months(fy.start, first_month)
    end = _add_months(fy.start, first_month + months) - timedelta(days=1)
    if first_month + months == 12:
        end = fy.end
    return Period(start, end)


def resolve(label: str | None, fye: str | None, as_of: date | None = None) -> Period | None:
    """The period a label names, or None when it can't be resolved."""
    if not label:
        return None
    for pat in _QUARTER:
        m = pat.search(label)
        if m:
            q = ORDINAL.get(m.group(1).lower()) or int(m.group(1))
            fy = _fy(m.group(2), fye)
            return None if fy is None else _block(fy, 3 * (q - 1), 3)
    m = _ENDED.search(label)
    if m:
        end = _date(m)
        span = SPAN_MONTHS.get((m.group("n") or re.sub(r"\s+", " ", m.group("unit"))).lower().replace("-", " "))
        span = span or SPAN_MONTHS.get(re.sub(r"\s+", " ", m.group("unit") or "").lower())
        return None if end is None or span is None else _ending(end, span)
    m = _AS_OF.search(label)
    if m:
        end = _date(m)
        return None if end is None else Period(end, end)
    m = _HALF.search(label)
    if m:
        h = int(m.group(1) or m.group(2) or 0) or (1 if m.group(3).lower() == "first" else 2)
        fy = _fy(m.group(4), fye)
        return None if fy is None else _block(fy, 6 * (h - 1), 6)
    m = _CALENDAR.search(label)
    if m:
        if re.search(r"[-\u2013/]", m.group(1)):
            return None  # a calendar-year range is more than one year
        y = _year(m.group(1))
        return None if y is None else Period(date(y, 1, 1), date(y, 12, 31))
    m = _FISCAL.search(label) or _PLAIN_YEAR.match(label)
    if m:
        return _fy(m.group(1), fye)
    if _NEXT_12.search(label) and as_of is not None:
        return Period(as_of + timedelta(days=1), _add_months(as_of, 12))
    return None


def period_slug(p: Period, fye: str | None) -> str:
    """The <period> slot of capex_guidance/capex_reported keys: FY2027, or Q2FY2026 for a quarter."""
    for fy_year in (p.end.year, p.end.year + 1):
        fy = fiscal_year(fy_year, fye)
        if p == fy:
            return f"FY{fy_year}"
        for q in range(4):
            if p == _block(fy, 3 * q, 3):
                return f"Q{q + 1}FY{fy_year}"
        for h in range(2):
            if p == _block(fy, 6 * h, 6):
                return f"H{h + 1}FY{fy_year}"
    return f"{p.start:%Y%m%d}-{p.end:%Y%m%d}"
