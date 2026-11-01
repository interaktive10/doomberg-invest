"""Themes (pipeline/reports/themes.py; docs/SPEC_ISSUES.md 67): demand evidence per industry against its price move,
the candidates P-08 reads, its answer checked, and its memory of earlier calls."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pipeline.db.models import Company, FactRow, FundamentalsRow
from pipeline.reports import themes as t


def quarters(revenues: list[float]) -> list[FundamentalsRow]:
    cid = uuid4()
    out = []
    for i, rev in enumerate(revenues):
        y, q = 2024 + i // 4, i % 4
        end = date(y, 3 * q + 3, 28)
        out.append(FundamentalsRow(company_id=cid, period_end=end, fiscal_label=f"Q{q + 1}",
                                   filed_at=datetime(y, 3 * q + 3, 28, tzinfo=UTC), revenue=Decimal(str(rev)),
                                   currency="USD", source="sec_xbrl"))  # fmt: skip
    return out


def test_revenue_acceleration_needs_growth_that_speeds_up() -> None:
    flat = quarters([100] * 9)
    assert t.ttm_growth(flat, 0) == 0.0 and not t.accelerating(flat)
    speeding = quarters([100, 100, 100, 100, 100, 100, 110, 130, 150])
    assert t.ttm_growth(speeding, 0) is not None and t.accelerating(speeding)
    assert t.ttm_growth(quarters([100] * 7), 0) is None  # two years needed


def firm(market: str, industry: str, move: float, demand: bool = False, fact: bool = False) -> t.Firm:
    c = Company(
        id=uuid4(),
        market=market,
        name=f"{industry} {uuid4().hex[:4]}",
        ticker="T" + uuid4().hex[:3].upper(),
        industry=industry,
    )  # type: ignore[arg-type]
    f = t.Firm(c, industry, accelerating=demand, move=move, price=10.0)
    if fact:
        assert c.id is not None
        f.facts.append(FactRow(company_id=c.id, fact_type="order_win", subject="a transformer order", subject_key="x",
                               unit="usd", as_of=date(2026, 10, 1),
                               published_at=datetime(2026, 10, 1, tzinfo=UTC)))  # fmt: skip
    return f


def world() -> list[t.Firm]:
    """Grid: 6 names, 4 with demand, flat price (early). Chips: 6 names, 3 with demand, up 80% (running). Retail and
    Banks: little demand evidence."""
    fs = [firm("us", "Grid", 0.02, demand=i < 2, fact=2 <= i < 4) for i in range(6)]
    fs += [firm("us", "Chips", 0.8, demand=i < 3) for i in range(6)]
    fs += [firm("us", "Retail", 0.1, demand=i < 1) for i in range(6)]
    fs += [firm("us", "Banks", 0.15) for _ in range(6)]
    fs += [firm("us", "Tiny", 0.0, demand=True) for _ in range(3)]  # under MIN_NAMES: no row
    return fs


def test_industries_count_demand_and_the_median_move() -> None:
    rows = {r["industry"]: r for r in t.industries(world())}
    assert set(rows) == {"Grid", "Chips", "Retail", "Banks"}
    assert rows["Grid"]["with_demand"] == 4 and rows["Grid"]["facts"] == 2 and rows["Grid"]["median_move"] == 0.02
    assert rows["Grid"]["examples"][0]["what"].startswith("order_win: ")  # facts first


def test_candidates_are_the_top_quarter_by_share_marked_early_or_running() -> None:
    rows = t.industries(world())
    cands = t.candidates(rows, {"us": 0.12})
    assert [(c["industry"], c["early"]) for c in cands] == [("Grid", True)]
    assert [e["id"] for e in cands[0]["examples"]] == ["e1", "e2", "e3", "e4"]


def cands() -> list[dict[str, Any]]:
    return t.candidates(t.industries(world()), {"us": 0.12})


def answer(**over: Any) -> dict[str, Any]:
    theme = {"market": "us", "industry": "Grid", "title": "Grid gear orders build", "confidence": "medium",
             "why": "4 of 6 grid companies show demand evidence while the median price moved 0.02.",
             "wrong_if": "orders stop and revenue slows", "evidence": ["e1", "e2"]} | over  # fmt: skip
    return {"themes": [theme], "reviews": [], "note": "First week."}


def test_a_grounded_theme_is_kept_with_its_evidence() -> None:
    c = cands()
    text = json.dumps(c)
    themes, _, note, dropped = t.check_answer(answer(), c, text, [])
    assert dropped == [] and note == "First week." and len(themes) == 1
    assert themes[0]["early"] and [e["id"] for e in themes[0]["evidence"]] == ["e1", "e2"]


def test_a_theme_that_strays_is_dropped_with_why() -> None:
    c = cands()
    text = json.dumps(c)
    for over, why in [({"industry": "Chips"}, "not a candidate industry"),
                      ({"evidence": ["e99"]}, "cites no evidence of its industry"),
                      ({"evidence": ["e1"]}, "a theme needs evidence from two companies"),
                      ({"why": "Orders up 340% this year."}, "a number the input lacks"),
                      ({"confidence": "sure"}, "unknown confidence")]:  # fmt: skip
        themes, _, _, dropped = t.check_answer(answer(**over), c, text, [])
        assert themes == [] and dropped[0].endswith(why), (over, dropped)


def test_reviews_name_only_earlier_calls_and_the_scorecard_measures_them() -> None:
    earlier = [{"week": "2026-10-23", "themes": [{"market": "us", "industry": "Grid", "title": "Grid",
                                                  "evidence": [{"company_id": "a", "price": 10.0},
                                                               {"company_id": "b", "price": 20.0}]}]}]  # fmt: skip
    card = t.scorecard(earlier, {"a": 12.0, "b": 21.0})
    assert card == [{"week": "2026-10-23", "market": "us", "industry": "Grid", "title": "Grid", "since": 0.125}]
    ans = {"themes": [], "note": "", "reviews": [
        {"market": "us", "industry": "Grid", "decision": "keep", "reason": "orders keep coming"},
        {"market": "us", "industry": "Oil", "decision": "drop", "reason": "never called"}]}  # fmt: skip
    _, reviews, _, _ = t.check_answer(ans, cands(), "{}", card)
    assert reviews == [{"market": "us", "industry": "Grid", "decision": "keep", "reason": "orders keep coming"}]
