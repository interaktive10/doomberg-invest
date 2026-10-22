"""Insider trading (PIT) on the F-IN sample (BRIEF §4.3, §8 M3-04): promoter market purchases are detected; sales,
gifts, transfers, conversions, ESOPs and non-promoter trades are told apart. Expected values checked by hand against
the disclosure XBRLs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

from pipeline.india.pit import parse_disclosure, parse_index_json
from pipeline.india.pledges import pledge_event
from pipeline.india.shareholding import parse_shareholding

FIN = Path(__file__).resolve().parents[2] / "fixtures" / "in"


def trades():
    return [t for p in sorted((FIN / "pit" / "disclosures").glob("*.xml")) for t in parse_disclosure(p.read_bytes())]


def test_promoter_purchases_are_detected() -> None:
    buys = sorted((t.symbol, t.person, t.category, t.shares, t.value, t.event_date)
                  for t in trades() if t.kind == "promoter_buy")  # fmt: skip
    assert [b[0] for b in buys] == ["BHAGERIA", "CSLFINANCE", "CSLFINANCE", "DIAMONDYD", "FIBERWEB", "SINCLAIR",
                                    "THANGAMAYL"]  # fmt: skip
    sinclair = next(b for b in buys if b[0] == "SINCLAIR")
    assert sinclair[1:] == ("NAVIN CHAND SUCHANTI", "Promoter", D(17500), D(1417187), date(2026, 9, 24))
    assert next(b for b in buys if b[0] == "BHAGERIA")[2] == "Promoter Group"


def test_identical_lines_of_one_disclosure_stay_two_trades() -> None:
    """Review F5: CSLFINANCE's disclosure has two equal same-day purchases (holdings 434,686 -> 439,686 -> 444,686);
    each line keeps its identity, so both are stored."""
    csl = [t for t in trades() if t.symbol == "CSLFINANCE"]
    assert [(t.line, t.person, t.shares, t.value, t.event_date) for t in csl] == [
        ("Disclosure1", "Rohit Gupta HUF", D(5000), D(1200000), date(2026, 9, 1)),
        ("Disclosure2", "Rohit Gupta HUF", D(5000), D(1200000), date(2026, 9, 1)),
    ]
    assert all(len({t.line for t in parse_disclosure(p.read_bytes())}) == len(parse_disclosure(p.read_bytes()))
               for p in (FIN / "pit" / "disclosures").glob("*.xml"))  # fmt: skip


def test_everything_else_is_told_apart() -> None:
    kinds = {(t.symbol, t.mode): t.kind for t in trades()}
    assert kinds[("GNA", "Market Sale")] == "promoter_sell"
    assert kinds[("AQYLON", "Market Sale")] == "promoter_sell"
    for key in [
        ("ELECTHERM", "Gift"),
        ("TINNARUBR", "Inter-se-Transfer"),
        ("BAGFILMS", "Conversion of security"),
        ("PATELENG", "Others"),
        ("360ONE", "Off Market"),
        ("LALPATHLAB", "ESOP"),
        ("FSL", "Off Market"),
    ]:
        assert kinds[key] is None, key
    director = [t for t in trades() if t.symbol == "LALPATHLAB" and t.mode == "Market Sale"]
    assert director and director[0].category == "Director" and director[0].kind is None  # not a promoter


def test_index_json() -> None:
    """The index the daily run reads (NSE's API). Its CSV twin had no reader and went in overhaul PR 4."""
    j = parse_index_json((FIN / "pit" / "pit.json").read_bytes())
    assert len(j) == 2865 and j[0].symbol == "SINCLAIR" and j[0].xbrl_url.startswith("https://")
    assert j[0].filed_at == datetime(2026, 9, 25, 7, 50, 13, tzinfo=UTC)  # dissemination 13:20:13 IST
    assert sum(x.revision for x in j) == 36


def test_pledge_changes_between_quarters() -> None:
    jp = parse_shareholding((FIN / "shareholding" / "SHP_JPPOWER_2026-06-30.xml").read_bytes())
    assert jp.pledged_shares is not None
    from dataclasses import replace

    march = replace(jp, quarter_end=date(2026, 3, 31), pledged_shares=jp.pledged_shares + 50_000_000)
    ev = pledge_event(march, jp, datetime(2026, 7, 13, 10, 27, 22, tzinfo=UTC))
    assert ev is not None and (ev.kind, ev.shares, ev.event_date) == ("pledge_released", D(50_000_000), jp.quarter_end)
    assert pledge_event(jp, jp, ev.filed_at) is None  # same quarter
    assert pledge_event(replace(march, quarter_end=date(2025, 12, 31)), jp, ev.filed_at) is None  # a skipped quarter
