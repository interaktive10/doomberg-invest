"""13F institutional holder counts (BRIEF §4.2, §4.6 S8): SEC Form 13F data sets -> ownership_q.inst_holders.

Per filer and period: the latest RESTATEMENT amendment replaces the original 13F-HR; NEW HOLDINGS amendments add to
it. Notices (13F-NT) hold nothing. Option rows (PUTCALL) and principal amounts (PRN, i.e. debt) are not holders of the
common stock, and neither are non-common CUSIPs (preferred, convertibles, units, warrants, options): a CUSIP is
non-common when most of its rows' TITLEOFCLASS say so, because filers label classes inconsistently (one NextEra
equity-unit row says "PUBLIC", two say "UNIT 06/01/2027").
CUSIPs map to companies by issuer-name fuzzy match (rapidfuzz >= 92) against the universe plus
config/cusip_overrides.yaml; unmapped CUSIPs are logged. A company's count is the number of distinct filers holding
any of its CUSIPs (share classes).

Availability: a count is only complete once the data set's filing window has closed, so filed_at is the day after
the window's last filing date (data sets are published after the window).

Data sets cover 3-month filing windows (Dec-Feb, Mar-May, Jun-Aug, Sep-Nov); pipeline/us/quarterly.py downloads
them and writes ownership_q.
"""

from __future__ import annotations

import calendar
import csv
import io
import zipfile
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import IO

from pipeline.us.names import non_common, normalize_name
from pipeline.us.submissions import end_of_day_utc

HOLDINGS_REPORTS = {"13F HOLDINGS REPORT", "13F COMBINATION REPORT"}
FUZZY_MIN = 92.0
DATASETS = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets"
PUBLISH_LAG_DAYS = 21  # a window's data set is assumed published three weeks after it closes


@dataclass(frozen=True)
class Holding:
    accession: str
    issuer: str
    cusip: str
    title: str


@dataclass(frozen=True)
class Filing13F:
    accession: str
    cik: str
    filing_date: date
    submission_type: str  # 13F-HR, 13F-HR/A, 13F-NT, ...
    period: date
    amendment_type: str  # "" | RESTATEMENT | NEW HOLDINGS
    report_type: str


@dataclass
class DataSet:
    filings: dict[str, Filing13F]
    holdings: dict[str, list[Holding]]  # accession -> share holdings (no options, no PRN)
    filed_through: date  # last filing date the data set covers
    skipped_rows: int = 0

    @property
    def available_at(self) -> datetime:
        return end_of_day_utc(self.filed_through)


def _dmy(s: str) -> date:
    return datetime.strptime(s.strip(), "%d-%b-%Y").date()


def _reader(fh: IO[str]) -> csv.DictReader[str]:
    return csv.DictReader(fh, delimiter="\t")


def read_dataset(submission: IO[str], coverpage: IO[str], infotable: IO[str], filed_through: date) -> DataSet:
    cover = {r["ACCESSION_NUMBER"]: r for r in _reader(coverpage)}
    filings: dict[str, Filing13F] = {}
    for r in _reader(submission):
        c = cover.get(r["ACCESSION_NUMBER"], {})
        filings[r["ACCESSION_NUMBER"]] = Filing13F(
            accession=r["ACCESSION_NUMBER"],
            cik=r["CIK"].zfill(10),
            filing_date=_dmy(r["FILING_DATE"]),
            submission_type=r["SUBMISSIONTYPE"],
            period=_dmy(r["PERIODOFREPORT"]),
            amendment_type=(c.get("AMENDMENTTYPE") or "").strip().upper(),
            report_type=(c.get("REPORTTYPE") or "").strip().upper(),
        )
    rows: list[Holding] = []
    votes: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # cusip -> [non-common rows, rows]
    skipped = 0
    for r in _reader(infotable):
        if (r.get("PUTCALL") or "").strip() or (r.get("SSHPRNAMTTYPE") or "").strip().upper() == "PRN":
            skipped += 1
            continue
        h = Holding(r["ACCESSION_NUMBER"], r["NAMEOFISSUER"].strip(), r["CUSIP"].strip().upper(), r["TITLEOFCLASS"])
        rows.append(h)
        v = votes[h.cusip]
        v[0] += non_common(h.title or "")
        v[1] += 1
    holdings: dict[str, list[Holding]] = defaultdict(list)
    for h in rows:
        n_non_common, total = votes[h.cusip]
        if 2 * n_non_common > total:
            skipped += 1
            continue
        holdings[h.accession].append(h)
    return DataSet(filings, dict(holdings), filed_through, skipped)


def read_dataset_zip(path: Path, filed_through: date) -> DataSet:
    with zipfile.ZipFile(path) as z:

        def open_(name: str) -> IO[str]:
            member = next(n for n in z.namelist() if n.rsplit("/", 1)[-1].upper() == name)
            return io.TextIOWrapper(z.open(member), encoding="utf-8", errors="replace")

        return read_dataset(open_("SUBMISSION.TSV"), open_("COVERPAGE.TSV"), open_("INFOTABLE.TSV"), filed_through)


def holders_by_cusip(ds: DataSet, period: date) -> dict[str, set[str]]:
    """CUSIP -> filer CIKs holding it for `period`, applying RESTATEMENT / NEW HOLDINGS amendments."""
    base: dict[str, Filing13F] = {}
    added: dict[str, list[Filing13F]] = defaultdict(list)
    for f in sorted(ds.filings.values(), key=lambda f: (f.filing_date, f.accession)):
        if f.period != period or not f.submission_type.startswith("13F-HR"):
            continue
        if f.report_type and f.report_type not in HOLDINGS_REPORTS:
            continue
        if f.submission_type == "13F-HR":
            if f.cik not in base or not base[f.cik].amendment_type:
                base[f.cik] = f  # a later original replaces an earlier one, never a restatement
        elif f.amendment_type == "RESTATEMENT":
            base[f.cik] = f
            added.pop(f.cik, None)  # a restatement is complete: earlier additions are superseded
        elif f.amendment_type == "NEW HOLDINGS":
            added[f.cik].append(f)
    out: dict[str, set[str]] = defaultdict(set)
    for cik, f in base.items():
        for h in ds.holdings.get(f.accession, []):
            out[h.cusip].add(cik)
        for a in added.get(cik, []):
            for h in ds.holdings.get(a.accession, []):
                out[h.cusip].add(cik)
    return dict(out)


def issuer_names(ds: DataSet) -> dict[str, str]:
    """CUSIP -> the most common issuer name reported for it."""
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rows in ds.holdings.values():
        for h in rows:
            votes[h.cusip][h.issuer] += 1
    return {c: max(v.items(), key=lambda kv: kv[1])[0] for c, v in votes.items()}


@dataclass
class Mapping13F:
    cusip_to_cik: dict[str, str] = field(default_factory=dict)
    unmapped: dict[str, str] = field(default_factory=dict)  # cusip -> issuer name


def map_cusips(
    names: Mapping[str, str],
    universe: Mapping[str, str],
    overrides: Mapping[str, str] | None = None,
    min_score: float = FUZZY_MIN,
) -> Mapping13F:
    """CUSIP -> CIK. `universe` is CIK -> company name. Overrides win; otherwise the best rapidfuzz match at or above
    `min_score` on normalized names (ties or ambiguity -> unmapped)."""
    from rapidfuzz import fuzz, process

    by_norm: dict[str, list[str]] = defaultdict(list)
    for cik, name in universe.items():
        n = normalize_name(name)
        if n:
            by_norm[n].append(cik)
    choices = list(by_norm)
    out = Mapping13F()
    for cusip, issuer in sorted(names.items()):
        if overrides and cusip in overrides:
            out.cusip_to_cik[cusip] = str(overrides[cusip]).zfill(10)
            continue
        n = normalize_name(issuer)
        exact = by_norm.get(n)
        if exact and len(exact) == 1:
            out.cusip_to_cik[cusip] = exact[0]
            continue
        best = process.extract(n, choices, scorer=fuzz.token_sort_ratio, limit=2) if n else []
        if best and best[0][1] >= min_score and (len(best) == 1 or best[0][1] > best[1][1]):
            ciks = by_norm[best[0][0]]
            if len(ciks) == 1:
                out.cusip_to_cik[cusip] = ciks[0]
                continue
        out.unmapped[cusip] = issuer
    return out


def company_holder_counts(holders: Mapping[str, set[str]], mapping: Mapping13F) -> dict[str, int]:
    """CIK -> distinct filers holding any of the company's CUSIPs."""
    per: dict[str, set[str]] = defaultdict(set)
    for cusip, filers in holders.items():
        cik = mapping.cusip_to_cik.get(cusip)
        if cik:
            per[cik] |= filers
    return {cik: len(f) for cik, f in per.items()}


def main_period(ds: DataSet) -> date:
    """The period most filings in the data set report on (the quarter the window was published for)."""
    counts: dict[date, int] = defaultdict(int)
    for f in ds.filings.values():
        counts[f.period] += 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


# ---------------------------------------------------------------- data set windows


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def windows_before(today: date, n: int = 1, lag_days: int = PUBLISH_LAG_DAYS) -> list[tuple[date, date]]:
    """The last `n` published 3-month filing windows (start, end), newest first. Windows end in Feb, May, Aug, Nov."""
    y, m = today.year, today.month
    out: list[tuple[date, date]] = []
    while len(out) < n:
        if m in (2, 5, 8, 11):
            end = _month_end(y, m)
            if end + timedelta(days=lag_days) <= today:
                sy, sm = (y, m - 2) if m > 2 else (y - 1, 12)
                out.append((date(sy, sm, 1), end))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def dataset_url(start: date, end: date) -> str:
    """e.g. .../01dec2024-28feb2025_form13f.zip"""
    return f"{DATASETS}/{start:%d%b%Y}-{end:%d%b%Y}".lower() + "_form13f.zip"
