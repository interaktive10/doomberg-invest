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


def test_staleness_rows_are_the_digests_with_india_back() -> None:
    """web/lib/staleness.ts lists config/staleness.yaml's SLAs and fallbacks (the digest's; web/tests/staleness.test.ts
    checks the same from the web side), India's nse and bse rows included again (docs/SPEC_ISSUES.md 55; paused in
    overhaul PR 1, 46). They are the sources the pipeline still reads: the dead ones (yahoo, stooq, fred, eia, gdelt)
    are gone, so Home's banner and Settings never name them (overhaul PR 4)."""
    doc = yaml.safe_load((ROOT / "config" / "staleness.yaml").read_text(encoding="utf-8"))
    ts = (WEB / "lib" / "staleness.ts").read_text(encoding="utf-8")
    sla = re.search(r"SLA_DAYS: Record<string, number> = \{(.*?)\};", ts, re.S)
    fallback = re.search(r"FALLBACK_OF: Record<string, string> = \{(.*?)\};", ts, re.S)
    assert sla is not None and fallback is not None
    fallbacks = doc["fallback_of"] or {}
    assert {k: int(v) for k, v in re.findall(r"(\w+): (\d+),", sla.group(1))} == doc["sla_days"]
    assert dict(re.findall(r'(\w+): "(\w+)"', fallback.group(1))) == fallbacks
    assert set(doc["sla_days"]) == {"sec", "twelvedata", "sec_13f", "nse", "bse"} and fallbacks == {"bse": "nse"}


def test_indias_rows_read_alike_in_the_digest_and_the_web() -> None:
    """Production's bse row has never succeeded (BSE records a success only in a week it stood in for NSE): with its
    fallback row it rests while NSE is on time and raises no banner; a late NSE is named (docs/SPEC_ISSUES.md 55; the
    web side is web/tests/staleness.test.ts)."""
    from pipeline.db.models import SourceHealth
    from pipeline.digest import weekly as digest

    now = datetime(2026, 9, 19, 3, tzinfo=UTC)
    rows = [SourceHealth(source="bse"), SourceHealth(source="nse", last_success=datetime(2026, 9, 12, 6, tzinfo=UTC))]
    sla, fallbacks = digest.sla_days(), digest.fallbacks()
    assert digest.banner(rows, now, sla, fallbacks) == []
    late = [SourceHealth(source="bse"), SourceHealth(source="nse", last_success=datetime(2026, 9, 1, 6, tzinfo=UTC))]
    assert digest.banner(late, now, sla, fallbacks) != []


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
    assert float(const("PROMOTE_WEIGHT")) == float(rules["promote_weight"])  # the top of the weight bars (PR 6)
    assert re.findall(r'"(S\d+)"', const("NOT_TESTABLE")) == [s for s in cfg["not_testable"] if s != "S11"]


def test_why_this_score_reads_the_scoring_rules() -> None:
    """Overhaul PR 5: web/lib/why.ts adds Evidence up by family as pipeline/signals/scores.py does, so its copies of
    config/signals.yaml `scores` (families, at most 2 signals a family, the divisor, the one-family cap and minimum,
    the soft-flag penalty, Gap's minimum) and Gap's metrics (config/context.yaml's C1-C3) are pinned here."""
    why = (WEB / "lib" / "why.ts").read_text(encoding="utf-8")
    cfg = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["scores"]
    context = yaml.safe_load((ROOT / "config" / "context.yaml").read_text(encoding="utf-8"))

    def const(name: str) -> str:
        m = re.search(rf"export const {name}(?:: [^=]+)? = ([^;]+);", why, re.S)
        assert m is not None, name
        return m.group(1)

    families = dict(re.findall(r"(\w+): \[([^\]]*)\]", const("FAMILIES")))
    assert {f: re.findall(r'"(S\d+)"', ids) for f, ids in families.items()} == cfg["families"]
    assert list(families) == list(cfg["families"])
    assert int(const("MAX_SIGNALS_PER_FAMILY")) == cfg["max_signals_per_family"]
    assert float(const("EVIDENCE_DIVISOR")) == float(cfg["evidence_divisor"])
    assert int(const("SINGLE_FAMILY_CAP")) == cfg["single_family_cap"]
    assert int(const("MIN_FAMILIES")) == cfg["min_families"]
    assert int(const("SOFT_FLAG_PENALTY")) == cfg["soft_flag_penalty"]
    assert int(const("GAP_MIN_METRICS")) == cfg["gap_min_metrics"]
    metrics = sorted({k.split("_")[0].upper() for k in context if re.fullmatch(r"c\d+(_\w+)?", k)})
    assert re.findall(r'"(C\d+)"', const("GAP_METRICS")) == metrics == ["C1", "C2", "C3"]
