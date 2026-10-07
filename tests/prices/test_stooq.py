"""M4-04 (Stooq side): weekly CSV parsing, symbols, and the answers Stooq gives instead of data (BRIEF §4.4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from pipeline.net.http import HttpClient
from pipeline.net.stooq import StooqClient, StooqUnavailable, csv_url, friday_of, parse_csv, stooq_symbol
from pipeline.settings import Settings

PX = Path(__file__).resolve().parents[2] / "fixtures" / "px"


def test_symbols() -> None:
    assert stooq_symbol("AAPL") == "aapl.us" and stooq_symbol("BRK.B") == "brk-b.us" and stooq_symbol("^SPX") == "^spx"
    assert csv_url("^spx") == "https://stooq.com/q/d/l/?s=^spx&i=w"


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


def test_client_reads_through_the_allowlisted_http_client(tmp_path: Path) -> None:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    http.register_mock(csv_url("pwr.us"), (PX / "pwr.us_w.csv").read_bytes())
    bars = StooqClient(http).weekly("PWR")
    assert bars[-1].close == D((PX / "pwr.us_w.csv").read_text().splitlines()[-1].split(",")[4])


def keyed(tmp_path: Path, key: str | None) -> HttpClient:
    settings = Settings(
        database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path, stooq_api_key=key
    )
    return HttpClient(settings)


def test_the_apikey_rides_in_the_url(tmp_path: Path) -> None:
    """Since 2026 Stooq serves the CSV only with an apikey (STOOQ_API_KEY); the first live run got an HTML page."""
    http = keyed(tmp_path, "k3y")
    http.register_mock(csv_url("pwr.us") + "&apikey=k3y", (PX / "pwr.us_w.csv").read_bytes())
    assert StooqClient(http).weekly("PWR")
    assert http.calls == ["https://stooq.com/q/d/l/?s=pwr.us&i=w&apikey=k3y"]


def test_errors_never_carry_the_key(tmp_path: Path) -> None:
    """The errors end up in the runs table, source_health (the web app's Settings) and the digest issue."""
    key = "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    http = keyed(tmp_path, key)
    url = f"{csv_url('pwr.us')}&apikey={key}"
    http.register_error(url, 403)
    with pytest.raises(StooqUnavailable) as failed:
        StooqClient(http).weekly("PWR")
    assert str(failed.value) == "Stooq request failed (403)"
    for page in (f"<html>Bad request: {url}</html>", "x" * 100 + f"apikey={key}"):  # the second is cut at 120
        http.register_mock(url, page.encode())
        with pytest.raises(StooqUnavailable) as answered:
            StooqClient(http).weekly("PWR")
        assert key[:6] not in str(answered.value) and "apikey=***" in str(answered.value)


def test_without_a_key_the_error_says_so(tmp_path: Path) -> None:
    http = keyed(tmp_path, None)
    http.register_mock(csv_url("pwr.us"), b'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots">')
    with pytest.raises(StooqUnavailable, match=r"^STOOQ_API_KEY is not set: <!DOCTYPE html>"):
        StooqClient(http).weekly("PWR")
