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
from pipeline.db.models import Company, CorpEvent, InsiderEvent, OwnershipRow, PriceW, Score, SignalValue
from pipeline.db.pit import cutoff_for
from pipeline.net.gdelt import build_query, timeline_url
from pipeline.net.http import HttpClient
from pipeline.net.stooq import csv_url, parse_csv
from pipeline.screener import MetricFilter, ScreenSpec, run_screen
from pipeline.settings import Settings
from pipeline.signals import weekly
from pipeline.signals.context import Metric
from pipeline.signals.reverse_dcf import C2
from pipeline.signals.scores import Evidence
from pipeline.signals.series import Series
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


def test_ownership_revision_filed_after_w_changes_nothing_as_of_w(conn: psycopg.Connection[Any]) -> None:
    """M4 review R1-F2: re-filing June's shareholding pattern after W (same numbers) used to replace the row, so the
    as-of-W run lost it: S8 went missing, R5 read March's pledge and the bucket moved. Versions keep it."""
    week = date(2026, 9, 18)
    repo.upsert_in_companies(conn, [Company(market="in", name="Pledged Ltd", isin="INE000X01011", nse_symbol="PLDG")])
    cid = repo.company_ids_by(conn, "nse_symbol")["PLDG"]

    def pattern(q: date, fii_dii: str, pledged: str, filed: datetime) -> OwnershipRow:
        return OwnershipRow(company_id=cid, quarter_end=q, filed_at=filed, fii_pct=Decimal(fii_dii),
                            dii_pct=Decimal(0), promoter_pct=Decimal(50), promoter_pledged_pct=Decimal(pledged),
                            source="nse_shp")  # fmt: skip

    repo.upsert_ownership(conn, [
        pattern(date(2025, 12, 31), "10", "10", datetime(2026, 1, 20, tzinfo=UTC)),
        pattern(date(2026, 3, 31), "11", "10", datetime(2026, 4, 20, tzinfo=UTC)),
        pattern(date(2026, 6, 30), "12.5", "25", datetime(2026, 7, 20, tzinfo=UTC)),
    ])  # fmt: skip
    weekly.run(conn, week, http=None)
    before = snapshot_in(conn, week)
    sig, flags, scores = before
    assert ("S8", True) in [(r[0], r[1]) for r in sig]  # FII+DII 10 -> 12.5: +2.5 pp
    assert [r[1] for r in flags if r[0] == "R5"] == [True] and scores[0][2] == "excluded"  # pledge 25% of promoter
    repo.upsert_ownership(conn, [pattern(date(2026, 6, 30), "12.5", "25", datetime(2026, 10, 1, tzinfo=UTC))])
    weekly.run(conn, week, http=None)
    assert snapshot_in(conn, week) == before


def snapshot_in(conn: psycopg.Connection[Any], week: date) -> tuple[list[Any], list[Any], list[Any]]:
    sig = conn.execute("select signal_id, fired, strength, inputs from signal_values where week_end = %s order by 1",
                       (week,)).fetchall()  # fmt: skip
    flags = conn.execute("select flag_id, hard, inputs from redflag_values where week_end = %s order by 1",
                         (week,)).fetchall()  # fmt: skip
    scores = conn.execute("select evidence, families, bucket from scores where week_end = %s", (week,)).fetchall()
    return sig, flags, scores


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


def test_s7_amendment_filed_later_moving_the_trade_back_is_read(conn: psycopg.Connection[Any]) -> None:
    """M4 review R2-F4: the weekly run loaded insider events by trade date (the last 100 days), so a Form 4/A filed
    this month that moves a trade to May was never loaded and the original still counted. Loading by filing date
    keeps the amendment next to its original: S7 goes quiet."""
    week = date(2026, 9, 18)
    cid = add(conn, "0000018230")

    def buy(person: str, value: int, day: date, filed: datetime, url: str, amends: date | None = None) -> InsiderEvent:
        return InsiderEvent(company_id=cid, event_date=day, filed_at=filed, person=person, kind="open_market_buy",
                            shares=Decimal(1000), value=Decimal(value), currency="USD", source_url=url,
                            amends=amends)  # fmt: skip

    repo.insert_insider_events(conn, [
        buy("ALICE", 200_000, date(2026, 9, 1), datetime(2026, 9, 2, 20, tzinfo=UTC), "https://www.sec.gov/a"),
        buy("BOB", 100_000, date(2026, 9, 3), datetime(2026, 9, 4, 20, tzinfo=UTC), "https://www.sec.gov/b"),
    ])  # fmt: skip

    def s7() -> tuple[bool, Any]:
        row = conn.execute("select fired, inputs from signal_values where company_id = %s and week_end = %s "
                           "and signal_id = 'S7'", (cid, week)).fetchone()  # fmt: skip
        assert row is not None
        return row[0], row[1]

    weekly.run(conn, week, http=None)
    assert s7()[0] is True
    repo.insert_insider_events(conn, [buy("ALICE", 200_000, date(2026, 5, 1), datetime(2026, 9, 10, 20, tzinfo=UTC),
                                          "https://www.sec.gov/a-amended", amends=date(2026, 9, 2))])  # fmt: skip
    weekly.run(conn, week, http=None)
    fired, inputs = s7()
    assert fired is False and inputs["insiders"] == 1


def test_stooq_stale_when_every_download_fails_cleared_when_it_answers(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    """M4 review R1-F3: a run where every Stooq download fails leaves source_health stale (the web's banner); a run
    where Stooq answers clears it; a re-run of the week doesn't download what it already has."""
    week = date(2026, 9, 18)
    cid = add(conn, "0001050915")
    fundamentals(conn, "0001050915", cid)
    thesis(conn, cid)
    down = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path / "a"))
    down.register_mock(csv_url("pwr.us"), (FIX / "px" / "limit.txt").read_bytes())  # benchmarks: no answer at all
    stats = weekly.run(conn, week, http=down, imports=tmp_path / "imports", gdelt_limit=0)
    assert (stats.stooq_ok, stats.stooq_failed, stats.bench_ok, stats.bench_failed) == (0, 1, 0, 12)

    def stooq() -> Any:
        return {h.source: h for h in repo.source_health(conn)}["stooq"]

    assert stooq().stale and (stooq().last_error or "").startswith("stale: 13 downloads failed")
    up = weekly.run(conn, week, http=mock_http(tmp_path / "b"), imports=tmp_path / "imports", gdelt_limit=0)
    assert up.stooq_ok == 1 and not stooq().stale and stooq().last_error is None and stooq().last_success
    http = mock_http(tmp_path / "c")
    again = weekly.run(conn, week, http=http, imports=tmp_path / "imports", gdelt_limit=0)
    assert (again.stooq_ok, again.stooq_skipped, again.bench_skipped) == (0, 1, 2)  # PWR, ^spx and XLK are priced
    assert csv_url("pwr.us") not in http.calls and csv_url("^spx") not in http.calls
    assert not stooq().stale  # the other ten benchmarks failed again, but this week's prices are in


def test_adjusted_source_split_moves_market_cap_to_the_new_basis(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M4 review R1-F6: stored closes 10x the fresh download's (Stooq re-adjusted its history for a 10:1 split).
    Until a 10-Q reports the new count, market cap is price x the pre-split count x 10."""
    week = date(2026, 9, 18)
    cid = add(conn, "0001050915")
    fundamentals(conn, "0001050915", cid)
    thesis(conn, cid)

    def market_cap() -> Decimal:
        row = conn.execute("select metrics->>'market_cap' from company_metrics where company_id = %s", (cid,))
        return Decimal(str((row.fetchone() or [None])[0]))

    with conn.transaction(force_rollback=True):
        weekly.run(conn, week, http=mock_http(tmp_path / "a"), imports=tmp_path / "imports", gdelt_limit=0)
        before = market_cap()
    old = [PriceW(company_id=cid, week_end=b.week_end, close=b.close * 10, adj_close=b.close * 10, source="stooq")
           for b in parse_csv((FIX / "px" / "pwr.us_w.csv").read_bytes()) if b.week_end < week]  # fmt: skip
    repo.upsert_prices(conn, old)
    stats = weekly.run(conn, week, http=mock_http(tmp_path / "b"), imports=tmp_path / "imports", gdelt_limit=0)
    assert stats.source_splits == [f"PWR {week} x10"]
    assert abs(market_cap() / before - 10) < Decimal("1e-9")
    stored = conn.execute("select split_ratio from prices_w where company_id = %s and week_end = %s", (cid, week))
    assert stored.fetchone() == (Decimal(10),)
    nxt = weekly.run(
        conn, week + timedelta(days=7), http=mock_http(tmp_path / "c"), imports=tmp_path / "i", gdelt_limit=0
    )
    assert nxt.source_splits == []  # the history is on the new basis now; the ratio stays on its week


def test_gdelt_budget_goes_to_the_highest_evidence_across_both_markets(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    """M4 review R1-F7: with one query left, the staged company with the highest Evidence gets it, whichever market
    it is in (the US was served first, in name order)."""
    week = date(2026, 9, 18)
    us = add(conn, "0000018230")
    repo.upsert_in_companies(conn, [Company(market="in", name="Pledged Ltd", isin="INE000X01011", nse_symbol="PLDG")])
    companies = {c.id: c for c in repo.companies(conn) if c.id is not None}
    ind = repo.company_ids_by(conn, "nse_symbol")["PLDG"]
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    for c in companies.values():
        http.register_mock(timeline_url(build_query(c.name, c.ticker if c.market == "us" else c.nse_symbol, c.market)),
                           (FIX / "gdelt" / "timeline_pwr.json").read_bytes())  # fmt: skip

    def scored(cid: uuid.UUID, ev: int) -> weekly.Scored:
        c = companies[cid]
        e = Evidence(Decimal(ev), Decimal(0), {}, (), 0, False)
        return weekly.Scored(c, Series([], c.market), e, False, {}, None, {})

    nothing = weekly.Priced(None, None, None, Metric(None, None, None, {}), C2(None, None, {}))
    stats = weekly.ScoresStats(week.isoformat())
    rows = weekly.context_rows(conn, week, weekly.Configs.load(), {us: scored(us, 30), ind: scored(ind, 70)},
                               {us: nothing, ind: nothing}, http, 1, stats)  # fmt: skip
    c4 = {r.company_id: r.inputs for r in rows if r.metric_id == "C4"}
    assert stats.gdelt_queried == 1 and "articles_90d" in c4[ind] and c4[us].get("missing") == ["gdelt_count"]


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
