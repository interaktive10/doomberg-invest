"""Regression (weekly run 2026-10-08): an annual report that isn't a PDF stopped the Capex Desk job with PDFium's
"Data format error"; it is a PdfUnreadable (a ValueError), which india_text records and skips."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest

from pipeline.capex import run
from pipeline.db.models import Company
from pipeline.facts.pdf_text import PdfUnreadable, page_texts

NOT_A_PDF = b"<html><body>Service unavailable</body></html>"


def test_a_body_pdfium_cant_open_is_a_value_error() -> None:
    with pytest.raises(PdfUnreadable):
        page_texts(NOT_A_PDF)
    assert issubclass(PdfUnreadable, ValueError)


def test_india_text_skips_an_unreadable_annual_report(monkeypatch: pytest.MonkeyPatch) -> None:
    class Nse:
        def api(self, path: str) -> Any:
            return {}

        def get(self, url: str) -> bytes:
            return NOT_A_PDF

    class Rep:
        published = datetime(2026, 6, 1, tzinfo=UTC)
        url = "https://nsearchives.nseindia.com/annual_reports/AR_X.pdf"
        label = "Annual report 2025-26"

    class NoEvents:
        def corp_events(self, *a: Any, **k: Any) -> list[Any]:
            return []

    monkeypatch.setattr(run, "as_of", lambda week: NoEvents())
    monkeypatch.setattr(run.annual_report, "listing_path", lambda symbol: "x")
    monkeypatch.setattr(run.annual_report, "latest", lambda doc: Rep())
    stats = run.CapexStats("2026-10-02")
    c = Company(id=uuid4(), market="in", name="X Ltd", nse_symbol="XLTD")
    assert run.india_text(None, Nse(), c, date(2026, 10, 2), stats) == []  # type: ignore[arg-type]
    assert stats.errors == ["annual report XLTD: PdfUnreadable"]
