"""M7: the web app ports a few pipeline rules to TypeScript. Their shared fixtures are checked here against the
Python, and in web/tests against the port, so the two can't drift apart."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pipeline.thesis.evidence_pack import next_filing

WEB = Path(__file__).resolve().parents[1] / "web"


def test_next_filing_fixture_is_the_pipelines_answer() -> None:
    """M7 review R1-F3: web/lib/filing.ts moves a thesis's next review date with evidence_pack.next_filing's rule."""
    cases = json.loads((WEB / "tests" / "fixtures" / "next_filing.json").read_text(encoding="utf-8"))
    assert len(cases) > 5
    for c in cases:
        latest = date.fromisoformat(c["latest_end"]) if c["latest_end"] else None
        w = next_filing(c["market"], c["fye"], latest, date.fromisoformat(c["today"]))
        got = None if w is None else {"period_end": w.period_end.isoformat(), "form": w.form,
                                      "opens": w.opens.isoformat(), "closes": w.closes.isoformat()}  # fmt: skip
        assert got == c["expected"], c
