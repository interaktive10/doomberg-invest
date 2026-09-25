"""Manual CSV imports: the last fallback when NSE and BSE are both unavailable (BRIEF §4.3 "Access rules").

Manzoor downloads CSVs with the NSE pages' own "Download (.csv)" buttons and adds them through the web upload screen,
which commits them under `imports/` (M7). The pipeline reads every CSV there; the kind is recognised by its header:
- `bhavcopy`: the CM-UDiFF common bhavcopy (TradDt, ISIN, TckrSymb, SctySrs, ClsPric, …), NSE or BSE;
- `bhavdata_full`: NSE's "security-wise full bhavcopy" (SYMBOL, SERIES, DATE1, CLOSE_PRICE, TTL_TRD_QNTY, …).
Anything else is reported and skipped. (The insider-trading page's CSV is only an index of links to each
disclosure's XBRL, so it can't replace the network; results and shareholding XBRL are catch-up work for the next
run, not a manual import.) Imports are idempotent: the same file gives the same rows, and the writers
upsert, so a file can stay in imports/ after it was used.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline.india import bhavcopy
from pipeline.india.bhavcopy import BhavRow
from pipeline.settings import REPO_ROOT

IMPORTS_DIR = REPO_ROOT / "imports"
FULL_BHAV_REQUIRED = ("SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE")


def _norm(h: str) -> str:
    return " ".join(h.replace("﻿", "").split()).upper()


def detect(header: list[str]) -> str:
    cols = {_norm(h) for h in header}
    if {"TRADDT", "ISIN", "TCKRSYMB", "CLSPRIC"} <= cols:
        return "bhavcopy"
    if set(FULL_BHAV_REQUIRED) <= cols:
        return "bhavdata_full"
    return "unknown"


@dataclass
class Imported:
    path: Path
    kind: str
    prices: list[BhavRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _decimal(s: str | None) -> Decimal | None:
    s = (s or "").strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_bhavdata_full(text: str, series: tuple[str, ...] = ("EQ",)) -> list[BhavRow]:
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [_norm(h) for h in (reader.fieldnames or [])]
    out: list[BhavRow] = []
    for r in reader:
        row = {k: (v or "").strip() for k, v in r.items() if k}
        close = _decimal(row.get("CLOSE_PRICE"))
        if row.get("SERIES", "").upper() not in series or close is None or close <= 0:
            continue
        vol = _decimal(row.get("TTL_TRD_QNTY"))
        out.append(
            BhavRow(
                trade_date=datetime.strptime(row["DATE1"], "%d-%b-%Y").date(),
                source="NSE",
                symbol=row["SYMBOL"].upper(),
                isin="",  # this format has no ISIN: matched by symbol
                series=row["SERIES"].upper(),
                close=close,
                volume=int(vol) if vol is not None else None,
                name="",
            )
        )
    return out


def import_file(path: Path) -> Imported:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    header = next(csv.reader(io.StringIO(text)), [])
    kind = detect(header)
    out = Imported(path, kind)
    if kind == "bhavcopy":
        parsed = bhavcopy.parse(raw, series=None)
        if parsed.source == "NSE":  # NSE files carry series: keep EQ; BSE files carry groups, matched by ISIN
            parsed = bhavcopy.parse(raw)
        out.prices, out.warnings = parsed.rows, parsed.warnings
    elif kind == "bhavdata_full":
        out.prices = parse_bhavdata_full(text)
    else:
        out.warnings.append(f"{path.name}: unrecognised CSV (header {header[:6]}); skipped")
    return out


def import_dir(directory: Path = IMPORTS_DIR) -> list[Imported]:
    if not directory.is_dir():
        return []
    return [import_file(p) for p in sorted(directory.iterdir()) if p.suffix.lower() == ".csv" and p.is_file()]
