"""Repositories: idempotent writes, restatement rows, typed contracts (BRIEF §3, §4.1.4)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from pydantic import ValidationError

from pipeline.db import repo
from pipeline.db.models import (
    Company,
    CorpEvent,
    FundamentalsRow,
    InsiderEvent,
    PriceW,
    Score,
    SignalValue,
    WeightsVersion,
)
from pipeline.db.pit import as_of

from .conftest import new_company

FILED = datetime(2025, 2, 1, tzinfo=UTC)


def test_fundamentals_reingest_is_idempotent_and_restatement_adds_a_row(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    base = dict(
        company_id=cid, period_end=date(2024, 12, 31), fiscal_label="FY2024Q4", currency="USD", source="sec_xbrl"
    )
    repo.insert_fundamentals(conn, [FundamentalsRow(**base, filed_at=FILED, revenue=Decimal(10))])  # type: ignore[arg-type]
    repo.insert_fundamentals(conn, [FundamentalsRow(**base, filed_at=FILED, revenue=Decimal(10))])  # type: ignore[arg-type]
    restated = datetime(2025, 6, 1, tzinfo=UTC)
    repo.insert_fundamentals(conn, [FundamentalsRow(**base, filed_at=restated, revenue=Decimal(11))])  # type: ignore[arg-type]
    versions = conn.execute("select count(*) from fundamentals_display_v where company_id = %s", (cid,)).fetchone()
    assert versions == (1,)  # the display view shows the latest version only
    assert [r.revenue for r in as_of(date(2025, 3, 7)).fundamentals(conn, [cid])] == [Decimal(10)]
    assert [r.revenue for r in as_of(date(2025, 6, 6)).fundamentals(conn, [cid])] == [Decimal(11)]


def test_events_are_deduplicated(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    ev = InsiderEvent(
        company_id=cid,
        event_date=date(2025, 1, 10),
        filed_at=FILED,
        person="X",
        kind="open_market_buy",
        source_url="https://www.sec.gov/f4",
    )
    ce = CorpEvent(company_id=cid, event_date=date(2025, 1, 10), filed_at=FILED, kind="late_filing", source_url="u")
    for _ in range(2):
        repo.insert_insider_events(conn, [ev])  # shares is null: NULLS NOT DISTINCT still dedupes
        repo.insert_corp_events(conn, [ce])
    snap = as_of(date(2025, 2, 7))
    assert len(snap.insider_events(conn, [cid])) == 1
    assert len(snap.corp_events(conn, [cid])) == 1


def test_weekly_outputs_upsert(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    wk = date(2025, 3, 28)
    for strength in ("0.4", "0.6"):
        repo.upsert_signal_values(
            conn,
            [
                SignalValue(
                    company_id=cid, week_end=wk, signal_id="S3", fired=True, strength=Decimal(strength), inputs={"q": 1}
                )
            ],
        )
    repo.upsert_scores(
        conn,
        [
            Score(
                company_id=cid,
                week_end=wk,
                evidence=Decimal(62),
                families=["fundamentals", "behavior"],
                bucket="none",
                weights_version="w0-equal",
            )
        ],
    )
    repo.upsert_prices(conn, [PriceW(company_id=cid, week_end=wk, close=Decimal("101.5"), source="stooq")])
    assert conn.execute("select strength, inputs from signal_values where company_id = %s", (cid,)).fetchall() == [
        (Decimal("0.6"), {"q": 1})
    ]
    assert conn.execute("select families from scores where company_id = %s", (cid,)).fetchone() == (
        ["fundamentals", "behavior"],
    )


def test_contracts_reject_bad_rows() -> None:
    with pytest.raises(ValidationError):
        SignalValue(
            company_id=new_uuid(),
            week_end=date(2025, 1, 3),
            signal_id="S1",
            fired=True,
            strength=Decimal("1.2"),
            inputs={},
        )
    with pytest.raises(ValidationError):  # naive filed_at would make as_of() ambiguous
        FundamentalsRow(
            company_id=new_uuid(),
            period_end=date(2024, 12, 31),
            fiscal_label="x",
            filed_at=datetime(2025, 1, 1),
            currency="USD",
            source="sec_xbrl",
        )
    with pytest.raises(ValidationError):
        Company(market="uk", name="x")  # type: ignore[arg-type]


def test_weights_versions_are_immutable(conn: psycopg.Connection[Any]) -> None:
    w = WeightsVersion(version="t-1", weights={"S1": 1.0}, reason="test")
    assert repo.insert_weights_version(conn, w)
    assert not repo.insert_weights_version(conn, w.model_copy(update={"weights": {"S1": 9.0}}))
    assert conn.execute("select weights from weights_versions where version = 't-1'").fetchone() == ({"S1": 1.0},)


def test_india_symbol_rename_keeps_company(conn: psycopg.Connection[Any]) -> None:
    repo.upsert_in_companies(
        conn, [Company(market="in", name="Old Name Ltd", nse_symbol="OLDSYM", isin="INE000T01011")]
    )
    (cid,) = conn.execute("select id from companies where isin = 'INE000T01011'").fetchone() or (None,)
    repo.upsert_in_companies(
        conn, [Company(market="in", name="New Name Ltd", nse_symbol="NEWSYM", isin="INE000T01011")]
    )
    assert conn.execute("select id, nse_symbol, name from companies where isin = 'INE000T01011'").fetchall() == [
        (cid, "NEWSYM", "New Name Ltd")
    ]


def test_source_health_and_runs(conn: psycopg.Connection[Any]) -> None:
    repo.ensure_sources(conn, ["t_src"])
    repo.mark_source_error(conn, "t_src", "403 x3", stale=True)
    assert [h.stale for h in repo.source_health(conn) if h.source == "t_src"] == [True]
    repo.mark_source_success(conn, "t_src")
    assert [(h.stale, h.last_error) for h in repo.source_health(conn) if h.source == "t_src"] == [(False, None)]
    run = repo.start_run(conn, "weekly")
    repo.finish_run(conn, run, "ok", {"rows": 3})
    assert conn.execute("select status, stats from runs where id = %s", (run,)).fetchone() == ("ok", {"rows": 3})


def new_uuid() -> Any:
    import uuid

    return uuid.uuid4()
