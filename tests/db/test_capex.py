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
from tests.db.test_facts_pipeline import router

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
    facts_repo.decide_membership(conn, cid, "grid", "confirmed")
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        facts_repo.decide_membership(conn, cid, "power_equipment", "rejected")  # a rejection needs a reason
    facts_repo.decide_membership(conn, cid, "power_equipment", "rejected", "cables, not transformers")
    assert not facts_repo.propose_membership(conn, cid, "grid", "p06", "{}", "a new quote")  # decided rows stay
    status = dict(conn.execute("select category, status from capex_memberships").fetchall())
    assert status == {"grid": "confirmed", "power_equipment": "rejected"}
    views = desk.load_views(conn, WEEK, repo.companies(conn))
    assert list(views[cid].categories) == ["grid"]


def test_s11_view_has_the_index_the_distance_and_export_exposure(conn: psycopg.Connection[Any]) -> None:
    msft = company(conn, "us", "MICROSOFT CORP", "MSFT", "0000789019", capex_desk=True)
    volt = company(conn, "us", "Voltara Grid Systems, Inc.", "VOLT", "0000999002")
    arvl = company(conn, "in", "Aravalli Cables Limited", "ARVL")
    for cid, cat in ((volt, "grid"), (arvl, "grid")):
        facts_repo.propose_membership(conn, cid, cat, "industry_map", "test")
        facts_repo.decide_membership(conn, cid, cat, "confirmed")
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
