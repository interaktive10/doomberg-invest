"""Regression (weekly run 2026-10-08): a body PDFium can't open (an annual report that wasn't a PDF stopped the old
Capex Desk job with PDFium's "Data format error") is a PdfUnreadable (a ValueError), which the text run's readers
record and skip."""

from __future__ import annotations

import pytest

from pipeline.facts.pdf_text import PdfUnreadable, page_texts

NOT_A_PDF = b"<html><body>Service unavailable</body></html>"


def test_a_body_pdfium_cant_open_is_a_value_error() -> None:
    with pytest.raises(PdfUnreadable):
        page_texts(NOT_A_PDF)
    assert issubclass(PdfUnreadable, ValueError)
