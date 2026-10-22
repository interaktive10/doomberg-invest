"""Cassettes (BRIEF §9): a recording replays byte-for-byte, a changed request misses, and the hash manifest catches
hand edits. The committed cassettes, if any, match their manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.llm.cassettes import CASSETTE_DIR, Player, Recorder, manifest_problems, write_manifest
from pipeline.llm.providers.base import ProviderError, Request
from tests.llm.conftest import Scripted

REQ = Request("P-07", "gemini-small", "sys", "TITLE: a\nSUMMARY: b", {"type": "object"}, "json", "t", 0.0)


def test_record_then_replay(tmp_path: Path) -> None:
    rec = Recorder(Scripted("gemini", [{"categories": ["results"], "read_pdf": False}]), tmp_path)
    live = rec.complete(REQ)
    write_manifest(tmp_path)
    replay = Player("gemini", tmp_path).complete(REQ)
    assert replay.content == live.content and replay.tokens_in == live.tokens_in
    assert manifest_problems(tmp_path) == []
    with pytest.raises(ProviderError, match="cassette miss"):
        Player("gemini", tmp_path).complete(Request(**{**REQ.__dict__, "user": "TITLE: a\nSUMMARY: changed"}))
    with pytest.raises(ProviderError, match="cassette miss"):
        Player("groq", tmp_path).complete(REQ)  # recorded for gemini only


def test_a_hand_edit_breaks_the_manifest(tmp_path: Path) -> None:
    Recorder(Scripted("gemini"), tmp_path).complete(REQ)
    write_manifest(tmp_path)
    f = next(tmp_path.rglob("*.json"))
    f.write_text(f.read_text(encoding="utf-8").replace("other", "results"), encoding="utf-8")
    assert any("edited by hand" in p for p in manifest_problems(tmp_path))


def test_committed_cassettes_match_their_manifest() -> None:
    assert manifest_problems(CASSETTE_DIR) == []


def test_the_recorder_covers_every_m5_prompt_and_replays(tmp_path: Path) -> None:
    """M5 review R1-F7 (BRIEF §9): recording writes cassettes for P-01 (F-SYN) and for the P-02 and P-07 samples
    (P-03 is no longer called: docs/SPEC_ISSUES.md 50; P-06 went with the Capex Desk: 52), and a Player replays the
    samples with the same answers."""
    from pipeline.facts.evaluate import SYN, load_truth, run_corpus
    from pipeline.facts.samples import run_samples
    from pipeline.llm.router import Done, Router
    from tests.facts.fakes import MultiOracle
    from tests.llm.conftest import FakeClock, quotas

    truth = load_truth()
    rec = Router({"gemini": Recorder(MultiOracle(truth), tmp_path)}, quotas(["gemini"], rpd=10_000), FakeClock())
    run_corpus(rec, truth=truth)
    live = run_samples(rec, SYN, truth)
    write_manifest(tmp_path)
    assert {p.parent.name for p in tmp_path.rglob("*.json")} == {"P-01", "P-02", "P-07"}
    assert all(isinstance(r, Done) for rs in live.values() for r in rs) and all(live.values())
    play = Router({"gemini": Player("gemini", tmp_path)}, quotas(["gemini"], rpd=10_000), FakeClock())
    again = run_samples(play, SYN, truth)
    assert all(isinstance(r, Done) for rs in again.values() for r in rs)
    content = {k: [r.content for r in v if isinstance(r, Done)] for k, v in live.items()}
    assert {k: [r.content for r in v if isinstance(r, Done)] for k, v in again.items()} == content
    assert manifest_problems(tmp_path) == []
