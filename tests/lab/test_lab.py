"""The Signal Lab on F-LAB (BRIEF §4.10, §8 M8-01, M8-02): the planted signal is found out of sample, the noise
signal isn't, and moving the planted filings later removes the effect (the panel reads point in time)."""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import yaml

from pipeline.lab import evaluate, panel
from pipeline.lab.events import events
from pipeline.lab.panel import PanelRow
from pipeline.lab.prices import month_ends
from pipeline.signals import registry, s01_orderbook, s05_capital_discipline
from pipeline.signals import weekly as live

from .conftest import load_generator

FAST = panel.Options(modules=(s01_orderbook, s05_capital_discipline), with_legacy=False, with_gap=False)


@cache
def stats(shift: int) -> dict[tuple[str, str], evaluate.Stat]:
    gen = load_generator()
    data, _ = gen.make(seed=7, n=500, shift_filed_days=shift)
    rows = panel.build(data, month_ends(gen.FIRST_MONTH, gen.LAST_MONTH), live.Configs.load(), (12,), FAST)
    out = evaluate.event_stats(events(rows, 12), (12,), gen.PERIODS)
    return {(s.signal_id, s.period): s for s in out}


def test_planted_signal_is_found_out_of_sample() -> None:
    """M8-01: the planted S1 effect (+2.5% a month for a year after the filing) has t_nw >= 3 out of sample."""
    s = stats(0)[("S1", "out_of_sample")]
    assert s.n >= 40 and s.mean is not None and s.mean > 0.2 and s.t_nw is not None and s.t_nw >= 3
    assert (s.hit_rate or 0) > 0.7


def test_noise_signal_is_not() -> None:
    """M8-01: S5 fires on buybacks that move nothing: |t_nw| < 2 in both periods."""
    for period in ("in_sample", "out_of_sample"):
        s = stats(0)[("S5", period)]
        assert s.n >= 40 and s.t_nw is not None and abs(s.t_nw) < 2, (period, s)


def test_moving_filed_at_later_removes_the_planted_effect() -> None:
    """M8-02 (leak test): the planted companies' filings are made public 400 days later. S1 then fires after the
    drift, and a point-in-time panel finds nothing; a panel that read by period end would still find it."""
    s = stats(400)[("S1", "out_of_sample")]
    assert s.n >= 20 and s.t_nw is not None and abs(s.t_nw) < 2 and s.mean is not None and abs(s.mean) < 0.1


def test_the_panel_runs_the_live_signal_code() -> None:
    """Import, don't copy (§4.10.1): the default signal set is the live registry, scored by the live run's code."""
    assert panel.Options().modules is registry.SIGNALS
    assert panel.live is live and panel.live.score_company is live.score_company


def test_full_panel_with_legacy_rules_and_gap(f_lab: ModuleType) -> None:
    """All twelve signals, L1-L6 and Gap on a small slice: every row carries every rule, Evidence in [0, 100]."""
    data, _ = f_lab.make(seed=3, n=40)
    rows = panel.build(data, month_ends(f_lab.FIRST_MONTH, date(2017, 6, 30)), live.Configs.load(), (12, 24))
    assert len(rows) == 40 * 30
    ids = {*(m.ID for m in registry.SIGNALS), "L1", "L2", "L3", "L4", "L5", "L6"}
    assert all(set(r.fired) == ids for r in rows)
    assert all(r.evidence is not None and 0 <= r.evidence <= 100 for r in rows)
    assert any(r.gap is not None for r in rows) and any(r.fired["L6"] for r in rows)
    # forward returns read every close of the company (F-LAB's run to 2019-12), not only the panel's months
    assert all(12 in r.excess and 24 in r.excess for r in rows)


def row(cid: object, m: date, fired: bool, excess: float = 0.0) -> PanelRow:
    return PanelRow(cid, m, {"S1": fired}, 0.0, None, 10.0, {12: 0.0}, {12: excess})  # type: ignore[arg-type]


def test_an_event_is_the_first_fire_in_12_months() -> None:
    """§4.10.2: a signal firing every month for 30 months gives events at months 0, 12 and 24."""
    cid = uuid4()
    months = month_ends(date(2015, 1, 31), date(2017, 6, 30))
    evts = events([row(cid, m, True) for m in months], 12)
    assert [e.month_end for e in evts] == [date(2015, 1, 31), date(2016, 1, 31), date(2017, 1, 31)]
    gaps = [row(cid, m, i in (0, 5, 13)) for i, m in enumerate(months)]
    assert [e.month_end for e in events(gaps, 12)] == [months[0], months[13]]  # month 5 is inside the window


@pytest.mark.parametrize("lags", [0, 12])
def test_newey_west_standard_error(lags: int) -> None:
    """Independent values one month apart: with no lags, the plain SE of the mean (population variance); lags
    only add the (here negative) cross terms, and t_nw never uses less than the plain error."""
    obs = [(m, v) for m, v in zip(month_ends(date(2015, 1, 31), date(2015, 6, 30)), (1.0, -1.0, 2.0, 0.0, 1.0, 3.0),
                                  strict=True)]  # fmt: skip
    se = evaluate.newey_west_se(obs, lags)
    mean = 1.0
    diag = sum((v - mean) ** 2 for _, v in obs) / len(obs) ** 2
    assert se is not None
    if lags == 0:
        assert abs(se**2 - diag) < 1e-12
    s = evaluate.stat("X", 12, "in_sample", obs)
    plain = evaluate.plain_se([v for _, v in obs])
    assert plain is not None and s.t_nw is not None and abs(s.t_nw) <= mean / plain + 1e-12
    assert (s.n, s.mean, s.median, s.hit_rate) == (6, 1.0, 1.0, 4 / 6)


def test_deciles_rank_within_the_month() -> None:
    m = date(2016, 1, 31)
    rows = [PanelRow(uuid4(), m, {}, float(i), None, 1.0, {}, {}) for i in range(20)]
    dec = evaluate.deciles(rows, "evidence")
    assert sorted(dec.values()) == [d for d in range(1, 11) for _ in range(2)]
    ties = [PanelRow(uuid4(), m, {}, 0.0, None, 1.0, {}, {}) for _ in range(10)]
    assert set(evaluate.deciles(ties, "evidence").values()) == {6}  # all tied: the middle decile


def test_every_signal_gets_statistics_even_without_events() -> None:
    cid = uuid4()
    rows = [row(cid, m, False) for m in month_ends(date(2015, 1, 31), date(2015, 3, 31))]
    stats = evaluate.event_stats(events(rows, 12), (12,), {"in_sample": (date(2015, 1, 31), date(2015, 12, 31))},
                                 ["S1", "S2"])  # fmt: skip
    assert [(s.signal_id, s.n, s.t_nw) for s in stats] == [("S1", 0, None), ("S2", 0, None)]


def test_periods_from_config() -> None:
    bounds = evaluate.period_bounds({"in_sample": ["2012-01", "2018-12"], "out_of_sample": ["2019-01", "2025-12"]})
    assert bounds == {"in_sample": (date(2012, 1, 31), date(2018, 12, 31)),
                      "out_of_sample": (date(2019, 1, 31), date(2025, 12, 31))}  # fmt: skip


def test_noise_companies_are_not_planted() -> None:
    """Review R1-F6: the noise signal's companies carry no planted drift."""
    _, truth = load_generator().make(seed=7, n=500)
    assert truth.planted and truth.noise and not truth.planted.keys() & truth.noise.keys()


def test_lab_results_notes_carry_the_unfloored_t() -> None:
    """Review R1-F2: lab_results.notes keeps the unfloored Newey-West t next to the prove-first lower bound."""
    from pipeline.lab.run import results

    s = stats(0)[("S5", "in_sample")]
    assert s.t_nw_unfloored is not None and s.t_nw is not None and abs(s.t_nw) <= abs(s.t_nw_unfloored) + 1e-9
    note = results([s], "us")[0].notes or ""
    assert note.startswith("lower_bound=") and f"t_nw_unfloored={s.t_nw_unfloored:.4f}" in note


def _feed(shares_by_quarter: list[tuple[date, int]], closes: list[tuple[date, float]]) -> panel.Feed:
    from datetime import UTC, datetime, time, timedelta
    from decimal import Decimal

    from pipeline.db.models import Company, FundamentalsRow
    from pipeline.lab.prices import MonthBar

    cid = uuid4()
    rows = [FundamentalsRow(company_id=cid, period_end=q, fiscal_label=f"Q{q:%Y%m}",
                            filed_at=datetime.combine(q + timedelta(days=30), time(21), tzinfo=UTC),
                            shares_outstanding=Decimal(n), currency="USD", source="sec_xbrl")
            for q, n in shares_by_quarter]  # fmt: skip
    bars = [MonthBar(m, Decimal(str(c)), Decimal(str(c)), Decimal(str(c))) for m, c in closes]
    company = Company(id=cid, market="us", name="Split Co", ticker="SPLT")
    return panel.Feed(company, panel.LabData("us", [company], {cid: rows}, {cid: bars}))


def test_share_basis_is_split_neutral_for_a_7_for_1_split() -> None:
    """Review R1-F1: a 7:1 split (outside the old standard ratios) puts earlier share counts on today's basis, so the
    adjusted close x the Lab's shares is the market cap of the day (raw close 7x the adjusted one)."""
    from datetime import UTC, datetime

    quarters = [(date(2013, 9, 30), 100_000_000), (date(2013, 12, 31), 100_000_000), (date(2014, 3, 31), 100_000_000),
                (date(2014, 6, 30), 700_000_000), (date(2014, 9, 30), 700_000_000)]  # fmt: skip
    feed = _feed(quarters, [(date(2014, 2, 28), 10.0), (date(2014, 10, 31), 10.0)])
    feed.advance(datetime(2014, 3, 1, tzinfo=UTC))  # February 2014: the latest known count is Q4 2013's 100M
    shares = feed.shares()
    assert shares is not None and shares == 700_000_000  # 100M x 7, today's basis
    raw_cap = 70.0 * 100_000_000  # the raw close was 7x the split-adjusted 10.0
    assert float(shares) * float(feed.close(date(2014, 2, 28)) or 0) == raw_cap


def test_aapl_share_basis_covers_the_2014_split() -> None:
    """Review R1-F1 on real data (F-US AAPL): 7:1 in June 2014 and 4:1 in August 2020, so a share count reported
    for 2013-12-31 is multiplied by 28."""
    import json

    from pipeline.us.fundamentals import load_xbrl_map, quarterize_company, to_models
    from pipeline.us.submissions import parse_submissions

    fix = Path(__file__).resolve().parents[2] / "fixtures" / "us"
    cf = json.loads((fix / "companyfacts" / "CIK0000320193.json").read_text(encoding="utf-8"))
    subs = parse_submissions(json.loads((fix / "submissions" / "CIK0000320193.json").read_text(encoding="utf-8")))
    cid = uuid4()
    rows = to_models(cid, quarterize_company(cf, subs, load_xbrl_map(), date(2026, 9, 20)).rows)
    from pipeline.db.models import Company

    company = Company(id=cid, market="us", name="Apple Inc.", ticker="AAPL")
    feed = panel.Feed(company, panel.LabData("us", [company], {cid: rows}, {cid: []}))
    assert feed._factor(date(2013, 12, 31)) == 28 and feed._factor(date(2020, 9, 26)) == 1


def test_ownership_revised_later_replays_the_version_current_each_month() -> None:
    """M4 review R1-F2 in the Lab: the loader reads every ownership version (as_of().ownership() keeps one per
    quarter), and each month sees the version as_of(month-end) would return, never a later revision."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from pipeline.db.models import Company, OwnershipRow
    from pipeline.db.pit import cutoff_for

    cid = uuid4()
    company = Company(id=cid, market="in", name="Revised Ltd", nse_symbol="RVSD")
    q = date(2026, 6, 30)
    first = OwnershipRow(company_id=cid, quarter_end=q, filed_at=datetime(2026, 7, 20, tzinfo=UTC),
                         fii_pct=Decimal(10), dii_pct=Decimal(2), source="nse_shp")  # fmt: skip
    revised = first.model_copy(update={"filed_at": datetime(2026, 10, 1, tzinfo=UTC), "fii_pct": Decimal(20)})
    feed = panel.Feed(company, panel.LabData("in", [company], {cid: []}, {cid: []}, {cid: [first, revised]}))

    def fii(m: date) -> list[Decimal | None]:
        return [h.fii_pct for h in feed.batch(m, cutoff_for(m)).ownership[cid]]

    assert fii(date(2026, 6, 30)) == [] and fii(date(2026, 8, 31)) == [Decimal(10)]
    assert fii(date(2026, 10, 31)) == [Decimal(20)]  # one row per quarter, the revision once it was filed


def _company_data(
    quarters: list[tuple[date, int]], closes: list[tuple[date, float]], name: str = "Pop Co"
) -> tuple[panel.LabData, UUID]:
    """One company with flat quarters (revenue as given, 100M shares, no debt or cash) filed 30 days after each
    quarter end, and month-end closes."""
    from datetime import UTC, datetime, time, timedelta
    from decimal import Decimal

    from pipeline.db.models import Company, FundamentalsRow
    from pipeline.lab.prices import MonthBar

    cid = uuid4()
    rows = [FundamentalsRow(company_id=cid, period_end=q, fiscal_label=f"Q{q:%Y%m}",
                            filed_at=datetime.combine(q + timedelta(days=30), time(21), tzinfo=UTC),
                            revenue=Decimal(rev), total_debt=Decimal(0), cash=Decimal(0),
                            shares_outstanding=Decimal(100_000_000), currency="USD", source="sec_xbrl")
            for q, rev in quarters]  # fmt: skip
    bars = [MonthBar(m, Decimal(str(c)), Decimal(str(c)), Decimal(str(c))) for m, c in closes]
    company = Company(id=cid, market="us", name=name, ticker=name[:4].upper())
    return panel.LabData("us", [company], {cid: rows}, {cid: bars}), cid


def _quarters(first: date, last: date) -> list[date]:
    from pipeline.lab.prices import add_months

    out, q = [], first
    while q <= last:
        out.append(q)
        q = add_months(q, 3)
    return out


def test_the_population_is_applied_point_in_time() -> None:
    """M8 review R2-F1: a company is in a month's population only with a 10-K/10-Q filed in the last 460 days and
    TTM revenue of at least $50M, both as known that month (never today's universe flag). Its rows start and stop
    with them, its forward returns still use every close, and the excess is over the month's population only."""
    from decimal import Decimal

    months = month_ends(date(2013, 6, 30), date(2017, 12, 31))
    small = [(q, 10_000_000 if q <= date(2013, 12, 31) else 30_000_000)
             for q in _quarters(date(2012, 12, 31), date(2014, 12, 31))]  # fmt: skip
    a, cid_a = _company_data(small, [(m, 10.0 + i) for i, m in enumerate(months)], "Shrinking Filer")
    b, cid_b = _company_data([(q, 1_000_000_000) for q in _quarters(date(2012, 12, 31), date(2017, 9, 30))],
                             [(m, 50.0 + i / 2) for i, m in enumerate(months)], "Big Co")  # fmt: skip
    data = panel.LabData("us", a.companies + b.companies, {**a.versions, **b.versions}, {**a.bars, **b.bars})
    pop = panel.Population(filing_days=460, min_ttm_revenue=Decimal(50_000_000))
    opts = panel.Options(modules=(s01_orderbook,), with_legacy=False, with_gap=False, population=pop)
    rows = panel.build(data, months, live.Configs.load(), (12,), opts)
    mine = [r for r in rows if r.company_id == cid_a]
    # TTM 10+10+10+30 = 60M >= 50M once Q1 2014 is filed (2014-04-30 21:00); the last filing (Q4 2014) is 2015-01-30,
    # and 2016-04-30 is the last month-end within 460 days of it
    assert (mine[0].month_end, mine[-1].month_end) == (date(2014, 4, 30), date(2016, 4, 30))
    assert len(mine) == 25 and all(r.month_end >= date(2013, 6, 30) for r in rows if r.company_id == cid_b)
    last = mine[-1]
    assert 12 in last.fwd and abs(last.fwd[12] - ((10.0 + 46) / (10.0 + 34) - 1)) < 1e-9  # 2017-04-30's close
    other = next(r for r in rows if r.company_id == cid_b and r.month_end == last.month_end)
    assert abs(last.excess[12] - (last.fwd[12] - (last.fwd[12] + other.fwd[12]) / 2)) < 1e-12
    late = next(r for r in rows if r.company_id == cid_b and r.month_end == date(2016, 12, 31))
    assert late.excess[12] == 0.0  # alone in its month's population: the benchmark is its own return


def test_c1_history_is_capped_at_history_years(monkeypatch: pytest.MonkeyPatch) -> None:
    """M8 review R2-F2: C1 ranks the month's multiple against the last `c1.history_years` (config/context.yaml) of
    month-end multiples, as the live run's price history, not against every month since the start."""
    from decimal import Decimal

    from pipeline.signals import context

    months = month_ends(date(2010, 1, 31), date(2025, 12, 31))
    closes = [(m, 200.0 if m <= date(2015, 12, 31) else 50.0 if m <= date(2024, 12, 31) else 100.0) for m in months]
    data, _ = _company_data([(q, 1_000_000_000) for q in _quarters(date(2009, 3, 31), date(2025, 9, 30))], closes)
    cfgs = live.Configs.load()
    assert panel.Shared.of(cfgs).c1_months == 12 * int(cfgs.context["c1"]["history_years"]) == 120
    seen: list[tuple[list[tuple[date, Decimal | None, Decimal | None]], context.Metric]] = []
    real = context.c1

    def spy(history: list[tuple[date, Decimal | None, Decimal | None]], min_weeks: int = 52) -> context.Metric:
        out = real(history, min_weeks)
        seen.append((list(history), out))
        return out

    monkeypatch.setattr(context, "c1", spy)
    panel.build(data, months, cfgs, (12,), panel.Options(modules=(s01_orderbook,), with_legacy=False))
    history, metric = seen[-1]
    assert history[-1][0] == date(2025, 12, 31) and len(history) == 120 and history[0][0] == date(2016, 1, 31)
    assert metric.score == Decimal(5) and metric == real([h for h in history if h[0] > date(2015, 12, 31)], 12)
    everything = real([(m, Decimal(c) * 100_000_000 / 4_000_000_000, None) for m, c in closes], 12)
    assert everything.score is not None and abs(everything.score - Decimal("40.625")) < Decimal("0.001")  # the bug


def test_the_lab_reads_the_live_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, f_lab: ModuleType) -> None:
    """M8 review R2-F4: S12's tightness lookback and C3's return window come from config/signals.yaml and
    config/context.yaml, as in the live run: with 3 quarters and 26 weeks, the Lab's cross-section uses 3 and C3
    ranks 6-month returns."""
    import shutil

    from pipeline.lab.prices import add_months

    root = tmp_path
    shutil.copytree(Path(__file__).resolve().parents[2] / "config", root / "config")
    for name, section, key, value in (("signals.yaml", "s12_cycle", "tightness_lookback_quarters", 3),
                                      ("context.yaml", "c3_runup", "lookback_weeks", 26)):  # fmt: skip
        path = root / "config" / name
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc[section][key] = value
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    cfgs = live.Configs.load(root)
    assert (panel.Shared.of(cfgs).tightness_quarters, panel.Shared.of(cfgs).c3_months) == (3, 6)
    data, _ = f_lab.make(seed=3, n=6)
    months = month_ends(date(2016, 1, 31), date(2016, 3, 31))
    seen: dict[str, object] = {}
    real = panel.cross_sections

    def spy(*args: object, **kwargs: object) -> dict[date, panel.MonthCross]:
        out = real(*args, **kwargs)  # type: ignore[arg-type]
        seen["out"] = out
        return out

    monkeypatch.setattr(panel, "cross_sections", spy)
    panel.build(data, months, cfgs, (12,), panel.Options(modules=(s01_orderbook,), with_legacy=False))
    mc = seen["out"][months[-1]]  # type: ignore[index]
    assert mc.cross.tightness_quarters == 3
    m, back = months[-1], add_months(months[-1], -6)
    six = [float(bar[m] / bar[back] - 1) for bar in ({b.month_end: b.close for b in data.bars[c.id]}
                                                       for c in data.companies if c.id)]  # fmt: skip
    assert sorted(float(r) for r in mc.returns) == pytest.approx(sorted(six))
