"""Benchmarks (BRIEF §4.4): NSE's index-close file (real, 2026-06-05) and the US histories from Yahoo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path

from pipeline.net.http import HttpClient
from pipeline.net.stooq import parse_csv
from pipeline.net.yahoo import HOSTS, YahooClient, chart_url
from pipeline.prices.benchmarks import fetch_us, index_close_url, india_rows, parse_index_closes, us_rows
from pipeline.settings import Settings

ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def test_nse_index_closes() -> None:
    raw = (ROOT / "in" / "indices" / "ind_close_all_05062026.csv").read_bytes()
    closes = parse_index_closes(raw)
    assert closes["NIFTY 50"] == (date(2026, 6, 5), D("23366.7")) and len(closes) > 100
    rows = india_rows(raw, ["NIFTY 50", "NIFTY 500"])
    assert [(r.symbol, r.week_end, r.close) for r in rows] == [
        ("NIFTY 50", date(2026, 6, 5), D("23366.7")), ("NIFTY 500", date(2026, 6, 5), D("22465.35"))]  # fmt: skip
    assert index_close_url(date(2026, 6, 5)).endswith("/ind_close_all_05062026.csv")


def test_us_history_window() -> None:
    bars = parse_csv((ROOT / "px" / "xlk.us_w.csv").read_bytes())
    rows = us_rows(bars, "XLK", date(2026, 9, 18), weeks=52)
    assert len(rows) == 52 and rows[-1].week_end == date(2026, 9, 18) and {r.symbol for r in rows} == {"XLK"}


def test_us_benchmarks_keep_their_config_symbols(tmp_path: Path) -> None:
    """config/context.yaml names the S&P 500 the way Stooq did (^spx); Yahoo calls it ^GSPC. Rows keep the config's
    symbol (C3 reads them back by it), and one symbol Yahoo doesn't answer never stops the others."""
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    http.register_mock(chart_url("^GSPC"), (ROOT / "px" / "yahoo" / "_GSPC.json").read_bytes())
    http.register_mock(chart_url("XLK"), (ROOT / "px" / "yahoo" / "XLK.json").read_bytes())
    for host in HOSTS:
        http.register_error(chart_url("XLI", host), 429)
    rows, errors = fetch_us(YahooClient(http), ["^spx", "XLI", "XLK"], date(2026, 9, 18))
    assert {r.symbol for r in rows} == {"^spx", "XLK"} and len(rows) == 2 * 260
    assert errors == ["benchmark XLI: YahooUnavailable: Yahoo request failed (429)"]
