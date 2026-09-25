"""The Signal Lab runner against the database (BRIEF §4.10): companies and every fundamentals version read through
as_of, prices from a Stooq-format bulk zip, lab_results written, the report and a proposal for every weight."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import Company
from pipeline.lab import run
from pipeline.lab.report import CAVEATS

from ..lab.conftest import load_generator

ROOT = Path(__file__).resolve().parents[2]


def bulk_zip(path: Path, bars: dict[str, list[Any]]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for ticker, rows in bars.items():
            lines = ["<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>"]
            lines += [f"{ticker}.US,D,{b.month_end:%Y%m%d},000000,{b.close},{b.close},{b.close},{b.close},1000,0"
                      for b in rows]  # fmt: skip
            z.writestr(f"data/daily/us/nasdaq stocks/1/{ticker.lower()}.us.txt", "\n".join(lines) + "\n")
    return path


def test_lab_run_on_f_lab_companies(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    gen = load_generator()
    data, _ = gen.make(seed=5, n=20)
    repo.upsert_us_companies(conn, [Company(market="us", name=c.name, cik=f"{900000 + i:010d}", ticker=c.ticker)
                                    for i, c in enumerate(data.companies)])  # fmt: skip
    ids = {c.ticker: c.id for c in repo.companies(conn, market="us")}
    rows = [v.model_copy(update={"company_id": ids[c.ticker]}) for c in data.companies for v in data.versions[c.id]]
    repo.insert_fundamentals(conn, rows)
    prices = bulk_zip(tmp_path / "d_us_txt.zip", {c.ticker: data.bars[c.id] for c in data.companies if c.ticker})
    text, props, panel_rows, stats = run.run(conn, "us", prices, date(2026, 9, 25))
    assert len(panel_rows) == 20 * 60 and {s.horizon for s in stats} == {12, 24, 36}
    stored = conn.execute("select count(*), count(distinct signal_id) from lab_results where market = 'us'").fetchone()
    assert stored is not None and stored[0] > 0 and stored[1] >= 12 + 6 + 2 * 10  # signals, L1-L6, two decile sets
    assert all(c in text for c in CAVEATS) and text.startswith("# Signal Lab report")
    weights = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))
    assert sorted(p.signal_id for p in props) == sorted([*weights["signals"], *weights["legacy"]])
