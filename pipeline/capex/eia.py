"""EIA planned generator additions (BRIEF §2.7 "EIA (free key; generator additions for the capex desk)", §4.11).

API v2 route electricity/operating-generator-capacity (monthly EIA-860M inventory), filtered to planned units (status
P, L, T, U, V, TS: from "planned, approvals not initiated" to "construction complete, not yet operating"), summing
nameplate MW per report month: the size of the planned pipeline each month. The key goes in the query string, as the
API requires; error messages never include the URL (so the key can't reach logs or the runs table).

The response shape follows EIA's v2 documentation: {"response": {"total": N, "data": [{"period": "YYYY-MM",
"status": "...", "technology": "...", "nameplate-capacity-mw": "..."}]}}. The build container can't reach
api.eia.gov, so fixtures/eia/ holds that documented shape, not a recording (docs/SPEC_ISSUES.md).
"""

from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx

from pipeline.net.http import HttpClient

API = "https://api.eia.gov/v2/electricity/operating-generator-capacity/data/"
PLANNED = ("P", "L", "T", "U", "V", "TS")
PAGE = 5000
MAX_PAGES = 40


class EiaError(Exception):
    """The EIA request or response failed (message without the URL)."""


def url(key: str, start: str, end: str, offset: int = 0) -> str:
    params: list[tuple[str, str]] = [("api_key", key), ("frequency", "monthly"), ("data[0]", "nameplate-capacity-mw")]
    params += [("facets[status][]", s) for s in PLANNED]
    params += [("start", start), ("end", end), ("sort[0][column]", "period"), ("sort[0][direction]", "asc"),
               ("offset", str(offset)), ("length", str(PAGE))]  # fmt: skip
    return f"{API}?{urlencode(params)}"


def month_end(period: str) -> date:
    y, m = (int(x) for x in period.split("-")[:2])
    return date(y, m, calendar.monthrange(y, m)[1])


def parse(raw: bytes) -> tuple[dict[date, Decimal], int, int]:
    """(month end -> planned MW on this page, total rows, rows on this page)."""
    try:
        doc = json.loads(raw)["response"]
        rows = doc["data"]
        total = int(doc.get("total") or len(rows))
    except (ValueError, KeyError, TypeError) as e:
        raise EiaError(f"unexpected EIA response ({type(e).__name__})") from e
    out: dict[date, Decimal] = defaultdict(Decimal)
    for r in rows:
        try:
            mw = Decimal(str(r.get("nameplate-capacity-mw") or "0"))
            out[month_end(str(r["period"]))] += mw
        except (InvalidOperation, KeyError, ValueError):
            continue
    return dict(out), total, len(rows)


def planned_additions(http: HttpClient, key: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    """Monthly planned-capacity totals (MW), oldest first."""
    months: dict[date, Decimal] = defaultdict(Decimal)
    seen = 0
    for page in range(MAX_PAGES):
        try:
            raw = http.get_bytes(url(key, f"{start:%Y-%m}", f"{end:%Y-%m}", page * PAGE))
        except httpx.HTTPError as e:
            status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else type(e).__name__
            raise EiaError(f"EIA request failed ({status})") from None
        got, total, n = parse(raw)
        for d, v in got.items():
            months[d] += v
        seen += n
        if n == 0 or seen >= total:
            break
    return sorted(months.items())
