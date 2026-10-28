"""P8 price order (pipeline/signals/weekly.py price_targets; overhaul PR 1, docs/DECISIONS.log). At most §4.4's 400
symbols are priced a week (Twelve Data answers 8 a minute), so the order decides who gets a Gap: research entries,
theses and positions first at any Evidence (before P8 a thesis below 40 could be cut by higher-Evidence names), then
names that can reach a bucket, then one-family filler, which can't, up to US_PRICE_FILL_MAX symbols with the
benchmarks."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from pipeline.db.models import Company
from pipeline.signals import weekly
from pipeline.signals.scores import Evidence
from pipeline.signals.series import Series

ROOT = Path(__file__).resolve().parents[2]
SCORES = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["scores"]
MIN_EV = Decimal(str(SCORES["us_price_candidate_min_evidence"]))  # 40
MIN_FAMILIES = int(SCORES["min_families"])  # 2
BENCHMARKS = len(yaml.safe_load((ROOT / "config" / "context.yaml").read_text(encoding="utf-8"))["benchmarks"]["us"])
CAP = weekly.US_PRICE_MAX_SYMBOLS - BENCHMARKS  # 388 companies beside the 12 benchmarks
FILL = weekly.US_PRICE_FILL_MAX - BENCHMARKS  # 238: where one-family filler stops
FAMILIES = ("fundamentals", "behavior", "text", "structural")


def name(n: int, evidence: float, families: int = 2, hard: bool = False, market: str = "us",
         ticker: str | None = "T") -> weekly.Scored:  # fmt: skip
    """Company n (its id is UUID(int=n), so ids sort like n) with this week's Evidence."""
    c = Company(id=UUID(int=n), market=market, name=f"Company {n}", ticker=None if ticker is None else f"{ticker}{n}")
    e = Evidence(Decimal(str(evidence)), Decimal(0), {}, FAMILIES[:families], 0, families < MIN_FAMILIES)
    return weekly.Scored(c, Series([], market), e, hard, {}, None, {})


def pool(*groups: Iterable[weekly.Scored]) -> dict[UUID, weekly.Scored]:
    return {sc.company.id: sc for g in groups for sc in g if sc.company.id is not None}


def targets(scored: dict[UUID, weekly.Scored], research: Collection[int] = (),
            last_week: Collection[int] = ()) -> list[int]:  # fmt: skip
    got = weekly.price_targets(scored, {UUID(int=n) for n in research}, {UUID(int=n) for n in last_week}, MIN_EV,
                               MIN_FAMILIES, BENCHMARKS)  # fmt: skip
    return [sc.company.id.int for sc in got if sc.company.id is not None]


def test_the_caps_are_the_brief_and_p8s() -> None:
    assert (BENCHMARKS, CAP, FILL) == (12, 388, 238)


def test_a_thesis_at_evidence_10_is_kept_against_500_rivals() -> None:
    rivals = [name(n, 60 + n % 40, families=3) for n in range(1, 501)]  # all can reach a bucket
    got = targets(pool([name(1000, 10, families=1)], rivals), research=[1000])
    assert got[0] == 1000 and len(got) == CAP


def test_a_two_family_45_ranks_before_a_one_family_50() -> None:
    assert targets(pool([name(1, 50, families=1), name(2, 45, families=2)])) == [2, 1]


def test_a_hard_flagged_name_stays_in_tier_2() -> None:
    hard = name(1, 90, families=3, hard=True)
    assert targets(pool([hard, name(2, 41), name(3, 50, families=1)])) == [2, 1, 3]  # by Evidence within tier 2
    bucketable = [name(n, 41) for n in range(10, 10 + FILL)]
    got = targets(pool([hard], bucketable))
    assert len(got) == FILL and 1 not in got  # the fill is spent: no Gap, it is Excluded anyway


def test_tier_2_stops_at_the_fill() -> None:
    one_family = [name(n, 40 + n % 16, families=1) for n in range(1, 501)]
    got = targets(pool(one_family))
    assert len(got) == FILL
    assert min(Decimal(40 + n % 16) for n in got) >= max(Decimal(40 + n % 16) for n in range(1, 501) if n not in got)
    bucketable = [name(n, 45) for n in range(1001, 1101)]
    got = targets(pool(one_family, bucketable))
    assert len(got) == FILL and got[:100] == list(range(1001, 1101))  # 100 that can reach a bucket, then 138 filler


def test_watch_names_are_priced_with_the_names_that_can_reach_a_bucket() -> None:
    """SPEC_ISSUES 56: a one-family name that can reach Watch (buckets.watchable) needs a Gap, so it is priced in tier
    1, beyond the filler's cap; the other one-family names of the same Evidence wait for what's left of the fill."""
    filler = [name(n, 50, families=1) for n in range(1, 501)]
    watch = [name(n, 50, families=1) for n in range(1001, 1301)]
    got = weekly.price_targets(pool(filler, watch), set(), set(), MIN_EV, MIN_FAMILIES, BENCHMARKS,
                               watch={UUID(int=n) for n in range(1001, 1301)})  # fmt: skip
    assert [sc.company.id.int for sc in got if sc.company.id is not None] == list(range(1001, 1301))  # 300 > FILL
    few = weekly.price_targets(pool(filler, watch[:10]), set(), set(), MIN_EV, MIN_FAMILIES, BENCHMARKS,
                               watch={UUID(int=n) for n in range(1001, 1011)})  # fmt: skip
    ids = [sc.company.id.int for sc in few if sc.company.id is not None]
    assert ids[:10] == list(range(1001, 1011)) and len(ids) == FILL  # then filler up to the fill


def test_last_weeks_names_come_after_this_weeks_filler() -> None:
    """§4.4's candidate set is Evidence >= 40 this week or last; a name only last week's can't reach a bucket now."""
    got = targets(pool([name(1, 39), name(2, 40, families=1), name(3, 12)]), last_week=[1, 3, 4])
    assert got == [2, 1, 3]  # 4 isn't scored this week (no row: nothing to price)


def test_never_above_388() -> None:
    research = [name(n, 5, families=0) for n in range(1, 301)]
    bucketable = [name(n, 80) for n in range(1001, 1301)]
    got = targets(pool(research, bucketable), research=range(1, 301))
    assert len(got) == CAP and got[:300] == list(range(1, 301))
    assert len(targets(pool(bucketable, [name(n, 99) for n in range(2001, 2201)]))) == CAP


def test_ties_break_by_id() -> None:
    same = [name(n, 50) for n in (7, 3, 5)] + [name(n, 47, families=1) for n in (9, 8)]
    assert targets(pool(same)) == [3, 5, 7, 8, 9]
    assert targets(pool([name(n, 5, families=0) for n in (4, 2)]), research=[4, 2]) == [2, 4]


def test_only_us_names_with_a_ticker_are_asked() -> None:
    names = [name(1, 90, market="in"), name(2, 90, ticker=None), name(3, 90)]
    assert targets(pool(names), research=[1, 2]) == [3]


CASES = {  # names that can reach a bucket, one-family names -> staged names priced
    "2026-10-09": (16, 440, 238),
    "all-one-family": (0, 500, 238),
    "small-stage": (5, 20, 31),
    "no-room-for-filler": (238, 300, 244),
    "over-the-cap": (400, 0, 388),
}


@pytest.mark.parametrize(("bucketable", "filler", "priced"), CASES.values(), ids=CASES.keys())
def test_c3s_comparison_group_stays_at_30_or_more(bucketable: int, filler: int, priced: int) -> None:
    """C3 ranks a staged name's 52-week return among the stage's names priced this week plus the benchmarks
    (context_rows); overhaul PR 2 makes it null below a group of 30. 2026-10-09's stage had 456 names, 440 of them
    one-family. Six research entries below 40 are staged too; 150 names only last week's are not."""
    stage = [name(n, 40 + n % 40, families=2) for n in range(1, bucketable + 1)]
    stage += [name(n, 40 + n % 16, families=1) for n in range(1001, filler + 1001)]
    research = [name(n, 20, families=1) for n in range(5001, 5007)]
    last_week = [name(n, 30, families=1) for n in range(6001, 6151)]
    got = targets(pool(stage, research, last_week), research=range(5001, 5007), last_week=range(6001, 6151))
    staged = [n for n in got if n < 6001]
    assert len(staged) == priced and len(staged) + BENCHMARKS >= 30
