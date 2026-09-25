"""SEC companyfacts JSON -> typed facts for the fundamentals_q columns (BRIEF §4.1.2).

Each column has an ordered list of alternatives (config/signals.yaml xbrl_map). The fallback is applied per period,
not per company: filers switch concepts over time (Apple reported revenue as SalesRevenueNet until 2018, Revenues in
2018 and RevenueFromContractWithCustomerExcludingAssessedTax since), so "first present wins" for each period. An
alternative can be a sum (a list): its first concept must be present for the period, the others are added when
present (total debt = noncurrent + current maturities + commercial paper).

Only 10-K and 10-Q family filings (and their amendments) feed fundamentals. `fy`/`fp` on a fact describe the filing
that reported it, not the fact's own period, so periods always come from start/end dates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pipeline.us.submissions import end_of_day_utc


class Kind(Enum):
    FLOW = "flow"  # additive over time: quarters from 3-month values, YTD differences, Q4 = FY - Q1 - Q2 - Q3
    AVERAGE = "average"  # weighted average over the period (diluted shares): not additive
    INSTANT = "instant"  # balance-sheet value at the quarter end
    COVER = "cover"  # cover-page value (dei), dated after the period; keyed by the filing's report period


COLUMN_KIND: dict[str, Kind] = {
    "revenue": Kind.FLOW,
    "op_income": Kind.FLOW,
    "net_income": Kind.FLOW,
    "pretax_income": Kind.FLOW,
    "tax_expense": Kind.FLOW,
    "cfo": Kind.FLOW,
    "capex": Kind.FLOW,
    "da": Kind.FLOW,
    "interest_expense": Kind.FLOW,
    "diluted_shares": Kind.AVERAGE,
    "total_assets": Kind.INSTANT,
    "cash": Kind.INSTANT,
    "total_debt": Kind.INSTANT,
    "equity": Kind.INSTANT,
    "receivables": Kind.INSTANT,
    "inventory": Kind.INSTANT,
    "deferred_revenue": Kind.INSTANT,
    "rpo": Kind.INSTANT,
    "shares_outstanding": Kind.COVER,
}
SHARE_COLUMNS = frozenset({"diluted_shares", "shares_outstanding"})
FUNDAMENTAL_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A", "10-QT", "10-QT/A"})
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A"})


@dataclass(frozen=True)
class Fact:
    column: str
    rank: int  # position of the alternative in the column's fallback list; 0 wins
    part: int  # position of the concept inside a summed alternative (0 = the required one)
    start: date | None  # None for instants
    end: date
    val: Decimal
    accn: str
    form: str
    fy: int | None
    fp: str | None
    filed_at: datetime  # acceptance time (UTC), or the conservative end-of-filing-date fallback

    @property
    def days(self) -> int | None:
        return (self.end - self.start).days if self.start else None


def _unit_for(column: str) -> str:
    return "shares" if column in SHARE_COLUMNS else "USD"


Alternative = str | Sequence[str]


def alternatives(spec: Sequence[Alternative]) -> list[list[str]]:
    """xbrl_map entry -> [[concept, ...], ...]; a bare string is a one-concept alternative."""
    return [[a] if isinstance(a, str) else list(a) for a in spec]


def load_facts(
    doc: Mapping[str, Any],
    xbrl_map: Mapping[str, Sequence[Alternative]],
    accepted: Mapping[str, datetime],
) -> tuple[list[Fact], list[str]]:
    """All usable facts for the mapped columns, plus notes on what was skipped (e.g. non-USD units)."""
    facts: list[Fact] = []
    notes: list[str] = []
    seen: set[tuple[str, int, int, date | None, date, str]] = set()
    all_facts = doc.get("facts") or {}
    for column, spec in xbrl_map.items():
        if column not in COLUMN_KIND:
            continue  # config keys that are not fundamentals_q columns
        unit = _unit_for(column)
        for rank, concepts in enumerate(alternatives(spec)):
            for part, qualified in enumerate(concepts):
                facts.extend(_concept_facts(all_facts, column, rank, part, qualified, unit, accepted, seen, notes))
    return facts, notes


def _concept_facts(
    all_facts: Mapping[str, Any],
    column: str,
    rank: int,
    part: int,
    qualified: str,
    unit: str,
    accepted: Mapping[str, datetime],
    seen: set[tuple[str, int, int, date | None, date, str]],
    notes: list[str],
) -> list[Fact]:
    ns, _, name = qualified.rpartition(":")
    item = (all_facts.get(ns or "us-gaap") or {}).get(name)
    if not item:
        return []
    units = item.get("units") or {}
    if unit not in units:
        if units:
            notes.append(f"{qualified}: units {sorted(units)} skipped (expected {unit})")
        return []
    out: list[Fact] = []
    for f in units[unit]:
        form = str(f.get("form", ""))
        if form not in FUNDAMENTAL_FORMS or f.get("val") is None:
            continue
        accn = str(f["accn"])
        start = date.fromisoformat(f["start"]) if f.get("start") else None
        end = date.fromisoformat(f["end"])
        key = (column, rank, part, start, end, accn)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Fact(
                column=column,
                rank=rank,
                part=part,
                start=start,
                end=end,
                val=Decimal(str(f["val"])),
                accn=accn,
                form=form,
                fy=int(f["fy"]) if f.get("fy") is not None else None,
                fp=f.get("fp"),
                filed_at=accepted.get(accn) or end_of_day_utc(date.fromisoformat(f["filed"])),
            )
        )
    return out
