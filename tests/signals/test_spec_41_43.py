"""docs/SPEC_ISSUES.md 41-43 (applied 2026-10-08), on the 2026-W40 candidates' own numbers: S4 needs TTM CFO to rise
(Pfizer: CFO -12% while net income fell 60%); S1 and C2's g(ob) need an order book of at least a quarter of TTM
revenue (Alpha Metallurgical: 6%); C2 is null where growth lowers the reverse DCF's value, and its evidence growth
reads TTM revenue YoY, not a lumpy quarter's."""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal as D
from typing import Any

import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals import s01_orderbook, s04_earnings_quality
from pipeline.signals.base import Ctx
from pipeline.signals.reverse_dcf import c2
from pipeline.signals.series import Quarter, Series

SIGNALS = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
C2_CFG = yaml.safe_load((REPO_ROOT / "config" / "context.yaml").read_text(encoding="utf-8"))["c2_reverse_dcf"]
ENDS = [date(2023, 9, 30), date(2023, 12, 31), date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30),
        date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31),
        date(2026, 3, 31), date(2026, 6, 30)]  # fmt: skip


def series(**cols: list[int]) -> Series:
    n = len(next(iter(cols.values())))
    ends = ENDS[-n:]
    return Series([Quarter(e, {k: D(v[i]) for k, v in cols.items()}) for i, e in enumerate(ends)], "us")


def without(section: str, key: str) -> dict[str, Any]:
    cfg = copy.deepcopy(SIGNALS)
    cfg[section].pop(key)
    return cfg


def test_s4_needs_cash_flow_to_rise_not_only_net_income_to_fall() -> None:
    """Pfizer's last 8 quarters ($ millions): CCR 1.41 -> 3.09 because net income fell 60%; CFO fell 12%."""
    s = series(cfo=[6714, 6721, 2335, -582, 4603, 5348, 2615, 835],
               net_income=[4465, 410, 2967, 2910, 3541, -1647, 2687, -248], total_assets=[200000] * 8)  # fmt: skip
    now = s04_earnings_quality.compute(Ctx("c", "us", date(2026, 10, 2), s, SIGNALS))
    assert not now.fired and now.inputs["ttm_cfo"] < now.inputs["ttm_cfo_year_ago"]
    before = s04_earnings_quality.compute(Ctx("c", "us", date(2026, 10, 2), s,
                                              without("s4_earnings_quality", "cfo_must_rise_yoy")))  # fmt: skip
    assert before.fired and before.strength == D(1)


def test_s4_still_fires_when_cash_flow_rises() -> None:
    """Celsius ($ thousands): CFO more than doubled while net income held."""
    s = series(cfo=[12934, 75672, 103367, 43712, 331801, -119438, 73723, 222543],
               net_income=[6356, -18876, 44419, 99855, -61014, 24739, 110099, 55293],
               total_assets=[3000000] * 8)  # fmt: skip
    assert s04_earnings_quality.compute(Ctx("c", "us", date(2026, 10, 2), s, SIGNALS)).fired


AMR = {"revenue": [741820, 959991, 864072, 803969, 671897, 617347, 531957, 550274, 526778, 520472, 524987, 492856],
       "rpo": [156552, 124612, 85016, 59905, 38623, 24898, 20635, 35896, 51677, 95860, 107712, 124373]}  # fmt: skip


def test_s1_and_c2_ignore_an_order_book_under_a_quarter_of_revenue() -> None:
    """Alpha Metallurgical ($ thousands): RPO up 246% while revenue fell, but RPO is 6% of TTM revenue."""
    ctx = Ctx("c", "us", date(2026, 10, 2), series(**AMR), SIGNALS)
    res = s01_orderbook.compute(ctx)
    assert not res.fired and abs(res.inputs["coverage"] - 0.060226) < 1e-6
    assert s01_orderbook.compute(Ctx("c", "us", date(2026, 10, 2), series(**AMR),
                                     without("s1_orderbook", "min_coverage"))).strength == D(1)  # fmt: skip
    assert s01_orderbook.orderbook_growth(ctx, min_coverage=D("0.25")) is None
    g = s01_orderbook.orderbook_growth(ctx)
    assert g is not None and abs(g - D("2.464815")) < D("0.000001")


def _quarters(rev: list[D], margin: str, equity: list[int]) -> Series:
    ends = [date(2021 + (i + 2) // 4, 3 * ((i + 2) % 4) + 3, 30 if 3 * ((i + 2) % 4) + 3 in (6, 9) else 31)
            for i in range(len(rev))]  # fmt: skip
    m = D(margin)
    return Series([Quarter(e, {"revenue": r, "op_income": r * m, "pretax_income": r * m,
                               "tax_expense": r * m * D("0.21"), "equity": D(equity[i]), "cash": D(0),
                               "total_debt": D(0), "total_assets": D(9000)})
                   for i, (e, r) in enumerate(zip(ends, rev, strict=True))], "us")  # fmt: skip


def test_c2_is_null_where_growth_lowers_the_dcf_value() -> None:
    """A 10% margin with capital growing far faster than revenue (S2C at its 0.5 floor): each $ of growth earns
    0.10 x 0.79 x 0.5 = 4% on its capital, under the 9% discount rate, so g* would read backwards."""
    s = _quarters([D(1000) * D("1.01") ** i for i in range(20)], "0.10", [3000 + 500 * i for i in range(20)])
    got = c2(s, D(1500), "us", C2_CFG)
    assert got.value is None and got.score is None and got.inputs["missing"] == ["value_creating_growth"]
    assert abs(got.inputs["growth_return"] - 0.10 * 0.79 * 0.5) < 1e-9
    old = c2(s, D(1500), "us", {**C2_CFG, "growth_must_add_value": False})
    assert old.score is not None  # what W40 scored: a number with the wrong sign


def test_c2_evidence_growth_reads_ttm_revenue_growth() -> None:
    """A lumpy last quarter (1.5x) sets the quarterly YoY far above the TTM's; g_e follows the TTM."""
    rev = [D(1000) * D("1.02") ** i for i in range(20)]
    rev[-1] *= D("1.5")
    s = _quarters(rev, "0.15", [3000 + 20 * i for i in range(20)])
    ttm = c2(s, D(20000), "us", C2_CFG).inputs["g_e"]
    quarterly = c2(s, D(20000), "us", {**C2_CFG, "evidence_growth": {**C2_CFG["evidence_growth"],
                                                                         "latest_yoy_basis": "quarter"}})  # fmt: skip
    assert ttm is not None and quarterly.inputs["g_e"] is not None and ttm < quarterly.inputs["g_e"]
