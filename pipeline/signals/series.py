"""A company's quarters as known at an as-of date, and BRIEF §4.6's shared definitions.

Lags count quarters back from the latest known quarter (lag 0). Values are Decimal throughout, so thresholds compare
exactly (a just-below-threshold case stays below).

India (BRIEF §4.3, §7.6): balance sheets and cash flows are half-yearly. The results rows carry cfo/capex on the Q2
and Q4 rows only (Q2 = H1, Q4 = H2), and balance-sheet items only on those rows. TTM of a half-yearly flow is the
sum of the two half-years in the 4-quarter window; a balance-sheet "point" is the latest value within 2 quarters.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

ZERO = Decimal(0)
ONE = Decimal(1)
HALF_YEARLY_FLOWS = frozenset({"cfo", "capex"})
HALF_YEARLY_POINTS = frozenset({"total_assets", "cash", "equity", "receivables", "inventory", "total_debt"})
COLUMNS = (
    "revenue", "op_income", "net_income", "pretax_income", "tax_expense", "cfo", "capex", "da", "interest_expense",
    "total_assets", "cash", "total_debt", "equity", "receivables", "inventory", "deferred_revenue", "rpo",
    "diluted_shares", "shares_outstanding",
)  # fmt: skip
QUARTER_GAP_DAYS = 100  # consecutive quarter ends are ~91 days apart; more means a gap in the history


@dataclass(frozen=True)
class Quarter:
    end: date
    values: Mapping[str, Decimal | None]

    def get(self, col: str) -> Decimal | None:
        return self.values.get(col)


def clip(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, x))


def growth(now: Decimal | None, then: Decimal | None) -> Decimal | None:
    """now / then - 1, defined only for a positive base."""
    if now is None or then is None or then <= 0:
        return None
    return now / then - 1


def ratio(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def dec(x: object) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


class Series:
    """One company's quarters, oldest first (latest version of each as of the cutoff)."""

    def __init__(self, quarters: Iterable[Quarter], market: str, tax_default: Mapping[str, Decimal] | None = None):
        self.quarters = sorted(quarters, key=lambda q: q.end)
        self.market = market
        self._tax_default = tax_default or {"us": Decimal("0.21"), "in": Decimal("0.25")}

    @classmethod
    def from_rows(cls, rows: Sequence[Any], market: str) -> Series:
        """From FundamentalsRow-like objects (period_end plus one attribute per column)."""
        return cls((Quarter(r.period_end, {c: getattr(r, c, None) for c in COLUMNS}) for r in rows), market)

    def __len__(self) -> int:
        return len(self.quarters)

    def at(self, lag: int) -> Quarter | None:
        i = len(self.quarters) - 1 - lag
        return self.quarters[i] if 0 <= i < len(self.quarters) else None

    @property
    def latest_end(self) -> date | None:
        return self.quarters[-1].end if self.quarters else None

    def _window(self, lag: int, n: int = 4) -> list[Quarter] | None:
        qs = [self.at(k) for k in range(lag, lag + n)]
        if any(q is None for q in qs):
            return None
        got = [q for q in qs if q is not None]
        if (got[0].end - got[-1].end).days > QUARTER_GAP_DAYS * (n - 1):
            return None
        return got

    # ------------------------------------------------------------ building blocks

    def value(self, col: str, lag: int = 0) -> Decimal | None:
        q = self.at(lag)
        return None if q is None else q.get(col)

    def ttm(self, col: str, lag: int = 0) -> Decimal | None:
        """Sum of the 4 quarters ending at `lag`. India half-yearly flows: the two half-years in the window."""
        w = self._window(lag)
        if w is None:
            return None
        vals = [q.get(col) for q in w]
        if self.market == "in" and col in HALF_YEARLY_FLOWS:
            known = [v for v in vals if v is not None]
            return sum(known, ZERO) if len(known) == 2 else None
        if any(v is None for v in vals):
            return None
        return sum((v for v in vals if v is not None), ZERO)

    def point(self, col: str, lag: int = 0) -> Decimal | None:
        """A balance-sheet value at `lag`. India half-yearly items: the latest one within 2 quarters."""
        v = self.value(col, lag)
        if v is None and self.market == "in" and col in HALF_YEARLY_POINTS:
            prev = self.at(lag + 1)
            now = self.at(lag)
            if prev is not None and now is not None and (now.end - prev.end).days <= 100:
                return prev.get(col)
        return v

    def mean_point(self, col: str, lag: int = 0, n: int = 4) -> Decimal | None:
        """Mean of the known values of a balance-sheet item over the n quarters ending at `lag`."""
        vals = [self.value(col, k) for k in range(lag, lag + n) if self.at(k) is not None]
        known = [v for v in vals if v is not None]
        return sum(known, ZERO) / len(known) if known else None

    # ------------------------------------------------------------ BRIEF §4.6 shared definitions

    def tax_rate(self, lag: int = 0) -> Decimal:
        """clip(TTM(tax)/TTM(pretax), 0.10, 0.35); the market default when pretax <= 0 or unknown."""
        tax, pretax = self.ttm("tax_expense", lag), self.ttm("pretax_income", lag)
        if tax is None or pretax is None or pretax <= 0:
            return self._tax_default[self.market]
        return clip(tax / pretax, Decimal("0.10"), Decimal("0.35"))

    def nopat(self, lag: int = 0) -> Decimal | None:
        op = self.ttm("op_income", lag)
        return None if op is None else op * (1 - self.tax_rate(lag))

    def invested_capital(self, lag: int = 0) -> Decimal | None:
        """IC = total_debt + equity - cash, floored at 0.05 x total_assets. A missing debt figure counts as no
        debt (filers without borrowings report no debt concept); equity, cash and assets must be known."""
        equity, cash, assets = self.point("equity", lag), self.point("cash", lag), self.point("total_assets", lag)
        if equity is None or cash is None or assets is None:
            return None
        debt = self.point("total_debt", lag) or ZERO
        return max(debt + equity - cash, Decimal("0.05") * assets)

    def mean_ic(self, lag: int = 0, n: int = 4) -> Decimal | None:
        ics = [self.invested_capital(k) for k in range(lag, lag + n) if self.at(k) is not None]
        known = [v for v in ics if v is not None]
        return sum(known, ZERO) / len(known) if known else None

    def roic(self, lag: int = 0) -> Decimal | None:
        return ratio(self.nopat(lag), self.mean_ic(lag))

    def opm(self, lag: int = 0) -> Decimal | None:
        rev = self.ttm("revenue", lag)
        return None if rev is None or rev <= 0 else ratio(self.ttm("op_income", lag), rev)

    def net_debt(self, lag: int = 0) -> Decimal | None:
        """ND = total_debt - cash; unknown when debt isn't reported (signals on leverage need the real figure)."""
        debt, cash = self.point("total_debt", lag), self.point("cash", lag)
        return None if debt is None or cash is None else debt - cash

    def fcf(self, lag: int = 0) -> Decimal | None:
        cfo, capex = self.ttm("cfo", lag), self.ttm("capex", lag)
        return None if cfo is None or capex is None else cfo - capex

    def ebitda(self, lag: int = 0) -> Decimal | None:
        op, da = self.ttm("op_income", lag), self.ttm("da", lag)
        return None if op is None or da is None else op + da

    def shares(self, lag: int = 0) -> tuple[Decimal | None, str]:
        """Diluted weighted shares where reported (US), else shares outstanding (India: paid-up / face value)."""
        d = self.value("diluted_shares", lag)
        return (d, "diluted_shares") if d is not None else (self.point("shares_outstanding", lag), "shares_outstanding")

    def quarterly_yoy(self, col: str, lag: int = 0) -> Decimal | None:
        """A single quarter against the same quarter a year earlier (lag + 4, which must be ~1 year back)."""
        now, then = self.at(lag), self.at(lag + 4)
        if now is None or then is None or not 330 <= (now.end - then.end).days <= 400:
            return None
        return growth(now.get(col), then.get(col))

    def ttm_yoy(self, col: str, lag: int = 0) -> Decimal | None:
        return growth(self.ttm(col, lag), self.ttm(col, lag + 4))
