"""Indian quarterly results XBRL (Ind AS) -> fundamentals_q (BRIEF §4.3 "Financial results", §8 M3-02).

Sources: NSE's legacy results filings (taxonomy in-bse-fin, to FY2025 Q3) and SEBI Integrated Filing - Financials
(taxonomy in-capmkt, from FY2025 Q4). Both are read by local element name through config/signals.yaml ind_as_map.

Each filing has the quarter (3-month duration ending at the report date), the year to date (from the financial
year's start) and, in Q2 and Q4 filings only, the period-end balance sheet and the year-to-date cash flow
(India publishes balance sheets and cash flows half-yearly). Rows:
- P&L columns: the quarter, as reported. op_income = pretax_income + interest_expense - other_income (ind_as_map
  op_income_derived; null unless all three are known).
- balance-sheet columns: the Q2 and Q4 rows only (the half-year instants); Q1/Q3 rows have them null.
- cfo, capex: half-year flows. The Q2 row holds H1 (April-September); the Q4 row holds H2 = FY - H1 (same basis;
  null when H1 is unknown). Q1/Q3 rows have them null. TTM CFO = the latest H1 + H2 pair.
- shares_outstanding: paid-up equity capital / face value per share (both are in every filing).
Consolidated results win over standalone for the same quarter; a standalone filing only counts until a
consolidated one exists. A revision is a new row version with its own filed_at (like a US restatement). filed_at is
the exchange's submission time of the XBRL (IST in the listing, converted to UTC), never the period end.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import yaml

from pipeline.india.xbrl import Instance, XbrlError, parse_instance
from pipeline.settings import REPO_ROOT

Basis = Literal["consolidated", "standalone"]
QUARTER_DAYS = (80, 100)
PL_COLUMNS = ("revenue", "pretax_income", "tax_expense", "net_income", "interest_expense", "da")
HALF_YEAR_FLOWS = ("cfo", "capex")
INSTANT_COLUMNS = ("total_assets", "cash", "equity", "receivables", "inventory")


class ResultsError(XbrlError):
    pass


def load_ind_as_map(root: object = REPO_ROOT) -> dict[str, list[str]]:
    from pathlib import Path

    cfg = yaml.safe_load((Path(str(root)) / "config" / "signals.yaml").read_text(encoding="utf-8"))
    return {k: list(v) for k, v in cfg["ind_as_map"].items() if isinstance(v, list)}


@dataclass(frozen=True)
class Results:
    """One parsed results filing."""

    symbol: str
    isin: str | None
    basis: Basis
    fy_start: date
    fy_end: date
    period_start: date
    period_end: date
    quarter: int  # 1..4 within the financial year
    audited: bool | None
    pl: dict[str, Decimal | None]  # the quarter
    other_income: Decimal | None
    instants: dict[str, Decimal | None]  # period-end balance sheet (Q2/Q4), else all None
    ytd_flows: dict[str, Decimal | None]  # year-to-date cfo/capex (H1 at Q2, FY at Q4)
    shares_outstanding: Decimal | None

    @property
    def fiscal_label(self) -> str:
        return f"FY{self.fy_end.year}Q{self.quarter}"


def _first(inst: Instance, names: Sequence[str], start: date | None, end: date) -> Decimal | None:
    for n in names:
        v = inst.number(n, start, end)
        if v is not None:
            return v
    return None


def _basis(text: str | None) -> Basis:
    t = (text or "").strip().lower()
    if t.startswith("consolidated"):
        return "consolidated"
    if t.startswith("standalone") or t.startswith("non-consolidated") or t.startswith("non consolidated"):
        return "standalone"
    raise ResultsError(f"unknown NatureOfReportStandaloneConsolidated {text!r}")


def parse_results(raw: bytes | str, ind_as_map: Mapping[str, Sequence[str]]) -> Results:
    inst = parse_instance(raw)
    end_s = inst.text("DateOfEndOfReportingPeriod")
    fy_start_s, fy_end_s = inst.text("DateOfStartOfFinancialYear"), inst.text("DateOfEndOfFinancialYear")
    if not end_s or not fy_start_s or not fy_end_s:
        raise ResultsError("results XBRL without reporting-period / financial-year dates")
    period_end, fy_start, fy_end = (date.fromisoformat(s[:10]) for s in (end_s, fy_start_s, fy_end_s))
    quarters = sorted(
        {
            c.start
            for c in inst.contexts.values()
            if c.start and c.end == period_end and not c.dims and QUARTER_DAYS[0] <= (c.days or 0) <= QUARTER_DAYS[1]
        }
    )
    if not quarters:
        raise ResultsError(f"no 3-month context ending {period_end}")
    q_start = quarters[-1]
    quarter = ((period_end.year - fy_start.year) * 12 + period_end.month - fy_start.month) // 3 + 1
    if not 1 <= quarter <= 4:
        raise ResultsError(f"period end {period_end} outside the financial year {fy_start}..{fy_end}")
    pl = {c: _first(inst, ind_as_map.get(c, ()), q_start, period_end) for c in PL_COLUMNS}
    other = _first(inst, ind_as_map.get("other_income", ()), q_start, period_end)
    instants: dict[str, Decimal | None] = {c: None for c in (*INSTANT_COLUMNS, "total_debt")}
    flows: dict[str, Decimal | None] = {c: None for c in HALF_YEAR_FLOWS}
    if quarter in (2, 4):
        instants.update({c: _first(inst, ind_as_map.get(c, ()), None, period_end) for c in INSTANT_COLUMNS})
        parts = [inst.number(n, None, period_end) for n in ind_as_map.get("total_debt_parts", ())]
        known = [p for p in parts if p is not None]
        instants["total_debt"] = sum(known, Decimal(0)) if known else None
        flows = {c: _first(inst, ind_as_map.get(c, ()), fy_start, period_end) for c in HALF_YEAR_FLOWS}
    paid_up = _first(inst, ("PaidUpValueOfEquityShareCapital",), q_start, period_end) or _first(
        inst, ("PaidUpValueOfEquityShareCapital",), fy_start, period_end)  # fmt: skip
    face = _first(inst, ("FaceValueOfEquityShareCapital",), q_start, period_end) or _first(
        inst, ("FaceValueOfEquityShareCapital",), fy_start, period_end)  # fmt: skip
    audited = inst.text("WhetherResultsAreAuditedOrUnaudited")
    return Results(
        symbol=(inst.text("Symbol") or "").upper(),
        isin=inst.text("ISIN"),
        basis=_basis(inst.text("NatureOfReportStandaloneConsolidated")),
        fy_start=fy_start,
        fy_end=fy_end,
        period_start=q_start,
        period_end=period_end,
        quarter=quarter,
        audited=None if audited is None else audited.strip().lower() == "audited",
        pl=pl,
        other_income=other,
        instants=instants,
        ytd_flows=flows,
        shares_outstanding=(paid_up / face) if paid_up is not None and face else None,
    )


# ---------------------------------------------------------------- point-in-time rows


@dataclass(frozen=True)
class Filed:
    """A parsed filing with its public time (UTC)."""

    results: Results
    filed_at: datetime
    source_url: str = ""


@dataclass(frozen=True)
class IndiaRow:
    period_end: date
    fiscal_label: str
    filed_at: datetime
    basis: Basis
    values: dict[str, Decimal | None]
    fy_start: date | None = None  # the row's financial year: its inputs are that year's filings only


@dataclass
class Build:
    rows: list[IndiaRow] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)  # standalone filings superseded by consolidated ones
    issues: list[str] = field(default_factory=list)


def _values(r: Results, h1: Results | None) -> dict[str, Decimal | None]:
    v: dict[str, Decimal | None] = dict(r.pl)
    pbt, fin, oth = r.pl.get("pretax_income"), r.pl.get("interest_expense"), r.other_income
    v["op_income"] = pbt + fin - oth if pbt is not None and fin is not None and oth is not None else None
    v.update(r.instants)
    if r.quarter == 2:
        v.update(r.ytd_flows)
    elif r.quarter == 4:
        for c in HALF_YEAR_FLOWS:
            fy, first = r.ytd_flows.get(c), (h1.ytd_flows.get(c) if h1 is not None else None)
            v[c] = fy - first if fy is not None and first is not None else None
    else:
        v.update({c: None for c in HALF_YEAR_FLOWS})
    v["shares_outstanding"] = r.shares_outstanding
    return v


def build_rows(filings: Sequence[Filed]) -> Build:
    """Point-in-time rows for one company from all its results filings (any order)."""
    out = Build()
    latest: dict[date, Results] = {}  # period_end -> the filing whose values count now
    last_emitted: dict[date, dict[str, Decimal | None]] = {}
    for f in sorted(filings, key=lambda f: (f.filed_at, f.results.basis != "consolidated")):
        r = f.results
        cur = latest.get(r.period_end)
        if cur is not None and cur.basis == "consolidated" and r.basis == "standalone":
            out.ignored.append(f"{r.period_end} standalone filed {f.filed_at:%Y-%m-%d}: consolidated already filed")
            continue
        latest[r.period_end] = r
        touched = [r.period_end]
        if r.quarter == 2:  # a new H1 changes the same year's derived H2
            touched += [p for p, x in latest.items() if x.quarter == 4 and x.fy_start == r.fy_start]
        for p in touched:
            x = latest[p]
            h1 = next((y for y in latest.values() if y.quarter == 2 and y.fy_start == x.fy_start), None)
            if x.quarter == 4 and h1 is not None and h1.basis != x.basis:
                out.issues.append(f"{p}: H1 is {h1.basis}, FY is {x.basis}; H2 cash flow left null")
                h1 = None
            vals = _values(x, h1)
            if all(v is None for v in vals.values()) or last_emitted.get(p) == vals:
                continue
            last_emitted[p] = vals
            out.rows.append(IndiaRow(p, x.fiscal_label, f.filed_at, x.basis, vals, x.fy_start))
    out.rows.sort(key=lambda r: (r.period_end, r.filed_at))
    return out


# ---------------------------------------------------------------- the listing and the runner's store

LISTING_API = "integrated-filing-results?index=equities&type=Integrated%20Filing-%20Financials"
PAGE_SIZE = 50


@dataclass(frozen=True)
class ResultsListing:
    """One row of NSE's integrated-filing results API."""

    seq_id: str
    symbol: str
    period_end: date
    basis: Basis
    revision: bool
    filed_at: datetime  # UTC (the listing's creation_Date is IST)
    xbrl_url: str


def listing_path(day_from: date, day_to: date, page: int = 1) -> str:
    return (f"{LISTING_API}&from_date={day_from:%d-%m-%Y}&to_date={day_to:%d-%m-%Y}"
            f"&page={page}&size={PAGE_SIZE}")  # fmt: skip


def company_listing_path(symbol: str, page: int = 1) -> str:
    """One company's filing history, newest first (unpaged, NSE returns only the first 20 rows; review R2-F2 on M3)."""
    return f"{LISTING_API}&symbol={symbol}&page={page}&size={PAGE_SIZE}"


def parse_listing(raw: bytes | str) -> tuple[list[ResultsListing], int, int]:
    """The usable rows of one page, the total count across pages, and the page's row count (usable or not: paging
    counts every row)."""
    import json

    from pipeline.india.announcements import ist_to_utc

    doc = json.loads(raw)
    data = doc.get("data", [])
    out: list[ResultsListing] = []
    for r in data:
        url = str(r.get("xbrl") or "")
        if not url.startswith("https://") or not url.lower().endswith(".xml") or not r.get("symbol"):
            continue
        out.append(
            ResultsListing(
                seq_id=str(r.get("seq_Id") or url),
                symbol=str(r["symbol"]).upper(),
                period_end=datetime.strptime(str(r["qe_Date"]).title(), "%d-%b-%Y").date(),
                basis=_basis(str(r.get("consolidated") or "")),
                revision=str(r.get("type_Sub") or "").lower() == "revision",
                filed_at=ist_to_utc(str(r["creation_Date"])),
                xbrl_url=url,
            )
        )
    return out, int(doc.get("totalCount") or len(data)), len(data)


def preferred(listing: Sequence[ResultsListing]) -> list[ResultsListing]:
    """Drop a standalone filing when a consolidated one exists for the same company, quarter and submission."""
    consolidated = {(x.symbol, x.period_end, x.revision) for x in listing if x.basis == "consolidated"}
    return [x for x in listing if x.basis == "consolidated" or (x.symbol, x.period_end, x.revision) not in consolidated]


def to_json(f: Filed) -> dict[str, object]:
    r = f.results

    def num(v: Decimal | None) -> str | None:
        return None if v is None else str(v)

    return {
        "symbol": r.symbol,
        "isin": r.isin,
        "basis": r.basis,
        "fy_start": r.fy_start.isoformat(),
        "fy_end": r.fy_end.isoformat(),
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "quarter": r.quarter,
        "audited": r.audited,
        "pl": {k: num(v) for k, v in r.pl.items()},
        "other_income": num(r.other_income),
        "instants": {k: num(v) for k, v in r.instants.items()},
        "ytd_flows": {k: num(v) for k, v in r.ytd_flows.items()},
        "shares_outstanding": num(r.shares_outstanding),
        "filed_at": f.filed_at.isoformat(),
        "url": f.source_url,
    }


def from_json(d: Mapping[str, object]) -> Filed:
    def num(v: object) -> Decimal | None:
        return None if v is None else Decimal(str(v))

    def nums(v: object) -> dict[str, Decimal | None]:
        return {str(k): num(x) for k, x in dict(v).items()} if isinstance(v, dict) else {}

    basis: Basis = "consolidated" if d["basis"] == "consolidated" else "standalone"
    results = Results(
        symbol=str(d["symbol"]), isin=None if d.get("isin") is None else str(d["isin"]), basis=basis,
        fy_start=date.fromisoformat(str(d["fy_start"])), fy_end=date.fromisoformat(str(d["fy_end"])),
        period_start=date.fromisoformat(str(d["period_start"])), period_end=date.fromisoformat(str(d["period_end"])),
        quarter=int(str(d["quarter"])), audited=None if d.get("audited") is None else bool(d["audited"]),
        pl=nums(d.get("pl")), other_income=num(d.get("other_income")), instants=nums(d.get("instants")),
        ytd_flows=nums(d.get("ytd_flows")), shares_outstanding=num(d.get("shares_outstanding")),
    )  # fmt: skip
    return Filed(results, datetime.fromisoformat(str(d["filed_at"])), str(d.get("url") or ""))
