"""M4 against the database: signals as of W ignore later filings (M4-02); the weekly scoring run on F-US with Stooq
and GDELT served by mocks (prices, splits flagged, context, Gap, buckets, shortlist, metrics); history pruning
(docs/SPEC_ISSUES.md 9); the screener API (screen() over screener_v)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from pipeline.db import repo
from pipeline.db.models import Company, CorpEvent, InsiderEvent, Score, SignalValue
from pipeline.db.pit import cutoff_for
from pipeline.net.gdelt import build_query, timeline_url
from pipeline.net.http import HttpClient
from pipeline.net.stooq import csv_url
from pipeline.screener import MetricFilter, ScreenSpec, run_screen
from pipeline.settings import Settings
from pipeline.signals import weekly
from pipeline.us.fundamentals import load_xbrl_map, quarterize_company, to_models
from pipeline.us.submissions import parse_submissions

FIX = Path(__file__).resolve().parents[2] / "fixtures"
TODAY = date(2026, 9, 20)
COMPANIES = {"0000018230": ("CATERPILLAR INC", "CAT"), "0000320193": ("Apple Inc.", "AAPL"),
             "0001050915": ("QUANTA SERVICES, INC.", "PWR"), "0000898293": ("JABIL INC", "JBL")}  # fmt: skip


def add(conn: psycopg.Connection[Any], cik: str) -> uuid.UUID:
    name, ticker = COMPANIES[cik]
    repo.upsert_us_companies(conn, [Company(market="us", name=name, cik=cik, ticker=ticker)])
    return repo.company_ids_by(conn, "cik")[cik]


def fundamentals(conn: psycopg.Connection[Any], cik: str, cid: uuid.UUID, known_by: datetime | None = None) -> int:
    cf = json.loads((FIX / "us" / "companyfacts" / f"CIK{cik}.json").read_text(encoding="utf-8"))
    subs = parse_submissions(json.loads((FIX / "us" / "submissions" / f"CIK{cik}.json").read_text(encoding="utf-8")))
    rows = quarterize_company(cf, subs, load_xbrl_map(), TODAY).rows
    models = to_models(cid, [r for r in rows if known_by is None or r.filed_at < known_by])
    repo.insert_fundamentals(conn, models)
    return len(models)


def snapshot(conn: psycopg.Connection[Any], week: date) -> tuple[list[Any], list[Any], list[Any]]:
    sig = conn.execute(
        "select c.cik, v.signal_id, v.fired, v.strength, v.inputs from signal_values v "
        "join companies c on c.id = v.company_id where v.week_end = %s order by 1, 2",
        (week,),
    ).fetchall()
    flags = conn.execute(
        "select c.cik, r.flag_id, r.hard, r.inputs from redflag_values r join companies c on c.id = r.company_id "
        "where r.week_end = %s order by 1, 2",
        (week,),
    ).fetchall()
    scores = conn.execute(
        "select c.cik, s.evidence, s.families, s.bucket from scores s join companies c on c.id = s.company_id "
        "where s.week_end = %s order by 1",
        (week,),
    ).fetchall()
    return sig, flags, scores


# ---------------------------------------------------------------- M4-02


def test_signals_as_of_w_are_identical_whether_or_not_later_filings_exist(conn: psycopg.Connection[Any]) -> None:
    week = date(2022, 6, 24)
    cutoff = cutoff_for(week)
    runs = {}
    for mode in ("with later filings", "only what was known at W"):
        with conn.transaction(force_rollback=True):
            ids = {cik: add(conn, cik) for cik in ("0000018230", "0000320193", "0001050915")}
            later = mode == "with later filings"
            n = {cik: fundamentals(conn, cik, cid, None if later else cutoff) for cik, cid in ids.items()}
            if later:
                assert all(v > 20 for v in n.values())
                cat = ids["0000018230"]
                repo.insert_insider_events(conn, [InsiderEvent(
                    company_id=cat, event_date=week - timedelta(days=5), filed_at=datetime(2022, 7, 15, tzinfo=UTC),
                    person="LATE FILER", kind="open_market_buy", shares=Decimal(10000), value=Decimal(2_000_000),
                    currency="USD", source_url="https://www.sec.gov/late")])  # fmt: skip
                repo.insert_corp_events(conn, [CorpEvent(
                    company_id=cat, event_date=week - timedelta(days=10), filed_at=datetime(2022, 8, 1, tzinfo=UTC),
                    kind="auditor_change", source_url="https://www.sec.gov/late-8k")])  # fmt: skip
            weekly.run(conn, week, http=None)
            runs[mode] = snapshot(conn, week)
    sig, flags, scores = runs["with later filings"]
    assert len(sig) == 3 * 12 and len(scores) == 3
    assert runs["with later filings"] == runs["only what was known at W"]


# ---------------------------------------------------------------- the weekly scoring run


def mock_http(tmp_path: Path) -> HttpClient:
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    for sym in ("pwr.us", "jbl.us", "cat.us", "xlk.us"):
        http.register_mock(csv_url(sym), (FIX / "px" / f"{sym}_w.csv").read_bytes())
    http.register_mock(csv_url("^spx"), (FIX / "px" / "_spx_w.csv").read_bytes())
    http.register_mock(timeline_url(build_query("QUANTA SERVICES, INC.", "PWR", "us")),
                       (FIX / "gdelt" / "timeline_pwr.json").read_bytes())  # fmt: skip
    http.register_mock(timeline_url(build_query("JABIL INC", "JBL", "us")), (FIX / "gdelt" / "empty.json").read_bytes())
    http.register_mock(timeline_url(build_query("CATERPILLAR INC", "CAT", "us")),
                       (FIX / "gdelt" / "empty.json").read_bytes())  # fmt: skip
    return http


def thesis(conn: psycopg.Connection[Any], cid: uuid.UUID) -> None:
    """A live thesis puts a company at the candidate stage whatever its Evidence (BRIEF §4.4)."""
    conn.execute(
        "insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, created_week) "
        "values (%s, 'research', '', '{}', '{}', 'manual', '{}', %s)",
        (cid, date(2026, 9, 18)),
    )


def test_weekly_scoring_run_on_f_us(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    week = date(2026, 9, 18)
    ids = {cik: add(conn, cik) for cik in COMPANIES}
    for cik, cid in ids.items():
        fundamentals(conn, cik, cid)
    pwr, jbl = ids["0001050915"], ids["0000898293"]
    thesis(conn, pwr)
    thesis(conn, jbl)
    stats = weekly.run(conn, week, http=mock_http(tmp_path), imports=tmp_path / "imports")

    # the candidate stage: PWR and JBL by their theses, CAT by its Evidence (50: S1 fired)
    assert stats.companies == 4 and stats.stage == 3 and stats.stooq_ok == 3 and stats.gdelt_queried == 3
    n_signals = conn.execute("select count(*) from signal_values where week_end = %s", (week,)).fetchone()
    assert n_signals == (4 * 12,)
    prices = conn.execute("select count(*), min(week_end), max(week_end) from prices_w where company_id = %s", (pwr,))
    count, first, last = prices.fetchone() or (0, None, None)
    assert count == 260 and last == week and first is not None
    # JBL's synthetic history halves in week 150 while its share count doesn't move: flagged, never adjusted
    assert any(j.startswith("JBL ") for j in stats.unconfirmed_jumps)
    unadjusted = conn.execute("select count(*) from prices_w where company_id = %s and adj_close <> close", (jbl,))
    assert unadjusted.fetchone() == (0,)
    # context: C1-C4 rows for the staged companies; GDELT counts (180 for PWR, 0 for JBL and CAT) ranked within the
    # set
    ctx = dict(conn.execute("select metric_id, inputs from context_values where company_id = %s and week_end = %s",
                            (pwr, week)).fetchall())  # fmt: skip
    assert set(ctx) == {"C1", "C2", "C3", "C4"}
    assert ctx["C4"]["articles_90d"] == 180 and ctx["C4"]["population"] == 3
    assert ctx["C4"]["score"] == round(100 - 100 * (2 + 0.5) / 3, 6)  # above two zeros -> pct 83.3, score 16.7
    assert ctx["C3"]["population"] >= 3  # PWR, JBL and the benchmarks (^spx, XLK)
    score = conn.execute("select gap, bucket, weights_version from scores where company_id = %s and week_end = %s",
                         (pwr, week)).fetchone()  # fmt: skip
    assert score is not None and score[0] is not None and score[2] == "w0-equal"
    metrics = conn.execute("select metrics from company_metrics where company_id = %s", (pwr,)).fetchone()
    assert metrics is not None and metrics[0]["market_cap"] > 0 and "revenue_ttm" in metrics[0]
    assert {r["company_id"] for r in run_screen(conn, ScreenSpec(market="us"))} == set(ids.values())
    # a re-run of the same week replaces its rows
    weekly.run(conn, week, http=mock_http(tmp_path), imports=tmp_path / "imports")
    assert conn.execute("select count(*) from scores where week_end = %s", (week,)).fetchone() == (4,)
    assert conn.execute("select count(*) from context_values where week_end = %s", (week,)).fetchone() == (12,)
    # the next week reuses the GDELT counts (under 28 days old) instead of asking again
    nxt = weekly.run(conn, week + timedelta(days=7), http=mock_http(tmp_path), imports=tmp_path / "imports")
    assert (nxt.gdelt_queried, nxt.gdelt_reused) == (0, 3)


def test_manual_price_import_when_stooq_fails(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    week = date(2026, 9, 18)
    cid = add(conn, "0001050915")
    fundamentals(conn, "0001050915", cid)
    thesis(conn, cid)
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    http.register_mock(csv_url("pwr.us"), (FIX / "px" / "limit.txt").read_bytes())  # "Exceeded the daily hits limit"
    imports = tmp_path / "imports"
    imports.mkdir()
    (imports / "PWR.csv").write_bytes((FIX / "px" / "pwr.us_w.csv").read_bytes())
    stats = weekly.run(conn, week, http=http, imports=imports, gdelt_limit=0)
    assert (stats.stooq_ok, stats.stooq_imported) == (0, 1)
    assert conn.execute("select count(*) from prices_w where company_id = %s", (cid,)).fetchone() == (260,)


# ---------------------------------------------------------------- pruning (SPEC_ISSUES 9)


def test_older_weeks_keep_fired_signals_and_the_first_quiet_week(conn: psycopg.Connection[Any]) -> None:
    cid = add(conn, "0000018230")
    weeks = [date(2026, 8, 21) + timedelta(weeks=i) for i in range(5)]  # fired: no, yes, yes, no, no
    rows = [SignalValue(company_id=cid, week_end=w, signal_id="S1", fired=f, strength=Decimal(f), inputs={"x": 1})
            for w, f in zip(weeks, (False, True, True, False, False), strict=True)]  # fmt: skip
    repo.upsert_signal_values(conn, rows)
    repo.upsert_scores(conn, [Score(company_id=cid, week_end=w, evidence=Decimal(0), families=[], bucket="none",
                                    weights_version="w0-equal") for w in weeks])  # fmt: skip
    pruned = repo.prune_scoring_history(conn, weeks[-1], keep_from=weeks[0], none_from=weeks[-2])
    kept = conn.execute("select week_end, fired, inputs from signal_values where company_id = %s order by 1", (cid,))
    assert kept.fetchall() == [(weeks[1], True, {}), (weeks[2], True, {}), (weeks[3], False, {}),
                               (weeks[4], False, {"x": 1})]  # fmt: skip
    assert pruned["signal_values"] == 1  # week 0: never fired before it
    left = conn.execute("select week_end from scores where company_id = %s order by 1", (cid,)).fetchall()
    assert left == [(weeks[3],), (weeks[4],)]


# ---------------------------------------------------------------- the screener API


def test_screen_filters(conn: psycopg.Connection[Any]) -> None:
    week = date(2026, 9, 18)
    a, b, c = (add(conn, cik) for cik in ("0000018230", "0000320193", "0001050915"))
    repo.upsert_scores(conn, [
        Score(company_id=a, week_end=week, evidence=Decimal(75), gap=Decimal(60), families=["behavior", "fundamentals"],
              bucket="candidate", weights_version="w0-equal"),
        Score(company_id=b, week_end=week, evidence=Decimal(45), gap=Decimal(40), families=["fundamentals"],
              bucket="none", weights_version="w0-equal"),
        Score(company_id=c, week_end=week, evidence=Decimal(65), gap=Decimal(30), families=["fundamentals", "text"],
              bucket="priced_in", weights_version="w0-equal"),
    ])  # fmt: skip
    repo.upsert_signal_values(conn, [
        SignalValue(company_id=a, week_end=week, signal_id="S1", fired=True, strength=Decimal(1), inputs={}),
        SignalValue(company_id=c, week_end=week, signal_id="S9", fired=True, strength=Decimal("0.4"), inputs={}),
    ])  # fmt: skip
    conn.execute(
        "insert into redflag_values (company_id, week_end, flag_id, hard, inputs) values (%s, %s, 'R3', true, %s)",
        (c, week, Jsonb({"status": "fired"})),
    )
    repo.upsert_company_metrics(conn, week, {a: {"roic": 0.14}, b: {"roic": 0.02}, c: {"roic": 0.2}})

    def ids(**spec: Any) -> list[uuid.UUID]:
        return [r["company_id"] for r in run_screen(conn, ScreenSpec(**spec))]

    assert ids() == [a, c, b]  # Evidence first
    assert ids(min_evidence=Decimal(60)) == [a, c]
    assert ids(buckets=["candidate", "none"]) == [a, b]
    assert ids(signals_any=["S9"]) == [c]
    assert ids(families_all=["fundamentals", "behavior"]) == [a]
    assert ids(exclude_hard_flags=True) == [a, b]
    assert ids(metrics=[MetricFilter(metric="roic", op=">=", value=Decimal("0.1"))]) == [a, c]
    assert ids(metrics=[MetricFilter(metric="market_cap", op=">", value=Decimal(0))]) == []  # not in the metrics
    row = run_screen(conn, ScreenSpec(signals_any=["S1"]))[0]
    assert row["fired_signals"] == ["S1"] and row["red_flags"] == [] and row["hard_flag"] is False
