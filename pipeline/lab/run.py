"""Run the Signal Lab (BRIEF §4.10; lab.yml). `python -m pipeline.lab.run --market us --prices FILE --state FILE`.

Reads everything through pipeline.db.pit.as_of (every version of every quarter, with its filing time; the panel then
applies each month-end's cutoff), month-end prices from the Twelve Data download (pipeline/lab/price_history.py, kept
in the database: pipeline.db.state), and writes:
- the panel as Parquet as soon as it is built (--panel-out; lab.yml keeps it in the Actions cache, §2.8);
- lab_results rows (signals and legacy rules x horizon x period, Evidence and Gap deciles);
- docs/LAB_REPORT.md (--report), with the §7 caveats at the top;
- with --propose, config/weights.yaml with the §4.10.5 proposals and the weights PR's body with each signal's verdict
  (--pr-body; lab.yml opens the PR; it needs the human-approved label).
Until the download is complete the run is blocked (exit 3) with the download's own reason (blocked_reason; M8-05):
lab-prices.yml downloads the prices with no human step and starts the first run itself. India runs only once
config/lab.yaml enables it (§4.10.7).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import Company, LabResult, WeightsVersion
from pipeline.db.pit import as_of
from pipeline.lab import evaluate, panel, proposals, report
from pipeline.lab.events import events, signal_ids
from pipeline.lab.prices import DownloadState, add_months, month_end, month_ends, read_prices
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals import weekly as live
from pipeline.us.universe import UniverseRules, structural

BLOCKED_EXIT = 3


def lab_config(root: Path = REPO_ROOT) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((root / "config" / "lab.yaml").read_text(encoding="utf-8"))
    return cfg


def blocked_reason(prices: Path, state: DownloadState | None, cfg: dict[str, Any]) -> str | None:
    """Why the Lab can't run yet, or None: the download's own state first (price_history records this text in its
    lab_prices runs row when the probe blocks it), then the price file itself."""
    p = cfg["prices"]
    if state is not None and state.status == "blocked":
        return f"the Twelve Data download is blocked: {state.reason}"
    if state is not None and state.status != "complete":
        if not state.tickers:
            return "the Twelve Data download hasn't started (lab-prices.yml, Sunday to Thursday in Nov and Dec)"
        return (f"the Twelve Data download has {state.settled():,} of {len(state.tickers):,} tickers; lab-prices.yml "
                "resumes it Sunday to Thursday and starts the Lab once every ticker is done")  # fmt: skip
    if not prices.is_file():
        return (f"no Lab prices yet: lab-prices.yml downloads them from Twelve Data into the database "
                f"({p['stored_as']['asset']}) with no human step")  # fmt: skip
    return None


class _Row(Protocol):
    @property
    def company_id(self) -> UUID: ...


def _by_company[R: _Row](rows: Iterable[R]) -> dict[UUID, list[R]]:
    out: dict[UUID, list[R]] = defaultdict(list)
    for r in rows:
        out[r.company_id].append(r)
    return out


def population(market: str, root: Path = REPO_ROOT) -> panel.Population | None:
    """The §1.3 rules the panel applies month by month (M8 review R2-F1). US: a 10-K/10-Q within the universe's
    filing lookback and TTM revenue at its floor, as known at each month-end. India: none (NSE's EQ list and the
    ASM/GSM lists have no history; docs/DECISIONS.log)."""
    if market != "us":
        return None
    rules = UniverseRules.load(root)
    return panel.Population(filing_days=rules.filing_lookback_days, min_ttm_revenue=rules.min_ttm_revenue_usd)


def describe(market: str, pop: panel.Population | None, left_out: int) -> str:
    if pop is None:
        return (f"every {market.upper()} company with a price file (the universe's surveillance lists have no "
                "history, so they aren't applied)")  # fmt: skip
    floor = "" if pop.min_ttm_revenue is None else f" and TTM revenue of at least ${pop.min_ttm_revenue / 10**6:,.0f}M"
    return (f"the §1.3 universe as of each month-end: {left_out} companies with a structural exclusion (SPAC, fund, "
            f"royalty/grantor trust, foreign private issuer, no listed common stock or no public common equity) are "
            f"left out, and each month keeps the companies with a 10-K/10-Q filed in the last {pop.filing_days} "
            f"days{floor}, as known then "
            "(never today's universe flag). Listing status and market cap aren't applied (today's listing would add "
            "survivorship bias; market cap is a candidate-stage rule)")  # fmt: skip


def lab_companies(conn: psycopg.Connection[Any], market: str, root: Path = REPO_ROOT) -> tuple[list[Company], int]:
    """The companies of the market with a ticker, less the structural exclusions (they give no rows, events or
    members of the excess average), and how many were left out. price_history downloads prices for exactly these."""
    companies = [c for c in repo.companies(conn, market=market) if c.id is not None and c.ticker]
    rules = UniverseRules.load(root) if market == "us" else None
    kept = [c for c in companies if rules is None or structural(c.sic, c.excluded_reason, rules) is None]
    return kept, len(companies) - len(kept)


def load(conn: psycopg.Connection[Any], market: str, prices: Path, today: date, root: Path = REPO_ROOT
         ) -> panel.LabData:  # fmt: skip
    """The Lab's companies (lab_companies) with prices, and every row the panel reads (point in time later, per
    month)."""
    kept, left_out = lab_companies(conn, market, root)
    bars = read_prices(prices, [c.ticker for c in kept if c.ticker])
    companies = [c for c in kept if c.ticker in bars]
    ids = [c.id for c in companies if c.id is not None]
    snap = as_of(today)
    return panel.LabData(
        market=market,
        companies=companies,
        versions=_by_company(snap.fundamental_versions(conn, ids)),
        bars={c.id: bars[c.ticker] for c in companies if c.id is not None and c.ticker},
        ownership=_by_company(snap.ownership_versions(conn, ids)),  # every version: replayed per month
        insiders=_by_company(snap.insider_events(conn, ids)),
        events=_by_company(snap.corp_events(conn, ids)),
        facts=_by_company(snap.facts(conn, ids)),
        left_out=left_out,
    )


def _dec(x: float | None) -> Decimal | None:
    return None if x is None else Decimal(str(round(x, 6)))


def _notes(s: evaluate.Stat) -> str | None:
    parts = [] if s.lower_bound is None else [f"lower_bound={s.lower_bound:.6f}"]
    if s.t_nw_unfloored is not None:
        parts.append(f"t_nw_unfloored={s.t_nw_unfloored:.4f}")
    return "; ".join(parts) or None


def results(stats: Sequence[evaluate.Stat], market: str) -> list[LabResult]:
    return [
        LabResult.model_validate(
            {
                "signal_id": s.signal_id,
                "market": market,
                "horizon_m": s.horizon,
                "period": s.period,
                "n": s.n,
                "excess_mean": _dec(s.mean),
                "excess_median": _dec(s.median),
                "hit_rate": _dec(s.hit_rate),
                "p10": _dec(s.p10),
                "t_nw": _dec(s.t_nw),
                "notes": _notes(s),
            }
        )  # fmt: skip
        for s in stats
    ]


def write_panel(rows: Sequence[panel.PanelRow], path: Path, horizons: Sequence[int]) -> None:
    import polars as pl

    ids = sorted({k for r in rows for k in r.fired})
    table = {
        "company_id": [str(r.company_id) for r in rows],
        "month_end": [r.month_end for r in rows],
        "close": [r.close for r in rows],
        "evidence": [r.evidence for r in rows],
        "gap": [r.gap for r in rows],
        **{f"fired_{s}": [r.fired.get(s, False) for r in rows] for s in ids},
        **{f"excess_{h}m": [r.excess.get(h) for r in rows] for h in horizons},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(table).write_parquet(path)


Outcome = tuple[str, list[proposals.Proposal], list[panel.PanelRow], list[evaluate.Stat]]


def run(conn: psycopg.Connection[Any], market: str, prices: Path, today: date, root: Path = REPO_ROOT,
        workers: int = 1, panel_out: Path | None = None) -> Outcome:  # fmt: skip
    """The report text, the proposals, the panel and the signal statistics (lab_results are written). The panel is
    written to `panel_out` as soon as it is built, before the statistics, so a run that fails later still keeps it."""
    cfg = lab_config(root)
    horizons = [int(h) for h in cfg["horizons_months"]]
    data = load(conn, market, prices, today, root)
    months = month_ends(date.fromisoformat(str(cfg["start"])), add_months(month_end(today), -1))
    cfgs = live.Configs.load(root)
    pop = population(market, root)
    opts = panel.Options(c1_min_months=int(cfg["c1_min_months"]), population=pop)
    rows = panel.build(data, months, cfgs, horizons, opts, workers)
    if panel_out is not None:
        write_panel(rows, panel_out, horizons)
    evts = events(rows, int(cfg["event_window_months"]))
    periods = evaluate.period_bounds(cfg["periods"])
    k = int(cfg["deciles"])
    ev_stats = evaluate.event_stats(evts, horizons, periods, signal_ids(rows))
    evid, gp = (evaluate.decile_stats(rows, s, horizons, periods, k) for s in ("evidence", "gap"))
    repo.insert_lab_results(conn, results([*ev_stats, *evid, *gp], market))
    weights = yaml.safe_load((root / "config" / "weights.yaml").read_text(encoding="utf-8"))
    props = proposals.propose(ev_stats, weights, int(cfg["proposal_horizon_months"]), cfg.get("not_testable") or ())
    info = report.RunInfo(market, months[0], months[-1], len({r.company_id for r in rows}), len(rows), len(evts),
                          periods, f"Twelve Data month-end closes ({prices.name}, kept in the database)",
                          describe(market, pop, data.left_out))  # fmt: skip
    return report.render(info, ev_stats, evid, gp, props), props, rows, ev_stats


def version_for(now: datetime) -> str:
    """One version per Lab run (two runs on a day don't share one; M8 review R2-F3)."""
    return f"lab-{now:%Y-%m-%dT%H%M%SZ}"


def record_proposal(
    conn: psycopg.Connection[Any], proposed: dict[str, Any], changed: Sequence[proposals.Proposal]
) -> bool:
    """weights_versions gets the proposed version with the §4.10.5 reason of every changed weight, not yet approved;
    pipeline.db.weights approves it once main's config/weights.yaml carries it with the same weights (merged with the
    human-approved label; weights.yml and the weekly scores run). False if the version already exists."""
    reason = "Signal Lab §4.10.5 proposals: " + "; ".join(
        f"{p.section}.{p.signal_id} {p.old} -> {p.new} ({p.reason})" for p in changed
    )
    version = WeightsVersion(
        version=str(proposed["version"]),
        weights={k: v for k, v in proposed.items() if k != "version"},
        reason=reason[:4000],
        approved_by=None,
    )
    return repo.insert_weights_version(conn, version)


def main(argv: list[str] | None = None) -> int:
    cfg = lab_config()
    lab = REPO_ROOT / ".cache" / "lab"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market", choices=("us", "in"), default="us")
    ap.add_argument("--prices", type=Path, default=lab / cfg["prices"]["asset"])
    ap.add_argument("--state", type=Path, default=lab / cfg["prices"]["state"], help="the download's state")
    ap.add_argument("--report", type=Path, default=REPO_ROOT / "docs" / "LAB_REPORT.md")
    ap.add_argument("--propose", action="store_true", help="write the §4.10.5 proposals into config/weights.yaml")
    ap.add_argument("--panel-out", type=Path, default=REPO_ROOT / ".cache" / "lab" / "panel.parquet")
    ap.add_argument("--pr-body", type=Path, help="with --propose: write the weights PR's body here")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    if not cfg["markets"].get(a.market):
        print(f"lab: market {a.market} is not enabled in config/lab.yaml (India: after "
              f"{cfg['india_min_quarters']} quarters of collected data, BRIEF §4.10.7)")  # fmt: skip
        return 0
    reason = blocked_reason(a.prices, DownloadState.load(a.state), cfg)
    if reason:
        print(f"lab: BLOCKED: {reason}")
        return BLOCKED_EXIT
    now = datetime.now(UTC)
    settings = Settings.from_env()
    path = REPO_ROOT / "config" / "weights.yaml"
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "lab") as tracked:
        text, props, rows, stats = run(conn, a.market, a.prices, now.date(), workers=a.workers, panel_out=a.panel_out)
        changed = [p for p in props if p.new != p.old]
        after = proposals.render(path.read_text(encoding="utf-8"), props, version_for(now))
        if a.propose and changed and not record_proposal(conn, yaml.safe_load(after), changed):
            raise RuntimeError(f"weights version {version_for(now)} already exists; re-run the Lab")
        tracked.update({"company_months": len(rows), "stats": len(stats), "weight_changes": len(changed)})
    a.report.write_text(text, encoding="utf-8")
    if a.propose and changed:
        path.write_text(after, encoding="utf-8")
        if a.pr_body is not None:
            rules = yaml.safe_load(after)["lab_rules"]
            a.pr_body.write_text(proposals.pr_body(props, rules, int(cfg["proposal_horizon_months"])), encoding="utf-8")
    print(
        f"lab {a.market}: {len(rows)} company-months, {len(stats)} statistics, {len(changed)} weight changes proposed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
