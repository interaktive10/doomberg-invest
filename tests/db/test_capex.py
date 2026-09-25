"""The Capex Desk against the database (BRIEF §4.11): memberships count only once confirmed (M5-06; a rejection needs
a reason; a decided row is never overwritten by a new proposal), S11's view (index direction, graph distance through
links, export exposure), the demand index built from point-in-time facts, P-06 on an India company's text, and the
weekly brief."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from pipeline.capex import desk
from pipeline.capex import run as capex
from pipeline.db import facts_repo, repo
from pipeline.db.models import CorpEvent
from pipeline.facts.canonical import canonical
from pipeline.facts.process import normalize
from pipeline.llm.providers.base import Completion, Request
from pipeline.llm.router import Router
from tests.db.test_facts_pipeline import router
from tests.llm.conftest import FakeClock, quotas

WEEK = date(2026, 9, 25)


def company(conn: psycopg.Connection[Any], market: str, name: str, ticker: str, cik: str | None = None,
            capex_desk: bool = True) -> UUID:  # fmt: skip
    col = "ticker" if market == "us" else "nse_symbol"
    fye = "1231" if market == "us" else "0331"
    row = conn.execute(f"insert into companies (market, name, cik, {col}, capex_desk, fiscal_year_end) "  # noqa: S608
                       "values (%s, %s, %s, %s, %s, %s) returning id",
                       (market, name, cik, ticker, capex_desk, fye)).fetchone()  # fmt: skip
    assert row is not None
    cid: UUID = row[0]
    return cid


def document(conn: psycopg.Connection[Any], cid: UUID, url: str, published: datetime) -> UUID:
    return facts_repo.upsert_document(conn, company_id=cid, kind="10-Q", url=url, published_at=published,
                                      sha256="0" * 64, raw_path="/dev/null", status="extracted")  # fmt: skip


def fact(conn: psycopg.Connection[Any], cid: UUID, doc: UUID, fact_type: str, key: str, value: D, unit: str,
         as_of: date, period_end: date | None = None, quote: str = "A stated fact for the test.") -> None:  # fmt: skip
    conn.execute(
        "insert into facts (company_id, document_id, fact_type, subject, subject_key, value_num, unit, as_of, "
        "period_end, quote, char_start, char_end, extraction_model, confidence, verification_status) values "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, 'test', 0.9, 'verified')",
        (cid, doc, fact_type, key, key, value, unit, as_of, period_end, quote, len(quote)),
    )


def test_memberships_count_only_after_confirmation(conn: psycopg.Connection[Any]) -> None:
    cid = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    assert facts_repo.propose_membership(conn, cid, "grid", "p06", "{}", "EHV cables for utilities")
    assert facts_repo.propose_membership(conn, cid, "power_equipment", "p06", "{}", "substation equipment")
    assert desk.load_views(conn, WEEK, repo.companies(conn)) == {}  # proposals don't count
    facts_repo.decide_membership(conn, cid, "grid", "confirmed", at=datetime(2026, 9, 20, tzinfo=UTC))
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        facts_repo.decide_membership(conn, cid, "power_equipment", "rejected")  # a rejection needs a reason
    facts_repo.decide_membership(conn, cid, "power_equipment", "rejected", "cables, not transformers")
    assert not facts_repo.propose_membership(conn, cid, "grid", "p06", "{}", "a new quote")  # decided rows stay
    status = dict(conn.execute("select category, status from capex_memberships").fetchall())
    assert status == {"grid": "confirmed", "power_equipment": "rejected"}
    views = desk.load_views(conn, WEEK, repo.companies(conn))
    assert list(views[cid].categories) == ["grid"]


def test_a_membership_counts_from_the_week_it_was_confirmed(conn: psycopg.Connection[Any]) -> None:
    """M5 review R1-F5: a confirmation made on 2026-09-25 doesn't reach back into June's S11 view (point in time),
    and counts from its own week."""
    cid = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    facts_repo.propose_membership(conn, cid, "grid", "p06", "{}", "EHV cables for utilities")
    facts_repo.decide_membership(conn, cid, "grid", "confirmed", at=datetime(2026, 9, 25, 13, 51, tzinfo=UTC))
    assert desk.load_views(conn, date(2026, 6, 26), repo.companies(conn)) == {}
    assert desk.load_views(conn, date(2026, 9, 18), repo.companies(conn)) == {}
    assert list(desk.load_views(conn, WEEK, repo.companies(conn))[cid].categories) == ["grid"]


def test_eia_values_count_from_their_release(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M5 review R1-F5: EIA publishes month M's 860M inventory late in month M+1, so its value is filed under the
    end of M+1; a re-run of an earlier week doesn't read a later release."""
    from pipeline.capex import eia
    from pipeline.net.http import HttpClient
    from pipeline.settings import Settings

    fix = Path(__file__).resolve().parents[2] / "fixtures" / "eia"
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    start = WEEK - timedelta(days=365 * capex.EIA_YEARS)
    http.register_mock(eia.url("k3y", f"{start:%Y-%m}", f"{WEEK:%Y-%m}", 0), (fix / "planned_page1.json").read_bytes())
    http.register_mock(eia.url("k3y", f"{start:%Y-%m}", f"{WEEK:%Y-%m}", eia.PAGE),
                       (fix / "planned_page2.json").read_bytes())  # fmt: skip
    capex.ingest_eia(conn, http, "k3y", WEEK, capex.CapexStats(WEEK.isoformat()))
    rows = conn.execute("select week_end, value, detail->>'month' from capex_inputs "
                        "where input_id = 'eia_planned_additions_mw' order by 1").fetchall()  # fmt: skip
    assert rows == [(date(2026, 7, 31), D("370.5"), "2026-06"), (date(2026, 8, 31), D(1100), "2026-07"),
                    (date(2026, 9, 30), D(1114), "2026-08")]  # fmt: skip
    seen = facts_repo.capex_input_history(conn, "eia_planned_additions_mw", date(2026, 1, 1), date(2026, 8, 28))
    assert len(seen) == 1  # as of 2026-08-28 only June's value (published in July) was out


def test_s11_view_has_the_index_the_distance_and_export_exposure(conn: psycopg.Connection[Any]) -> None:
    msft = company(conn, "us", "MICROSOFT CORP", "MSFT", "0000789019", capex_desk=True)
    volt = company(conn, "us", "Voltara Grid Systems, Inc.", "VOLT", "0000999002")
    arvl = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    for cid, cat in ((volt, "grid"), (arvl, "grid")):
        facts_repo.propose_membership(conn, cid, cat, "industry_map", "test")
        facts_repo.decide_membership(conn, cid, cat, "confirmed", at=datetime(2026, 9, 20, tzinfo=UTC))
    facts_repo.upsert_capex_index(conn, WEEK, [{"category": "grid", "value": D("0.8"), "direction": "rising",
                                                "input_growth": D("0.35"), "inputs": {}}])  # fmt: skip
    t0 = datetime(2026, 1, 5, tzinfo=UTC)
    doc_v = document(conn, volt, "https://www.sec.gov/v.htm", t0)
    doc_a = document(conn, arvl, "https://nsearchives.nseindia.com/a.pdf", t0)
    fact(conn, volt, doc_v, "supply_link", "link:microsoft", D(0), "other", date(2026, 1, 5))
    fact(conn, arvl, doc_a, "supply_link", "link:voltara", D(0), "other", date(2026, 1, 5))
    fact(conn, arvl, doc_a, "export_exposure", "export_exposure:share_pct", D(28), "percent", date(2025, 6, 30))
    fact(conn, arvl, doc_a, "export_exposure", "export_exposure:share_pct", D(35), "percent", date(2026, 1, 5),
         quote="Exports to data center projects in the United States were 35% of revenue.")  # fmt: skip
    fids = {r[1]: r[0] for r in conn.execute("select id, subject_key from facts where fact_type = 'supply_link'")}
    e_msft = facts_repo.upsert_entity(conn, "Microsoft Corporation", "microsoft", "company", "0000789019")
    e_volt = facts_repo.upsert_entity(conn, "Voltara Grid Systems", "voltara grid systems", "company")
    facts_repo.link_fact(conn, fids["link:microsoft"], volt, e_msft, "customer")
    facts_repo.link_fact(conn, fids["link:voltara"], arvl, e_volt, "customer")
    conn.execute("update links set first_seen_at = %s", (datetime(2026, 1, 6, tzinfo=UTC),))  # not the wall clock
    views = desk.load_views(conn, WEEK, repo.companies(conn))
    assert views[volt].graph_distance == 1 and views[arvl].graph_distance == 2 and msft not in views
    assert views[arvl].direction == {"grid": "rising"} and views[arvl].input_growth == {"grid": D("0.35")}
    assert views[arvl].export_exposure_rising and views[arvl].export_quote
    assert not views[volt].export_exposure_rising


def test_the_index_from_point_in_time_facts(conn: psycopg.Connection[Any]) -> None:
    """Hyperscaler guidance growing faster over the last half-year: `compute` rises; the facts are read as of the
    week, so a guidance published after it changes nothing."""
    msft = company(conn, "us", "MICROSOFT CORP", "MSFT", "0000789019")
    start = date(2023, 1, 6)
    for k in range(0, 190, 4):  # a new statement every 4 weeks; +10%/yr, then +60%/yr in the last 26 weeks
        d = start + timedelta(weeks=k)
        years = k / 52
        rate = 0.10 if d < WEEK - timedelta(weeks=26) else 0.60
        value = D(
            str(
                round(
                    50e9
                    * (1.10**years)
                    * (1 + (rate - 0.10) * max(0.0, (d - (WEEK - timedelta(weeks=26))).days / 365)),
                    0,
                )
            )
        )
        doc = document(conn, msft, f"https://www.sec.gov/msft/{k}.htm", datetime.combine(d, datetime.min.time(), UTC))
        fact(conn, msft, doc, "capex_guidance", "capex_guidance:FY2027", value, "usd", d, date(2027, 6, 30))
    late = document(conn, msft, "https://www.sec.gov/msft/late.htm", datetime(2026, 10, 30, tzinfo=UTC))
    fact(conn, msft, late, "capex_guidance", "capex_guidance:FY2027", D(10) ** 13, "usd", date(2026, 10, 30),
         date(2027, 6, 30))  # fmt: skip
    stats = capex.CapexStats(WEEK.isoformat())
    capex.build_index(conn, WEEK, repo.companies(conn), desk.config(), stats)
    rows = {r["category"]: r for r in facts_repo.capex_index(conn, WEEK)}
    assert set(rows) == set(desk.config()["categories"])
    assert rows["compute"]["direction"] == "rising" and rows["compute"]["value"] > D("0.5")
    assert rows["grid"]["direction"] == "flat" and rows["grid"]["value"] is None  # no grid inputs yet
    level = conn.execute("select value from capex_inputs where input_id = 'hyperscaler_capex_guidance' "
                         "and week_end = %s", (WEEK,)).fetchone()  # fmt: skip
    assert level is not None and level[0] < D(10) ** 12  # the statement published after the week isn't read


def test_p06_proposes_grounded_memberships_and_an_export_fact(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    arvl = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    repo.insert_corp_events(conn, [CorpEvent(
        company_id=arvl, event_date=date(2026, 9, 18), filed_at=datetime(2026, 9, 18, 10, tzinfo=UTC),
        kind="announcement", source_url="https://nsearchives.nseindia.com/corporate/ARVL_1.pdf",
        detail={"category": "Award of Order", "text": "Aravalli Cables has received an export order for extra-high "
                "voltage cables and substation equipment for a data center in the United States. Exports were 35% of "
                "revenue in FY2026."})])  # fmt: skip
    stats = capex.CapexStats(WEEK.isoformat())
    capex.cross_border(conn, router(), None, repo.companies(conn), {arvl}, WEEK, desk.config(), tmp_path, stats)
    rows = conn.execute("select category, status, quote, char_start, char_end from capex_memberships").fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        ("grid", "proposed")
    ] and stats.p06_dropped == 1  # the GPU quote isn't there
    doc = conn.execute("select id, url from documents where url like 'nse-profile:%'").fetchone()
    assert doc is not None and doc[1] == "nse-profile:ARVL:2026-09-25"
    exp = conn.execute("select value_num, verification_status, quote from facts where fact_type = 'export_exposure'")
    value, status, quote = exp.fetchone() or (None, None, None)
    assert value == D(35) and status == "verified" and quote.startswith("Exports were 35% of revenue")
    assert stats.proposed_in == 1 and stats.export_facts == 1
    assert (tmp_path / "raw" / "ARVL" / "profile" / "20260925.txt").exists()  # the P-06 text is kept on the runner


class Scripted:
    """A provider with one fixed answer."""

    name = "gemini"

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.requests: list[Request] = []

    def available(self) -> bool:
        return True

    def complete(self, req: Request) -> Completion:
        self.requests.append(req)
        return Completion(self.answer)


def test_p06_quotes_are_grounded_in_the_canonical_text(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    """M5 review R1-F3: the announcement has CRLF and double spaces, and the model quotes it with single spaces.
    Every membership and fact of the P-06 document is its canonical text at the stored offsets (M5-02), and a quote
    found only past the 30,000 characters P-06 was sent is dropped."""
    arvl = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    body = ("Aravalli Cables has received an export order for extra-high voltage cables  and substation\r\n"
            "equipment for a data center.\r\n\r\nExports were 35%  of revenue in FY2026."
            + " The company makes cables for many industries." * 800
            + " Our transformer factory supplies substations in Europe.")  # fmt: skip
    repo.insert_corp_events(conn, [CorpEvent(
        company_id=arvl, event_date=date(2026, 9, 18), filed_at=datetime(2026, 9, 18, 10, tzinfo=UTC),
        kind="announcement", source_url="https://nsearchives.nseindia.com/corporate/ARVL_2.pdf",
        detail={"category": "Award of Order", "text": body})])  # fmt: skip
    answer = {
        "categories": [
            {"category": "grid", "quote": "extra-high voltage cables and substation equipment for a data center",
             "confidence": 0.9},
            {"category": "power_equipment", "quote": "Our transformer factory supplies substations in Europe.",
             "confidence": 0.9},  # only past the 30,000 characters sent
        ],
        "export_exposure": {"share_pct": 35, "overseas_order_book": None,
                            "quote": "Exports were 35% of revenue in FY2026."},
    }  # fmt: skip
    provider = Scripted(answer)
    stats = capex.CapexStats(WEEK.isoformat())
    capex.cross_border(conn, Router({"gemini": provider}, quotas(["gemini"], rpd=100), FakeClock()), None,
                       repo.companies(conn), {arvl}, WEEK, desk.config(), tmp_path, stats)  # fmt: skip
    doc = conn.execute("select id, url, raw_path from documents where url like 'nse-profile:%'").fetchone()
    assert doc is not None
    text = normalize(doc[1], Path(doc[2]).read_bytes()).text
    assert len(text) > 30_000 and "\r" not in provider.requests[0].user and "  " not in provider.requests[0].user
    rows = conn.execute(
        "select quote, char_start, char_end from facts where document_id = %(d)s union all "
        "select quote, char_start, char_end from capex_memberships where document_id = %(d)s",
        {"d": doc[0]},
    ).fetchall()
    assert len(rows) == 2 and stats.p06_dropped == 1  # the grid membership and the export fact
    for quote, start, end in rows:
        assert text[start:end] == quote and canonical(quote) == quote


def test_the_weekly_brief(conn: psycopg.Connection[Any]) -> None:
    cid = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    facts_repo.propose_membership(conn, cid, "grid", "p06", "{}", "EHV cables and substation equipment")
    facts_repo.upsert_capex_index(conn, WEEK - timedelta(days=7), [{"category": "grid", "value": D("0.2"),
                                  "direction": "flat", "input_growth": D("0.1"), "inputs": {}}])  # fmt: skip
    facts_repo.upsert_capex_index(conn, WEEK, [{"category": "grid", "value": D("0.7"), "direction": "rising",
                                                "input_growth": D("0.3"), "inputs": {}}])  # fmt: skip
    text = capex.brief(conn, WEEK)
    assert text.startswith("## Capex brief — week ending 2026-09-25")
    assert "| grid | +0.70σ | rising | +0.20σ flat |" in text
    assert "- Aravalli Cables Limited → grid: “EHV cables and substation equipment”" in text
    assert "### Most material new facts" in text and "### S11 capex propagation" in text


def test_the_brief_names_each_change_once(conn: psycopg.Connection[Any]) -> None:
    """M5 review R1-F13: a new fact's note already says "new: …", so the brief doesn't print "new: new:"."""
    cid = company(conn, "us", "Voltara Grid Systems, Inc.", "VOLT", "0000999002")
    doc = document(conn, cid, "https://www.sec.gov/v2.htm", datetime(2026, 9, 22, tzinfo=UTC))
    fact(conn, cid, doc, "backlog", "backlog:total", D(80) * 10**9, "usd", date(2026, 9, 22))
    (fid,) = conn.execute("select id from facts where document_id = %s", (doc,)).fetchone() or (None,)
    conn.execute("insert into diffs (company_id, subject_key, new_fact_id, change_kind, computed_note) "
                 "values (%s, 'backlog:total', %s, 'new', 'new: $80.0B')", (cid, fid))  # fmt: skip
    text = capex.brief(conn, WEEK)
    assert "new: new:" not in text and "backlog `backlog:total` · new: $80.0B —" in text
