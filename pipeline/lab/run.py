"""Run the Signal Lab (BRIEF §4.10; lab.yml, manual). `python -m pipeline.lab.run --market us --prices FILE`.

Reads everything through pipeline.db.pit.as_of (every version of every quarter, with its filing time; the panel then
applies each month-end's cutoff), prices from the Stooq bulk file, and writes:
- lab_results rows (signals and legacy rules x horizon x period, Evidence and Gap deciles);
- docs/LAB_REPORT.md (--report), with the §7 caveats at the top;
- with --propose, config/weights.yaml with the §4.10.5 proposals (lab.yml opens the PR; it needs the
  human-approved label);
- the panel as Parquet (--panel-out; lab.yml keeps it as a release asset, §2.8).
Without the bulk file the run is BLOCKED(human) (exit 3): Manzoor downloads it once (it has a CAPTCHA) and attaches
it to the `lab-data` release (M8-05). India runs only once config/lab.yaml enables it (§4.10.7).
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
from pipeline.db.models import LabResult
from pipeline.db.pit import as_of
from pipeline.lab import evaluate, panel, proposals, report
from pipeline.lab.events import events, signal_ids
from pipeline.lab.prices import add_months, month_end, month_ends, read_bulk
from pipeline.settings import REPO_ROOT, Settings
from pipeline.signals import weekly as live

BLOCKED_EXIT = 3


def lab_config(root: Path = REPO_ROOT) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((root / "config" / "lab.yaml").read_text(encoding="utf-8"))
    return cfg


def blocked_reason(prices: Path, cfg: dict[str, Any]) -> str | None:
    if prices.is_file():
        return None
    p = cfg["prices"]
    return (f"BLOCKED(human: the Stooq bulk file {p['asset']} is not attached to the `{p['release_tag']}` release; "
            f"download it once from stooq.com (it has a CAPTCHA) and attach it, BRIEF §2.7)")  # fmt: skip


class _Row(Protocol):
    @property
    def company_id(self) -> UUID: ...


def _by_company[R: _Row](rows: Iterable[R]) -> dict[UUID, list[R]]:
    out: dict[UUID, list[R]] = defaultdict(list)
    for r in rows:
        out[r.company_id].append(r)
    return out


def load(conn: psycopg.Connection[Any], market: str, prices: Path, today: date) -> panel.LabData:
    """Companies of the market with a price file, and every row the panel reads (point in time later, per month)."""
    companies = [c for c in repo.companies(conn, market=market) if c.id is not None and c.ticker]
    bars = read_bulk(prices, [c.ticker for c in companies if c.ticker])
    companies = [c for c in companies if c.ticker in bars]
    ids = [c.id for c in companies if c.id is not None]
    snap = as_of(today)
    return panel.LabData(
        market=market,
        companies=companies,
        versions=_by_company(snap.fundamental_versions(conn, ids)),
        bars={c.id: bars[c.ticker] for c in companies if c.id is not None and c.ticker},
        ownership=_by_company(snap.ownership(conn, ids)),
        insiders=_by_company(snap.insider_events(conn, ids)),
        events=_by_company(snap.corp_events(conn, ids)),
        facts=_by_company(snap.facts(conn, ids)),
    )


def _dec(x: float | None) -> Decimal | None:
    return None if x is None else Decimal(str(round(x, 6)))


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
                "notes": None if s.lower_bound is None else f"lower_bound={s.lower_bound:.6f}",
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
        workers: int = 1) -> Outcome:  # fmt: skip
    """The report text, the proposals, the panel and the signal statistics (lab_results are written)."""
    cfg = lab_config(root)
    horizons = [int(h) for h in cfg["horizons_months"]]
    data = load(conn, market, prices, today)
    months = month_ends(date.fromisoformat(str(cfg["start"])), add_months(month_end(today), -1))
    cfgs = live.Configs.load(root)
    rows = panel.build(data, months, cfgs, horizons, panel.Options(c1_min_months=int(cfg["c1_min_months"])), workers)
    evts = events(rows, int(cfg["event_window_months"]))
    periods = evaluate.period_bounds(cfg["periods"])
    k = int(cfg["deciles"])
    ev_stats = evaluate.event_stats(evts, horizons, periods, signal_ids(rows))
    evid, gp = (evaluate.decile_stats(rows, s, horizons, periods, k) for s in ("evidence", "gap"))
    repo.insert_lab_results(conn, results([*ev_stats, *evid, *gp], market))
    weights = yaml.safe_load((root / "config" / "weights.yaml").read_text(encoding="utf-8"))
    props = proposals.propose(ev_stats, weights, int(cfg["proposal_horizon_months"]))
    info = report.RunInfo(market, months[0], months[-1], len(data.companies), len(rows), len(evts), periods,
                          f"Stooq bulk daily file {prices.name}")  # fmt: skip
    return report.render(info, ev_stats, evid, gp, props), props, rows, ev_stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market", choices=("us", "in"), default="us")
    ap.add_argument("--prices", type=Path, default=REPO_ROOT / ".cache" / "lab" / "d_us_txt.zip")
    ap.add_argument("--report", type=Path, default=REPO_ROOT / "docs" / "LAB_REPORT.md")
    ap.add_argument("--propose", action="store_true", help="write the §4.10.5 proposals into config/weights.yaml")
    ap.add_argument("--panel-out", type=Path, default=REPO_ROOT / ".cache" / "lab" / "panel.parquet")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    cfg = lab_config()
    if not cfg["markets"].get(a.market):
        print(f"lab: market {a.market} is not enabled in config/lab.yaml (India: after "
              f"{cfg['india_min_quarters']} quarters of collected data, BRIEF §4.10.7)")  # fmt: skip
        return 0
    reason = blocked_reason(a.prices, cfg)
    if reason:
        print(f"lab: {reason}")
        return BLOCKED_EXIT
    today = datetime.now(UTC).date()
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, "lab") as tracked:
        text, props, rows, stats = run(conn, a.market, a.prices, today, workers=a.workers)
        tracked.update({"company_months": len(rows), "stats": len(stats)})
    a.report.write_text(text, encoding="utf-8")
    write_panel(rows, a.panel_out, [int(h) for h in cfg["horizons_months"]])
    if a.propose:
        path = REPO_ROOT / "config" / "weights.yaml"
        path.write_text(proposals.render(path.read_text(encoding="utf-8"), props, f"lab-{today}"), encoding="utf-8")
    changed = [p for p in props if p.new != p.old]
    print(
        f"lab {a.market}: {len(rows)} company-months, {len(stats)} statistics, {len(changed)} weight changes proposed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
