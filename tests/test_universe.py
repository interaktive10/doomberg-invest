"""Universe seed parsers (BRIEF §1.3) and the M0-05 snapshot counts. The capex seed was resolved once in M0; its
resolver went with the Capex Desk (docs/SPEC_ISSUES.md 52) and the result is in config/capex_seed.yaml."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pipeline.india.securities import SchemaError, parse_equity_list
from pipeline.india.securities import load_snapshot as load_nse
from pipeline.us.universe import load_snapshot as load_sec
from pipeline.us.universe import parse_tickers_exchange

ROOT = Path(__file__).resolve().parents[1]

SEC_SAMPLE = json.dumps(
    {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [320193, "Apple Inc.", "AAPL", "Nasdaq"],
            [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
            [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
            [18230, "Caterpillar Inc", "CAT", "NYSE"],
            [999, "Some OTC Co", "OTCX", "OTC"],
            [998, "No Exchange Co", "NOEX", None],
        ],
    }
)

NSE_SAMPLE = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "ABB,ABB India Limited,EQ,01-JAN-1995,2,1,INE117A01022,2\n"
    "LT,Larsen & Toubro Limited,EQ,23-JUN-2004,2,1,INE018A01030,2\n"
    "SOMEBE,Some BE Limited,BE,01-JAN-2020,10,1,INE000X01010,10\n"
)


def test_sec_parser_keeps_nyse_nasdaq_one_row_per_cik() -> None:
    rows = parse_tickers_exchange(SEC_SAMPLE)
    assert [(r.cik, r.tickers, r.exchange) for r in rows] == [
        ("0000018230", ("CAT",), "NYSE"),
        ("0000320193", ("AAPL",), "Nasdaq"),
        ("0001652044", ("GOOGL", "GOOG"), "Nasdaq"),
    ]


def test_nse_parser_keeps_eq_series_and_strips_headers() -> None:
    rows = parse_equity_list(NSE_SAMPLE.encode("utf-8-sig"))
    assert [(r.symbol, r.series, r.isin) for r in rows] == [("ABB", "EQ", "INE117A01022"), ("LT", "EQ", "INE018A01030")]


def test_nse_parser_rejects_changed_schema() -> None:
    with pytest.raises(SchemaError):
        parse_equity_list("SYMBOL,NAME\nABB,ABB India\n")


def test_nse_parser_all_series() -> None:
    rows = parse_equity_list(NSE_SAMPLE, series=None)
    assert [(r.symbol, r.series) for r in rows] == [("ABB", "EQ"), ("LT", "EQ"), ("SOMEBE", "BE")]


# ------------------------------------------------------------------ M0-05 (needs the fetched snapshots)


@pytest.mark.snapshots
def test_us_universe_count() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "universe_us.yaml").read_text(encoding="utf-8"))
    assert len(load_sec(ROOT / cfg["snapshot"])) >= cfg["min_count_check"]


@pytest.mark.snapshots
def test_india_eq_count() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "universe_in.yaml").read_text(encoding="utf-8"))
    assert len(load_nse(ROOT / cfg["snapshot"])) >= cfg["min_count_check"]
