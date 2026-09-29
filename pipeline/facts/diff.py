"""Fact diffs (Appendix F.6), computed by code, never by an LLM.

For each new verified fact, the latest earlier verified fact of the same company and subject_key:
- single values: `raised` / `lowered` when the change is > 0.5%, else `reaffirmed`;
- ranges: midpoints decide raised/lowered/reaffirmed; with the midpoint reaffirmed, a width change > 10% is
  `widened` / `narrowed`;
- no earlier fact: `new`; different units or a value on only one side: `changed`;
- a withdrawal (P-01 `withdrawn` with its quote) is `changed` with the note "withdrawn" (the diffs table has no
  `withdrawn`/`removed` kind; docs/SPEC_ISSUES.md). Absence of a fact is never a removal.
computed_note: "$38.0B → $45.0B (+18.4%)".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

VALUE_TOL = Decimal("0.005")
WIDTH_TOL = Decimal("0.10")


@dataclass(frozen=True)
class Value:
    num: Decimal | None
    low: Decimal | None
    high: Decimal | None
    unit: str

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


def fmt(v: Decimal | None, unit: str) -> str:
    if v is None:
        return "–"
    if unit in {"usd", "usd_per_year"}:
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
        return f"{fmt(v.low, v.unit)}–{fmt(v.high, v.unit)}"
    return fmt(v.num, v.unit)


def compute(prev: Value | None, new: Value, withdrawn: bool = False) -> Diff:
    if withdrawn:
        return Diff("changed", None, None, f"{_show(prev) if prev else '–'} → withdrawn")
    if prev is None:
        return Diff("new", None, None, f"new: {_show(new)}")
    a, b = prev.mid, new.mid
    if prev.unit != new.unit or a is None or b is None:
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
