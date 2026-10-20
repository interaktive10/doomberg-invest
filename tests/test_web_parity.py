"""M7: the web app ports a few pipeline rules to TypeScript. Their shared fixtures are checked here against the
Python, and in web/tests against the port, so the two can't drift apart."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml

from pipeline.thesis.evidence_pack import next_filing

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


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


def test_staleness_rows_are_the_digests_and_india_is_paused() -> None:
    """web/lib/staleness.ts lists config/staleness.yaml's SLAs and fallbacks (the digest's; web/tests/staleness.test.ts
    checks the same from the web side), and neither has India's nse/bse rows while India is paused (overhaul PR 1,
    docs/SPEC_ISSUES.md 46)."""
    doc = yaml.safe_load((ROOT / "config" / "staleness.yaml").read_text(encoding="utf-8"))
    ts = (WEB / "lib" / "staleness.ts").read_text(encoding="utf-8")
    sla = re.search(r"SLA_DAYS: Record<string, number> = \{(.*?)\};", ts, re.S)
    fallback = re.search(r"FALLBACK_OF: Record<string, string> = \{(.*?)\};", ts, re.S)
    assert sla is not None and fallback is not None
    fallbacks = doc["fallback_of"] or {}
    assert {k: int(v) for k, v in re.findall(r"(\w+): (\d+),", sla.group(1))} == doc["sla_days"]
    assert dict(re.findall(r'(\w+): "(\w+)"', fallback.group(1))) == fallbacks
    assert not {"nse", "bse"} & (set(doc["sla_days"]) | set(fallbacks) | set(fallbacks.values()))
