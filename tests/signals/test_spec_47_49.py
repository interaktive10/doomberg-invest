"""docs/SPEC_ISSUES.md 47-49 (approved by Manzoor: analysis audit P3, P5 and P6), on the 2026-W40 candidates' own
numbers where they show the problem.
- 47: S4 needs TTM net income >= 0.9x a year earlier (Matador: -15% with CFO +8% fired at full strength) and is quiet
  for banks, lenders and insurers (SIC 6000-6411; REITs at 6798 are scored); R2 compares receivables growth with the
  same quarter's revenue growth, not TTM revenue's.
- 48: C2 is null unless ROIC beats the discount rate (Howard Hughes' other inputs with a ROIC of 5.4%: null), and null
  when ROIC is unknown; C3 is null when its comparison group has fewer than 30 members; C4 is gone, and the C4 weight
  config/weights.yaml still carries is never read.
- 49: S7 doesn't count a filer whose only role is 10% owner; a joint "director; 10% owner" filing and one without a
  role still count."""

from __future__ import annotations

import copy
import importlib.util
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal as D
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from pipeline.db import seed
from pipeline.db.models import Company, InsiderEvent
from pipeline.lab import panel
from pipeline.net.http import ALLOWED_HOSTS
from pipeline.settings import REPO_ROOT
from pipeline.signals import context, redflags, reverse_dcf, s04_earnings_quality, s07_insider, weekly
from pipeline.signals.base import Ctx, Insider
from pipeline.signals.scores import Evidence, Weights, gap
from pipeline.signals.series import Quarter, Series

SIGNALS = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
FLAGS = yaml.safe_load((REPO_ROOT / "config" / "redflags.yaml").read_text(encoding="utf-8"))
WEEK = date(2026, 10, 2)
ENDS = [date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30),
        date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]  # fmt: skip


def series(**cols: list[int] | list[str]) -> Series:
    return Series([Quarter(e, {k: D(v[i]) for k, v in cols.items()}) for i, e in enumerate(ENDS)], "us")


def without(section: str, key: str) -> dict[str, Any]:
    cfg = copy.deepcopy(SIGNALS)
    cfg[section].pop(key)
    return cfg


# ---------------------------------------------------------------- 47: S4

# $ thousands, the last 8 quarters to 2026-06-30 as scored in 2026-W40 (total assets are a flat stand-in)
MATADOR = {
    "net_income": [248291, 214533, 240085, 150225, 176364, 192547, -35872, 390652],
    "cfo": [610437, 574959, 727879, 501027, 721660, 474449, 470546, 937128],
    "total_assets": [10000000] * 8,
}
CELSIUS = {
    "net_income": [6356, -18876, 44419, 99855, -61014, 24739, 110099, 55293],
    "cfo": [12934, 75672, 103367, 43712, 331801, -119438, 73723, 222543],
    "total_assets": [3000000] * 8,
}


def s4(cols: dict[str, Any], cfg: dict[str, Any] = SIGNALS, sic: str | None = None) -> Any:
    return s04_earnings_quality.compute(Ctx("c", "us", WEEK, series(**cols), cfg, sic=sic))


def test_s4_is_quiet_when_net_income_falls_15_pct_while_cfo_rises_8_pct() -> None:
    """Matador: TTM NI 853.1m -> 723.7m (0.848x) while TTM CFO rose 7.9%, so CCR went 2.83 -> 3.60."""
    now = s4(MATADOR)
    assert not now.fired and now.strength == 0
    i = now.inputs
    assert abs(i["ttm_net_income"] / i["ttm_net_income_year_ago"] - 0.8483) < 1e-4
    assert abs(i["ttm_cfo"] / i["ttm_cfo_year_ago"] - 1.0785) < 1e-4
    before = s4(MATADOR, without("s4_earnings_quality", "ni_min_ratio_yoy"))
    assert before.fired and before.strength == D(1)  # what W40 scored


def test_s4_still_fires_when_net_income_holds() -> None:
    """Celsius in W40: TTM NI 131.8m -> 129.1m (0.98x) while CFO more than doubled."""
    r = s4(CELSIUS)
    assert r.fired and r.strength == D(1)
    assert abs(r.inputs["ttm_net_income"] / r.inputs["ttm_net_income_year_ago"] - 0.98) < 1e-3


@pytest.mark.parametrize(("ni_last", "fires"), [("90", True), ("89.99", False)])
def test_s4_net_income_floor_is_inclusive(ni_last: str, fires: bool) -> None:
    """TTM NI 400 -> 360 is exactly 0.9x and fires; 359.99 doesn't (CCR 1.10 -> 1.33, Sloan falling, CFO up)."""
    cols = {"net_income": ["100"] * 4 + ["90"] * 3 + [ni_last], "cfo": ["110"] * 4 + ["120"] * 4,
            "total_assets": ["10000"] * 8}  # fmt: skip
    assert s4(cols).fired is fires


@pytest.mark.parametrize(("sic", "excluded"), [
    ("6022", True),  # state commercial bank
    ("6000", True),
    ("6411", True),  # insurance agents and brokers
    ("6798", False),  # REITs (Howard Hughes) are scored
    ("2086", False),  # Celsius
    (None, False),  # no SIC (India; a filer without one)
])  # fmt: skip
def test_s4_is_quiet_for_banks_and_insurers_only(sic: str | None, excluded: bool) -> None:
    r = s4(CELSIUS, sic=sic)
    assert r.fired is not excluded
    assert (r.inputs.get("reason") == "financial SIC excluded") is excluded


def test_the_weekly_run_gives_s4_the_company_sic() -> None:
    """score_company passes the companies row's SIC to the signals (the Signal Lab scores through it too)."""

    def scored(sic: str) -> bool:
        cid = uuid.uuid4()
        c = Company(id=cid, market="us", name="Test Co", ticker="TST", sic=sic, sector=None, excluded_reason=None)
        b = weekly.Batch(rows={}, ownership={}, insiders={}, events={}, facts={})
        results, _, _ = weekly.score_company(c, series(**CELSIUS), b, weekly.Configs.load(), weekly.CrossSection(),
                                             WEEK)  # fmt: skip
        return results["S4"].fired

    assert scored("2086") and not scored("6022")


# ---------------------------------------------------------------- 47: R2


def r2(receivables_last: int, basis: str | None = None) -> redflags.FlagResult:
    cfg = FLAGS["R2"] if basis is None else {**FLAGS["R2"], "revenue_basis": basis}
    s = series(revenue=[1000] * 7 + [1400], receivables=[1000] * 7 + [receivables_last])
    return redflags.r2(Ctx("c", "us", WEEK, s, SIGNALS), cfg)


def test_r2_compares_receivables_with_the_same_quarters_revenue() -> None:
    """Quarterly revenue +40%, receivables +45%: a 5 pp gap. Against TTM revenue (+10%) the gap was 35 pp."""
    now = r2(1450)
    assert now.status == "clear" and not now.hard
    assert now.inputs["revenue_growth"] == 0.4 and now.inputs["gap_pp"] == 5.0
    assert now.inputs["revenue_basis"] == "quarter"
    before = r2(1450, basis="ttm")
    assert before.status == "fired" and before.inputs["gap_pp"] == 35.0


def test_r2_still_fires_when_receivables_outgrow_the_quarter() -> None:
    r = r2(1650)  # +65% vs +40%
    assert r.status == "fired" and r.inputs["gap_pp"] == 25.0


# ---------------------------------------------------------------- 48: C2, C3 and Gap without C4

C2_CFG = yaml.safe_load((REPO_ROOT / "config" / "context.yaml").read_text(encoding="utf-8"))["c2_reverse_dcf"]
# Howard Hughes' C2 inputs in 2026-W40 ($ thousands): TTM revenue 2,372.9m, operating margin 27.06%, tax 23.79%,
# S2C at its 1.5 default and EV 6,704.5m (g* 1.51%). Its equity sets ROIC = TTM NOPAT 489.3m / invested capital.
HHH = {"revenue": [593232] * 8, "op_income": [160528] * 8, "pretax_income": [160528] * 8, "tax_expense": [38194] * 8,
       "cash": [0] * 8, "total_debt": [0] * 8, "total_assets": [10_000_000] * 8}  # fmt: skip
HHH_EV = D(6704451)


@pytest.mark.parametrize(("equity", "roic", "scored"), [
    (9_061_778, 0.054, False),  # under the 9% US discount rate, as Howard Hughes' own 6.9% is
    (4_077_800, 0.12, True),
    (None, None, False),  # no equity reported, so no invested capital: ROIC unknown
])  # fmt: skip
def test_c2_needs_roic_above_the_discount_rate(equity: int | None, roic: float | None, scored: bool) -> None:
    s = series(**HHH) if equity is None else series(**HHH, equity=[equity] * 8)
    got = reverse_dcf.c2(s, HHH_EV, "us", C2_CFG)
    assert (got.score is not None) is scored
    if scored:
        assert abs(got.inputs["g_star"] - 0.01513) < 1e-4 and got.inputs["s2c"] == 1.5  # HHH's W40 g*
    else:
        assert got.value is None and got.inputs == {"missing": ["roic_above_discount"], "roic": roic, "discount": 0.09}


def test_c3_needs_a_comparison_group_of_30() -> None:
    assert context.c3(D("0.01"), [D(x) / 100 for x in range(-2, 3)], D(90), 30).inputs == {
        "missing": ["population"], "return_52w": 0.01, "population": 5, "min_population": 30}  # fmt: skip
    got = context.c3(D("0.01"), [D(x) / 100 for x in range(-15, 15)], D(90), 30)  # 30 returns, -15% to +14%
    assert got.score == D(45) and got.inputs["population"] == 30  # 16 below, 1 tie: pct 55


def staged(n: int) -> tuple[dict[uuid.UUID, weekly.Scored], dict[uuid.UUID, weekly.Priced]]:
    """n priced US companies with 52-week returns of 0%, 1%, ... and nothing else."""
    scored, priced = {}, {}
    for i in range(n):
        cid = uuid.uuid4()
        c = Company(id=cid, market="us", name=f"Company {i:02d} Inc", ticker=f"TK{i:02d}")
        scored[cid] = weekly.Scored(c, Series([], "us"), Evidence(D(50), D(0), {}, (), 0, False), False, {}, None, {})
        priced[cid] = weekly.Priced(None, None, D(i) / 100, context.Metric(None, None, None, {}),
                                    reverse_dcf.C2(None, None, {}))  # fmt: skip
    return scored, priced


@pytest.mark.parametrize(("n", "min_population", "scored"), [(29, 30, False), (30, 30, True), (5, 5, True)])
def test_the_weekly_run_takes_c3_min_population_from_config_and_writes_no_c4(
    n: int, min_population: int, scored: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(weekly, "benchmark_returns", lambda conn, symbols, week, weeks=52: [])
    cfgs = weekly.Configs.load()
    assert cfgs.context["c3_runup"]["min_population"] == 30 and "c4_attention" not in cfgs.context
    c3_cfg = {**cfgs.context["c3_runup"], "min_population": min_population}
    rows = weekly.context_rows(None, WEEK, replace(cfgs, context={**cfgs.context, "c3_runup": c3_cfg}), *staged(n))
    assert len(rows) == 3 * n and {r.metric_id for r in rows} == {"C1", "C2", "C3"}
    assert all((r.inputs["score"] is not None) is scored for r in rows if r.metric_id == "C3")


def test_the_lab_gap_takes_c3_min_population_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Signal Lab's C3 ranks within the month's population (panel.MonthCross.returns) under the same rule."""
    seen: list[context.Metric] = []
    real = context.c3

    def spy(*args: Any) -> context.Metric:
        seen.append(real(*args))
        return seen[-1]

    monkeypatch.setattr(context, "c3", spy)
    m = date(2016, 1, 31)
    feed = SimpleNamespace(series=Series([], "us"), market="us", close=lambda d: D(110) if d == m else D(100))
    cfgs = weekly.Configs.load()
    for n, scored in ((29, False), (30, True)):
        mc = panel.MonthCross(weekly.CrossSection(), None, [D(i) / 100 for i in range(n)])  # type: ignore[arg-type]
        panel._gap(feed, SimpleNamespace(g_ob=None), m, None, [], mc, cfgs, panel.Options(),  # type: ignore[arg-type]
                   panel.Shared.of(cfgs))  # fmt: skip
        assert seen[-1].inputs["return_52w"] == 0.1 and (seen[-1].score is not None) is scored


def test_gap_never_reads_the_c4_weight_left_in_weights_yaml() -> None:
    """config/weights.yaml keeps C4: 1.0 (it changes only through its own human-approved PR). gap() reads a weight
    only for a metric it is given, so the leftover counts neither toward the mean nor toward the two-metric minimum."""
    w = Weights.load()
    assert gap({"C1": D(60), "C2": None, "C3": D(40)}, w, 2) == D(50)
    assert gap({"C1": D(60), "C2": None, "C3": None}, w, 2) is None
    heavy = Weights(w.version, w.families, w.signals, {**w.context, "C4": D(5)})
    assert gap({"C1": D(60), "C2": D(30), "C3": D(30)}, heavy, 2) == D(40)


def test_gdelt_is_gone_end_to_end() -> None:
    """No client, no allowlisted host, no seeded health row and no fixtures; the old source_health row stays (no
    migration) and simply stops being updated."""
    assert importlib.util.find_spec("pipeline.net.gdelt") is None
    assert not any("gdelt" in host for host in ALLOWED_HOSTS) and "gdelt" not in seed.SOURCES
    assert not (REPO_ROOT / "fixtures" / "gdelt").exists() and not hasattr(context, "c4")
    assert not hasattr(weekly, "attention") and not hasattr(weekly, "mark_gdelt")


# ---------------------------------------------------------------- 49: S7

S7_WEEK = date(2026, 9, 18)
DAY, FILED = date(2026, 9, 1), datetime(2026, 9, 2, 20, tzinfo=UTC)


def buy(person: str, value: int, role: str | None) -> Insider:
    url = f"https://www.sec.gov/f4/{person.replace(' ', '_')}"
    return Insider("c", person, DAY, FILED, "open_market_buy", D(value), False, url, "USD", role=role)


def s7(*insiders: Insider, cfg: dict[str, Any] = SIGNALS) -> Any:
    return s07_insider.compute(Ctx("c", "us", S7_WEEK, Series([], "us"), cfg, insiders=list(insiders)))


def test_s7_ignores_two_funds_that_are_only_10pct_owners() -> None:
    funds = (buy("Alpha Capital LP", 5_000_000, "10% owner"), buy("Beta Partners Fund", 3_000_000, "10% owner"))
    r = s7(*funds)
    assert not r.fired and r.inputs["insiders"] == 0
    assert r.inputs["ignored_by_role"] == ["Alpha Capital LP", "Beta Partners Fund"]
    assert s7(*funds, cfg=without("s7_insider", "us_ignore_roles")).fired  # what counted before


def test_s7_a_fund_does_not_complete_a_cluster() -> None:
    r = s7(buy("Alpha Capital LP", 5_000_000, "10% owner"), buy("DIRECTOR ONE", 300_000, "director"))
    assert not r.fired and r.inputs["insiders"] == 1


def test_s7_fires_on_a_director_and_the_ceo() -> None:
    r = s7(buy("DIRECTOR ONE", 150_000, "director"), buy("CHIEF EXEC", 120_000, "Chief Executive Officer"))
    assert r.fired and r.inputs["insiders"] == 2 and "ignored_by_role" not in r.inputs


def test_s7_counts_a_director_who_is_also_a_10pct_owner() -> None:
    r = s7(buy("FOUNDER", 200_000, "director; 10% owner"), buy("DIRECTOR ONE", 100_000, "director"))
    assert r.fired and r.inputs["buyers"] == ["DIRECTOR ONE", "FOUNDER"]


def test_s7_counts_a_filing_without_a_role() -> None:
    r = s7(buy("UNKNOWN ROLE", 200_000, None), buy("DIRECTOR ONE", 100_000, "director"))
    assert r.fired and r.inputs["insiders"] == 2


def test_the_weekly_run_reads_the_filer_role() -> None:
    """insider_events.role reaches S7 (the weekly run's converter; the Signal Lab uses the same one)."""
    row = InsiderEvent(company_id=uuid.uuid4(), event_date=date(2026, 9, 1), filed_at=datetime(2026, 9, 2, tzinfo=UTC),
                       person="Alpha Capital LP", role="10% owner", kind="open_market_buy", shares=D(1000),
                       value=D(5_000_000), currency="USD", planned=False, source_url="https://www.sec.gov/f4/a",
                       amends=None)  # fmt: skip
    ins = weekly.insider(row)
    assert ins.role == "10% owner" and ins.amends is None and ins.currency == "USD"
