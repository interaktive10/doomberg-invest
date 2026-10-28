"""Fact diffs (Appendix F.6), computed by code, never by an LLM.

For each new verified fact, the latest earlier verified fact of the same company and subject_key:
- single values: `raised` / `lowered` when the change is > 0.5%, else `reaffirmed`;
- ranges: midpoints decide raised/lowered/reaffirmed; with the midpoint reaffirmed, a width change > 10% is
  `widened` / `narrowed`;
- no earlier fact: `new`; different units or currencies, or a value on only one side: `changed`;
- a withdrawal (P-01 `withdrawn` with its quote) is `changed` with the note "withdrawn" (the diffs table has no
  `withdrawn`/`removed` kind; docs/SPEC_ISSUES.md). Absence of a fact is never a removal.
computed_note: "$38.0B → $45.0B (+18.4%)"; rupees in crore, as the web shows them: "₹371 cr → ₹450 cr (+21.3%)".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

VALUE_TOL = Decimal("0.005")
WIDTH_TOL = Decimal("0.10")
MONEY_UNITS = frozenset({"usd", "usd_per_year"})  # money; the fact's `currency` says which (USD when unstated)
LAKH, CRORE, LAKH_CRORE = Decimal(10) ** 5, Decimal(10) ** 7, Decimal(10) ** 12


@dataclass(frozen=True)
class Value:
    num: Decimal | None
    low: Decimal | None
    high: Decimal | None
    unit: str
    currency: str | None = None

    @property
    def money(self) -> str | None:
        """The currency of a money value (USD when unstated: v1 stored dollars only); None for any other unit."""
        return (self.currency or "USD").upper() if self.unit in MONEY_UNITS else None

    @property
    def mid(self) -> Decimal | None:
        if self.low is not None and self.high is not None:
            return (self.low + self.high) / 2
        return self.num

    @property
    def width(self) -> Decimal | None:
        return self.high - self.low if self.low is not None and self.high is not None else None


@dataclass(frozen=True)
class Diff:
    change_kind: str
    delta_abs: Decimal | None
    delta_pct: Decimal | None
    computed_note: str


def rupees(v: Decimal) -> str:
    """₹2.65 lakh cr, ₹26,458 cr, ₹45.3 cr, ₹3.4 lakh, ₹450 (web/lib/format.ts rupees(); below a lakh crore the
    Indian and Western digit groupings agree)."""
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= LAKH_CRORE or (a / CRORE).quantize(Decimal(1)) >= 10**5:
        return f"{sign}₹{a / LAKH_CRORE:,.2f} lakh cr"
    if a >= CRORE:
        crore = a / CRORE
        return f"{sign}₹{crore:,.0f} cr" if crore >= 100 else f"{sign}₹{crore:,.1f} cr"
    if a >= LAKH:
        lakh = (a / LAKH).quantize(Decimal("0.1"))
        return f"{sign}₹{a / CRORE:,.1f} cr" if lakh >= 100 else f"{sign}₹{lakh:,.1f} lakh"
    return f"{sign}₹{a:,.0f}"


def fmt(v: Decimal | None, unit: str, currency: str | None = None) -> str:
    if v is None:
        return "–"
    if unit in MONEY_UNITS and (currency or "").upper() == "INR":
        return rupees(v)
    if unit in MONEY_UNITS:
        a = abs(v)
        for scale, suffix in ((Decimal(10) ** 12, "T"), (Decimal(10) ** 9, "B"), (Decimal(10) ** 6, "M"),
                              (Decimal(10) ** 3, "K")):  # fmt: skip
            if a >= scale:
                return f"{'-' if v < 0 else ''}${a / scale:.1f}{suffix}"
        return f"${v:.0f}"
    suffix = {"mw": " MW", "gw": " GW", "mwh": " MWh", "percent": "%", "months": " months", "weeks": " weeks",
              "years": " years", "sq_ft": " sq ft"}.get(unit, "")  # fmt: skip
    return f"{v.normalize():f}{suffix}"


def _show(v: Value) -> str:
    if v.low is not None and v.high is not None:
        return f"{fmt(v.low, v.unit, v.currency)}–{fmt(v.high, v.unit, v.currency)}"
    return fmt(v.num, v.unit, v.currency)


def compute(prev: Value | None, new: Value, withdrawn: bool = False) -> Diff:
    if withdrawn:
        return Diff("changed", None, None, f"{_show(prev) if prev else '–'} → withdrawn")
    if prev is None:
        return Diff("new", None, None, f"new: {_show(new)}")
    a, b = prev.mid, new.mid
    if prev.unit != new.unit or prev.money != new.money or a is None or b is None:
        return Diff("changed", None, None, f"{_show(prev)} → {_show(new)}")
    delta = b - a
    pct = (delta / abs(a) * 100).quantize(Decimal("0.1")) if a != 0 else None
    note = f"{_show(prev)} → {_show(new)}" + (f" ({pct:+}%)" if pct is not None else "")
    moved = abs(delta) > VALUE_TOL * abs(a) if a != 0 else delta != 0
    if moved:
        return Diff("raised" if delta > 0 else "lowered", delta, pct, note)
    wa, wb = prev.width, new.width
    if wa is not None and wb is not None and wa > 0 and abs(wb - wa) > WIDTH_TOL * wa:
        return Diff("widened" if wb > wa else "narrowed", delta, pct, note)
    return Diff("reaffirmed", delta, pct, note)
