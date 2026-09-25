"""M5-01 structure tests (no cassettes needed): the F-SYN corpus through normalize -> chunks -> prefilter -> P-01
(the oracle mock) -> Verify-1. Every planted fact is found with its expected status, nothing else is stored, and
each class of model mistake is rejected by the check that owns it. With cassettes, `python -m pipeline.facts.evaluate
--replay` scores the real models on the same corpus (M5-01's thresholds)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pipeline.facts.evaluate import SYN, load_truth, run_corpus, score
from pipeline.llm.router import Router
from tests.facts.oracle import Oracle
from tests.llm.conftest import FakeClock, quotas

GEN = Path(__file__).resolve().parents[2] / "scripts" / "make_synthetic.py"


@pytest.fixture(scope="module")
def truth() -> dict[str, object]:
    return load_truth()


def test_the_corpus_is_the_generators_output(truth: dict[str, object]) -> None:
    """F-SYN is 12 documents from scripts/make_synthetic.py (seed 7): 4 press releases, 4 10-Q-style HTML filings,
    2 risk-factor versions, 2 presentation PDFs; the committed files are exactly what the generator writes."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_synthetic", GEN)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_synthetic"] = mod  # dataclasses resolve their module while the file runs
    spec.loader.exec_module(mod)
    built = mod.build(7)
    assert sorted(built["docs"]) == sorted(
        p.name for p in SYN.iterdir() if p.name not in {"ground_truth.json", "README.md"}
    )
    for name, body in built["docs"].items():
        assert (SYN / name).read_bytes() == body, name
    kinds = sorted(d["kind"] for d in truth["documents"])  # type: ignore[index]
    assert kinds.count("10-Q") == 4 and kinds.count("presentation") == 2 and kinds.count("10-K") == 2
    assert kinds.count("EX-99.1") + kinds.count("press_release") == 4


def test_oracle_answers_are_all_found_and_nothing_else_is_stored(truth: dict[str, object]) -> None:
    oracle = Oracle(truth)  # type: ignore[arg-type]
    router = Router({"gemini": oracle}, quotas(["gemini"], rpd=10_000), FakeClock())
    outcomes = run_corpus(router, truth=truth)  # type: ignore[arg-type]
    report = score(outcomes, truth)  # type: ignore[arg-type]
    assert report.planted == 24 and report.misses == [] and report.extras == [], report.summary()
    assert report.recall == 1.0 and report.precision == 1.0
    rejected = sum((o.rejected for o in outcomes.values()), start=type(next(iter(outcomes.values())).rejected)())
    assert rejected["V1-TYPE"] >= 4 and rejected["V1-QUOTE"] >= 1 and rejected["V1-NUM"] >= 1
    assert rejected["V1-UNIT"] >= 1 and sum(o.duplicates for o in outcomes.values()) >= 1
    # risk factors aren't sent to P-01 (the risk diff reads them), and the non-USD order waits for review
    assert outcomes["kyst_10k_2025_risk.htm"].sent == 0
    arvl = [c for c, _ in outcomes["arvl_pr_order.htm"].facts if c.fact_type == "order_win"]
    assert [c.verification_status for c in arvl] == ["needs_review"] and "currency" in arvl[0].verification_notes


def test_every_stored_quote_is_the_canonical_text_at_its_offsets(truth: dict[str, object]) -> None:
    """The grounding invariant (M5-02 in the database) holds for every fact the engine emits."""
    from pipeline.facts.process import normalize

    router = Router({"gemini": Oracle(truth)}, quotas(["gemini"], rpd=10_000), FakeClock())  # type: ignore[arg-type]
    outcomes = run_corpus(router, truth=truth)  # type: ignore[arg-type]
    n = 0
    for name, o in outcomes.items():
        text = normalize(name, (SYN / name).read_bytes()).text
        for c, _ in o.facts:
            assert text[c.char_start : c.char_end] == c.quote
            n += 1
    assert n == 24
