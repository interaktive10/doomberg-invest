"""M5-06: P-06 answers are grounded like Appendix F (ungrounded categories dropped), and only confirmed memberships
count for S11 (BRIEF §4.11)."""

from __future__ import annotations

from decimal import Decimal as D

import yaml

from pipeline.capex.membership import CrossBorderInput, parse, profile_text, us_categories
from pipeline.capex.view import export_signals, view
from pipeline.settings import REPO_ROOT

CFG = yaml.safe_load((REPO_ROOT / "config" / "categories.yaml").read_text(encoding="utf-8"))
CATS = tuple(CFG["categories"])
TEXT = profile_text([
    ("Announcement 2026-09-18", "Aravalli Cables has received an export order worth Rs 450 crore for high-voltage "
                                "cables for a data center project in the United States."),
    ("Annual report 2025-26, p. 14", "We manufacture extra-high-voltage power cables and substation equipment for "
                                     "utilities and data centers. Exports were 35% of revenue in FY2026."),
])  # fmt: skip


def test_grounded_categories_are_kept_and_the_rest_dropped() -> None:
    answer = {
        "categories": [
            {"category": "grid", "quote": "extra-high-voltage power cables and substation equipment for utilities",
             "confidence": 0.9},
            {"category": "power_equipment", "quote": "We manufacture EHV cables for hyperscalers", "confidence": 0.8},
            {"category": "space_launch", "quote": "We manufacture extra-high-voltage power cables", "confidence": 0.9},
            {"category": "construction", "quote": " ".join(["word"] * 61), "confidence": 0.9},
        ],
        "export_exposure": {"share_pct": 35, "overseas_order_book": None,
                            "quote": "Exports were 35% of revenue in FY2026."},
    }  # fmt: skip
    r = parse(answer, TEXT, CATS)
    assert [g.category for g in r.categories] == ["grid"]
    g = r.categories[0]
    assert TEXT[g.char_start : g.char_end] == g.quote and g.confidence == D("0.90")
    assert len(r.dropped) == 3 and any("not found" in x for x in r.dropped)
    assert r.export is not None and r.export.share_pct == D(35)
    assert TEXT[r.export.char_start : r.export.char_end] == "Exports were 35% of revenue in FY2026."
    bad = parse({"categories": [], "export_exposure": {"share_pct": 50, "quote": "Exports were 50% of revenue."}}, TEXT,
                CATS)  # fmt: skip
    assert bad.export is None and bad.dropped == ["export_exposure: quote not found in the text"]


def test_p06_input_lists_the_categories_and_limits_the_schema() -> None:
    inp = CrossBorderInput("Aravalli Cables Limited", "ARVL", CATS, TEXT)
    assert inp.variables()["categories"] == ", ".join(CATS)
    assert inp.schema()["properties"]["categories"]["items"]["properties"]["category"]["enum"] == list(CATS)


def test_only_confirmed_memberships_reach_s11() -> None:
    rows = [("grid", "confirmed"), ("power_equipment", "proposed"), ("cooling", "rejected")]
    confirmed = [c for c, status in rows if status == "confirmed"]
    v = view(confirmed, {"grid": ("rising", D("0.3")), "power_equipment": ("rising", D("0.4"))}, 2, False, True)
    assert list(v.categories) == ["grid"] and v.direction == {"grid": "rising"} and v.graph_distance == 2
    assert view([], {"grid": ("rising", D("0.3"))}, None, False, False).categories == ()


def test_us_proposals_from_the_industry_map() -> None:
    assert us_categories("power_equipment", "3612", CFG)[0] == ["power_equipment", "grid"]
    cats, why = us_categories(None, "3585", CFG)
    assert cats == ["cooling"] and why == "SIC 3585"
    assert us_categories(None, "9999", CFG) == ([], "")


def test_export_signals() -> None:
    from dataclasses import dataclass
    from datetime import UTC, date, datetime
    from uuid import uuid4

    @dataclass
    class F:
        company_id: object
        fact_type: str
        subject_key: str
        value_num: D | None
        unit: str
        period_end: date | None
        as_of: date
        published_at: datetime

    cid = uuid4()
    facts = [F(cid, "export_exposure", "export_exposure:share_pct", D(28), "percent", None, date(2025, 9, 1),
               datetime(2025, 9, 1, tzinfo=UTC)),
             F(cid, "export_exposure", "export_exposure:share_pct", D(35), "percent", None, date(2026, 9, 1),
               datetime(2026, 9, 1, tzinfo=UTC))]  # fmt: skip
    assert export_signals(facts, {cid: "export order for a data center project in the United States"}) == (True, True)
    assert export_signals(facts[:1], {cid: "exports to Europe"}) == (False, False)
