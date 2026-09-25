"""S7 reads amended Form 4s as amended (M4 review R1-F4): the latest version of a filing decides whether the buy is
planned and when it was, before the 10b5-1 and window filters."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D

import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals import s07_insider
from pipeline.signals.base import Ctx, Insider
from pipeline.signals.series import Series

CFG = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
WEEK = date(2026, 9, 18)


def buy(person: str, value: int, day: date, filed: datetime, url: str, planned: bool = False,
        amends: date | None = None) -> Insider:  # fmt: skip
    return Insider("c", person, day, filed, "open_market_buy", D(value), planned, url, "USD", amends)


def ctx(*insiders: Insider) -> Ctx:
    return Ctx("c", "us", WEEK, Series([], "us"), CFG, insiders=list(insiders))


A = buy("ALICE", 200_000, date(2026, 9, 1), datetime(2026, 9, 2, 20, tzinfo=UTC), "https://sec/a")
B = buy("BOB", 100_000, date(2026, 9, 3), datetime(2026, 9, 4, 20, tzinfo=UTC), "https://sec/b")


def test_s7_fires_on_two_unplanned_buyers() -> None:
    r = s07_insider.compute(ctx(A, B))
    assert r.fired and r.inputs["insiders"] == 2 and r.inputs["total_usd"] == 300_000


def test_s7_ignores_a_buy_amended_to_planned() -> None:
    amended = buy("ALICE", 200_000, date(2026, 9, 1), datetime(2026, 9, 5, 20, tzinfo=UTC), "https://sec/a2",
                  planned=True, amends=date(2026, 9, 2))  # fmt: skip
    r = s07_insider.compute(ctx(A, B, amended))
    assert not r.fired and r.inputs["insiders"] == 1


def test_s7_amendment_moving_the_trade_out_of_the_window() -> None:
    moved = buy("ALICE", 200_000, date(2026, 6, 1), datetime(2026, 9, 5, 20, tzinfo=UTC), "https://sec/a3",
                amends=date(2026, 9, 2))  # fmt: skip
    r = s07_insider.compute(ctx(A, B, moved))
    assert not r.fired and r.inputs["insiders"] == 1
