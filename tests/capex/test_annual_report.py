"""India annual-report excerpts for P-06 (BRIEF §4.11): NSE's listing -> the latest report; its pages -> the
prefiltered excerpts P-06 reads."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pipeline.capex import annual_report as ar

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "in" / "annual_reports"


def test_the_latest_report_of_the_live_listing() -> None:
    r = ar.latest((FIX / "annual_reports_KEI.json").read_bytes())
    assert r is not None and r.url.endswith("AR_31533_KEI_2025_2026_A_10132962_05092026162231.pdf")
    assert r.published == datetime(2026, 9, 5, 10, 52, 32, tzinfo=UTC)  # 16:22:32 IST
    assert r.label == "Annual report 2025-26"


def test_rows_without_a_pdf_link_or_a_date_are_skipped() -> None:
    when = "05-SEP-2026 16:22:32"
    base = "https://nsearchives.nseindia.com/annual_reports"
    rows = [{"fileName": "http://example.org/a.pdf", "disseminationDateTime": when},
            {"fileName": f"{base}/a.zip", "disseminationDateTime": when}, {"fileName": f"{base}/a.pdf"}]  # fmt: skip
    assert ar.latest(json.dumps({"data": rows}).encode()) is None and ar.latest(b"[]") is None
    assert ar.listing_path("M&M") == "annual-reports?index=equities&symbol=M%26M"


def test_excerpts_keep_prefiltered_pages_in_page_order_within_the_limit() -> None:
    capex = "Our order book for power transformers and switchgear reached a record; data center cable demand rose."
    plain = "The board thanks the shareholders for their continued support."
    pages = [plain, capex, plain, capex + " Export orders grew.", capex]
    got = ar.excerpts(pages, "Annual report 2025-26", max_chars=2 * len(capex) + 25)
    assert [label for label, _ in got] == ["Annual report 2025-26, p. 2", "Annual report 2025-26, p. 4"]
    assert got[1][1] == capex + " Export orders grew."
