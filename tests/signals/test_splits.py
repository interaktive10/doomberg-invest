"""M4-04 (split detection): a price jump is adjusted only when the share count confirms it (BRIEF §4.4)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

from pipeline.prices.bars import parse_csv
from pipeline.prices.splits import (
    RATIOS,
    TOL,
    SourceSplit,
    adjust,
    date_source_split,
    price_jumps,
    rebased,
    split_ratio,
)

FRIDAYS = [date(2026, 1, 2) + timedelta(weeks=i) for i in range(20)]


def closes(split_week: int | None, ratio: str = "2") -> list[tuple[date, D]]:
    after = split_week if split_week is not None else len(FRIDAYS)
    return [(d, D(100) / (D(ratio) if i >= after else 1)) for i, d in enumerate(FRIDAYS)]


QUARTERS = [date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]


def test_standard_ratios() -> None:
    assert split_ratio(D("2.02")) == D(2) and split_ratio(D("1.49")) == D("1.5") and split_ratio(D("0.1")) == D("0.1")
    assert split_ratio(D("1.8")) is None and split_ratio(D("1.1")) is None


def test_confirmed_split_adjusts_history() -> None:
    shares = list(zip(QUARTERS, (D(100), D(100), D(200)), strict=True))  # doubled by the June quarter
    a = adjust(closes(10), shares)  # the price halves in week 10 (2026-03-13)
    assert [j.week_end for j in a.confirmed] == [FRIDAYS[10]] and a.unconfirmed == []
    assert {v for v in a.adj_close.values()} == {D(50)}  # one continuous series on today's basis
    assert a.share_factor(date(2026, 3, 31)) == D(2) and a.share_factor(date(2026, 6, 30)) == D(1)


def test_unconfirmed_jump_is_flagged_not_adjusted() -> None:
    shares = list(zip(QUARTERS, (D(100), D(100), D(101)), strict=True))  # no share-count change: a crash, not a split
    a = adjust(closes(10), shares)
    assert a.confirmed == [] and [j.week_end for j in a.unconfirmed] == [FRIDAYS[10]]
    assert a.adj_close[FRIDAYS[0]] == D(100)  # never silently adjusted


def test_split_without_a_price_jump_means_prices_were_already_adjusted() -> None:
    """Twelve Data's history is split-adjusted: no jump, but older share counts move to today's basis."""
    shares = list(zip(QUARTERS, (D(100), D(100), D(300)), strict=True))
    a = adjust(closes(None), shares)
    assert a.confirmed == [] and a.unconfirmed == [] and a.adj_close[FRIDAYS[0]] == D(100)
    assert a.share_factor(date(2025, 12, 31)) == D(3)


def test_bonus_issue_one_for_one_and_a_consolidation() -> None:
    bonus = adjust(closes(5, "2"), list(zip(QUARTERS, (D(10), D(20), D(20)), strict=True)))
    assert len(bonus.confirmed) == 1
    merge = [(d, D(10) * (10 if i >= 5 else 1)) for i, d in enumerate(FRIDAYS)]  # 1:10 consolidation
    cons = adjust(merge, list(zip(QUARTERS, (D(1000), D(100), D(100)), strict=True)))
    assert [j.ratio for j in cons.confirmed] == [D("0.1")] and cons.adj_close[FRIDAYS[0]] == D(100)


def test_f_px_jbl_split_week_is_an_exact_two_for_one_drop() -> None:
    """The scoring-run test flags JBL's week-150 drop: the fixture halves the close with no market move on top
    (a 2:1 drop times one week's move fell outside the 3% tolerance and was never detected)."""
    csv = Path(__file__).resolve().parents[2] / "fixtures" / "px" / "jbl.us_w.csv"
    bars = parse_csv(csv.read_bytes())
    jumps = price_jumps([(b.week_end, b.close) for b in bars])
    assert [(j.week_end, j.ratio) for j in jumps] == [(bars[150].week_end, D(2))]


def test_any_whole_split_ratio_up_to_fifty_and_the_nearest_wins() -> None:
    """M8 review R1-F1: AAPL's 7:1 (2014), GE's 1:8 (2021) and CMG's 50:1 (2024) are splits too."""
    assert split_ratio(D("6.9515")) == D(7) and split_ratio(D("0.126")) == D(1) / D(8)
    assert split_ratio(D("50.4")) == D(50) and split_ratio(D(41)) == D(41)  # the nearest ratio, not the first in 3%
    assert split_ratio(D("1.8")) is None and split_ratio(D("1.1")) is None and split_ratio(D("60")) is None
    seven = adjust(closes(10, "7"), list(zip(QUARTERS, (D(100), D(100), D(700)), strict=True)))
    assert [j.ratio for j in seven.confirmed] == [D(7)] and seven.share_factor(date(2025, 12, 31)) == D(7)


# ---------------------------------------------------------------- a split-adjusted source (M4 review R1-F6)

NVDA_SHARES = D("2460000000")  # the pre-split count the last 10-Q reported


def test_adjusted_source_rebased_history_is_a_split_before_any_filing_shows_it() -> None:
    """A split-adjusted source re-adjusts its whole history for a 10:1 split: every stored close is 10x the fresh one.
    Until the next 10-Q reports the new count, market cap is price x the pre-split count x 10, never price x the
    pre-split count."""
    stored = [(d, D(1200)) for d in FRIDAYS[:19]]
    fresh = [(d, D(120)) for d in FRIDAYS]  # the split took effect in the new week
    split = rebased(stored, fresh)
    assert split == SourceSplit(FRIDAYS[19], D(10))
    shares = [(q, NVDA_SHARES) for q in QUARTERS[:2]]
    a = adjust(fresh, shares, [split])
    assert a.pending == [split] and a.confirmed == [] and a.unconfirmed == []
    assert a.adj_close[FRIDAYS[19]] * NVDA_SHARES * a.share_factor(QUARTERS[1]) == D("2.952E12")
    # the June 10-Q reports the post-split count: the share split confirms it, and the factor isn't applied twice
    later = adjust(fresh, [*shares, (QUARTERS[2], NVDA_SHARES * 10)], [split])
    assert later.pending == [] and later.share_factor(QUARTERS[2]) == 1 and later.share_factor(QUARTERS[1]) == 10


def test_adjusted_source_lagging_or_corrected_histories() -> None:
    # the source priced two weeks after the split before re-adjusting: those weeks already agree
    stored = [(d, D(1200) if i < 17 else D(120)) for i, d in enumerate(FRIDAYS[:19])]
    assert rebased(stored, [(d, D(120)) for d in FRIDAYS]) == SourceSplit(FRIDAYS[17], D(10))
    # a 1:8 consolidation: the old closes were an eighth of the new ones
    assert rebased([(d, D(10)) for d in FRIDAYS[:19]], [(d, D(80)) for d in FRIDAYS]) == SourceSplit(
        FRIDAYS[19], D(1) / D(8)
    )
    fresh = [(d, D(100)) for d in FRIDAYS]
    assert rebased([(d, D("100.4")) for d in FRIDAYS[:19]], fresh) is None  # a dividend re-adjustment
    assert rebased([(d, D(100) if i != 7 else D(200)) for i, d in enumerate(FRIDAYS)], fresh) is None  # a fix
    assert rebased([], fresh) is None and rebased(fresh, fresh) is None


def test_adjusted_source_after_a_gap_in_the_stored_history() -> None:
    """M4 review R2-F2: the stored closes stop at 2026-01-02 (the company left the candidate set) and the download
    comes back rebased 10:1. The split is dated at the newest week, not the gap's first, so the pre-split counts
    known so far are all multiplied; when a 10-Q shows the 10x count, the share split takes over (no x100)."""
    weeks = [date(2025, 10, 3) + timedelta(weeks=i) for i in range(51)]  # to 2026-09-18
    stored = [(d, D(1200)) for d in weeks if d <= date(2026, 1, 2)]
    fresh = [(d, D(120)) for d in weeks]
    split = rebased(stored, fresh)
    assert split == SourceSplit(date(2026, 9, 18), D(10), since=date(2026, 1, 9))
    counts = [(date(2025, 12, 31), NVDA_SHARES), (date(2026, 3, 31), NVDA_SHARES), (date(2026, 6, 30), NVDA_SHARES)]
    stored_split = date_source_split(split, counts, weeks)  # no filing shows it yet: the newest week
    assert stored_split == SourceSplit(date(2026, 9, 18), D(10))
    a = adjust(fresh, counts, [stored_split])
    assert a.pending == [stored_split] and a.share_factor(date(2026, 6, 30)) == 10  # market cap x10, never x1
    later = adjust(fresh, [*counts, (date(2026, 9, 30), NVDA_SHARES * 10)], [stored_split])
    assert later.pending == [] and later.share_factor(date(2025, 12, 31)) == 10


def test_adjusted_source_split_in_a_gap_that_a_filing_already_reported() -> None:
    """M4 review R3-F1 (the mirror of R2-F2): the stored closes stop at 2026-01-02, the split happened in February,
    and the March and June 10-Qs already report the 10x count. The share split confirms the source split: it is
    stored inside the share split's window, nothing stays pending, the June count is on today's basis (factor 1) and
    the December count x10."""
    weeks = [date(2025, 10, 3) + timedelta(weeks=i) for i in range(51)]  # to 2026-09-18
    stored = [(d, D(1200)) for d in weeks if d <= date(2026, 1, 2)]
    fresh = [(d, D(120)) for d in weeks]
    split = rebased(stored, fresh)
    assert split == SourceSplit(date(2026, 9, 18), D(10), since=date(2026, 1, 9))
    counts = [(date(2025, 12, 31), NVDA_SHARES), (date(2026, 3, 31), NVDA_SHARES * 10),
              (date(2026, 6, 30), NVDA_SHARES * 10)]  # fmt: skip
    stored_split = date_source_split(split, counts, weeks)
    assert stored_split == SourceSplit(date(2026, 1, 9), D(10))
    a = adjust(fresh, counts, [stored_split])
    assert a.pending == [] and a.share_factor(date(2026, 6, 30)) == 1 and a.share_factor(date(2025, 12, 31)) == 10
    assert a.adj_close[date(2026, 9, 18)] * NVDA_SHARES * 10 * a.share_factor(date(2026, 6, 30)) == D(120) * (
        NVDA_SHARES * 10
    )  # market cap: close x the June count
    # a share split of the same ratio long before the gap (2020) is not this one
    old = [(date(2020, 3, 31), NVDA_SHARES // 10), (date(2020, 6, 30), NVDA_SHARES), *counts[:1]]
    assert date_source_split(split, old, weeks) == SourceSplit(date(2026, 9, 18), D(10))


def test_split_ratio_checks_only_the_nearest_ratios() -> None:
    """M4 review R3 idea (speed): split_ratio tries the ratios either side of r and 1/r, with the same answer as
    trying every ratio in RATIOS (this runs for every pair of consecutive counts)."""

    def every(r: D) -> D | None:
        best: tuple[D, D] | None = None
        for k in RATIOS:
            for ratio, dist in ((k, abs(r / k - 1)), (1 / k, abs(r * k - 1))):
                if dist <= TOL and (best is None or dist < best[0]):
                    best = (dist, ratio)
        return None if best is None else best[1]

    probes = [D(k) * D(f) for k in range(1, 55) for f in ("0.97", "0.9701", "0.985", "1", "1.02999", "1.03", "1.0301")]
    probes += [1 / p for p in probes] + [D("1.46"), D("51.4"), D("51.6"), D("0.0195"), D("7.1"), D("1.2")]
    assert all(split_ratio(p) == every(p) for p in probes)
