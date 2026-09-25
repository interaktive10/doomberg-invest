"""Splits and bonus issues in weekly prices (BRIEF §4.4): a price discontinuity is adjusted only when a matching
share-count change confirms it. Unconfirmed jumps are flagged and never adjusted.

- A share split is a change between consecutive share counts within 3% of a split ratio: every whole ratio from 2:1
  to 50:1, and 3:2 and 5:2, or the reverse for a consolidation; the nearest one wins. Real splits aren't only the
  standard ones (AAPL 7:1 in 2014, GE 1:8 in 2021, CMG 50:1 in 2024; M8 review R1-F1), and a missed split rescales
  every earlier market cap by its ratio.
- A price jump is a week-over-week move whose inverse is within 3% of such a ratio.
- A jump inside a split's window (from a month before the last old-count period end to 120 days after the first
  new-count period end, to allow for reporting lag) is confirmed: closes before it are divided by the ratio.
- A split with no jump in the prices means the source is already adjusted (Stooq): prices stay as they are, and
  older share counts are multiplied by the ratio so market caps use the current share basis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

RATIOS = tuple(sorted({Decimal(n) for n in range(2, 51)} | {Decimal("1.5"), Decimal("2.5")}))
TOL = Decimal("0.03")
BEFORE_DAYS, AFTER_DAYS = 30, 120


def split_ratio(r: Decimal) -> Decimal | None:
    """r = new count / old count (or old price / new price). The standard ratio it matches, or None."""
    if r <= 0:
        return None
    best: tuple[Decimal, Decimal] | None = None  # (distance, ratio)
    for k in RATIOS:
        for ratio, dist in ((k, abs(r / k - 1)), (1 / k, abs(r * k - 1))):  # a split, or a consolidation
            if dist <= TOL and (best is None or dist < best[0]):
                best = (dist, ratio)
    return None if best is None else best[1]


@dataclass(frozen=True)
class ShareSplit:
    old_end: date  # the last period end with the old share count
    new_end: date  # the first period end with the new count
    ratio: Decimal  # new shares per old share


@dataclass(frozen=True)
class Jump:
    week_end: date  # the first week at the new price level
    ratio: Decimal  # old price / new price


def share_splits(shares: Sequence[tuple[date, Decimal]]) -> list[ShareSplit]:
    rows = sorted((d, v) for d, v in shares if v and v > 0)
    out = []
    for (d0, v0), (d1, v1) in zip(rows, rows[1:], strict=False):
        k = split_ratio(v1 / v0)
        if k is not None:
            out.append(ShareSplit(d0, d1, k))
    return out


def price_jumps(closes: Sequence[tuple[date, Decimal]]) -> list[Jump]:
    rows = sorted((d, c) for d, c in closes if c > 0)
    out = []
    for (d0, c0), (d1, c1) in zip(rows, rows[1:], strict=False):
        if (d1 - d0).days > 14:
            continue  # a gap in the history: the move can't be dated
        k = split_ratio(c0 / c1)
        if k is not None:
            out.append(Jump(d1, k))
    return out


@dataclass(frozen=True)
class Adjusted:
    adj_close: dict[date, Decimal]
    confirmed: list[Jump]
    unconfirmed: list[Jump]
    splits: list[ShareSplit]

    def share_factor(self, period_end: date) -> Decimal:
        """Multiplier putting a share count reported for `period_end` on today's basis."""
        f = Decimal(1)
        for s in self.splits:
            if s.old_end >= period_end:
                f *= s.ratio
        return f


def matches(j: Jump, s: ShareSplit) -> bool:
    in_window = s.old_end - timedelta(days=BEFORE_DAYS) <= j.week_end <= s.new_end + timedelta(days=AFTER_DAYS)
    return in_window and abs(s.ratio / j.ratio - 1) <= TOL


def adjust(closes: Sequence[tuple[date, Decimal]], shares: Sequence[tuple[date, Decimal]]) -> Adjusted:
    splits = share_splits(shares)
    confirmed: list[Jump] = []
    unconfirmed: list[Jump] = []
    for j in price_jumps(closes):
        (confirmed if any(matches(j, s) for s in splits) else unconfirmed).append(j)
    adj = {}
    for d, c in closes:
        f = Decimal(1)
        for j in confirmed:
            if j.week_end > d:
                f *= j.ratio
        adj[d] = c / f
    return Adjusted(adj, confirmed, unconfirmed, splits)
