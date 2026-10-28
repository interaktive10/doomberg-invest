"""Buckets and the weekly shortlist (BRIEF §1.7, §4.8).

| Bucket    | Rule                                                              |
| candidate | Evidence >= 60, Gap >= 50, no hard red flag                       |
| priced_in | Evidence >= 60, Gap < 50                                          |
| early     | Evidence 40-59 (40 <= E < 60) with >= 2 families, Gap >= 50           |
| watch     | one family at full strength (Evidence 50), no red flag, revenue up, Gap >= 60: each market's top few |
| excluded  | any hard red flag                                                 |
| none      | anything else: Gap unknown, below the market-cap floor, weak evidence |

The shortlist takes at most 10 new candidates a week across both markets and desks, ranked by Evidence then Gap,
skipping any company shortlisted in the previous 12 weeks.

Watch (docs/SPEC_ISSUES.md 56) is for the names the two-family rule leaves out: one kind of evidence as strong as it
gets, nothing against it, a growing business and a price that hasn't followed. Not enough to act on, so only a few per
market get it (config/signals.yaml `scores.buckets.watch.per_market`): the deeper ones first (more of the family's
signals agree), then last week's Watch names (a list that doesn't churn), then the larger Gap."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

Bucket = Literal["candidate", "priced_in", "early", "watch", "excluded", "none"]


def _d(x: object) -> Decimal:
    return Decimal(str(x))


def bucket(
    evidence: Decimal,
    gap: Decimal | None,
    n_families: int,
    hard_flag: bool,
    cfg: Mapping[str, Any],
    market_cap_ok: bool = True,
) -> Bucket:
    """cfg is config/signals.yaml `scores.buckets`."""
    if hard_flag:
        return "excluded"
    if gap is None or not market_cap_ok:
        return "none"
    cand, pin, early = cfg["candidate"], cfg["priced_in"], cfg["early"]
    if evidence >= _d(cand["min_evidence"]) and gap >= _d(cand["min_gap"]):
        return "candidate"
    if evidence >= _d(pin["min_evidence"]) and gap < _d(pin["max_gap_exclusive"]):
        return "priced_in"
    if (
        _d(early["min_evidence"]) <= evidence < _d(early["max_evidence"]) + 1  # "40-59": 59.9 is still early
        and n_families >= int(early["min_families"])
        and gap >= _d(early["min_gap"])
    ):
        return "early"
    return "none"


def watchable(
    evidence: Decimal, n_families: int, hard: bool, revenue_yoy: Decimal | None, cfg: Mapping[str, Any]
) -> bool:
    """Watch's evidence side, known before prices (the US prices these first, P8): one family (max_families) at
    Evidence >= min_evidence, no hard flag, TTM revenue up on a year (known, >= min_revenue_yoy). cfg is
    `scores.buckets.watch`."""
    return (
        not hard
        and 1 <= n_families <= int(cfg["max_families"])
        and evidence >= _d(cfg["min_evidence"])
        and revenue_yoy is not None
        and revenue_yoy >= _d(cfg["min_revenue_yoy"])
    )


@dataclass(frozen=True)
class WatchName:
    company_id: UUID
    market: str
    depth: int  # how many of its family's signals fired
    incumbent: bool  # on last week's Watch list
    gap: Decimal


def watch_list(names: Iterable[WatchName], per_market: Mapping[str, Any]) -> list[WatchName]:
    """Each market's Watch names (the bucket would be `none` otherwise, with Gap >= min_gap and the market cap ok):
    the deeper first, then last week's, then the larger Gap, then id; at most per_market[market]."""
    by_market: dict[str, list[WatchName]] = defaultdict(list)
    for n in names:
        by_market[n.market].append(n)
    out: list[WatchName] = []
    for market, rows in sorted(by_market.items()):
        ranked = sorted(rows, key=lambda n: (-n.depth, not n.incumbent, -n.gap, str(n.company_id)))
        out += ranked[: int(per_market.get(market, 0))]
    return out


@dataclass(frozen=True)
class Ranked:
    company_id: UUID
    evidence: Decimal
    gap: Decimal | None
    bucket: str


def shortlist(rows: Iterable[Ranked], recently_shortlisted: set[UUID], limit: int) -> list[Ranked]:
    """New candidates only (not shortlisted in the novelty window), best Evidence first, then Gap."""
    new = [r for r in rows if r.bucket == "candidate" and r.company_id not in recently_shortlisted]
    return sorted(new, key=lambda r: (-r.evidence, -(r.gap or Decimal(0)), str(r.company_id)))[:limit]


def market_cap_ok(market: str, market_cap: Decimal | None, universe_cfg: Mapping[str, Mapping[str, Any]]) -> bool:
    """§1.3: US market cap >= $300M, India >= Rs 500 crore, applied at the candidate stage. Unknown -> not ok."""
    key = {"us": "candidate_min_mcap_usd", "in": "candidate_min_mcap_inr"}[market]
    return market_cap is not None and market_cap >= _d(universe_cfg[market][key])
