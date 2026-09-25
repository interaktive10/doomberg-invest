"""M4-03: the reverse DCF recovers a known g within +/-0.1 pp from a synthetic EV, g* rises with EV, and there is
no answer when no growth rate in [-20%, 60%] explains the EV (BRIEF §4.7 C2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest
import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals.reverse_dcf import (
    DcfInputs,
    c2,
    evidence_growth,
    five_year_margin,
    implied_growth,
    present_value,
    sales_to_capital,
)
from pipeline.signals.series import Quarter, Series

CFG = yaml.safe_load((REPO_ROOT / "config" / "context.yaml").read_text(encoding="utf-8"))["c2_reverse_dcf"]
BASE = DcfInputs(ev=0.0, revenue=1000.0, margin=0.15, tax=0.21, s2c=1.5, discount=0.09, terminal_growth=0.025)


@pytest.mark.parametrize("g", [-0.15, -0.05, 0.0, 0.03, 0.08, 0.15, 0.30, 0.55])
def test_recovers_a_known_growth_rate(g: float) -> None:
    x = replace(BASE, ev=present_value(g, BASE))
    got = implied_growth(x)
    assert got is not None and abs(got - g) <= 0.001


def test_implied_growth_rises_with_ev() -> None:
    evs = [present_value(g, BASE) * k for g in (0.02,) for k in (0.6, 0.8, 1.0, 1.2, 1.5, 2.0)]
    gs = [implied_growth(replace(BASE, ev=ev)) for ev in evs]
    assert all(g is not None for g in gs)
    assert all(a is not None and b is not None and a < b for a, b in zip(gs, gs[1:], strict=False))


def test_no_root_is_none() -> None:
    assert implied_growth(replace(BASE, ev=present_value(0.60, BASE) * 3)) is None  # needs > 60% a year
    assert implied_growth(replace(BASE, ev=present_value(-0.20, BASE) / 3)) is None  # below -20% a year
    assert implied_growth(replace(BASE, ev=-100.0)) is None


def test_india_uses_its_own_rates() -> None:
    assert CFG["discount_rate"] == {"us": 0.09, "in": 0.12} and CFG["terminal_growth"] == {"us": 0.025, "in": 0.045}


def test_evidence_growth_weights_and_caps() -> None:
    assert evidence_growth(D("0.20"), D("0.10"), D("0.10"), CFG) == D("0.14")  # 0.4x0.2 + 0.3x0.1 + 0.3x0.1
    assert evidence_growth(None, D("0.10"), D("0.20"), CFG) == D("0.15")  # renormalized without the order book
    assert evidence_growth(D("1.0"), D("0.9"), D("0.9"), CFG) == D("0.40")  # capped
    assert evidence_growth(D("0.5"), None, None, CFG) is None


def test_c2_on_a_series() -> None:
    """A company growing 2% a quarter (TTM +8.2%) whose EV prices ~5% growth: the gap is positive, score > 50."""
    ends = [date(2021 + (i + 2) // 4, 3 * ((i + 2) % 4) + 3, 30 if 3 * ((i + 2) % 4) + 3 in (6, 9) else 31)
            for i in range(20)]  # fmt: skip
    rows = []
    for i, e in enumerate(ends):
        rev = D(1000) * D("1.02") ** i
        rows.append(Quarter(e, {"revenue": rev, "op_income": rev * D("0.15"), "pretax_income": rev * D("0.15"),
                                "tax_expense": rev * D("0.15") * D("0.21"), "equity": D(3000) + 20 * i, "cash": D(0),
                                "total_debt": D(0), "total_assets": D(6000)}))  # fmt: skip
    s = Series(rows, "us")
    s2c, margin = sales_to_capital(s, CFG), five_year_margin(s, CFG)
    assert s2c == D(4) and margin == D("0.15")  # revenue grew far more than capital: S2C clipped at 4
    x = DcfInputs(ev=0.0, revenue=float(s.ttm("revenue") or 0), margin=0.15, tax=0.21, s2c=4.0, discount=0.09,
                  terminal_growth=0.025)  # fmt: skip
    got = c2(s, D(str(present_value(0.05, x))), "us", CFG)
    assert abs(got.inputs["g_star"] - 0.05) < 0.001
    assert got.value is not None and got.score is not None and got.value > 0 and got.score > 50  # g_e ~8% > 5%
    assert c2(s, None, "us", CFG).score is None
