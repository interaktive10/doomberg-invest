"""S8 discovery (BRIEF §4.6).
US: 13F holder count at or below the 40th percentile of its revenue-size decile, and holders up >= 15% QoQ in each of
the last 2 quarters. Strength clip(latest QoQ growth / 0.5, 0, 1).
India: FII + DII <= 15% and up >= 2 pp over 2 quarters. Strength clip(dpp / 6, 0, 1)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pipeline.signals.base import Ctx, Holding, SignalResult, cfg_dec, fired, missing, num, quiet
from pipeline.signals.series import ZERO, clip, growth

ID, FAMILY = "S8", "behavior"


def consecutive(rows: list[Holding], n: int) -> list[Holding] | None:
    """The last n quarters, if they are consecutive quarter ends."""
    last = rows[-n:]
    if len(last) < n or any((b.quarter_end - a.quarter_end).days > 100 for a, b in zip(last, last[1:], strict=False)):
        return None
    return last


def compute(ctx: Ctx) -> SignalResult:
    c = ctx.section("s8_discovery")
    rows = sorted(ctx.ownership, key=lambda h: h.quarter_end)
    return _us(ctx, c, rows) if ctx.market == "us" else _india(c, rows)


def _us(ctx: Ctx, c: Mapping[str, Any], rows: list[Holding]) -> SignalResult:
    n = int(c["us_consecutive_quarters"])
    last = consecutive([h for h in rows if h.inst_holders is not None], n + 1)
    if last is None:
        return missing("holder_counts")
    counts = [Decimal(h.inst_holders or 0) for h in last]
    growths = [growth(b, a) for a, b in zip(counts, counts[1:], strict=False)]
    pct = ctx.holder_pct_in_size_decile
    inputs = {"holders": [int(x) for x in counts], "qoq": [num(g) for g in growths], "pct_in_size_decile": num(pct)}
    if pct is None:
        return missing("pct_in_size_decile", **inputs)
    need = cfg_dec(c, "us_min_holder_growth_qoq")
    rising = all(g is not None and g >= need for g in growths)
    if not rising or pct > cfg_dec(c, "us_max_holder_pct_in_size_decile"):
        return quiet(**inputs)
    return fired(clip((growths[-1] or ZERO) / cfg_dec(c, "us_strength_divisor"), ZERO, Decimal(1)), **inputs)


def _india(c: Mapping[str, Any], rows: list[Holding]) -> SignalResult:
    known = [h for h in rows if h.fii_pct is not None and h.dii_pct is not None]
    last = consecutive(known, int(c["in_rise_quarters"]) + 1)
    if last is None:
        return missing("fii_dii_history")
    share = [(h.fii_pct or ZERO) + (h.dii_pct or ZERO) for h in last]
    rise = share[-1] - share[0]
    inputs = {"fii_dii_pct": num(share[-1]), "rise_pp": num(rise)}
    if share[-1] > cfg_dec(c, "in_max_fii_dii_pct") or rise < cfg_dec(c, "in_min_rise_pp"):
        return quiet(**inputs)
    return fired(clip(rise / cfg_dec(c, "in_strength_divisor_pp"), ZERO, Decimal(1)), **inputs)
