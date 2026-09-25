"""US events from real EDGAR daily indexes and submissions (BRIEF §4.2, §8 M2-04): 8-K 4.01 -> auditor_change,
NT 10-K/10-Q -> late_filing, capex-desk 8-K items 1.01/2.03 queued for text extraction, Form 4 selection."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from pipeline.us.events import IndexRow, filing_events, master_index_url, parse_master_index, select
from pipeline.us.submissions import Submissions, parse_submissions

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "us"
GERON, QUIDEL, MRC, IRWD, ADMA = "0000886744", "0001906324", "0001439095", "0001446847", "0001368514"
UNIVERSE = {GERON, QUIDEL, MRC, IRWD, ADMA}


def index(day: str) -> list[IndexRow]:
    return parse_master_index((FIX / "events" / f"master.{day}.idx").read_text(encoding="latin-1"))


def subs(cik: str, folder: str = "events") -> Submissions:
    return parse_submissions(json.loads((FIX / folder / f"CIK{cik}.json").read_text(encoding="utf-8")))


def test_master_index_parsing_and_url() -> None:
    rows = index("20250303")
    assert len(rows) == 33 and all(len(r.cik) == 10 for r in rows)
    geron = [r for r in rows if r.cik == GERON]
    assert [(r.form, r.date_filed) for r in geron] == [("4", date(2025, 3, 3))] * 3
    assert geron[0].url == "https://www.sec.gov/Archives/edgar/data/886744/0000950170-25-030327.txt"
    assert master_index_url(date(2025, 3, 3)) == (
        "https://www.sec.gov/Archives/edgar/daily-index/2025/QTR1/master.20250303.idx"
    )
    assert master_index_url(date(2025, 10, 1)).endswith("/2025/QTR4/master.20251001.idx")


def test_selection_keeps_universe_filings_once() -> None:
    rows = index("20250303")
    owner_copy = IndexRow(
        "0001270928", "SCARLETT JOHN A", "4", date(2025, 3, 3), "edgar/data/1270928/0000950170-25-030329.txt"
    )  # fmt: skip  (the same Form 4 filed under the owner's CIK)
    sel = select([*rows, owner_copy], UNIVERSE)
    assert [r.accession for r in sel.form4] == ["0000950170-25-030327", "0000950170-25-030329", "0000950170-25-030330"]
    assert sel.need_submissions == {ADMA, MRC, IRWD}  # 8-K / NT filers; the noise rows are not in the universe
    assert select(rows, set()).form4 == []
    form10 = IndexRow("0009999902", "NEWCO SPINCO INC", "10-12B", date(2025, 3, 3), "edgar/data/9999902/x.txt")
    assert select([form10], set()).need_submissions == set()  # tracked as a pending registration by the daily run


def test_auditor_change_and_late_filings_from_todays_filings() -> None:
    today = {r.accession for r in index("20250304") if r.cik == QUIDEL}
    events, texts = filing_events(subs(QUIDEL), today)
    assert [(e.kind, e.event_date, e.filed_at) for e in events] == [
        ("auditor_change", date(2025, 3, 4), datetime(2025, 3, 4, 21, 15, 31, tzinfo=UTC))
    ]
    assert events[0].detail["items"] == ["4.01", "9.01"] and texts == []
    late = []
    day1 = index("20250303")
    for cik in (ADMA, MRC, IRWD):
        evs, _ = filing_events(subs(cik), {r.accession for r in day1 if r.cik == cik})
        late += [(e.cik, e.kind, e.detail["form"]) for e in evs]
    assert late == [(ADMA, "late_filing", "NT 10-K"), (MRC, "late_filing", "NT 10-K"), (IRWD, "late_filing", "NT 10-K")]


def test_history_mode_finds_every_event() -> None:
    kinds = [(e.kind, e.event_date) for e in filing_events(subs(ADMA))[0]]
    assert kinds == [("auditor_change", date(2024, 10, 9)), ("auditor_change", date(2024, 10, 31)),
                     ("late_filing", date(2025, 3, 3))]  # fmt: skip


def test_capex_desk_8k_items_are_queued_for_text() -> None:
    gev = subs("0001996810", folder="submissions")
    _, texts = filing_events(gev, {"0001193125-24-084048"}, capex_desk=True)  # 2024-04-02: 1.01, 2.03, ...
    assert [(t.accession, t.form, t.period_of_report) for t in texts] == [
        ("0001193125-24-084048", "8-K", date(2024, 3, 27))  # period = earliest event
    ]
    t = texts[0]
    assert {"1.01", "2.03"} <= set(t.items)
    assert t.primary_doc_url == "https://www.sec.gov/Archives/edgar/data/1996810/000119312524084048/d807682d8k.htm"
    assert t.accepted_at == datetime(2024, 4, 2, 10, 58, 4, tzinfo=UTC)
    assert filing_events(gev, {"0001193125-24-084048"}, capex_desk=False) == ([], [])


def test_published_days_and_catch_up_planning() -> None:
    """Review F2: the daily run reads the quarter's listing and processes every published day it hasn't done."""
    from pipeline.us.events import days_to_process, published_days, quarter_listing_url, quarters_between

    listing = json.loads((FIX / "events" / "daily-index-2025-QTR1.json").read_text(encoding="utf-8"))
    days = published_days(listing)
    assert days == [date(2025, 2, 28), date(2025, 3, 3), date(2025, 3, 4)]  # company/form/crawler/sitemap ignored
    assert days_to_process(days, None) == days  # a first run takes the latest three
    assert days_to_process(days, date(2025, 3, 3)) == [date(2025, 3, 4)]
    assert days_to_process(days, date(2025, 3, 4)) == []  # 03-05 isn't published yet: nothing is skipped for good
    assert quarter_listing_url(date(2025, 3, 4)).endswith("/daily-index/2025/QTR1/index.json")
    assert quarters_between(date(2024, 12, 30), date(2025, 1, 2)) == [date(2024, 10, 1), date(2025, 1, 1)]
    assert quarters_between(date(2025, 2, 1), date(2025, 3, 4)) == [date(2025, 1, 1)]


def test_item_2_01_is_an_acquisition_event() -> None:
    """M4 (R4 "share count +10% without an acquisition"): 8-K item 2.01 becomes corp_events(kind='acquisition')."""
    evs = [(e.kind, e.event_date, e.detail["items"]) for e in filing_events(subs(MRC))[0] if e.kind == "acquisition"]
    items = ["1.01", "1.02", "2.01", "2.03", "5.02", "5.03", "7.01", "9.01"]
    assert evs == [("acquisition", date(2024, 10, 31), items)]
