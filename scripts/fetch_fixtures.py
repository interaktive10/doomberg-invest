#!/usr/bin/env python3
"""The only script allowed to use the network in tests/builds (BRIEF §9). Run once; results are committed.

  fetch_fixtures.py universe     # M0: SEC company_tickers_exchange.json + NSE EQUITY_L.csv -> data/universe/

Later milestones add their fixture sets (F-US, F-F4, F-13F, F-IN, F-PX) as further subcommands.
Needs SEC_USER_AGENT and a network policy that allows the BRIEF §0.2 domains. MOCK_EXTERNALS is ignored here.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.india.securities import NSE_EQUITY_LIST_URL  # noqa: E402
from pipeline.net.http import HttpClient  # noqa: E402
from pipeline.settings import Settings  # noqa: E402
from pipeline.us.universe import SEC_TICKERS_EXCHANGE_URL  # noqa: E402

UNIVERSE_DIR = ROOT / "data" / "universe"


def fetch_universe(client: HttpClient) -> list[str]:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url, name in (
        (SEC_TICKERS_EXCHANGE_URL, "us_tickers_exchange.json"),
        (NSE_EQUITY_LIST_URL, "nse_equity_list.csv"),
    ):
        try:
            (UNIVERSE_DIR / name).write_bytes(client.get_bytes(url))
            print(f"fetched {url} -> data/universe/{name}")
        except Exception as e:  # noqa: BLE001 — report every source, then fail
            errors.append(f"{url}: {type(e).__name__}: {e}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["universe"])
    a = ap.parse_args(argv)
    settings = dataclasses.replace(Settings.from_env(), mock_externals=False)
    client = HttpClient(settings)
    errors = fetch_universe(client) if a.what == "universe" else []
    for e in errors:
        print(f"FAILED {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
