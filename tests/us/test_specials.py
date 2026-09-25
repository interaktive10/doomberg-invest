"""Spin-offs (BRIEF §4.2): GE Vernova's Form 10 became effective with the 2024-04-02 separation 8-K; the parent is
proposed from names in the Form 10 and left unconfirmed."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from pipeline.us.specials import effective_spinoff, html_to_text, parent_candidates
from pipeline.us.submissions import parse_submissions

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "us"
ROOT = FIX.parents[1]


def gev():
    return parse_submissions(json.loads((FIX / "submissions" / "CIK0001996810.json").read_text(encoding="utf-8")))


def universe_names() -> dict[str, str]:
    snap = json.loads((ROOT / "data" / "universe" / "us_tickers_exchange.json").read_text(encoding="utf-8"))
    i, n = snap["fields"].index("cik"), snap["fields"].index("name")
    return {str(r[i]).zfill(10): r[n] for r in snap["data"]}


def test_gev_is_effective_at_the_separation_8k() -> None:
    spin = effective_spinoff(gev())
    assert spin is not None
    assert (spin.evidence, spin.event_date, spin.filed_at) == (
        "8-K 5.01/3.03", date(2024, 4, 2), datetime(2024, 4, 2, 10, 58, 4, tzinfo=UTC))  # fmt: skip
    assert spin.form10_accession == "0001193125-24-059354"  # the latest Form 10 amendment holds the final text
    assert spin.form10_doc_url.endswith("/000119312524059354/d542465d1012ba.htm")


def test_other_evidence_and_no_form10() -> None:
    s = gev()
    no_8k = replace(s, filings=tuple(f for f in s.filings if f.form != "8-K"))
    spin = effective_spinoff(no_8k)  # GEV's only EFFECT notice is for an S-1 (2024-05-23): not evidence
    assert spin is not None and (spin.evidence, spin.event_date) == ("first periodic report", date(2024, 4, 30))
    form10 = next(f for f in s.filings if f.form == "10-12B/A")
    effect = replace(
        form10,
        accession="0009999999-24-000001",
        form="EFFECT",
        filing_date=date(2024, 3, 20),
        accepted_at=datetime(2024, 3, 21, 4, 15, tzinfo=UTC),
        items=("10-12B", "", "2024-03-20"),
    )
    spin = effective_spinoff(replace(no_8k, filings=(*no_8k.filings, effect)))
    assert spin is not None and (spin.evidence, spin.event_date) == ("EFFECT", date(2024, 3, 20))
    pending = replace(s, filings=tuple(f for f in s.filings if f.form.startswith("10-12B")))
    assert effective_spinoff(pending) is None  # registered, not yet effective
    assert effective_spinoff(replace(s, filings=())) is None


def test_parent_candidate_is_general_electric() -> None:
    text = html_to_text((FIX / "events" / "gev_form10.htm").read_text(encoding="utf-8", errors="replace"))
    cands = parent_candidates(text, universe_names(), exclude_cik="0001996810")
    assert cands and cands[0]["cik"] == "0000040545" and cands[0]["name"] == "GENERAL ELECTRIC CO"
    assert all(c["cik"] != "0001996810" for c in cands)  # never the registrant itself


def test_parent_candidates_need_two_mentions_and_two_words() -> None:
    names = {"1": "Acme Widgets Inc", "2": "Apple Inc", "3": "Other Holdings Corp"}
    text = "Acme Widgets, Inc. will distribute ... Apple Apple Apple ... Acme Widgets and Other Holdings"
    assert parent_candidates(text, names) == [{"cik": "1", "name": "Acme Widgets Inc", "mentions": 2}]
    assert html_to_text("<p>A&amp;B<script>x()</script> <b>Corp</b></p>") == "A&B Corp"
