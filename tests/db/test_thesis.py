"""M6 against the database: evidence packs (M6-01), the queue file, ingest from a push event (M6-03), the fallback's
time window (M6-04), kill criteria on a new fundamentals row (M6-05) and the digest issue body (M6-06)."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from pipeline.db import repo
from pipeline.db.models import FundamentalsRow, Score, SignalValue
from pipeline.digest import weekly as digest
from pipeline.digest.github_issue import MockIssues, publish
from pipeline.llm.router import Done
from pipeline.thesis import evidence_pack as ep
from pipeline.thesis import fallback_writer, ingest, kill_criteria, queue

FIX = Path(__file__).resolve().parents[2] / "fixtures"
SNAPSHOT = Path(__file__).resolve().parents[1] / "digest" / "snapshots" / "digest_2026-W38.md"
W = date(2026, 9, 18)
SECRET = "SECRET-JOURNAL-TEXT-7f3a"


def company(conn: psycopg.Connection[Any], cid: str, name: str, ticker: str, market: str = "us") -> uuid.UUID:
    conn.execute(
        "insert into companies (id, market, name, cik, ticker, nse_symbol, fiscal_year_end, sector) "
        "values (%s, %s, %s, %s, %s, %s, '1231', 'Industrials')",
        (
            cid,
            market,
            name,
            "00009" + ticker.zfill(5) if market == "us" else None,
            ticker if market == "us" else None,
            ticker if market == "in" else None,
        ),  # fmt: skip
    )
    return uuid.UUID(cid)


def quarters(cid: uuid.UUID, revenues: list[int], last_end: date = date(2026, 6, 30)) -> list[FundamentalsRow]:
    """Consecutive quarters ending at last_end, each filed 35 days after its quarter end."""
    out = []
    ends = []
    y, m = last_end.year, last_end.month
    for _ in revenues:
        ends.append(date(y, m, 30 if m in (6, 9) else 31))
        y, m = (y, m - 3) if m > 3 else (y - 1, m + 9)
    for end, rev in zip(reversed(ends), revenues, strict=True):
        out.append(FundamentalsRow(company_id=cid, period_end=end, fiscal_label=f"Q{end:%Y%m}",
                                   filed_at=datetime.combine(end + timedelta(days=35), datetime.min.time(), UTC),
                                   revenue=Decimal(rev), op_income=Decimal(rev) / 5, currency="USD",
                                   source="sec_xbrl"))  # fmt: skip
    return out


def week_rows(conn: psycopg.Connection[Any], cid: uuid.UUID, evidence: str = "62.5", gap: str | None = "58.3") -> None:
    repo.upsert_scores(conn, [Score(company_id=cid, week_end=W, evidence=Decimal(evidence),
                                    gap=None if gap is None else Decimal(gap), families=["fundamentals", "text"],
                                    bucket="candidate", weights_version="w0-equal")])  # fmt: skip
    repo.upsert_signal_values(conn, [
        SignalValue(company_id=cid, week_end=W, signal_id="S1", fired=True, strength=Decimal("0.82"),
                    inputs={"g_ob": 0.4483, "g_rev": 0.2755}),
        SignalValue(company_id=cid, week_end=W, signal_id="S5", fired=False, strength=Decimal(0), inputs={}),
    ])  # fmt: skip
    c2 = Jsonb({"g_implied": 0.12, "g_evidence": 0.18})
    conn.execute("insert into context_values (company_id, week_end, metric_id, value, pct, inputs) values "
                 "(%s, %s, 'C2', 0.06, null, %s)", (cid, W, c2))  # fmt: skip


def verified_fact(conn: psycopg.Connection[Any], cid: uuid.UUID, published: datetime, quote: str) -> uuid.UUID:
    doc = conn.execute(
        "insert into documents (company_id, kind, url, published_at, sha256, raw_path) values "
        "(%s, 'EX-99.1', %s, %s, 'x', 'raw') returning id",
        (cid, f"https://www.sec.gov/Archives/edgar/data/1/{uuid.uuid4().hex}/ex991.htm", published),
    ).fetchone()
    assert doc is not None
    row = conn.execute(
        "insert into facts (company_id, document_id, fact_type, subject, subject_key, value_num, unit, as_of, quote, "
        "char_start, char_end, extraction_model, confidence, verification_status) values (%s, %s, 'order_win', "
        "'order', 'order_win:hyperscaler', 600000000, 'usd', %s, %s, 0, %s, 'test', 0.9, 'verified') returning id",
        (cid, doc[0], published.date(), quote, len(quote)),
    ).fetchone()
    assert row is not None
    return uuid.UUID(str(row[0]))


# ---------------------------------------------------------------- M6-01


def test_pack_is_schema_valid_stable_point_in_time_and_public_only(conn: psycopg.Connection[Any]) -> None:
    cid = company(conn, "00000000-0000-4000-8000-0000000000a1", "Quanta Test", "QTST")
    repo.insert_fundamentals(conn, quarters(cid, [800, 850, 900, 950, 1000, 1050, 1100, 1150, 1200, 1250, 1300,
                                                  1350, 1400, 1450]))  # fmt: skip
    week_rows(conn, cid)
    before = verified_fact(conn, cid, datetime(2026, 8, 6, 20, tzinfo=UTC), "a $600 million order from a customer")
    verified_fact(conn, cid, datetime(2026, 9, 19, 1, tzinfo=UTC), "published after the week: not in the pack")
    thesis = conn.execute("insert into theses (company_id, state, card_md, card_json, evidence_pack, author, "
                          "validation, created_week) values (%s, 'position', '', '{}', '{}', 'manual', '{}', %s) "
                          "returning id", (cid, W)).fetchone()  # fmt: skip
    assert thesis is not None
    conn.execute("insert into journal (thesis_id, entry_date, action, portfolio_pct, reason) values "
                 "(%s, %s, 'start_position', 4.5, %s)", (thesis[0], W, SECRET))  # fmt: skip
    conn.execute("insert into postmortems (thesis_id, what_happened, lessons) values (%s, %s, %s)",
                 (thesis[0], SECRET, SECRET))  # fmt: skip
    c = next(x for x in repo.companies(conn) if x.id == cid)
    pack = ep.build(conn, c, W)
    again = ep.build(conn, c, W)
    doc = ep.to_json(pack)
    assert doc == ep.to_json(again) and ep.EvidencePack.model_validate(doc) == pack  # stable
    ids = pack.ids()
    assert len(ids) == len(set(ids)) and all(ep.ID.match(i) for i in ids)
    assert len([m for m in pack.metrics if m.name == "revenue"]) == ep.QUARTERS  # the last 12 quarters
    assert [f.id for f in pack.facts] == [f"f:{before}"] and pack.facts[0].url.startswith("https://www.sec.gov/")
    assert {"s:S1", "c:C2", "c:evidence", "c:gap"} <= set(ids) and "s:S5" not in ids  # fired signals only
    assert next(k.value for k in pack.kill_metrics if k.id == "m:revenue_ttm") == Decimal(1300 + 1350 + 1400 + 1450)
    assert pack.next_filing is not None and pack.next_filing.closes == date(2026, 11, 14)
    text = json.dumps(doc)
    assert SECRET not in text and "portfolio" not in text


def test_queue_holds_the_shortlist_in_rank_order(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    a = company(conn, "00000000-0000-4000-8000-0000000000b1", "Alpha Test", "ALPT")
    b = company(conn, "00000000-0000-4000-8000-0000000000b2", "Beta Test", "BETT")
    for cid in (a, b):
        repo.insert_fundamentals(conn, quarters(cid, [100, 110, 120, 130, 140]))
        week_rows(conn, cid)
    repo.insert_shortlist(conn, W, [(b, Decimal(70), Decimal(60)), (a, Decimal(65), Decimal(55))])
    doc = queue.build_queue(conn, W)
    assert doc["week"] == "2026-W38" and [p["company"]["key"] for p in doc["packs"]] == ["us-bett", "us-alpt"]
    path = queue.write(doc, tmp_path)
    assert path == tmp_path / "data" / "thesis_queue" / "2026-W38.json" and json.loads(path.read_text()) == doc


# ---------------------------------------------------------------- M6-03


def card_tree(tmp_path: Path, cid: uuid.UUID) -> tuple[Path, dict[str, Any]]:
    """data/thesis_queue/2026-W38.json with F-CARD's pack for `cid`, and its good card pushed."""
    pack = json.loads((FIX / "card" / "pack.json").read_text(encoding="utf-8"))
    pack["company"]["company_id"] = str(cid)
    (tmp_path / "data" / "thesis_queue").mkdir(parents=True)
    (tmp_path / "data" / "thesis_queue" / "2026-W38.json").write_text(json.dumps({"week": "2026-W38", "packs": [pack]}))
    cards = tmp_path / "data" / "thesis_cards" / "2026-W38"
    cards.mkdir(parents=True)
    shutil.copy(FIX / "card" / "good.json", cards / "us-nmbs.json")
    (tmp_path / "config").mkdir()
    shutil.copy(FIX.parent / "config" / "terms.yaml", tmp_path / "config" / "terms.yaml")
    return cards, pack


PUSH = {"ref": "refs/heads/routine-2026-W38", "commits": [{"added": ["data/thesis_cards/2026-W38/us-nmbs.json",
                                                                    "data/thesis_cards/2026-W38/us-nmbs.md"],
                                                         "modified": [], "removed": []}],
        "head_commit": {"added": [], "modified": []}}  # fmt: skip


def test_ingest_from_a_push_event_upserts_idempotently(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path, cid)
    shutil.copy(FIX / "card" / "bad_number.json", cards / "us-othr.json")  # no pack and a bad number: rejected
    weeks = ingest.weeks_from_event(PUSH)
    assert weeks == ["2026-W38"]
    stats = ingest.ingest(conn, weeks, tmp_path)
    assert stats.ingested == ["2026-W38/us-nmbs.json"] and list(stats.rejected) == ["2026-W38/us-othr.json"]

    def state() -> list[Any]:
        return conn.execute(
            "select t.state, t.author, t.created_week, k.metric, k.operator, k.threshold, k.baseline, k.check_after "
            "from theses t join kill_criteria k on k.thesis_id = t.id where t.company_id = %s order by k.metric",
            (cid,)).fetchall()  # fmt: skip

    first = state()
    assert first == [("research", "routine", W, "m:op_margin_ttm", "<", Decimal("0.12"), Decimal("0.1650"),
                      date(2026, 11, 20)),
                     ("research", "routine", W, "m:rpo_yoy", "<", Decimal("0.1"), Decimal("0.4483"),
                      date(2026, 11, 20))]  # fmt: skip
    assert ingest.ingest(conn, weeks, tmp_path).ingested == ["2026-W38/us-nmbs.json"] and state() == first
    edited = json.loads((cards / "us-nmbs.json").read_text())
    edited["summary"] = "An edited summary."
    (cards / "us-nmbs.json").write_text(json.dumps(edited))
    ingest.ingest(conn, weeks, tmp_path)
    assert conn.execute("select count(*), max(card_json->>'summary') from theses where company_id = %s",
                        (cid,)).fetchone() == (1, "An edited summary.")  # fmt: skip
    conn.execute("update theses set state = 'thesis' where company_id = %s", (cid,))
    again = ingest.ingest(conn, weeks, tmp_path)
    assert again.unchanged == ["2026-W38/us-nmbs.json"] and again.ingested == []  # accepted cards are left alone


# ---------------------------------------------------------------- M6-04


class CardRouter:
    """P-04 through a fake provider: answers with the given card."""

    def __init__(self, card: dict[str, Any]) -> None:
        self.card, self.calls = card, 0

    def call(self, data: Any) -> Done:
        self.calls += 1
        if data.prompt_id == "P-05":
            return Done({"supported": True, "unsupported_parts": [], "reason": "stated"}, "fake", "m")
        return Done(copy.deepcopy(self.card), "fake", "m")


def test_fallback_runs_only_when_the_week_has_no_cards(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path, cid)
    (cards / "us-nmbs.json").unlink()  # the routine wrote nothing
    good = json.loads((FIX / "card" / "good.json").read_text())
    sunday = datetime(2026, 9, 20, 23, 0, tzinfo=UTC)
    monday = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
    router = CardRouter(good)
    early = fallback_writer.write_cards(conn, router, "2026-W38", tmp_path, now=lambda: sunday)  # type: ignore[arg-type]
    assert not early.ran and "too early" in early.reason and router.calls == 0
    ran = fallback_writer.write_cards(conn, router, "2026-W38", tmp_path, now=lambda: monday)  # type: ignore[arg-type]
    assert ran.ran and ran.written == ["us-nmbs"]
    row = conn.execute("select author, state from theses where company_id = %s", (cid,)).fetchone()
    assert row == ("fallback", "research")
    later = fallback_writer.write_cards(conn, router, "2026-W38", tmp_path, now=lambda: monday + timedelta(hours=1))  # type: ignore[arg-type]
    assert not later.ran and later.reason == "the week already has cards"


def test_fallback_skips_a_week_the_routine_covered(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    card_tree(tmp_path, cid)
    ingest.ingest(conn, ["2026-W38"], tmp_path)
    router = CardRouter({})
    out = fallback_writer.write_cards(conn, router, "2026-W38", tmp_path,  # type: ignore[arg-type]
                                      now=lambda: datetime(2026, 9, 21, 7, tzinfo=UTC))  # fmt: skip
    assert not out.ran and router.calls == 0
    assert fallback_writer.due(W) == datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


# ---------------------------------------------------------------- M6-05


def watched(conn: psycopg.Connection[Any], cid: uuid.UUID) -> uuid.UUID:
    row = conn.execute("insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, "
                       "created_week) values (%s, 'thesis', '', '{}', '{}', 'routine', '{}', %s) returning id",
                       (cid, W - timedelta(days=70))).fetchone()  # fmt: skip
    assert row is not None
    conn.execute("insert into kill_criteria (thesis_id, metric, operator, threshold, check_after, baseline, why) "
                 "values (%s, 'm:revenue_ttm_yoy', '<', 0.05, %s, 0.2, 'growth is the thesis')",
                 (row[0], W - timedelta(days=30)))  # fmt: skip
    return uuid.UUID(str(row[0]))


def test_a_new_fundamentals_row_triggers_a_kill_criterion(conn: psycopg.Connection[Any]) -> None:
    cid = company(conn, "00000000-0000-4000-8000-0000000000d1", "Delta Test", "DLTT")
    repo.insert_fundamentals(conn, quarters(cid, [100, 105, 110, 115, 120, 126, 132, 138]))
    tid = watched(conn, cid)
    first = kill_criteria.evaluate(conn, W)
    assert first.checked == 1 and first.triggered == []
    assert conn.execute("select state from theses where id = %s", (tid,)).fetchone() == ("thesis",)
    # the September quarter's 10-Q, filed within the next week: revenue falls, TTM growth drops under 5%
    new = FundamentalsRow(company_id=cid, period_end=date(2026, 9, 30), fiscal_label="Q202609",
                          filed_at=datetime(2026, 9, 22, 21, tzinfo=UTC), revenue=Decimal(40), currency="USD",
                          source="sec_xbrl")  # fmt: skip
    repo.insert_fundamentals(conn, [new])
    nxt = W + timedelta(days=7)
    second = kill_criteria.evaluate(conn, nxt)
    assert len(second.triggered) == 1 and "m:revenue_ttm_yoy" in second.triggered[0]
    row = conn.execute("select t.state, k.status, k.triggered_week, k.last_value < 0.05 from theses t join "
                       "kill_criteria k on k.thesis_id = t.id where t.id = %s", (tid,)).fetchone()  # fmt: skip
    assert row == ("review", "triggered", nxt, True)
    _, body = digest.build(conn, nxt)
    assert "**Delta Test**: kill criterion `m:revenue_ttm_yoy` < 0.05 met (now -0.0311)" in body
    assert "moved to review" in body
    third = kill_criteria.evaluate(conn, nxt + timedelta(days=7))
    assert third.theses == 0  # in review: no longer monitored, and not triggered twice


# ---------------------------------------------------------------- M6-06


def test_digest_issue_body_snapshot(conn: psycopg.Connection[Any]) -> None:
    a = company(conn, "00000000-0000-4000-8000-0000000000e1", "Echo Grid Corp.", "ECHO")
    b = company(conn, "00000000-0000-4000-8000-0000000000e2", "Kappa Cables", "KAPPA", market="in")
    for cid, ev in ((a, "72.5"), (b, "64")):
        repo.insert_fundamentals(conn, quarters(cid, [100, 110, 120, 130, 140]))
        week_rows(conn, cid, evidence=ev)
    repo.insert_shortlist(conn, W, [(a, Decimal("72.5"), Decimal("61.2")), (b, Decimal(64), None)])
    tid = watched(conn, b)
    conn.execute("update kill_criteria set status = 'triggered', triggered_week = %s, last_value = 0.031 "
                 "where thesis_id = %s", (W, tid))  # fmt: skip
    conn.execute("update theses set state = 'review' where id = %s", (tid,))
    brief = "## Capex brief — week ending 2026-09-18\n\n### Demand index\n\n- grid: rising (+1.2σ)\n"
    conn.execute("insert into capex_briefs (week_end, body_md) values (%s, %s)", (W, brief))
    conn.execute(
        "insert into source_health (source, last_success, last_error, stale) values "
        "('sec', '2026-09-18 06:00+00', null, false), ('nse', '2026-09-12 06:00+00', null, false), "
        "('stooq', null, 'stale: 13 downloads failed: stooq PWR: Exceeded the daily hits limit', true)"
    )
    conn.execute(
        "insert into llm_calls (prompt_id, provider, model, ok, tokens_in, tokens_out, error, created_at) "
        "values ('P-01', 'gemini', 'm', true, 1000, 200, null, '2026-09-16 02:00+00'), "
        "('P-01', 'gemini', 'm', false, null, null, 'gemini: 429', '2026-09-16 02:05+00'), "
        "('P-07', 'groq', 'm', true, 300, 20, null, '2026-09-17 02:00+00'), "
        "('P-01', 'groq', 'm', true, 999, 1, null, '2026-09-10 02:00+00')"
    )  # the week before: not counted
    conn.execute(
        "insert into lab_results (run_at, signal_id, market, horizon_m, period, n, excess_mean, t_nw) "
        "values ('2026-09-15 10:00+00', 'S1', 'us', 12, 'out_of_sample', 56, 0.4, 6.8)"
    )
    title, body = digest.build(conn, W, "https://doomberg.example", now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    assert title == "Doomberg weekly — 2026-W38"
    if not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(body, encoding="utf-8")
        pytest.fail(f"wrote {SNAPSHOT.name}: review it and commit it (the snapshot pins the digest's format)")
    assert body == SNAPSHOT.read_text(encoding="utf-8")
    for word in ("gainer", "loser", "top mover", "return"):
        assert word not in body.lower()  # no price-move content
    api = MockIssues()
    assert publish(api, title, body) == 1
    assert api.requests[-1] == ("POST", "/issues", {"title": title, "body": body, "labels": ["digest"]})
    assert publish(api, title, body) == 1 and api.requests[-1][0] == "PATCH"


@pytest.fixture(autouse=True)
def _mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_EXTERNALS", "true")
