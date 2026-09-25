"""M7 review R1-F5: the Company page charts the per-quarter series the weekly run writes (company_series), computed
with the §4.6 definitions the signals and the screener use, so the page can't disagree with them."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals.series import Quarter, Series
from pipeline.signals.weekly import series_points

S2 = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["s2_incremental_roic"]


def quarters() -> Series:
    """16 US quarters whose debt is tagged only in the 10-Ks (M4 review R1-F1), as the review's repro built them."""
    ends = [date(y, m, d) for y in (2022, 2023, 2024, 2025) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]
    out = []
    for i, e in enumerate(ends):
        op = Decimal(60) + Decimal("0.8") * i * i
        row = {"revenue": Decimal(1000 + 40 * i), "op_income": op, "net_income": op * Decimal("0.75"),
               "pretax_income": op, "tax_expense": op * Decimal("0.22"), "cfo": op * Decimal("1.1"),
               "capex": Decimal(30), "da": Decimal(25), "total_assets": Decimal(6000 + 150 * i),
               "cash": Decimal(300), "total_debt": Decimal(2500) if e.month == 12 else None,
               "equity": Decimal(1500 + 120 * i), "rpo": None, "diluted_shares": Decimal(100),
               "shares_outstanding": Decimal(100)}  # fmt: skip
        out.append(Quarter(e, row))
    return Series(out, "us")


def test_company_series_use_the_46_definitions() -> None:
    s = quarters()
    points = series_points(s, S2)
    assert [p["period_end"] for p in points][-2:] == ["2025-09-30", "2025-12-31"] and len(points) == 12
    last, before = points[-1], points[-2]
    assert last["roic"] == round(float(s.roic(0)), 6) and abs(last["roic"] - 0.1213) < 5e-4
    inc = (s.nopat(0) - s.nopat(12)) / (s.invested_capital(0) - s.invested_capital(12))
    assert last["incremental_roic"] == round(float(inc), 6) and abs(last["incremental_roic"] - 0.312) < 5e-4
    # a 10-Q quarter: debt carried from the 10-K, not read as 0 (the page showed 0.2015 and -0.36 net cash)
    assert abs(before["roic"] - 0.1116) < 5e-4
    assert abs(before["nd_to_ebitda"] - 2.61) < 5e-3
    assert last["revenue_ttm"] == float(s.ttm("revenue", 0)) and "rpo" not in last  # no RPO reported: left out


def test_incremental_roic_needs_enough_invested_capital_growth() -> None:
    s = quarters()
    points = series_points(s, {**S2, "min_delta_ic_pct": 10})  # dIC never exceeds 10 x IC 12 quarters ago
    assert all("incremental_roic" not in p for p in points)
    assert "incremental_roic" not in series_points(s, S2)[0]  # the oldest points have no 12-quarter lookback
