"""NSE securities list (BRIEF §1.3, §4.3, §8 M0-05).

Parses EQUITY_L.csv ("Securities available for Equity segment"). Headers are matched by name after stripping
whitespace, because NSE pads some of them (" SERIES", " ISIN NUMBER"). SME companies are published in a separate
list, so this file is main-board only. ASM/GSM exclusion is applied in M3 from the surveillance lists.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
REQUIRED = ("SYMBOL", "NAME OF COMPANY", "SERIES", "ISIN NUMBER")


@dataclass(frozen=True)
class NseSecurity:
    symbol: str
    name: str
    series: str
    isin: str


class SchemaError(ValueError):
    pass


def parse_equity_list(raw: bytes | str, series: tuple[str, ...] | None = ("EQ",)) -> list[NseSecurity]:
    """Rows of EQUITY_L.csv in the given series (None = every series)."""
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    reader = csv.reader(io.StringIO(text))
    header = [h.strip().upper() for h in next(reader)]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise SchemaError(f"EQUITY_L.csv missing columns: {missing}")
    ix = {c: header.index(c) for c in REQUIRED}
    keep = None if series is None else {s.upper() for s in series}
    out: list[NseSecurity] = []
    for row in reader:
        if len(row) < len(header):
            continue
        s = row[ix["SERIES"]].strip().upper()
        if keep is None or s in keep:
            out.append(
                NseSecurity(
                    row[ix["SYMBOL"]].strip(), row[ix["NAME OF COMPANY"]].strip(), s, row[ix["ISIN NUMBER"]].strip()
                )
            )
    return out


def load_snapshot(path: Path) -> list[NseSecurity]:
    return parse_equity_list(path.read_bytes())
