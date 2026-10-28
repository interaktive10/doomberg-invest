"""F-LAB (BRIEF §9): a synthetic panel of 500 companies x 60 month-ends with one planted signal and one noise signal,
built in memory (seeded) for the Signal Lab tests (M8-01, M8-02).

- Every company files flat quarters (revenue, order book, cash flows, balance sheet, shares) 30 days after each
  quarter end, from 2012 (the signals need two years of history) to 2019.
- Planted: a quarter of the companies see their order book (RPO) step up 40%. The live S1 fires once the second
  such quarter is filed (order book growth beats revenue growth by >= 10 pp in two quarters, coverage rising). From
  the month after that filing, the stock drifts +2.5% a month for 12 months (the market learns what the filing said).
- Noise: about a fifth of the companies, never a planted one, buy back 4% of their shares. The live S5 fires (path
  A: shares down >= 2% YoY, FCF > 0, net debt flat); the price does nothing.
- Prices: month-end closes 2015-01 to 2019-12, log returns N(0.5%, 8%) a month plus the planted drift.
- `shift_filed_days` moves every filing of the planted companies later (the leak test, M8-02): S1 then fires after
  the drift, so a point-in-time Lab finds nothing (with a shift past the freshness rule's 210 days, S1 doesn't fire
  on those filings at all: pipeline/signals/weekly.py FUNDAMENTALS_MAX_AGE_DAYS).
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from pipeline.db.models import Company, FundamentalsRow
from pipeline.lab.panel import LabData
from pipeline.lab.prices import MonthBar, add_months, month_end, month_ends

FIRST_QUARTER = date(2012, 3, 31)
LAST_QUARTER = date(2019, 12, 31)
FIRST_MONTH, LAST_MONTH = date(2015, 1, 31), date(2019, 12, 31)
PERIODS = {
    "in_sample": (date(2015, 1, 31), date(2016, 12, 31)),
    "out_of_sample": (date(2017, 1, 31), date(2018, 12, 31)),
}
DRIFT, VOL, MU = 0.025, 0.08, 0.005
FILING_LAG = timedelta(days=30)


@dataclass(frozen=True)
class Truth:
    planted: dict[uuid.UUID, date]  # company -> the month-end its S1 becomes visible (true filing)
    noise: dict[uuid.UUID, date]  # company -> the quarter its buyback starts


def quarter_ends() -> list[date]:
    out, q = [], FIRST_QUARTER
    while q <= LAST_QUARTER:
        out.append(q)
        q = add_months(q, 3)
    return out


def filed(q: date, shift: int = 0) -> datetime:
    return datetime.combine(q + FILING_LAG + timedelta(days=shift), time(21), tzinfo=UTC)


def _row(cid: uuid.UUID, q: date, i: int, scale: Decimal, rpo: Decimal, shares: Decimal, shift: int) -> FundamentalsRow:
    m = scale
    return FundamentalsRow(
        company_id=cid, period_end=q, fiscal_label=f"FY{q.year}Q{(q.month - 1) // 3 + 1}", filed_at=filed(q, shift),
        revenue=100 * m, op_income=10 * m, net_income=7 * m, pretax_income=9 * m, tax_expense=2 * m, cfo=20 * m,
        capex=10 * m, da=5 * m, interest_expense=1 * m, total_assets=400 * m, cash=30 * m, total_debt=50 * m,
        equity=200 * m, receivables=30 * m, inventory=20 * m, rpo=rpo * m, diluted_shares=shares,
        shares_outstanding=shares, currency="USD", source="sec_xbrl",
    )  # fmt: skip


def make(seed: int = 7, n: int = 500, shift_filed_days: int = 0) -> tuple[LabData, Truth]:
    rng = random.Random(seed)
    quarters = quarter_ends()
    months = month_ends(FIRST_MONTH, LAST_MONTH)
    companies, versions, bars = [], {}, {}
    planted: dict[uuid.UUID, date] = {}
    noise: dict[uuid.UUID, date] = {}
    # a step at quarter q* fires once q*+1 is filed: keep those filings between 2015-02 and 2018-11
    step_quarters = [q for q in quarters if date(2014, 12, 31) <= add_months(q, 3) <= date(2018, 9, 30)]
    for k in range(n):
        cid = uuid.UUID(int=rng.getrandbits(128))
        companies.append(Company(id=cid, market="us", name=f"Synthetic {k:03d} Inc", ticker=f"SYN{k:03d}"))
        scale = Decimal(rng.choice((5, 20, 80, 300))) * Decimal(1_000_000)
        base_shares = Decimal(rng.choice((50, 100, 400))) * Decimal(1_000_000)
        is_planted, is_noise = rng.random() < 0.25, rng.random() < 0.25
        step = rng.choice(step_quarters) if is_planted else None
        buyback = rng.choice(quarters[12:-4]) if is_noise else None
        if is_planted:  # disjoint sets: the noise signal carries no planted drift (review R1-F6); the draw above
            buyback = None  # is still taken, so every other company is unchanged
        shift = shift_filed_days if is_planted else 0
        rows = []
        for i, q in enumerate(quarters):
            rpo = Decimal(280) if step is not None and q >= step else Decimal(200)
            shares = base_shares * Decimal("0.96") if buyback is not None and q >= buyback else base_shares
            rows.append(_row(cid, q, i, scale, rpo, shares, shift))
        versions[cid] = rows
        visible = None
        if step is not None:
            visible = month_end(filed(add_months(step, 3)).date())  # the second stepped quarter's filing month
            planted[cid] = visible
        if buyback is not None:
            noise[cid] = buyback
        price = 20.0 + 80.0 * rng.random()
        series = []
        for m in months:
            drift = DRIFT if visible is not None and visible < m <= add_months(visible, 12) else 0.0
            price *= math.exp(rng.gauss(MU, VOL) + drift)
            p = Decimal(str(round(price, 4)))
            series.append(MonthBar(m, p, p, p))
        bars[cid] = series
    return LabData("us", companies, versions, bars), Truth(planted, noise)
