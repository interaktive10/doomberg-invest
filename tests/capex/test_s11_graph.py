"""M5-07: S11 on a synthetic counterparty graph (BRIEF §4.11): distances from the anchors through links, then the
live S11 rule on each company's CapexView."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from uuid import UUID, uuid4

import yaml

from pipeline.capex.graph import LinkRow, distances
from pipeline.capex.view import view
from pipeline.settings import REPO_ROOT
from pipeline.signals import s11_capex
from pipeline.signals.base import Ctx, Fact
from pipeline.signals.series import Quarter, Series

CFG = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
WEEK = date(2026, 9, 25)

MSFT, SUPPLIER, SUB, FAR = uuid4(), uuid4(), uuid4(), uuid4()
COMPANIES = {MSFT: ("MICROSOFT CORP", "0000789019"), SUPPLIER: ("Voltara Grid Systems, Inc.", "0000000001"),
             SUB: ("Aravalli Cables Ltd", None), FAR: ("Remote Parts Co", None)}  # fmt: skip


def link(frm: UUID, name: str, cik: str | None = None) -> LinkRow:
    return LinkRow(frm, uuid4(), name, cik)


LINKS = [
    link(SUPPLIER, "Microsoft Corporation", "789019"),  # the supplier names the anchor as its customer (CIK match)
    link(SUB, "Voltara Grid Systems"),  # the Indian cable maker supplies the supplier (name match)
    link(FAR, "Aravalli Cables Limited"),  # three hops out
]


def series(growth: float) -> Series:
    quarters = []
    for k in range(8):
        year = 2024 + (k + 2) // 4
        month = ((k + 2) % 4) * 3 + 3
        rev = D(100) * (D(1) + D(str(growth))) ** (1 if k >= 4 else 0)
        quarters.append(Quarter(date(year, month, 28), {"revenue": rev}))
    return Series(quarters, "us")


def ctx(cid: UUID, dist: int | None, growth: float, facts: list[Fact], market: str = "us") -> Ctx:
    cap = view(["grid"], {"grid": ("rising", D("0.40"))}, dist, False, market == "in")
    return Ctx(str(cid), market, WEEK, series(growth), CFG, facts=facts, capex=cap)


ORDER = [Fact("order_win", "order_win:us_data_center_cables", date(2026, 9, 18), D(4_500_000_000), "usd")]


def test_graph_distances_from_the_anchor() -> None:
    d = distances(LINKS, COMPANIES, [MSFT])
    assert d == {MSFT: 0, SUPPLIER: 1, SUB: 2, FAR: 3}


def test_s11_fires_for_a_second_order_member_with_order_evidence() -> None:
    d = distances(LINKS, COMPANIES, [MSFT])
    r = s11_capex.compute(ctx(SUB, d[SUB], 0.35, ORDER, market="in"))
    assert r.fired and r.inputs["second_order"] is True
    assert r.strength == D("0.75")  # 0.5 + 0.25 (India export quote about a US data center)


def test_first_order_needs_the_growth_lag() -> None:
    d = distances(LINKS, COMPANIES, [MSFT])
    lagging = s11_capex.compute(ctx(SUPPLIER, d[SUPPLIER], 0.20, ORDER))  # 40% input growth vs 20% revenue: 20 pp
    keeping_up = s11_capex.compute(ctx(SUPPLIER, d[SUPPLIER], 0.35, ORDER))  # 5 pp: below the 10 pp rule
    assert lagging.fired and not keeping_up.fired


def test_no_order_evidence_or_too_far_stays_quiet() -> None:
    d = distances(LINKS, COMPANIES, [MSFT])
    assert not s11_capex.compute(ctx(SUB, d[SUB], 0.35, [])).fired  # no S1, no order/customer/export fact
    assert not s11_capex.compute(ctx(FAR, d[FAR], 0.35, ORDER)).fired  # distance 3 and no lag
