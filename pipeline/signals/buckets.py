"""Buckets and the weekly shortlist (BRIEF §1.7, §4.8).

| Bucket    | Rule                                                              |
| candidate | Evidence >= 60, Gap >= 50, no hard red flag                       |
| priced_in | Evidence >= 60, Gap < 50                                          |
| early     | Evidence 40-59 (below the candidate bar) with >= 2 families, Gap >= 50 |
| excluded  | any hard red flag                                                 |
| none      | anything else: Gap unknown, below the market-cap floor, weak evidence |

The shortlist takes at most 10 new candidates a week across both markets and desks, ranked by Evidence then Gap,
skipping any company shortlisted in the previous 12 weeks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

Bucket = Literal["candidate", "priced_in", "early", "excluded", "none"]


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
        _d(early["min_evidence"]) <= evidence < _d(cand["min_evidence"])
        and n_families >= int(early["min_families"])
        and gap >= _d(early["min_gap"])
    ):
        return "early"
    return "none"


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


def families_list(families: Sequence[str]) -> list[str]:
    return sorted(families)
