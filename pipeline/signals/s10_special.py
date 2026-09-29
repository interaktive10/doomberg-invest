"""S10 special situations (BRIEF §4.6): a spin-off or demerger <= 18 months ago, a reorganization <= 24 months, a
rights issue <= 6 months, or a holding company listed in config/holdcos.yaml. Strength 0.6."""

from __future__ import annotations

from pipeline.signals.base import Ctx, SignalResult, cfg_dec, fired, months_before, quiet

ID, FAMILY = "S10", "structural"


def compute(ctx: Ctx) -> SignalResult:
    c = ctx.section("s10_special")
    months = {
        "spinoff": int(c["spinoff_demerger_months"]),
        "demerger": int(c["spinoff_demerger_months"]),
        "reorganization": int(c["reorganization_months"]),
        "rights_issue": int(c["rights_issue_months"]),
    }
    recent = sorted(
        {f"{e.kind}:{e.event_date}" for e in ctx.events
         if e.kind in months and months_before(ctx.week, months[e.kind]) <= e.event_date <= ctx.week}
    )  # fmt: skip
    inputs = {"events": recent, "holdco": ctx.holdco}
    return fired(cfg_dec(c, "strength"), **inputs) if recent or ctx.holdco else quiet(**inputs)
