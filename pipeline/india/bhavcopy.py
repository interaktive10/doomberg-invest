"""CM-UDiFF common bhavcopy (BRIEF §4.3, §4.4, §8 M3-01): NSE's daily equity file, and BSE's in the same format.

Parsed by column name (TradDt, ISIN, TckrSymb, SctySrs, ClsPric, TtlTradgVol, …), never by position. Unknown columns
are reported as warnings; a missing required column raises BhavcopySchemaError. Rows are kept by the session/series
rules: the final session (SsnId F1) and, on NSE, series EQ. BSE files carry BSE group codes (A, B, X, …) instead of
NSE series, so BSE rows are matched to the NSE-listed universe by ISIN.

NSE:  https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
BSE:  https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from pipeline.net.bse import BseUnavailable, bhavcopy_url
from pipeline.net.nse import NseBlocked

if TYPE_CHECKING:
    from pipeline.net.bse import BseClient
    from pipeline.net.nse import NseClient

KNOWN_COLUMNS = (
    "TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "ISIN", "TckrSymb", "SctySrs", "XpryDt",
    "FininstrmActlXpryDt", "StrkPric", "OptnTp", "FinInstrmNm", "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
    "PrvsClsgPric", "UndrlygPric", "SttlmPric", "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd", "SsnId", "NewBrdLotQty", "Rmks", "Rsvd1", "Rsvd2", "Rsvd3", "Rsvd4",
)  # fmt: skip
REQUIRED = ("TradDt", "ISIN", "TckrSymb", "SctySrs", "ClsPric", "TtlTradgVol")
FINAL_SESSION = "F1"


class BhavcopySchemaError(ValueError):
    pass


@dataclass(frozen=True)
class BhavRow:
    trade_date: date
    source: str  # NSE | BSE
    symbol: str
    isin: str
    series: str
    close: Decimal
    volume: int | None
    name: str
    turnover: Decimal | None = None  # traded value (INR): a size/liquidity order for the results backfill


@dataclass
class Bhavcopy:
    source: str
    trade_date: date | None
    rows: list[BhavRow]
    warnings: list[str] = field(default_factory=list)
    skipped: int = 0


def nse_url(d: date) -> str:
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


def looks_like_bhavcopy(raw: bytes) -> bool:
    """BSE answers a missing file with its HTML home page (status 200); a real file starts with the UDiFF header
    (or is a zip)."""
    head = raw[:200].lstrip(b"\xef\xbb\xbf").lstrip()
    return head.startswith(b"PK") or head.startswith(b"TradDt")


def _text(raw: bytes) -> str:
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            raw = z.read(name)
    return raw.decode("utf-8-sig", errors="replace")


def _decimal(s: str | None) -> Decimal | None:
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse(raw: bytes, series: tuple[str, ...] | None = ("EQ",)) -> Bhavcopy:
    """Parse one UDiFF file (zip or csv). `series` filters NSE series; None keeps every row (BSE)."""
    reader = csv.DictReader(io.StringIO(_text(raw)))
    header = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise BhavcopySchemaError(f"bhavcopy is missing required columns {missing} (header: {header[:12]}…)")
    unknown = [c for c in header if c not in KNOWN_COLUMNS]
    out = Bhavcopy(source="", trade_date=None, rows=[])
    if unknown:
        out.warnings.append(f"unknown columns ignored: {unknown}")
    keep = None if series is None else {s.upper() for s in series}
    for r in reader:
        src = (r.get("Src") or "").strip().upper()
        out.source = out.source or src
        session = (r.get("SsnId") or FINAL_SESSION).strip().upper()
        ser = (r.get("SctySrs") or "").strip().upper()
        close = _decimal(r.get("ClsPric"))
        if session != FINAL_SESSION or (keep is not None and ser not in keep) or close is None or close <= 0:
            out.skipped += 1
            continue
        vol = _decimal(r.get("TtlTradgVol"))
        d = date.fromisoformat((r.get("TradDt") or "").strip())
        out.trade_date = out.trade_date or d
        out.rows.append(
            BhavRow(
                trade_date=d,
                source=src,
                symbol=(r.get("TckrSymb") or "").strip().upper(),
                isin=(r.get("ISIN") or "").strip().upper(),
                series=ser,
                close=close,
                volume=int(vol) if vol is not None else None,
                name=(r.get("FinInstrmNm") or "").strip(),
                turnover=_decimal(r.get("TtlTrfVal")),
            )
        )
    return out


def week_days_back(friday: date, days: int = 5) -> list[date]:
    """The Friday, then earlier weekdays of the same week (holidays: use the last trading day, BRIEF §4.3)."""
    return [d for d in (friday - timedelta(days=n) for n in range(days)) if d.weekday() < 5]


def fetch_week(
    nse: NseClient, bse: BseClient, friday: date, imports: Path
) -> tuple[list[BhavRow], str, date | None, list[str]]:
    """The week's last trading-day closes: NSE, else BSE, else manual imports. BSE is asked first whether a day
    traded (it answers a missing file with its home page), because NSE answers a missing file with 403, the same
    as a block: asking NSE for a holiday would count towards stale."""
    notes: list[str] = []
    for day in week_days_back(friday):
        try:
            bse_raw: bytes | None = bse.get(bhavcopy_url(day), use_cache=True)
        except (BseUnavailable, httpx.HTTPError) as e:
            notes.append(f"BSE bhavcopy {day}: {type(e).__name__}")
            bse_raw = None
        bse_ok = bse_raw is not None and looks_like_bhavcopy(bse_raw)
        if bse_raw is not None and not bse_ok:
            continue  # no BSE file: a holiday, try the day before
        if not nse.stale:
            try:
                nse_raw = nse.get(nse_url(day), use_cache=True)
                if looks_like_bhavcopy(nse_raw):
                    return parse(nse_raw).rows, "NSE", day, notes
            except (NseBlocked, httpx.HTTPError) as e:
                notes.append(f"NSE bhavcopy {day}: {type(e).__name__}")
        if bse_ok and bse_raw is not None:
            return parse(bse_raw, series=None).rows, "BSE", day, notes
        break  # neither exchange answered for a trading day: manual imports
    week = set(week_days_back(friday))
    from pipeline.india import manual_import  # imports parse() from this module

    manual = [r for imp in manual_import.import_dir(imports) for r in imp.prices if r.trade_date in week]
    if manual:
        day = max(r.trade_date for r in manual)
        return [r for r in manual if r.trade_date == day], "manual", day, notes
    return [], "none", None, notes
