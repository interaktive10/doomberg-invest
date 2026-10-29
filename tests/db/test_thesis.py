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

from pipeline.db import repo, thesis_repo
from pipeline.db.models import FundamentalsRow, Score, SignalValue
from pipeline.digest import weekly as digest
from pipeline.digest.github_issue import MockIssues, publish
from pipeline.llm.router import Done
from pipeline.thesis import evidence_pack as ep
from pipeline.thesis import fallback_writer, ingest, kill_criteria, queue, vault

FIX = Path(__file__).resolve().parents[2] / "fixtures"
SNAPSHOT = Path(__file__).resolve().parents[1] / "digest" / "snapshots" / "digest_2026-W38.md"
W = date(2026, 9, 18)
SECRET = "SECRET-JOURNAL-TEXT-7f3a"
KEY = "test-vault-key-0123456789abcdef"  # THESIS_VAULT_KEY in these tests (tests/thesis/test_vault.py)


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


def verified_fact(conn: psycopg.Connection[Any], cid: uuid.UUID, published: datetime, quote: str,
                  stored: datetime | None = None) -> uuid.UUID:  # fmt: skip
    """A verified order-win fact; `stored` is when the text run wrote it (facts.created_at; now by default)."""
    doc = conn.execute(
        "insert into documents (company_id, kind, url, published_at, sha256, raw_path) values "
        "(%s, 'EX-99.1', %s, %s, 'x', 'raw') returning id",
        (cid, f"https://www.sec.gov/Archives/edgar/data/1/{uuid.uuid4().hex}/ex991.htm", published),
    ).fetchone()
    assert doc is not None
    row = conn.execute(
        "insert into facts (company_id, document_id, fact_type, subject, subject_key, value_num, unit, as_of, quote, "
        "char_start, char_end, extraction_model, confidence, verification_status, created_at) values (%s, %s, "
        "'order_win', 'order', 'order_win:hyperscaler', 600000000, 'usd', %s, %s, 0, %s, 'test', 0.9, 'verified', "
        "coalesce(%s, now())) returning id",
        (cid, doc[0], published.date(), quote, len(quote), stored),
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


PUSH = {"ref": "refs/heads/routine-2026-W38", "commits": [{"added": ["data/thesis_cards/2026-W38.sealed"],
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


def test_fallback_packs_come_from_the_sealed_queue_else_the_database(conn: psycopg.Connection[Any],
                                                                    tmp_path: Path) -> None:  # fmt: skip
    """SPEC_ISSUES 60: the fallback opens main's sealed queue; without the key weekly.yml sealed nothing, so it builds
    the packs from the database as weekly.yml does, for a week with scores only (weekly.yml queues a week only after
    its scores)."""
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    card_tree(tmp_path, cid)
    plain = tmp_path / "data" / "thesis_queue" / "2026-W38.json"
    vault.seal_queue("2026-W38", KEY, tmp_path)
    sealed = plain.read_bytes()
    plain.unlink()
    assert fallback_writer.prepare(conn, "2026-W38", KEY, tmp_path) == "the sealed queue"
    assert plain.read_bytes() == sealed
    assert fallback_writer.prepare(conn, "2026-W38", None, tmp_path) == "the queue file"  # a working copy is read
    plain.unlink()
    assert fallback_writer.prepare(conn, "2026-W38", None, tmp_path) == "" and not plain.exists()  # no scores yet
    a = company(conn, "00000000-0000-4000-8000-0000000000b1", "Alpha Test", "ALPT")
    repo.insert_fundamentals(conn, quarters(a, [100, 110, 120, 130, 140]))
    week_rows(conn, a)
    repo.insert_shortlist(conn, W, [(a, Decimal(70), Decimal(60))])
    assert fallback_writer.prepare(conn, "2026-W38", "another-vault-key-0123456789abcd", tmp_path) == "the database"
    doc = json.loads(plain.read_text())
    assert doc == json.loads(json.dumps(queue.build_queue(conn, W)))
    assert [p["company"]["key"] for p in doc["packs"]] == ["us-alpt"]
    assert fallback_writer.week_end_of("2026-W38") == W
    assert fallback_writer.week_end_of("2026-W01") == date(2026, 1, 2)


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
    assert "## To do\n\n- Theses in review: 1 (Delta Test (DLTT))\n" in body  # names only (overhaul PR 5)
    assert "m:revenue_ttm_yoy" not in body
    third = kill_criteria.evaluate(conn, nxt + timedelta(days=7))
    assert third.theses == 0  # in review: no longer monitored, and not triggered twice


def test_a_retriggered_criterion_is_in_that_weeks_digest(conn: psycopg.Connection[Any]) -> None:
    """M6 review R1-F10: met in week 1 (review), kept as a thesis, not met in week 2, met again in week 3: the
    criterion's triggered_week is week 3, so week 3's digest lists it."""
    cid = company(conn, "00000000-0000-4000-8000-0000000000d2", "Retrigger Test", "RTRG")
    repo.insert_fundamentals(conn, quarters(cid, [100, 105, 110, 115, 120, 126, 132, 138]))
    tid = watched(conn, cid)
    weak = FundamentalsRow(company_id=cid, period_end=date(2026, 9, 30), fiscal_label="Q202609",
                           filed_at=datetime(2026, 9, 22, 21, tzinfo=UTC), revenue=Decimal(40), currency="USD",
                           source="sec_xbrl")  # fmt: skip
    w1, w2, w3 = W + timedelta(days=7), W + timedelta(days=14), W + timedelta(days=21)
    repo.insert_fundamentals(conn, [weak])
    assert len(kill_criteria.evaluate(conn, w1).triggered) == 1
    conn.execute("update theses set state = 'thesis' where id = %s", (tid,))  # reviewed: the thesis stands
    strong = weak.model_copy(update={"revenue": Decimal(150), "filed_at": datetime(2026, 9, 29, 21, tzinfo=UTC)})
    repo.insert_fundamentals(conn, [strong])
    assert kill_criteria.evaluate(conn, w2).triggered == []
    repo.insert_fundamentals(conn, [weak.model_copy(update={"filed_at": datetime(2026, 10, 6, 21, tzinfo=UTC)})])
    assert len(kill_criteria.evaluate(conn, w3).triggered) == 1
    row = conn.execute("select status, triggered_week from kill_criteria where thesis_id = %s", (tid,)).fetchone()
    assert row == ("triggered", w3)
    _, body = digest.build(conn, w3)
    assert "- Theses in review: 1 (Retrigger Test (RTRG))" in body


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
    conn.execute(
        "insert into source_health (source, last_success, last_error, stale) values "
        "('sec', '2026-09-18 06:00+00', null, false), ('twelvedata', '2026-09-07 06:00+00', null, false), "
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
    for word in ("LLM", "gemini", "| Source |", "Capex", "Lab"):  # overhaul PR 5: no quota, source or Lab tables
        assert word not in body, word
    api = MockIssues()
    assert publish(api, title, body) == 1
    assert api.requests[-1] == ("POST", "/issues", {"title": title, "body": body, "labels": ["digest"]})
    assert publish(api, title, body) == 1 and api.requests[-1][0] == "PATCH"


@pytest.fixture(autouse=True)
def _mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_EXTERNALS", "true")


# ---------------------------------------------------------------- M6 review round 1


def test_a_pushed_queue_or_code_change_ingests_nothing(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """R1-F4: a card push may change data/thesis_cards/** only, and since the repository is public only as a sealed
    bundle (SPEC_ISSUES 60); anything else (the queue, code, a plaintext card) ingests nothing. Cards are checked
    against the queue on disk (main's, in thesis-ingest.yml), and that pack must itself pass the EvidencePack schema:
    an extra field fails."""
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    card_tree(tmp_path, cid)
    vault.seal_cards("2026-W38", KEY, tmp_path)
    card = "data/thesis_cards/2026-W38.sealed"
    for other in ("data/thesis_queue/2026-W38.sealed", "pipeline/thesis/validate.py",
                  "data/thesis_cards/2026-W38/us-nmbs.json"):  # fmt: skip
        stats = ingest.from_changed(conn, [card, other], tmp_path, secret=KEY)
        assert stats.ingested == [], other
        assert "a card push carries only data/thesis_cards/<week>.sealed" in stats.rejected["push"][0], other
    assert conn.execute("select count(*) from theses").fetchone() == (0,)
    queue = tmp_path / "data" / "thesis_queue" / "2026-W38.json"
    doc = json.loads(queue.read_text())
    doc["packs"][0]["metrics"][1]["pct"] = "1350000000"  # an edited pack
    queue.write_text(json.dumps(doc))
    stats = ingest.from_changed(conn, [card], tmp_path, secret=KEY)
    assert stats.ingested == [] and any("Extra inputs" in e for e in stats.rejected["2026-W38/us-nmbs.json"])
    del doc["packs"][0]["metrics"][1]["pct"]
    queue.write_text(json.dumps(doc))
    assert ingest.from_changed(conn, [card], tmp_path, secret=KEY).ingested == ["2026-W38/us-nmbs.json"]


def test_ingest_opens_the_sealed_cards_and_queue_and_its_log_names_no_card(conn: psycopg.Connection[Any],
                                                                           tmp_path: Path) -> None:  # fmt: skip
    """SPEC_ISSUES 60: thesis-ingest.yml has main's sealed queue and the push's sealed cards, never a plaintext file in
    git. Without THESIS_VAULT_KEY, or with another key, nothing is opened or ingested. The public log counts rejected
    cards by week and names none: a plaintext card push is refused by count, a failing card by week."""
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path, cid)
    vault.seal_queue("2026-W38", KEY, tmp_path)
    vault.seal_cards("2026-W38", KEY, tmp_path)
    shutil.rmtree(cards)
    (tmp_path / "data" / "thesis_queue" / "2026-W38.json").unlink()  # the checkout holds the sealed files alone
    push = ["data/thesis_cards/2026-W38.sealed"]
    none = ingest.from_changed(conn, push, tmp_path)
    assert none.ingested == [] and "THESIS_VAULT_KEY is not set" in none.rejected["2026-W38"][0]
    wrong = ingest.from_changed(conn, push, tmp_path, secret="another-vault-key-0123456789abcd")
    assert wrong.ingested == [] and "another key sealed it" in wrong.rejected["2026-W38"][0] and not cards.exists()
    assert conn.execute("select count(*) from theses").fetchone() == (0,)
    assert ingest.from_changed(conn, push, tmp_path, secret=KEY).ingested == ["2026-W38/us-nmbs.json"]
    assert (cards / "us-nmbs.json").exists()  # the working copy validate.py and render.py read
    plain = ingest.from_changed(conn, [*push, "data/thesis_cards/2026-W38/us-nmbs.md"], tmp_path, secret=KEY)
    lines = ingest.log_lines(plain)
    assert len(lines) == 1 and "1 unsealed file(s) under data/thesis_cards/" in lines[0] and "nmbs" not in lines[0]
    failed = ingest.IngestStats(rejected={"2026-W38/us-nmbs.json": ["facts[0]: Nimbus Compute's 45% ..."],
                                          "2026-W38/in-m-m.json": ["no pack for in-m-m"],
                                          "2026-W39": ["no queue"]})  # fmt: skip
    assert ingest.log_lines(failed) == ["  rejected 2026-W39: no queue", "  rejected 2 card(s) of 2026-W38: the "
                                        "reasons are in this run's stats (runs, kind thesis_ingest)"]  # fmt: skip


def test_card_md_is_the_rendering_of_the_validated_json(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """R1-F7: a pushed .md never becomes card_md; the rendering of the validated JSON does."""
    from pipeline.thesis.render import render, title_for

    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path, cid)
    (cards / "us-nmbs.md").write_text("A guaranteed multibagger: revenue will triple to $9 billion.\n")
    assert ingest.ingest(conn, ["2026-W38"], tmp_path).ingested == ["2026-W38/us-nmbs.json"]
    md = conn.execute("select card_md from theses where company_id = %s", (cid,)).fetchone()
    good = json.loads((cards / "us-nmbs.json").read_text())
    assert md == (render(good, title_for(cards / "us-nmbs.json", tmp_path)),) and "multibagger" not in md[0]


def test_fallback_and_ingest_llm_calls_are_logged(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """R1-F9: the fallback's P-04 (and P-05) calls go through a router that writes llm_calls and starts from the day's
    usage; both mains build it that way."""
    import inspect

    from pipeline.db import facts_repo
    from pipeline.llm.quotas import Quotas
    from tests.llm.conftest import Scripted, quotas

    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path, cid)
    (cards / "us-nmbs.json").unlink()
    good = json.loads((FIX / "card" / "good.json").read_text())
    base = quotas(["gemini"])
    q = Quotas.from_doc({**base.raw, "routing": {**base.raw["routing"], "P-04-fallback": ["gemini"]}})
    support = {"supported": True, "unsupported_parts": [], "reason": "stated"}
    gemini = Scripted("gemini", [good, *[support] * 6])  # P-05 checks each of the 6 items (M6 review R3-F1)
    today = datetime.now(UTC).date()  # llm_calls.created_at is the database's now()
    router = facts_repo.logged_router(conn, {"gemini": gemini}, q, today)
    out = fallback_writer.write_cards(conn, router, "2026-W38", tmp_path,
                                      now=lambda: datetime(2026, 9, 21, 6, tzinfo=UTC))  # fmt: skip
    assert out.written == ["us-nmbs"] and len(gemini.requests) == 7
    rows = conn.execute("select prompt_id, provider, ok from llm_calls order by created_at").fetchall()
    assert len(rows) == len(gemini.requests) and rows[0] == ("P-04", "gemini", True)
    assert [r[0] for r in rows[1:]] == ["P-05"] * 6
    assert facts_repo.llm_usage(conn, today)["gemini"][0] == len(rows)  # where the next run starts
    for main in (fallback_writer.main, ingest.main):
        assert "facts_repo.logged_router(" in inspect.getsource(main)


def test_the_digest_without_scores_says_the_candidates_are_missing(conn: psycopg.Connection[Any]) -> None:
    """R1-F6: the digest runs every week; when the scoring run didn't finish it still publishes, and says so."""
    conn.execute("insert into source_health (source, last_success, last_error, stale) values "
                 "('sec', '2026-09-01 06:00+00', null, false)")  # fmt: skip
    _, body = digest.build(conn, W, now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    assert "**Candidates are missing this week:** no scores were written for 2026-09-18" in body
    assert "## Health\n\n**Stale data:** sec (no success for 17 days; SLA 8)" in body
    assert "## To do" in body and "## What changed\n\nNo scores this week, so no score changes.\n" in body


@pytest.mark.parametrize(("env", "why"), [
    ({"US_RESULT": "failure", "US_RAN": "true", "SCORES_RESULT": "skipped"},
     "the US data run failed, so nothing was scored"),
    ({"US_RESULT": "success", "US_RAN": "", "SCORES_RESULT": "skipped"},
     "the US data run skipped its steps (a secret is missing), so nothing was scored"),
    ({"US_RESULT": "success", "US_RAN": "true", "SCORES_RESULT": "cancelled"},
     "the scoring run was cancelled or timed out"),
    ({}, "the scoring run didn't finish"),
], ids=["us-failed", "us-skipped", "scores-timed-out", "by-hand"])  # fmt: skip
def test_the_digest_without_scores_says_why(conn: psycopg.Connection[Any], env: dict[str, str], why: str) -> None:
    """Overhaul PR 1 review (actions-GHA-1): scores run only after a us job that ran and succeeded, so a week without
    scores is most often one whose US run failed; weekly.yml passes the jobs' results and the digest names the job
    (tests/digest/test_unscored.py has every case)."""
    _, body = digest.build(conn, W, now=datetime(2026, 9, 19, 3, tzinfo=UTC), why_unscored=digest.unscored_why(env))
    assert (f"**Candidates are missing this week:** no scores were written for 2026-09-18 ({why}; see health "
            "below).") in body  # fmt: skip


def test_health_ends_with_the_actions_minutes_line(conn: psycopg.Connection[Any]) -> None:
    """Overhaul PR 3: the meter's one line (pipeline/digest/minutes.py; tests/digest/test_minutes.py has the line and
    its warning) closes the health section, after the health line (overhaul PR 5: one line, no table); without it (a
    build outside main) the section is the health line alone, as in the snapshot."""
    conn.execute("insert into source_health (source, last_success, last_error, stale) values "
                 "('sec', '2026-09-18 06:00+00', null, false)")  # fmt: skip
    line = "Actions: 812 of 2,000 this cycle, projected 1,340."
    _, body = digest.build(conn, W, now=datetime(2026, 9, 19, 3, tzinfo=UTC), actions=[line])
    section = body.split("## Health\n\n", 1)[1]
    assert section == f"Sources: none late or stale.\n\n{line}\n"
    _, without = digest.build(conn, W, now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    assert "Actions:" not in without


@pytest.mark.parametrize(("nse", "banner"), [("2026-09-18 06:00+00", None), (None, "nse (stale)")],
                         ids=["nse-fine", "nse-stale"])  # fmt: skip
def test_fallback_banner_only_when_its_primary_is_down(conn: psycopg.Connection[Any], nse: str | None,
                                                       banner: str | None,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """M6 review R2-F5: BSE records a success only in weeks it stood in for NSE, so while NSE is within its SLA an
    old BSE date isn't stale data (the table still lists it); when NSE is stale, the banner names NSE. India's rows
    are out of config/staleness.yaml while it is paused (docs/SPEC_ISSUES.md 46): this is the config once they're
    back."""
    sla = digest.sla_days()
    monkeypatch.setattr(digest, "sla_days", lambda root=None: {**sla, "nse": 10, "bse": 10})
    monkeypatch.setattr(digest, "fallbacks", lambda root=None: {"bse": "nse"})
    conn.execute("insert into source_health (source, last_success, last_error, stale) values "
                 "('bse', '2026-08-01 06:00+00', null, false), ('nse', %s, %s, %s)",
                 (nse, None if nse else "stale: 3 bhavcopy downloads failed", nse is None))  # fmt: skip
    _, body = digest.build(conn, W, now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    health = body.split("## Health\n\n", 1)[1]
    if banner is None:
        assert health == "Sources: none late or stale.\n", health
    else:
        assert "**Stale data:**" in health and banner in health and "bse (no success for 48 days; SLA 10)" in health


def test_fallback_p04_and_p05_replay_from_cassettes(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """R1-F13 (BRIEF §9 "fallback P-04" and P-05 cassettes): P-04 on F-CARD's pack and validate.py's P-05 call are
    recorded through cassette recorders (pipeline.thesis.samples, as record-cassettes.yml does), and the fallback
    writer replays them offline and writes the card."""
    from pipeline.llm.cassettes import Player, Recorder, manifest_problems, write_manifest
    from pipeline.llm.quotas import Quotas
    from pipeline.llm.router import Router
    from pipeline.thesis import samples
    from tests.llm.conftest import FakeClock, Scripted, quotas

    order = "f:6f1c2a52-3b1e-4c43-9e59-3d1b1f0a0002"
    card = json.loads((FIX / "card" / "good.json").read_text())
    card["facts"][3] = {"text": f"A hyperscale cloud provider placed a multi-year order [{order}].", "cites": [order]}
    base = quotas(["gemini"])
    q = Quotas.from_doc({**base.raw, "routing": {**base.raw["routing"], "P-04-fallback": ["gemini"]}})
    tapes = tmp_path / "cassettes"
    support = {"supported": True, "unsupported_parts": [], "reason": "the quote states the order"}
    # P-05 checks each of the card's 6 fact and why-mispriced items (M6 review R3-F1)
    recorder = Router({"gemini": Recorder(Scripted("gemini", [card, *[support] * 6]), tapes)}, q, FakeClock())
    _, result = samples.run(recorder)
    assert result is not None and result.ok, result
    write_manifest(tapes)
    assert {p.parent.name for p in tapes.rglob("*.json")} == {"P-04", "P-05"} and manifest_problems(tapes) == []
    pack_id = json.loads((FIX / "card" / "pack.json").read_text())["company"]["company_id"]
    cid = company(conn, pack_id, "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path / "repo", cid)
    (cards / "us-nmbs.json").unlink()  # the routine wrote nothing: the fallback runs
    player = Router({"gemini": Player("gemini", tapes)}, q, FakeClock())
    out = fallback_writer.write_cards(conn, player, "2026-W38", tmp_path / "repo",
                                      now=lambda: datetime(2026, 9, 21, 6, tzinfo=UTC))  # fmt: skip
    assert out.written == ["us-nmbs"] and out.failed == {}


# ---------------------------------------------------------------- overhaul PR 5: research entries and What changed


def research_entry(conn: psycopg.Connection[Any], cid: uuid.UUID, week: date, state: str = "research") -> uuid.UUID:
    """What the web app's Research button stores (web/app/(app)/candidates/actions.ts research): a thesis in research
    by `manual` with no card, for the latest scored week."""
    row = conn.execute("insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, "
                       "created_week) values (%s, %s, '', '{}', '{}', 'manual', '{}', %s) returning id",
                       (cid, state, week)).fetchone()  # fmt: skip
    assert row is not None
    return uuid.UUID(str(row[0]))


def test_queue_adds_research_entries_after_the_shortlist_oldest_first(conn: psycopg.Connection[Any]) -> None:
    """docs/SPEC_ISSUES.md 35: the open manual research entries come after the shortlist, oldest first, within the
    10 packs; one on the shortlist is packed once, one made after the week or dismissed is not packed."""
    a, b, c, d, e = (company(conn, f"00000000-0000-4000-8000-0000000000f{i}", f"Research {i}", f"RSR{i}")
                     for i in range(1, 6))  # fmt: skip
    for cid in (a, b, c, d, e):
        repo.insert_fundamentals(conn, quarters(cid, [100, 110, 120, 130, 140]))
        week_rows(conn, cid)
    repo.insert_shortlist(conn, W, [(a, Decimal(70), Decimal(60))])
    research_entry(conn, b, W - timedelta(days=7))
    research_entry(conn, c, W - timedelta(days=14))  # the oldest
    research_entry(conn, a, W - timedelta(days=7))  # on the shortlist: packed once, in its rank
    research_entry(conn, d, W + timedelta(days=7))  # made after the week
    research_entry(conn, e, W - timedelta(days=21), state="dismissed")
    doc = queue.build_queue(conn, W)
    assert [p["company"]["key"] for p in doc["packs"]] == ["us-rsr1", "us-rsr3", "us-rsr2"]
    assert [p["company"]["key"] for p in queue.build_queue(conn, W, limit=2)["packs"]] == ["us-rsr1", "us-rsr3"]


def test_ingest_fills_a_research_entry_in_place_idempotently(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """docs/SPEC_ISSUES.md 35, M6-03: the card for a company with an open research entry fills that row (its link
    stays) with the author and the validation result, and a re-run updates the same row. A card that fails validation
    leaves the entry as it was, which the web app can't accept (web/lib/theses.ts acceptable: not by `manual`, a card,
    validation.ok)."""
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    cards, _ = card_tree(tmp_path, cid)
    entry = research_entry(conn, cid, W - timedelta(days=7))

    def theses() -> list[Any]:
        return conn.execute(
            "select t.id, t.state, t.author, t.created_week, t.card_md <> '', t.validation -> 'ok', "
            "(select count(*) from kill_criteria k where k.thesis_id = t.id) from theses t where t.company_id = %s",
            (cid,)).fetchall()  # fmt: skip

    good = (cards / "us-nmbs.json").read_text()
    shutil.copy(FIX / "card" / "bad_number.json", cards / "us-nmbs.json")
    bad = ingest.ingest(conn, ["2026-W38"], tmp_path)
    assert bad.ingested == [] and list(bad.rejected) == ["2026-W38/us-nmbs.json"]
    unfilled = theses()
    assert unfilled == [(entry, "research", "manual", W - timedelta(days=7), False, None, 0)]
    _, _, author, _, has_card, ok, _ = unfilled[0]
    assert not (author != "manual" and has_card and ok is True)  # not acceptable

    (cards / "us-nmbs.json").write_text(good)
    assert ingest.ingest(conn, ["2026-W38"], tmp_path).ingested == ["2026-W38/us-nmbs.json"]
    filled = theses()
    assert filled == [(entry, "research", "routine", W, True, True, 2)]  # the same row, now with its card
    assert ingest.ingest(conn, ["2026-W38"], tmp_path).ingested == ["2026-W38/us-nmbs.json"] and theses() == filled
    conn.execute("update theses set state = 'thesis' where id = %s", (entry,))  # accepted
    assert ingest.ingest(conn, ["2026-W38"], tmp_path).unchanged == ["2026-W38/us-nmbs.json"]


def test_ingest_of_a_shortlisted_research_entry_never_breaks_the_weeks_unique_card(
    conn: psycopg.Connection[Any], tmp_path: Path
) -> None:
    """Migration 0010's theses_generated_week allows one routine/fallback card per company and week. A research entry
    whose company is also on the week's shortlist gets one pack and one card: ingest fills the entry, and a re-run
    updates that row (one generated card for the week, no second insert). When the week already has a generated card
    of the company (Manzoor dismissed it, then pressed Research again), the fill is skipped, so the update can't
    collide with it: the card stays as it was and the entry waits for a later week's card."""
    cid = company(conn, "00000000-0000-4000-8000-00000000c0de", "Nimbus Compute Corp.", "NMBS")
    card_tree(tmp_path, cid)
    repo.insert_shortlist(conn, W, [(cid, Decimal(70), Decimal(60))])
    entry = research_entry(conn, cid, W - timedelta(days=7))

    def rows() -> list[Any]:
        return conn.execute("select id, state, author, created_week from theses where company_id = %s order by id",
                            (cid,)).fetchall()  # fmt: skip

    for _ in range(2):  # idempotent
        assert ingest.ingest(conn, ["2026-W38"], tmp_path).ingested == ["2026-W38/us-nmbs.json"]
        assert rows() == [(entry, "research", "routine", W)]

    conn.execute("update theses set state = 'dismissed' where id = %s", (entry,))
    again = research_entry(conn, cid, W)  # Research pressed again in the same scored week
    for _ in range(2):
        stats = ingest.ingest(conn, ["2026-W38"], tmp_path)
        assert stats.unchanged == ["2026-W38/us-nmbs.json"] and stats.rejected == {}
        assert sorted(rows(), key=lambda r: r[2]) == [(again, "research", "manual", W),
                                                      (entry, "dismissed", "routine", W)]  # fmt: skip


def scored_week(conn: psycopg.Connection[Any], cid: uuid.UUID, week: date, evidence: str, bucket: str, fired: str,
                families: tuple[str, ...] = ("fundamentals", "text"),
                flags: tuple[tuple[str, bool, str], ...] = ()) -> None:  # fmt: skip
    repo.upsert_scores(conn, [Score(company_id=cid, week_end=week, evidence=Decimal(evidence), gap=Decimal(58),
                                    families=list(families), bucket=bucket, weights_version="w0-equal")])  # fmt: skip
    repo.upsert_signal_values(conn, [
        SignalValue(company_id=cid, week_end=week, signal_id=s, fired=s in fired.split(),
                    strength=Decimal("0.8") if s in fired.split() else Decimal(0), inputs={})
        for s in ("S1", "S4", "S9")])  # fmt: skip
    for flag_id, hard, status in flags:
        conn.execute("insert into redflag_values (company_id, week_end, flag_id, hard, inputs) values (%s, %s, %s, %s, "
                     "%s)", (cid, week, flag_id, hard, Jsonb({"status": status})))  # fmt: skip


def diff(conn: psycopg.Connection[Any], cid: uuid.UUID, fact: uuid.UUID, kind: str, note: str) -> None:
    conn.execute("insert into diffs (company_id, subject_key, new_fact_id, change_kind, computed_note) values "
                 "(%s, 'order_win:hyperscaler', %s, %s, %s)", (cid, fact, kind, note))  # fmt: skip


def test_what_changed_reads_this_and_last_week_and_the_weeks_facts(conn: psycopg.Connection[Any]) -> None:
    """Overhaul PR 5: the previous scored week against this one (a fired red flag counts, an `unknown` one doesn't),
    then the scope's verified facts stored in the week (point in time: published and stored before the week's cutoff),
    with their diffs, reaffirmed ones left out; the funnel counts the week's stored rows."""
    prev = W - timedelta(days=7)
    mtdr = company(conn, "00000000-0000-4000-8000-0000000000a1", "Matador Test", "MTDR")
    quiet = company(conn, "00000000-0000-4000-8000-0000000000a2", "Quiet Test", "QUIE")
    flag = company(conn, "00000000-0000-4000-8000-0000000000a3", "Flag Test", "FLAG")
    other = company(conn, "00000000-0000-4000-8000-0000000000a4", "Outside Test", "OUTS")
    scored_week(conn, mtdr, prev, "62", "candidate", "S4 S9")
    scored_week(conn, mtdr, W, "48", "none", "S9", families=("text",))
    scored_week(conn, quiet, prev, "50", "early", "S1 S9")
    scored_week(conn, quiet, W, "50", "early", "S1 S9", flags=(("R1", False, "unknown"),))
    scored_week(conn, flag, prev, "52", "early", "S1 S9")
    scored_week(conn, flag, W, "52", "early", "S1 S9", flags=(("R1", False, "fired"),))
    scored_week(conn, other, W, "30", "none", "S1")

    def fact(cid: uuid.UUID, published: datetime, quote: str) -> uuid.UUID:
        return verified_fact(conn, cid, published, quote, stored=published + timedelta(hours=2))

    raised = fact(mtdr, datetime(2026, 9, 15, 20, tzinfo=UTC), "a $600 million order from a customer")
    diff(conn, mtdr, raised, "raised", "$400.0M → $600.0M (+50.0%)")
    same = fact(mtdr, datetime(2026, 9, 16, 20, tzinfo=UTC), "the order book is unchanged at $600m")
    diff(conn, mtdr, same, "reaffirmed", "$600.0M → $600.0M (+0.0%)")
    fact(mtdr, datetime(2026, 9, 19, 1, tzinfo=UTC), "published after the week's cutoff")
    fact(mtdr, datetime(2026, 9, 10, 20, tzinfo=UTC), "published and read before the week began")
    fact(other, datetime(2026, 9, 15, 20, tzinfo=UTC), "a company outside the scope")
    _, body = digest.build(conn, W, now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    assert "## This week\n\nUS 4 → stage 3 → candidates 0 → new 0 · 1 of 3 fire one family, capped at 55\n" in body
    section = body.split("## What changed\n\n", 1)[1].split("\n\n## ", 1)[0]
    assert section.splitlines() == [
        f"- [MTDR](/company/{mtdr}) left Candidate: S4 stopped, Evidence 62 → 48",
        f"- [FLAG](/company/{flag}) R1 soft flag",
        f"- [MTDR](/company/{mtdr}) order win raised: $400.0M → $600.0M (+50.0%)",
    ]  # fmt: skip


def test_a_fact_read_a_week_late_is_in_the_next_digest_once(conn: psycopg.Connection[Any]) -> None:
    """PR 5 review: the daily reader defers documents, so a fact is often stored a week or more after its filing was
    published. What changed selects facts by when they were stored (and published before the week's cutoff), so one
    published in week 1 and read in week 2 is in week 2's digest, and in no other."""
    w1, w2, w3 = W - timedelta(days=7), W, W + timedelta(days=7)
    cid = company(conn, "00000000-0000-4000-8000-0000000000a5", "Late Read Test", "LATE")
    for week in (w1, w2, w3):
        scored_week(conn, cid, week, "62", "candidate", "S1 S9")  # nothing else changes
    # published in week 1, read in week 2
    verified_fact(conn, cid, datetime(2026, 9, 9, 20, tzinfo=UTC), "a $600 million order from a customer",
                  stored=datetime(2026, 9, 15, 2, tzinfo=UTC))  # fmt: skip
    line = f"- [LATE](/company/{cid}) new verified order win: order"
    seen = {}
    for week in (w1, w2, w3):
        _, body = digest.build(conn, week, now=datetime.combine(week + timedelta(days=1), datetime.min.time(), UTC))
        seen[week] = body.split("## What changed\n\n", 1)[1].split("\n\n## ", 1)[0].count("new verified order win")
    assert seen == {w1: 0, w2: 1, w3: 0}
    _, body = digest.build(conn, w2, now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    assert line in body


def test_the_digest_never_carries_private_fields(conn: psycopg.Connection[Any]) -> None:
    """Overhaul PR 5 (the digest is a GitHub issue): with a company in What changed and To do, its position state, the
    start_position date, journal reasons, reviews.note, candidate_actions.reason, dismissed_reason, override_reason
    and post-mortems are seeded with sentinels, and none reaches body_md."""
    prev = W - timedelta(days=7)
    cid = company(conn, "00000000-0000-4000-8000-0000000000b9", "Private Test", "PRIV")
    gone = company(conn, "00000000-0000-4000-8000-0000000000ba", "Dismissed Test", "DISM")
    scored_week(conn, cid, prev, "61", "candidate", "S1 S9")
    scored_week(conn, cid, W, "73", "candidate", "S1 S4 S9")
    scored_week(conn, gone, prev, "64", "candidate", "S1 S9")
    scored_week(conn, gone, W, "63", "early", "S1 S9")
    held = conn.execute("insert into theses (company_id, state, card_md, card_json, evidence_pack, author, validation, "
                        "created_week, next_review) values (%s, 'position', '', '{}', '{}', 'routine', '{}', %s, %s) "
                        "returning id", (cid, W - timedelta(days=70), W - timedelta(days=1))).fetchone()  # fmt: skip
    closed = conn.execute("insert into theses (company_id, state, card_md, card_json, evidence_pack, author, "
                          "validation, created_week, dismissed_reason) values (%s, 'dismissed', '', '{}', '{}', "
                          "'routine', '{}', %s, %s) returning id", (gone, prev, SECRET)).fetchone()  # fmt: skip
    assert held is not None and closed is not None
    conn.execute("insert into journal (thesis_id, entry_date, action, portfolio_pct, reason, override_reason) values "
                 "(%s, '2026-08-27', 'start_position', 7.25, %s, %s)", (held[0], SECRET, SECRET))  # fmt: skip
    conn.execute("insert into reviews (thesis_id, period_end, note) values (%s, '2026-06-30', %s)", (held[0], SECRET))
    conn.execute("insert into postmortems (thesis_id, what_happened, lessons) values (%s, %s, %s)",
                 (closed[0], SECRET, SECRET))  # fmt: skip
    conn.execute("insert into candidate_actions (company_id, week_end, action, reason) values (%s, %s, 'dismiss', %s)",
                 (gone, prev, SECRET))  # fmt: skip
    title, body = digest.build(conn, W, "https://doomberg.example", now=datetime(2026, 9, 19, 3, tzinfo=UTC))
    thesis_repo.upsert_digest(conn, W, title, body, None)
    stored = conn.execute("select body_md from digests where week_end = %s", (W,)).fetchone()
    assert stored is not None and stored[0] == body
    assert f"[PRIV](https://doomberg.example/company/{cid}) Evidence 61 → 73: S4 fired" in body  # in What changed
    assert "- Theses in review: 1 (Private Test (PRIV))" in body  # in To do (its review date has come)
    assert "[DISM]" in body  # left Candidate
    for secret in (SECRET, "2026-08-27", "7.25", "start_position"):
        assert secret not in stored[0], secret
    assert "position" not in stored[0].lower() and "journal" not in stored[0].lower()
    # a public repository's issue (SPEC_ISSUES 57): not even the position's name or ticker
    pub = digest.public_body(body, "https://doomberg.example")
    assert "Private Test" not in pub and "PRIV" not in pub and "DISM" not in pub and "- Theses in review: 1" in pub
