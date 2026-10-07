"""The US weekly price source (BRIEF §4.4): Twelve Data (pipeline/net/twelvedata.py) since 2026-10, or Yahoo
(pipeline/net/yahoo.py) with PRICE_SOURCE=yahoo (docs/SPEC_ISSUES.md 37, 38). Either answers weekly bars keyed by
their Friday, or raises PriceUnavailable. NoSuchSymbol is an answer (the source is up, but has nothing for that
symbol), so it never counts toward the failures in a row that stop the stage."""

from __future__ import annotations

from typing import Protocol

from pipeline.net.stooq import Bar


class PriceUnavailable(Exception):
    """The source answered something other than prices, or didn't answer."""


class NoSuchSymbol(PriceUnavailable):
    """The source answered, but has no prices for the symbol (unknown, delisted, or not on the plan)."""


class WeeklySource(Protocol):
    name: str  # source_health's source and prices_w.source

    def weekly(self, ticker: str) -> list[Bar]: ...
