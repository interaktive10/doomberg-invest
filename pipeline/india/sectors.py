"""Indian companies' sectors (docs/SPEC_ISSUES.md 68): NSE's index constituent lists carry an Industry column (the
Nifty Total Market's 750 names and the Microcap 250), which the India universe never stored, so no Indian company could
belong to a theme. Matched by ISIN, else symbol, written to companies.sector where it differs. Two requests a run.

`python -m pipeline.india.sectors`."""

from __future__ import annotations

import csv
import io
import sys
from collections.abc import Mapping
from typing import Any

import psycopg

from pipeline.db import repo
from pipeline.net.http import HttpClient
from pipeline.settings import Settings

LISTS = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
)


def parse(text: str) -> dict[str, tuple[str, str]]:
    """ISIN -> (symbol, industry) from one list (Company Name,Industry,Symbol,Series,ISIN Code)."""
    out = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        isin = (row.get("ISIN Code") or "").strip()
        sym = (row.get("Symbol") or "").strip()
        ind = (row.get("Industry") or "").strip()
        if ind and (isin or sym):
            out[isin or f"sym:{sym}"] = (sym, ind)
    return out


def sectors(conn: psycopg.Connection[Any], lists: Mapping[str, tuple[str, str]]) -> int:
    """Set each Indian company's sector from the lists; returns how many changed."""
    by_symbol = {sym: ind for sym, ind in lists.values() if sym}
    changes = {}
    for c in repo.companies(conn, market="in"):
        ind = (lists.get(c.isin or "") or (None, None))[1] or by_symbol.get(c.nse_symbol or "")
        if ind and ind != c.sector and c.id is not None:
            changes[c.id] = ind
    repo.set_sectors(conn, changes)
    return len(changes)


def main() -> int:
    settings = Settings.from_env()
    http = HttpClient(settings)
    lists: dict[str, tuple[str, str]] = {}
    for url in LISTS:
        lists.update(parse(http.get_bytes(url).decode("utf-8", errors="replace")))
    with psycopg.connect(settings.database_url) as conn:
        n = sectors(conn, lists)
    print(f"india sectors: {len(lists)} listed, {n} companies updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
