"""Themes v2 (pipeline/reports/themes.py; docs/SPEC_ISSUES.md 68): a library of demand chains, keywords to companies,
statuses, the rethink's calendar, P-08's answer checked and applied."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from pipeline.db.models import Company, FundamentalsRow
from pipeline.reports import drivers as dv
from pipeline.reports import themes as t

ROOT = Path(__file__).resolve().parents[2]


def quarters(revenues: list[float]) -> list[FundamentalsRow]:
    cid = uuid4()
    return [FundamentalsRow(company_id=cid, period_end=date(2024 + i // 4, 3 * (i % 4) + 3, 28), fiscal_label="Q",
                            filed_at=datetime(2024 + i // 4, 3 * (i % 4) + 3, 28, tzinfo=UTC),
                            revenue=Decimal(str(r)), currency="USD", source="sec_xbrl")
            for i, r in enumerate(revenues)]  # fmt: skip


def test_revenue_acceleration_needs_growth_that_speeds_up() -> None:
    assert not t.accelerating(quarters([100] * 9))
    assert t.accelerating(quarters([100, 100, 100, 100, 100, 100, 110, 130, 150]))
    assert t.ttm_growth(quarters([100] * 7), 0) is None


def firm(name: str, industry: str | None = None, sector: str | None = None, market: str = "us",
         move: float | None = 0.1, demand: bool = False) -> t.Firm:  # fmt: skip
    c = Company(
        id=uuid4(),
        market=market,
        name=name,
        ticker=name[:4].upper(),
        industry=industry,  # type: ignore[arg-type]
        sector=sector,
    )
    return t.Firm(c, industry or sector or "Unclassified", accelerating=demand, move=move, price=10.0)


def world() -> list[t.Firm]:
    return [firm("Goodgrip Inc", "Tires & Inner Tubes", demand=True), firm("Roadway Corp", "Tires & Inner Tubes"),
            firm("Apollo Tyres Ltd", sector="Automobile and Auto Components", market="in", demand=True),
            firm("Brakeline Inc", "Motor Vehicle Parts & Accessories", move=0.02),
            firm("Asian Paints Ltd", sector="Consumer Durables", market="in"),
            firm("Big Bank", "National Commercial Banks", move=0.3)]  # fmt: skip


def test_keywords_match_industry_sector_or_name_in_either_market() -> None:
    fs = t.members(world(), ["tire", "TYRE", "motor vehicle parts"])
    assert sorted(f.company.name for f in fs) == ["Apollo Tyres Ltd", "Brakeline Inc", "Goodgrip Inc", "Roadway Corp"]
    assert [f.company.name for f in t.members(world(), ["paint"])] == [
        "Asian Paints Ltd"
    ]  # by name, India's sector is coarse


def test_status_reads_the_driver_and_the_run_up() -> None:
    assert t.status_of(0.8, 0.02) == "building" and t.status_of(0.8, 0.25) == "priced_in"
    assert (
        t.status_of(-0.9, 0.0) == "fading"
        and t.status_of(0.1, 0.0) == "watching"
        and t.status_of(None, None) == "watching"
    )


def test_the_rethink_is_monthly_sooner_on_a_trigger_never_twice_a_week() -> None:
    assert t.rethink_due(date(2026, 11, 6), None, False) == (True, "the first rethink")
    assert t.rethink_due(date(2026, 11, 6), date(2026, 10, 2), False)[0]  # the first Friday of a new month
    assert not t.rethink_due(date(2026, 11, 13), date(2026, 11, 6), False)[0]  # mid-month, nothing moved
    assert t.rethink_due(date(2026, 11, 13), date(2026, 11, 6), True)[0]  # a status changed
    assert not t.rethink_due(date(2026, 11, 8), date(2026, 11, 6), True)[0]  # never twice in a week
    assert t.rethink_due(date(2026, 12, 18), date(2026, 11, 6), False)[0]  # five weeks
    assert t.next_rethink(date(2026, 11, 13)) == date(2026, 12, 4) and t.next_rethink(date(2026, 12, 11)) == date(
        2027, 1, 1
    )
    prev = [{"slug": "a", "status": "watching", "z_at_rethink": 0.1}]
    assert t.triggered(prev, [{"slug": "a", "status": "building", "z": 0.2}])
    assert t.triggered(prev, [{"slug": "a", "status": "watching", "z": 1.3}])
    assert not t.triggered(prev, [{"slug": "a", "status": "watching", "z": 0.5}])


def test_the_seed_library_is_valid() -> None:
    lib = t.seed(ROOT)
    drv = dv.load(ROOT)
    assert len(lib) >= 6 and len({x["slug"] for x in lib}) == len(lib)
    for x in lib:
        assert x["driver"] in drv or x["driver"] == dv.FILINGS
        assert x["transform"] in dv.TRANSFORMS and x["keywords"] and x["category"]
        assert x["transform"] != "cohort" or x["lag_months"] >= 12
    assert {x["category"] for x in lib} - {"Technology & AI"}  # not only about AI


DRV = {"TOTALSA": dv.Driver("TOTALSA", "US light vehicle sales", "m"), "HSN1F": dv.Driver("HSN1F", "Homes", "k")}
LIB = [{"slug": "vehicle-replacement", "title": "Cars bought in a boom", "category": "Replacement cycles",
        "driver": "TOTALSA", "transform": "cohort", "lag_months": 48, "keywords": ["tire"], "why": "w",
        "notes": []}]  # fmt: skip


def answer(**new: Any) -> dict[str, Any]:
    n = {"title": "Cheaper money lifts brakes", "category": "Replacement cycles", "driver": "TOTALSA",
         "reading": "yoy", "lag_months": 0, "keywords": ["tire", "motor vehicle parts"],
         "why": "Sales rose 3% while parts makers lag.", "wrong_if": "Parts sales stall."} | new  # fmt: skip
    return {
        "reviews": [{"slug": "vehicle-replacement", "decision": "keep", "note": "The 48 month wave holds."}],
        "new": [n],
        "note": "Added a parts theme.",
    }


def test_a_grounded_answer_is_kept_and_applied() -> None:
    r = t.check_answer(answer(), LIB, world(), DRV, json.dumps({"x": 0.03, "lag": 48}))
    assert (
        r.dropped == [] and r.note == "Added a parts theme." and r.reviews["vehicle-replacement"]["decision"] == "keep"
    )
    assert r.new[0]["slug"] == "cheaper-money-lifts-brakes" and r.new[0]["origin"] == "ai"
    lib, retired = t.apply([dict(x) for x in LIB], [], r, date(2026, 11, 6))
    assert [x["slug"] for x in lib] == ["vehicle-replacement", "cheaper-money-lifts-brakes"] and retired == []
    assert lib[0]["notes"][-1] == {"week": "2026-11-06", "decision": "keep", "text": "The 48 month wave holds."}
    assert lib[1]["born"] == "2026-11-06"


def test_a_new_theme_that_strays_is_dropped_with_why() -> None:
    text = json.dumps({"x": 0.03, "lag": 48})
    for over, why in [({"driver": "GOLD"}, "an unknown driver"), ({"category": "Vibes"}, "an unknown category"),
                      ({"reading": "cohort", "lag_months": 6}, "a bad lag"),
                      ({"keywords": ["spaceships"]}, "keywords that match too few companies"),
                      ({"why": "Sales rose 41% this year."}, "a number the input lacks"),
                      ({"title": "Cars bought in a boom"}, "a theme the library has")]:  # fmt: skip
        r = t.check_answer(answer(**over), LIB, world(), DRV, text)
        assert r.new == [] and why in r.dropped[0], (over, r.dropped)


def test_a_retired_theme_moves_out_with_its_notes() -> None:
    ans = {
        "reviews": [{"slug": "vehicle-replacement", "decision": "retire", "note": "The wave has passed."}],
        "new": [],
    }
    r = t.check_answer(ans, LIB, world(), DRV, "{}")
    lib, retired = t.apply([dict(x) for x in LIB], [], r, date(2026, 12, 4))
    assert lib == [] and retired[0]["slug"] == "vehicle-replacement" and retired[0]["notes"][-1]["decision"] == "retire"
    assert {"57", "57.1", "2", "12"} <= t.allowed_numbers("0.571 0.02 0.12") and "3" not in t.allowed_numbers("0.02")


def test_a_driver_that_fails_or_runs_past_the_budget_uses_its_last_good_copy(tmp_path: Path) -> None:
    """The first live run (2026-11-01) ran past its job's limit; FRED from a runner can be slow, so downloads have a
    budget and a stored copy to fall back on."""
    from pipeline.net import fred
    from pipeline.net.http import HttpClient
    from pipeline.settings import Settings

    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    http.register_mock(fred.URL.format(id="TOTALSA"), (ROOT / "fixtures" / "fred" / "TOTALSA.csv").read_bytes())
    old = [(date(2020, 1, 1), 1.0)]
    pts, missing = t.driver_points(http, ["TOTALSA", "HSN1F", "PERMIT"], {"HSN1F": old})
    assert len(pts["TOTALSA"]) > 400 and pts["HSN1F"] == old and "PERMIT" not in pts
    assert (
        missing[0].startswith("HSN1F: ")
        and missing[0].endswith("last good copy used")
        and missing[1].startswith("PERMIT")
    )
    late, why = t.driver_points(http, ["TOTALSA"], {"TOTALSA": old}, budget=-1)
    assert late["TOTALSA"] == old and "over the time budget" in why[0]
