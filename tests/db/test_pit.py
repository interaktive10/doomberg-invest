"""M1-02: rows filed after W are invisible to as_of(W); the tests try to cheat (BRIEF §3, §8 M1)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from pipeline.db import repo
from pipeline.db.models import CorpEvent, FundamentalsRow, InsiderEvent, OwnershipRow
from pipeline.db.pit import AsOf, as_of, cutoff_for, select_as_of

from .conftest import new_company

W = date(2025, 3, 28)  # a Friday week end
END_OF_W = datetime(2025, 3, 28, 23, 59, 59, 999999, tzinfo=UTC)
AFTER_W = datetime(2025, 3, 29, 0, 0, 0, tzinfo=UTC)


def fq(cid: UUID, period_end: date, filed_at: datetime, revenue: str) -> FundamentalsRow:
    return FundamentalsRow(
        company_id=cid,
        period_end=period_end,
        fiscal_label="Q",
        filed_at=filed_at,
        revenue=Decimal(revenue),
        currency="USD",
        source="sec_xbrl",
    )


def test_cutoff_rules() -> None:
    assert cutoff_for(W) == AFTER_W
    t = datetime(2025, 3, 28, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert cutoff_for(t) == datetime(2025, 3, 28, 6, 30, 0, 1, tzinfo=UTC)


@pytest.mark.parametrize("bad", ["2025-03-28", 20250328, None, datetime(2025, 3, 28, 12, 0)])
def test_rejects_ambiguous_or_wrong_types(bad: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        as_of(bad)


def test_cutoff_cannot_be_moved_after_construction() -> None:
    snap = as_of(W)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.cutoff = datetime(2100, 1, 1, tzinfo=UTC)  # type: ignore[misc]
    with pytest.raises(ValueError):
        AsOf(datetime(2100, 1, 1))  # naive cutoff


def test_fundamentals_hide_rows_filed_after_w(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    repo.insert_fundamentals(
        conn,
        [
            fq(cid, date(2024, 12, 31), datetime(2025, 2, 20, 21, 0, tzinfo=UTC), "100"),  # visible
            fq(cid, date(2024, 12, 31), END_OF_W, "101"),  # restatement filed the last microsecond of W: visible
            fq(cid, date(2024, 12, 31), AFTER_W, "999"),  # restatement filed after W: invisible
            fq(cid, date(2025, 3, 31), datetime(2025, 5, 1, tzinfo=UTC), "555"),  # next quarter, filed later
        ],
    )
    rows = as_of(W).fundamentals(conn, [cid])
    assert [(r.period_end, r.revenue) for r in rows] == [(date(2024, 12, 31), Decimal("101"))]
    later = as_of(date(2025, 5, 2)).fundamentals(conn, [cid])
    assert [(r.period_end, r.revenue) for r in later] == [
        (date(2024, 12, 31), Decimal("999")),
        (date(2025, 3, 31), Decimal("555")),
    ]


def test_restatement_returns_right_version_at_each_date(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    q = date(2023, 12, 31)
    repo.insert_fundamentals(
        conn,
        [
            fq(cid, q, datetime(2024, 2, 1, tzinfo=UTC), "10"),
            fq(cid, q, datetime(2024, 8, 1, tzinfo=UTC), "12"),
        ],
    )
    assert [r.revenue for r in as_of(date(2024, 1, 26)).fundamentals(conn, [cid])] == []
    assert [r.revenue for r in as_of(date(2024, 6, 7)).fundamentals(conn, [cid])] == [Decimal("10")]
    assert [r.revenue for r in as_of(date(2024, 8, 2)).fundamentals(conn, [cid])] == [Decimal("12")]


def test_all_companies_when_no_filter(conn: psycopg.Connection[Any]) -> None:
    a, b = new_company(conn), new_company(conn)
    repo.insert_fundamentals(
        conn,
        [fq(a, date(2024, 12, 31), datetime(2025, 2, 1, tzinfo=UTC), "1"), fq(b, date(2024, 12, 31), AFTER_W, "2")],
    )
    seen = {r.company_id for r in as_of(W).fundamentals(conn)}
    assert a in seen and b not in seen


def test_company_filter_is_bound_not_spliced(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(ValueError):
        as_of(W).fundamentals(conn, ["00000000-0000-0000-0000-000000000000') or true --"])  # type: ignore[list-item]


def test_ownership_hidden_until_filed(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    repo.upsert_ownership(
        conn,
        [
            OwnershipRow(
                company_id=cid,
                quarter_end=date(2024, 12, 31),
                filed_at=datetime(2025, 2, 14, tzinfo=UTC),
                inst_holders=120,
                source="sec_13f",
            ),
            OwnershipRow(
                company_id=cid, quarter_end=date(2025, 3, 31), filed_at=AFTER_W, inst_holders=150, source="sec_13f"
            ),
        ],
    )
    assert [r.inst_holders for r in as_of(W).ownership(conn, [cid])] == [120]


def test_ownership_revision_never_leaks_backwards(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    q = date(2024, 12, 31)
    first = OwnershipRow(
        company_id=cid, quarter_end=q, filed_at=datetime(2025, 2, 14, tzinfo=UTC), inst_holders=120, source="s"
    )
    revised = OwnershipRow(company_id=cid, quarter_end=q, filed_at=AFTER_W, inst_holders=130, source="s")
    repo.upsert_ownership(conn, [first])
    repo.upsert_ownership(conn, [revised])
    assert [r.inst_holders for r in as_of(W).ownership(conn, [cid])] == []  # a gap, never the revised value
    assert [r.inst_holders for r in as_of(date(2025, 4, 4)).ownership(conn, [cid])] == [130]
    repo.upsert_ownership(conn, [first])  # an older filing arriving late never replaces a newer one
    assert [r.inst_holders for r in as_of(date(2025, 4, 4)).ownership(conn, [cid])] == [130]


def test_insider_and_corp_events_hidden_until_filed(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)
    # The trade happened inside W but the Form 4 was filed after W: invisible at W (event_date is not availability).
    repo.insert_insider_events(
        conn,
        [
            InsiderEvent(
                company_id=cid,
                event_date=date(2025, 3, 27),
                filed_at=AFTER_W,
                person="A. Director",
                kind="open_market_buy",
                shares=Decimal(1000),
                value=Decimal(50000),
                source_url="https://www.sec.gov/x",
            ),
            InsiderEvent(
                company_id=cid,
                event_date=date(2025, 3, 20),
                filed_at=datetime(2025, 3, 21, tzinfo=UTC),
                person="B. Officer",
                kind="open_market_buy",
                shares=Decimal(500),
                source_url="https://www.sec.gov/y",
            ),
        ],
    )
    repo.insert_corp_events(
        conn,
        [
            CorpEvent(
                company_id=cid,
                event_date=date(2025, 3, 26),
                filed_at=AFTER_W,
                kind="auditor_change",
                source_url="https://www.sec.gov/8k",
            )
        ],
    )
    snap = as_of(W)
    assert [e.person for e in snap.insider_events(conn, [cid])] == ["B. Officer"]
    assert snap.corp_events(conn, [cid]) == []
    assert [e.kind for e in as_of(date(2025, 4, 4)).corp_events(conn, [cid])] == ["auditor_change"]
    assert [e.person for e in snap.insider_events(conn, [cid], since=date(2025, 3, 21))] == []


def test_select_as_of_matches_sql_rule() -> None:
    rows = [("q4", datetime(2025, 2, 1, tzinfo=UTC), 1), ("q4", END_OF_W, 2), ("q4", AFTER_W, 3)]
    got = select_as_of(rows, cutoff_for(W), key=lambda r: r[0], filed_at=lambda r: r[1])
    assert [r[2] for r in got] == [2]


def test_fundamental_versions_keep_every_version_before_the_cutoff(conn: psycopg.Connection[Any]) -> None:
    """M4 (C1's point-in-time history): all versions filed before W, none after; select_as_of picks per week."""
    cid = new_company(conn)
    q = date(2024, 12, 31)
    repo.insert_fundamentals(conn, [fq(cid, q, datetime(2025, 2, 1, tzinfo=UTC), "100"),
                                    fq(cid, q, datetime(2025, 3, 10, tzinfo=UTC), "110"),
                                    fq(cid, q, AFTER_W, "999")])  # fmt: skip
    rows = as_of(W).fundamental_versions(conn, [cid])
    assert [r.revenue for r in rows] == [Decimal(100), Decimal(110)]
    early = select_as_of(rows, cutoff_for(date(2025, 3, 7)), lambda r: r.period_end, lambda r: r.filed_at)
    assert [r.revenue for r in early] == [Decimal(100)]


def test_facts_need_a_published_document_and_verification(conn: psycopg.Connection[Any]) -> None:
    cid = new_company(conn)

    def doc(url: str, published: datetime) -> UUID:
        row = conn.execute(
            "insert into documents (company_id, kind, url, published_at, sha256, raw_path) "
            "values (%s, 'press_release', %s, %s, 'x', 'x') returning id",
            (cid, url, published),
        ).fetchone()
        assert row is not None
        return UUID(str(row[0]))

    def fact(document: UUID, key: str, status: str) -> None:
        conn.execute(
            "insert into facts (company_id, document_id, fact_type, subject, subject_key, unit, as_of, quote, "
            "char_start, char_end, extraction_model, confidence, verification_status) "
            "values (%s, %s, 'order_win', 'grid order', %s, 'usd', %s, 'a quoted sentence', 0, 17, 'm', 0.9, %s)",
            (cid, document, key, date(2025, 3, 1), status),
        )

    before, after = doc("https://example.org/a", END_OF_W), doc("https://example.org/b", AFTER_W)
    fact(before, "order:a", "verified")
    fact(before, "order:b", "needs_review")
    fact(after, "order:c", "verified")
    assert [f.subject_key for f in as_of(W).facts(conn, [cid])] == ["order:a"]
    assert {f.subject_key for f in as_of(W + timedelta(days=1)).facts(conn, [cid])} == {"order:a", "order:c"}
