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

import yaml

from pipeline.settings import REPO_ROOT

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
# BRIEF §4.6 shared definitions, from config/signals.yaml `shared` (protected; M4 review R1-F9: read, not restated)
SHARED = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["shared"]
TAX_CLIP = tuple(Decimal(str(x)) for x in SHARED["tax_rate_clip"])
TAX_DEFAULT = {str(k): Decimal(str(v)) for k, v in SHARED["tax_rate_default"].items()}
IC_FLOOR = Decimal(str(SHARED["ic_floor_pct_assets"]))
ROIC_IC_QUARTERS = int(SHARED["roic_ic_mean_quarters"])
DEBT_CARRY_QUARTERS = 4  # a missing debt figure reads the last one reported within a year (M4 review R1-F1)


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
        self._tax_default = tax_default or TAX_DEFAULT
        self._splits: list[Any] | None = None  # share_splits(), computed once (R4, S5 and the screener ask ~9 times)

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
        return clip(tax / pretax, TAX_CLIP[0], TAX_CLIP[1])

    def nopat(self, lag: int = 0) -> Decimal | None:
        op = self.ttm("op_income", lag)
        return None if op is None else op * (1 - self.tax_rate(lag))

    def debt(self, lag: int = 0) -> Decimal | None:
        """total_debt at `lag`: as reported there; else the latest figure reported in the year before (filers such
        as CAT and ORCL tag debt only in their 10-Ks, so a 10-Q quarter reads the last 10-K's figure); zero only for
        a filer with no debt figure anywhere in its history (no borrowings, no debt concept); otherwise unknown
        (M4 review R1-F1: a missing figure is never read as zero debt)."""
        v = self.point("total_debt", lag)
        now = self.at(lag)
        if v is not None or now is None:
            return v
        for k in range(lag + 1, lag + 1 + DEBT_CARRY_QUARTERS):
            q = self.at(k)
            if q is None or (now.end - q.end).days > 400:
                break
            if q.get("total_debt") is not None:
                return q.get("total_debt")
        return ZERO if all(q.get("total_debt") is None for q in self.quarters) else None

    def invested_capital(self, lag: int = 0) -> Decimal | None:
        """IC = total_debt + equity - cash, floored at 0.05 x total_assets; debt as `debt()` reads it (unknown debt
        -> unknown IC); equity, cash and assets must be known."""
        equity, cash, assets = self.point("equity", lag), self.point("cash", lag), self.point("total_assets", lag)
        debt = self.debt(lag)
        if equity is None or cash is None or assets is None or debt is None:
            return None
        return max(debt + equity - cash, IC_FLOOR * assets)

    def mean_ic(self, lag: int = 0, n: int = ROIC_IC_QUARTERS) -> Decimal | None:
        ics = [self.invested_capital(k) for k in range(lag, lag + n) if self.at(k) is not None]
        known = [v for v in ics if v is not None]
        return sum(known, ZERO) / len(known) if known else None

    def roic(self, lag: int = 0) -> Decimal | None:
        return ratio(self.nopat(lag), self.mean_ic(lag))

    def opm(self, lag: int = 0) -> Decimal | None:
        rev = self.ttm("revenue", lag)
        return None if rev is None or rev <= 0 else ratio(self.ttm("op_income", lag), rev)

    def net_debt(self, lag: int = 0) -> Decimal | None:
        """ND = total_debt - cash, with debt as `debt()` reads it (the same rule as invested capital and EV)."""
        debt, cash = self.debt(lag), self.point("cash", lag)
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

    def share_splits(self) -> list[Any]:
        """Share-count changes that are splits, bonus issues or consolidations (a split ratio between consecutive
        counts, pipeline.prices.splits): India's counts (paid-up capital / face value) are never adjusted for them."""
        from pipeline.prices.splits import share_splits

        if self._splits is None:
            history = []
            for k in range(len(self.quarters) - 1, -1, -1):
                v, _ = self.shares(k)
                q = self.at(k)
                if v is not None and q is not None:
                    history.append((q.end, v))
            self._splits = share_splits(history)
        return self._splits

    def split_adjusted_shares(self, lag: int = 0) -> tuple[Decimal | None, str]:
        """The share count at `lag` on the latest quarter's basis: a 1:1 bonus or a face-value split multiplies
        every earlier count by its ratio, so neither reads as dilution (M4 review R2-F1). No price is used."""
        v, source = self.shares(lag)
        q = self.at(lag)
        if v is None or q is None:
            return v, source
        f = Decimal(1)
        for sp in self.share_splits():
            if sp.old_end >= q.end:
                f *= sp.ratio
        return v * f, source

    def shares_yoy(self, lag: int = 0) -> Decimal | None:
        """Split-adjusted share-count change against a year earlier (None without a year back)."""
        if not self.year_back_ok(lag):
            return None
        return growth(self.split_adjusted_shares(lag)[0], self.split_adjusted_shares(lag + 4)[0])

    def year_back_ok(self, lag: int = 0) -> bool:
        """The quarter at lag + 4 is about a year before the one at lag (330-400 days): with a quarter missing, the
        row four places back is 15 months back and a YoY on it is wrong (M4 review R1-F8)."""
        now, then = self.at(lag), self.at(lag + 4)
        return now is not None and then is not None and 330 <= (now.end - then.end).days <= 400

    def quarterly_yoy(self, col: str, lag: int = 0) -> Decimal | None:
        """A single quarter against the same quarter a year earlier."""
        if not self.year_back_ok(lag):
            return None
        now, then = self.at(lag), self.at(lag + 4)
        assert now is not None and then is not None
        return growth(now.get(col), then.get(col))

    def ttm_yoy(self, col: str, lag: int = 0) -> Decimal | None:
        """TTM against the TTM a year earlier (the two windows must end about a year apart)."""
        return growth(self.ttm(col, lag), self.ttm(col, lag + 4)) if self.year_back_ok(lag) else None
