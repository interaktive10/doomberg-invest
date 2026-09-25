"""M4-01: every signal S1-S12 and red flag R1-R6 on F-SYNQ (fixtures/synq): a true case, a false case and a
just-below-threshold case, all passing. Strengths are checked to 8 decimals."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals import redflags
from pipeline.signals.base import CapexView, Ctx, Event, Fact, Holding, Insider, SectorView
from pipeline.signals.registry import SIGNALS
from pipeline.signals.series import Quarter, Series

DOC = json.loads((REPO_ROOT / "fixtures" / "synq" / "cases.json").read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = DOC["cases"]
SIGNALS_CFG = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
FLAGS_CFG = yaml.safe_load((REPO_ROOT / "config" / "redflags.yaml").read_text(encoding="utf-8"))
EIGHT = Decimal("0.00000001")


def d(x: Any) -> Decimal | None:
    return None if x is None else Decimal(str(x))


def holding(h: dict[str, Any]) -> Holding:
    pcts = (d(h.get(k)) for k in ("fii_pct", "dii_pct", "promoter_pct", "promoter_pledged_pct"))
    return Holding(date.fromisoformat(h["quarter_end"]), h.get("inst_holders"), *pcts)


def insider(i: dict[str, Any]) -> Insider:
    when, filed = date.fromisoformat(i["event_date"]), datetime.fromisoformat(i["filed_at"])
    return Insider("c", i["person"], when, filed, i["kind"], d(i["value"]), i["planned"], i["source_url"])


def fact(f: dict[str, Any]) -> Fact:
    when = date.fromisoformat(f["as_of"])
    return Fact(f["fact_type"], f["subject_key"], when, d(f.get("value_num")), counterparty=f.get("counterparty"))


def event(e: dict[str, Any]) -> Event:
    return Event(e["kind"], date.fromisoformat(e["event_date"]), e.get("detail", {}))


def sector_view(sec: dict[str, Any] | None) -> SectorView | None:
    if sec is None:
        return None
    capex, yoy = [d(v) for v in sec["capex_da_medians"]], [d(v) for v in sec["revenue_yoy_medians"]]
    return SectorView(sec["sector"], capex, yoy, sec["tightness_facts"])


def capex_view(cap: dict[str, Any] | None) -> CapexView | None:
    if cap is None:
        return None
    return CapexView(cap["categories"], cap["direction"], {k: Decimal(v) for k, v in cap["input_growth"].items()})


def ctx_for(case: dict[str, Any]) -> Ctx:
    quarters = [
        Quarter(date.fromisoformat(q["end"]), {k: d(v) for k, v in {**DOC["base"], **q["values"]}.items()})
        for q in case["quarters"]
    ]
    return Ctx(
        company_id="c",
        market=case["market"],
        week=date.fromisoformat(case["week"]),
        series=Series(quarters, case["market"]),
        cfg=SIGNALS_CFG,
        ownership=[holding(h) for h in case.get("ownership", [])],
        insiders=[insider(i) for i in case.get("insiders", [])],
        events=[event(e) for e in case.get("events", [])],
        facts=[fact(f) for f in case.get("facts", [])],
        holder_pct_in_size_decile=d(case.get("holder_pct_in_size_decile")),
        sector=sector_view(case.get("sector")),
        capex=capex_view(case.get("capex")),
        fired=case.get("prior", {}),
    )


def flag_of(case: dict[str, Any]) -> redflags.FlagResult:
    return next(f for f in redflags.compute_all(ctx_for(case), FLAGS_CFG) if f.flag_id == case["target"])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_synq_case(case: dict[str, Any]) -> None:
    target, expect = case["target"], case["expect"]
    if target.startswith("S"):
        r = {m.ID: m for m in SIGNALS}[target].compute(ctx_for(case))
        assert "missing" not in r.inputs, r.inputs  # the rule was evaluated, not skipped for lack of data
        assert r.fired is expect["fired"], r.inputs
        if expect["strength"] is not None:
            assert r.strength.quantize(EIGHT) == Decimal(expect["strength"]).quantize(EIGHT), r.inputs
        if not r.fired:
            assert r.strength == 0
    else:
        flag = flag_of(case)
        assert flag.status == ("fired" if expect["fired"] else "clear"), flag.inputs


def test_every_signal_and_flag_has_true_false_and_boundary_cases() -> None:
    kinds: dict[str, set[str]] = defaultdict(set)
    for c in CASES:
        kinds[c["target"]].add(c["kind"])
    assert set(kinds) == {f"S{i}" for i in range(1, 13)} | {f"R{i}" for i in range(1, 7)}
    assert all({"true", "false", "boundary"} <= k for k in kinds.values()), kinds


def test_only_r3_and_r5_are_hard() -> None:
    fired_cases = [c for c in CASES if c["target"].startswith("R") and c["kind"] == "true"]
    assert {c["target"] for c in fired_cases if flag_of(c).hard} == {"R3", "R5"}


def test_fixture_is_reproducible() -> None:
    script = REPO_ROOT / "fixtures" / "synq" / "make_synq.py"
    assert subprocess.run([sys.executable, str(script), "--check"], check=False).returncode == 0
