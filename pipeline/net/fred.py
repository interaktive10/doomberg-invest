"""FRED's public monthly series (St. Louis Fed; free, no key): the fredgraph CSV, one series per request
(docs/SPEC_ISSUES.md 68). Daily and weekly series are averaged per calendar month; FRED's "." (no value) is skipped.
MOCK_EXTERNALS serves registered fixtures (fixtures/fred/<ID>.csv; tests register them)."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date

from pipeline.net.http import HttpClient

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"

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


def series(http: HttpClient, series_id: str, timeout: float = 20.0) -> Points:
    return parse(http.get_bytes(URL.format(id=series_id), timeout=timeout).decode("utf-8", errors="replace"))
