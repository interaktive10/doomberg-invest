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
