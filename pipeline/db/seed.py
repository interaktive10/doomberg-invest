"""Seed the database from the committed snapshots and config (BRIEF §8 M1 "seed scripts"). `python -m pipeline.db.seed`.

- companies: US from data/universe/us_tickers_exchange.json (NYSE/Nasdaq), India from nse_equity_list.csv (EQ);
  `capex_desk` from config/capex_seed.yaml (India: verified symbols only). Companies that left a snapshot are
  marked out of the universe, never deleted. M2/M3 apply the remaining universe rules (§1.3) on top.
  A snapshot below its M0-05 floor (config/universe_*.yaml) is refused before anything is written.
- weights_versions: the version in config/weights.yaml (immutable once written).
- source_health: one row per external source, so staleness is visible from the first run (§2.7).
Idempotent: re-running changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import Company, WeightsVersion
from pipeline.india.securities import NseSecurity
from pipeline.india.securities import load_snapshot as load_nse
from pipeline.settings import REPO_ROOT, Settings
from pipeline.us.universe import ListedFiler
from pipeline.us.universe import load_snapshot as load_sec

US_SNAPSHOT = REPO_ROOT / "data" / "universe" / "us_tickers_exchange.json"
IN_SNAPSHOT = REPO_ROOT / "data" / "universe" / "nse_equity_list.csv"
CAPEX_SEED = REPO_ROOT / "config" / "capex_seed.yaml"
WEIGHTS = REPO_ROOT / "config" / "weights.yaml"
SOURCES = ("sec", "sec_13f", "nse", "bse", "stooq", "gdelt", "fred", "eia")


class SnapshotTooSmall(ValueError):
    """A snapshot below the universe floor (config/universe_*.yaml min_count_check) is treated as a bad download."""


@dataclass(frozen=True)
class SeedReport:
    us: int
    india: int
    us_capex: int
    in_capex: int
    us_left_universe: int
    in_left_universe: int
    weights_inserted: bool


def us_companies(filers: list[ListedFiler], capex_tickers: set[str]) -> list[Company]:
    return [
        Company(
            market="us",
            name=f.name,
            cik=f.cik,
            ticker=f.tickers[0],
            capex_desk=any(t in capex_tickers for t in f.tickers),
        )
        for f in filers
    ]


def in_companies(securities: list[NseSecurity], capex_symbols: set[str]) -> list[Company]:
    return [
        Company(market="in", name=s.name, isin=s.isin, nse_symbol=s.symbol, capex_desk=s.symbol in capex_symbols)
        for s in securities
    ]


def capex_sets(seed: dict[str, Any]) -> tuple[set[str], set[str]]:
    us = {t for group in seed["us"].values() for t in group}
    india = {str(e["nse"]) for e in seed["india"] if e.get("verified")}
    return us, india


def seed(conn: psycopg.Connection[Any], root: Path = REPO_ROOT) -> SeedReport:
    capex_us, capex_in = capex_sets(yaml.safe_load((root / "config" / "capex_seed.yaml").read_text(encoding="utf-8")))
    us = us_companies(load_sec(root / "data" / "universe" / "us_tickers_exchange.json"), capex_us)
    india = in_companies(load_nse(root / "data" / "universe" / "nse_equity_list.csv"), capex_in)
    for market, rows in (("us", us), ("in", india)):
        cfg = yaml.safe_load((root / "config" / f"universe_{market}.yaml").read_text(encoding="utf-8"))
        if len(rows) < int(cfg["min_count_check"]):
            raise SnapshotTooSmall(
                f"{market} snapshot has {len(rows)} companies, below the floor of {cfg['min_count_check']}; "
                "refusing to seed from it (re-fetch with `make universe`)"
            )
    with conn.transaction():
        repo.upsert_us_companies(conn, us)
        repo.upsert_in_companies(conn, india)
        us_out = repo.mark_missing_out_of_universe(conn, "us", [c.cik for c in us if c.cik], repo.SNAPSHOT_OUT["us"])
        in_out = repo.mark_missing_out_of_universe(
            conn, "in", [c.nse_symbol for c in india if c.nse_symbol], repo.SNAPSHOT_OUT["in"]
        )
        w: dict[str, Any] = yaml.safe_load((root / "config" / "weights.yaml").read_text(encoding="utf-8"))
        inserted = repo.insert_weights_version(
            conn,
            WeightsVersion(
                version=str(w["version"]),
                weights={k: v for k, v in w.items() if k != "version"},
                reason="initial weights from config/weights.yaml (BRIEF §1.7: equal; legacy L* at 0)",
                approved_by="brief",
            ),
        )
        repo.ensure_sources(conn, SOURCES)
    return SeedReport(
        us=len(us),
        india=len(india),
        us_capex=sum(c.capex_desk for c in us),
        in_capex=sum(c.capex_desk for c in india),
        us_left_universe=us_out,
        in_left_universe=in_out,
        weights_inserted=inserted,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=None)
    a = ap.parse_args(argv)
    missing = [str(p.relative_to(REPO_ROOT)) for p in (US_SNAPSHOT, IN_SNAPSHOT) if not p.exists()]
    if missing:
        print(f"seed: missing snapshots {missing}; run `make universe` first", file=sys.stderr)
        return 1
    with psycopg.connect(a.database_url or Settings.from_env().database_url) as conn:
        r = seed(conn)
    print(
        f"seed: US {r.us} companies ({r.us_capex} capex desk), India {r.india} ({r.in_capex} capex desk); "
        f"left universe US {r.us_left_universe}, India {r.in_left_universe}; "
        f"weights {'inserted' if r.weights_inserted else 'already present'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
