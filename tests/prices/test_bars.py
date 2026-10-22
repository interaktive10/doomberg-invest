"""M4-04: the manual price import's weekly CSV (imports/us_prices/<TICKER>.csv, BRIEF §4.4's fallback; the format
Stooq's weekly CSV had), read by pipeline/prices/bars.py since the Stooq client went (docs/SPEC_ISSUES.md 52)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pipeline.prices.bars import NotWeeklyCsv, friday_of, parse_csv

PX = Path(__file__).resolve().parents[2] / "fixtures" / "px"


def test_bars_are_keyed_by_friday() -> None:
    bars = parse_csv((PX / "aapl.us_w.csv").read_bytes())
    assert len(bars) == 260 and all(b.week_end.weekday() == 4 for b in bars)
    assert bars[-1].week_end == date(2026, 9, 18) and bars[0].volume is not None
    assert friday_of(date(2026, 9, 17)) == date(2026, 9, 18) and friday_of(date(2026, 9, 20)) == date(2026, 9, 18)


def test_index_file_has_no_volume() -> None:
    bars = parse_csv((PX / "_spx_w.csv").read_bytes())
    assert bars and all(b.volume is None for b in bars)


@pytest.mark.parametrize("body", [b"No data", b"Exceeded the daily hits limit", b"", b"Date,Close\n"])
def test_a_file_that_is_not_a_weekly_csv_raises(body: bytes) -> None:
    with pytest.raises(NotWeeklyCsv):
        parse_csv(body)
