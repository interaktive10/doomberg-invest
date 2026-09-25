"""Canonical text, HTML/PDF normalization, section maps, chunking, the prefilter and grounding (Appendix F.3-F.4)."""

from __future__ import annotations

from pipeline.facts.canonical import canonical, join_blocks
from pipeline.facts.chunk import prefilter, score, select, split
from pipeline.facts.ground import ground, grounded_quote
from pipeline.facts.html_text import normalize_html
from pipeline.facts.pdf_text import normalize_pages, page_of

TEN_Q = """<html><head><title>t</title><style>p { x }</style></head><body>
<div style="display: none"><ix:header>Hidden 999</ix:header></div>
<table><tr><td>Item 1A.</td><td>Risk Factors</td><td>31</td></tr></table>
<p>Item 1. Financial Statements</p>
<p><b>Note 4 — Leases</b></p><p>Leases not yet commenced total $2.1&nbsp;billion.</p>
<p>Note 5. Commitments and Contingencies</p><p>Purchase obligations were $3 billion.</p>
<p>Item 2. Management&#8217;s Discussion and Analysis of Financial Condition</p>
<p>Revenue</p><p>We expect   capital expenditures of<br/>approximately $75 billion.</p>
<table><tr><td>Backlog</td><td>$</td><td>1,234</td><td> </td></tr><tr><td>Total</td><td>9</td></tr></table>
<p>Item 1A. Risk Factors</p><p>Risks about data centers and AI demand.</p>
<p>Item 3. Quantitative Disclosures</p><p>None.</p><script>var x = "Item 7";</script></body></html>"""


def test_canonical_rules() -> None:
    raw = "  A  b\t c \r\n next  line \n\n\n\n Para​ two  Three"
    assert canonical(raw) == "A b c\nnext line\n\nPara two\n\nThree"
    assert canonical(canonical(raw)) == canonical(raw)
    text, spans = join_blocks(["one", "", " two  words "])
    assert text == "one\n\ntwo words" and spans == [(0, 3), (3, 3), (5, 14)]  # an empty block spans nothing


def test_html_drops_hidden_keeps_rows_and_maps_sections() -> None:
    n = normalize_html(TEN_Q)
    assert "Hidden 999" not in n.text and "var x" not in n.text and "p { x }" not in n.text
    assert "Backlog | $ | 1,234\nTotal | 9" in n.text  # table rows, empty cells dropped
    assert "We expect capital expenditures of\napproximately $75 billion." in n.text  # <br> is a line break
    names = {s["name"]: n.text[int(s["char_start"]) : int(s["char_end"])] for s in n.section_map}
    assert set(names) == {"financial_statements", "note_leases", "note_commitments", "mdna", "risk_factors"}
    assert names["mdna"].startswith("Item 2. Management’s Discussion") and "Revenue" in names["mdna"]
    assert names["note_leases"].startswith("Note 4 — Leases") and "$2.1 billion" in names["note_leases"]
    assert "Item 1A. | Risk Factors" not in names["risk_factors"]  # the table of contents isn't the section


def test_pdf_pages_and_page_map() -> None:
    n = normalize_pages(["Title line\r\nSecond  line", "", "Page three text"])
    assert n.text == "Title line\nSecond line\n\nPage three text"
    assert [p["page"] for p in n.page_map] == [1, 2, 3]
    assert page_of(n.page_map, n.text.index("Page three")) == 3


def test_chunks_cover_mdna_and_notes_but_not_risk_factors() -> None:
    n = normalize_html(TEN_Q)
    chunks = select("10-Q", n.text, n.section_map, n.page_map)
    sections = [c.section for c in chunks]
    assert sections == ["note_leases", "note_commitments", "mdna"]
    assert all(n.text[c.char_start : c.char_end] == c.text for c in chunks)
    plain = select("10-K", "Item 1. Business\n\nText.", [{"name": "risk_factors", "char_start": 0, "char_end": 5}], [])
    assert [c.text for c in plain] == ["1. Business\n\nText."]


def test_split_overlaps_and_cuts_at_paragraphs() -> None:
    text = "\n\n".join(f"Paragraph {i} " + "x" * 90 for i in range(30))
    chunks = split(text, 0, len(text), max_chars=1000, overlap=200)
    assert chunks[0].char_start == 0 and chunks[-1].char_end == len(text)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.char_start < a.char_end  # overlap
        assert text[a.char_end : a.char_end + 2] == "\n\n" or a.char_end == len(text)


def test_prefilter_scores_keywords_with_plurals_and_case() -> None:
    assert score("Data center leases, AI and two transformers; said, maid") == 4  # "AI" is case-sensitive
    assert score("ai data centre") == 1
    chunks = split("Our AI data center capacity grew.", 0, 33)
    assert prefilter(chunks) == chunks and prefilter(split("Nothing here.", 0, 13)) == []


def test_grounding_exact_then_insensitive_never_fuzzy() -> None:
    text = "Intro.\n\nWe expect capital expenditures of\napproximately $75 billion in fiscal 2027.\n\nEnd."
    q = "We expect capital expenditures of approximately $75 billion"
    s, e = ground(q, text) or (0, 0)
    assert text[s:e] == "We expect capital expenditures of\napproximately $75 billion"  # the line break is kept
    assert ground("“We expect capital expenditures of approximately $75 billion”", text) == (s, e)
    assert ground("We expect capital expenditures of approximately $76 billion", text) is None  # a digit differs
    assert ground("we expect capital expenditures", text) is None  # case matters
    assert ground("We expect capital", text, lo=20) is None  # outside the chunk
    assert grounded_quote("End", text) is None  # shorter than a storable quote
