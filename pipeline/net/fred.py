"""FRED's public monthly series (St. Louis Fed; docs/SPEC_ISSUES.md 68). With FRED_API_KEY (free, no card) through
FRED's API; without it, the fredgraph CSV, which FRED rate-limits unpredictably (on 2026-11-01 half the series answered
404 from a plain client and a browser User-Agent stalled). Daily and weekly series are averaged per calendar month;
FRED's "." (no value) is skipped. MOCK_EXTERNALS serves registered fixtures (fixtures/fred/<ID>.csv)."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import date

from pipeline.net.http import HttpClient

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
API = "https://api.stlouisfed.org/fred/series/observations?series_id={id}&api_key={key}&file_type=json"

Points = list[tuple[date, float]]


def parse(text: str) -> Points:
    """The CSV -> (month start, value) per month, oldest first; several values in a month are averaged."""
    months: dict[date, list[float]] = defaultdict(list)
    rows = csv.reader(io.StringIO(text))
    next(rows, None)  # header: observation_date,<ID>
    for row in rows:
        if len(row) < 2 or not row[1].strip() or row[1].strip() == ".":
            continue
        try:
            d, v = date.fromisoformat(row[0][:10]), float(row[1])
        except ValueError:
            continue
        months[date(d.year, d.month, 1)].append(v)
    return [(m, sum(vs) / len(vs)) for m, vs in sorted(months.items())]


def parse_api(body: bytes) -> Points:
    """The API's JSON (observations: [{date, value}]) -> the same monthly points as parse()."""
    rows = json.loads(body).get("observations") or []
    return parse("observation_date,x\n" + "".join(f"{o.get('date')},{o.get('value')}\n" for o in rows))


def series(http: HttpClient, series_id: str, timeout: float = 20.0, api_key: str | None = None) -> Points:
    if api_key:
        return parse_api(http.get_bytes(API.format(id=series_id, key=api_key), timeout=timeout))
    return parse(http.get_bytes(URL.format(id=series_id), timeout=timeout).decode("utf-8", errors="replace"))
