"""M2-01: F-US quarterized values equal the expected CSVs for 3 companies, including Q4 derivation (BRIEF §8 M2).

The expected CSVs come from fixtures/us/expected/derive_expected.py, which does not import pipeline code (SEC frame
tags + hand arithmetic for Q4 and YTD cash flow)."""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from pipeline.us.companyfacts import load_facts
from pipeline.us.quarterize import QuarterRow, quarterize
from pipeline.us.submissions import parse_submissions

ROOT = Path(__file__).resolve().parents[2]
F_US = {"AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810", "CAT": "0000018230",
        "ORCL": "0001341439", "PWR": "0001050915", "JBL": "0000898293", "GEV": "0001996810"}  # fmt: skip
XMAP = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["xbrl_map"]


def company(ticker: str) -> tuple[list[QuarterRow], dict[date, QuarterRow]]:
    cik = F_US[ticker]
    doc = json.loads((ROOT / "fixtures/us/companyfacts" / f"CIK{cik}.json").read_text(encoding="utf-8"))
    subs = parse_submissions(json.loads((ROOT / "fixtures/us/submissions" / f"CIK{cik}.json").read_text()))
    facts, _ = load_facts(doc, XMAP, subs.accepted())
    rows, _ = quarterize(facts, {f.accession: f.report_date for f in subs.filings if f.report_date})
    return rows, {r.period_end: r for r in rows}


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "CAT"])
def test_expected_csv(ticker: str) -> None:
    _, latest = company(ticker)
    rows = list(csv.DictReader((ROOT / "fixtures/us/expected" / f"{ticker}.csv").open(encoding="utf-8")))
    assert len(rows) == 8
    for row in rows:
        got = latest[date.fromisoformat(row["period_end"])]
        for col in ("revenue", "op_income", "net_income", "cfo", "total_assets", "cash"):
            expected = Decimal(row[col]) if row[col] else None
            assert got.values[col] == expected, (ticker, row["period_end"], col)


def test_published_quarters_including_derived_q4() -> None:
    """Spot checks against the companies' published quarterly revenue ($M)."""
    _, aapl = company("AAPL")
    fy24 = [date(2023, 12, 30), date(2024, 3, 30), date(2024, 6, 29), date(2024, 9, 28)]
    assert [aapl[d].values["revenue"] for d in fy24] == [Decimal(v) * 10**6 for v in (119575, 90753, 85777, 94930)]
    _, msft = company("MSFT")
    fy24m = [date(2023, 9, 30), date(2023, 12, 31), date(2024, 3, 31), date(2024, 6, 30)]
    assert [msft[d].values["revenue"] for d in fy24m] == [Decimal(v) * 10**6 for v in (56517, 62020, 61858, 64727)]
    _, cat = company("CAT")
    assert cat[date(2023, 12, 31)].values["revenue"] == Decimal(17070) * 10**6  # 67,060 - 15,862 - 17,318 - 16,810
    _, nvda = company("NVDA")
    assert nvda[date(2025, 1, 26)].values["revenue"] == Decimal(39331) * 10**6


@pytest.mark.parametrize("ticker", sorted(F_US))
def test_every_fixture_company_quarterizes(ticker: str) -> None:
    rows, latest = company(ticker)
    assert len(latest) >= 8
    assert rows == sorted(rows, key=lambda r: (r.period_end, r.filed_at))
    assert all(r.filed_at.tzinfo is not None for r in rows)
    labels = [latest[e].fiscal_label for e in sorted(latest)[-8:]]
    assert len(set(labels)) == 8, labels  # no duplicate fiscal labels (ORCL's mis-tagged fy no longer leaks in)


def test_total_debt_uses_real_totals() -> None:
    """The M0 map fell back to current maturities only; F-US showed PWR at $63M instead of ~$4B."""
    _, pwr = company("PWR")
    assert pwr[date(2024, 12, 31)].values["total_debt"] == Decimal(4162436000)
    _, orcl = company("ORCL")
    assert orcl[date(2025, 5, 31)].values["total_debt"] == Decimal(92568000000)
