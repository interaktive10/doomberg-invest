"""M4-04: Stooq's weekly CSV format, the format of a manual price import (imports/us_prices/<TICKER>.csv) since US
prices come from Yahoo (docs/SPEC_ISSUES.md 37), and the answers Stooq gave instead of data (BRIEF §4.4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pipeline.net.stooq import StooqUnavailable, friday_of, parse_csv

PX = Path(__file__).resolve().parents[2] / "fixtures" / "px"


def test_bars_are_keyed_by_friday() -> None:
    bars = parse_csv((PX / "aapl.us_w.csv").read_bytes())
    assert len(bars) == 260 and all(b.week_end.weekday() == 4 for b in bars)
    assert bars[-1].week_end == date(2026, 9, 18) and bars[0].volume is not None
    assert friday_of(date(2026, 9, 17)) == date(2026, 9, 18) and friday_of(date(2026, 9, 20)) == date(2026, 9, 18)


def test_index_file_has_no_volume() -> None:
    bars = parse_csv((PX / "_spx_w.csv").read_bytes())
    assert bars and all(b.volume is None for b in bars)


@pytest.mark.parametrize("name", ["no_data.txt", "limit.txt"])
def test_non_csv_answers_raise(name: str) -> None:
    with pytest.raises(StooqUnavailable):
        parse_csv((PX / name).read_bytes())
