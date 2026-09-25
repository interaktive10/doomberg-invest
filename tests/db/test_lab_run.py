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


def test_proposed_weights_version_has_the_lab_reason(conn: psycopg.Connection[Any]) -> None:
    """Review R1-F3: a Lab proposal is recorded with its §4.10.5 reasons and no approval; once config/weights.yaml
    carries it (merged with the human-approved label) the seed marks it approved and keeps the Lab's reason; a later
    version the Lab didn't write never gets the initial "brief" reason."""
    from decimal import Decimal

    from pipeline.db.seed import INITIAL_REASON, record_weights_in_use
    from pipeline.lab.proposals import Proposal

    w = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))
    proposed = {**w, "version": "lab-2026-10-01", "signals": {**w["signals"], "S1": 1.5}}
    why = "OOS mean +0.0600, t_nw 3.40 >= 2, in-sample +0.0100"
    assert run.record_proposal(conn, proposed, [Proposal("S1", "signals", Decimal("1.0"), Decimal("1.5"), why)])
    sql = "select reason, approved_by, approved_at, weights->'signals'->>'S1' from weights_versions where version = %s"
    reason, by, at, s1 = conn.execute(sql, ("lab-2026-10-01",)).fetchone() or (None, None, None, None)
    assert reason == f"Signal Lab §4.10.5 proposals: signals.S1 1.0 -> 1.5 ({why})" and by is None and at is None
    assert s1 == "1.5"
    assert record_weights_in_use(conn, proposed) is False  # merged: approve, don't rewrite
    reason, by, at, _ = conn.execute(sql, ("lab-2026-10-01",)).fetchone() or (None, None, None, None)
    assert reason.startswith("Signal Lab §4.10.5 proposals") and by == "human-approved PR" and at is not None
    assert record_weights_in_use(conn, {**w, "version": "manual-2026-11"}) is True
    reason, by, _, _ = conn.execute(sql, ("manual-2026-11",)).fetchone() or (None, None, None, None)
    assert reason != INITIAL_REASON and by == "human-approved PR"
