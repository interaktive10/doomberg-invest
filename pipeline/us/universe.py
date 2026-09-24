"""US universe seed (BRIEF §1.3, §8 M0-05).

M0 scope: the listed-filer seed from SEC `company_tickers_exchange.json` (cik, name, ticker, exchange), filtered to
NYSE/Nasdaq. The full rules (10-K/10-Q filers, SIC exclusions, 20-F exclusion, TTM revenue >= $50M) need
submissions.zip and companyfacts, and are applied in M2 by the same module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SEC_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


@dataclass(frozen=True)
class ListedFiler:
    cik: str  # zero-padded to 10 digits
    name: str
    tickers: tuple[str, ...]
    exchange: str


def parse_tickers_exchange(raw: bytes | str, exchanges: tuple[str, ...] = ("NYSE", "Nasdaq")) -> list[ListedFiler]:
    """One row per CIK listed on an allowed exchange; a CIK with several share classes keeps all its tickers."""
    doc = json.loads(raw)
    fields: list[str] = doc["fields"]
    idx = {f: fields.index(f) for f in ("cik", "name", "ticker", "exchange")}
    by_cik: dict[str, ListedFiler] = {}
    allowed = {e.lower() for e in exchanges}
    for row in doc["data"]:
        exch = row[idx["exchange"]]
        if not exch or str(exch).lower() not in allowed:
            continue
        cik = str(row[idx["cik"]]).zfill(10)
        ticker = str(row[idx["ticker"]]).upper()
        prev = by_cik.get(cik)
        if prev is None:
            by_cik[cik] = ListedFiler(cik, str(row[idx["name"]]), (ticker,), str(exch))
        elif ticker not in prev.tickers:
            by_cik[cik] = ListedFiler(cik, prev.name, (*prev.tickers, ticker), prev.exchange)
    return sorted(by_cik.values(), key=lambda f: f.cik)


def load_snapshot(path: Path) -> list[ListedFiler]:
    return parse_tickers_exchange(path.read_bytes())
