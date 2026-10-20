"""The Signal Lab runner against the database (BRIEF §4.10): companies and every fundamentals version read through
as_of, prices from the Lab's month-price asset (pipeline/lab/prices.py), lab_results written, the report and a
proposal for every weight."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from psycopg.types.json import Jsonb

from pipeline.db import repo
from pipeline.db.models import Company
from pipeline.db.weights import INITIAL_REASON, MERGED_BY, MERGED_REASON, WeightsMismatch, record_weights_in_use
from pipeline.lab import price_history, run
from pipeline.lab.prices import write_month_csv
from pipeline.lab.proposals import Proposal
from pipeline.lab.report import CAVEATS

from ..lab.conftest import load_generator

ROOT = Path(__file__).resolve().parents[2]


def price_asset(path: Path, bars: dict[str, list[Any]]) -> Path:
    """The F-LAB month bars as the asset lab-prices.yml builds (ticker,month_end,close,high,low, gzip)."""
    write_month_csv(path, bars)
    return path


def test_lab_run_on_f_lab_companies(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    gen = load_generator()
    data, _ = gen.make(seed=5, n=20)
    repo.upsert_us_companies(conn, [Company(market="us", name=c.name, cik=f"{900000 + i:010d}", ticker=c.ticker)
                                    for i, c in enumerate(data.companies)])  # fmt: skip
    ids = {c.ticker: c.id for c in repo.companies(conn, market="us")}
    rows = [v.model_copy(update={"company_id": ids[c.ticker]}) for c in data.companies for v in data.versions[c.id]]
    repo.insert_fundamentals(conn, rows)
    prices = price_asset(tmp_path / "us_month_prices.csv.gz", {c.ticker: data.bars[c.id] for c in data.companies
                                                                if c.ticker})  # fmt: skip
    panel = tmp_path / "panel.parquet"  # written as soon as it is built (lab.yml uploads it on always())
    text, props, panel_rows, stats = run.run(conn, "us", prices, date(2026, 9, 25), panel_out=panel)
    assert len(panel_rows) == 20 * 60 and {s.horizon for s in stats} == {12, 24, 36} and panel.stat().st_size > 0
    stored = conn.execute("select count(*), count(distinct signal_id) from lab_results where market = 'us'").fetchone()
    assert stored is not None and stored[0] > 0 and stored[1] >= 12 + 6 + 2 * 10  # signals, L1-L6, two decile sets
    assert all(c in text for c in CAVEATS) and text.startswith("# Signal Lab report")
    weights = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))
    assert sorted(p.signal_id for p in props) == sorted([*weights["signals"], *weights["legacy"]])


def test_proposed_weights_version_has_the_lab_reason(conn: psycopg.Connection[Any]) -> None:
    """Review R1-F3: a Lab proposal is recorded with its §4.10.5 reasons and no approval; once main's
    config/weights.yaml carries it unedited (merged with the human-approved label) pipeline.db.weights approves it and
    keeps the Lab's reason; a later version the Lab didn't write never gets the initial "brief" reason."""
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


def test_the_lab_population_is_the_universe(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M8 review R2-F1: companies with a structural exclusion (SPAC, fund, royalty/grantor trust, foreign private
    issuer, preferred-only) give no rows, events or members of the excess average; the time-dependent rules (TTM
    revenue >= $50M, a 10-K/10-Q within 460 days) apply as of each month from the point-in-time series, never from
    today's flag or listing; the report states the population."""
    gen = load_generator()
    data, _ = gen.make(seed=7, n=12)
    special: dict[str, dict[str, Any]] = {
        "SYN000": {"sic": "6770", "in_universe": False, "excluded_reason": "SPAC (SIC 6770)"},
        "SYN001": {"sic": "6722", "in_universe": False, "excluded_reason": "not listed on NYSE/Nasdaq"},  # a fund
        "SYN002": {"sic": "3674", "in_universe": False, "excluded_reason": "foreign private issuer (20-F/40-F filer)"},
        "SYN003": {"in_universe": False, "excluded_reason": "no common stock listed (preferred series only)"},
        "SYN004": {"in_universe": False, "excluded_reason": "TTM revenue 10,000,000 < 50,000,000"},  # today only
        "SYN005": {"in_universe": False, "excluded_reason": repo.SNAPSHOT_OUT["us"]},  # delisted today
    }
    repo.upsert_us_companies(conn, [Company(market="us", name=c.name, cik=f"{900000 + i:010d}", ticker=c.ticker,
                                            **special.get(c.ticker or "", {}))
                                    for i, c in enumerate(data.companies)])  # fmt: skip
    ids = {c.ticker: c.id for c in repo.companies(conn, market="us")}
    rows = []
    for c in data.companies:
        for v in data.versions[c.id]:
            if c.ticker == "SYN006" and v.period_end <= date(2015, 12, 31):
                v = v.model_copy(update={"revenue": Decimal(10_000_000)})  # TTM 40M until Q1 2016
            if c.ticker == "SYN007" and v.period_end > date(2016, 12, 31):
                continue  # its last 10-Q: 2017-01-30
            rows.append(v.model_copy(update={"company_id": ids[c.ticker]}))
    repo.insert_fundamentals(conn, rows)
    prices = price_asset(tmp_path / "us_month_prices.csv.gz", {c.ticker: data.bars[c.id] for c in data.companies
                                                                if c.ticker})  # fmt: skip
    today = date(2026, 9, 25)
    loaded = run.load(conn, "us", prices, today)
    kept = {f"SYN{k:03d}" for k in range(4, 12)}
    assert loaded.left_out == 4 and {c.ticker for c in loaded.companies} == kept
    text, _, panel_rows, _ = run.run(conn, "us", prices, today)
    ticker = {v: k for k, v in ids.items()}
    months: dict[str, list[date]] = defaultdict(list)
    for r in panel_rows:
        months[str(ticker[r.company_id])].append(r.month_end)
    assert set(months) == kept  # the structural four: no rows, so no events and no place in any average
    assert len(months["SYN004"]) == len(months["SYN005"]) == 60  # today's flags don't reach back
    assert min(months["SYN006"]) == date(2016, 4, 30)  # TTM 10+10+10+Q1 2016 >= $50M once Q1 2016 is filed
    assert max(months["SYN007"]) == date(2018, 4, 30)  # 455 days after 2017-01-30; 2018-05-31 is 486
    last = next(r for r in panel_rows if ticker[r.company_id] == "SYN007" and r.month_end == date(2018, 4, 30))
    assert 12 in last.fwd  # still has its forward return (the 2019-04 close)
    close = {c.ticker: {b.month_end: float(b.close) for b in data.bars[c.id]} for c in data.companies}
    for m, members in ((date(2016, 1, 31), kept - {"SYN006"}), (date(2017, 6, 30), kept)):
        later = date(m.year + 1, m.month, m.day)
        bench = sum(close[t][later] / close[t][m] - 1 for t in members) / len(members)
        for r in (r for r in panel_rows if r.month_end == m):
            assert abs((r.fwd[12] - r.excess[12]) - bench) < 1e-9, (m, ticker[r.company_id])
    assert "- Population: the §1.3 universe as of each month-end: 4 companies with a structural exclusion" in text
    assert "10-K/10-Q filed in the last 460 days and TTM revenue of at least $50M" in text


def test_an_edited_proposal_is_not_approved_with_the_lab_weights(conn: psycopg.Connection[Any]) -> None:
    """M8 review R2-F3: the Lab proposes S3 1.0 -> 1.5 and S9 1.0 -> 0.0; the PR keeps S9 at 1.0 but not the version.
    The stored row (S9 = 0.0) is not approved, the run fails with a message to bump the version, and the bumped
    version is recorded with the merged weights and approved; an approved row always has approved_at."""
    w = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))
    version = "lab-2026-10-20T120000Z"
    proposed = {**w, "version": version, "signals": {**w["signals"], "S3": 1.5, "S9": 0.0}}
    changed = [
        Proposal("S3", "signals", Decimal("1.0"), Decimal("1.5"), "OOS mean +0.05, t_nw 2.4 >= 2"),
        Proposal("S9", "signals", Decimal("1.0"), Decimal("0.0"), "OOS mean -0.04, t_nw -2.2 <= -2"),
    ]
    assert run.record_proposal(conn, proposed, changed)
    merged = {**proposed, "signals": {**proposed["signals"], "S9": 1.0}}
    with pytest.raises(WeightsMismatch, match=r"signals\.S9: stored 0\.0 vs file 1\.0.*bump `version:`"):
        record_weights_in_use(conn, merged)
    sql = ("select approved_by, approved_at, reason, weights->'signals'->>'S9' from weights_versions "
           "where version = %s")  # fmt: skip
    assert conn.execute(sql, (version,)).fetchone() == (None, None, run_reason(changed), "0.0")
    assert record_weights_in_use(conn, {**merged, "version": f"{version}-edited"}) is True
    by, at, reason, s9 = conn.execute(sql, (f"{version}-edited",)).fetchone() or (None, None, None, None)
    assert (by, reason, s9) == (MERGED_BY, MERGED_REASON, "1.0") and at is not None
    assert record_weights_in_use(conn, {**w, "version": "w0-equal"}) is True  # the initial version: approved_at too
    by, at, reason, _ = conn.execute(sql, ("w0-equal",)).fetchone() or (None, None, None, None)
    assert (by, reason) == ("brief", INITIAL_REASON) and at is not None


def run_reason(changed: list[Proposal]) -> str:
    return "Signal Lab §4.10.5 proposals: " + "; ".join(
        f"{p.section}.{p.signal_id} {p.old} -> {p.new} ({p.reason})" for p in changed
    )


def test_the_weekly_run_records_the_weights_version_before_scoring(conn: psycopg.Connection[Any]) -> None:
    """M8 review R2-F3: the weekly scores run records (and approves) the version its scores name before it writes
    one, and stops, writing nothing, when the stored weights of that version differ from config/weights.yaml."""
    from datetime import timedelta

    from pipeline.signals import weekly

    w = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))
    week = date(2026, 9, 18)
    weekly.run(conn, week, http=None)
    row = conn.execute("select approved_by, approved_at from weights_versions where version = %s",
                       (w["version"],)).fetchone()  # fmt: skip
    assert row is not None and row[0] in ("brief", MERGED_BY) and row[1] is not None
    conn.execute("update weights_versions set weights = jsonb_set(weights, '{signals,S1}', '0.5') where version = %s",
                 (w["version"],))  # fmt: skip
    nxt = week + timedelta(days=7)
    with pytest.raises(WeightsMismatch, match="bump"):
        weekly.run(conn, nxt, http=None)
    assert conn.execute("select count(*) from scores where week_end = %s", (nxt,)).fetchone() == (0,)


def test_a_run_off_main_never_approves_weights(conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """M8 review R3-F1: a weekly or quarterly run dispatched on another branch (the Lab's weights PR branch) records
    the version that branch carries, unapproved; only a run on main approves it."""
    w = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))
    proposal = {**w, "version": "lab-2026-10-20T120000Z", "signals": {**w["signals"], "S3": 1.5}}
    sql = "select approved_by, approved_at from weights_versions where version = %s"
    monkeypatch.setenv("GITHUB_REF", "refs/heads/lab/weights-x")
    assert record_weights_in_use(conn, proposal) is True
    assert conn.execute(sql, (proposal["version"],)).fetchone() == (None, None)
    assert record_weights_in_use(conn, proposal) is False  # again on the branch: still not approved
    assert conn.execute(sql, (proposal["version"],)).fetchone() == (None, None)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")  # merged: the run on main approves it
    assert record_weights_in_use(conn, proposal) is False
    by, at = conn.execute(sql, (proposal["version"],)).fetchone() or (None, None)
    assert by == MERGED_BY and at is not None


def test_the_digest_reads_the_downloads_pending_tickers(conn: psycopg.Connection[Any]) -> None:
    """PR 3 review spec-F2: the digest's minutes projection reads the latest finished lab_prices run that recorded its
    progress (a run that failed before recording any, or one still running, is passed over); before any run, every
    ticker the Lab reads plus the probe; none once the download is complete."""
    repo.upsert_us_companies(conn, [Company(market="us", name=f"{t} Co", cik=f"{990000 + i:010d}", ticker=t)
                                    for i, t in enumerate(("AAA", "BBB", "CCC"))])  # fmt: skip
    assert price_history.pending_tickers(conn) == 3 + 1
    runs = "insert into runs (kind, started_at, finished_at, status, stats) values ('lab_prices', %s, %s, %s, %s)"
    conn.execute(runs, ("2026-11-01 10:07+00", "2026-11-01 11:37+00", "partial",
                        Jsonb({"status": "partial", "tickers": 5200, "pending": 4550})))  # fmt: skip
    conn.execute(runs, ("2026-11-02 10:07+00", "2026-11-02 10:08+00", "failed", Jsonb({})))
    conn.execute(runs, ("2026-11-03 10:07+00", None, "running", Jsonb({})))
    assert repo.latest_run_stats(conn, "lab_prices", "tickers") == {"status": "partial", "tickers": 5200,
                                                                     "pending": 4550}  # fmt: skip
    assert price_history.pending_tickers(conn) == 4550
    conn.execute(runs, ("2026-11-10 10:07+00", "2026-11-10 11:30+00", "ok",
                        Jsonb({"status": "complete", "tickers": 5200, "pending": 0})))  # fmt: skip
    assert price_history.pending_tickers(conn) == 0
