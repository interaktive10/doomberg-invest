"""The twelve evidence signals in evaluation order (BRIEF §1.4, §4.6). S11 and S12 read S1, S2 and S6, so they run
after them; every signal sees the fired flags of the ones before it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from types import ModuleType

from pipeline.signals import (
    s01_orderbook,
    s02_incremental_roic,
    s03_operating_leverage,
    s04_earnings_quality,
    s05_capital_discipline,
    s06_derisking,
    s07_insider,
    s08_discovery,
    s09_text,
    s10_special,
    s11_capex,
    s12_cycle,
)
from pipeline.signals.base import Ctx, SignalResult

SIGNALS: tuple[ModuleType, ...] = (
    s01_orderbook, s02_incremental_roic, s03_operating_leverage, s04_earnings_quality, s05_capital_discipline,
    s06_derisking, s07_insider, s08_discovery, s09_text, s10_special, s11_capex, s12_cycle,
)  # fmt: skip
FAMILY = {m.ID: m.FAMILY for m in SIGNALS}


def evaluate(ctx: Ctx, modules: Sequence[ModuleType] = SIGNALS) -> dict[str, SignalResult]:
    """All twelve signals, or a subset in the same order (the Signal Lab's fast checks)."""
    out: dict[str, SignalResult] = {}
    for m in modules:
        r: SignalResult = m.compute(replace(ctx, fired={k: v.fired for k, v in out.items()}))
        out[m.ID] = r
    return out
