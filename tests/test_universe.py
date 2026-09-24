"""Universe seed parsers (BRIEF §1.3) and the M0-05 snapshot counts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from pipeline.india.securities import SchemaError, parse_equity_list
from pipeline.india.securities import load_snapshot as load_nse
from pipeline.us.universe import load_snapshot as load_sec
from pipeline.us.universe import parse_tickers_exchange

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import resolve_capex_seed  # noqa: E402

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


def test_resolve_marks_unresolved_without_snapshots() -> None:
    seed = yaml.safe_load((ROOT / "config" / "capex_seed.yaml").read_text(encoding="utf-8"))
    r = resolve_capex_seed.resolve(seed, None, None)
    assert r.us_total == 61 and r.in_total == 41 and r.unresolved == 102
    assert "Why unresolved" in resolve_capex_seed.render_issues(r)


def test_resolve_with_snapshots() -> None:
    seed = {"us": {"g": ["CAT", "ZZZZ"]}, "india": [{"name": "ABB India", "nse": "ABB"}, {"name": "X", "nse": "NOPE"}]}
    r = resolve_capex_seed.resolve(seed, {"CAT"}, {"ABB": "ABB India Limited"})
    assert r.in_resolved == ["ABB"]
    assert [u.split()[0] for u in r.us_unresolved] == ["ZZZZ"]
    assert [x[1] for x in r.in_unresolved] == ["NOPE"]


def test_mark_verified_only_flips_resolved() -> None:
    text = "  - {name: A, group: g, nse: ABB, verified: false}\n  - {name: B, group: g, nse: GVT&D, verified: false}\n"
    out = resolve_capex_seed.mark_verified(text, {"GVT&D"})
    assert "nse: ABB, verified: false" in out and "nse: GVT&D, verified: true" in out


# ------------------------------------------------------------------ M0-05 (needs the fetched snapshots)


@pytest.mark.snapshots
def test_us_universe_count() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "universe_us.yaml").read_text(encoding="utf-8"))
    assert len(load_sec(ROOT / cfg["snapshot"])) >= cfg["min_count_check"]


@pytest.mark.snapshots
def test_india_eq_count() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "universe_in.yaml").read_text(encoding="utf-8"))
    assert len(load_nse(ROOT / cfg["snapshot"])) >= cfg["min_count_check"]


@pytest.mark.snapshots
def test_capex_seed_resolved_or_listed() -> None:
    seed = yaml.safe_load((ROOT / "config" / "capex_seed.yaml").read_text(encoding="utf-8"))
    us = {t for f in load_sec(ROOT / "data/universe/us_tickers_exchange.json") for t in f.tickers}
    nse = {s.symbol: s.name for s in load_nse(ROOT / "data/universe/nse_equity_list.csv")}
    r = resolve_capex_seed.resolve(seed, us, nse)
    issues = (ROOT / "docs" / "UNIVERSE_ISSUES.md").read_text(encoding="utf-8")
    for u in r.us_unresolved:
        assert u.split()[0] in issues
    for name, sym, _ in r.in_unresolved:
        assert f"`{sym}`" in issues, f"{name} unresolved and not listed"
