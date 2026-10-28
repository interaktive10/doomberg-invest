"""S9 verified text facts (BRIEF §4.6): >= 1 verified fact in the last 2 quarters of the types order_win,
customer_win (with its customer named: §1.9 "a new named customer or program", docs/SPEC_ISSUES.md 58),
capacity_addition (with a named counterparty or a commitment), price_increase, lead_time (longer than the previous
statement), new_segment, or governance_flag (a removal). Strength min(1, 0.4 x count).

Facts reach the signal already point-in-time (document published by the week) and verified (Appendix F.5).
governance_flag subject keys end in ":added" or ":removed" (pipeline/facts, M5)."""

from __future__ import annotations

from decimal import Decimal

from pipeline.signals.base import Ctx, Fact, SignalResult, cfg_dec, fired, months_before, quiet

ID, FAMILY = "S9", "text"
PLAIN = frozenset({"order_win", "price_increase", "new_segment"})
NAMED = frozenset({"customer_win", "capacity_addition"})  # count with a named counterparty (capacity: or a commitment)


def longer_lead_time(f: Fact, facts: list[Fact]) -> bool:
    earlier = [g for g in facts if g.fact_type == "lead_time" and g.subject_key == f.subject_key and g.as_of < f.as_of]
    earlier = [g for g in earlier if g.value_num is not None]
    if f.value_num is None or not earlier:
        return False
    before = max(earlier, key=lambda g: g.as_of).value_num
    return before is not None and f.value_num > before


def qualifies(f: Fact, facts: list[Fact], types: frozenset[str]) -> bool:
    if f.fact_type not in types:
        return False
    if f.fact_type in PLAIN:
        return True
    if f.fact_type in NAMED and f.counterparty:
        return True
    if f.fact_type == "capacity_addition":
        return "commit" in f"{f.subject} {f.subject_key}".lower()
    if f.fact_type == "lead_time":
        return longer_lead_time(f, facts)
    if f.fact_type == "governance_flag":
        return f.subject_key.endswith(":removed")
    return False


def recent_facts(ctx: Ctx, quarters: int) -> list[Fact]:
    start = months_before(ctx.week, 3 * quarters)
    return [f for f in ctx.facts if start <= f.as_of <= ctx.week]


def compute(ctx: Ctx) -> SignalResult:
    c = ctx.section("s9_text")
    types = frozenset(c["fact_types"])
    facts = list(ctx.facts)
    # one fact per subject: the same order restated in a press release and a 10-Q counts once
    hits = sorted({f"{f.fact_type}:{f.subject_key}" for f in recent_facts(ctx, int(c["lookback_quarters"]))
                   if qualifies(f, facts, types)})  # fmt: skip
    inputs = {"count": len(hits), "facts": hits[:10]}
    if not hits:
        return quiet(**inputs)
    return fired(min(Decimal(1), cfg_dec(c, "strength_per_fact") * len(hits)), **inputs)
