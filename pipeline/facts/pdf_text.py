"""PDF -> canonical text with page_map (Appendix F.3): pypdfium2 text per page; pages joined as paragraphs."""

from __future__ import annotations

from pipeline.facts.canonical import join_blocks
from pipeline.facts.html_text import Normalized

MAX_PAGES = 400  # annual reports run to 300+ pages; anything longer is cut (logged by the caller)


def page_texts(data: bytes, max_pages: int = MAX_PAGES) -> list[str]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        out = []
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            tp = page.get_textpage()
            try:
                out.append(tp.get_text_range())
            finally:
                tp.close()
                page.close()
        return out
    finally:
        pdf.close()


def normalize_pages(pages: list[str]) -> Normalized:
    text, spans = join_blocks(pages)
    page_map = [{"page": i + 1, "char_start": s, "char_end": e} for i, (s, e) in enumerate(spans)]
    return Normalized(text, [], page_map)


def normalize_pdf(data: bytes) -> Normalized:
    return normalize_pages(page_texts(data))


def page_of(page_map: list[dict[str, int]], offset: int) -> int | None:
    for p in page_map:
        if p["char_start"] <= offset < p["char_end"] or p["char_start"] == offset == p["char_end"]:
            return p["page"]
    return None
