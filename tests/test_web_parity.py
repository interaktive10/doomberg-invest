"""M7: the web app ports a few pipeline rules to TypeScript. Their shared fixtures are checked here against the
Python, and in web/tests against the port, so the two can't drift apart."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from pipeline.thesis.evidence_pack import KILL_METRICS, next_filing

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
    docs/SPEC_ISSUES.md 46). They are the US sources the pipeline still reads: the dead ones (yahoo, stooq, fred, eia,
    gdelt) are gone, so Home's banner and Settings never name them (overhaul PR 4)."""
    doc = yaml.safe_load((ROOT / "config" / "staleness.yaml").read_text(encoding="utf-8"))
    ts = (WEB / "lib" / "staleness.ts").read_text(encoding="utf-8")
    sla = re.search(r"SLA_DAYS: Record<string, number> = \{(.*?)\};", ts, re.S)
    fallback = re.search(r"FALLBACK_OF: Record<string, string> = \{(.*?)\};", ts, re.S)
    assert sla is not None and fallback is not None
    fallbacks = doc["fallback_of"] or {}
    assert {k: int(v) for k, v in re.findall(r"(\w+): (\d+),", sla.group(1))} == doc["sla_days"]
    assert dict(re.findall(r'(\w+): "(\w+)"', fallback.group(1))) == fallbacks
    assert not {"nse", "bse"} & (set(doc["sla_days"]) | set(fallbacks) | set(fallbacks.values()))
    assert set(doc["sla_days"]) == {"sec", "twelvedata", "sec_13f"}


def test_a_paused_indias_rows_read_alike_in_the_digest_and_raise_no_banner() -> None:
    """Overhaul PR 1 review (pipeline-F2): production's bse row has never succeeded (BSE records a success only in a
    week it stood in for NSE), so without its fallback row the digest's table reads "never succeeded", as
    web/tests/staleness.test.ts does for Settings, and nse keeps its last success with no SLA; the stale banner names
    neither (docs/SPEC_ISSUES.md 46)."""
    from pipeline.db.models import SourceHealth
    from pipeline.digest import weekly as digest

    now = datetime(2026, 9, 19, 3, tzinfo=UTC)
    rows = [SourceHealth(source="bse"), SourceHealth(source="nse", last_success=datetime(2026, 9, 12, 6, tzinfo=UTC))]
    sla, fallbacks = digest.sla_days(), digest.fallbacks()
    assert digest.banner(rows, now, sla, fallbacks) == []
    assert digest.health(rows, now, sla, fallbacks)[2:] == ["| bse | never | never succeeded |",
                                                            "| nse | 2026-09-12 06:00Z | ok |"]  # fmt: skip


def _ts_keys(text: str, name: str) -> list[str]:
    block = re.search(rf"export const {name}[^=]*= \{{(.*?)\n\}};", text, re.S)
    assert block is not None, name
    return re.findall(r"^  (\w+): ", block.group(1), re.M)


def test_kill_criteria_words_cover_every_kill_metric() -> None:
    """Overhaul PR 4: the Thesis page reads each kill criterion in words (web/lib/labels.ts METRIC_LABEL and
    killSentence; web/tests/labels.test.ts words every entry), one entry per evidence_pack.KILL_METRICS metric."""
    labels = (WEB / "lib" / "labels.ts").read_text(encoding="utf-8")
    assert _ts_keys(labels, "METRIC_LABEL") == list(KILL_METRICS)


def test_the_lab_pages_verdict_reads_the_labs_rule() -> None:
    """Overhaul PR 4: web/lib/lab.ts verdict is pipeline/lab/proposals.py's (BRIEF §4.10.5) at config/lab.yaml's
    proposal horizon with config/weights.yaml's lab_rules t thresholds, and its 'not testable yet' signals are
    config/lab.yaml's not_testable (S11 is gone from the app)."""
    lab = (WEB / "lib" / "lab.ts").read_text(encoding="utf-8")
    cfg = yaml.safe_load((ROOT / "config" / "lab.yaml").read_text(encoding="utf-8"))
    rules = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))["lab_rules"]

    def const(name: str) -> str:
        m = re.search(rf"export const {name} = ([^;]+);", lab)
        assert m is not None, name
        return m.group(1)

    assert int(const("PROPOSAL_HORIZON_MONTHS")) == cfg["proposal_horizon_months"]
    assert float(const("PROMOTE_MIN_T_NW")) == float(rules["promote_min_t_nw"])
    assert float(const("DEMOTE_MAX_T_NW")) == float(rules["demote_max_t_nw"])
    assert re.findall(r'"(S\d+)"', const("NOT_TESTABLE")) == [s for s in cfg["not_testable"] if s != "S11"]
